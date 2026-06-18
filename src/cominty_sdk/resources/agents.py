from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.exceptions import AuthenticationError, ComintyAPIError
from cominty_sdk.models.agents import AgentOut

if TYPE_CHECKING:
    from cominty_sdk.resources.threads import ThreadsResource


class AgentsResource:
    """List org-managed agents (GET /agents) with fallbacks for API-token mode."""

    def __init__(
        self,
        http: AsyncHTTPClient,
        *,
        admin_http: AsyncHTTPClient | None = None,
        threads: ThreadsResource | None = None,
        default_user_id: str | None = None,
    ) -> None:
        self._http = http
        self._admin_http = admin_http
        self._threads = threads
        self._default_user_id = default_user_id

    async def _fetch(self, http: AsyncHTTPClient) -> list[AgentOut]:
        data = await http.request("GET", "/agents")
        if not isinstance(data, list):
            return []
        return [AgentOut.model_validate(item) for item in data]

    async def list(self) -> list[AgentOut]:
        """Return agents from GET /agents (org admin API).

        Tries the chat/API-token client first, then the admin session client if configured.
        Raises the last error when both fail.
        """
        last_error: ComintyAPIError | None = None
        # Prefer admin/session client for GET /agents (org management API).
        for http in (self._admin_http, self._http):
            if http is None:
                continue
            try:
                return await self._fetch(http)
            except ComintyAPIError as exc:
                last_error = exc
                if exc.status_code in {401, 403, 404}:
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise AuthenticationError(
            "No HTTP client available for GET /agents. "
            "Set COMINTY_API_KEY or COMINTY_SESSION_TOKEN.",
        )

    async def list_discovered(
        self,
        *,
        user_id: str | None = None,
        limit: int = 50,
    ) -> builtins.list[AgentOut]:
        """Infer agent ids/names from recent chat threads (API-token friendly)."""
        if self._threads is None:
            raise ValueError("ThreadsResource is required for list_discovered().")
        summaries = await self._threads.list(
            user_id=user_id or self._default_user_id,
            limit=limit,
        )
        seen: dict[str, AgentOut] = {}
        for thread in summaries:
            agent = thread.agent
            if agent.id in seen:
                continue
            seen[agent.id] = AgentOut(
                id=agent.id,
                name=agent.name,
                mode="discovered",
                description="Inferred from GET /chat thread history (not GET /agents).",
                instructions=None,
                owner="",
            )
        return list(seen.values())
