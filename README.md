# Cominty Python SDK

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

- `dev`: `https://api.dev.cominty.com`
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

The API returns JSONL events on the stream endpoint:

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

CI publishing to PyPI is **disabled for now** — pending Trusted Publishing (OIDC) setup.

### Local development (current workflow)

Install in editable mode and run tests locally:

```bash
uv sync --all-extras --dev
uv run pytest
```

### Manual publish (when needed)

```bash
uv build
uv publish --username __token__
```

### CI on release tags

Pushing a semver tag (`v*`) runs tests, verifies the tag matches `pyproject.toml`, and builds the package — without publishing yet.

```bash
git tag v0.2.0
git push origin v0.2.0
```

## License

MIT
