from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import respx

from cominty_sdk import AsyncCominty, Thread, ThreadSummary

# Mirror the canonical ids in conftest (tests/ is not an importable package).
THREAD_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"

MakeThread = Callable[..., dict[str, Any]]


def _summary(name: str = "A thread") -> dict[str, Any]:
    return {
        "id": THREAD_ID,
        "name": name,
        "created_at": "2026-06-28T10:00:00Z",
        "live": False,
        "agent": {"id": "agt_1", "name": "Support"},
        "starred": False,
        "project_id": None,
    }


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
async def test_list_scopes_to_client_user_id(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/chat").mock(
        return_value=httpx.Response(200, json=[_summary("one"), _summary("two")])
    )

    threads = await client.threads.list()

    assert [t.name for t in threads] == ["one", "two"]
    assert all(isinstance(t, ThreadSummary) for t in threads)
    params = route.calls.last.request.url.params
    assert params["user_id"] == USER_ID
    assert params["limit"] == "50"
    assert params["page"] == "0"


async def test_list_passes_pagination_and_terms(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/chat").mock(return_value=httpx.Response(200, json=[]))

    await client.threads.list(limit=10, page=2, terms=["invoice", "q3"])

    params = route.calls.last.request.url.params
    assert params["limit"] == "10"
    assert params["page"] == "2"
    assert params.get_list("terms") == ["invoice", "q3"]


# --------------------------------------------------------------------------- #
# get
# --------------------------------------------------------------------------- #
async def test_get_returns_full_thread(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    route = mock_api.get(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(200, json=make_thread())
    )

    thread = await client.threads.get(THREAD_ID)

    assert isinstance(thread, Thread)
    assert str(thread.id) == THREAD_ID
    assert len(thread.messages) == 2  # full history, not just a summary
    assert route.calls.last.request.method == "GET"


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
async def test_update_sends_only_provided_fields(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    # PUT /chat/{id} responds with a summary (NO messages), not a full Thread.
    route = mock_api.put(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(200, json={**_summary("Renamed"), "starred": True})
    )

    thread = await client.threads.update(THREAD_ID, name="Renamed")

    request = route.calls.last.request
    assert request.method == "PUT"
    # starred omitted -> excluded from the body (partial update)
    assert json.loads(request.content) == {"name": "Renamed"}
    assert isinstance(thread, ThreadSummary)
    assert thread.name == "Renamed"


async def test_update_starred_only(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.put(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(200, json={**_summary(), "starred": True})
    )

    result = await client.threads.update(THREAD_ID, starred=True)

    assert json.loads(route.calls.last.request.content) == {"starred": True}
    assert result.starred is True


# --------------------------------------------------------------------------- #
# archive
# --------------------------------------------------------------------------- #
async def test_archive_sends_delete(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.delete(f"/chat/{THREAD_ID}").mock(return_value=httpx.Response(204))

    result = await client.threads.archive(THREAD_ID)

    assert result is None
    assert route.calls.last.request.method == "DELETE"
