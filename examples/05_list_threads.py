"""List the current user's conversations.

    python examples/05_list_threads.py

``threads.list()`` is scoped to the client's ``user_id`` automatically. It
returns lightweight summaries (no messages); use ``threads.get(id)`` to load a
thread's full history. ``terms`` does a free-text search; ``limit``/``page``
paginate (page is zero-based).
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import make_client


async def main() -> None:
    async with make_client() as client:
        threads = await client.threads.list(limit=20)

        if not threads:
            pretty.console.print("No threads yet — run a chat example first.")
            return

        pretty.thread_table(threads, title=f"Threads for {client.user_id}")

        # Free-text search across the user's threads:
        matches = await client.threads.list(terms=["invoice"], limit=5)
        pretty.console.print(f"\n{len(matches)} thread(s) matching 'invoice'.")


if __name__ == "__main__":
    asyncio.run(main())
