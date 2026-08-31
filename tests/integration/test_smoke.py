"""Opt-in smoke tests against the real API.

Run with credentials in the environment:

    COMINTY_API_KEY=... COMINTY_USER_ID=user_... COMINTY_AGENT_ID=... \\
        uv run pytest -m integration
"""

from __future__ import annotations

import os

import pytest

from cominty_sdk import AsyncCominty

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
        run = await client.chat.start(
            agent_id=agent_id, message="Reply with exactly: pong"
        )
        reply = await run.result()
        assert reply.content
        assert str(reply.thread_id) == str(run.thread.id)


@pytest.mark.asyncio
async def test_cancel_message(creds: tuple[str, str], agent_id: str) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        run = await client.chat.start(agent_id=agent_id, message="Write a long story.")
        cancelled = await client.chat.cancel(run.message_id)
        assert cancelled.status.value == "cancelled"


@pytest.mark.asyncio
async def test_export_message(creds: tuple[str, str], agent_id: str) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        run = await client.chat.start(
            agent_id=agent_id, message="Reply with exactly: pong"
        )
        reply = await run.result()
        exported = await client.chat.export(reply.id, format="pdf")
        assert isinstance(exported, bytes)
        assert len(exported) > 0


@pytest.mark.asyncio
async def test_upload_and_download_file(creds: tuple[str, str]) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        content = b"hello from the integration test"
        uploaded = await client.chat.upload_file(
            content, filename="smoke.txt", mimetype="text/plain"
        )
        assert uploaded.name == "smoke.txt"

        downloaded = await client.chat.download_file(uploaded.id)
        assert downloaded == content
