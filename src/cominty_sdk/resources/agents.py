from __future__ import annotations

from typing import TYPE_CHECKING, Union
from urllib.parse import quote

from pydantic import ValidationError

from cominty_sdk.exceptions import InvalidParams
from cominty_sdk.models.agents import (
    AgentOut,
    AgentSummaryOut,
    CreateAgentParams,
    LLMModelSummaryOut,
    SetAgentModelsParams,
    UpdateAgentParams,
)
from cominty_sdk.models.capabilities import AgentCapabilities
from cominty_sdk.models.common import Scope

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

__all__ = ["AgentsResource"]

# Ellipsis distinguishes "argument omitted" from "passed as None" on update(), as in
# resources/memory.py. "ellipsis" is typeshed's name for the type of `...`.
_OptionalStr = Union[str, "ellipsis"]  # noqa: F821 - typeshed-only, not a real name
_OptionalNullableStr = Union[str, None, "ellipsis"]  # noqa: F821
_OptionalScope = Union[Scope, "ellipsis"]  # noqa: F821
_OptionalCapabilities = Union[AgentCapabilities, None, "ellipsis"]  # noqa: F821
_OptionalBool = Union[bool, "ellipsis"]  # noqa: F821


class AgentsResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(self) -> list[AgentSummaryOut]:
        """
        List the agents this API key can use.

        Sends ``GET /agents``: the built-in Cominty agents (``managed=True``), the
        organization-scoped agents, and the agents owned by the key's creator.

        Returns:
            list[AgentSummaryOut]: Summaries without ``instructions`` or ``models``.
        """
        raw = await self._transport.request("GET", "/agents")
        return [AgentSummaryOut.model_validate(item) for item in raw]

    async def list_models(self) -> list[LLMModelSummaryOut]:
        """
        List the language models a custom agent can be given.

        Sends ``GET /agents/models``. Pass the ids to :meth:`create` or :meth:`set_models`.

        Returns:
            list[LLMModelSummaryOut]: The selectable models.
        """
        raw = await self._transport.request("GET", "/agents/models")
        return [LLMModelSummaryOut.model_validate(item) for item in raw]

    async def get(self, agent_id: str) -> AgentOut:
        """
        Fetch one agent, including its instructions and model chain.

        Sends ``GET /agents/{agent_id}``.

        Args:
            agent_id (str): The agent's id, as in ``AgentSummaryOut.id``.

        Returns:
            AgentOut: The agent.

        Raises:
            NotFoundError: No such agent, or not visible to this API key.
        """
        raw = await self._transport.request("GET", f"/agents/{_path(agent_id)}")
        return AgentOut.model_validate(raw)

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        instructions: str | None = None,
        scope: Scope = "private",
        capabilities: AgentCapabilities | None = None,
        allow_execution_options_override: bool = False,
        model_ids: list[str] | None = None,
    ) -> AgentOut:
        """
        Create a custom agent.

        Sends ``POST /agents``. The agent is owned by the admin who minted the API key
        (``AgentOut.owner``) and lives in the key's organization.

        Args:
            name (str): Display name.
            description (str | None): Short description, at most 500 characters.
            instructions (str | None): System instructions, at most 30 000 characters.
            scope (Scope): ``"private"`` (the owner only, default) or ``"organization"``.
            capabilities (AgentCapabilities | None): Tools the agent may use. Omitted
                capabilities keep the platform defaults. ``capabilities.memory`` sets
                the agent's memory namespace.
            allow_execution_options_override (bool): Let a chat override the agent's
                tool configuration. Default is ``False``.
            model_ids (list[str] | None): Model chain in failover order, from
                :meth:`list_models`. Omit for the organization's default chain.

        Returns:
            AgentOut: The new agent.

        Raises:
            InvalidParams: A parameter failed local validation (empty ``name``, a text
                over its limit, an empty ``model_ids``).
            APIError: ``capabilities.skills.include`` names a skill the key cannot
                read (422).
        """
        try:
            params = CreateAgentParams(
                name=name,
                description=description,
                instructions=instructions,
                scope=scope,
                capabilities=capabilities,
                allow_execution_options_override=allow_execution_options_override,
                model_ids=model_ids,
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="agents.create") from None
        raw = await self._transport.request(
            "POST", "/agents", json_body=params.model_dump(mode="json", exclude_none=True)
        )
        return AgentOut.model_validate(raw)

    async def update(
        self,
        agent_id: str,
        *,
        name: _OptionalStr = ...,
        description: _OptionalNullableStr = ...,
        instructions: _OptionalNullableStr = ...,
        scope: _OptionalScope = ...,
        capabilities: _OptionalCapabilities = ...,
        allow_execution_options_override: _OptionalBool = ...,
    ) -> AgentOut:
        """
        Update some fields of a custom agent.

        Sends ``PUT /agents/{agent_id}``. Only the arguments you pass are sent; omit
        one to leave it unchanged. ``description``, ``instructions`` and
        ``capabilities`` accept ``None`` to clear them. A ``capabilities`` object is
        merged key by key into the agent's: each capability you pass replaces the
        stored one, the others stay.

        Args:
            agent_id (str): Agent to update.
            name (str): New display name.
            description (str | None): New description, or ``None`` to clear it.
            instructions (str | None): New instructions, or ``None`` to clear them.
            scope (Scope): ``"private"`` or ``"organization"``.
            capabilities (AgentCapabilities | None): Capabilities to replace, or
                ``None`` to clear them all.
            allow_execution_options_override (bool): New value of the flag.

        Returns:
            AgentOut: The updated agent.

        Raises:
            InvalidParams: No argument was passed, a value failed validation, or
                ``name``/``scope``/``allow_execution_options_override`` was ``None``.
            NotFoundError: No such agent, or not writable by this API key (built-in
                agents included).
        """
        fields: dict[str, object] = {}
        for key, value in (
            ("name", name),
            ("description", description),
            ("instructions", instructions),
            ("scope", scope),
            ("capabilities", capabilities),
            ("allow_execution_options_override", allow_execution_options_override),
        ):
            if value is not ...:
                fields[key] = value
        try:
            params = UpdateAgentParams.model_validate(fields)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="agents.update") from None
        raw = await self._transport.request(
            "PUT",
            f"/agents/{_path(agent_id)}",
            json_body=params.model_dump(mode="json", exclude_unset=True),
        )
        return AgentOut.model_validate(raw)

    async def set_models(self, agent_id: str, *, model_ids: list[str]) -> AgentOut:
        """
        Replace an agent's model chain.

        Sends ``PUT /agents/{agent_id}/models``. On a built-in (``managed``) agent
        this sets the organization-level chain for that agent's tier instead.

        Args:
            agent_id (str): Agent to update.
            model_ids (list[str]): At least one model id, in failover order.

        Returns:
            AgentOut: The agent with its new ``models``.

        Raises:
            InvalidParams: ``model_ids`` is empty.
            NotFoundError: No such agent, or an unknown model id (404 ``Bad model_ids``).
        """
        try:
            params = SetAgentModelsParams(model_ids=model_ids)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="agents.set_models") from None
        raw = await self._transport.request(
            "PUT", f"/agents/{_path(agent_id)}/models", json_body=params.model_dump(mode="json")
        )
        return AgentOut.model_validate(raw)

    async def delete(self, agent_id: str) -> None:
        """
        Delete a custom agent. This is permanent.

        Sends ``DELETE /agents/{agent_id}`` (204). Messages the agent handled keep
        working and report their agent as ``"ARCHIVED"``.

        Args:
            agent_id (str): Agent to delete.

        Returns:
            None: The agent is gone.

        Raises:
            NotFoundError: No such agent, or not writable by this API key.
        """
        await self._transport.request("DELETE", f"/agents/{_path(agent_id)}")


def _path(segment: str) -> str:
    return quote(segment, safe="")
