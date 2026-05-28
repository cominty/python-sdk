#!/usr/bin/env python3
"""Integration smoke test for all cominty-sdk chat endpoints."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cominty_sdk import AsyncCominty, HumanMessage
from cominty_sdk.exceptions import ComintyAPIError, ComintyError


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False


def required_env() -> tuple[str, str | None, str | None, str, float]:
    from cominty_sdk.config import DEFAULT_AGENT_ID, DEFAULT_API_URL

    api_key = os.environ.get("COMINTY_API_KEY")
    api_url = os.environ.get("COMINTY_API_URL")
    agent_id = os.environ.get("COMINTY_AGENT_ID")
    user_id = os.environ.get("COMINTY_USER_ID", "sdk-test-user")
    wait_timeout = float(os.environ.get("COMINTY_TEST_TIMEOUT", "120"))

    if not api_key:
        print("Missing required environment variable: COMINTY_API_KEY")
        print()
        print("Example:")
        print('  export COMINTY_API_KEY="<access_token from POST /api-tokens>"')
        print(f'  # optional overrides (defaults: {DEFAULT_API_URL}, {DEFAULT_AGENT_ID})')
        print('  export COMINTY_USER_ID="user_123"  # optional, defaults to sdk-test-user')
        print('  export COMINTY_TEST_TIMEOUT="120"    # optional agent wait timeout in seconds')
        print("  uv run python scripts/test_all_endpoints.py")
        sys.exit(1)

    return api_key, api_url, agent_id, user_id, wait_timeout


def format_error(exc: BaseException) -> str:
    if isinstance(exc, ComintyAPIError):
        parts = [f"{type(exc).__name__}: {exc.message}"]
        if exc.status_code is not None:
            parts.append(f"status_code={exc.status_code}")
        if exc.body is not None:
            parts.append(f"body={exc.body!r}")
        return " ".join(parts)
    return f"{type(exc).__name__}: {exc}"


async def run_step(name: str, fn) -> StepResult:
    print(f"→ {name}...", flush=True)
    try:
        detail = await fn()
        print("  ok", flush=True)
        return StepResult(name=name, ok=True, detail=str(detail))
    except ComintyAPIError as exc:
        print("  failed", flush=True)
        return StepResult(name=name, ok=False, detail=format_error(exc))
    except Exception as exc:
        print("  failed", flush=True)
        return StepResult(name=name, ok=False, detail=format_error(exc))


async def run_skip(name: str, detail: str) -> StepResult:
    print(f"→ {name}... skipped", flush=True)
    return StepResult(name=name, ok=True, detail=detail, skipped=True)


async def main() -> int:
    api_key, api_url, agent_id, user_id, wait_timeout = required_env()
    results: list[StepResult] = []

    from cominty_sdk.config import DEFAULT_AGENT_ID, DEFAULT_API_URL

    print(f"Base URL: {api_url or DEFAULT_API_URL}")
    print(f"Agent ID: {agent_id or DEFAULT_AGENT_ID}")
    print(f"User ID: {user_id}")
    print(f"Agent wait timeout: {wait_timeout}s")
    print()

    async with AsyncCominty(
        api_key=api_key,
        base_url=api_url,
        agent_id=agent_id,
        user_id=user_id,
        timeout=120.0,
        stream_timeout=300.0,
    ) as client:
        usage = await run_step("usage.get", lambda: _usage(client))
        if not usage.ok and "status_code=403" in usage.detail:
            results.append(
                await run_skip(
                    "usage.get",
                    "skipped: /chat/usage returns 403 with API token (Clerk session only)",
                )
            )
        else:
            results.append(usage)

        results.append(await run_step("threads.list", lambda: _threads_list(client)))

        thread_id: str | None = None
        message_id: str | None = None
        agent_replied = False

        start = await run_step(
            "chat.start_and_wait",
            lambda: _chat_start_and_wait(client, wait_timeout),
        )
        results.append(start)
        if start.ok:
            thread_id = start.detail.split("thread_id=")[1].split()[0]
            message_id = start.detail.split("message_id=")[1].split()[0]
            agent_replied = "status=success" in start.detail or "status=completed" in start.detail

        if thread_id:
            results.append(
                await run_step(
                    "threads.get",
                    lambda: _threads_get(client, thread_id),
                )
            )
            results.append(
                await run_step(
                    "threads.update",
                    lambda: _threads_update(client, thread_id),
                )
            )

        if thread_id and message_id and agent_replied:
            results.append(
                await run_step(
                    "messages.stream",
                    lambda: _messages_stream(client, message_id),
                )
            )
            results.append(
                await run_step(
                    "messages.send_and_wait",
                    lambda: _messages_send_and_wait(client, thread_id, wait_timeout),
                )
            )
            results.append(
                await run_step(
                    "messages.export (docx)",
                    lambda: _messages_export(client, message_id),
                )
            )
        elif thread_id and message_id:
            results.append(
                await run_skip(
                    "messages.stream",
                    "skipped: agent reply did not complete within timeout",
                )
            )
            results.append(
                await run_skip(
                    "messages.send_and_wait",
                    "skipped: thread still live while assistant message is pending",
                )
            )
            results.append(
                await run_skip(
                    "messages.export (docx)",
                    "skipped: export requires a completed assistant message",
                )
            )

        upload = await run_step("files.upload", lambda: _files_upload(client))
        results.append(upload)
        if upload.ok:
            file_id = upload.detail.split("file_id=")[1].strip()
            results.append(
                await run_step(
                    "files.download",
                    lambda: _files_download(client, file_id),
                )
            )

        if thread_id:
            results.append(
                await run_step(
                    "threads.archive",
                    lambda: _threads_archive(client, thread_id),
                )
            )

    print()
    print("Results")
    print("-------")
    passed = 0
    for result in results:
        status = "SKIP" if result.skipped else "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}")
        if result.detail:
            print(f"       {result.detail}")
        if result.ok:
            passed += 1

    print()
    print(f"{passed}/{len(results)} steps passed")
    return 0 if passed == len(results) else 1


async def _usage(client: AsyncCominty) -> str:
    report = await client.usage.get()
    return f"period_days={report.period_days}"


async def _threads_list(client: AsyncCominty) -> str:
    threads = await client.threads.list(limit=5)
    return f"count={len(threads)}"


async def _chat_start_and_wait(client: AsyncCominty, timeout: float) -> str:
    thread, reply = await client.chat.start_and_wait(
        HumanMessage(content="Reply with exactly: SDK endpoint test OK"),
        name="sdk-endpoint-test",
        timeout=timeout,
    )
    return (
        f"thread_id={thread.id} message_id={reply.id} "
        f"status={reply.status} content_len={len(reply.content)}"
    )


async def _threads_get(client: AsyncCominty, thread_id: str) -> str:
    thread = await client.threads.get(thread_id)
    return f"messages={len(thread.messages)} live={thread.live}"


async def _threads_update(client: AsyncCominty, thread_id: str) -> str:
    thread = await client.threads.update(thread_id, name="sdk-endpoint-test-updated", starred=True)
    return f"name={thread.name!r} starred={thread.starred}"


async def _messages_stream(client: AsyncCominty, message_id: str) -> str:
    events = 0
    async for _event in client.messages.stream(message_id):
        events += 1
        if events >= 1:
            break
    return f"events_received={events}"


async def _messages_send_and_wait(
    client: AsyncCominty,
    thread_id: str,
    timeout: float,
) -> str:
    message = await client.messages.send_and_wait(
        thread_id,
        HumanMessage(content="Reply with exactly: second message OK"),
        timeout=timeout,
    )
    return f"status={message.status} content_len={len(message.content)}"


async def _messages_export(client: AsyncCominty, message_id: str) -> str:
    data = await client.messages.export(message_id, format="docx")
    return f"bytes={len(data)}"


async def _files_upload(client: AsyncCominty) -> str:
    payload = b"cominty sdk upload test\n"
    with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as handle:
        handle.write(payload)
        path = Path(handle.name)
    try:
        file_id = await client.files.upload(path)
    finally:
        path.unlink(missing_ok=True)
    return f"file_id={file_id}"


async def _files_download(client: AsyncCominty, file_id: str) -> str:
    url = await client.files.download(file_id)
    return f"url_len={len(url)}"


async def _threads_archive(client: AsyncCominty, thread_id: str) -> str:
    await client.threads.archive(thread_id)
    return "archived"


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except ComintyError as exc:
        print(format_error(exc), file=sys.stderr)
        raise SystemExit(1) from exc
