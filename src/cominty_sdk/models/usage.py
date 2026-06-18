"""Pydantic models for chat usage reporting."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    user_id: str
    count: int


class DailyUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str
    breakdown: list[Usage] = Field(default_factory=list)


class UserDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    image_url: str | None = None


class AgentDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class UsageReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    period_days: int
    timeseries: list[DailyUsage] = Field(default_factory=list)
    users: dict[str, UserDetail] = Field(default_factory=dict)
    agents: dict[str, AgentDetail] = Field(default_factory=dict)
