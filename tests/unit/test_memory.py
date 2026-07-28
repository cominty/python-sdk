"""Unit tests for the memory resource: list, create, get, update, delete.

user_id is sourced from the client (set once at construction). Every memory
endpoint takes it as a query param except POST /memory, which takes it in the
request body instead — confirmed against the validated OpenAPI contract.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from cominty_sdk import (
    AsyncCominty,
    ConflictError,
    InvalidParams,
    MemoryFileOut,
    MemoryFileSummaryOut,
)

USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"


def _file(
    path: str = "notes/todo.md",
    *,
    purpose: str = "scratch notes",
    content: str = "buy milk",
    version: str = "v1",
) -> dict[str, object]:
    return {
        "path": path,
        "purpose": purpose,
        "content": content,
        "created_at": "2026-06-28T10:00:00Z",
        "updated_at": "2026-06-28T10:00:00Z",
        "version": version,
    }


def _summary(
    path: str = "notes/todo.md", *, purpose: str = "scratch notes", version: str = "v1"
) -> dict[str, object]:
    return {
        "path": path,
        "purpose": purpose,
        "created_at": "2026-06-28T10:00:00Z",
        "updated_at": "2026-06-28T10:00:00Z",
        "version": version,
    }


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
async def test_list_scopes_to_client_user_id(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/memory").mock(
        return_value=httpx.Response(200, json=[_summary("a"), _summary("b")])
    )

    files = await client.memory.list()

    assert [f.path for f in files] == ["a", "b"]
    assert all(isinstance(f, MemoryFileSummaryOut) for f in files)
    params = route.calls.last.request.url.params
    assert params["user_id"] == USER_ID
    assert route.calls.last.request.method == "GET"


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
async def test_create_sends_user_id_in_body_not_query(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/memory").mock(
        return_value=httpx.Response(201, json=_file())
    )

    result = await client.memory.create(
        path="notes/todo.md", purpose="scratch notes", content="buy milk"
    )

    request = route.calls.last.request
    assert request.method == "POST"
    # user_id belongs in the body here — every other memory endpoint puts it
    # in the query string instead.
    assert "user_id" not in request.url.params
    body = json.loads(request.content)
    assert body == {
        "path": "notes/todo.md",
        "purpose": "scratch notes",
        "content": "buy milk",
        "user_id": USER_ID,
    }
    assert isinstance(result, MemoryFileOut)
    assert result.path == "notes/todo.md"


async def test_create_conflict_raises_conflict_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.post("/memory").mock(
        return_value=httpx.Response(
            409, json={"detail": "A memory file already exists at 'notes/todo.md'."}
        )
    )

    with pytest.raises(ConflictError):
        await client.memory.create(
            path="notes/todo.md", purpose="scratch notes", content="buy milk"
        )


# --------------------------------------------------------------------------- #
# get
# --------------------------------------------------------------------------- #
async def test_get_sends_path_and_user_id_as_query(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/memory/file").mock(
        return_value=httpx.Response(200, json=_file())
    )

    result = await client.memory.get("notes/todo.md")

    params = route.calls.last.request.url.params
    assert params["path"] == "notes/todo.md"
    assert params["user_id"] == USER_ID
    assert isinstance(result, MemoryFileOut)
    assert result.content == "buy milk"


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
async def test_update_omitted_field_is_excluded_from_body(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put("/memory/file").mock(
        return_value=httpx.Response(200, json=_file(content="new content", version="v2"))
    )

    result = await client.memory.update("notes/todo.md", version="v1", content="new content")

    request = route.calls.last.request
    # purpose was never passed -> excluded entirely, not sent as null.
    assert json.loads(request.content) == {"content": "new content"}
    params = request.url.params
    assert params["path"] == "notes/todo.md"
    assert params["version"] == "v1"
    assert params["user_id"] == USER_ID
    assert isinstance(result, MemoryFileOut)
    assert result.version == "v2"


async def test_update_explicit_none_clears_field(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put("/memory/file").mock(return_value=httpx.Response(200, json=_file()))

    await client.memory.update("notes/todo.md", version="v1", purpose=None)

    # An explicit None round-trips as a JSON null, distinct from being omitted.
    assert json.loads(route.calls.last.request.content) == {"purpose": None}


async def test_update_no_fields_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.update("notes/todo.md", version="v1")

    # Rejected client-side before any request is sent — a no-op PUT would just
    # waste a round trip and silently mask a caller bug.
    assert mock_api.calls.call_count == 0


async def test_update_version_round_trips_unchanged(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put("/memory/file").mock(return_value=httpx.Response(200, json=_file()))

    opaque_version = "W/\"2026-06-28T10:00:00Z-xyz\""
    await client.memory.update("notes/todo.md", version=opaque_version, content="x")

    assert route.calls.last.request.url.params["version"] == opaque_version


async def test_update_conflict_raises_conflict_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.put("/memory/file").mock(
        return_value=httpx.Response(409, json={"detail": "version mismatch"})
    )

    with pytest.raises(ConflictError):
        await client.memory.update("notes/todo.md", version="stale", content="x")


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
async def test_delete_sends_query_and_returns_none(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.delete("/memory/file").mock(return_value=httpx.Response(204))

    result = await client.memory.delete("notes/todo.md")

    assert result is None
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.params["path"] == "notes/todo.md"
    assert request.url.params["user_id"] == USER_ID


# --------------------------------------------------------------------------- #
# lifecycle
# --------------------------------------------------------------------------- #
async def test_full_lifecycle(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    mock_api.post("/memory").mock(return_value=httpx.Response(201, json=_file(version="v1")))
    mock_api.get("/memory").mock(return_value=httpx.Response(200, json=[_summary()]))
    mock_api.get("/memory/file").mock(return_value=httpx.Response(200, json=_file(version="v1")))
    mock_api.put("/memory/file").mock(
        return_value=httpx.Response(200, json=_file(content="updated", version="v2"))
    )
    mock_api.delete("/memory/file").mock(return_value=httpx.Response(204))

    created = await client.memory.create(
        path="notes/todo.md", purpose="scratch notes", content="buy milk"
    )
    listed = await client.memory.list()
    fetched = await client.memory.get(created.path)
    updated = await client.memory.update(
        fetched.path, version=fetched.version, content="updated"
    )
    deleted = await client.memory.delete(updated.path)

    assert created.path == "notes/todo.md"
    assert listed[0].path == "notes/todo.md"
    assert fetched.version == "v1"
    assert updated.content == "updated"
    assert updated.version == "v2"
    assert deleted is None