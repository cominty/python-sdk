"""Pydantic models for chat threads."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cominty_sdk.models.messages import MessageOut


class AgentSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class ThreadOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    created_at: datetime
    live: bool
    agent: AgentSummary
    starred: bool
    messages: list[MessageOut] = Field(default_factory=list)


class ThreadSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    created_at: datetime
    live: bool
    agent: AgentSummary
    starred: bool


class ThreadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    starred: bool | None = None
