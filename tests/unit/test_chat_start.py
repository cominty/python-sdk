from __future__ import annotations

import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx

from cominty_sdk import (
    ALL,
    Agent,
    AgentCapabilities,
    AsyncCominty,
    AuthError,
    ConflictError,
    InvalidParams,
    McpPolicy,
    MessageScope,
    NotFoundError,
    PermissionError,
    RateLimitError,
    SDKError,
    ServerError,
    StartedChat,
)

MakeThread = Callable[..., dict[str, Any]]
MakeMessage = Callable[..., dict[str, Any]]

# A well-formed Cominty (Clerk) user id: must match ^user_[A-Za-z0-9]{20,}$,
# which client-side validation enforces before any request goes out.
USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"

# Extra UUIDs for the multi-assistant ordering test.
_USER_2 = "44444444-4444-4444-4444-444444444444"
_ASSISTANT_1 = "55555555-5555-5555-5555-555555555555"
_ASSISTANT_2 = "66666666-6666-6666-6666-666666666666"


# --------------------------------------------------------------------------- #
# Happy path: the returned handle
# --------------------------------------------------------------------------- #
async def test_returns_started_chat_with_thread_and_reply(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    make_thread: MakeThread,
    ids: SimpleNamespace,
) -> None:
    mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    run = await client.chat.start(agent_id="agt_1", message="hi")

    assert isinstance(run, StartedChat)
    assert str(run.thread.id) == ids.thread
    assert str(run.message_id) == ids.assistant_msg  # the live assistant reply
    agent = run.thread.messages[-1].agent
    assert isinstance(agent, Agent)
    assert agent.name == "Support"


async def test_thread_is_non_optional_on_started_chat(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))
    run = await client.chat.start(agent_id="agt_1", message="hi")
    # StartedChat narrows thread to Thread (never None): accessible without a guard.
    assert run.thread.messages[0].role.value == "user"


