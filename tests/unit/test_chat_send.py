"""Unit tests for ``client.chat.send`` — the follow-up (continue-in-thread) call.

Covers: endpoint + body (user_id sourced from the client, not the caller), the
streamable handle it returns, and that client-side validation still fires before
any request.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import AssistantRun, AsyncCominty, InvalidParams

# Mirror the canonical ids in conftest (tests/ is not an importable package).
THREAD_ID = "11111111-1111-1111-1111-111111111111"
ASSISTANT_MSG_ID = "33333333-3333-3333-3333-333333333333"
USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"

MakeMessage = Callable[..., dict[str, Any]]


async def test_posts_to_thread_with_body(
    client: AsyncCominty, mock_api: respx.MockRouter, make_message: MakeMessage
) -> None:
    route = mock_api.post(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(
            200, json=make_message(id=ASSISTANT_MSG_ID, role="assistant", live=True)
        )
    )

    await client.chat.send(THREAD_ID, message="and again", agent_id="agt_1")

    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/chat/{THREAD_ID}"
    # user_id comes from the client; "name" is start-only so never sent here.
    assert json.loads(request.content) == {
        "message": {"content": "and again"},
        "options": {"agent_id": "agt_1", "user_id": USER_ID},
    }


async def test_returns_run_for_new_reply(
    client: AsyncCominty, mock_api: respx.MockRouter, make_message: MakeMessage
) -> None:
    # POST /chat/{id} returns the new assistant Message directly (not a Thread).
    mock_api.post(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(
            200, json=make_message(id=ASSISTANT_MSG_ID, role="assistant", live=True)
        )
    )

    run = await client.chat.send(THREAD_ID, message="hi", agent_id="agt_1")

    assert isinstance(run, AssistantRun)
    assert str(run.message_id) == ASSISTANT_MSG_ID  # the new assistant reply to stream


async def test_accepts_uuid_thread_id(
    client: AsyncCominty, mock_api: respx.MockRouter, make_message: MakeMessage
) -> None:
    route = mock_api.post(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(
            200, json=make_message(id=ASSISTANT_MSG_ID, role="assistant", live=True)
        )
    )

    await client.chat.send(UUID(THREAD_ID), message="hi", agent_id="agt_1")

    assert route.called


async def test_validation_fires_before_request(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post(f"/chat/{THREAD_ID}")

    with pytest.raises(InvalidParams) as exc:
        await client.chat.send(
            THREAD_ID, message="hi", agent_id="a", disabled_tools=["bogus"]
        )

    assert not route.called
    assert str(exc.value).startswith("Invalid parameters for chat.send:")
