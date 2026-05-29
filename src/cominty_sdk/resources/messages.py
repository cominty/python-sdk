from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Literal
from uuid import UUID

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk._qa import StreamEvent, is_stream_terminal_event
from cominty_sdk._streaming import stream_message_events
from cominty_sdk.config import DEFAULT_AGENT_ID, DEFAULT_POLL_INTERVAL, DEFAULT_POLL_TIMEOUT, TERMINAL_STATUSES
from cominty_sdk.exceptions import ComintyError, ComintyTimeoutError
from cominty_sdk.models.messages import (
    ChatOptions,
    ChatRequest,
    HumanMessage,
    MessageOut,
    parse_message_response,
)
from cominty_sdk.resources.threads import ThreadsResource


class MessagesResource:
    """Message send, stream, cancel, export, and polling operations."""

    def __init__(
        self,
        http: AsyncHTTPClient,
        *,
        default_agent_id: str | None,
        threads: ThreadsResource,
    ) -> None:
        self._http = http
        self._default_agent_id = default_agent_id
        self._threads = threads

    def _resolve_agent_id(self, agent_id: str | None) -> str:
        return agent_id or self._default_agent_id or DEFAULT_AGENT_ID

    async def send(
        self,
        thread_id: str | UUID,
        message: HumanMessage,
        *,
        agent_id: str | None = None,
    ) -> MessageOut:
        """Send a message in an existing thread."""
        request = ChatRequest(
            message=message,
            options=ChatOptions(agent_id=self._resolve_agent_id(agent_id)),
        )
        data = await self._http.request(
            "POST",
            f"/chat/{thread_id}",
            json=request.model_dump(exclude_none=True),
        )
        return parse_message_response(data)

    async def send_and_wait(
        self,
        thread_id: str | UUID,
        message: HumanMessage,
        *,
        agent_id: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_POLL_TIMEOUT,
        prefer_stream: bool = True,
    ) -> MessageOut:
        """Send a message and wait until the assistant response completes."""
        await self.send(thread_id, message, agent_id=agent_id)
        assistant = self.find_assistant_message(await self._threads.get(thread_id))
        return await self.wait_until_done(
            assistant.id,
            thread_id=thread_id,
            poll_interval=poll_interval,
            timeout=timeout,
            prefer_stream=prefer_stream,
        )

    @staticmethod
    def find_assistant_message(thread: object) -> MessageOut:
        from cominty_sdk.models.threads import ThreadOut

        assert isinstance(thread, ThreadOut)
        for message in reversed(thread.messages):
            if message.role == "assistant":
                return message
        raise ValueError("Thread returned without an assistant message.")

    async def wait_until_done(
        self,
        message_id: str | UUID,
        *,
        thread_id: str | UUID,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_POLL_TIMEOUT,
        prefer_stream: bool = True,
    ) -> MessageOut:
        """Wait until the message completes via stream, with poll fallback."""
        if prefer_stream:
            try:
                return await self._wait_until_done_via_stream(
                    message_id,
                    thread_id=thread_id,
                    timeout=timeout,
                )
            except ComintyTimeoutError:
                raise
            except Exception:
                pass
        return await self._wait_until_done_via_poll(
            message_id,
            thread_id=thread_id,
            poll_interval=poll_interval,
            timeout=timeout,
        )

    async def _wait_until_done_via_stream(
        self,
        message_id: str | UUID,
        *,
        thread_id: str | UUID,
        timeout: float,
    ) -> MessageOut:
        """Consume GET /chat/messages/{id}/stream until a terminal JSONL event."""
        deadline = asyncio.get_running_loop().time() + timeout
        saw_terminal = False
        event_count = 0
        try:
            async for event in self.stream(message_id):
                event_count += 1
                if is_stream_terminal_event(event):
                    saw_terminal = True
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    raise ComintyTimeoutError(
                        f"Timed out waiting for message {message_id} stream to complete."
                    )
        except ComintyTimeoutError:
            raise
        except Exception:
            pass

        message = await self._get_message_from_thread(message_id, thread_id=thread_id)
        thread = await self._threads.get(thread_id)
        if saw_terminal or event_count > 0:
            if self._is_message_complete(message, thread_live=thread.live):
                return message
        if saw_terminal:
            return message
        if event_count == 0:
            raise ComintyError(
                f"Stream ended without events for message {message_id}."
            )
        raise ComintyError(
            f"Stream ended without a terminal event for message {message_id}."
        )

    @staticmethod
    def _is_message_complete(message: MessageOut, *, thread_live: bool) -> bool:
        if message.is_terminal():
            return True
        if not thread_live and message.status.lower() in TERMINAL_STATUSES:
            return True
        return not thread_live and message.status.lower() not in {"pending", "running", "in_progress", "processing"}

    async def _wait_until_done_via_poll(
        self,
        message_id: str | UUID,
        *,
        thread_id: str | UUID,
        poll_interval: float,
        timeout: float,
    ) -> MessageOut:
        """Poll GET /chat/{thread_id} until the message reaches a terminal state."""
        deadline = asyncio.get_running_loop().time() + timeout
        message_uuid = UUID(str(message_id))
        while True:
            thread = await self._threads.get(thread_id)
            message = await self._get_message_from_thread(message_id, thread_id=thread_id)
            if message.id == message_uuid and self._is_message_complete(
                message,
                thread_live=thread.live,
            ):
                return message
            if asyncio.get_running_loop().time() >= deadline:
                raise ComintyTimeoutError(
                    f"Timed out waiting for message {message_id} to complete."
                )
            await asyncio.sleep(poll_interval)

    async def _get_message_from_thread(
        self,
        message_id: str | UUID,
        *,
        thread_id: str | UUID,
    ) -> MessageOut:
        message_uuid = UUID(str(message_id))
        thread = await self._threads.get(thread_id)
        for message in thread.messages:
            if message.id == message_uuid:
                return message
        raise ValueError(f"Message {message_id} not found in thread {thread_id}.")

    async def cancel(self, message_id: str | UUID) -> MessageOut:
        return await self._http.request_model(
            "POST",
            f"/chat/messages/{message_id}/cancel",
            MessageOut,
        )

    async def export(
        self,
        message_id: str | UUID,
        *,
        format: Literal["pdf", "docx"],
    ) -> bytes:
        return await self._http.request_bytes(
            "GET",
            f"/chat/messages/{message_id}/export",
            params={"format": format},
        )

    def stream(
        self,
        message_id: str | UUID,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream JSONL events for a message."""
        return stream_message_events(
            self._http,
            str(message_id),
            last_event_id=last_event_id,
        )
