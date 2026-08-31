"""Cancel an in-flight assistant message.

    python examples/09_cancel_message.py

Demonstrates ``chat.cancel`` — stops a message that's still being generated
and returns its final ``Message``, with ``status`` set to ``"cancelled"``.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(agent_id=AGENT_ID, message="Write a long story.")

        cancelled = await client.chat.cancel(run.message_id)
        pretty.console.print(f"  [bold]cancel[/]  status={cancelled.status.value!r}")


if __name__ == "__main__":
    asyncio.run(main())
