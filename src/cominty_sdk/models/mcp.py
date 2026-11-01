from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = ["McpServerOut", "McpManifestOut"]


class McpServerOut(BaseModel):
    """One MCP integration visible to this caller."""

    model_config = ConfigDict(extra="ignore")

    name: str
    """Stable integration id, the value ``McpCapability.connections`` and
    ``McpScope.connections`` take."""
    title: str
    """Label to show."""
    description: str
    """Short text to show."""
    is_enabled: bool
    """``True`` when this caller has the integration turned on."""
    origin: str
    """Where the server comes from. Current payloads use ``builtin`` and ``remote``;
    other values may appear."""
    scope: str
    """Who the integration belongs to. Current payloads use ``organization`` and ``user``."""
    requires_oauth_connect: bool
    """``True`` when the user must connect OAuth before the server can be used."""
    connection_status: str | None = None
    """Present when known, for example ``connected``."""
    icon_uri: str | None = None
    mcp_url: str | None = None
    """Remote server URL, when this server has one."""
    owner_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class McpManifestOut(BaseModel):
    # Envelope of GET /mcp/manifest. Callers receive McpServerOut, never this.

    model_config = ConfigDict(extra="ignore")

    servers: list[McpServerOut]
