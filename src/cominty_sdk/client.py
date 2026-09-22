from __future__ import annotations

from types import TracebackType

from typing_extensions import Self

from ._config import Config
from ._transport import AsyncTransport
from .models.chat import validate_user_id
from .resources.chat import ChatResource
from .resources.memory import MemoryResource
from .resources.threads import ThreadsResource

__all__ = ["AsyncCominty"]


class AsyncCominty:
    """Async client for the Cominty API."""

    def __init__(
        self,
        *,
        user_id: str | None = None,
        api_token: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """
        Build a client. ``user_id`` is applied to every request.

        Resource methods do not take ``user_id``. Construct once, reuse, and
        close with ``async with`` or :meth:`close`.

        Args:
            user_id (str | None): End user every call acts on behalf of.
                Falls back to ``COMINTY_USER_ID``.
            api_token (str | None): API key. Falls back to ``COMINTY_API_KEY``.
            base_url (str | None): API origin. Falls back to ``COMINTY_BASE_URL``,
                then ``https://ds.cominty.com``.
            timeout (float | None): Request timeout in seconds. Default is 60.

        Raises:
            ValueError: ``api_token`` or ``user_id`` is missing, or ``user_id``
                is not a Cominty user id.

        Examples:
            async with AsyncCominty(api_token="...", user_id="user_...") as client:
                run = await client.chat.start(agent_id="agt_1", message="Hello")
                print(await run.text())
        """
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
        self.memory = MemoryResource(self._transport, user_id=self._config.user_id)

    @property
    def user_id(self) -> str:
        """
        End-user id applied to every request.

        Returns:
            str: The resolved ``user_id``.
        """
        return self._config.user_id

    @property
    def base_url(self) -> str:
        """
        API origin this client talks to, without a trailing slash.

        Returns:
            str: The resolved base URL.
        """
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