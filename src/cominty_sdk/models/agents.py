"""Pydantic models for managed agents (GET /agents)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AgentMode(StrEnum):
    LITE = "lite"
    HIVE = "hive"


class AgentOut(BaseModel):
    """Org-managed agent configuration returned by GET /agents."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    mode: AgentMode | str
    description: str | None = None
    instructions: str | None = None
    owner: str
