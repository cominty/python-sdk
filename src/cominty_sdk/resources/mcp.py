from __future__ import annotations

from typing import TYPE_CHECKING

from cominty_sdk.models.mcp import McpManifestOut, McpServerOut

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

__all__ = ["McpResource"]


class McpResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(self, *, enabled: bool | None = True) -> list[McpServerOut]:
        """
        List the MCP integrations this API key can use.

        Sends ``GET /mcp/manifest``. A server's ``name`` is the value to store in
        ``McpCapability.connections`` or ``McpScope.connections``. The endpoint
        returns every server, including ones this caller has not turned on;
        ``enabled`` filters that list here.

        Args:
            enabled (bool | None): Which servers to keep, matched on
                ``McpServerOut.is_enabled``. ``True`` (the default) keeps the ones
                this caller has turned on. ``False`` keeps only the ones that are
                off. ``None`` returns every server, in the order the API sent them.

        Returns:
            list[McpServerOut]: The matching integrations. May be empty.

        Raises:
            ServerError: The manifest could not be loaded.
        """
        raw = await self._transport.request("GET", "/mcp/manifest")
        servers = McpManifestOut.model_validate(raw).servers
        if enabled is None:
            return servers
        return [server for server in servers if server.is_enabled is enabled]
