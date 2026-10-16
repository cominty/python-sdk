from __future__ import annotations

import asyncio
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import quote
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from cominty_sdk.exceptions import InvalidParam, InvalidParams, SDKError
from cominty_sdk.models.capabilities import AgentCapabilities, MessageScope
from cominty_sdk.models.chat import (
    SERVER_DEFAULT,
    ConfirmFileUploadParams,
    ConversationFile,
    ExportFormat,
    ExportMessageParams,
    FileUploadPermission,
    MaxSteps,
    Message,
    MessageRole,
    StartChatParams,
    Thread,
    UploadFileParams,
)
from cominty_sdk.streaming import AssistantRun, StartedChat

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

__all__ = ["ChatResource"]

_DEFAULT_MIMETYPE = "application/octet-stream"
# CONVERSATION_FILE_MAX_SIZE of the hosted API (500 MiB). Checked locally so an oversized
# file fails before any request; a lower limit on another deployment is still reported
# by the storage backend.
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024

_url_adapter: TypeAdapter[str] = TypeAdapter(str)


class ChatResource:
    def __init__(self, transport: AsyncTransport, *, user_id: str) -> None:
        self._transport = transport
        self._user_id = user_id

    async def start(
        self,
        *,
        agent_id: str,
        message: str,
        name: str | None = None,
        file_ids: list[str] | None = None,
        thread_capabilities: AgentCapabilities | None = None,
        message_scope: MessageScope | None = None,
        max_steps: MaxSteps = SERVER_DEFAULT,
    ) -> StartedChat:
        """
        Start a new thread and return a handle on the assistant reply.

        Sends ``POST /chat``. Iterate the handle for progress events, or await
        ``run.text()`` / ``run.result()`` for the final answer.

        Args:
            agent_id (str): Managed agent that handles the thread.
            message (str): First user message.
            name (str | None): Thread title. Omit it to leave the thread unnamed.
            file_ids (list[str] | None): Uploaded file ids attached to the message.
            thread_capabilities (AgentCapabilities | None): Overrides some of the
                agent's capabilities for this thread, frozen for its lifetime. Each
                capability you pass replaces the agent's; the others keep the agent's
                value. A follow-up cannot change it. ``memory`` freezes the thread's
                memory bag. With capabilities but no ``memory``, the thread uses the
                agent's namespace, or runs without memory if the agent has none.
            message_scope (MessageScope | None): Turns a capability on
                or off, or narrows its allowlist, for this first message only.
            max_steps (MaxSteps): Cap on the agent's tool rounds for this
                message, an integer ``>= 1``. Leave it at ``SERVER_DEFAULT`` to let the
                server apply its own default (60 today, subject to change). Reaching the
                cap is not an error: the reply ends with ``status="success"`` and asks
                whether to continue. It is a rough order of magnitude, not an exact
                count, and does not limit tokens, cost, or duration.

        Returns:
            StartedChat: Handle for the in-progress assistant reply. ``thread`` is set.

        Raises:
            InvalidParams: A parameter failed local validation.
        """
        body = self._build_body(
            agent_id=agent_id,
            message=message,
            name=name,
            file_ids=file_ids,
            thread_capabilities=thread_capabilities,
            message_scope=message_scope,
            max_steps=max_steps,
            context="chat.start",
        )
        raw = await self._transport.request("POST", "/chat", json_body=body)
        thread = Thread.model_validate(raw)
        reply = _live_assistant_message(thread)
        return StartedChat(self._transport, reply.id, thread=thread)

    async def send(
        self,
        thread_id: str | UUID,
        *,
        message: str,
        agent_id: str,
        file_ids: list[str] | None = None,
        message_scope: MessageScope | None = None,
        max_steps: MaxSteps = SERVER_DEFAULT,
    ) -> AssistantRun:
        """
        Send a follow-up in an existing thread.

        Sends ``POST /chat/{thread_id}``. The response is the new assistant
        message, not the whole thread, so the returned run has no ``thread``.
        Pass a suggested option, or free text, as ``message`` to answer an
        agent question. The thread's memory bag, if any, was fixed at
        ``start``: a follow-up cannot change it.

        Args:
            thread_id (str | UUID): Thread to continue.
            message (str): Follow-up text.
            agent_id (str): Managed agent that handles this turn.
            file_ids (list[str] | None): Uploaded file ids attached to the message.
            message_scope (MessageScope | None): Turns a capability on
                or off, or narrows its allowlist, for this message only. Limited to
                what the thread was started with.
            max_steps (MaxSteps): Cap on the agent's tool rounds for this
                message, an integer ``>= 1``. The cap is per message, not per thread:
                a follow-up that leaves it at ``SERVER_DEFAULT`` runs with the server
                default (60 today), whatever earlier messages used. Pass an integer on
                every call to keep a custom cap. Typically the answer to a "do you want
                me to continue?" reply.

        Returns:
            AssistantRun: Handle for the new assistant reply.

        Raises:
            InvalidParams: A parameter failed local validation.
        """
        body = self._build_body(
            agent_id=agent_id,
            message=message,
            name=None,
            file_ids=file_ids,
            thread_capabilities=None,
            message_scope=message_scope,
            max_steps=max_steps,
            context="chat.send",
        )
        raw = await self._transport.request("POST", f"/chat/{thread_id}", json_body=body)
        reply = Message.model_validate(raw)
        return AssistantRun(self._transport, reply.id)

    def stream(self, message_id: str | UUID) -> AssistantRun:
        """
        Attach a handle to an assistant message that already exists.

        No request is sent until the handle is iterated or awaited.

        Args:
            message_id (str | UUID): Assistant message to stream.

        Returns:
            AssistantRun: Handle with no ``thread`` attached.
        """
        return AssistantRun(self._transport, _as_uuid(message_id))

    async def cancel(self, message_id: str | UUID) -> Message:
        """
        Cancel an assistant message that is still being generated.

        Sends ``POST /chat/messages/{message_id}/cancel``. The status flips to
        ``cancelled`` right away, and whatever the agent produced before that
        is kept in ``events``. Not idempotent: cancelling a message that is
        no longer running raises.

        Args:
            message_id (str | UUID): Assistant message to cancel.

        Returns:
            Message: The message, with ``status`` set to ``MessageStatus.cancelled``.

        Raises:
            ValueError: ``message_id`` is not a UUID.
            NotFoundError: No such message for this API key.
            APIError: The message is not live (400): it already finished, failed,
                or was already cancelled. User messages are never live.
        """
        raw = await self._transport.request("POST", f"/chat/messages/{_as_uuid(message_id)}/cancel")
        return Message.model_validate(raw)

    async def export(self, message_id: str | UUID, *, format: ExportFormat) -> bytes:
        """
        Export a finished message as a document.

        Sends ``GET /chat/messages/{message_id}/export``. The server renders the
        message content (Markdown) to the requested format and returns the file.
        No file name comes back: pick one yourself when you write the bytes.

        Args:
            message_id (str | UUID): Message to export.
            format (ExportFormat): ``"pdf"`` or ``"docx"``.

        Returns:
            bytes: The file content.

        Raises:
            ValueError: ``message_id`` is not a UUID.
            InvalidParams: ``format`` is not ``"pdf"`` or ``"docx"``.
            NotFoundError: No such message for this API key.
            APIError: The message has no content (400), for instance because it is
                still running.
        """
        try:
            params = ExportMessageParams(format=format)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="chat.export") from None
        return await self._transport.request_bytes(
            "GET",
            f"/chat/messages/{_as_uuid(message_id)}/export",
            params={"format": params.format},
        )

    async def upload_file(
        self,
        file: bytes | os.PathLike[str],
        *,
        filename: str | None = None,
        mimetype: str | None = None,
    ) -> ConversationFile:
        """
        Upload a file so a message can use it through ``file_ids``.

        Runs the whole presigned upload: ``GET /chat/files/upload`` asks for a
        permission, the bytes go straight to the storage backend (which never
        sees your API key), then ``POST /chat/files`` confirms the upload. Pass
        the returned ``id`` in ``file_ids`` of ``start`` or ``send`` (5 files per
        message at most). A file is at most 500 MiB, checked before anything is
        sent. The server also enforces a daily quota per organization, and another
        deployment may set a lower size limit: such a refusal raises ``APIError``
        with the storage reason. The whole file is held in memory.

        Args:
            file (bytes | os.PathLike[str]): The content, or a ``pathlib.Path`` to read it from.
                A plain ``str`` is rejected: it would be ambiguous between a path and text.
            filename (str | None): Name stored with the file, 1 to 255 characters
                without ``/``. Optional for a path (its name is used), required for bytes.
            mimetype (str | None): Content type. Guessed from the file name when
                omitted, falling back to ``application/octet-stream``.

        Returns:
            ConversationFile: The registered file. Its ``id`` is what ``file_ids`` takes.

        Raises:
            InvalidParams: ``file`` is neither bytes nor a path or is over 500 MiB,
                ``filename`` is missing for bytes or invalid, or ``mimetype`` is empty.
            OSError: ``file`` is a path that cannot be read (missing, a directory, ...).
            APIError: The storage backend or the API refused the upload.
            SDKError: The API answered with an upload permission the SDK cannot use.
        """
        source, resolved_name = _resolve_upload(file, filename)
        try:
            params = UploadFileParams(
                filename=resolved_name,
                mimetype=(
                    mimetype
                    if mimetype is not None
                    else mimetypes.guess_type(resolved_name)[0] or _DEFAULT_MIMETYPE
                ),
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="chat.upload_file") from None
        size = len(source) if isinstance(source, bytes) else source.stat().st_size
        if size > _MAX_UPLOAD_BYTES:
            raise _invalid_upload(
                "file",
                f"is {size} bytes, over the {_MAX_UPLOAD_BYTES} bytes (500 MiB) the API accepts",
            )
        # Read off the event loop: a large file would otherwise freeze every task.
        content = (
            source if isinstance(source, bytes) else await asyncio.to_thread(source.read_bytes)
        )

        raw = await self._transport.request(
            "GET", "/chat/files/upload", params=params.model_dump(mode="json")
        )
        try:
            permission = FileUploadPermission.model_validate(raw)
        except ValidationError:
            # Not InvalidParams, and not the raw error: its input holds the presigned fields.
            raise SDKError(
                "GET /chat/files/upload did not answer with a presigned upload "
                "(expected a url and fields containing a key)"
            ) from None
        etag = await self._transport.upload_to_presigned_url(
            permission.url,
            fields=permission.fields,
            filename=params.filename,
            content=content,
            mimetype=params.mimetype,
        )
        confirmation = ConfirmFileUploadParams(etag=etag, key=permission.fields["key"])
        confirmed = await self._transport.request(
            "POST", "/chat/files", json_body=confirmation.model_dump(mode="json")
        )
        return ConversationFile.model_validate(confirmed)

    async def download_file(self, file_id: str) -> bytes:
        """
        Download the content of a conversation file.

        Sends ``GET /chat/files/{file_id}``, which answers with a short-lived
        presigned URL (5 minutes), then fetches the bytes from it without your
        API key. Works for files you uploaded and files the agent produced. Not
        scoped to the client's ``user_id``: any file created through the API in
        the same organization can be downloaded. The whole file is held in memory.

        Args:
            file_id (str): ``ConversationFile.id`` of the file.

        Returns:
            bytes: The file content.

        Raises:
            ValueError: ``file_id`` is empty.
            NotFoundError: No such file for this API key.
            APIError: The storage backend refused the download.
            SDKError: The API did not answer with a download URL.
        """
        if not file_id:
            raise ValueError("file_id must be a non-empty string")
        raw = await self._transport.request("GET", f"/chat/files/{quote(file_id, safe='')}")
        try:
            url = _url_adapter.validate_python(raw)
        except ValidationError:
            raise SDKError(
                f"GET /chat/files/{file_id} did not answer with a download URL string"
            ) from None
        return await self._transport.download_from_presigned_url(url)

    def _build_body(
        self,
        *,
        agent_id: str,
        message: str,
        name: str | None,
        file_ids: list[str] | None,
        thread_capabilities: AgentCapabilities | None,
        message_scope: MessageScope | None,
        max_steps: MaxSteps,
        context: str,
    ) -> dict[str, object]:
        # Validate the whole request in one pass so error locations are rooted
        # consistently, then surface a clean SDK error instead of raw pydantic.
        # user_id is sourced from the client, not the caller.
        options: dict[str, object] = {
            "agent_id": agent_id,
            "user_id": self._user_id,
            "capabilities": thread_capabilities,
        }
        # The sentinel leaves the key out so the server default applies. An
        # explicit None is passed through on purpose: the model rejects it.
        if max_steps is not SERVER_DEFAULT:
            options["max_steps"] = max_steps
        try:
            params = StartChatParams.model_validate(
                {
                    "name": name,
                    "message": {
                        "content": message,
                        "file_ids": file_ids,
                        "scope": message_scope,
                    },
                    "options": options,
                }
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context=context) from None
        return params.model_dump(mode="json", exclude_none=True)


