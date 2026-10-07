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

NAMESPACE = "support-bot"

# The live API rejects a path with more than one folder segment (422 "Maximum
# folder depth is 1").
TOO_DEEP_PATH = "a/b/c.md"

# The live API rejects a namespace longer than 128 characters.
TOO_LONG_NAMESPACE = "x" * 129


def _file(
    path: str = "notes/todo.md",
    *,
    namespace: str = NAMESPACE,
    purpose: str = "scratch notes",
    content: str = "buy milk",
    version: str = "v1",
) -> dict[str, object]:
    return {
        "path": path,
        "namespace": namespace,
        "purpose": purpose,
        "content": content,
        "created_at": "2026-06-28T10:00:00Z",
        "updated_at": "2026-06-28T10:00:00Z",
        "version": version,
    }


def _summary(
    path: str = "notes/todo.md",
    *,
    namespace: str = NAMESPACE,
    purpose: str = "scratch notes",
    version: str = "v1",
) -> dict[str, object]:
    return {
        "path": path,
        "namespace": namespace,
        "purpose": purpose,
        "created_at": "2026-06-28T10:00:00Z",
        "updated_at": "2026-06-28T10:00:00Z",
        "version": version,
    }


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
async def test_list_without_namespace_omits_query_param(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/memory").mock(
        return_value=httpx.Response(200, json=[_summary("a"), _summary("b")])
    )

    files = await client.memory.list()

    assert [f.path for f in files] == ["a", "b"]
    assert all(isinstance(f, MemoryFileSummaryOut) for f in files)
    assert "namespace" not in route.calls.last.request.url.params
    assert route.calls.last.request.method == "GET"


async def test_list_with_namespace_filters(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/memory").mock(return_value=httpx.Response(200, json=[_summary("a")]))

    await client.memory.list(namespace=NAMESPACE)

    assert route.calls.last.request.url.params["namespace"] == NAMESPACE


async def test_list_namespace_too_long_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.list(namespace=TOO_LONG_NAMESPACE)

    assert mock_api.calls.call_count == 0


# --------------------------------------------------------------------------- #
# list_namespaces
# --------------------------------------------------------------------------- #
async def test_list_namespaces_returns_distinct_names(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/memory/namespaces").mock(
        return_value=httpx.Response(200, json=["default", NAMESPACE])
    )

    namespaces = await client.memory.list_namespaces()

    assert namespaces == ["default", NAMESPACE]
    assert route.calls.last.request.method == "GET"


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
async def test_create_sends_namespace_in_body(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/memory").mock(return_value=httpx.Response(201, json=_file()))

    result = await client.memory.create(
        path="notes/todo.md", namespace=NAMESPACE, purpose="scratch notes", content="buy milk"
    )

    request = route.calls.last.request
    assert request.method == "POST"
    body = json.loads(request.content)
    assert body == {
        "path": "notes/todo.md",
        "namespace": NAMESPACE,
        "purpose": "scratch notes",
        "content": "buy milk",
    }
    assert isinstance(result, MemoryFileOut)
    assert result.path == "notes/todo.md"
    assert result.namespace == NAMESPACE


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
            path="notes/todo.md", namespace=NAMESPACE, purpose="scratch notes", content="buy milk"
        )


async def test_create_empty_content_is_allowed(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    # The API has no minimum-length constraint on content.
    mock_api.post("/memory").mock(return_value=httpx.Response(201, json=_file(content="")))

    result = await client.memory.create(
        path="notes/todo.md", namespace=NAMESPACE, purpose="scratch notes", content=""
    )

    assert result.content == ""


async def test_create_path_too_deep_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.create(
            path=TOO_DEEP_PATH, namespace=NAMESPACE, purpose="x", content="y"
        )

    assert mock_api.calls.call_count == 0


async def test_create_namespace_too_long_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.create(
            path="notes/todo.md", namespace=TOO_LONG_NAMESPACE, purpose="x", content="y"
        )

    assert mock_api.calls.call_count == 0


# --------------------------------------------------------------------------- #
# get
# --------------------------------------------------------------------------- #
async def test_get_sends_path_and_namespace_as_query(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/memory/file").mock(return_value=httpx.Response(200, json=_file()))

    result = await client.memory.get("notes/todo.md", namespace=NAMESPACE)

    params = route.calls.last.request.url.params
    assert params["path"] == "notes/todo.md"
    assert params["namespace"] == NAMESPACE
    assert isinstance(result, MemoryFileOut)
    assert result.content == "buy milk"


async def test_get_path_too_deep_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.get(TOO_DEEP_PATH, namespace=NAMESPACE)

    assert mock_api.calls.call_count == 0


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
async def test_update_omitted_field_is_excluded_from_body(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put("/memory/file").mock(
        return_value=httpx.Response(200, json=_file(content="new content", version="v2"))
    )

    result = await client.memory.update(
        "notes/todo.md", namespace=NAMESPACE, version="v1", content="new content"
    )

    request = route.calls.last.request
    assert json.loads(request.content) == {"content": "new content"}
    params = request.url.params
    assert params["path"] == "notes/todo.md"
    assert params["namespace"] == NAMESPACE
    assert params["version"] == "v1"
    assert isinstance(result, MemoryFileOut)
    assert result.version == "v2"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"purpose": None},
        {"content": None},
        {"content": "new content", "purpose": None},
    ],
)
async def test_update_explicit_none_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter, kwargs: dict[str, object]
) -> None:
    # The API silently ignores an explicit null (200, value unchanged) instead
    # of clearing the field, so the SDK rejects it client-side rather than
    # sending a request that looks like it succeeded but did nothing.
    with pytest.raises(InvalidParams):
        await client.memory.update("notes/todo.md", namespace=NAMESPACE, version="v1", **kwargs)

    assert mock_api.calls.call_count == 0


