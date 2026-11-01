"""List MCP servers and give the enabled ones to a new agent.

    python examples/19_mcp_servers.py

``mcp.list`` reads ``GET /mcp/manifest``. ``enabled=None`` returns every server,
including ones this key has not turned on. The default keeps only the enabled
ones, and their ``name`` is what ``McpCapability.connections`` stores. The agent
created here is deleted before the script exits.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import make_client

from cominty_sdk import AgentCapabilities, McpCapability


async def main() -> None:
    async with make_client() as client:
        servers = await client.mcp.list(enabled=None)
        pretty.console.print(f"  [bold]manifest[/] {len(servers)} server(s)")
        for server in servers:
            state = "on" if server.is_enabled else "off"
            oauth = "oauth" if server.requires_oauth_connect else "no oauth"
            pretty.console.print(
                f"    {server.title}  name={server.name}  {state}  "
                f"{server.origin}  {server.scope}  {oauth}"
            )

        enabled = await client.mcp.list()
        if not enabled:
            pretty.console.print("  [bold]create[/]   skipped: no enabled MCP server")
            return

        agent = await client.agents.create(
            name="SDK example MCP agent",
            instructions="Reply in one short sentence.",
            capabilities=AgentCapabilities(
                mcp=McpCapability(
                    activation="always",
                    connections=[server.name for server in enabled],
                ),
            ),
        )
        try:
            assert agent.capabilities is not None and agent.capabilities.mcp is not None
            pretty.console.print(
                f"  [bold]create[/]   {agent.id} connections={agent.capabilities.mcp.connections}"
            )
        finally:
            await client.agents.delete(agent.id)
            pretty.console.print("  [bold]delete[/]   [green]done[/]")


if __name__ == "__main__":
    asyncio.run(main())
