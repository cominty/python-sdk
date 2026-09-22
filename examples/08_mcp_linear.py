"""Give the custom agent MCP context: list Hiroshi's current sprint from Linear.

    export COMINTY_CUSTOM_AGENT_ID="<your custom agent id>"
    python examples/08_mcp_linear.py

Builds on 07: the same custom French executive-briefing agent, but here it pulls
live context from the **Linear MCP server** instead of being handed the data.
The agent looks up Hiroshi's tasks in the current sprint, then reports them in
its own tone: a clean, non-technical French summary for leadership.

Prerequisites (configured on the platform, not in code):
- The Linear MCP server is connected to your org / available to the agent.
- The custom agent has tools (MCP) enabled.

Tool control is by *exclusion*: tools are on by default and you disable what you
don't want. Here we disable web search and company documents so the agent draws
context only from MCP (Linear). Watch the stream for the Linear tool calls.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import CUSTOM_AGENT_ID, make_client

from cominty_sdk import events

REQUEST = (
    "Using Linear, list the tasks assigned to Hiroshi in the current sprint. "
    "For each: title, status, and whether it's at risk of slipping. Then give a "
    "leadership-ready summary of where Hiroshi's sprint stands."
)


async def main() -> None:
    if not CUSTOM_AGENT_ID:
        print(
            "Set COMINTY_CUSTOM_AGENT_ID to your custom agent id "
            "(platform.cominty.ai -> Agents) and re-run."
        )
        return

    async with make_client() as client:
        pretty.panel(REQUEST, title="Request", style="yellow")

        run = await client.chat.start(
            agent_id=CUSTOM_AGENT_ID,
            message=REQUEST,
            # Keep MCP (Linear) ON; cut the rest so context comes only from Linear.
            disabled_tools=["web", "company_documents"],
        )

        # The stream surfaces the Linear MCP calls as ToolCall events.
        async for event in run:
            pretty.render(event)
            if isinstance(event, events.ToolCall) and event.status == "error":
                pretty.console.print(
                    f"       [red]↳ {event.data.error}[/]"  # e.g. Linear not connected
                )

        # Reported in the agent's voice: French, C-level, bullet points.
        pretty.answer(await run.text(), title="Synthèse sprint: Hiroshi (FR)")


if __name__ == "__main__":
    asyncio.run(main())
