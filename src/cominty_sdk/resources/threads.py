"""The threads resource: list, read, rename/star, and archive conversations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from ..models.chat import Thread, ThreadSummary, UpdateThreadParams

if TYPE_CHECKING:
    from .._transport import AsyncTransport

__all__ = ["ThreadsResource"]


class ThreadsResource:
    def __init__(self, transport: AsyncTransport, *, user_id: str) -> None:
        self._transport = transport
        self._user_id = user_id

    async def list(
        self,
        *,
        limit: int = 50,
        page: int = 0,
        terms: list[str] | None = None,
    ) -> list[ThreadSummary]:
        """List the current user's threads, newest first.

        Sends ``GET /chat`` scoped to the client's ``user_id``. ``terms`` filters
        by free-text search; ``limit``/``page`` paginate (page is zero-based).
        Returns lightweight :class:`~.models.chat.ThreadSummary` objects (no
        messages) — call :meth:`get` to load a thread's contents.
        """
        params: dict[str, object] = {
            "user_id": self._user_id,
            "limit": limit,
            "page": page,
        }
        if terms is not None:
            params["terms"] = terms
        raw = await self._transport.request("GET", "/chat", params=params)
        return [ThreadSummary.model_validate(item) for item in raw]

    async def get(self, thread_id: str | UUID) -> Thread:
        """Fetch a single thread with its full message history (``GET /chat/{id}``)."""
        raw = await self._transport.request("GET", f"/chat/{thread_id}")
        return Thread.model_validate(raw)

    async def update(
        self,
        thread_id: str | UUID,
        *,
        name: str | None = None,
        starred: bool | None = None,
    ) -> ThreadSummary:
        """Rename and/or (un)star a thread (``PUT /chat/{id}``).

        Partial: only the fields you pass are sent. Returns the updated thread
        as a :class:`~.models.chat.ThreadSummary` — this endpoint responds
        without the message history (unlike :meth:`get`).
        """
        body = UpdateThreadParams(name=name, starred=starred).model_dump(
            mode="json", exclude_none=True
        )
        raw = await self._transport.request("PUT", f"/chat/{thread_id}", json_body=body)
        return ThreadSummary.model_validate(raw)

    async def archive(self, thread_id: str | UUID) -> None:
        """Archive (soft-delete) a thread (``DELETE /chat/{id}``)."""
        await self._transport.request("DELETE", f"/chat/{thread_id}")
