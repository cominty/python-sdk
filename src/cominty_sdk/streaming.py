from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING
from uuid import UUID

from .events import AnyEvent, parse_event
from .exceptions import SDKError, StreamInterrupted
from .models.chat import Message, Question, Thread

if TYPE_CHECKING:
    from ._transport import AsyncTransport

__all__ = ["AssistantRun", "StartedChat"]

_SHUTDOWN_KEY = "__server_is_shutting_down"


class AssistantRun:
    """A live assistant message you can stream, or just await the result of.

    The stream is single-use: consume it once, either by iterating events or by
    calling :meth:`result` / :meth:`text`.
    """

    def __init__(
        self,
        transport: AsyncTransport,
        message_id: UUID,
        *,
        thread: Thread | None = None,
        last_event_id: str | None = None,
    ) -> None:
        self._transport = transport
        self._message_id = message_id
        self._thread = thread
        self._last_event_id = last_event_id
        self._terminal: Message | None = None
        self._consumed = False
        self._gen: AsyncGenerator[AnyEvent] | None = None

    @property
    def message_id(self) -> UUID:
        return self._message_id

    @property
    def thread(self) -> Thread | None:
        """
        Thread from the originating ``start`` call, when there is one.

        Returns:
            Thread | None: The thread, or ``None`` for ``chat.stream(message_id)``.
        """
        return self._thread

    def __aiter__(self) -> AsyncIterator[AnyEvent]:
        if self._gen is None:
            self._gen = self._stream()
        return self._gen

    async def _stream(self) -> AsyncGenerator[AnyEvent]:
        if self._consumed:
            # __aiter__ memoizes self._gen, so this never re-fires through the
            # public API: a defensive guard against calling this method directly.
            raise SDKError("this AssistantRun stream has already been consumed")  # pragma: no cover
        self._consumed = True

        headers: dict[str, str] = {}
        if self._last_event_id is not None:
            headers["last-event-id"] = self._last_event_id

        path = f"/chat/messages/{self._message_id}/stream"
        async with self._transport.stream_lines("GET", path, headers=headers) as lines:
            async for obj in lines:
                if _SHUTDOWN_KEY in obj:
                    partial = Message.model_validate(obj["partial"])
                    self._terminal = partial
                    raise StreamInterrupted(
                        "server shut down before the message completed",
                        partial=partial,
                    )
                if "correlation_id" in obj:
                    event = parse_event(obj)
                    self._last_event_id = event.id
                    yield event
                    continue
                # No correlation_id and not a shutdown envelope -> terminal
                # message snapshot. The stream is over.
                self._terminal = Message.model_validate(obj)
                return

    async def result(self) -> Message:
        """
        Drain the stream if needed and return the final message.

        Returns:
            Message: The terminal assistant message.

        Raises:
            StreamInterrupted: The server shut down before the message completed.
            SDKError: The stream was already partially consumed, or it ended
                without a terminal message.
        """
        if self._terminal is not None:
            return self._terminal
        if self._consumed:
            raise SDKError("stream was partially consumed; the final message is unavailable")
        async for _ in self:
            pass
        if self._terminal is None:
            raise SDKError("stream ended without a terminal message")
        return self._terminal

    async def text(self) -> str:
        """
        The assistant's final reply text.

        Returns:
            str: ``result().content``.
        """
        return (await self.result()).content

    async def questions(self) -> list[Question]:
        """
        Clarifying questions the agent is asking, if any.

        An empty list means the agent gave a final answer. Answer a question by
        sending the chosen option, or free text, as the next message.

        Returns:
            list[Question]: Each item has a ``prompt`` and suggested ``options``.

        Examples:
            await client.chat.send(
                run.thread.id,
                message=picked,
                agent_id="agt_1",
            )
        """
        return (await self.result()).questions or []

    async def aclose(self) -> None:
        if self._gen is not None:
            await self._gen.aclose()

    async def __aenter__(self) -> AssistantRun:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


class StartedChat(AssistantRun):
    """The run returned by :meth:`~.resources.chat.ChatResource.start`.

    Identical to :class:`AssistantRun`, but :attr:`thread` is guaranteed present
    (the originating ``POST /chat`` always returns one), so callers don't have to
    guard against ``None``.
    """

    @property
    def thread(self) -> Thread:  # type: ignore[override]  # narrows Thread | None
        assert self._thread is not None  # always set by ChatResource.start
        return self._thread
