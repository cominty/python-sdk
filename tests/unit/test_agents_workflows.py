"""Simulate full user journeys against a stateful fake ``/agents`` API.

These are not per-method unit checks — each test walks a realistic sequence
(discover models → create → list/get → optional chat.start → update →
set_models → delete) and asserts the SDK never raises unexpectedly, and that
documented failure modes surface as typed errors.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx

from cominty_sdk import (
    APIError,
    AsyncCominty,
    AuthError,
    CustomAgent,
    InvalidParams,
    NotFoundError,
    PermissionError,
    ServerError,
)

USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"
THREAD_ID = "11111111-1111-1111-1111-111111111111"
USER_MSG_ID = "22222222-2222-2222-2222-222222222222"
ASSISTANT_MSG_ID = "33333333-3333-3333-3333-333333333333"

_MODELS = [
    {"id": "mdl_gpt", "name": "GPT"},
    {"id": "mdl_claude", "name": "Claude"},
]


class FakeAgentsBackend:
    """In-memory stand-in for ENG-1171 ``/agents`` routes."""

    def __init__(self) -> None:
        self.agents: dict[str, dict[str, Any]] = {}
        self.auth_ok = True

    def _unauthorized(self) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid token"})

    def _check_auth(self) -> httpx.Response | None:
        if not self.auth_ok:
            return self._unauthorized()
        return None

    def list_models(self, request: httpx.Request) -> httpx.Response:
        if blocked := self._check_auth():
            return blocked
        return httpx.Response(200, json=list(_MODELS))

    def list_agents(self, request: httpx.Request) -> httpx.Response:
        if blocked := self._check_auth():
            return blocked
        summaries = [
            {
                "id": a["id"],
                "name": a["name"],
                "description": a["description"],
                "execution_options": a["execution_options"],
                "managed": a["managed"],
                "scope": a["scope"],
                "owner": a["owner"],
            }
            for a in self.agents.values()
        ]
        return httpx.Response(200, json=summaries)

    def create(self, request: httpx.Request) -> httpx.Response:
        if blocked := self._check_auth():
            return blocked
        body = json.loads(request.content)
        model_ids = body.get("model_ids")
        if model_ids is not None and len(model_ids) == 0:
            return httpx.Response(422, json={"detail": "model_ids too short"})
        if body.get("scope") == "organization" and body.get("_member"):
            return httpx.Response(400, json={"detail": "Unauthorized scope"})

        agent_id = f"agt_{uuid4().hex[:8]}"
        models = [_m for _m in _MODELS if _m["id"] in (model_ids or [])]
        agent = {
            "id": agent_id,
            "name": body["name"],
            "description": body.get("description"),
            "instructions": body.get("instructions"),
            "execution_options": body.get("execution_options"),
            "allow_execution_options_override": body.get("allow_execution_options_override", False),
            "managed": False,
            "scope": body.get("scope", "private"),
            "owner": USER_ID,
            "models": models,
        }
        self.agents[agent_id] = agent
        return httpx.Response(200, json=agent)

    def get(self, request: httpx.Request) -> httpx.Response:
        if blocked := self._check_auth():
            return blocked
        agent_id = request.url.path.rsplit("/", 1)[-1]
        agent = self.agents.get(agent_id)
        if agent is None:
            return httpx.Response(404, json={"detail": "Not Found"})
        return httpx.Response(200, json=agent)

    def update(self, request: httpx.Request) -> httpx.Response:
        if blocked := self._check_auth():
            return blocked
        agent_id = request.url.path.rsplit("/", 1)[-1]
        agent = self.agents.get(agent_id)
        if agent is None:
            return httpx.Response(404, json={"detail": "Not Found"})
        body = json.loads(request.content or b"{}")
        if "model_ids" in body:
            return httpx.Response(422, json={"detail": "extra fields not permitted"})
        for key, value in body.items():
            agent[key] = value
        return httpx.Response(200, json=agent)

    def set_models(self, request: httpx.Request) -> httpx.Response:
        if blocked := self._check_auth():
            return blocked
        # path: /agents/{id}/models
        parts = request.url.path.strip("/").split("/")
        agent_id = parts[1]
        agent = self.agents.get(agent_id)
        if agent is None:
            return httpx.Response(404, json={"detail": "Not Found"})
        body = json.loads(request.content)
        model_ids = body["model_ids"]
        unknown = [mid for mid in model_ids if mid not in {m["id"] for m in _MODELS}]
        if unknown:
            return httpx.Response(404, json={"detail": "Bad model_ids"})
        agent["models"] = [m for m in _MODELS if m["id"] in model_ids]
        # preserve order from request
        by_id = {m["id"]: m for m in _MODELS}
        agent["models"] = [by_id[mid] for mid in model_ids]
        return httpx.Response(200, json=agent)

    def delete(self, request: httpx.Request) -> httpx.Response:
        if blocked := self._check_auth():
            return blocked
        agent_id = request.url.path.rsplit("/", 1)[-1]
        if agent_id not in self.agents:
            return httpx.Response(404, json={"detail": "Not Found"})
        del self.agents[agent_id]
        return httpx.Response(204)


def _mount(mock_api: respx.MockRouter, backend: FakeAgentsBackend) -> None:
    mock_api.get("/agents/models").mock(side_effect=backend.list_models)
    mock_api.get("/agents").mock(side_effect=backend.list_agents)
    mock_api.post("/agents").mock(side_effect=backend.create)
    mock_api.get(url__regex=r"/agents/[^/]+$").mock(side_effect=backend.get)
    mock_api.patch(url__regex=r"/agents/[^/]+$").mock(side_effect=backend.update)
    mock_api.put(url__regex=r"/agents/[^/]+/models$").mock(side_effect=backend.set_models)
    mock_api.delete(url__regex=r"/agents/[^/]+$").mock(side_effect=backend.delete)


def _thread_for_agent(agent_id: str, agent_name: str) -> dict[str, Any]:
    return {
        "id": THREAD_ID,
        "name": "Workflow thread",
        "created_at": "2026-06-28T10:00:00Z",
        "live": True,
        "agent": {"id": agent_id, "name": agent_name},
        "starred": False,
        "project_id": None,
        "messages": [
            {
                "id": USER_MSG_ID,
                "thread_id": THREAD_ID,
                "role": "user",
                "content": "hi",
                "questions": None,
                "live": False,
                "status": "success",
                "events": None,
                "structured_output": None,
                "files": [],
            },
            {
                "id": ASSISTANT_MSG_ID,
                "thread_id": THREAD_ID,
                "role": "assistant",
                "content": "",
                "questions": None,
                "live": True,
                "status": "pending",
                "events": None,
                "structured_output": None,
                "files": [],
            },
        ],
    }


# --------------------------------------------------------------------------- #
# Happy-path workflows
# --------------------------------------------------------------------------- #
async def test_workflow_org_admin_full_lifecycle(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    """Discover models → create org agent → list/get → update → set_models → delete."""
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    models = await client.agents.list_models()
    assert [m.id for m in models] == ["mdl_gpt", "mdl_claude"]

    agent = await client.agents.create(
        name="Researcher",
        description="Org research",
        instructions="Cite sources.",
        scope="organization",
        execution_options={"temperature": 0.1},
        allow_execution_options_override=True,
        model_ids=[models[0].id],
    )
    assert isinstance(agent, CustomAgent)
    assert agent.scope == "organization"
    assert agent.models[0].id == "mdl_gpt"

    listed = await client.agents.list()
    assert len(listed) == 1
    assert listed[0].id == agent.id

    fetched = await client.agents.get(agent.id)
    assert fetched.instructions == "Cite sources."
    assert fetched.owner == USER_ID

    updated = await client.agents.update(
        agent.id,
        description="Updated blurb",
        instructions="Cite sources. Be brief.",
    )
    assert updated.description == "Updated blurb"
    assert updated.instructions == "Cite sources. Be brief."
    # untouched fields survive
    assert updated.scope == "organization"
    assert updated.models[0].id == "mdl_gpt"

    reassigned = await client.agents.set_models(agent.id, model_ids=["mdl_claude", "mdl_gpt"])
    assert [m.id for m in reassigned.models] == ["mdl_claude", "mdl_gpt"]

    await client.agents.delete(agent.id)
    assert backend.agents == {}

    with pytest.raises(NotFoundError):
        await client.agents.get(agent.id)


async def test_workflow_minimal_private_then_chat(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    """Create private agent with defaults → chat.start with its id → delete."""
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    agent = await client.agents.create(name="Scratch")
    assert agent.scope == "private"
    assert agent.models == []
    assert agent.allow_execution_options_override is False

    mock_api.post("/chat").mock(
        return_value=httpx.Response(200, json=_thread_for_agent(agent.id, agent.name))
    )

    run = await client.chat.start(agent_id=agent.id, message="hello")
    assert run.thread.agent.id == agent.id
    assert run.thread.agent.name == "Scratch"

    await client.agents.delete(agent.id)
    with pytest.raises(NotFoundError):
        await client.agents.get(agent.id)


async def test_workflow_create_without_models_then_attach(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    agent = await client.agents.create(name="Later models")
    assert agent.models == []

    with_models = await client.agents.set_models(agent.id, model_ids=["mdl_gpt"])
    assert [m.id for m in with_models.models] == ["mdl_gpt"]

    again = await client.agents.get(agent.id)
    assert again.models[0].id == "mdl_gpt"

    await client.agents.delete(agent.id)


async def test_workflow_two_agents_list_and_selective_delete(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    a = await client.agents.create(name="Alpha", model_ids=["mdl_gpt"])
    b = await client.agents.create(name="Beta", scope="organization", model_ids=["mdl_claude"])

    names = {x.name for x in await client.agents.list()}
    assert names == {"Alpha", "Beta"}

    await client.agents.delete(a.id)
    remaining = await client.agents.list()
    assert len(remaining) == 1
    assert remaining[0].id == b.id

    await client.agents.delete(b.id)
    assert await client.agents.list() == []


async def test_workflow_partial_updates_accumulate(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    agent = await client.agents.create(
        name="Mutable",
        instructions="v1",
        execution_options={"temperature": 0.5},
    )

    await client.agents.update(agent.id, name="Mutable v2")
    mid = await client.agents.get(agent.id)
    assert mid.name == "Mutable v2"
    assert mid.instructions == "v1"

    await client.agents.update(
        agent.id,
        instructions="v2",
        allow_execution_options_override=True,
    )
    final = await client.agents.get(agent.id)
    assert final.name == "Mutable v2"
    assert final.instructions == "v2"
    assert final.allow_execution_options_override is True
    assert final.execution_options == {"temperature": 0.5}

    await client.agents.delete(agent.id)


# --------------------------------------------------------------------------- #
# Failure workflows — typed errors, no silent success
# --------------------------------------------------------------------------- #
async def test_workflow_client_validation_never_hits_network(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)
    calls_before = len(mock_api.calls)

    with pytest.raises(InvalidParams):
        await client.agents.create(name="Bad", model_ids=[])
    with pytest.raises(InvalidParams):
        await client.agents.create(
            name="Bad",
            scope="team",  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidParams):
        await client.agents.set_models("agt_x", model_ids=[])

    assert len(mock_api.calls) == calls_before
    assert backend.agents == {}


async def test_workflow_missing_agent_errors(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)
    missing = "agt_does_not_exist"

    with pytest.raises(NotFoundError):
        await client.agents.get(missing)
    with pytest.raises(NotFoundError):
        await client.agents.update(missing, name="Nope")
    with pytest.raises(NotFoundError):
        await client.agents.set_models(missing, model_ids=["mdl_gpt"])
    with pytest.raises(NotFoundError):
        await client.agents.delete(missing)


async def test_workflow_delete_twice_second_raises(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    agent = await client.agents.create(name="Once")
    await client.agents.delete(agent.id)
    with pytest.raises(NotFoundError):
        await client.agents.delete(agent.id)


async def test_workflow_bad_model_ids_on_set_models(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    agent = await client.agents.create(name="Models")
    with pytest.raises(NotFoundError) as exc:
        await client.agents.set_models(agent.id, model_ids=["mdl_unknown"])
    assert exc.value.detail == "Bad model_ids"

    # store unchanged
    assert (await client.agents.get(agent.id)).models == []
    await client.agents.delete(agent.id)


async def test_workflow_auth_failure_mid_journey(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    agent = await client.agents.create(name="Alive")
    backend.auth_ok = False

    with pytest.raises(AuthError):
        await client.agents.list()
    with pytest.raises(AuthError):
        await client.agents.get(agent.id)
    with pytest.raises(AuthError):
        await client.agents.update(agent.id, name="X")
    with pytest.raises(AuthError):
        await client.agents.delete(agent.id)

    backend.auth_ok = True
    still = await client.agents.get(agent.id)
    assert still.name == "Alive"
    await client.agents.delete(agent.id)


async def test_workflow_permission_and_server_errors(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    """When the API rejects a call, the SDK surfaces typed errors (no crash)."""
    mock_api.get("/agents").mock(return_value=httpx.Response(403, json={"detail": "Forbidden"}))
    with pytest.raises(PermissionError):
        await client.agents.list()

    mock_api.post("/agents").mock(
        return_value=httpx.Response(400, json={"detail": "model_ids is not allowed for members"})
    )
    with pytest.raises(APIError) as exc:
        await client.agents.create(name="Member", model_ids=["mdl_gpt"])
    assert exc.value.status_code == 400

    mock_api.get("/agents/models").mock(
        return_value=httpx.Response(503, json={"detail": "Unavailable"})
    )
    with pytest.raises(ServerError):
        await client.agents.list_models()


async def test_workflow_recover_after_failed_update(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    """A failed update must not corrupt subsequent successful calls."""
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    agent = await client.agents.create(name="Stable", instructions="keep")

    # Force next PATCH to 500 via a one-shot override
    call_count = {"n": 0}

    def flaky_update(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(500, json={"detail": "boom"})
        return backend.update(request)

    mock_api.patch(url__regex=r"/agents/[^/]+$").mock(side_effect=flaky_update)

    with pytest.raises(ServerError):
        await client.agents.update(agent.id, name="Should fail")

    ok = await client.agents.update(agent.id, name="Recovered")
    assert ok.name == "Recovered"
    assert ok.instructions == "keep"
    await client.agents.delete(agent.id)


# --------------------------------------------------------------------------- #
# Guard: path routing (list_models vs get-by-id)
# --------------------------------------------------------------------------- #
async def test_workflow_list_models_not_confused_with_get(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    backend = FakeAgentsBackend()
    _mount(mock_api, backend)

    models = await client.agents.list_models()
    assert len(models) == 2

    # Creating an agent whose id looks nothing like "models"
    agent = await client.agents.create(name="Normal")
    assert not re.search(r"models", agent.id)
    fetched = await client.agents.get(agent.id)
    assert fetched.name == "Normal"
    await client.agents.delete(agent.id)
