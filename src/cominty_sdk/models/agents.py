from __future__ import annotations

from typing import Annotated, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from cominty_sdk.exceptions import InvalidParams

from .capabilities import AgentCapabilities
from .common import Scope

__all__ = [
    # request models
    "CreateAgentParams",
    "UpdateAgentParams",
    "SetAgentModelsParams",
    # response models
    "LLMModelSummaryOut",
    "AgentSummaryOut",
    "AgentOut",
]

# Server-side limits (settings.CUSTOM_AGENT_DESCRIPTION_MAX_LENGTH / _INSTRUCTIONS_MAX_LENGTH).
_DESCRIPTION_MAX_LENGTH = 500
_INSTRUCTIONS_MAX_LENGTH = 30_000


# --------------------------------------------------------------------------- #
# Request models  (strict: reject unknown fields, no coercion)
# --------------------------------------------------------------------------- #
class CreateAgentParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)
    instructions: str | None = Field(default=None, max_length=_INSTRUCTIONS_MAX_LENGTH)
    scope: Scope = "private"
    capabilities: AgentCapabilities | None = None
    allow_execution_options_override: bool = False
    model_ids: list[str] | None = Field(default=None, min_length=1)


class UpdateAgentParams(BaseModel):
    """Partial update body for ``PUT /agents/{id}``.

    Dumped with ``exclude_unset=True`` so only explicitly-passed fields are sent.
    ``description``, ``instructions`` and ``capabilities`` accept ``None`` (the
    server clears them); the other fields cannot be null and reject it locally.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)
    instructions: str | None = Field(default=None, max_length=_INSTRUCTIONS_MAX_LENGTH)
    scope: Scope | None = None
    capabilities: AgentCapabilities | None = None
    allow_execution_options_override: bool | None = None

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> UpdateAgentParams:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self

    @model_validator(mode="after")
    def _reject_explicit_none_on_required_fields(self) -> UpdateAgentParams:
        nulled = sorted(
            name
            for name in ("name", "scope", "allow_execution_options_override")
            if name in self.model_fields_set and getattr(self, name) is None
        )
        if nulled:
            raise ValueError(
                f"{' and '.join(nulled)} cannot be set to None: omit the argument instead"
            )
        return self


class SetAgentModelsParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    model_ids: list[str] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Response models  (lenient: ignore unknown fields)
# --------------------------------------------------------------------------- #
def _known_capabilities(value: object) -> object:
    # AgentCapabilities is a strict input model. A capability the API adds later, or a
    # newer shape of a known one (an extra field, a new activation), must not break every
    # agent read, so those are left out. Sending the result back through update() is
    # safe: the API merges capabilities key by key and keeps the ones left out.
    if not isinstance(value, dict):
        return value
    known: dict[str, object] = {}
    for name, capability in cast("dict[str, object]", value).items():
        if name not in AgentCapabilities.model_fields:
            continue
        try:
            AgentCapabilities.model_validate({name: capability})
        except InvalidParams:
            continue
        known[name] = capability
    return known


class LLMModelSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class AgentSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str | None
    capabilities: Annotated[AgentCapabilities | None, BeforeValidator(_known_capabilities)]
    execution_options: dict[str, object] | None
    """Legacy tool configuration. New agents describe this through ``capabilities``."""
    memory_namespace: str | None
    managed: bool
    """``True`` for the built-in Cominty agents, which cannot be edited or deleted."""
    scope: Scope
    owner: str
    """Clerk user id of the creator. For an agent created with an API key, this is the
    admin who minted the key: the ``user_id`` to chat with over key-indexed sources."""


class AgentOut(AgentSummaryOut):
    instructions: str | None
    allow_execution_options_override: bool
    models: list[LLMModelSummaryOut]
    """Model chain, in failover order."""
