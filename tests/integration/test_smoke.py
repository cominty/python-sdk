from __future__ import annotations

import os
from uuid import uuid4

import pytest

from cominty_sdk import AsyncCominty, ConflictError, NotFoundError

pytestmark = pytest.mark.integration


@pytest.fixture
def creds() -> tuple[str, str]:
    key = os.environ.get("COMINTY_API_KEY")
    user_id = os.environ.get("COMINTY_USER_ID")
    if not key or not user_id:
        pytest.skip("COMINTY_API_KEY and COMINTY_USER_ID must be set")
    return key, user_id


@pytest.fixture
def agent_id() -> str:
    agent = os.environ.get("COMINTY_AGENT_ID")
    if not agent:
        pytest.skip("COMINTY_AGENT_ID not set")
    return agent


@pytest.mark.asyncio
async def test_list_threads(creds: tuple[str, str]) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        threads = await client.threads.list(limit=5)
        assert isinstance(threads, list)


@pytest.mark.asyncio
async def test_start_and_get_reply(creds: tuple[str, str], agent_id: str) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        run = await client.chat.start(agent_id=agent_id, message="Reply with exactly: pong")
        reply = await run.result()
        assert reply.content
        assert str(reply.thread_id) == str(run.thread.id)


@pytest.mark.asyncio
async def test_memory_lifecycle(creds: tuple[str, str]) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        path = f"sdk-integration-tests/{uuid4()}.md"
        created = await client.memory.create(
            path=path, purpose="integration test", content="buy milk"
        )
        try:
            assert created.path == path
            assert created.content == "buy milk"

            summaries = await client.memory.list()
            assert any(f.path == path for f in summaries)

            fetched = await client.memory.get(path)
            assert fetched.content == "buy milk"

            updated = await client.memory.update(
                path, version=fetched.version, content="buy oat milk"
            )
            assert updated.content == "buy oat milk"

            with pytest.raises(ConflictError):
                await client.memory.update(path, version=fetched.version, content="stale write")
        finally:
            await client.memory.delete(path)

        with pytest.raises(NotFoundError):
            await client.memory.get(path)
