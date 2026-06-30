"""Fire a message and just await the final answer (no event handling).

    python examples/02_await_result.py

When you don't care about progress events, skip the iteration entirely: ``start``
returns a run, and ``await run.text()`` drains the stream internally and gives you
the finished reply. Use ``run.result()`` for the full Message (status, files,
structured output, ...).
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="Give me one fun fact about octopuses.",
        )

        # text() blocks until the agent finishes, then returns the reply string.
        pretty.answer(await run.text())

        # Or get the whole Message for richer access (cached after the first call):
        reply = await run.result()
        pretty.console.print(
            f"  [dim]status[/] {reply.status.value}   [dim]files[/] {len(reply.files)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