def _live_assistant_message(thread: Thread) -> Message:
    for msg in reversed(thread.messages):
        if msg.role == MessageRole.assistant:
            return msg
    raise SDKError("started thread contained no assistant message to stream")


def _resolve_upload(source: object, filename: str | None) -> tuple[bytes | Path, str]:
    # Typed as object on purpose: callers without a type checker can pass anything.
    if isinstance(source, bytes):
        if filename is None:
            raise _invalid_upload("filename", "required when `file` is bytes")
        return source, filename
    if isinstance(source, os.PathLike):
        path = Path(cast("os.PathLike[str]", source))
        return path, filename if filename is not None else path.name
    # A str is refused rather than read as a path: upload_file("hello") would otherwise
    # fail with a baffling FileNotFoundError.
    hint = ": wrap a path in Path(...)" if isinstance(source, str) else ""
    raise _invalid_upload(
        "file", f"expected bytes or a pathlib.Path, got {type(source).__name__}{hint}"
    )


def _invalid_upload(param: str, message: str) -> InvalidParams:
    # The offending value is left out: it may be a whole file, or a secret passed by mistake.
    error = InvalidParam(param=param, message=message, input=None)
    return InvalidParams(
        f"Invalid parameters for chat.upload_file:\n  - {param}: {message}", errors=[error]
    )


def _as_uuid(message_id: str | UUID) -> UUID:
    if isinstance(message_id, UUID):
        return message_id
    try:
        return UUID(message_id)
    except ValueError:
        raise ValueError(f"message_id must be a UUID, got {message_id!r}") from None
