"""Unit tests for ``client.chat.export`` — exporting a message as pdf/docx."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import AsyncCominty, NotFoundError

ASSISTANT_MSG_ID = "33333333-3333-3333-3333-333333333333"


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
async def test_sends_format_as_query_param(
    client: AsyncCominty, mock_api: respx.MockRouter, fmt: Literal["pdf", "docx"]
) -> None:
    route = mock_api.get(f"/chat/messages/{ASSISTANT_MSG_ID}/export").mock(
        return_value=httpx.Response(200, content=b"file-bytes")
    )

    await client.chat.export(ASSISTANT_MSG_ID, format=fmt)

    assert route.calls.last.request.url.params["format"] == fmt


async def test_returns_raw_file_bytes(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/messages/{ASSISTANT_MSG_ID}/export").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4 fake content")
    )

    result = await client.chat.export(ASSISTANT_MSG_ID, format="pdf")

    assert result == b"%PDF-1.4 fake content"


async def test_accepts_uuid_message_id(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(f"/chat/messages/{ASSISTANT_MSG_ID}/export").mock(
        return_value=httpx.Response(200, content=b"file-bytes")
    )

    await client.chat.export(UUID(ASSISTANT_MSG_ID), format="docx")

    assert route.called


async def test_export_unknown_message_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/messages/{ASSISTANT_MSG_ID}/export").mock(
        return_value=httpx.Response(404, json={"detail": "no such message"})
    )

    with pytest.raises(NotFoundError):
        await client.chat.export(ASSISTANT_MSG_ID, format="pdf")
