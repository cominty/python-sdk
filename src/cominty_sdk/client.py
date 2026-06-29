"""The async client — the one object users construct."""

from __future__ import annotations

from types import TracebackType

from typing_extensions import Self

from ._config import Config
from ._transport import AsyncTransport
from .resources.chat import ChatResource

__all__ = ["AsyncCominty"]


class AsyncCominty:
    """Async client for the Cominty API.

    Construct once, reuse, and close when done — ideally via ``async with``::

        async with AsyncCominty(api_token="...") as client:
            run = await client.chat.start(
                agent_id="agt_1", message="Hello", user_id="u_1",
            )
            async for event in run:
                ...
            print(await run.text())
    """

    def __init__(
        self,
        *,
        api_token: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._config = Config.resolve(
            api_token=api_token, base_url=base_url, timeout=timeout
        )
        self._transport = AsyncTransport(self._config)
        self.chat = ChatResource(self._transport)

    @property
    def base_url(self) -> str:
        """The resolved API base URL this client talks to."""
        return self._config.base_url

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._transport.aclose()
