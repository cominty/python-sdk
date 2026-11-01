from __future__ import annotations

import json
from typing import cast

import httpx
import pytest
import respx

from cominty_sdk import (
    AgentCapabilities,
    AgentOut,
    AgentSummaryOut,
    AsyncCominty,
    IndexedDocumentsCapability,
    InvalidParams,
    LLMModelSummaryOut,
    MemoryCapability,
    NotFoundError,
    WebCapability,
)

AGENT_ID = "agt_V1StGXR8_Z5jdHi6B"
OWNER = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"


def _summary(
    *, id: str = AGENT_ID, capabilities: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "id": id,
        "name": "Support",
        "description": "Answers support tickets",
        "capabilities": capabilities,
        "execution_options": None,
        "memory_namespace": None,
        "managed": False,
        "scope": "private",
        "owner": OWNER,
    }


def _agent(**overrides: object) -> dict[str, object]:
    return {
        **_summary(),
        "instructions": "Be brief.",
        "allow_execution_options_override": False,
        "models": [{"id": "mdl_1", "name": "claude-sonnet"}],
        **overrides,
    }


# --------------------------------------------------------------------------- #
# list / list_models / get
# --------------------------------------------------------------------------- #
async def test_list_returns_summaries(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/agents").mock(
        return_value=httpx.Response(200, json=[_summary(), _summary(id="agt_2")])
    )

    agents = await client.agents.list()

    assert [a.id for a in agents] == [AGENT_ID, "agt_2"]
    assert all(isinstance(a, AgentSummaryOut) for a in agents)
    assert agents[0].owner == OWNER
    assert route.calls.last.request.method == "GET"


