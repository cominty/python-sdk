"""Stream an agent's progress events live, then print the final answer.

    python examples/01_stream_events.py

Start a thread, then iterate the run to watch the agent work — tool calls, LLM
steps, and the final result event — as they arrive. Iterating yields *progress
events only*; the finished reply is captured for you and returned by ``text()``.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="What can you help me with? Answer in one sentence.",
        )
        pretty.header(run.thread.id, run.message_id)

        # Iterating yields progress events only; pretty.render() prints each as
        # one aligned, color-coded row (color = status, icon = event type).
        async for event in run:
            pretty.render(event)

        pretty.answer(await run.text())


if __name__ == "__main__":
    asyncio.run(main())
