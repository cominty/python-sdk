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
   COMINTY_API_KEY=<access_token from POST /api-tokens>
   COMINTY_USER_ID=user_123
   # COMINTY_ENVIRONMENT=production   # dev | staging | production (default)
   ```

   Don't have a token yet? See [Authentication](#authentication) below.
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
| `COMINTY_API_KEY` | API access token from `POST /api-tokens` (required for chat) |
| `COMINTY_SESSION_TOKEN` | Clerk session JWT for admin ops (`/api-tokens` management) |
| `COMINTY_API_URL` | Override base URL (default: `https://ds.cominty.com`) |
| `COMINTY_ENVIRONMENT` | `dev`, `staging`, or `production` (default: `production`) |
| `COMINTY_AGENT_ID` | Default agent pid (default: `__cominty_agents::agent.chat`) |
| `COMINTY_USER_ID` | End-user identifier (required in API token mode, e.g. `user_123`) |
| `COMINTY_ORG_ID` | Organization id header for Clerk session token requests |
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

Cominty uses **two different credentials**:

| Credential | Header | Used for |
|------------|--------|----------|
| **Clerk session token** | `Authorization: Bearer <jwt>` (+ optional `x-cmt-current-org-id`) | Admin: `POST/GET/DELETE /api-tokens` |
| **API access token** | `x-cominty-token: Bearer <access_token>` | Chat SDK: `/chat`, files, usage |

### 1. Create an API token (admin, one-time setup)

Use a Clerk session token (from the Cominty portal, valid ~1 min) or ask an admin for a longer test token:

```python
async with AsyncCominty(
    session_token="eyJ...",          # Clerk JWT
    org_id="8",
    base_url="https://ds.cominty.com",
) as admin:
    created = await admin.api_tokens.create("my-sdk-token")
    print(created.access_token)  # save immediately
```

Or via curl:

```bash
curl -X POST "https://ds.cominty.com/api-tokens" \
  -H "Authorization: Bearer $COMINTY_SESSION_TOKEN" \
  -H "x-cmt-current-org-id: 8" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-sdk-token"}'
```

### 2. Use the API token for chat

```bash
export COMINTY_API_KEY="<access_token>"
export COMINTY_USER_ID="user_123"
# COMINTY_API_URL and COMINTY_AGENT_ID are optional (SDK defaults above)
```

In API token mode, `user_id` is **required** when starting a conversation.

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
| Usage | `get` (requires a Clerk session token, not an API token) |
| Agents | `list` (requires a Clerk session token) |

### List agents (benchmark / agent selection)

`GET /agents` returns org-managed agents (`id`, `name`, `mode`, …). Use `agent_id` in chat options — not a raw LLM model slug.

```python
async with AsyncCominty() as client:
    agents = await client.agents.list()
    for agent in agents:
        print(agent.name, agent.id, agent.mode)
```

`GET /agents` uses the **Clerk session JWT** (`COMINTY_SESSION_TOKEN`), not the chat API access token.
Match the API environment to your Clerk issuer (dev JWT → `COMINTY_ENVIRONMENT=dev`).
The SDK auto-fills `COMINTY_ORG_ID` / `COMINTY_USER_ID` from the JWT when omitted.

```bash
export COMINTY_SESSION_TOKEN="<JWT from browser DevTools>"
export COMINTY_ENVIRONMENT=dev
uv run python scripts/list_agents.py
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
