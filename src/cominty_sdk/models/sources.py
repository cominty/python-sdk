from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from .common import Scope

__all__ = [
    # enums
    "SourceStatus",
    "SourceStore",
    # request models
    "SourceConfig",
    "CreateSourceParams",
    "UpdateSourceParams",
    # response models
    "FileOut",
    "DriveOut",
    "SourceOut",
]


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class SourceStatus(str, Enum):
    pending = "pending"
    syncing = "syncing"
    synced = "synced"
    error = "error"
    out_of_sync = "out_of_sync"
    cancelling = "cancelling"
    pausing = "pausing"
    paused = "paused"
    archived = "archived"
    disconnected = "disconnected"
    inoperative_connection = "inoperative_connection"
    expired_connection = "expired_connection"
    invalid_configuration = "invalid_configuration"
    daily_quota_reached = "daily_quota_reached"


class SourceStore(str, Enum):
    draganddrop = "draganddrop"
    googledrive = "googledrive"
    sharepoint = "sharepoint"


# --------------------------------------------------------------------------- #
# Request models  (strict: reject unknown fields, no coercion)
# --------------------------------------------------------------------------- #
class SourceConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    drive_id: str


class CreateSourceParams(BaseModel):
    """Body of ``POST /dc/sources``. API keys may only create private drag-and-drop
    sources, so ``store`` and ``scope`` are fixed rather than exposed."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str | None = None
    store: Literal["draganddrop"] = "draganddrop"
    scope: Literal["private"] = "private"
    config: SourceConfig


class UpdateSourceParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str


# --------------------------------------------------------------------------- #
# Response models  (lenient: ignore unknown fields)
# --------------------------------------------------------------------------- #
class FileOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: datetime
    updated_at: datetime
    name: str
    size: int
    mimetype: str


class DriveOut(BaseModel):
    # Internal: a drive is the container behind a drag-and-drop source. The SDK never
    # hands one to the caller; sources expose their files through list_files instead.
    model_config = ConfigDict(extra="ignore")

    id: str
    files: list[FileOut]


class SourceOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    """Numeric id, the one ``IndexedDocumentsCapability.source_ids`` takes."""
    pid: str
    """Public id, the one every ``client.sources`` method takes."""
    created_at: datetime
    name: str
    scope: Scope
    created_by: str
    store: SourceStore
    status: SourceStatus
    size: int
    embedded_size: int
    config: dict[str, object]
    """Store configuration as the API returns it: ``{"meta": {...}, "values": {...}}``,
    where ``values`` holds ``drive_id`` for a drag-and-drop source. Prefer :attr:`drive_id`."""
    documents_synced: int
    documents_failed: int
    oversized_documents: int
    documents_embedded: int
    last_synced_at: datetime | None
    archived_at: datetime | None

    @property
    def drive_id(self) -> str | None:
        """
        The drive holding this source's files.

        Returns:
            str | None: The drive id of a drag-and-drop source, ``None`` for a connected store.
        """
        # The API nests the stored values under "values"; accept a flat dict too.
        values = self.config.get("values", self.config)
        if not isinstance(values, dict):
            return None
        drive_id = cast("dict[str, object]", values).get("drive_id")
        return drive_id if isinstance(drive_id, str) and drive_id else None
