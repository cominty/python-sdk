"""Pydantic models for chat file operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FileUploadPermission(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    fields: dict[str, str] = Field(default_factory=dict)


class FileUploadConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etag: str
    key: str


class ConversationFileOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    size: int
    mimetype: str
    origin: str
    url: str | None = None
