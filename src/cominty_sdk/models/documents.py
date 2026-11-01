from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .sources import SourceStore

__all__ = ["DocumentMetadataOut"]


class DocumentMetadataOut(BaseModel):
    """Where a document cited by an agent comes from."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    source_id: int
    source_pid: str
    source_type: SourceStore
    document_name: str
    document_uri: str | None
    document_extension: str
    document_mime_type: str
