from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import SERVER_DEFAULT, AssistantRun, AsyncCominty, InvalidParams

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


async def test_sends_max_steps_in_options_when_provided(
    client: AsyncCominty, mock_api: respx.MockRouter, make_message: MakeMessage
) -> None:
    route = mock_api.post(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(
            200, json=make_message(id=ASSISTANT_MSG_ID, role="assistant", live=True)
        )
    )

    await client.chat.send(THREAD_ID, message="yes, continue", agent_id="agt_1", max_steps=10)

    assert json.loads(route.calls.last.request.content)["options"]["max_steps"] == 10


@pytest.mark.parametrize("explicit", [False, True])
async def test_omits_max_steps_for_the_server_default(
    client: AsyncCominty, mock_api: respx.MockRouter, make_message: MakeMessage, explicit: bool
) -> None:
    route = mock_api.post(f"/chat/{THREAD_ID}").mock(
        return_value=httpx.Response(
            200, json=make_message(id=ASSISTANT_MSG_ID, role="assistant", live=True)
        )
    )

    if explicit:
        await client.chat.send(THREAD_ID, message="hi", agent_id="agt_1", max_steps=SERVER_DEFAULT)
    else:
        await client.chat.send(THREAD_ID, message="hi", agent_id="agt_1")

    assert "max_steps" not in json.loads(route.calls.last.request.content)["options"]


@pytest.mark.parametrize("bad", [None, 0, -1, 2.5, True, "5"])
async def test_invalid_max_steps_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter, bad: object
) -> None:
    route = mock_api.post(f"/chat/{THREAD_ID}")

    with pytest.raises(InvalidParams) as exc:
        await client.chat.send(
            THREAD_ID,
            message="hi",
            agent_id="agt_1",
            max_steps=bad,  # type: ignore[arg-type]
        )

    assert exc.value.errors[0]["param"] == "max_steps"
    assert not route.called


async def test_validation_fires_before_request(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post(f"/chat/{THREAD_ID}")

    with pytest.raises(InvalidParams) as exc:
        await client.chat.send(THREAD_ID, message="hi", agent_id="a", disabled_tools=["bogus"])

    assert not route.called
    assert str(exc.value).startswith("Invalid parameters for chat.send:")
