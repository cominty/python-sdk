"""Unit tests for the low-level transport: timeout/network error mapping on
both the plain-request and streaming paths, and JSONL line tolerance.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import APIConnectionError, AsyncCominty

MakeEvent = Callable[..., dict[str, Any]]
MakeMessage = Callable[..., dict[str, Any]]
Jsonl = Callable[..., str]


# --------------------------------------------------------------------------- #
# request() — timeout / network errors
# --------------------------------------------------------------------------- #
async def test_request_timeout_raises_connection_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/chat").mock(side_effect=httpx.TimeoutException("boom"))

    with pytest.raises(APIConnectionError, match="timed out"):
        await client.threads.list()


async def test_request_network_error_raises_connection_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/chat").mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(APIConnectionError, match="failed"):
        await client.threads.list()


# --------------------------------------------------------------------------- #
# stream_lines() — timeout / network errors
# --------------------------------------------------------------------------- #
async def test_stream_timeout_raises_connection_error(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    path = f"/chat/messages/{ids.assistant_msg}/stream"
    mock_api.get(path).mock(side_effect=httpx.TimeoutException("boom"))

    run = client.chat.stream(UUID(ids.assistant_msg))
    with pytest.raises(APIConnectionError, match="timed out"):
        async for _ in run:
            pass


async def test_stream_network_error_raises_connection_error(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    path = f"/chat/messages/{ids.assistant_msg}/stream"
    mock_api.get(path).mock(side_effect=httpx.ConnectError("no route"))

    run = client.chat.stream(UUID(ids.assistant_msg))
    with pytest.raises(APIConnectionError, match="failed"):
        async for _ in run:
            pass


# --------------------------------------------------------------------------- #
# JSONL line tolerance
# --------------------------------------------------------------------------- #
async def test_non_json_line_is_skipped(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("waiting_for_start", id="0-0"),
        "not valid json at all",
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(f"/chat/messages/{ids.assistant_msg}/stream").mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    names = [e.name async for e in run]

    assert names == ["waiting_for_start"]


async def test_non_dict_json_line_is_skipped(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("waiting_for_start", id="0-0"),
        "[1, 2, 3]",  # valid JSON, but not an object
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(f"/chat/messages/{ids.assistant_msg}/stream").mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    names = [e.name async for e in run]

    assert names == ["waiting_for_start"]
