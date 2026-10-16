"""Upload files, attach them to a message, then download one back.

    python examples/14_upload_files.py

``chat.upload_file`` takes raw bytes (then ``filename`` is required) or a
``pathlib.Path`` (the name and the mimetype are inferred from it). Its result's
``id`` is what ``file_ids=[...]`` takes on ``chat.start`` and ``chat.send``, up
to 5 files per message, each at most 500 MiB. ``chat.download_file`` fetches the content of any
conversation file by id.

The bytes travel straight to the storage backend with a presigned URL: your API
key is only sent to the Cominty API. A bigger file raises ``InvalidParams`` before any
request; the daily upload quota, or a lower limit elsewhere, raises ``APIError`` with
the storage reason.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import _pretty as pretty
from _shared import AGENT_ID, make_client

NOTES = b"Project Atlas ships on March 3. The owner is Camille."
PRICES = "item,price\nlicence,120\nsupport,45\n"


async def main() -> None:
    work_dir = Path(tempfile.mkdtemp(prefix="cominty-upload-"))
    prices_path = work_dir / "prices.csv"
    prices_path.write_text(PRICES)

    async with make_client() as client:
        # Bytes need a filename. The mimetype is guessed from it (text/plain here).
        notes = await client.chat.upload_file(NOTES, filename="notes.txt")
        pretty.console.print(f"  [bold]upload[/]    {notes.name} ({notes.size} bytes)")

        # A Path brings its own name and mimetype (text/csv here).
        prices = await client.chat.upload_file(prices_path)
        pretty.console.print(f"  [bold]upload[/]    {prices.name} ({prices.mimetype})")

        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="Who owns Project Atlas, and what do the two items cost in total?",
            file_ids=[notes.id, prices.id],
        )
        pretty.answer(await run.text())

        content = await client.chat.download_file(notes.id)
        pretty.console.print(f"  [bold]download[/]  matches the upload: {content == NOTES}")


if __name__ == "__main__":
    asyncio.run(main())
