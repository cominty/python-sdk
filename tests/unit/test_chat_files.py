from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import httpx
import pytest
import respx

from cominty_sdk import (
    APIConnectionError,
    APIError,
    AsyncCominty,
    ConversationFile,
    InvalidParams,
    NotFoundError,
    SDKError,
    ServerError,
)
from cominty_sdk.resources.chat import (
    _MAX_UPLOAD_BYTES,
)

STORAGE_URL = "https://storage.example.com/upload-bucket"
SIGNED_DOWNLOAD_URL = "https://storage.example.com/files/a.txt?X-Amz-Signature=secret-signature"
FILE_ID = "V1StGXR8_Z5jdHi6B-myT"
ETAG = '"abc123etag"'


def _fail_if_read(self: Path) -> bytes:
    raise AssertionError(f"{self} was read although it is over the size limit")


def _permission() -> dict[str, object]:
    return {
        "url": STORAGE_URL,
        "fields": {
            "key": "org/chat/files/chat_over_api/44444444/a.txt",
            "policy": "opaque-policy",
            "x-amz-signature": "opaque-signature",
        },
    }


def _conversation_file(name: str = "a.txt") -> dict[str, object]:
    return {
        "id": FILE_ID,
        "name": name,
        "size": 5,
        "mimetype": "text/plain",
        "origin": "user",
        "share_links": [],
        "url": f"https://api.test/chat/files/{FILE_ID}",
    }


def _xml_error(
    status: int, code: str, message: str | None = None, content_type: str = "application/xml"
) -> httpx.Response:
    detail = f"<Message>{message}</Message>" if message is not None else ""
    body = f"<?xml version='1.0'?><Error><Code>{code}</Code>{detail}</Error>"
    return httpx.Response(status, text=body, headers={"Content-Type": content_type})


class _UploadRoutes:
    def __init__(self, mock_api: respx.MockRouter) -> None:
        self.permission = mock_api.get("/chat/files/upload").mock(
            return_value=httpx.Response(200, json=_permission())
        )
        self.storage = mock_api.post(STORAGE_URL).mock(
            return_value=httpx.Response(204, headers={"ETag": ETAG})
        )
        self.confirm = mock_api.post("/chat/files").mock(
            return_value=httpx.Response(200, json=_conversation_file())
        )


@pytest.fixture
def upload_routes(mock_api: respx.MockRouter) -> _UploadRoutes:
    return _UploadRoutes(mock_api)


