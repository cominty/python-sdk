"""Upload a file, attach it to a message, then download it back.

    python examples/11_upload_download_files.py

Demonstrates ``chat.upload_file`` (accepts raw bytes or a file path) and
``chat.download_file``. The uploaded file's ``.id`` is what feeds
``file_ids=[...]`` on ``chat.start``/``chat.send``.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client

CONTENT = b"Cominty SDK examples are runnable end to end."


async def main() -> None:
    async with make_client() as client:
        uploaded = await client.chat.upload_file(
            CONTENT, filename="notes.txt", mimetype="text/plain"
        )
        pretty.console.print(f"  [bold]upload[/]    id={uploaded.id!r}  size={uploaded.size}")

        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="Summarize the attached file in one sentence.",
            file_ids=[uploaded.id],
        )
        pretty.console.print(f"  [bold]attach[/]    {await run.text()}")

        downloaded = await client.chat.download_file(uploaded.id)
        with open("notes-downloaded.txt", "wb") as f:
            f.write(downloaded)
        pretty.console.print(
            f"  [bold]download[/]  {len(downloaded)} bytes -> notes-downloaded.txt "
            f"(matches={downloaded == CONTENT})"
        )


if __name__ == "__main__":
    asyncio.run(main())
