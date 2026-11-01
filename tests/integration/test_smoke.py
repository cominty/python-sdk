from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest

from cominty_sdk import AsyncCominty, ConflictError, McpServerOut, MessageStatus, NotFoundError

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
async def test_cancel_message(creds: tuple[str, str], agent_id: str) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        run = await client.chat.start(agent_id=agent_id, message="Write a long story.")
        cancelled = await client.chat.cancel(run.message_id)
        assert cancelled.status == MessageStatus.cancelled


@pytest.mark.asyncio
async def test_export_message(creds: tuple[str, str], agent_id: str) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        run = await client.chat.start(agent_id=agent_id, message="Reply with exactly: pong")
        reply = await run.result()
        exported = await client.chat.export(reply.id, format="pdf")
        assert exported.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_upload_and_download_file(creds: tuple[str, str]) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        content = b"hello from the integration test"
        uploaded = await client.chat.upload_file(content, filename="smoke.txt")
        assert uploaded.name == "smoke.txt"
        assert await client.chat.download_file(uploaded.id) == content


@pytest.mark.asyncio
async def test_memory_lifecycle(creds: tuple[str, str]) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        namespace = f"sdk-integration-tests-{uuid4()}"
        path = "notes.md"
        created = await client.memory.create(
            path=path, namespace=namespace, purpose="integration test", content="buy milk"
        )
        try:
            assert created.path == path
            assert created.namespace == namespace
            assert created.content == "buy milk"

            summaries = await client.memory.list(namespace=namespace)
            assert any(f.path == path for f in summaries)

            assert namespace in await client.memory.list_namespaces()

            fetched = await client.memory.get(path, namespace=namespace)
            assert fetched.content == "buy milk"

            updated = await client.memory.update(
                path, namespace=namespace, version=fetched.version, content="buy oat milk"
            )
            assert updated.content == "buy oat milk"

            with pytest.raises(ConflictError):
                await client.memory.update(
                    path, namespace=namespace, version=fetched.version, content="stale write"
                )
        finally:
            await client.memory.delete(path, namespace=namespace)

        with pytest.raises(NotFoundError):
            await client.memory.get(path, namespace=namespace)


@pytest.mark.asyncio
async def test_agent_lifecycle(creds: tuple[str, str]) -> None:
    from cominty_sdk import AgentCapabilities, WebCapability

    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        models = await client.agents.list_models()
        assert models
        agent = await client.agents.create(
            name=f"sdk-integration-{uuid4()}",
            instructions="Reply with exactly: pong",
            capabilities=AgentCapabilities(web=WebCapability(activation="never")),
            model_ids=[models[0].id],
        )
        try:
            fetched = await client.agents.get(agent.id)
            assert fetched.id == agent.id
            assert fetched.capabilities is not None
            assert fetched.capabilities.web is not None
            assert fetched.capabilities.web.activation == "never"
            assert any(a.id == agent.id for a in await client.agents.list())

            updated = await client.agents.update(agent.id, description="updated", instructions=None)
            assert updated.description == "updated"
            assert updated.instructions is None
        finally:
            await client.agents.delete(agent.id)

        with pytest.raises(NotFoundError):
            await client.agents.get(agent.id)


@pytest.mark.asyncio
async def test_skill_lifecycle(creds: tuple[str, str], tmp_path: Path) -> None:
    api_key, user_id = creds
    folder = tmp_path / "sdk-integration-skill"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: sdk-integration-skill\ndescription: A throwaway skill for the SDK tests.\n---\n"
        "Say pong.\n"
    )
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        skill = await client.skills.create(folder, display_name=f"sdk-integration-{uuid4()}")
        try:
            assert skill.frontmatter.name == "sdk-integration-skill"
            assert skill.source.value == "custom"
            assert any(s.id == skill.id for s in await client.skills.list())

            updated = await client.skills.update(skill.id, active=False)
            assert updated.active is False

            await asyncio.sleep(1.1)  # version tags are second-resolution
            versioned = await client.skills.upload_version(skill.id, folder)
            assert versioned.id == skill.id
        finally:
            await client.skills.delete(skill.id)


@pytest.mark.asyncio
async def test_source_lifecycle(creds: tuple[str, str], tmp_path: Path) -> None:
    api_key, user_id = creds
    (tmp_path / "a.md").write_text("# Atlas\n\nAtlas ships on March 3.\n")
    (tmp_path / "b.txt").write_text("The owner is Camille.\n")
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        source = await client.sources.create(tmp_path, name=f"sdk-integration-{uuid4()}")
        try:
            assert source.drive_id
            assert (await client.sources.get(source.pid)).pid == source.pid
            files = await client.sources.list_files(source.pid)
            assert sorted(f.name for f in files) == ["a.md", "b.txt"]

            synced = await client.sources.wait_synced(source.pid, timeout=300, interval=5)
            assert synced.status.value == "synced"

            (tmp_path / "c.txt").write_text("Support costs 45.\n")
            added = await client.sources.add_files(source.pid, [tmp_path / "c.txt"])
            assert [f.name for f in added] == ["c.txt"]
            assert await client.sources.download_file(added[0].id) == b"Support costs 45.\n"

            await client.sources.remove_file(source.pid, added[0].id)
            assert "c.txt" not in [f.name for f in await client.sources.list_files(source.pid)]
        finally:
            archived = await client.sources.archive(source.pid)
            assert archived.status.value == "archived"


@pytest.mark.asyncio
async def test_list_mcp_servers(creds: tuple[str, str]) -> None:
    api_key, user_id = creds
    async with AsyncCominty(api_token=api_key, user_id=user_id) as client:
        servers = await client.mcp.list(enabled=None)
        assert isinstance(servers, list)
        assert all(isinstance(server, McpServerOut) and server.name for server in servers)
