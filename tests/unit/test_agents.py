"""Exhaustive unit tests for ``client.agents``.

Covers happy paths for every method, request shaping (token, no user_id,
partial bodies), client-side validation (must never hit the network), HTTP
error mapping, and response tolerance — the scenarios a human QA pass would
walk through against a mocked API.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from cominty_sdk import (
    Agent,
    APIError,
    AsyncCominty,
    AuthError,
    CustomAgent,
    CustomAgentSummary,
    InvalidParams,
    LLMModelSummary,
    NotFoundError,
    PermissionError,
)

AGENT_ID = "agt_custom_1"
MODEL_ID = "mdl_1"
USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"


def _model_summary(model_id: str = MODEL_ID, name: str = "GPT") -> dict[str, Any]:
    return {"id": model_id, "name": name}


def _agent_summary(
    *,
    agent_id: str = AGENT_ID,
    name: str = "My agent",
    scope: str = "private",
    managed: bool = False,
) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": name,
        "description": "A helper",
        "execution_options": None,
        "managed": managed,
        "scope": scope,
        "owner": USER_ID,
    }


def _agent_detail(
    *,
    name: str | None = None,
    instructions: str = "Be helpful",
    scope: str = "private",
    models: list[dict[str, Any]] | None = None,
    execution_options: dict[str, Any] | None = None,
    allow_execution_options_override: bool = False,
) -> dict[str, Any]:
    return {
        **_agent_summary(name=name or "My agent", scope=scope),
        "instructions": instructions,
        "allow_execution_options_override": allow_execution_options_override,
        "execution_options": execution_options,
        "models": models if models is not None else [_model_summary()],
    }


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
async def test_list_returns_summaries(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/agents").mock(
        return_value=httpx.Response(
            200,
            json=[
                _agent_summary(name="one", scope="organization"),
                _agent_summary(name="two"),
            ],
        )
    )

    agents = await client.agents.list()

    assert [a.name for a in agents] == ["one", "two"]
    assert agents[0].scope == "organization"
    assert all(isinstance(a, CustomAgentSummary) for a in agents)
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == "/agents"
    assert "user_id" not in route.calls.last.request.url.params
    assert route.calls.last.request.headers["x-cominty-token"] == "test-token"


async def test_list_empty(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    mock_api.get("/agents").mock(return_value=httpx.Response(200, json=[]))
    assert await client.agents.list() == []


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
async def test_create_sends_full_body_and_returns_detail(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/agents").mock(
        return_value=httpx.Response(
            200,
            json=_agent_detail(
                scope="organization",
                execution_options={"temperature": 0.2},
                allow_execution_options_override=True,
            ),
        )
    )

    agent = await client.agents.create(
        name="My agent",
        description="A helper",
        instructions="Be helpful",
        scope="organization",
        execution_options={"temperature": 0.2},
        allow_execution_options_override=True,
        model_ids=[MODEL_ID, "mdl_2"],
    )

    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == "/agents"
    assert json.loads(request.content) == {
        "name": "My agent",
        "description": "A helper",
        "instructions": "Be helpful",
        "scope": "organization",
        "execution_options": {"temperature": 0.2},
        "allow_execution_options_override": True,
        "model_ids": [MODEL_ID, "mdl_2"],
    }
    assert "user_id" not in request.url.params
    assert request.headers["x-cominty-token"] == "test-token"
    assert isinstance(agent, CustomAgent)
    assert agent.id == AGENT_ID
    assert agent.scope == "organization"
    assert agent.allow_execution_options_override is True
    assert agent.execution_options == {"temperature": 0.2}
    assert agent.models[0].id == MODEL_ID


async def test_create_omits_none_optional_fields(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/agents").mock(return_value=httpx.Response(200, json=_agent_detail()))

    await client.agents.create(name="Minimal")

    assert json.loads(route.calls.last.request.content) == {
        "name": "Minimal",
        "scope": "private",
        "allow_execution_options_override": False,
    }


async def test_create_empty_model_ids_raises_before_request(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/agents")

    with pytest.raises(InvalidParams) as exc:
        await client.agents.create(name="Bad", model_ids=[])

    assert not route.called
    assert len(mock_api.calls) == 0
    assert any(e["param"] == "model_ids" for e in exc.value.errors)


async def test_create_invalid_scope_raises_before_request(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/agents")

    with pytest.raises(InvalidParams) as exc:
        await client.agents.create(
            name="Bad",
            scope="team",  # type: ignore[arg-type]
        )

    assert not route.called
    assert any(e["param"] == "scope" for e in exc.value.errors)


# --------------------------------------------------------------------------- #
# get
# --------------------------------------------------------------------------- #
async def test_get_returns_detail(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.get(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(200, json=_agent_detail())
    )

    agent = await client.agents.get(AGENT_ID)

    assert isinstance(agent, CustomAgent)
    assert agent.instructions == "Be helpful"
    assert agent.owner == USER_ID
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == f"/agents/{AGENT_ID}"


async def test_get_ignores_unknown_response_fields(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(
            200, json={**_agent_detail(), "future_field": "ok", "models": []}
        )
    )

    agent = await client.agents.get(AGENT_ID)

    assert agent.models == []
    assert not hasattr(agent, "future_field")


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
async def test_update_sends_patch_with_only_provided_fields(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.patch(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(200, json=_agent_detail(name="Renamed", instructions="New"))
    )

    agent = await client.agents.update(AGENT_ID, name="Renamed")

    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == f"/agents/{AGENT_ID}"
    assert json.loads(request.content) == {"name": "Renamed"}
    assert agent.name == "Renamed"


async def test_update_multiple_fields_and_execution_options(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.patch(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(
            200,
            json=_agent_detail(
                instructions="Revise",
                execution_options={"max_tokens": 100},
                allow_execution_options_override=True,
            ),
        )
    )

    await client.agents.update(
        AGENT_ID,
        description="Updated",
        instructions="Revise",
        execution_options={"max_tokens": 100},
        allow_execution_options_override=True,
    )

    assert json.loads(route.calls.last.request.content) == {
        "description": "Updated",
        "instructions": "Revise",
        "execution_options": {"max_tokens": 100},
        "allow_execution_options_override": True,
    }


async def test_update_bool_false_is_sent(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.patch(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(200, json=_agent_detail())
    )

    await client.agents.update(AGENT_ID, allow_execution_options_override=False)

    assert json.loads(route.calls.last.request.content) == {
        "allow_execution_options_override": False
    }


async def test_update_empty_body_when_nothing_passed(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.patch(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(200, json=_agent_detail())
    )

    await client.agents.update(AGENT_ID)

    assert json.loads(route.calls.last.request.content) == {}


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
async def test_delete_sends_delete(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.delete(f"/agents/{AGENT_ID}").mock(return_value=httpx.Response(204))

    result = await client.agents.delete(AGENT_ID)

    assert result is None
    assert route.calls.last.request.method == "DELETE"
    assert route.calls.last.request.url.path == f"/agents/{AGENT_ID}"


# --------------------------------------------------------------------------- #
# list_models / set_models
# --------------------------------------------------------------------------- #
async def test_list_models(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/agents/models").mock(
        return_value=httpx.Response(200, json=[_model_summary(), _model_summary("mdl_2", "Claude")])
    )

    models = await client.agents.list_models()

    assert [m.id for m in models] == [MODEL_ID, "mdl_2"]
    assert all(isinstance(m, LLMModelSummary) for m in models)
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == "/agents/models"


async def test_set_models(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.put(f"/agents/{AGENT_ID}/models").mock(
        return_value=httpx.Response(
            200,
            json=_agent_detail(models=[_model_summary("mdl_2", "Claude")]),
        )
    )

    agent = await client.agents.set_models(AGENT_ID, model_ids=["mdl_2"])

    request = route.calls.last.request
    assert request.method == "PUT"
    assert request.url.path == f"/agents/{AGENT_ID}/models"
    assert json.loads(request.content) == {"model_ids": ["mdl_2"]}
    assert agent.models[0].id == "mdl_2"


async def test_set_models_empty_raises_before_request(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put(f"/agents/{AGENT_ID}/models")

    with pytest.raises(InvalidParams) as exc:
        await client.agents.set_models(AGENT_ID, model_ids=[])

    assert not route.called
    assert any(e["param"] == "model_ids" for e in exc.value.errors)


# --------------------------------------------------------------------------- #
# End-to-end lifecycle (mocked) — create → get → update → set_models → delete
# --------------------------------------------------------------------------- #
async def test_lifecycle_create_get_update_set_models_delete(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.post("/agents").mock(return_value=httpx.Response(200, json=_agent_detail()))
    mock_api.get(f"/agents/{AGENT_ID}").mock(return_value=httpx.Response(200, json=_agent_detail()))
    mock_api.patch(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(200, json=_agent_detail(name="Renamed"))
    )
    mock_api.put(f"/agents/{AGENT_ID}/models").mock(
        return_value=httpx.Response(200, json=_agent_detail(models=[_model_summary("mdl_2")]))
    )
    mock_api.delete(f"/agents/{AGENT_ID}").mock(return_value=httpx.Response(204))

    created = await client.agents.create(name="My agent", model_ids=[MODEL_ID])
    fetched = await client.agents.get(created.id)
    updated = await client.agents.update(fetched.id, name="Renamed")
    with_models = await client.agents.set_models(updated.id, model_ids=["mdl_2"])
    await client.agents.delete(with_models.id)

    assert created.id == AGENT_ID
    assert fetched.instructions == "Be helpful"
    assert updated.name == "Renamed"
    assert with_models.models[0].id == "mdl_2"
    assert len(mock_api.calls) == 5


# --------------------------------------------------------------------------- #
# HTTP error mapping (same transport path as chat)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthError),
        (403, PermissionError),
        (404, NotFoundError),
    ],
)
async def test_http_errors_map_to_typed_exceptions(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    status: int,
    expected: type[Exception],
) -> None:
    mock_api.get(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(status, json={"detail": "Nope"})
    )

    with pytest.raises(expected) as exc:
        await client.agents.get(AGENT_ID)

    err = exc.value
    assert isinstance(err, (AuthError, PermissionError, NotFoundError))
    assert err.status_code == status
    assert err.detail == "Nope"


async def test_create_forbidden_maps_api_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.post("/agents").mock(
        return_value=httpx.Response(400, json={"detail": "model_ids is not allowed for members"})
    )

    with pytest.raises(APIError) as exc:
        await client.agents.create(name="X", model_ids=[MODEL_ID])

    assert exc.value.status_code == 400
    assert "model_ids" in str(exc.value)


# --------------------------------------------------------------------------- #
# Naming: chat Agent vs CustomAgent stay distinct
# --------------------------------------------------------------------------- #
def test_chat_agent_and_custom_agent_are_distinct_types() -> None:
    chat_agent = Agent(id="agt_1", name="Support")
    custom = CustomAgent.model_validate(_agent_detail())

    assert type(chat_agent) is not type(custom)
    assert chat_agent.id == "agt_1"
    assert custom.models[0].id == MODEL_ID
