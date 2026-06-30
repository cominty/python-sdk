"""Shared fixtures for the v1 test suite.

Minimalist on purpose — a base URL, a live ``AsyncCominty`` bound to a respx
mock, and small factories for the ``ThreadOut`` / ``MessageOut`` payloads the
chat endpoints return.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
import respx

from cominty_sdk import AsyncCominty

BASE_URL = "https://api.test"
THREAD_ID = "11111111-1111-1111-1111-111111111111"
USER_MSG_ID = "22222222-2222-2222-2222-222222222222"
ASSISTANT_MSG_ID = "33333333-3333-3333-3333-333333333333"
# A well-formed Cominty (Clerk) user id — matches ^user_[A-Za-z0-9]{20,}$, which
# the client validates at construction. Set once, applied to every call.
USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"


@pytest.fixture
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def user_id() -> str:
    return USER_ID


@pytest.fixture
def ids() -> SimpleNamespace:
    """Canonical UUIDs used across the default thread payload."""
    return SimpleNamespace(
        thread=THREAD_ID, user_msg=USER_MSG_ID, assistant_msg=ASSISTANT_MSG_ID
    )


@pytest_asyncio.fixture
async def client(base_url: str) -> AsyncIterator[AsyncCominty]:
    async with AsyncCominty(
        api_token="test-token", user_id=USER_ID, base_url=base_url
    ) as instance:
        yield instance


@pytest.fixture
def mock_api(base_url: str) -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=base_url, assert_all_called=False) as router:
        yield router


@pytest.fixture
def make_message() -> Callable[..., dict[str, Any]]:
    def _make(
        *,
        id: str,
        role: str,
        content: str = "",
        status: str = "success",
        live: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": id,
            "thread_id": THREAD_ID,
            "role": role,
            "content": content,
            "questions": None,
            "live": live,
            "status": status,
            "events": None,
            "structured_output": None,
            "files": [],
        }

    return _make


@pytest.fixture
def make_thread(
    make_message: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    def _make(
        *,
        messages: list[dict[str, Any]] | None = None,
        name: str = "Test thread",
    ) -> dict[str, Any]:
        if messages is None:
            messages = [
                make_message(id=USER_MSG_ID, role="user", content="hi"),
                make_message(
                    id=ASSISTANT_MSG_ID,
                    role="assistant",
                    content="",
                    status="pending",
                    live=True,
                ),
            ]
        return {
            "id": THREAD_ID,
            "name": name,
            "created_at": "2026-06-28T10:00:00Z",
            "live": True,
            "agent": {"id": "agt_1", "name": "Support"},
            "starred": False,
            "project_id": None,
            "messages": messages,
        }

    return _make


@pytest.fixture
def make_event() -> Callable[..., dict[str, Any]]:
    def _make(
        name: str,
        *,
        id: str = "1-0",
        correlation_id: int = 1,
        status: str = "success",
        at: str = "2026-06-29T10:00:00Z",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "id": id,
            "correlation_id": correlation_id,
            "at": at,
            "name": name,
            "status": status,
        }
        if data is not None:
            event["data"] = data
        return event

    return _make


@pytest.fixture
def jsonl() -> Callable[..., str]:
    """Render a JSONL stream body. ``dict`` items are JSON-encoded; ``str`` items
    are emitted verbatim (use ``""`` to inject a blank keep-alive line)."""

    def _make(*lines: dict[str, Any] | str) -> str:
        rendered = [ln if isinstance(ln, str) else json.dumps(ln) for ln in lines]
        return "\n".join(rendered) + "\n"

    return _make