# --------------------------------------------------------------------------- #
# Happy path: the request that goes out
# --------------------------------------------------------------------------- #
async def test_sends_post_with_token_and_minimal_body(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    route = mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    await client.chat.start(agent_id="agt_1", message="hi")

    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == "/chat"
    assert request.headers["x-cominty-token"] == "test-token"
    # exclude_none drops every optional that wasn't passed.
    assert json.loads(request.content) == {
        "message": {"content": "hi"},
        "options": {"agent_id": "agt_1", "user_id": USER_ID},
    }


async def test_includes_optional_fields_when_provided(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    route = mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    await client.chat.start(
        agent_id="agt_1",
        message="hi",
        name="My chat",
        file_ids=["f1", "f2"],
    )

    body = json.loads(route.calls.last.request.content)
    assert body["name"] == "My chat"
    assert body["message"]["file_ids"] == ["f1", "f2"]


async def test_start_does_not_open_the_stream(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    await client.chat.start(agent_id="agt_1", message="hi")

    # start() only POSTs; the stream opens lazily on iteration, not here.
    assert len(mock_api.calls) == 1
    assert mock_api.calls.last.request.method == "POST"


async def test_includes_memory_namespace_when_provided(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    route = mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    await client.chat.start(agent_id="agt_1", message="hi", memory_namespace="support-bot")

    body = json.loads(route.calls.last.request.content)
    assert body["options"]["memory_namespace"] == "support-bot"


async def test_omits_memory_namespace_when_not_provided(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    route = mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    await client.chat.start(agent_id="agt_1", message="hi")

    assert "memory_namespace" not in json.loads(route.calls.last.request.content)["options"]


async def test_memory_namespace_too_long_raises_invalid_params(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/chat")

    with pytest.raises(InvalidParams):
        await client.chat.start(agent_id="agt_1", message="hi", memory_namespace="x" * 129)

    assert not route.called


async def test_uses_configured_base_url(make_thread: MakeThread) -> None:
    with respx.mock(base_url="https://sandbox.test", assert_all_called=False) as router:
        route = router.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))
        async with AsyncCominty(
            api_token="t", user_id=USER_ID, base_url="https://sandbox.test"
        ) as c:
            await c.chat.start(agent_id="a", message="hi")
        assert str(route.calls.last.request.url) == "https://sandbox.test/chat"


# --------------------------------------------------------------------------- #
# Client-side validation: must fail BEFORE any HTTP request
# --------------------------------------------------------------------------- #
async def test_content_too_long_raises(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/chat")

    with pytest.raises(InvalidParams) as exc:
        await client.chat.start(agent_id="a", message="x" * 30_001)

    assert not route.called
    assert any(e["param"] == "content" for e in exc.value.errors)


async def test_too_many_file_ids_raises(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/chat")

    with pytest.raises(InvalidParams) as exc:
        await client.chat.start(
            agent_id="a",
            message="hi",
            file_ids=[f"f{i}" for i in range(6)],
        )

    assert not route.called
    assert any(e["param"] == "file_ids" for e in exc.value.errors)


async def test_multiple_validation_errors_collected(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams) as exc:
        await client.chat.start(
            agent_id="a",
            message="x" * 30_001,
            file_ids=[1],  # type: ignore[list-item]
        )

    params = {e["param"] for e in exc.value.errors}
    assert {"content", "file_ids[0]"} <= params
    assert len(mock_api.calls) == 0


async def test_invalid_params_message_is_clean(client: AsyncCominty) -> None:
    with pytest.raises(InvalidParams) as exc:
        await client.chat.start(agent_id="a", message="x" * 30_001)

    text = str(exc.value)
    assert text.startswith("Invalid parameters for chat.start:")
    assert "content" in text
    assert "at most 30000" in text  # the constraint is shown
    assert "pydantic" not in text.lower()  # no leaked library internals


# --------------------------------------------------------------------------- #
# HTTP error mapping
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthError),
        (403, PermissionError),
        (404, NotFoundError),
        (409, ConflictError),
        (500, ServerError),
        (503, ServerError),
    ],
)
async def test_http_errors_map_to_exceptions(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    status: int,
    expected: type[Exception],
) -> None:
    mock_api.post("/chat").mock(return_value=httpx.Response(status, json={"detail": "nope"}))

    with pytest.raises(expected):
        await client.chat.start(agent_id="a", message="hi")


# The API sends a short string detail. Concurrency is a transient cap; quota
# cases need an admin. The SDK turns the terse detail into an actionable message.
async def test_rate_limit_concurrency_message(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    # Exactly what the backend raises: HTTPException(429, "Too many concurrent requests").
    mock_api.post("/chat").mock(
        return_value=httpx.Response(429, json={"detail": "Too many concurrent requests"})
    )

    with pytest.raises(RateLimitError) as exc:
        await client.chat.start(agent_id="a", message="hi")

    err = exc.value
    assert err.status_code == 429
    assert err.scope == "concurrency"
    text = str(err)
    assert "concurrent" in text.lower()
    assert "Wait for an in-flight request" in text  # transient: retry guidance
    assert "admin" in text.lower()


async def test_rate_limit_organization_quota(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    # Real shape: {"quota_reached": "organization", "reset_at": "..."}.
    mock_api.post("/chat").mock(
        return_value=httpx.Response(
            429,
            json={
                "detail": {
                    "quota_reached": "organization",
                    "reset_at": "2026-06-30T00:00:00+00:00",
                }
            },
        )
    )

    with pytest.raises(RateLimitError) as exc:
        await client.chat.start(agent_id="a", message="hi")

    err = exc.value
    assert err.scope == "organization"
    assert err.reset_at is not None
    text = str(err)
    assert "Organization rate limit reached" in text
    assert "organization's total request quota" in text  # explicit it's org-wide
    assert "Ask an organization admin to raise your plan's limit." in text
    assert "Quota resets at 2026-06-30T00:00:00+00:00" in text


async def test_rate_limit_user_quota(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    mock_api.post("/chat").mock(
        return_value=httpx.Response(
            429,
            json={
                "detail": {
                    "quota_reached": "user",
                    "reset_at": "2026-06-30T00:00:00+00:00",
                }
            },
        )
    )

    with pytest.raises(RateLimitError) as exc:
        await client.chat.start(agent_id="a", message="hi")

    err = exc.value
    assert err.scope == "user"
    text = str(err)
    assert "User rate limit reached" in text  # explicit it's the user, not the org
    assert "user request quota" in text
    assert "Organization rate limit" not in text


# --------------------------------------------------------------------------- #
# Locating the assistant reply
# --------------------------------------------------------------------------- #
async def test_thread_without_assistant_message_raises_sdk_error(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    make_thread: MakeThread,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    payload = make_thread(messages=[make_message(id=ids.user_msg, role="user", content="hi")])
    mock_api.post("/chat").mock(return_value=httpx.Response(200, json=payload))

    with pytest.raises(SDKError):
        await client.chat.start(agent_id="a", message="hi")


async def test_picks_last_assistant_message(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    make_thread: MakeThread,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    payload = make_thread(
        messages=[
            make_message(id=ids.user_msg, role="user", content="hi"),
            make_message(id=_ASSISTANT_1, role="assistant", content="first"),
            make_message(id=_USER_2, role="user", content="again"),
            make_message(id=_ASSISTANT_2, role="assistant", status="pending", live=True),
        ]
    )
    mock_api.post("/chat").mock(return_value=httpx.Response(200, json=payload))

    run = await client.chat.start(agent_id="a", message="hi")

    assert str(run.message_id) == _ASSISTANT_2


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
async def test_sends_thread_capabilities_and_message_scope(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    route = mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    await client.chat.start(
        agent_id="agt_1",
        message="hi",
        thread_capabilities=AgentCapabilities(
            web="never", mcp=McpPolicy(activation="always", connections=ALL)
        ),
        message_scope=MessageScope(image_generation=True),
    )

    body = json.loads(route.calls.last.request.content)
    assert body["options"]["capabilities"] == {
        "web": {"activation": "never"},
        "mcp": {"activation": "always", "connections": "*"},
    }
    assert body["message"]["capabilities"] == {"image_generation": {"enabled": True}}


async def test_omits_capabilities_by_default(
    client: AsyncCominty, mock_api: respx.MockRouter, make_thread: MakeThread
) -> None:
    route = mock_api.post("/chat").mock(return_value=httpx.Response(200, json=make_thread()))

    await client.chat.start(agent_id="agt_1", message="hi")

    body = json.loads(route.calls.last.request.content)
    assert "capabilities" not in body["options"]
    assert "capabilities" not in body["message"]
