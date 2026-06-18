from __future__ import annotations

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.models.usage import UsageReport


class UsageResource:
    """Chat usage reporting."""

    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http

    async def get(self) -> UsageReport:
        return await self._http.request_model("GET", "/chat/usage", UsageReport)