async def test_upload_runs_permission_storage_and_confirm(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    result = await client.chat.upload_file(b"hello", filename="a.txt", mimetype="text/plain")

    permission_request = upload_routes.permission.calls.last.request
    assert dict(permission_request.url.params) == {"filename": "a.txt", "mimetype": "text/plain"}
    confirm_request = upload_routes.confirm.calls.last.request
    # The ETag goes back exactly as the storage backend sent it, quotes included.
    assert json.loads(confirm_request.content) == {
        "etag": ETAG,
        "key": "org/chat/files/chat_over_api/44444444/a.txt",
    }
    assert isinstance(result, ConversationFile)
    assert result.id == FILE_ID


async def test_upload_posts_permission_fields_then_file_to_storage(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    await client.chat.upload_file(b"hello", filename="a.txt", mimetype="text/plain")

    request = upload_routes.storage.calls.last.request
    body = request.content.decode()
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert 'name="policy"' in body
    assert "opaque-signature" in body
    # S3 ignores every form field that comes after the file part.
    assert body.index('name="policy"') < body.index('name="file"')
    assert 'filename="a.txt"' in body
    assert "hello" in body


async def test_upload_never_sends_the_api_token_to_storage(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    await client.chat.upload_file(b"hello", filename="a.txt", mimetype="text/plain")

    assert "x-cominty-token" in upload_routes.permission.calls.last.request.headers
    assert "x-cominty-token" not in upload_routes.storage.calls.last.request.headers


async def test_upload_reads_a_path_and_infers_name_and_mimetype(
    client: AsyncCominty, upload_routes: _UploadRoutes, tmp_path: Path
) -> None:
    source = tmp_path / "data.csv"
    source.write_bytes(b"a,b\n1,2\n")

    await client.chat.upload_file(source)

    params = dict(upload_routes.permission.calls.last.request.url.params)
    assert params == {"filename": "data.csv", "mimetype": "text/csv"}
    assert b"a,b\n1,2\n" in upload_routes.storage.calls.last.request.content


async def test_upload_explicit_name_and_mimetype_win_over_the_path(
    client: AsyncCominty, upload_routes: _UploadRoutes, tmp_path: Path
) -> None:
    source = tmp_path / "data.csv"
    source.write_bytes(b"x")

    await client.chat.upload_file(source, filename="renamed.bin", mimetype="application/x-custom")

    params = dict(upload_routes.permission.calls.last.request.url.params)
    assert params == {"filename": "renamed.bin", "mimetype": "application/x-custom"}


async def test_upload_unknown_extension_falls_back_to_octet_stream(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    await client.chat.upload_file(b"x", filename="blob.unknownext")

    params = dict(upload_routes.permission.calls.last.request.url.params)
    assert params["mimetype"] == "application/octet-stream"


async def test_upload_bytes_over_the_size_limit_raise_before_any_request(
    client: AsyncCominty, upload_routes: _UploadRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cominty_sdk.resources.chat._MAX_UPLOAD_BYTES", 10)

    with pytest.raises(InvalidParams, match="11 bytes, over the 10 bytes") as caught:
        await client.chat.upload_file(b"x" * 11, filename="a.txt")

    assert [error["param"] for error in caught.value.errors] == ["file"]
    assert not upload_routes.permission.called


async def test_upload_exactly_at_the_size_limit_is_accepted(
    client: AsyncCominty, upload_routes: _UploadRoutes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cominty_sdk.resources.chat._MAX_UPLOAD_BYTES", 10)

    await client.chat.upload_file(b"x" * 10, filename="a.txt")

    assert upload_routes.permission.called


async def test_upload_path_over_the_size_limit_is_refused_without_reading_it(
    client: AsyncCominty,
    upload_routes: _UploadRoutes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cominty_sdk.resources.chat._MAX_UPLOAD_BYTES", 10)
    source = tmp_path / "big.bin"
    source.write_bytes(b"x" * 11)
    monkeypatch.setattr(Path, "read_bytes", _fail_if_read)

    with pytest.raises(InvalidParams, match="over the 10 bytes"):
        await client.chat.upload_file(source)

    assert not upload_routes.permission.called


def test_the_size_limit_is_500_mib() -> None:
    assert _MAX_UPLOAD_BYTES == 524_288_000


async def test_upload_missing_path_raises_file_not_found(
    client: AsyncCominty, upload_routes: _UploadRoutes, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        await client.chat.upload_file(tmp_path / "nope.txt")

    assert not upload_routes.permission.called


@pytest.mark.parametrize("bad_filename", ["", "a/b.txt", "x" * 256])
async def test_upload_invalid_filename_raises_before_any_request(
    client: AsyncCominty, upload_routes: _UploadRoutes, bad_filename: str
) -> None:
    with pytest.raises(InvalidParams) as caught:
        await client.chat.upload_file(b"x", filename=bad_filename)

    assert [error["param"] for error in caught.value.errors] == ["filename"]
    assert not upload_routes.permission.called


async def test_upload_empty_mimetype_is_rejected(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    with pytest.raises(InvalidParams) as caught:
        await client.chat.upload_file(b"x", filename="a.txt", mimetype="")

    assert [error["param"] for error in caught.value.errors] == ["mimetype"]
    assert not upload_routes.permission.called


async def test_upload_bytes_without_filename_raises(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    with pytest.raises(InvalidParams) as caught:
        await client.chat.upload_file(b"x")

    assert [error["param"] for error in caught.value.errors] == ["filename"]
    assert not upload_routes.permission.called


async def test_upload_plain_str_is_rejected_without_echoing_it(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    with pytest.raises(InvalidParams, match="wrap a path in Path") as caught:
        await client.chat.upload_file(cast("bytes", "my secret text"), filename="a.txt")

    assert [error["param"] for error in caught.value.errors] == ["file"]
    assert caught.value.errors[0]["input"] is None
    assert "my secret text" not in str(caught.value)
    assert not upload_routes.permission.called


@pytest.mark.parametrize("not_a_file", [bytearray(b"x"), memoryview(b"x"), 42])
async def test_upload_other_types_are_rejected(
    client: AsyncCominty, upload_routes: _UploadRoutes, not_a_file: object
) -> None:
    with pytest.raises(InvalidParams, match="expected bytes or a pathlib.Path") as caught:
        await client.chat.upload_file(cast("bytes", not_a_file), filename="a.txt")

    assert type(not_a_file).__name__ in str(caught.value)
    assert not upload_routes.permission.called


async def test_upload_directory_raises_os_error(
    client: AsyncCominty, upload_routes: _UploadRoutes, tmp_path: Path
) -> None:
    with pytest.raises(IsADirectoryError):
        await client.chat.upload_file(tmp_path, filename="dir.txt")

    assert not upload_routes.permission.called


async def test_upload_path_without_a_name_is_rejected(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    with pytest.raises(InvalidParams) as caught:
        await client.chat.upload_file(Path("/"))

    assert [error["param"] for error in caught.value.errors] == ["filename"]


async def test_upload_permission_refused_raises_api_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/chat/files/upload").mock(
        return_value=httpx.Response(400, json={"detail": "Too many pending files"})
    )

    with pytest.raises(APIError, match="Too many pending files"):
        await client.chat.upload_file(b"x", filename="a.txt")


async def test_upload_permission_without_key_raises_sdk_error_without_leaking_fields(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/chat/files/upload").mock(
        return_value=httpx.Response(
            200, json={"url": STORAGE_URL, "fields": {"x-amz-signature": "secret-signature"}}
        )
    )

    with pytest.raises(SDKError, match="did not answer with a presigned upload") as caught:
        await client.chat.upload_file(b"x", filename="a.txt")

    assert "secret-signature" not in str(caught.value)
    assert caught.value.__suppress_context__


async def test_upload_storage_error_surfaces_the_s3_reason(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(
        return_value=_xml_error(400, "EntityTooLarge", "Your proposed upload exceeds the maximum")
    )

    with pytest.raises(APIError, match="EntityTooLarge: Your proposed upload exceeds") as caught:
        await client.chat.upload_file(b"x", filename="a.txt")

    assert caught.value.status_code == 400
    assert not upload_routes.confirm.called


async def test_upload_storage_error_without_message_keeps_the_code(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(return_value=_xml_error(403, "AccessDenied"))

    with pytest.raises(APIError) as caught:
        await client.chat.upload_file(b"x", filename="a.txt")

    assert str(caught.value) == "AccessDenied"


async def test_upload_storage_error_entities_are_decoded(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(
        return_value=_xml_error(400, "InvalidArgument", "Policy says &quot;no&quot; &amp; more")
    )

    with pytest.raises(APIError, match='InvalidArgument: Policy says "no" & more'):
        await client.chat.upload_file(b"x", filename="a.txt")


async def test_upload_storage_error_is_only_parsed_when_the_body_is_xml(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(return_value=_xml_error(502, "FakeCode", content_type="text/html"))

    with pytest.raises(ServerError, match="HTTP 502"):
        await client.chat.upload_file(b"x", filename="a.txt")


async def test_upload_storage_error_without_xml_falls_back_to_status(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(
        return_value=httpx.Response(
            500, text="gateway exploded", headers={"Content-Type": "application/xml"}
        )
    )

    with pytest.raises(ServerError, match="HTTP 500"):
        await client.chat.upload_file(b"x", filename="a.txt")


async def test_upload_storage_without_etag_raises_sdk_error(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(return_value=httpx.Response(204))

    with pytest.raises(SDKError, match="no ETag"):
        await client.chat.upload_file(b"x", filename="a.txt")

    assert not upload_routes.confirm.called


@pytest.mark.parametrize("headers", [{"Location": "https://elsewhere.example.com"}, {}])
async def test_upload_storage_redirect_is_an_error(
    client: AsyncCominty, upload_routes: _UploadRoutes, headers: dict[str, str]
) -> None:
    upload_routes.storage.mock(return_value=httpx.Response(307, headers=headers))

    with pytest.raises(APIError, match="redirect") as caught:
        await client.chat.upload_file(b"x", filename="a.txt")

    assert caught.value.status_code == 307
    assert not upload_routes.confirm.called


async def test_upload_storage_timeout_raises_connection_error(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(side_effect=httpx.TimeoutException("boom"))

    with pytest.raises(APIConnectionError, match="Upload to .* timed out"):
        await client.chat.upload_file(b"x", filename="a.txt")


async def test_upload_storage_network_error_raises_connection_error(
    client: AsyncCominty, upload_routes: _UploadRoutes
) -> None:
    upload_routes.storage.mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(APIConnectionError, match="Upload to .* failed"):
        await client.chat.upload_file(b"x", filename="a.txt")


async def test_download_follows_the_presigned_url_and_returns_bytes(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    api_route = mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json=SIGNED_DOWNLOAD_URL)
    )
    storage_route = mock_api.get(SIGNED_DOWNLOAD_URL).mock(
        return_value=httpx.Response(200, content=b"raw file bytes")
    )

    result = await client.chat.download_file(FILE_ID)

    assert result == b"raw file bytes"
    assert "x-cominty-token" in api_route.calls.last.request.headers
    assert "x-cominty-token" not in storage_route.calls.last.request.headers


async def test_download_unknown_file_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )

    with pytest.raises(NotFoundError):
        await client.chat.download_file(FILE_ID)


async def test_download_rejects_a_response_that_is_not_a_url_string(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json={"url": SIGNED_DOWNLOAD_URL})
    )

    with pytest.raises(SDKError, match="did not answer with a download URL"):
        await client.chat.download_file(FILE_ID)


async def test_download_empty_id_raises_before_any_request(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(ValueError, match="file_id must be a non-empty string"):
        await client.chat.download_file("")

    assert not mock_api.calls


async def test_download_id_cannot_escape_the_files_path(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(url__regex=r"/chat/files/.*").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )

    with pytest.raises(NotFoundError):
        await client.chat.download_file("../threads")

    assert route.calls.last.request.url.raw_path == b"/chat/files/..%2Fthreads"


@pytest.mark.parametrize("headers", [{"Location": "https://elsewhere.example.com"}, {}])
async def test_download_storage_redirect_is_an_error(
    client: AsyncCominty, mock_api: respx.MockRouter, headers: dict[str, str]
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json=SIGNED_DOWNLOAD_URL)
    )
    mock_api.get(SIGNED_DOWNLOAD_URL).mock(return_value=httpx.Response(307, headers=headers))

    with pytest.raises(APIError, match="redirect") as caught:
        await client.chat.download_file(FILE_ID)

    assert caught.value.status_code == 307


async def test_download_storage_error_surfaces_the_s3_reason(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json=SIGNED_DOWNLOAD_URL)
    )
    mock_api.get(SIGNED_DOWNLOAD_URL).mock(
        return_value=_xml_error(403, "AccessDenied", "Request has expired")
    )

    with pytest.raises(APIError, match="AccessDenied: Request has expired"):
        await client.chat.download_file(FILE_ID)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.TimeoutException("boom"), "timed out"),
        (httpx.ConnectError("no route"), "failed"),
    ],
)
async def test_download_network_errors_never_leak_the_signature(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    failure: httpx.RequestError,
    expected: str,
) -> None:
    mock_api.get(f"/chat/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json=SIGNED_DOWNLOAD_URL)
    )
    mock_api.get(SIGNED_DOWNLOAD_URL).mock(side_effect=failure)

    with pytest.raises(APIConnectionError, match=expected) as caught:
        await client.chat.download_file(FILE_ID)

    assert "secret-signature" not in str(caught.value)
    assert "Download from https://storage.example.com/files/a.txt " in str(caught.value)