async def test_list_parses_capabilities_and_drops_unknown_ones(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    wire = {
        "web": {"activation": "always"},
        "memory": {"activation": "always", "namespace": "support"},
        "teleportation": {"activation": "always"},
    }
    mock_api.get("/agents").mock(
        return_value=httpx.Response(200, json=[_summary(capabilities=wire)])
    )

    (agent,) = await client.agents.list()

    assert agent.capabilities == AgentCapabilities(
        web=WebCapability(activation="always"),
        memory=MemoryCapability(activation="always", namespace="support"),
    )


async def test_list_drops_a_capability_whose_shape_this_sdk_does_not_know(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    wire = {
        "web": {"activation": "never"},
        "mcp": {"activation": "always", "connections": ["linear"], "tool_filter": ["x"]},
        "skills": {"activation": "on_request"},
        "indexed_documents": {"activation": "always", "source_ids": [42]},
    }
    mock_api.get("/agents").mock(
        return_value=httpx.Response(200, json=[_summary(capabilities=wire)])
    )

    (agent,) = await client.agents.list()

    assert agent.capabilities == AgentCapabilities(
        web=WebCapability(activation="never"),
        indexed_documents=IndexedDocumentsCapability(activation="always", source_ids=[42]),
    )


async def test_list_models(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    mock_api.get("/agents/models").mock(
        return_value=httpx.Response(200, json=[{"id": "mdl_1", "name": "claude-sonnet"}])
    )

    models = await client.agents.list_models()

    assert models == [LLMModelSummaryOut(id="mdl_1", name="claude-sonnet")]


async def test_get_returns_the_full_agent(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    mock_api.get(f"/agents/{AGENT_ID}").mock(return_value=httpx.Response(200, json=_agent()))

    agent = await client.agents.get(AGENT_ID)

    assert isinstance(agent, AgentOut)
    assert agent.instructions == "Be brief."
    assert [m.id for m in agent.models] == ["mdl_1"]


async def test_get_unknown_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/agents/nope").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )

    with pytest.raises(NotFoundError):
        await client.agents.get("nope")


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
async def test_create_sends_only_the_given_fields_plus_defaults(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/agents").mock(return_value=httpx.Response(200, json=_agent()))

    agent = await client.agents.create(name="Support")

    assert isinstance(agent, AgentOut)
    assert json.loads(route.calls.last.request.content) == {
        "name": "Support",
        "scope": "private",
        "allow_execution_options_override": False,
    }


async def test_create_serializes_capabilities_and_models(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/agents").mock(return_value=httpx.Response(200, json=_agent()))

    await client.agents.create(
        name="Support",
        description="Answers tickets",
        instructions="Be brief.",
        scope="organization",
        capabilities=AgentCapabilities(
            web=WebCapability(activation="never"),
            memory=MemoryCapability(activation="always", namespace="support"),
        ),
        allow_execution_options_override=True,
        model_ids=["mdl_1", "mdl_2"],
    )

    assert json.loads(route.calls.last.request.content) == {
        "name": "Support",
        "description": "Answers tickets",
        "instructions": "Be brief.",
        "scope": "organization",
        "capabilities": {
            "web": {"activation": "never"},
            "memory": {"activation": "always", "namespace": "support"},
        },
        "allow_execution_options_override": True,
        "model_ids": ["mdl_1", "mdl_2"],
    }


@pytest.mark.parametrize(
    ("kwargs", "param"),
    [
        ({"name": ""}, "name"),
        ({"name": "x", "description": "d" * 501}, "description"),
        ({"name": "x", "instructions": "i" * 30_001}, "instructions"),
        ({"name": "x", "scope": "public"}, "scope"),
        ({"name": "x", "model_ids": []}, "model_ids"),
    ],
)
async def test_create_rejects_invalid_params_before_any_request(
    client: AsyncCominty, mock_api: respx.MockRouter, kwargs: dict[str, object], param: str
) -> None:
    with pytest.raises(InvalidParams) as caught:
        await client.agents.create(**cast("dict[str, str]", kwargs))

    assert [e["param"] for e in caught.value.errors] == [param]
    assert mock_api.calls.call_count == 0


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
async def test_update_sends_only_the_passed_fields(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(200, json=_agent())
    )

    agent = await client.agents.update(AGENT_ID, name="Renamed", instructions=None)

    assert isinstance(agent, AgentOut)
    assert json.loads(route.calls.last.request.content) == {
        "name": "Renamed",
        "instructions": None,
    }


async def test_update_clears_or_merges_capabilities(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(200, json=_agent())
    )

    await client.agents.update(AGENT_ID, capabilities=None)
    assert json.loads(route.calls[0].request.content) == {"capabilities": None}

    await client.agents.update(
        AGENT_ID,
        capabilities=AgentCapabilities(web=WebCapability(activation="on_request")),
        scope="organization",
        allow_execution_options_override=True,
        description="New",
    )
    assert json.loads(route.calls[1].request.content) == {
        "capabilities": {"web": {"activation": "on_request"}},
        "scope": "organization",
        "allow_execution_options_override": True,
        "description": "New",
    }


async def test_update_without_any_field_is_rejected(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams, match="at least one field"):
        await client.agents.update(AGENT_ID)

    assert mock_api.calls.call_count == 0


@pytest.mark.parametrize("field", ["name", "scope", "allow_execution_options_override"])
async def test_update_rejects_none_on_required_fields(
    client: AsyncCominty, mock_api: respx.MockRouter, field: str
) -> None:
    with pytest.raises(InvalidParams, match=f"{field} cannot be set to None"):
        await client.agents.update(AGENT_ID, **cast("dict[str, str]", {field: None}))

    assert mock_api.calls.call_count == 0


async def test_update_not_writable_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.put(f"/agents/{AGENT_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )

    with pytest.raises(NotFoundError):
        await client.agents.update(AGENT_ID, name="Renamed")


# --------------------------------------------------------------------------- #
# set_models / delete
# --------------------------------------------------------------------------- #
async def test_set_models_replaces_the_chain(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put(f"/agents/{AGENT_ID}/models").mock(
        return_value=httpx.Response(200, json=_agent())
    )

    agent = await client.agents.set_models(AGENT_ID, model_ids=["mdl_2", "mdl_1"])

    assert isinstance(agent, AgentOut)
    assert json.loads(route.calls.last.request.content) == {"model_ids": ["mdl_2", "mdl_1"]}


async def test_set_models_rejects_an_empty_list(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams) as caught:
        await client.agents.set_models(AGENT_ID, model_ids=[])

    assert [e["param"] for e in caught.value.errors] == ["model_ids"]
    assert mock_api.calls.call_count == 0


async def test_delete_sends_delete_and_returns_none(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.delete(f"/agents/{AGENT_ID}").mock(return_value=httpx.Response(204))

    assert await client.agents.delete(AGENT_ID) is None
    assert route.calls.last.request.method == "DELETE"


async def test_agent_id_is_url_encoded(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/agents/__cominty_agents%3A%3Aagent.chat").mock(
        return_value=httpx.Response(200, json=_agent(id="__cominty_agents::agent.chat"))
    )

    await client.agents.get("__cominty_agents::agent.chat")

    assert route.call_count == 1
