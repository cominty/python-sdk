from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError

from cominty_sdk.exceptions import InvalidParams, SDKError
from cominty_sdk.models.chat import (
    SERVER_DEFAULT,
    DisablableTool,
    MaxSteps,
    Message,
    MessageRole,
    StartChatParams,
    Thread,
)
from cominty_sdk.streaming import AssistantRun, StartedChat

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

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
        memory_namespace: str | None = None,
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
            source_ids (list[int] | None): Connected source ids attached to the message.
            document_ids (list[str] | None): Document ids attached to the message.
            disabled_tools (list[DisablableTool] | None): Tools the agent must not use.
            memory_namespace (str | None): Memory bag for this thread, frozen for its
                lifetime. Omit to run with no memory tools, unless the agent has its
                own namespace set. A follow-up cannot change it.
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
            source_ids=source_ids,
            document_ids=document_ids,
            disabled_tools=disabled_tools,
            memory_namespace=memory_namespace,
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
        source_ids: list[int] | None = None,
        document_ids: list[str] | None = None,
        disabled_tools: list[DisablableTool] | None = None,
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
            source_ids (list[int] | None): Connected source ids attached to the message.
            document_ids (list[str] | None): Document ids attached to the message.
            disabled_tools (list[DisablableTool] | None): Tools the agent must not use.
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
            source_ids=source_ids,
            document_ids=document_ids,
            disabled_tools=disabled_tools,
            memory_namespace=None,
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
        memory_namespace: str | None,
        max_steps: MaxSteps,
        context: str,
    ) -> dict[str, object]:
        # Validate the whole request in one pass so error locations are rooted
        # consistently, then surface a clean SDK error instead of raw pydantic.
        # user_id is sourced from the client, not the caller.
        options: dict[str, object] = {
            "agent_id": agent_id,
            "user_id": self._user_id,
            "memory_namespace": memory_namespace,
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
                        "source_ids": source_ids,
                        "document_ids": document_ids,
                        "disabled_tools": disabled_tools,
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


def _as_uuid(message_id: str | UUID) -> UUID:
    return message_id if isinstance(message_id, UUID) else UUID(message_id)
