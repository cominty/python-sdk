from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx

from cominty_sdk import (
    AsyncCominty,
    FileOut,
    InvalidParams,
    NotFoundError,
    SDKError,
    SourceOut,
    SourceStatus,
    SourceSyncFailed,
)
from cominty_sdk.resources.sources import _MAX_FILES_PER_SOURCE

STORAGE_URL = "https://storage.example.com/upload-bucket"
SIGNED_DOWNLOAD_URL = "https://storage.example.com/files/a.txt?X-Amz-Signature=secret-signature"
DRIVE_ID = "drv_V1StGXR8_Z5jdHi6B"
SOURCE_PID = "src_PmeJ7Hw1l2Z0QyAbC"
FILE_ID = "fil_a1B2c3D4e5F6g7H8i"
ETAG = '"abc123etag"'


def _permission() -> dict[str, object]:
    return {
        "url": STORAGE_URL,
        "fields": {"key": "org/drives/drv/a.txt", "policy": "opaque", "x-amz-signature": "sig"},
    }


def _file(name: str = "a.txt", *, id: str = FILE_ID) -> dict[str, object]:
    return {
        "id": id,
        "created_at": "2026-06-28T10:00:00Z",
        "updated_at": "2026-06-28T10:00:00Z",
        "name": name,
        "size": 5,
        "mimetype": "text/plain",
    }


def _drive(files: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"id": DRIVE_ID, "files": files or []}


def _source(
    status: str = "synced",
    *,
    pid: str = SOURCE_PID,
    config: dict[str, object] | None = None,
    store: str = "draganddrop",
) -> dict[str, object]:
    return {
        "id": 42,
        "pid": pid,
        "created_at": "2026-06-28T10:00:00Z",
        "name": "Product docs",
        "scope": "private",
        "created_by": "user_31HPTBuBvX20xlQNAbvxjOxPbKB",
        "store": store,
        "status": status,
        "size": 10,
        "embedded_size": 10,
        "config": (
            {"meta": {"status": "ok", "errors": None}, "values": {"drive_id": DRIVE_ID}}
            if config is None
            else config
        ),
        "documents_synced": 1,
        "documents_failed": 0,
        "oversized_documents": 0,
        "documents_embedded": 1,
        "last_synced_at": None,
        "archived_at": None,
        "connection": None,
    }


class _Routes:
    def __init__(self, mock_api: respx.MockRouter) -> None:
        self.create_drive = mock_api.post("/drives").mock(
            return_value=httpx.Response(200, json=_drive())
        )
        self.get_drive = mock_api.get(f"/drives/{DRIVE_ID}").mock(
            return_value=httpx.Response(200, json=_drive([_file()]))
        )
        self.permission = mock_api.get(f"/drives/{DRIVE_ID}/upload").mock(
            return_value=httpx.Response(200, json=_permission())
        )
        self.storage = mock_api.post(STORAGE_URL).mock(
            return_value=httpx.Response(204, headers={"ETag": ETAG})
        )
        self.confirm = mock_api.post("/drives/upload").mock(
            return_value=httpx.Response(200, json=_file())
        )
        self.create_source = mock_api.post("/dc/sources").mock(
            return_value=httpx.Response(200, json=_source("pending"))
        )
        self.list_sources = mock_api.get("/dc/sources").mock(
            return_value=httpx.Response(200, json=[_source()])
        )
        self.status = mock_api.put(f"/dc/sources/{SOURCE_PID}/status").mock(
            return_value=httpx.Response(200, json=_source("syncing"))
        )


