"""The agents resource: list, create, read, update, delete, and model assignment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from ..exceptions import InvalidParams
from ..models.agents import (
    CreateAgentParams,
    CustomAgent,
    CustomAgentSummary,
    LLMModelSummary,
    SetAgentModelsParams,
    UpdateAgentParams,
)

if TYPE_CHECKING:
    from .._transport import AsyncTransport

__all__ = ["AgentsResource"]

AgentScope = Literal["organization", "private"]


class AgentsResource:
    """Manage custom agents via ``/agents`` (API-key auth; no ``user_id`` query)."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(self) -> list[CustomAgentSummary]:
        """List agents visible to the API key (``GET /agents``)."""
        raw = await self._transport.request("GET", "/agents")
        return [CustomAgentSummary.model_validate(item) for item in raw]

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        instructions: str | None = None,
        scope: AgentScope = "private",
        execution_options: dict[str, Any] | None = None,
        allow_execution_options_override: bool = False,
        model_ids: list[str] | None = None,
    ) -> CustomAgent:
        """Create a custom agent (``POST /agents``)."""
        try:
            params = CreateAgentParams(
                name=name,
                description=description,
                instructions=instructions,
                scope=scope,
                execution_options=execution_options,
                allow_execution_options_override=allow_execution_options_override,
                model_ids=model_ids,
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="agents.create") from None
        body = params.model_dump(mode="json", exclude_none=True)
        raw = await self._transport.request("POST", "/agents", json_body=body)
        return CustomAgent.model_validate(raw)

    async def get(self, agent_id: str) -> CustomAgent:
        """Fetch one agent with instructions and models (``GET /agents/{id}``)."""
        raw = await self._transport.request("GET", f"/agents/{agent_id}")
        return CustomAgent.model_validate(raw)

    async def update(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        execution_options: dict[str, Any] | None = None,
        allow_execution_options_override: bool | None = None,
    ) -> CustomAgent:
        """Partial update (``PATCH /agents/{id}``). Only passed fields are sent."""
        try:
            params = UpdateAgentParams(
                name=name,
                description=description,
                instructions=instructions,
                execution_options=execution_options,
                allow_execution_options_override=allow_execution_options_override,
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="agents.update") from None
        body = params.model_dump(mode="json", exclude_none=True)
        raw = await self._transport.request("PATCH", f"/agents/{agent_id}", json_body=body)
        return CustomAgent.model_validate(raw)

    async def delete(self, agent_id: str) -> None:
        """Delete a custom agent (``DELETE /agents/{id}``)."""
        await self._transport.request("DELETE", f"/agents/{agent_id}")

    async def list_models(self) -> list[LLMModelSummary]:
        """List models selectable for custom agents (``GET /agents/models``)."""
        raw = await self._transport.request("GET", "/agents/models")
        return [LLMModelSummary.model_validate(item) for item in raw]

    async def set_models(self, agent_id: str, *, model_ids: list[str]) -> CustomAgent:
        """Replace an agent's model chain (``PUT /agents/{id}/models``)."""
        try:
            params = SetAgentModelsParams(model_ids=model_ids)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="agents.set_models") from None
        body = params.model_dump(mode="json")
        raw = await self._transport.request("PUT", f"/agents/{agent_id}/models", json_body=body)
        return CustomAgent.model_validate(raw)
