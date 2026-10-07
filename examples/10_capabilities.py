"""Control what the agent can use.

    python examples/10_capabilities.py

Two scopes, one rule: the keyword name tells you the scope.

- ``thread_capabilities``: set when the thread starts, frozen for its lifetime.
- ``message_scope``: turn a capability on/off or narrow it for one message.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client

from cominty_sdk import (
    ALL,
    AgentCapabilities,
    IndexedDocumentsPolicy,
    MessageScope,
)


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="What is the VAT rate for food in France?",
            thread_capabilities=AgentCapabilities(
                web="always",
                indexed_documents=IndexedDocumentsPolicy(
                    activation="on_request", source_ids=ALL, document_ids=ALL
                ),
                image_generation="never",
            ),
        )
        pretty.answer(await run.text())

        follow_up = await client.chat.send(
            run.thread.id,
            agent_id=AGENT_ID,
            message="Now answer from our documents only.",
            message_scope=MessageScope(web=False, indexed_documents=True),
        )
        pretty.answer(await follow_up.text())


if __name__ == "__main__":
    asyncio.run(main())