@pytest.fixture
def routes(mock_api: respx.MockRouter) -> _Routes:
    return _Routes(mock_api)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "b.md").write_text("# b")
    (root / "a.txt").write_text("hello")
    (root / ".hidden").write_text("skip me")
    (root / "nested").mkdir()
    (root / "nested" / "c.txt").write_text("skip me too")
    return root


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
async def test_create_from_folder_runs_drive_uploads_then_source(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    source = await client.sources.create(folder)

    assert isinstance(source, SourceOut)
    assert source.status is SourceStatus.pending
    assert routes.create_drive.call_count == 1
    # Top-level regular files only, sorted; hidden files and sub-folders are skipped.
    names = [dict(call.request.url.params)["filename"] for call in routes.permission.calls]
    assert names == ["a.txt", "b.md"]
    assert dict(routes.permission.calls[1].request.url.params)["mimetype"] == "text/markdown"
    assert routes.storage.call_count == 2
    assert b"hello" in routes.storage.calls[0].request.content
    assert json.loads(routes.confirm.calls.last.request.content) == {
        "etag": ETAG,
        "key": "org/drives/drv/a.txt",
    }
    assert json.loads(routes.create_source.calls.last.request.content) == {
        "store": "draganddrop",
        "scope": "private",
        "config": {"drive_id": DRIVE_ID},
    }


async def test_create_never_sends_the_api_token_to_storage(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    await client.sources.create(folder)

    assert "x-cominty-token" in routes.permission.calls.last.request.headers
    assert "x-cominty-token" not in routes.storage.calls.last.request.headers


async def test_create_with_name_and_a_single_file(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    await client.sources.create(folder / "a.txt", name="FAQ")

    assert routes.permission.call_count == 1
    body = json.loads(routes.create_source.calls.last.request.content)
    assert body["name"] == "FAQ"


async def test_create_with_an_iterable_of_paths(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    await client.sources.create(iter([folder / "b.md", folder / "a.txt"]))

    # Explicit lists keep the caller's order.
    names = [dict(call.request.url.params)["filename"] for call in routes.permission.calls]
    assert names == ["b.md", "a.txt"]


@pytest.mark.parametrize(
    ("files", "match"),
    [
        ("knowledge", "got str: wrap a path in Path"),
        (42, "got int"),
        ([], "at least one file"),
        (["a.txt"], r"files\[0\]: expected a pathlib.Path, got str: wrap"),
        ([42], r"files\[0\]: expected a pathlib.Path, got int"),
    ],
)
async def test_create_rejects_bad_files_argument_before_any_request(
    client: AsyncCominty, routes: _Routes, files: object, match: str
) -> None:
    with pytest.raises(InvalidParams, match=match):
        await client.sources.create(cast("Path", files))

    assert routes.create_drive.call_count == 0


async def test_create_rejects_an_empty_folder(
    client: AsyncCominty, routes: _Routes, tmp_path: Path
) -> None:
    with pytest.raises(InvalidParams, match="contains no files"):
        await client.sources.create(tmp_path)

    assert routes.create_drive.call_count == 0


async def test_create_rejects_a_missing_file(
    client: AsyncCominty, routes: _Routes, tmp_path: Path
) -> None:
    with pytest.raises(InvalidParams, match="is not a readable file"):
        await client.sources.create([tmp_path / "ghost.txt"])

    assert routes.create_drive.call_count == 0


async def test_create_rejects_two_files_with_the_same_name(
    client: AsyncCominty, routes: _Routes, tmp_path: Path
) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    (tmp_path / "x" / "same.txt").write_text("1")
    (tmp_path / "y" / "same.txt").write_text("2")

    with pytest.raises(InvalidParams, match="share the name 'same.txt'"):
        await client.sources.create([tmp_path / "x" / "same.txt", tmp_path / "y" / "same.txt"])

    assert routes.create_drive.call_count == 0


async def test_create_rejects_more_than_the_per_source_cap(
    client: AsyncCominty, routes: _Routes, tmp_path: Path
) -> None:
    for index in range(_MAX_FILES_PER_SOURCE + 1):
        (tmp_path / f"{index}.txt").write_text("x")

    with pytest.raises(InvalidParams, match=f"at most {_MAX_FILES_PER_SOURCE} files") as caught:
        await client.sources.create(tmp_path)

    assert caught.value.errors[0]["param"] == "files"
    assert routes.create_drive.call_count == 0


async def test_create_rejects_a_non_string_name(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    with pytest.raises(InvalidParams, match="name") as caught:
        await client.sources.create(folder, name=cast("str", 42))

    # Fails after the uploads (the API validates the name) but before the source exists.
    assert caught.value.errors[0]["param"] == "name"
    assert routes.create_source.call_count == 0


async def test_create_permission_without_key_raises_sdk_error(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    routes.permission.mock(
        return_value=httpx.Response(200, json={"url": STORAGE_URL, "fields": {"sig": "secret"}})
    )

    with pytest.raises(SDKError, match="did not answer with a presigned upload") as caught:
        await client.sources.create(folder)

    assert "secret" not in str(caught.value)
    assert routes.create_source.call_count == 0


# --------------------------------------------------------------------------- #
# list / get / update
# --------------------------------------------------------------------------- #
async def test_list_returns_sources(client: AsyncCominty, routes: _Routes) -> None:
    sources = await client.sources.list()

    assert [s.pid for s in sources] == [SOURCE_PID]
    assert sources[0].id == 42
    assert routes.list_sources.calls.last.request.method == "GET"


async def test_get_picks_the_source_from_the_listing(client: AsyncCominty, routes: _Routes) -> None:
    routes.list_sources.mock(
        return_value=httpx.Response(200, json=[_source(pid="other"), _source()])
    )

    source = await client.sources.get(SOURCE_PID)

    assert source.pid == SOURCE_PID


async def test_get_unknown_pid_raises_not_found(client: AsyncCominty, routes: _Routes) -> None:
    with pytest.raises(NotFoundError, match="no source with pid 'nope'") as caught:
        await client.sources.get("nope")

    assert caught.value.status_code == 404


async def test_update_sends_the_name(
    client: AsyncCominty, routes: _Routes, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put(f"/dc/sources/{SOURCE_PID}").mock(
        return_value=httpx.Response(200, json=_source())
    )

    source = await client.sources.update(SOURCE_PID, name="Renamed")

    assert isinstance(source, SourceOut)
    assert json.loads(route.calls.last.request.content) == {"name": "Renamed"}


async def test_update_rejects_a_non_string_name(client: AsyncCominty, routes: _Routes) -> None:
    with pytest.raises(InvalidParams, match="name"):
        await client.sources.update(SOURCE_PID, name=cast("str", None))


# --------------------------------------------------------------------------- #
# files
# --------------------------------------------------------------------------- #
async def test_add_files_uploads_into_the_drive_then_syncs(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    added = await client.sources.add_files(SOURCE_PID, [folder / "a.txt"])

    assert [isinstance(f, FileOut) for f in added] == [True]
    assert routes.get_drive.call_count == 1
    assert routes.permission.call_count == 1
    assert routes.confirm.call_count == 1
    assert dict(routes.status.calls.last.request.url.params) == {"operation": "sync"}


@pytest.mark.parametrize("status", ["pending", "syncing", "paused", "cancelling"])
async def test_add_files_skips_the_sync_when_not_allowed(
    client: AsyncCominty, routes: _Routes, folder: Path, status: str
) -> None:
    routes.list_sources.mock(return_value=httpx.Response(200, json=[_source(status)]))

    await client.sources.add_files(SOURCE_PID, [folder / "a.txt"])

    assert routes.permission.call_count == 1
    assert routes.status.call_count == 0


async def test_add_files_counts_the_files_already_in_the_source(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    existing = [_file(f"{i}.txt", id=str(i)) for i in range(_MAX_FILES_PER_SOURCE - 1)]
    routes.get_drive.mock(return_value=httpx.Response(200, json=_drive(existing)))

    with pytest.raises(InvalidParams, match=f"this would make {_MAX_FILES_PER_SOURCE + 1}"):
        await client.sources.add_files(SOURCE_PID, folder)

    assert routes.permission.call_count == 0


async def test_add_files_without_a_drive_raises_sdk_error(
    client: AsyncCominty, routes: _Routes, folder: Path
) -> None:
    routes.list_sources.mock(
        return_value=httpx.Response(200, json=[_source(config={}, store="googledrive")])
    )

    with pytest.raises(SDKError, match="has no drive_id"):
        await client.sources.add_files(SOURCE_PID, folder)


async def test_list_files_reads_the_drive(client: AsyncCominty, routes: _Routes) -> None:
    files = await client.sources.list_files(SOURCE_PID)

    assert [f.name for f in files] == ["a.txt"]
    assert routes.get_drive.calls.last.request.method == "GET"


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"meta": {}, "values": {"drive_id": DRIVE_ID}}, DRIVE_ID),
        ({"drive_id": DRIVE_ID}, DRIVE_ID),
        ({"values": {"drive_id": ""}}, None),
        ({"values": "oops"}, None),
        ({}, None),
    ],
)
async def test_drive_id_reads_nested_or_flat_config(
    client: AsyncCominty, routes: _Routes, config: dict[str, object], expected: str | None
) -> None:
    routes.list_sources.mock(return_value=httpx.Response(200, json=[_source(config=config)]))

    source = await client.sources.get(SOURCE_PID)

    assert source.drive_id == expected


async def test_remove_file_deletes_then_syncs(
    client: AsyncCominty, routes: _Routes, mock_api: respx.MockRouter
) -> None:
    route = mock_api.delete(f"/files/{FILE_ID}").mock(return_value=httpx.Response(200))

    await client.sources.remove_file(SOURCE_PID, FILE_ID)

    assert route.call_count == 1
    assert dict(routes.status.calls.last.request.url.params) == {"operation": "sync"}


async def test_remove_file_rejects_an_empty_id(client: AsyncCominty, routes: _Routes) -> None:
    with pytest.raises(ValueError, match="file_id must be a non-empty string"):
        await client.sources.remove_file(SOURCE_PID, "")


async def test_download_file_fetches_the_presigned_url_without_the_token(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    api = mock_api.get(f"/files/{FILE_ID}").mock(
        return_value=httpx.Response(200, json=SIGNED_DOWNLOAD_URL)
    )
    storage = mock_api.get(SIGNED_DOWNLOAD_URL).mock(
        return_value=httpx.Response(200, content=b"hello")
    )

    assert await client.sources.download_file(FILE_ID) == b"hello"
    assert "x-cominty-token" in api.calls.last.request.headers
    assert "x-cominty-token" not in storage.calls.last.request.headers


async def test_download_file_without_a_url_raises_sdk_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/files/{FILE_ID}").mock(return_value=httpx.Response(200, json={"nope": 1}))

    with pytest.raises(SDKError, match="did not answer with a download URL"):
        await client.sources.download_file(FILE_ID)


async def test_download_file_rejects_an_empty_id(client: AsyncCominty) -> None:
    with pytest.raises(ValueError, match="file_id must be a non-empty string"):
        await client.sources.download_file("")


# --------------------------------------------------------------------------- #
# status operations
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("operation", ["start", "pause", "sync", "archive"])
async def test_status_verbs_send_the_operation(
    client: AsyncCominty, routes: _Routes, operation: str
) -> None:
    method = cast("Any", getattr(client.sources, operation))

    source = await method(SOURCE_PID)

    assert isinstance(source, SourceOut)
    request = routes.status.calls.last.request
    assert request.method == "PUT"
    assert dict(request.url.params) == {"operation": operation}


# --------------------------------------------------------------------------- #
# wait_synced
# --------------------------------------------------------------------------- #
async def test_wait_synced_polls_until_synced(client: AsyncCominty, routes: _Routes) -> None:
    routes.list_sources.mock(
        side_effect=[
            httpx.Response(200, json=[_source("pending")]),
            httpx.Response(200, json=[_source("syncing")]),
            httpx.Response(200, json=[_source("synced")]),
        ]
    )

    source = await client.sources.wait_synced(SOURCE_PID, interval=0)

    assert source.status is SourceStatus.synced
    assert routes.list_sources.call_count == 3


@pytest.mark.parametrize(
    "status",
    ["error", "paused", "archived", "daily_quota_reached", "invalid_configuration"],
)
async def test_wait_synced_raises_when_the_source_settles_elsewhere(
    client: AsyncCominty, routes: _Routes, status: str
) -> None:
    routes.list_sources.mock(return_value=httpx.Response(200, json=[_source(status)]))

    with pytest.raises(SourceSyncFailed, match=f"stopped in status {status!r}") as caught:
        await client.sources.wait_synced(SOURCE_PID, interval=0)

    assert caught.value.source.status == SourceStatus(status)


async def test_wait_synced_times_out(client: AsyncCominty, routes: _Routes) -> None:
    routes.list_sources.mock(return_value=httpx.Response(200, json=[_source("syncing")]))

    with pytest.raises(asyncio.TimeoutError):
        await client.sources.wait_synced(SOURCE_PID, timeout=0.05, interval=0.01)
