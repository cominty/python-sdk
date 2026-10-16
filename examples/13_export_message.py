"""Export a finished message as a PDF or DOCX file.

    python examples/13_export_message.py

``chat.export`` renders a message's content (Markdown) to a document and returns
the raw bytes. The server sends no file name, so you choose one when you write
them. Only a message that has content can be exported: one with none (for
instance a message still running) raises ``APIError`` (400).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    output_dir = Path(tempfile.mkdtemp(prefix="cominty-export-"))

    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="Write a short product brief about a note-taking app, in Markdown.",
        )
        reply = await run.result()

        for document_format in ("pdf", "docx"):
            content = await client.chat.export(reply.id, format=document_format)
            target = output_dir / f"brief.{document_format}"
            target.write_bytes(content)
            pretty.console.print(f"  [bold]export[/]  {len(content)} bytes -> {target}")


if __name__ == "__main__":
    asyncio.run(main())
