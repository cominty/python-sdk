from __future__ import annotations

from types import SimpleNamespace
from typing import Literal, cast
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import (
    APIError,
    AsyncCominty,
    ExportFormat,
    InvalidParams,
    NotFoundError,
)

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
async def test_sends_format_as_query_param(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    ids: SimpleNamespace,
    fmt: Literal["pdf", "docx"],
) -> None:
    route = mock_api.get(f"/chat/messages/{ids.assistant_msg}/export").mock(
        return_value=httpx.Response(200, content=b"file")
    )

    await client.chat.export(ids.assistant_msg, format=fmt)

    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/chat/messages/{ids.assistant_msg}/export"
    assert dict(request.url.params) == {"format": fmt}


@pytest.mark.parametrize(
    ("fmt", "content_type", "payload"),
    [("pdf", "application/pdf", b"%PDF-1.7 body"), ("docx", DOCX_TYPE, b"PK\x03\x04 body")],
)
async def test_returns_raw_file_bytes(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    ids: SimpleNamespace,
    fmt: ExportFormat,
    content_type: str,
    payload: bytes,
) -> None:
    mock_api.get(f"/chat/messages/{ids.assistant_msg}/export").mock(
        return_value=httpx.Response(200, content=payload, headers={"Content-Type": content_type})
    )

    result = await client.chat.export(ids.assistant_msg, format=fmt)

    assert isinstance(result, bytes)
    assert result == payload


async def test_accepts_uuid_message_id(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    route = mock_api.get(f"/chat/messages/{ids.assistant_msg}/export").mock(
        return_value=httpx.Response(200, content=b"file")
    )

    await client.chat.export(UUID(ids.assistant_msg), format="pdf")

    assert route.called


@pytest.mark.parametrize("bad_format", ["txt", "PDF", "", None])
async def test_invalid_format_raises_before_any_request(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    ids: SimpleNamespace,
    bad_format: str | None,
) -> None:
    route = mock_api.get(f"/chat/messages/{ids.assistant_msg}/export")

    with pytest.raises(InvalidParams) as caught:
        await client.chat.export(ids.assistant_msg, format=cast("ExportFormat", bad_format))

    assert [error["param"] for error in caught.value.errors] == ["format"]
    assert not route.called


async def test_unknown_message_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    mock_api.get(f"/chat/messages/{ids.assistant_msg}/export").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )

    with pytest.raises(NotFoundError):
        await client.chat.export(ids.assistant_msg, format="pdf")


async def test_message_without_content_raises_api_error(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    mock_api.get(f"/chat/messages/{ids.assistant_msg}/export").mock(
        return_value=httpx.Response(400, json={"detail": "Message has no content"})
    )

    with pytest.raises(APIError, match="Message has no content") as caught:
        await client.chat.export(ids.assistant_msg, format="pdf")

    assert caught.value.status_code == 400


@pytest.mark.parametrize("bad_id", ["", "not-a-uuid", "../threads/x"])
async def test_message_id_that_is_not_a_uuid_raises_before_any_request(
    client: AsyncCominty, mock_api: respx.MockRouter, bad_id: str
) -> None:
    with pytest.raises(ValueError, match="message_id must be a UUID"):
        await client.chat.export(bad_id, format="pdf")

    assert not mock_api.calls
