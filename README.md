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
| `COMINTY_API_KEY` | API key (required) |
| `COMINTY_API_URL` | Override base URL (optional, takes priority) |
| `COMINTY_ENVIRONMENT` | `dev`, `staging`, or `production` (default: `production`) |
| `COMINTY_AGENT_ID` | Default agent ID for chat operations |
| `COMINTY_MAX_RETRIES` | Max retries on transient errors (default: `3`) |
| `COMINTY_TIMEOUT` | Request timeout in seconds (default: `60`) |

Default base URLs are placeholders and can be overridden with `COMINTY_API_URL`:

- `dev`: `https://api.dev.cominty.com`
- `staging`: `https://api.staging.cominty.com`
- `production`: `https://api.cominty.com`

Authentication uses the `x-cominty-token` header.

## Quick start

```python
import asyncio

from cominty_sdk import AsyncCominty, HumanMessage


async def main() -> None:
    async with AsyncCominty() as client:
        thread, reply = await client.chat.start_and_wait(
            HumanMessage(content="What is Cominty?"),
            agent_id="your-agent-id",
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
