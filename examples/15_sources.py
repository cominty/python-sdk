"""Index a local folder, give it to an agent, and ask about it.

    python examples/15_sources.py

``sources.create`` takes a file, a folder (its top-level files) or a list of files
and does the whole flow: drive, presigned uploads, source, first sync.
``wait_synced`` blocks until the documents are searchable. The agent then gets the
source through ``IndexedDocumentsCapability(source_ids=[source.id])``: capabilities
take the numeric ``id``, every ``sources`` method takes the public ``pid``.

Sources created with an API key are private to the admin who minted it, so the chat
runs with that admin's user id (``agent.owner``), not necessarily ``COMINTY_USER_ID``.
Everything created here is archived or deleted before the script exits.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import _pretty as pretty
from _shared import make_client

from cominty_sdk import (
    AgentCapabilities,
    AsyncCominty,
    IndexedDocumentsCapability,
    WebCapability,
)

DOCS = {
    "atlas.md": "# Project Atlas\n\nAtlas ships on March 3. The owner is Camille.\n",
    "prices.csv": "item,price\nlicence,120\nsupport,45\n",
}


async def main() -> None:
    folder = Path(tempfile.mkdtemp(prefix="cominty-sources-"))
    for name, content in DOCS.items():
        (folder / name).write_text(content)

    async with make_client() as client:
        # One call: drive + uploads + source. The first sync starts right away.
        source = await client.sources.create(folder, name="SDK example docs")
        pretty.console.print(
            f"  [bold]create[/]   pid={source.pid} id={source.id} {source.status.value}"
        )

        agent = None
        try:
            source = await client.sources.wait_synced(source.pid, timeout=300)
            pretty.console.print(f"  [bold]synced[/]   {source.documents_synced} document(s)")

            for f in await client.sources.list_files(source.pid):
                pretty.console.print(f"  [bold]file[/]     {f.name} ({f.size} bytes)")

            # An agent that answers from this source only.
            agent = await client.agents.create(
                name="SDK example docs assistant",
                instructions="Answer from the indexed documents only. Be brief.",
                capabilities=AgentCapabilities(
                    web=WebCapability(activation="never"),
                    indexed_documents=IndexedDocumentsCapability(
                        activation="always", source_ids=[source.id]
                    ),
                ),
            )
            pretty.console.print(f"  [bold]agent[/]    {agent.id} owner={agent.owner}")

            # Key-created sources are visible to the key owner: chat as that user.
            async with AsyncCominty(user_id=agent.owner) as owner_client:
                run = await owner_client.chat.start(
                    agent_id=agent.id,
                    message="Who owns Project Atlas, and what does support cost?",
                )
                pretty.answer(await run.text())
        finally:
            if agent is not None:
                await client.agents.delete(agent.id)
            await client.sources.archive(source.pid)
            pretty.console.print("  [bold]cleanup[/]  [green]done[/]")


if __name__ == "__main__":
    asyncio.run(main())