async def test_update_no_fields_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.update("notes/todo.md", namespace=NAMESPACE, version="v1")

    assert mock_api.calls.call_count == 0


async def test_update_version_round_trips_unchanged(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put("/memory/file").mock(return_value=httpx.Response(200, json=_file()))

    opaque_version = 'W/"2026-06-28T10:00:00Z-xyz"'
    await client.memory.update(
        "notes/todo.md", namespace=NAMESPACE, version=opaque_version, content="x"
    )

    assert route.calls.last.request.url.params["version"] == opaque_version


async def test_update_conflict_raises_conflict_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.put("/memory/file").mock(
        return_value=httpx.Response(409, json={"detail": "version mismatch"})
    )

    with pytest.raises(ConflictError):
        await client.memory.update(
            "notes/todo.md", namespace=NAMESPACE, version="stale", content="x"
        )


async def test_update_path_too_deep_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.update(TOO_DEEP_PATH, namespace=NAMESPACE, version="v1", content="x")

    assert mock_api.calls.call_count == 0


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
async def test_delete_sends_query_and_returns_none(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.delete("/memory/file").mock(return_value=httpx.Response(204))

    result = await client.memory.delete("notes/todo.md", namespace=NAMESPACE)

    assert result is None
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.params["path"] == "notes/todo.md"
    assert request.url.params["namespace"] == NAMESPACE


async def test_delete_path_too_deep_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams):
        await client.memory.delete(TOO_DEEP_PATH, namespace=NAMESPACE)

    assert mock_api.calls.call_count == 0


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
        path="notes/todo.md", namespace=NAMESPACE, purpose="scratch notes", content="buy milk"
    )
    listed = await client.memory.list(namespace=NAMESPACE)
    fetched = await client.memory.get(created.path, namespace=NAMESPACE)
    updated = await client.memory.update(
        fetched.path, namespace=NAMESPACE, version=fetched.version, content="updated"
    )
    deleted = await client.memory.delete(updated.path, namespace=NAMESPACE)

    assert created.path == "notes/todo.md"
    assert created.namespace == NAMESPACE
    assert listed[0].path == "notes/todo.md"
    assert fetched.version == "v1"
    assert updated.content == "updated"
    assert updated.version == "v2"
    assert deleted is None
