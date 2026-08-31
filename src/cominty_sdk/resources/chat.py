"""The chat resource: start a thread and stream the assistant's reply."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import ValidationError

from ..exceptions import InvalidParams, SDKError
from ..models.chat import (
    ConversationFile,
    DisablableTool,
    FileUploadConfirmation,
    FileUploadPermission,
    FileUploadRequest,
    Message,
    MessageRole,
    StartChatParams,
    Thread,
)
from ..streaming import AssistantRun, StartedChat

if TYPE_CHECKING:
    from .._transport import AsyncTransport

__all__ = ["ChatResource"]


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
        source_ids: list[int] | None = None,
        document_ids: list[str] | None = None,
        disabled_tools: list[DisablableTool] | None = None,
    ) -> StartedChat:
        """Start a new thread with a first user message.

        Sends ``POST /chat``, then returns an :class:`~.streaming.AssistantRun`
        bound to the in-progress assistant reply. Iterate it for progress events,
        or ``await run.text()`` / ``await run.result()`` for the final answer.
        """
        body = self._build_body(
            agent_id=agent_id,
            message=message,
            name=name,
            file_ids=file_ids,
            source_ids=source_ids,
            document_ids=document_ids,
            disabled_tools=disabled_tools,
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
        source_ids: list[int] | None = None,
        document_ids: list[str] | None = None,
        disabled_tools: list[DisablableTool] | None = None,
    ) -> AssistantRun:
        """Send a follow-up message in an existing thread.

        The mirror of :meth:`start` for an ongoing conversation: sends
        ``POST /chat/{thread_id}`` and returns a streamable run for the new
        assistant reply. Use this to answer an agent's :class:`~.models.chat.Question`
        — pass the chosen option (or free text) as ``message``.

        Unlike :meth:`start`, this endpoint returns the new assistant
        :class:`~.models.chat.Message` directly (not the whole thread), so the
        returned :class:`~.streaming.AssistantRun` has no ``.thread`` — you
        already hold the ``thread_id``, and ``threads.get(thread_id)`` fetches the
        rest if needed.
        """
        body = self._build_body(
            agent_id=agent_id,
            message=message,
            name=None,
            file_ids=file_ids,
            source_ids=source_ids,
            document_ids=document_ids,
            disabled_tools=disabled_tools,
            context="chat.send",
        )
        raw = await self._transport.request(
            "POST", f"/chat/{thread_id}", json_body=body
        )
        reply = Message.model_validate(raw)
        return AssistantRun(self._transport, reply.id)

    def stream(self, message_id: str | UUID) -> AssistantRun:
        """Stream an existing assistant message by id (no I/O until consumed)."""
        return AssistantRun(self._transport, _as_uuid(message_id))

    async def cancel(self, message_id: str | UUID) -> Message:
        """Cancel an in-flight assistant message (``POST /chat/messages/{id}/cancel``).

        Returns the updated :class:`~.models.chat.Message`, with
        ``status`` set to :attr:`~.models.chat.MessageStatus.cancelled`.
        """
        raw = await self._transport.request(
            "POST", f"/chat/messages/{message_id}/cancel"
        )
        return Message.model_validate(raw)

    async def export(
        self, message_id: str | UUID, *, format: Literal["pdf", "docx"]
    ) -> bytes:
        return await self._transport.request_bytes(
            "GET",
            f"/chat/messages/{message_id}/export",
            params={"format": format},
        )

    async def upload_file(
        self, content: bytes | str | Path, *, filename: str, mimetype: str
    ) -> ConversationFile:
        """Upload a file for later use in ``file_ids=[...]`` on :meth:`start`/:meth:`send`.

        ``content`` is either raw bytes or a path to read them from.

        Orchestrates the full flow: requests a presigned upload permission
        (``GET /chat/files/upload``), uploads the content directly to the
        returned storage URL, then confirms the upload with Cominty
        (``POST /chat/files``). Returns the registered file — its ``.id`` is
        what feeds ``file_ids=[...]``.
        """
        if isinstance(content, (str, Path)):
            content = Path(content).read_bytes()

        try:
            validated = FileUploadRequest(filename=filename, mimetype=mimetype)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(
                exc, context="chat.upload_file"
            ) from None

        raw = await self._transport.request(
            "GET",
            "/chat/files/upload",
            params={"filename": validated.filename, "mimetype": validated.mimetype},
        )
        permission = FileUploadPermission.model_validate(raw)

        etag = await self._transport.upload_to_presigned_url(
            permission.url,
            fields=permission.fields,
            filename=validated.filename,
            content=content,
            mimetype=validated.mimetype,
        )

        confirmation = FileUploadConfirmation(etag=etag, key=permission.fields["key"])
        raw = await self._transport.request(
            "POST", "/chat/files", json_body=confirmation.model_dump(mode="json")
        )
        return ConversationFile.model_validate(raw)

    async def download_file(self, file_pid: str) -> bytes:
        """Download a conversation file's content (``GET /chat/files/{file_pid}``).

        The endpoint returns a short-lived presigned URL, not the file
        content itself — this fetches from it and returns the raw bytes.
        """
        presigned_url = await self._transport.request("GET", f"/chat/files/{file_pid}")
        return await self._transport.download_from_presigned_url(presigned_url)

    def _build_body(
        self,
        *,
        agent_id: str,
        message: str,
        name: str | None,
        file_ids: list[str] | None,
        source_ids: list[int] | None,
        document_ids: list[str] | None,
        disabled_tools: list[DisablableTool] | None,
        context: str,
    ) -> dict[str, object]:
        # Validate the whole request in one pass so error locations are rooted
        # consistently, then surface a clean SDK error instead of raw pydantic.
        # user_id is sourced from the client, not the caller.
        try:
            params = StartChatParams.model_validate(
                {
                    "name": name,
                    "message": {
                        "content": message,
                        "file_ids": file_ids,
                        "source_ids": source_ids,
                        "document_ids": document_ids,
                        "disabled_tools": disabled_tools,
                    },
                    "options": {"agent_id": agent_id, "user_id": self._user_id},
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


def _as_uuid(message_id: str | UUID) -> UUID:
    return message_id if isinstance(message_id, UUID) else UUID(message_id)
