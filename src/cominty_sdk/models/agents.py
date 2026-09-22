"""Request and response models for the agents resource.

Request models are strict (``strict=True, extra="forbid"``). Response models are
lenient (``extra="ignore"``). Named ``CustomAgent*`` to avoid colliding with the
chat-thread :class:`~.chat.Agent` (``{id, name}`` only).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CreateAgentParams",
    "UpdateAgentParams",
    "SetAgentModelsParams",
    "LLMModelSummary",
    "CustomAgentSummary",
    "CustomAgent",
]

AgentScope = Literal["organization", "private"]


# --------------------------------------------------------------------------- #
# Request models  (strict — reject unknown fields, no coercion)
# --------------------------------------------------------------------------- #
class CreateAgentParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    description: str | None = None
    instructions: str | None = None
    scope: AgentScope = "private"
    execution_options: dict[str, Any] | None = None
    allow_execution_options_override: bool = False
    model_ids: list[str] | None = Field(default=None, min_length=1)


class UpdateAgentParams(BaseModel):
    """Mutable agent fields. Only the fields you pass are sent (``exclude_none``)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    execution_options: dict[str, Any] | None = None
    allow_execution_options_override: bool | None = None


class SetAgentModelsParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    model_ids: list[str] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Response models  (lenient — ignore unknown fields)
# --------------------------------------------------------------------------- #
class LLMModelSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class CustomAgentSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str | None
    execution_options: dict[str, Any] | None
    managed: bool
    scope: str
    owner: str


class CustomAgent(CustomAgentSummary):
    instructions: str | None
    allow_execution_options_override: bool
    models: list[LLMModelSummary]
