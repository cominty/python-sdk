"""Create, list, read, update, and delete a memory file.

    python examples/09_memory.py

Demonstrates the full memory resource lifecycle, scoped to a namespace (a
caller-chosen bag name; the first create against a new one is enough to bring
it into existence). ``update`` is partial: only the fields you pass are
changed, and ``version`` (an opaque token from the previous read) guards
against overwriting a concurrent change: a stale ``version`` raises
``ConflictError``. The file created here is always deleted before the script
exits, even on error.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import _pretty as pretty
from _shared import make_client

from cominty_sdk import ConflictError


async def main() -> None:
    async with make_client() as client:
        namespace = f"sdk-examples-{uuid4()}"
        path = "notes.md"

        # create() -> the new file, in a namespace chosen by the caller. The
        # first create against a new namespace is enough to bring it into
        # existence: there is no separate call to create one.
        created = await client.memory.create(
            path=path,
            namespace=namespace,
            purpose="scratch note for the memory example",
            content="Remember to buy milk.",
        )
        pretty.console.print(f"  [bold]create[/]  path={created.path!r} namespace={namespace!r}")

        try:
            # list(namespace=...) -> lightweight summaries (no content) for
            # this bag only. Omit namespace to list every bag instead.
            summaries = await client.memory.list(namespace=namespace)
            pretty.console.print(f"  [bold]list[/]    {len(summaries)} file(s)")

            # list_namespaces() -> every distinct bag with at least one file.
            namespaces = await client.memory.list_namespaces()
            pretty.console.print(f"  [bold]namespaces[/] {namespace in namespaces}")

            # get() -> the full file, including content.
            fetched = await client.memory.get(path, namespace=namespace)
            pretty.console.print(f"  [bold]get[/]     content={fetched.content!r}")

            # update() is partial: only content changes here, purpose is untouched.
            # version must match the file's current version or this raises
            # ConflictError (409): the API's optimistic-concurrency guard.
            updated = await client.memory.update(
                path, namespace=namespace, version=fetched.version, content="Buy oat milk instead."
            )
            pretty.console.print(f"  [bold]update[/]  content={updated.content!r}")

            # Reusing the now-stale version demonstrates the 409 guard.
            try:
                await client.memory.update(
                    path, namespace=namespace, version=fetched.version, content="stale write"
                )
            except ConflictError:
                pretty.console.print("  [bold]conflict[/] [yellow]stale version rejected[/]")
        finally:
            # Always clean up the file this example created.
            await client.memory.delete(path, namespace=namespace)
            pretty.console.print("  [bold]delete[/]  [green]done[/]")


if __name__ == "__main__":
    asyncio.run(main())
