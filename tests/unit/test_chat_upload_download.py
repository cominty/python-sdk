"""Unit tests for ``client.chat.upload_file``/``download_file``.

``upload_file`` orchestrates 3 HTTP calls: a permission request and a confirm
call against the Cominty API, plus one direct upload to a presigned storage
URL on a *different* host — mocked here via its full absolute URL.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from cominty_sdk import AsyncCominty, ConversationFile, InvalidParams, NotFoundError

STORAGE_URL = "https://storage.example.com/upload-bucket"
FILE_ID = "44444444-4444-4444-4444-444444444444"


def _upload_permission() -> dict[str, object]:
    return {
        "url": STORAGE_URL,
        "fields": {
            "key": "uploads/44444444.txt",
            "policy": "opaque-policy",
            "x-amz-signature": "opaque-signature",
        },
    }


def _conversation_file() -> dict[str, object]:
    return {
        "id": FILE_ID,
        "name": "a.txt",
        "size": 5,
        "mimetype": "text/plain",
        "origin": "user",
        "share_links": [],
        "url": "https://cominty.example/files/44444444",
    }


async def test_upload_orchestrates_permission_upload_confirm(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    permission_route = mock_api.get("/chat/files/upload").mock(
        return_value=httpx.Response(200, json=_upload_permission())
    )
    storage_route = mock_api.post(STORAGE_URL).mock(
        return_value=httpx.Response(204, headers={"ETag": '"abc123etag"'})
    )
    confirm_route = mock_api.post("/chat/files").mock(
        return_value=httpx.Response(200, json=_conversation_file())
    )

    result = await client.chat.upload_file(
        b"hello", filename="a.txt", mimetype="text/plain"
    )

    assert permission_route.calls.last.request.url.params["filename"] == "a.txt"
    assert permission_route.calls.last.request.url.params["mimetype"] == "text/plain"
    assert storage_route.called
    assert json.loads(confirm_route.calls.last.request.content) == {
        "etag": "abc123etag",
        "key": "uploads/44444444.txt",
    }
    assert isinstance(result, ConversationFile)
    assert str(result.id) == FILE_ID


@pytest.mark.parametrize("as_str", [False, True])
async def test_upload_accepts_a_file_path(
    client: AsyncCominty, mock_api: respx.MockRouter, tmp_path: Path, as_str: bool
) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"hello")

    mock_api.get("/chat/files/upload").mock(
        return_value=httpx.Response(200, json=_upload_permission())
    )
    storage_route = mock_api.post(STORAGE_URL).mock(
        return_value=httpx.Response(204, headers={"ETag": '"abc123etag"'})
    )
    mock_api.post("/chat/files").mock(
        return_value=httpx.Response(200, json=_conversation_file())
    )

    await client.chat.upload_file(
        str(file_path) if as_str else file_path, filename="a.txt", mimetype="text/plain"
    )

    assert b"hello" in storage_route.calls.last.request.content


async def test_upload_sends_permission_fields_and_file_to_storage(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/chat/files/upload").mock(
        return_value=httpx.Response(200, json=_upload_permission())
    )
    storage_route = mock_api.post(STORAGE_URL).mock(
        return_value=httpx.Response(204, headers={"ETag": '"abc123etag"'})
    )
    mock_api.post("/chat/files").mock(
        return_value=httpx.Response(200, json=_conversation_file())
    )

    await client.chat.upload_file(b"hello", filename="a.txt", mimetype="text/plain")

    sent = storage_route.calls.last.request
    body = sent.content.decode("utf-8", errors="ignore")
    assert "opaque-policy" in body
    assert "hello" in body


async def test_upload_does_not_send_cominty_token_to_storage(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/chat/files/upload").mock(
        return_value=httpx.Response(200, json=_upload_permission())
    )
    storage_route = mock_api.post(STORAGE_URL).mock(
        return_value=httpx.Response(204, headers={"ETag": '"abc123etag"'})
    )
    mock_api.post("/chat/files").mock(
        return_value=httpx.Response(200, json=_conversation_file())
    )

    await client.chat.upload_file(b"hello", filename="a.txt", mimetype="text/plain")

    assert "x-cominty-token" not in storage_route.calls.last.request.headers


@pytest.mark.parametrize("bad_filename", ["a/b.txt", "x" * 256])
async def test_upload_invalid_filename_raises_before_request(
    client: AsyncCominty, mock_api: respx.MockRouter, bad_filename: str
) -> None:
    route = mock_api.get("/chat/files/upload")

    with pytest.raises(InvalidParams):
        await client.chat.upload_file(b"x", filename=bad_filename, mimetype="text/plain")

    assert not route.called


async def test_download_fetches_presigned_url_and_returns_bytes(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json=STORAGE_URL)
    )
    mock_api.get(STORAGE_URL).mock(return_value=httpx.Response(200, content=b"raw file bytes"))

    result = await client.chat.download_file(FILE_ID)

    assert result == b"raw file bytes"


async def test_download_does_not_send_cominty_token_to_storage(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json=STORAGE_URL)
    )
    storage_route = mock_api.get(STORAGE_URL).mock(
        return_value=httpx.Response(200, content=b"x")
    )

    await client.chat.download_file(FILE_ID)

    assert "x-cominty-token" not in storage_route.calls.last.request.headers


async def test_download_unknown_file_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "no such file"})
    )

    with pytest.raises(NotFoundError):
        await client.chat.download_file(FILE_ID)
