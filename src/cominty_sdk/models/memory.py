from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator
from typing_extensions import TypeAlias

from .chat import UserId

__all__ = [
    "MemoryFileCreate",
    "MemoryFileUpdate",
    "MemoryFileOut",
    "MemoryFileSummaryOut",
    "MemoryPath",
    "MemoryPathParam",
    "validate_memory_path",
]


# A path with more than one folder segment (e.g. "a/b/file.md") is rejected with a
# 422 "Maximum folder depth is 1".
_MAX_PATH_DEPTH = 1


def validate_memory_path(value: str) -> str:
    depth = value.count("/")
    if depth > _MAX_PATH_DEPTH:
        raise ValueError(
            f"path {value!r} has {depth} folder levels; the API allows at most "
            f"{_MAX_PATH_DEPTH} (e.g. 'folder/file.md' is fine, 'a/b/file.md' isn't)"
        )
    return value


MemoryPath: TypeAlias = Annotated[str, AfterValidator(validate_memory_path)]
"""A memory file path, folder-depth-checked before any request is sent."""


class MemoryPathParam(BaseModel):
    """Validates a bare ``path`` argument (``get``/``update``/``delete``,
    which don't otherwise go through a request-body model)."""

    model_config = ConfigDict(strict=True)

    path: MemoryPath


class MemoryFileCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    path: MemoryPath
    purpose: str
    content: str
    user_id: UserId
    """Unlike the other memory endpoints, ``POST /memory`` takes ``user_id`` in
    the request body rather than as a query parameter."""


class MemoryFileUpdate(BaseModel):
    """Partial update body for ``PUT /memory/file``.

    Dumped with ``exclude_unset=True`` so only explicitly-passed fields are
    sent. The API does not currently support clearing ``content``/``purpose``
    once set: a ``null`` is silently ignored server-side (200, value
    unchanged) rather than clearing the field. To avoid that confusing
    silent-no-op, this model rejects an explicit ``None`` locally instead of
    forwarding it.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    content: str | None = None
    purpose: str | None = None

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> MemoryFileUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one of `content` or `purpose` must be provided")
        return self

    @model_validator(mode="after")
    def _reject_explicit_none(self) -> MemoryFileUpdate:
        nulled = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulled:
            fields = " and ".join(nulled)
            raise ValueError(
                f"{fields} cannot be set to None: the API does not support "
                "clearing a field once set (it's currently a silent no-op): "
                "omit the argument instead of passing None"
            )
        return self


class MemoryFileOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    purpose: str
    content: str
    created_at: datetime
    updated_at: datetime
    version: str
    """Opaque concurrency token: pass it back unchanged to
    :meth:`~.resources.memory.MemoryResource.update`."""


class MemoryFileSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    purpose: str
    created_at: datetime
    updated_at: datetime
    version: str
