"""Export a finished message as a PDF or DOCX file.

    python examples/10_export_message.py

Demonstrates ``chat.export`` — downloads a finished message's output as a
file. Returns raw bytes; write them to disk yourself.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID, message="Reply with exactly: pong"
        )
        await run.text()

        pdf_bytes = await client.chat.export(run.message_id, format="pdf")
        with open("export.pdf", "wb") as f:
            f.write(pdf_bytes)
        pretty.console.print(f"  [bold]export[/]  {len(pdf_bytes)} bytes -> export.pdf")


if __name__ == "__main__":
    asyncio.run(main())
