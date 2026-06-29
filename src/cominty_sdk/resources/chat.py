"""The chat resource: start a thread and stream the assistant's reply."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError

from ..exceptions import InvalidParams, SDKError
from ..models.chat import (
    DisablableTool,
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
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def start(
        self,
        *,
        agent_id: str,
        message: str,
        user_id: str,
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
        # Validate the whole request in one pass so error locations are rooted
        # consistently, then surface a clean SDK error instead of raw pydantic.
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
                    "options": {"agent_id": agent_id, "user_id": user_id},
                }
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="chat.start") from None
        body = params.model_dump(mode="json", exclude_none=True)
        raw = await self._transport.request("POST", "/chat", json_body=body)
        thread = Thread.model_validate(raw)
        reply = _live_assistant_message(thread)
        return StartedChat(self._transport, reply.id, thread=thread)

    def stream(self, message_id: UUID) -> AssistantRun:
        """Stream an existing assistant message by id (no I/O until consumed)."""
        return AssistantRun(self._transport, message_id)


def _live_assistant_message(thread: Thread) -> Message:
    for msg in reversed(thread.messages):
        if msg.role == MessageRole.assistant:
            return msg
    raise SDKError("started thread contained no assistant message to stream")
