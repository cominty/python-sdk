#!/usr/bin/env python3
"""Integration smoke test for all cominty-sdk chat endpoints (verbose HTTP trace)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import httpx

from cominty_sdk import AsyncCominty, HumanMessage
from cominty_sdk._qa import extract_stream_reply, is_stream_terminal_event
from cominty_sdk.exceptions import ComintyAPIError, ComintyError, ComintyTimeoutError
from cominty_sdk.models.messages import MessageOut
from cominty_sdk.models.threads import ThreadOut


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False
    routes: list[str] = field(default_factory=list)


@dataclass
class TestContext:
    verbose: bool = True
    poll_interval: float = 2.0

    def route(self, method: str, path: str, *, note: str = "") -> str:
        line = f"{method} {path}"
        if note:
            line = f"{line}  ({note})"
        if self.verbose:
            print(f"    → {line}", flush=True)
        return line

    def info(self, message: str) -> None:
        if self.verbose:
            print(f"    · {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test Cominty chat API endpoints.")
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Hide per-request trace (summary only)",
    )
    parser.add_argument(
        "--wait-mode",
        choices=("stream", "poll"),
        default=os.environ.get("COMINTY_TEST_WAIT_MODE", "stream"),
        help="How to wait for assistant replies: stream (default) or poll-only",
    )
    return parser.parse_args()


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
        print('  export COMINTY_USER_ID="user_123"')
        print('  export COMINTY_TEST_TIMEOUT="120"')
        print('  export COMINTY_TEST_LIST_LIMIT="5"          # GET /chat limit')
        print('  export COMINTY_TEST_LIST_DETAIL_LIMIT="5" # GET /chat/{id} per thread')
        print('  export COMINTY_TEST_WAIT_MODE="poll"   # or stream (default)')
        print("  uv run python scripts/test_all_endpoints.py")
        print('  uv run python scripts/test_all_endpoints.py --wait-mode poll')
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


def describe_message(message: MessageOut) -> str:
    preview = message.content[:60].replace("\n", " ")
    if len(message.content) > 60:
        preview += "…"
    return (
        f"id={message.id} role={message.role!r} live={message.live} "
        f"status={message.status!r} is_terminal={message.is_terminal()} "
        f"content={preview!r}"
    )


def log_thread_messages(ctx: TestContext, thread: ThreadOut, *, label: str) -> None:
    ctx.info(f"{label}: thread_id={thread.id} live={thread.live} messages={len(thread.messages)}")
    for index, message in enumerate(thread.messages):
        ctx.info(f"  [{index}] {describe_message(message)}")


def find_assistant_message(thread: ThreadOut) -> MessageOut | None:
    for message in reversed(thread.messages):
        if message.role == "assistant":
            return message
    return None


async def wait_for_assistant_poll(
    client: AsyncCominty,
    ctx: TestContext,
    *,
    thread_id: str | UUID,
    assistant_id: UUID,
    timeout: float,
) -> MessageOut:
    """Poll-only wait: repeated GET /chat/{thread_id} until is_terminal()."""
    deadline = time.monotonic() + timeout
    poll = 0
    last_snapshot = ""
    ctx.info("wait mode=poll (no /stream — uses live/status on GET /chat/{id})")

    while True:
        poll += 1
        ctx.route("GET", f"/chat/{thread_id}", note=f"poll #{poll}")
        thread = await client.threads.get(thread_id)
        log_thread_messages(ctx, thread, label=f"poll #{poll}")

        for message in thread.messages:
            if message.id == assistant_id:
                snapshot = f"live={message.live} status={message.status!r}"
                if snapshot != last_snapshot:
                    ctx.info(
                        f"assistant changed: {snapshot} → is_terminal={message.is_terminal()}"
                    )
                    last_snapshot = snapshot
                if message.is_terminal():
                    return message
                break

        if time.monotonic() >= deadline:
            raise ComintyTimeoutError(
                f"Timed out after {timeout}s polling assistant {assistant_id}. "
                f"last_state={last_snapshot or 'n/a'}"
            )

        await asyncio.sleep(ctx.poll_interval)


async def wait_for_assistant_stream(
    client: AsyncCominty,
    ctx: TestContext,
    *,
    thread_id: str | UUID,
    assistant_id: UUID,
    timeout: float,
) -> MessageOut:
    """Wait via GET /chat/messages/{id}/stream (like the web UI), then poll fallback."""
    ctx.info("wait mode=stream (JSONL events, then GET /chat/{id} if needed)")
    deadline = time.monotonic() + timeout
    stream_path = f"/chat/messages/{assistant_id}/stream"
    ctx.route("GET", stream_path, note="JSONL — primary wait (same as Cominty app)")

    event_count = 0
    stream_terminal = False
    stream_status: int | None = None
    try:
        http = client._http
        assert http is not None
        async with http.stream_context("GET", stream_path) as response:
            stream_status = response.status_code
            ctx.info(
                f"stream opened: HTTP {stream_status} "
                f"content-type={response.headers.get('content-type', 'n/a')}"
            )
            async for line in response.aiter_lines():
                stripped = line.strip()
                if not stripped:
                    continue
                event = json.loads(stripped)
                event_count += 1
                ctx.info(f"stream event #{event_count}: {event}")
                if is_stream_terminal_event(event):
                    stream_terminal = True
                    reply = extract_stream_reply(event)
                    ctx.info(
                        "stream terminal event → fetching final message from thread"
                        + (f" (reply={reply!r})" if reply else "")
                    )
                    break
                if time.monotonic() >= deadline:
                    raise ComintyTimeoutError(
                        f"Timed out during stream on {assistant_id} "
                        f"after {event_count} event(s)."
                    )
    except ComintyTimeoutError:
        raise
    except httpx.ReadError as exc:
        ctx.info(
            f"stream ReadError ({exc!r}) — server closed connection with 0 events. "
            "Typical when assistant is still pending and no worker is attached."
        )
    except httpx.StreamClosed:
        ctx.info("stream closed by server with no terminal event")
    except Exception as exc:
        ctx.info(
            f"stream error ({type(exc).__name__}: {exc!r}) "
            f"status={stream_status} → fallback to GET /chat/{{id}} poll"
        )

    if stream_terminal or event_count > 0:
        ctx.route("GET", f"/chat/{thread_id}", note="final state after stream")
        thread = await client.threads.get(thread_id)
        log_thread_messages(ctx, thread, label="after stream")
        for message in thread.messages:
            if message.id == assistant_id:
                if message.is_terminal():
                    return message
                ctx.info(
                    f"stream ended but message not terminal yet: "
                    f"live={message.live} status={message.status!r}"
                )
                break

    ctx.info("continuing with poll fallback (GET /chat/{thread_id})")
    poll = 0
    last_snapshot = ""
    while True:
        poll += 1
        ctx.route("GET", f"/chat/{thread_id}", note=f"poll fallback #{poll}")
        thread = await client.threads.get(thread_id)
        log_thread_messages(ctx, thread, label=f"poll #{poll}")

        for message in thread.messages:
            if message.id == assistant_id:
                snapshot = f"live={message.live} status={message.status!r}"
                if snapshot != last_snapshot:
                    ctx.info(
                        f"assistant changed: {snapshot} → is_terminal={message.is_terminal()}"
                    )
                    last_snapshot = snapshot
                if message.is_terminal():
                    return message
                break

        if time.monotonic() >= deadline:
            raise ComintyTimeoutError(
                f"Timed out after {timeout}s waiting for assistant {assistant_id}. "
                f"stream_events={event_count} last_state={last_snapshot or 'n/a'}"
            )

        await asyncio.sleep(ctx.poll_interval)


async def wait_for_assistant(
    client: AsyncCominty,
    ctx: TestContext,
    *,
    thread_id: str | UUID,
    assistant_id: UUID,
    timeout: float,
    mode: str,
) -> MessageOut:
    if mode == "poll":
        return await wait_for_assistant_poll(
            client, ctx, thread_id=thread_id, assistant_id=assistant_id, timeout=timeout
        )
    return await wait_for_assistant_stream(
        client, ctx, thread_id=thread_id, assistant_id=assistant_id, timeout=timeout
    )


async def run_step(ctx: TestContext, client: AsyncCominty, name: str, fn) -> StepResult:
    print(f"→ {name}", flush=True)
    routes: list[str] = []
    try:
        detail, routes = await fn(ctx, client)
        print("  ok", flush=True)
        return StepResult(name=name, ok=True, detail=detail, routes=routes)
    except Exception as exc:
        print("  failed", flush=True)
        return StepResult(name=name, ok=False, detail=format_error(exc), routes=routes)


async def run_skip(name: str, detail: str) -> StepResult:
    print(f"→ {name}... skipped", flush=True)
    return StepResult(name=name, ok=True, detail=detail, skipped=True)


async def main() -> int:
    args = parse_args()
    ctx = TestContext(verbose=not args.quiet, poll_interval=2.0)
    wait_mode: str = args.wait_mode

    api_key, api_url, agent_id, user_id, wait_timeout = required_env()
    results: list[StepResult] = []

    from cominty_sdk.config import DEFAULT_AGENT_ID, DEFAULT_API_URL

    print(f"Base URL: {api_url or DEFAULT_API_URL}")
    print(f"Agent ID: {agent_id or DEFAULT_AGENT_ID}")
    print(f"User ID: {user_id}")
    print(f"Agent wait timeout: {wait_timeout}s (poll every {ctx.poll_interval}s)")
    print(f"Wait mode: {wait_mode}")
    print()

    async with AsyncCominty(
        api_key=api_key,
        base_url=api_url,
        agent_id=agent_id,
        user_id=user_id,
        timeout=120.0,
        stream_timeout=300.0,
    ) as client:
        usage = await run_step(ctx, client, "usage.get", _usage)
        if not usage.ok and "status_code=403" in usage.detail:
            results.append(
                await run_skip(
                    "usage.get",
                    "skipped: GET /chat/usage → 403 with API token (Clerk session only)",
                )
            )
        else:
            results.append(usage)

        results.append(await run_step(ctx, client, "threads.list", _threads_list))

        thread_id: str | None = None
        assistant_id: str | None = None
        agent_replied = False

        start = await run_step(ctx, client, "chat.start", _chat_start)
        results.append(start)

        if start.ok:
            thread_id = start.detail.split("thread_id=")[1].split()[0]
            assistant_id = start.detail.split("assistant_id=")[1].split()[0]

            wait = await run_step(
                ctx,
                client,
                f"messages.wait_for_assistant ({wait_mode})",
                lambda c, cl: _wait_assistant(
                    c, cl, thread_id, assistant_id, wait_timeout, wait_mode
                ),
            )
            results.append(wait)
            agent_replied = wait.ok

        if thread_id:
            results.append(
                await run_step(
                    ctx,
                    client,
                    "threads.get",
                    lambda c, cl, tid=thread_id: _threads_get(c, cl, tid),
                )
            )
            results.append(
                await run_step(
                    ctx,
                    client,
                    "threads.update",
                    lambda c, cl, tid=thread_id: _threads_update(c, cl, tid),
                )
            )

        if thread_id and assistant_id and agent_replied:
            results.append(
                await run_step(
                    ctx,
                    client,
                    "messages.stream",
                    lambda c, cl, mid=assistant_id: _messages_stream(c, cl, mid),
                )
            )
            results.append(
                await run_step(
                    ctx,
                    client,
                    "messages.send + wait",
                    lambda c, cl: _messages_send_and_wait(
                        c, cl, thread_id, wait_timeout, wait_mode
                    ),
                )
            )
            results.append(
                await run_step(
                    ctx,
                    client,
                    "messages.export (docx)",
                    lambda c, cl, mid=assistant_id: _messages_export(c, cl, mid),
                )
            )
        elif thread_id and assistant_id:
            results.append(
                await run_skip(
                    "messages.stream",
                    "skipped: assistant never reached is_terminal() within timeout",
                )
            )
            results.append(
                await run_skip(
                    "messages.send + wait",
                    "skipped: thread still live / assistant not terminal",
                )
            )
            results.append(
                await run_skip(
                    "messages.export (docx)",
                    "skipped: export needs a completed assistant message",
                )
            )

        upload = await run_step(ctx, client, "files.upload", _files_upload)
        results.append(upload)
        if upload.ok:
            file_id = upload.detail.split("file_id=")[1].strip()
            results.append(
                await run_step(
                    ctx,
                    client,
                    "files.download",
                    lambda c, cl, fid=file_id: _files_download(c, cl, fid),
                )
            )

        if thread_id:
            results.append(
                await run_step(
                    ctx,
                    client,
                    "threads.archive",
                    lambda c, cl, tid=thread_id: _threads_archive(c, cl, tid),
                )
            )

    print()
    print("Results")
    print("-------")
    passed = 0
    for result in results:
        status = "SKIP" if result.skipped else "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}")
        if result.routes:
            for route in result.routes:
                print(f"       {route}")
        if result.detail:
            print(f"       {result.detail}")
        if result.ok:
            passed += 1

    print()
    print(f"{passed}/{len(results)} steps passed")
    return 0 if passed == len(results) else 1


async def _usage(ctx: TestContext, client: AsyncCominty) -> tuple[str, list[str]]:
    routes = [ctx.route("GET", "/chat/usage")]
    report = await client.usage.get()
    return f"period_days={report.period_days}", routes


async def _threads_list(ctx: TestContext, client: AsyncCominty) -> tuple[str, list[str]]:
    list_limit = int(os.environ.get("COMINTY_TEST_LIST_LIMIT", "5"))
    detail_limit = int(os.environ.get("COMINTY_TEST_LIST_DETAIL_LIMIT", str(list_limit)))

    routes = [ctx.route("GET", "/chat", note=f"?limit={list_limit}&user_id=…")]
    summaries = await client.threads.list(limit=list_limit)
    ctx.info(
        f"GET /chat returned {len(summaries)} summaries — "
        "messages require GET /chat/{thread_id}"
    )

    message_counts: list[str] = []
    for index, summary in enumerate(summaries):
        ctx.info(
            f"summary [{index}] id={summary.id} name={summary.name!r} "
            f"agent={summary.agent.id} live={summary.live} starred={summary.starred}"
        )
        if index >= detail_limit:
            continue

        routes.append(ctx.route("GET", f"/chat/{summary.id}", note="full thread + messages"))
        thread = await client.threads.get(summary.id)
        log_thread_messages(ctx, thread, label=f"thread {summary.id}")

        previews: list[str] = []
        for msg_index, message in enumerate(thread.messages):
            preview = message.content[:40].replace("\n", " ")
            if len(message.content) > 40:
                preview += "…"
            previews.append(
                f"m{msg_index}:{message.role}/{message.status}/live={message.live}/{preview!r}"
            )
        message_counts.append(f"{summary.id}→{len(thread.messages)} msg(s)")

    detail = f"count={len(summaries)}"
    if message_counts:
        detail += f" messages=[{'; '.join(message_counts)}]"
    return detail, routes


async def _chat_start(ctx: TestContext, client: AsyncCominty) -> tuple[str, list[str]]:
    routes = [
        ctx.route("POST", "/chat", note="StartChat: message + options.agent_id + options.user_id")
    ]
    thread = await client.chat.start(
        HumanMessage(content="Reply with exactly: SDK endpoint test OK"),
        name="sdk-endpoint-test",
    )
    log_thread_messages(ctx, thread, label="POST /chat response")
    assistant = find_assistant_message(thread)
    if not assistant:
        raise RuntimeError("No assistant message in POST /chat response")
    ctx.info(
        "Will poll assistant message (not user). "
        "Do not assume status=pending alone means failure — check live + is_terminal()."
    )
    return (
        f"thread_id={thread.id} assistant_id={assistant.id} "
        f"initial_status={assistant.status!r} live={assistant.live}",
        routes,
    )


async def _wait_assistant(
    ctx: TestContext,
    client: AsyncCominty,
    thread_id: str,
    assistant_id: str,
    timeout: float,
    wait_mode: str,
) -> tuple[str, list[str]]:
    message = await wait_for_assistant(
        client,
        ctx,
        thread_id=thread_id,
        assistant_id=UUID(assistant_id),
        timeout=timeout,
        mode=wait_mode,
    )
    if wait_mode == "poll":
        routes = [f"GET /chat/{thread_id} (poll until is_terminal)"]
    else:
        routes = [
            f"GET /chat/messages/{assistant_id}/stream",
            f"GET /chat/{thread_id} (stream and/or poll)",
        ]
    return (
        f"assistant_id={message.id} status={message.status!r} live={message.live} "
        f"is_terminal={message.is_terminal()} content_len={len(message.content)}",
        routes,
    )


async def _threads_get(
    ctx: TestContext, client: AsyncCominty, thread_id: str
) -> tuple[str, list[str]]:
    routes = [ctx.route("GET", f"/chat/{thread_id}")]
    thread = await client.threads.get(thread_id)
    log_thread_messages(ctx, thread, label="GET thread")
    return f"messages={len(thread.messages)} live={thread.live}", routes


async def _threads_update(
    ctx: TestContext, client: AsyncCominty, thread_id: str
) -> tuple[str, list[str]]:
    routes = [ctx.route("PUT", f"/chat/{thread_id}", note="{ name, starred }")]
    thread = await client.threads.update(thread_id, name="sdk-endpoint-test-updated", starred=True)
    return f"name={thread.name!r} starred={thread.starred}", routes


async def _messages_stream(
    ctx: TestContext, client: AsyncCominty, message_id: str
) -> tuple[str, list[str]]:
    routes = [ctx.route("GET", f"/chat/messages/{message_id}/stream", note="JSONL")]
    events = 0
    async for event in client.messages.stream(message_id):
        events += 1
        ctx.info(f"stream event #{events}: {event}")
        if events >= 3:
            break
    return f"events_received={events}", routes


async def _messages_send_and_wait(
    ctx: TestContext,
    client: AsyncCominty,
    thread_id: str,
    timeout: float,
    wait_mode: str,
) -> tuple[str, list[str]]:
    routes = [ctx.route("POST", f"/chat/{thread_id}", note="Chat { message, options.agent_id }")]
    sent = await client.messages.send(
        thread_id,
        HumanMessage(content="Reply with exactly: second message OK"),
    )
    ctx.info(f"POST /chat/{{id}} immediate body: {describe_message(sent)}")
    thread = await client.threads.get(thread_id)
    routes.append(ctx.route("GET", f"/chat/{thread_id}", note="fetch thread after send"))
    assistant = find_assistant_message(thread)
    if not assistant:
        raise RuntimeError("No assistant message after POST /chat/{thread_id}")

    message = await wait_for_assistant(
        client,
        ctx,
        thread_id=thread_id,
        assistant_id=assistant.id,
        timeout=timeout,
        mode=wait_mode,
    )
    routes.append(f"wait via {wait_mode}")
    return f"status={message.status!r} content_len={len(message.content)}", routes


async def _messages_export(
    ctx: TestContext, client: AsyncCominty, message_id: str
) -> tuple[str, list[str]]:
    routes = [ctx.route("GET", f"/chat/messages/{message_id}/export", note="?format=docx")]
    data = await client.messages.export(message_id, format="docx")
    return f"bytes={len(data)}", routes


async def _files_upload(ctx: TestContext, client: AsyncCominty) -> tuple[str, list[str]]:
    routes: list[str] = []
    payload = b"cominty sdk upload test\n"
    with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as handle:
        handle.write(payload)
        path = Path(handle.name)
    try:
        ctx.route("GET", "/chat/files/upload", note="?mimetype&filename → S3 presign")
        ctx.route("POST", "<s3-presigned-url>", note="direct upload (not Cominty API)")
        ctx.route("POST", "/chat/files/upload", note="confirm { etag, key }")
        file_id = await client.files.upload(path)
        routes.extend(
            [
                "GET /chat/files/upload",
                "POST <s3-presigned-url>",
                "POST /chat/files/upload",
            ]
        )
    finally:
        path.unlink(missing_ok=True)
    return f"file_id={file_id}", routes


async def _files_download(
    ctx: TestContext, client: AsyncCominty, file_id: str
) -> tuple[str, list[str]]:
    routes = [ctx.route("GET", f"/chat/files/{file_id}")]
    url = await client.files.download(file_id)
    return f"url_len={len(url)}", routes


async def _threads_archive(
    ctx: TestContext, client: AsyncCominty, thread_id: str
) -> tuple[str, list[str]]:
    routes = [ctx.route("DELETE", f"/chat/{thread_id}", note="archive")]
    await client.threads.archive(thread_id)
    return "archived", routes


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except ComintyError as exc:
        print(format_error(exc), file=sys.stderr)
        raise SystemExit(1) from exc
