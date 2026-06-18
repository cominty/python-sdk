from __future__ import annotations

from uuid import UUID

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.models.threads import ThreadOut, ThreadSummaryOut, ThreadUpdate


class ThreadsResource:
    """Thread CRUD operations."""

    def __init__(
        self,
        http: AsyncHTTPClient,
        *,
        default_user_id: str | None = None,
        api_mode: bool = False,
    ) -> None:
        self._http = http
        self._default_user_id = default_user_id
        self._api_mode = api_mode

    def _resolve_user_id(self, user_id: str | None) -> str | None:
        resolved = user_id or self._default_user_id
        if self._api_mode and not resolved:
            raise ValueError(
                "user_id is required in API mode. Pass user_id= or set COMINTY_USER_ID."
            )
        return resolved

    async def list(
        self,
        *,
        user_id: str | None = None,
        limit: int = 50,
        page: int = 0,
        terms: list[str] | None = None,
    ) -> list[ThreadSummaryOut]:
        params: dict[str, object] = {"limit": limit, "page": page}
        resolved_user_id = self._resolve_user_id(user_id)
        if resolved_user_id is not None:
            params["user_id"] = resolved_user_id
        if terms is not None:
            params["terms"] = terms
        data = await self._http.request("GET", "/chat", params=params)
        return [ThreadSummaryOut.model_validate(item) for item in data]

    async def get(self, thread_id: str | UUID) -> ThreadOut:
        return await self._http.request_model("GET", f"/chat/{thread_id}", ThreadOut)

    async def update(
        self,
        thread_id: str | UUID,
        *,
        name: str | None = None,
        starred: bool | None = None,
    ) -> ThreadOut:
        payload = ThreadUpdate(name=name, starred=starred)
        return await self._http.request_model(
            "PUT",
            f"/chat/{thread_id}",
            ThreadOut,
            json=payload.model_dump(exclude_none=True),
        )

    async def archive(self, thread_id: str | UUID) -> None:
        await self._http.request("DELETE", f"/chat/{thread_id}")
