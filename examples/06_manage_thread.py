"""Read, rename/star, and archive a thread.

    python examples/06_manage_thread.py

Demonstrates the rest of the threads resource: ``get`` (full history),
``update`` (partial: only the fields you pass are changed), and ``archive``.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    async with make_client() as client:
        # Create something to manage.
        run = await client.chat.start(agent_id=AGENT_ID, message="Hello!")
        await run.text()
        thread_id = run.thread.id

        # get() -> full thread with message history.
        thread = await client.threads.get(thread_id)
        pretty.console.print(
            f"  [bold]get[/]      {len(thread.messages)} messages, name={thread.name!r}"
        )

        # update() is partial: rename and star in one call, or either alone.
        updated = await client.threads.update(thread_id, name="Renamed via SDK", starred=True)
        pretty.console.print(
            f"  [bold]update[/]   name={updated.name!r}  starred=[yellow]{updated.starred}[/]"
        )

        # archive() soft-deletes the thread.
        await client.threads.archive(thread_id)
        pretty.console.print("  [bold]archive[/]  [green]done[/]")


if __name__ == "__main__":
    asyncio.run(main())
