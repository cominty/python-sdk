"""Continue a conversation — send a follow-up in the same thread.

    python examples/03_follow_up.py

``chat.send(thread_id, ...)`` is the mirror of ``chat.start`` for an existing
thread: same arguments, same streamable run. The agent keeps the thread's
context, so you can build a multi-turn conversation.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    async with make_client() as client:
        # Turn 1 — start the thread.
        first = await client.chat.start(
            agent_id=AGENT_ID,
            message="Pick a programming language and say why in one line.",
        )
        thread_id = first.thread.id
        pretty.rule("Turn 1")
        pretty.answer(await first.text())

        # Turn 2 — follow up in the SAME thread; the agent remembers turn 1.
        second = await client.chat.send(
            thread_id,
            agent_id=AGENT_ID,
            message="Now show a 'hello world' in that language.",
        )
        pretty.rule("Turn 2")
        pretty.answer(await second.text())


if __name__ == "__main__":
    asyncio.run(main())
