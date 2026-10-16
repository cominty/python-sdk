"""Stop an assistant message that is still being generated.

    python examples/12_cancel_message.py

``chat.cancel`` flips a running message to ``cancelled`` right away and returns
it. It is not idempotent: cancelling a message that already finished (or was
already cancelled) raises ``APIError`` with status 400, so a "stop" button should
treat that error as "too late, nothing to stop". The second call below shows it.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import _pretty as pretty
from _shared import AGENT_ID, make_client

from cominty_sdk import APIError, AsyncCominty


async def cancel_and_report(client: AsyncCominty, message_id: UUID, label: str) -> None:
    try:
        cancelled = await client.chat.cancel(message_id)
    except APIError as error:
        pretty.console.print(f"  [bold]{label}[/]  [yellow]{error.status_code} {error}[/]")
    else:
        pretty.console.print(f"  [bold]{label}[/]  status={cancelled.status.value!r}")


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID, message="Write a very detailed 3000 word market report."
        )

        # A fast agent can finish before this runs: the 400 is reported, not fatal.
        await cancel_and_report(client, run.message_id, "cancel")
        # A second cancel is always rejected: the message is no longer live.
        await cancel_and_report(client, run.message_id, "again ")


if __name__ == "__main__":
    asyncio.run(main())
