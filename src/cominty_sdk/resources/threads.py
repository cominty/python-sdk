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
        """
        List the current user's threads, newest first.

        Sends ``GET /chat`` scoped to the client's ``user_id``. Summaries do not
        include messages. Call :meth:`get` to load a thread's contents.

        Args:
            limit (int): Page size. Default is 50.
            page (int): Zero-based page index. Default is 0.
            terms (list[str] | None): Free-text search terms. Omit to list everything.

        Returns:
            list[ThreadSummary]: Matching thread summaries.
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
        """
        Fetch one thread, including its messages.

        Sends ``GET /chat/{thread_id}``.

        Args:
            thread_id (str | UUID): Thread to load.

        Returns:
            Thread: The thread and its message history.
        """
        raw = await self._transport.request("GET", f"/chat/{thread_id}")
        return Thread.model_validate(raw)

    async def update(
        self,
        thread_id: str | UUID,
        *,
        name: str | None = None,
        starred: bool | None = None,
    ) -> ThreadSummary:
        """
        Rename and/or star a thread.

        Sends ``PUT /chat/{thread_id}``. Only the fields you pass are sent.
        The response is a summary, without messages.

        Args:
            thread_id (str | UUID): Thread to update.
            name (str | None): New title. Omit it to leave the title unchanged.
            starred (bool | None): Starred flag. Omit it to leave the flag unchanged.

        Returns:
            ThreadSummary: The updated thread, without messages.
        """
        body = UpdateThreadParams(name=name, starred=starred).model_dump(
            mode="json", exclude_none=True
        )
        raw = await self._transport.request("PUT", f"/chat/{thread_id}", json_body=body)
        return ThreadSummary.model_validate(raw)

    async def archive(self, thread_id: str | UUID) -> None:
        """
        Archive a thread. This is a soft delete.

        Sends ``DELETE /chat/{thread_id}``.

        Args:
            thread_id (str | UUID): Thread to archive.

        Returns:
            None: The thread is archived.
        """
        await self._transport.request("DELETE", f"/chat/{thread_id}")
