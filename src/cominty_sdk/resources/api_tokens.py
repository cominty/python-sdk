from __future__ import annotations

from uuid import UUID

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.models.api_tokens import ApiTokenCreated, ApiTokenOut


class ApiTokensResource:
    """Manage API tokens (requires admin Clerk session token)."""

    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http

    async def create(self, name: str) -> ApiTokenCreated:
        """Create an API token. The access_token secret is only returned once."""
        return await self._http.request_model(
            "POST",
            "/api-tokens",
            ApiTokenCreated,
            json={"name": name},
        )

    async def list(self) -> list[ApiTokenOut]:
        """List API token metadata (without secrets)."""
        data = await self._http.request("GET", "/api-tokens")
        return [ApiTokenOut.model_validate(item) for item in data]

    async def revoke(self, token_id: str | UUID) -> None:
        await self._http.request("DELETE", f"/api-tokens/{token_id}")
