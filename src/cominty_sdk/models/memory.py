from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from .chat import UserId

__all__ = [
    "MemoryFileCreate",
    "MemoryFileUpdate",
    "MemoryFileOut",
    "MemoryFileSummaryOut",
]


class MemoryFileCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    path: str
    purpose: str
    content: str
    user_id: UserId
    """Unlike the other memory endpoints, ``POST /memory`` takes ``user_id`` in
    the request body rather than as a query parameter — confirmed empirically,
    the OpenAPI contract doesn't declare it as a parameter here at all."""


class MemoryFileUpdate(BaseModel):
    """Partial update body for ``PUT /memory/file``.

    Built by the resource from only the arguments the caller actually passed,
    then dumped with ``exclude_unset=True`` — this is what lets an explicit
    ``None`` (clear the field) round-trip differently from an omitted argument
    (leave the field untouched), which plain ``exclude_none`` cannot do.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    content: str | None = None
    purpose: str | None = None

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> MemoryFileUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one of `content` or `purpose` must be provided")
        return self


class MemoryFileOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    purpose: str
    content: str
    created_at: datetime
    updated_at: datetime
    version: str
    """Opaque concurrency token (currently identical to ``updated_at``) — pass
    it back unchanged to :meth:`~.resources.memory.MemoryResource.update`.
    Never parse, compare, or otherwise interpret its contents."""


class MemoryFileSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    purpose: str
    created_at: datetime
    updated_at: datetime
    version: str