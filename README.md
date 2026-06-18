# Cominty Python SDK

[![PyPI](https://img.shields.io/pypi/v/cominty-sdk.svg)](https://pypi.org/project/cominty-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/cominty-sdk.svg)](https://pypi.org/project/cominty-sdk/)
[![CI](https://github.com/cominty/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/cominty/python-sdk/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Official async Python client for the Cominty managed agent chat API.

## Requirements

- Python 3.11+
- A Cominty API key

## Installation

```bash
pip install cominty-sdk
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add cominty-sdk
```

## Quick setup (3 steps)

1. **Install** — `pip install cominty-sdk` (or `uv add cominty-sdk`).
2. **Create a `.env`** — copy the template and fill in your API token:

   ```bash
   cp .env.example .env   # then edit COMINTY_API_KEY and COMINTY_USER_ID
   ```

   The SDK **loads `.env` automatically** (via `pydantic-settings`) — you don't
   need `python-dotenv` or to export anything. A minimal `.env`:

   ```dotenv
   COMINTY_API_KEY=<your API key>
   COMINTY_USER_ID=user_123
   # COMINTY_AGENT_ID=__cominty_agents::agent.chat   # optional, see below
   # COMINTY_ENVIRONMENT=production                   # dev | staging | production (default)
   ```

   Don't have a key yet? See [Authentication](#authentication) below.
3. **Run** — see [Quick start](#quick-start).

> Configuration resolution order for every option: **explicit argument** →
> **environment variable** (incl. `.env`) → **built-in default**.

`.env` is **optional** — it's a dev convenience. You can configure everything in
code (handy when secrets come from a vault or your app's own env), and the SDK
also reads real OS environment variables directly:

```python
client = AsyncCominty(
    api_key="ak_...",       # explicit args win over env / .env
    user_id="user_123",
    environment="production",
)
```

## Configuration

| Variable | Description |
|----------|-------------|
| `COMINTY_API_KEY` | Your API key (required) — create one at [platform.cominty.com/api-keys](https://platform.cominty.com/api-keys) |
| `COMINTY_USER_ID` | End-user identifier, required when starting a conversation (e.g. `user_123`) |
| `COMINTY_AGENT_ID` | Default agent id (default: `__cominty_agents::agent.chat`) — find yours at [platform.cominty.com/agents](https://platform.cominty.com/agents) |
| `COMINTY_API_URL` | Override base URL (default: `https://ds.cominty.com`) |
| `COMINTY_ENVIRONMENT` | `dev`, `staging`, or `production` (default: `production`) |
| `COMINTY_MAX_RETRIES` | Max retries on transient errors (default: `3`) |
| `COMINTY_TIMEOUT` | Request timeout in seconds (default: `60`) |

Defaults (no env required):

- API URL: `https://ds.cominty.com`
- Agent ID: `__cominty_agents::agent.chat`

Other environments via `COMINTY_ENVIRONMENT`:

- `dev`: `https://ds-dev.cominty.com`
- `staging`: `https://api.staging.cominty.com`
- `production`: `https://ds.cominty.com`

## Authentication

### 1. Get your API key

Create an API key from the Cominty platform:
**https://platform.cominty.com/api-keys**

Copy it (it's shown once) into your `.env` or environment:

```bash
export COMINTY_API_KEY="<your API key>"
export COMINTY_USER_ID="user_123"   # identifies the end-user of your app
```

`user_id` is **required** when starting a conversation.

### 2. Get your agent id

Create an agent — or pick an existing one — and copy its id from:
**https://platform.cominty.com/agents**

Agent ids look like `__cominty_agents::agent.chat` (the SDK default). Pass yours
via `agent_id=` or `COMINTY_AGENT_ID`:

```bash
export COMINTY_AGENT_ID="__cominty_agents::agent.chat"
```

## Quick start

```python
import asyncio

from cominty_sdk import AsyncCominty, HumanMessage


async def main() -> None:
    async with AsyncCominty() as client:
        thread, reply = await client.chat.start_and_wait(
            HumanMessage(content="What is Cominty?"),
            user_id="user_123",
        )
        print(reply.content)
        print(reply.tool_names)


asyncio.run(main())
```

## Send a message in an existing thread

```python
message = await client.messages.send_and_wait(
    thread_id=thread.id,
    message=HumanMessage(
        content="Search our docs for onboarding steps",
        source_ids=[42],
        disabled_tools=["web"],
    ),
    agent_id="your-agent-id",
)
```

## Upload a file

Upload is a single high-level call that performs the 3-step S3 flow internally:

```python
file_id = await client.files.upload("report.pdf")

await client.messages.send_and_wait(
    thread_id=thread.id,
    message=HumanMessage(content="Summarize this file", file_ids=[file_id]),
    agent_id="your-agent-id",
)
```

## Streaming

The API returns JSONL events on the stream endpoint. Terminal events include
`name: "result", status: "success"` or a final assistant snapshot with `live: false`.

By default, `wait_until_done` and `start_and_wait` consume the stream first, then
fall back to polling `GET /chat/{thread_id}` if needed. Disable streaming:

```python
reply = await client.messages.wait_until_done(
    message.id,
    thread_id=thread.id,
    prefer_stream=False,
)
```

```python
async for event in client.messages.stream(message.id):
    print(event)
```

## QA helpers

`MessageOut` exposes convenience accessors for automated QA:

```python
reply.tool_names           # tools invoked (from events)
reply.cite_tags            # raw <cite .../> tags
reply.document_citations   # parsed document citations
reply.web_citations        # parsed web citations
```

## Covered endpoints

| Resource | Methods |
|----------|---------|
| Threads | `list`, `get`, `update`, `archive` |
| Chat | `start`, `start_and_wait` |
| Messages | `send`, `send_and_wait`, `wait_until_done`, `cancel`, `export`, `stream` |
| Files | `upload`, `download` |
| Usage | `get` |
| Agents | `list` |

### Choosing an agent

Browse your agents and copy their ids from the platform:
**https://platform.cominty.com/agents**

Pass an agent id to any chat call via `agent_id=` (or set `COMINTY_AGENT_ID`):

```python
thread, reply = await client.chat.start_and_wait(
    HumanMessage(content="Hello"),
    user_id="user_123",
    agent_id="__cominty_agents::agent.chat",
)
```

## Development

```bash
uv sync --all-extras --dev
uv run pytest
uv run ruff check .
uv run mypy
```

Integration tests are opt-in:

```bash
COMINTY_API_KEY=... COMINTY_AGENT_ID=... uv run pytest -m integration
```

## Releasing

Publishing is **tag-driven** and uses **PyPI Trusted Publishing (OIDC)** — no API
tokens are stored in GitHub. The workflow lives in `.github/workflows/release.yml`.

### How a tag maps to a registry

| Tag example | Publishes to |
|-------------|--------------|
| `v0.2.0rc1`, `v0.2.0a1`, `v0.2.0b1`, `v0.2.0.dev1` (pre-release) | **TestPyPI** only |
| `v0.2.0` (final semver) | **TestPyPI**, then **PyPI** |

On any `v*` tag the workflow runs the test matrix, verifies the tag matches the
`version` in `pyproject.toml`, builds the sdist + wheel, and publishes. Final
releases go through TestPyPI first, then PyPI.

### Cutting a release

```bash
# 1. Bump the version in pyproject.toml (e.g. 0.1.0 -> 0.2.0)

# 2. (optional) dry-run to TestPyPI with a pre-release tag
git tag v0.2.0rc1 && git push origin v0.2.0rc1
#    verify: pip install -i https://test.pypi.org/simple/ cominty-sdk==0.2.0rc1

# 3. ship to PyPI with the final tag
git tag v0.2.0 && git push origin v0.2.0
```

### One-time setup (required before the first publish)

Trusted Publishing must be registered on **both** registries — once each:

1. **TestPyPI** → https://test.pypi.org/manage/account/publishing/ → add a
   pending publisher:
   - Project: `cominty-sdk` · Owner: `cominty` · Repo: `python-sdk`
   - Workflow: `release.yml` · Environment: `testpypi`
2. **PyPI** → https://pypi.org/manage/account/publishing/ → same, with
   Environment: `pypi`.
3. (recommended) In GitHub repo **Settings → Environments**, add required
   reviewers to the `pypi` environment so production publishes need an approval.

No secrets to configure — OIDC handles auth.

### Manual publish (fallback)

```bash
uv build
uv publish --token <pypi-token>          # PyPI
uv publish --token <testpypi-token> --publish-url https://test.pypi.org/legacy/
```

## License

MIT
