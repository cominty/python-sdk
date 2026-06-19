from __future__ import annotations

import json

import httpx
import pytest
import respx

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.exceptions import NotFoundError
from cominty_sdk.models.agents import AgentMode
from cominty_sdk.resources.agents import AgentsResource

BASE = "https://api.test.cominty.com"


@pytest.fixture
def agents() -> AgentsResource:
    http = AsyncHTTPClient(base_url=BASE, api_key="test-key", max_retries=1, timeout=5.0)
    return AgentsResource(http)


@respx.mock
@pytest.mark.asyncio
async def test_create_agent(agents: AgentsResource) -> None:
    route = respx.post(f"{BASE}/agents").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "ag_1",
                "name": "My Agent",
                "mode": "hive",
                "description": "d",
                "instructions": None,
                "owner": "org_1",
            },
        )
    )
    out = await agents.create(name="My Agent", mode=AgentMode.HIVE, description="d")
    assert out.id == "ag_1"
    assert out.mode == AgentMode.HIVE
    assert out.owner == "org_1"
    # mode enum is serialized to its value; None fields are omitted
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "My Agent", "mode": "hive", "description": "d"}


@respx.mock
@pytest.mark.asyncio
async def test_update_agent_partial(agents: AgentsResource) -> None:
    route = respx.put(f"{BASE}/agents/ag_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "ag_1",
                "name": "Renamed",
                "mode": "lite",
                "description": None,
                "instructions": None,
                "owner": "org_1",
            },
        )
    )
    out = await agents.update("ag_1", name="Renamed", mode="lite")
    assert out.name == "Renamed"
    assert out.mode == AgentMode.LITE
    # only provided fields are sent
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "Renamed", "mode": "lite"}


@respx.mock
@pytest.mark.asyncio
async def test_update_agent_not_found_surfaces(agents: AgentsResource) -> None:
    respx.put(f"{BASE}/agents/missing").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )
    with pytest.raises(NotFoundError):
        await agents.update("missing", name="x")
