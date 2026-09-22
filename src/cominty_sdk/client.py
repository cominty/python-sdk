"""The async client — the one object users construct."""

from __future__ import annotations

from types import TracebackType

from typing_extensions import Self

from ._config import Config
from ._transport import AsyncTransport
from .models.chat import validate_user_id
from .resources.agents import AgentsResource
from .resources.chat import ChatResource
from .resources.threads import ThreadsResource

__all__ = ["AsyncCominty"]


class AsyncCominty:
    """Async client for the Cominty API.

    ``user_id`` identifies the end user every call acts on behalf of. It is set
    once here (or via ``COMINTY_USER_ID``) and applied to every request, so
    resource methods never take it.

    Construct once, reuse, and close when done — ideally via ``async with``::

        async with AsyncCominty(api_token="...", user_id="user_...") as client:
            run = await client.chat.start(agent_id="agt_1", message="Hello")
            async for event in run:
                ...
            print(await run.text())
    """

    def __init__(
        self,
        *,
        user_id: str | None = None,
        api_token: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._config = Config.resolve(
            api_token=api_token,
            user_id=user_id,
            base_url=base_url,
            timeout=timeout,
        )
        # Fail fast on a malformed user id instead of as a server 400/404 later.
        try:
            validate_user_id(self._config.user_id)
        except ValueError as exc:
            raise ValueError(f"invalid user_id: {exc}") from None
        self._transport = AsyncTransport(self._config)
        self.chat = ChatResource(self._transport, user_id=self._config.user_id)
        self.threads = ThreadsResource(self._transport, user_id=self._config.user_id)
        self.agents = AgentsResource(self._transport)

    @property
    def user_id(self) -> str:
        """The end-user id every request is made on behalf of."""
        return self._config.user_id

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
