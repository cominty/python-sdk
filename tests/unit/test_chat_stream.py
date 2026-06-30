"""Exhaustive unit tests for the ``AssistantRun`` streaming handle.

Covers: events-only iteration, heartbeat/blank skipping, terminal capture via
``result``/``text``, single-use semantics, the server-shutdown ``Partial`` path,
forward-compat for unknown events, and stream-time HTTP errors.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import (
    AsyncCominty,
    NotFoundError,
    SDKError,
    StreamInterrupted,
    events,
)

MakeThread = Callable[..., dict[str, Any]]
MakeMessage = Callable[..., dict[str, Any]]
MakeEvent = Callable[..., dict[str, Any]]
Jsonl = Callable[..., str]

# A well-formed Cominty (Clerk) user id — see ^user_[A-Za-z0-9]{20,}$ validation.
_USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"

_COST = {
    "failed": False,
    "input_tokens": 10,
    "cached_tokens": 0,
    "output_tokens": 5,
    "input_cost": "0.001",
    "output_cost": "0.002",
    "total": "0.003",
}
_RESULT_DATA = {
    "reply": "final answer",
    "files": [],
    "questions": [],
    "metadata": None,
    "cost": _COST,
}


def _stream_path(message_id: str) -> str:
    return f"/chat/messages/{message_id}/stream"


# --------------------------------------------------------------------------- #
# Iteration — events only
# --------------------------------------------------------------------------- #
async def test_iterates_events_only_terminal_not_yielded(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("waiting_for_start", id="0-0", correlation_id=-1, status="running"),
        make_event(
            "llm",
            id="1-0",
            correlation_id=1,
            status="running",
            data={"description": "Reasoning", "model": "Opus"},
        ),
        make_event(
            "tool_call",
            id="2-0",
            correlation_id=2,
            status="success",
            data={"name": "web", "description": "search", "message": "done"},
        ),
        make_event("result", id="3-0", correlation_id=3, data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    collected = [event async for event in run]

    assert [e.name for e in collected] == [
        "waiting_for_start",
        "llm",
        "tool_call",
        "result",
    ]
    assert isinstance(collected[1], events.LlmStep)
    assert isinstance(collected[2], events.ToolCall)
    assert collected[2].data.message == "done"
    assert isinstance(collected[3], events.Result)
    assert collected[3].data.reply == "final answer"
    assert collected[3].data.cost.total == Decimal("0.003")


async def test_blank_heartbeat_line_skipped(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("waiting_for_start", id="0-0"),
        "",  # blank keep-alive line
        make_event("result", id="1-0", data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    names = [e.name async for e in run]

    assert names == ["waiting_for_start", "result"]


async def test_unknown_event_is_forward_compatible(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("brand_new_event", id="0-0", status="running", data={"x": 1}),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    collected = [event async for event in run]

    assert len(collected) == 1
    assert isinstance(collected[0], events.UnknownEvent)
    assert collected[0].name == "brand_new_event"


async def test_tracks_last_event_id_for_resume(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("waiting_for_start", id="0-0"),
        make_event("result", id="1782676050530-0", data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    async for _ in run:
        pass

    assert run._last_event_id == "1782676050530-0"  # noqa: SLF001


# --------------------------------------------------------------------------- #
# result() / text() — terminal capture
# --------------------------------------------------------------------------- #
async def test_result_returns_terminal_without_manual_iteration(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("result", id="1-0", data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    msg = await run.result()

    assert str(msg.id) == ids.assistant_msg
    assert msg.status.value == "success"
    assert msg.content == "final"
    assert msg.live is False


async def test_text_returns_final_reply(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(make_message(id=ids.assistant_msg, role="assistant", content="final"))
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    assert await run.text() == "final"


async def test_result_after_full_iteration_returns_terminal(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("result", id="1-0", data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    async for _ in run:
        pass

    assert (await run.result()).content == "final"


async def test_result_is_idempotent(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(make_message(id=ids.assistant_msg, role="assistant", content="final"))
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    first = await run.result()
    second = await run.result()
    assert first is second


async def test_non_live_message_yields_no_events(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    # A finished message streams only its terminal snapshot, no progress events.
    body = jsonl(make_message(id=ids.assistant_msg, role="assistant", content="cached"))
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    collected = [event async for event in run]

    assert collected == []
    assert (await run.result()).content == "cached"


# --------------------------------------------------------------------------- #
# Single-use semantics
# --------------------------------------------------------------------------- #
async def test_partial_iteration_then_result_raises(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("waiting_for_start", id="0-0"),
        make_event("result", id="1-0", data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    async for _ in run:
        break  # stop before the terminal message

    with pytest.raises(SDKError):
        await run.result()


# --------------------------------------------------------------------------- #
# Server shutdown -> StreamInterrupted
# --------------------------------------------------------------------------- #
async def test_partial_raises_stream_interrupted_on_iteration(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    partial = {
        "__server_is_shutting_down": True,
        "partial": make_message(
            id=ids.assistant_msg,
            role="assistant",
            content="half",
            status="running",
            live=True,
        ),
    }
    body = jsonl(make_event("llm", id="0-0", data={"description": "x", "model": "y"}), partial)
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    with pytest.raises(StreamInterrupted) as exc:
        async for _ in run:
            pass

    assert exc.value.partial.content == "half"
    assert exc.value.partial.status.value == "running"


async def test_partial_raises_stream_interrupted_via_text(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    partial = {
        "__server_is_shutting_down": True,
        "partial": make_message(
            id=ids.assistant_msg, role="assistant", content="half", status="running"
        ),
    }
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=jsonl(partial))
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    with pytest.raises(StreamInterrupted):
        await run.text()


# --------------------------------------------------------------------------- #
# Transport / primitive behavior
# --------------------------------------------------------------------------- #
async def test_stream_http_error_raises_on_iteration(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(404, json={"detail": "no such message"})
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    with pytest.raises(NotFoundError):
        async for _ in run:
            pass


def test_bare_stream_primitive_has_no_thread(
    client: AsyncCominty, ids: SimpleNamespace
) -> None:
    run = client.chat.stream(UUID(ids.assistant_msg))
    assert run.thread is None
    assert run.message_id == UUID(ids.assistant_msg)


async def test_context_manager_closes_cleanly(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(make_message(id=ids.assistant_msg, role="assistant", content="final"))
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    async with client.chat.stream(UUID(ids.assistant_msg)) as run:
        events_seen = [e async for e in run]
    assert events_seen == []


# --------------------------------------------------------------------------- #
# Integration: start() -> stream the returned handle
# --------------------------------------------------------------------------- #
async def test_start_then_stream_end_to_end(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_thread: MakeThread,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))
    body = jsonl(
        make_event("result", id="1-0", data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = await client.chat.start(agent_id="agt_1", message="hi")
    names = [e.name async for e in run]

    assert run.thread.id is not None  # StartedChat: thread present
    assert names == ["result"]
    assert (await run.result()).content == "final"


# --------------------------------------------------------------------------- #
# Agent clarifying questions
# --------------------------------------------------------------------------- #
async def test_questions_surfaced_from_terminal_message(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    terminal = {
        **make_message(id=ids.assistant_msg, role="assistant", content=""),
        "questions": [
            {"prompt": "Which environment?", "options": ["prod", "staging"]},
        ],
    }
    body = jsonl(make_event("result", id="1-0", data=_RESULT_DATA), terminal)
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    questions = await run.questions()

    assert [q.prompt for q in questions] == ["Which environment?"]
    assert questions[0].options == ["prod", "staging"]


async def test_questions_empty_when_none(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    jsonl: Jsonl,
    make_event: MakeEvent,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    body = jsonl(
        make_event("result", id="1-0", data=_RESULT_DATA),
        make_message(id=ids.assistant_msg, role="assistant", content="final"),
    )
    mock_api.get(_stream_path(ids.assistant_msg)).mock(
        return_value=httpx.Response(200, text=body)
    )

    run = client.chat.stream(UUID(ids.assistant_msg))
    assert await run.questions() == []
