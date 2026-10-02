"""Control what the agent can use.

    python examples/11_capabilities.py

Two scopes, one rule: the keyword name tells you the scope.

- ``thread_capabilities``: set when the thread starts, frozen for its lifetime.
- ``message_scope``: turn a capability on/off or narrow it for one message.

Every capability is an explicit object (``WebCapability``, ``McpCapability``, ...)
and its activation is always spelled out. Filters (``source_ids``, ``connections``,
...) default to ``ALL``, so passing ``ALL`` only makes the intent explicit.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client

from cominty_sdk import (
    ALL,
    AgentCapabilities,
    ImageGenerationCapability,
    IndexedDocumentsCapability,
    IndexedDocumentsScope,
    McpCapability,
    MemoryCapability,
    MessageScope,
    WebCapability,
    WebScope,
)


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="What is the VAT rate for food in France?",
            thread_capabilities=AgentCapabilities(
                web=WebCapability(activation="always"),
                # source_ids and document_ids omitted: both default to ALL.
                indexed_documents=IndexedDocumentsCapability(activation="on_request"),
                # Explicit ALL, same as leaving connections out.
                mcp=McpCapability(activation="on_request", connections=ALL),
                image_generation=ImageGenerationCapability(activation="never"),
                memory=MemoryCapability(activation="always", namespace="vat-demo"),
            ),
        )
        pretty.answer(await run.text())

        follow_up = await client.chat.send(
            run.thread.id,
            agent_id=AGENT_ID,
            message="Now answer from our documents only.",
            message_scope=MessageScope(
                web=WebScope(enabled=False),
                indexed_documents=IndexedDocumentsScope(enabled=True),
            ),
        )
        pretty.answer(await follow_up.text())


if __name__ == "__main__":
    asyncio.run(main())
