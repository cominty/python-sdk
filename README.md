# Cominty Python SDK

[![PyPI](https://img.shields.io/pypi/v/cominty-sdk.svg)](https://pypi.org/project/cominty-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/cominty-sdk.svg)](https://pypi.org/project/cominty-sdk/)
[![CI](https://github.com/cominty/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/cominty/python-sdk/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Official async Python client for the Cominty managed agent chat API.

Start a conversation with an agent, stream its progress live, and manage threads
— with a small, fully-typed surface that's the same on Python 3.9 through 3.13.

```python
import asyncio
from cominty_sdk import AsyncCominty

async def main() -> None:
    async with AsyncCominty() as client:          # reads COMINTY_API_KEY + COMINTY_USER_ID
        run = await client.chat.start(agent_id="__cominty_agents::agent.chat",
                                      message="What is Cominty?")
        print(await run.text())

asyncio.run(main())
```

- **Async-first**, built on `httpx`.
- **Fully typed** — ships `py.typed`; strict-checked with pyright. Pydantic models everywhere.
- **One handle for streaming *and* awaiting** — iterate a run for live progress
  events, or just `await run.text()` for the final answer.
- **Fail-fast validation** — bad parameters raise locally, before any request.
- **Typed errors** — every failure is a `ComintyError` subclass.

---

## Requirements

- **Python 3.9+**
- A Cominty API key and your user id (see [Authentication](#authentication))

## Installation

```bash
pip install cominty-sdk
# or
uv add cominty-sdk
```

## Authentication

You need two things, both from [platform.cominty.ai](https://platform.cominty.ai):

1. **API key** → [platform.cominty.ai/api-keys](https://platform.cominty.ai/api-keys) (shown once — copy it).
2. **Your user id** → avatar (top right) → **Profile**. It looks like `user_31HPTBuBvX20xlQNAbvxjOxPbKB`.

The user id identifies the end user every request acts on behalf of. It's set
**once on the client** (or via `COMINTY_USER_ID`) and applied to every call.

The simplest setup is environment variables:

```bash
export COMINTY_API_KEY="<your API key>"
export COMINTY_USER_ID="user_..."
```

```python
async with AsyncCominty() as client:   # picks both up from the environment
    ...
```

…or pass them explicitly (explicit arguments win over the environment):

```python
client = AsyncCominty(api_token="<your API key>", user_id="user_...")
```

A malformed `user_id` is rejected at construction, not as a server error later.

### Picking an agent

Every chat call takes an `agent_id`. Browse your agents and copy an id at
[platform.cominty.ai/agents](https://platform.cominty.ai/agents) — they look
like `__cominty_agents::agent.chat`.

## Quick start

Every conversation starts with `chat.start`, which returns a **run** — a handle
to the assistant's in-progress reply. From there, pick the style you need.

### Just get the answer

```python
run = await client.chat.start(agent_id=AGENT_ID, message="Give me one fun fact.")
print(await run.text())              # blocks until the agent finishes
```

`await run.result()` gives the full `Message` (status, files, structured output,
questions). `text()` is shorthand for `result().content`.

### Stream progress events

Iterating a run yields **progress events only** — tool calls, LLM steps, the
result event — as they happen. The finished reply is captured for you.

```python
from cominty_sdk import events

run = await client.chat.start(agent_id=AGENT_ID, message="Research X and summarize.")

async for event in run:
    if isinstance(event, events.ToolCall):
        print(f"tool {event.data.name} -> {event.status}")
    elif isinstance(event, events.LlmStep):
        print(f"llm  {event.data.description}")
    elif isinstance(event, events.Result):
        print(f"cost {event.data.cost.total}")

print("FINAL:", await run.text())    # available after the stream drains
```

> A run's stream is single-use: iterate it **or** await its result — the result
> is cached, so calling `text()`/`result()` after iterating is free.

### Continue the conversation

`chat.send(thread_id, ...)` is the mirror of `start` for an existing thread:
same arguments, same streamable run. The agent keeps the thread's context.

```python
first = await client.chat.start(agent_id=AGENT_ID, message="Pick a language.")
await first.text()

second = await client.chat.send(
    first.thread.id, agent_id=AGENT_ID, message="Now show hello-world in it.",
)
print(await second.text())
```

### Answer the agent's questions

When an agent needs more input, it ends its turn with clarifying **questions**
(a `prompt` plus suggested `options`) instead of a final answer. Read them, then
answer with a normal follow-up:

```python
run = await client.chat.start(agent_id=AGENT_ID, message="Book me a room.")
await run.text()

for q in await run.questions():
    print(q.prompt, q.options)

# answer = the chosen option (or free text)
reply = await client.chat.send(run.thread.id, agent_id=AGENT_ID, message="Tomorrow 10am")
print(await reply.text())
```

### Manage threads

`client.threads` is scoped to the client's `user_id` automatically.

```python
# List & search the user's conversations (summaries — no messages)
for t in await client.threads.list(limit=20):
    print(t.created_at, t.name, t.id)

await client.threads.list(terms=["invoice"])     # free-text search
await client.threads.list(limit=10, page=1)       # paginate (zero-based)

# Load one thread's full history
thread = await client.threads.get(thread_id)
print(len(thread.messages))

# Partial update — only the fields you pass change (returns a ThreadSummary)
await client.threads.update(thread_id, name="Renamed", starred=True)

# Archive (soft-delete)
await client.threads.archive(thread_id)
```

### Memory files

`client.memory` stores per-user files an agent can read back later — scoped to
the client's `user_id` automatically.

```python
# Create a file
file = await client.memory.create(
    path="preferences/tone.md", purpose="writing style", content="Keep it casual."
)

# List files (summaries — no content)
for f in await client.memory.list():
    print(f.path, f.purpose, f.version)

# Read one file's content
file = await client.memory.get("preferences/tone.md")

# Partial update — only the fields you pass change. `version` guards against
# overwriting a concurrent change: pass back the value from your last read,
# and a stale one raises ConflictError (409).
file = await client.memory.update(
    "preferences/tone.md", version=file.version, content="Keep it upbeat."
)

# Delete
await client.memory.delete("preferences/tone.md")
```

`version` is an opaque token — never parse or compare it, just round-trip
whatever the API last gave you.

There's currently no way to clear `content` or `purpose` once set — the API
ignores an explicit `null` (leaves the existing value untouched), so
`memory.update(..., content=None)` raises `InvalidParams` locally rather than
sending a request that looks like it succeeded but did nothing.

A few other things worth knowing:
- `path` may have at most one folder segment — `"preferences/tone.md"` is
  fine, `"a/b/tone.md"` isn't (raises `InvalidParams` locally).
- `content` may be an empty string; there's no minimum length.
- `memory.delete()` is not idempotent — deleting an already-deleted path
  raises `NotFoundError`, not a repeated success.

## Examples

Runnable scripts for each scenario live in [`examples/`](examples/):

| Script | Shows |
|--------|-------|
| [`01_stream_events.py`](examples/01_stream_events.py) | Stream progress events live |
| [`02_await_result.py`](examples/02_await_result.py) | Fire and await the final answer |
| [`03_follow_up.py`](examples/03_follow_up.py) | Continue in the same thread |
| [`04_answer_questions.py`](examples/04_answer_questions.py) | Read & answer agent questions |
| [`05_list_threads.py`](examples/05_list_threads.py) | List and search threads |
| [`06_manage_thread.py`](examples/06_manage_thread.py) | Get, rename/star, archive |
| [`07_custom_agent.py`](examples/07_custom_agent.py) | Call a custom managed agent (your own model + instructions) |
| [`08_mcp_linear.py`](examples/08_mcp_linear.py) | Custom agent pulls live context from an MCP server (Linear) |

They render colored, aligned output with [`rich`](https://github.com/Textualize/rich),
which ships in the dev extras:

```bash
uv sync --all-extras --dev                 # installs rich (or: pip install rich)
export COMINTY_API_KEY=... COMINTY_USER_ID=user_...
python examples/01_stream_events.py
```

## Message parameters

Both `chat.start` and `chat.send` accept:

| Argument | Type | Notes |
|----------|------|-------|
| `agent_id` | `str` | **Required.** The agent to run. |
| `message` | `str` | **Required.** The user's message (max 30,000 chars). |
| `name` | `str` | `start` only — names the new thread. |
| `file_ids` | `list[str]` | Attach previously-uploaded files (max 5). |
| `source_ids` | `list[int]` | Restrict retrieval to specific knowledge sources. |
| `document_ids` | `list[str]` | Restrict retrieval to specific documents. |
| `disabled_tools` | `list[str]` | Turn tools off: `"web"`, `"company_documents"`, `"mcp:<server>"`, or `"mcp:*"` for all MCP. |

Invalid values raise `InvalidParams` **before** any request is sent.

## Configuration

| Argument | Env var | Default |
|----------|---------|---------|
| `api_token` | `COMINTY_API_KEY` | — (required) |
| `user_id` | `COMINTY_USER_ID` | — (required) |
| `base_url` | `COMINTY_BASE_URL` | `https://ds.cominty.com` |
| `timeout` | — | `60` (seconds) |

Resolution order for each option: **explicit argument → environment variable →
default**. The SDK does **not** auto-load `.env`; export the vars or load the
file yourself (see [`.env.example`](.env.example)).

## Error handling

Every error is a subclass of `ComintyError`:

```python
from cominty_sdk import (
    ComintyError,        # base — catch-all
    APIError,            # any 4xx/5xx; carries .status_code and a typed .error body
    AuthError,           # 401
    PermissionError,     # 403
    NotFoundError,       # 404
    ConflictError,       # 409
    RateLimitError,      # 429 — exposes .reset_at
    ServerError,         # 5xx
    APIConnectionError,  # network failure / timeout, no response
    StreamInterrupted,   # server shut down mid-stream — carries the .partial Message
    InvalidParams,       # client-side validation failed — .errors lists each problem
    SDKError,            # unexpected SDK-internal condition
)

try:
    run = await client.chat.start(agent_id=AGENT_ID, message="hi")
    print(await run.text())
except RateLimitError as e:
    print(f"slow down — retry after {e.reset_at}")
except APIError as e:
    print(f"API error {e.status_code}: {e.error}")
```

## Development

```bash
uv sync --all-extras --dev
uv run pytest          # tests
uv run ruff check .    # lint
uv run pyright         # type-check (strict)
```

Integration tests are opt-in (they hit the real API):

```bash
COMINTY_API_KEY=... COMINTY_USER_ID=... uv run pytest -m integration
```

See [AGENTS.md](AGENTS.md) for coding conventions (typing, versioning, models).

## Releasing

Publishing to PyPI uses **Trusted Publishing (OIDC)** — no tokens stored in
GitHub — and is triggered by publishing a **GitHub Release**
(`.github/workflows/release.yml`). The published version comes from
`pyproject.toml`.

**`uv run invoke release` modifies repository files and CREATES A GIT COMMIT
AND TAG.** It bumps `pyproject.toml`, regenerates `uv.lock`, runs the lint /
type-check / test / build gate, then commits and tags — it never pushes and
never creates the GitHub Release itself.

```bash
# 1. bump, validate, commit, and tag locally — pick exactly one
uv run invoke release --patch            # X.Y.Z -> X.Y.(Z+1)
uv run invoke release --minor            # X.Y.Z -> X.(Y+1).0
uv run invoke release --major            # X.Y.Z -> (X+1).0.0
uv run invoke release --version X.Y.Z    # set an explicit version

# 2. push the commit and the tag it just created
git push origin HEAD
git push origin vX.Y.Z

# 3. create the release — this triggers the publish workflow
gh release create vX.Y.Z --title vX.Y.Z --generate-notes
#    pre-release rehearsal (skips `invoke release`): tag and push manually,
#    then gh release create vX.Y.Zrc1 --prerelease --generate-notes
```

A local rehearsal to TestPyPI is available via `uv run invoke publish-test`.

## License

MIT