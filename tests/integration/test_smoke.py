from __future__ import annotations

import os

import pytest

from cominty_sdk import AsyncCominty, HumanMessage

pytestmark = pytest.mark.integration


@pytest.fixture
def api_key() -> str:
    key = os.environ.get("COMINTY_API_KEY")
    if not key:
        pytest.skip("COMINTY_API_KEY not set")
    return key


@pytest.fixture
def agent_id() -> str:
    agent = os.environ.get("COMINTY_AGENT_ID")
    if not agent:
        pytest.skip("COMINTY_AGENT_ID not set")
    return agent


@pytest.mark.asyncio
async def test_list_threads(api_key: str) -> None:
    async with AsyncCominty(api_key=api_key) as client:
        threads = await client.threads.list(limit=5)
        assert isinstance(threads, list)


@pytest.mark.asyncio
async def test_start_and_wait_smoke(api_key: str, agent_id: str) -> None:
    async with AsyncCominty(api_key=api_key, agent_id=agent_id) as client:
        thread, message = await client.chat.start_and_wait(
            HumanMessage(content="Reply with exactly: pong"),
            timeout=180.0,
        )
        assert thread.id
        assert message.is_terminal()
