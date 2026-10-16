# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `client.chat.cancel(message_id)`: stops an assistant message that is still being generated
  (`POST /chat/messages/{id}/cancel`) and returns the `Message` with `status` set to
  `cancelled`. It is not idempotent: a message that is no longer running (finished, failed,
  already cancelled, or a user message) raises `APIError` (400), and an unknown message raises
  `NotFoundError`. See `examples/12_cancel_message.py`.
- `client.chat.export(message_id, format="pdf" | "docx")`: renders a message to a document
  (`GET /chat/messages/{id}/export`) and returns the raw bytes. The server sends no file name.
  Any other `format` raises `InvalidParams` locally; a message without content (for instance
  one still running) raises `APIError` (400). New public type `ExportFormat`. See
  `examples/13_export_message.py`.

## [1.0.0] - 2026-10-15

### Added
- Capabilities. `chat.start(..., thread_capabilities=AgentCapabilities(...))` overrides some
  of the agent's capabilities for the thread, frozen for its lifetime (not accepted on
  `chat.send`). `message_scope=MessageScope(...)` on `start` and `send` turns a
  capability on or off, or narrows its allowlist, for one message (sent as `message.scope`).
  Every capability is an explicit object with a required activation:
  `WebCapability`, `IndexedDocumentsCapability`, `McpCapability`, `SkillsCapability`,
  `ImageGenerationCapability`, `VideoGenerationCapability`, `MusicGenerationCapability`
  (`"always"`, `"on_request"` or `"never"`; skills take `"always"` or `"never"`). Message
  scopes are `WebScope`, `IndexedDocumentsScope`, `McpScope`, `ImageGenerationScope`,
  `VideoGenerationScope`, `MusicGenerationScope`, each with a required `enabled`. There are no
  shortcuts such as `web=True` or `web="on_request"`. Filters (`source_ids`, `document_ids`,
  `connections`, `include`) default to the new `ALL` (`"*"`, no restriction), which can also be
  passed explicitly; `None`, `[]` and `"*"` inside a list raise `InvalidParams`, and so does a
  filter combined with `"never"` or `enabled=False`.
- `MemoryCapability(activation="always", namespace=...)` / `MemoryCapability(activation="never")`
  in `AgentCapabilities(memory=...)`: sets the thread's memory bag (1 to 128 characters), or
  runs it without memory. Without a `memory` entry, the thread uses the agent's namespace, or
  no memory if the agent has none.
- New exports: `ALL`, `AgentCapabilities`, `MessageScope`, the `*Capability` and `*Scope`
  classes above, and `MemoryCapability`.
- `examples/11_capabilities.py`.

### Removed
- BREAKING: `source_ids`, `document_ids` and `disabled_tools` on `chat.start` / `chat.send`,
  plus `DisablableTool`, `HumanMessage.source_ids/document_ids/disabled_tools`. Migrate to
  `message_scope`:
  `disabled_tools=["web"]` -> `MessageScope(web=WebScope(enabled=False))`;
  `"company_documents"` -> `indexed_documents=IndexedDocumentsScope(enabled=False)`;
  `"mcp:*"` -> `mcp=McpScope(enabled=False)`;
  `"mcp:notion"` -> `mcp=McpScope(enabled=True, connections=[<connections to keep>])`;
  `source_ids=[101]` -> `indexed_documents=IndexedDocumentsScope(enabled=True, source_ids=[101])`;
  `document_ids=[...]` -> `IndexedDocumentsScope(enabled=True, document_ids=[...])`.
- BREAKING: `memory_namespace` on `chat.start`, and `StartChatOptions.memory_namespace`. The
  memory bag is now a capability, like the others. Migrate:
  `memory_namespace="support-bot"` ->
  `thread_capabilities=AgentCapabilities(memory=MemoryCapability(activation="always", namespace="support-bot"))`.

## [0.5.0] - 2026-10-07

### Added
- `chat.start(..., max_steps=...)` and `chat.send(..., max_steps=...)`: cap the
  agent's tool rounds for that one message (integer `>= 1`). The cap is per
  message, not per thread: a follow-up that leaves it unset runs with the server
  default (60 today, subject to change). Leaving it unset, or passing the new
  `SERVER_DEFAULT` sentinel, omits the field from the request. There is no
  "unlimited": `None`, integers below 1, floats, bools, and strings raise
  `InvalidParams` locally. Reaching the cap is not an error: the reply ends with
  `status="success"` and asks whether to continue, with no flag to detect it.
  New exports `SERVER_DEFAULT` and the `MaxSteps` alias. See
  `examples/10_max_steps.py`. Routines (which also accept `max_steps` server-side)
  are not exposed by this SDK.
- `Message.agent`: the agent that handled that message (`Agent | Literal["ARCHIVED"] | None`;
  `"ARCHIVED"` if the original agent has since been deleted). `Message.error_code`: set when
  the message failed for a known reason (e.g. `"budget_exhausted"`), typed as a plain `str`
  since the API adds new codes over time. `ThreadSummary.inception`: `"conversational"` or
  `"routine"`, exposed as the new `ThreadInception` enum.
- `client.memory`: full async CRUD for memory files, scoped to a
  caller-chosen **namespace** (a bag name, at most 128 characters, never
  trimmed): `list(namespace=None)`, `list_namespaces()`, `create()`, `get()`,
  `update()`, `delete()` (`GET/POST /memory`, `GET /memory/namespaces`,
  `GET/PUT/DELETE /memory/file`). `namespace` is required on `create()`,
  `get()`, `update()`, and `delete()`; optional on `list()` (omit it to list
  every bag). There is no call to create a namespace: the first `create()`
  against a new name brings that bag into existence. New models
  `MemoryFileCreate`, `MemoryFileUpdate`, `MemoryFileOut`,
  `MemoryFileSummaryOut` (the last two now carry `namespace`). `update()` is a
  partial update: pass only the fields you want to change; the API does not
  support clearing `content`/`purpose` once set (a `null` is silently ignored
  server-side), so passing `content=None`/`purpose=None` raises
  `InvalidParams` locally instead of sending a request that looks like it
  succeeded but did nothing. `path` may have at most one folder segment
  (`"folder/file.md"`, not `"a/b/file.md"`): checked locally, also raising
  `InvalidParams`, since the API only enforces this after a round trip.
  `content` may be an empty string (no minimum length). Guards against
  concurrent writes via an opaque `version` token, raising `ConflictError`
  (409) on a stale value: a malformed `version` raises `APIError` (422)
  instead. `delete()` is not idempotent: deleting an already-deleted path
  raises `NotFoundError` (404). See `examples/09_memory.py`.
- `chat.start(..., memory_namespace=...)`: attaches the new thread to a
  memory bag, frozen for the thread's lifetime. Omit it to run with no
  memory tools, unless the agent has its own namespace set. Not accepted on
  `chat.send`: a follow-up cannot change a thread's namespace.
- `uv run invoke code.format|code.check|code.test|code.all`: the day-to-day
  dev loop (ruff format, ruff check + pyright, pytest with the same
  `--cov-fail-under=100` floor as CI, or all three in order).
- `uv run invoke release --patch|--minor|--major|--version X.Y.Z`: a dev-only
  task that bumps `pyproject.toml`, regenerates `uv.lock`, runs the lint/
  type-check/test/build gate, then creates one release commit and one
  annotated `vX.Y.Z` tag. Prints a plan and asks for confirmation before
  writing any file, and again before committing and tagging (`--yes` skips
  both). Never pushes or creates the GitHub Release; prints the exact next
  commands instead. See `AGENTS.md` §12.4.

### Changed
- `__version__` is now resolved at runtime from installed package metadata
  (`importlib.metadata.version("cominty-sdk")`) instead of the removed
  `src/cominty_sdk/_version.py`. Falls back to `"unknown"` when the package
  isn't installed (e.g. a raw source checkout). The single source of truth
  for the version is now `pyproject.toml`'s `[project] version`.
- `uv run invoke clean` now also removes tool caches (`__pycache__`,
  `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.pyright`, `htmlcov`,
  `.coverage*`), not just build artifacts.

### Removed
- `ThreadSummary.agent` (and `Thread.agent`, since `Thread` extends it): the API no longer
  returns an agent on the thread itself. Use `Message.agent` on each message instead.

## [0.4.0] - 2026-06-30

### Added
- `client.threads`: `list()`, `get()`, `update()` and `archive()` to manage
  existing threads. New `UpdateThreadParams` export.
- `chat.send(thread_id, message=..., agent_id=...)`: send a follow-up message
  in an existing thread, for example to answer an agent's question.
- `StartedChat.questions()` / `AssistantRun.questions()`: the clarifying
  questions the agent is asking, if any.
- `AsyncCominty(user_id=...)` and `client.user_id`. The end-user id can also be
  set with `COMINTY_USER_ID`.
- `RateLimitError.scope` (`"organization"`, `"user"` or `"concurrency"`) and
  `RateLimitError.retry_after`, with a clearer error message saying which limit
  was hit.
- Runnable scripts in `examples/` (streaming, follow-ups, threads, custom agent,
  MCP).

### Changed
- **Breaking:** `user_id` is now required on the client (argument or
  `COMINTY_USER_ID`) and is no longer a parameter of `chat.start()`.
- Fixed `RateLimitError` handling of 429 responses and adjusted response models
  to the shapes the API actually returns.

## [0.3.0] - 2026-06-29

### Changed
- **Breaking:** v1 redesign with a new module layout. `client.chat.start()`
  returns a `StartedChat` handle and `client.chat.stream()` an `AssistantRun`,
  both streamable. Added the `events` module and the typed exception hierarchy
  (`InvalidParams`, `StreamInterrupted`, and so on).
- **Breaking:** the minimum Python version is lowered from 3.11 to 3.9.
- Toolchain moved to pyright (instead of mypy), `invoke` tasks, and the
  `AGENTS.md` coding guide.

### Removed
- The `agents`, `files`, `messages`, `usage` and `api_tokens` resources of the
  0.1/0.2 client, as well as the retry helper.

### CI
- PyPI release workflow (Trusted Publishing) and `invoke` build/publish tasks.

## [0.2.0] - 2026-06-19

### Added
- `agents.create()` (`POST /agents`) and `agents.update()` (`PUT /agents/{id}`)
  to manage org agents with an API key, no Clerk session required.

## [0.1.1] - 2026-06-18

### Added
- `agents.list()` (`GET /agents`) with fallback discovery (`list_discovered()`).
- `py.typed` marker so downstream type checkers see the SDK's types.
- Tag-driven release pipeline publishing to TestPyPI (pre-release tags) and
  PyPI (final tags) via Trusted Publishing (OIDC).

### Changed
- Fixed API-key authentication mode and end-user id handling.

> **Correction (2026-07-24):** an earlier revision of this entry claimed
> `__version__` was already sourced from package metadata as of 0.1.1. That
> was inaccurate: the SDK still hard-coded the version via
> `src/cominty_sdk/_version.py` at the time. The actual switch to
> `importlib.metadata` ships in 0.5.0 above.

### Docs
- Setup now points to [platform.cominty.ai](https://platform.cominty.ai) for
  creating API keys and finding agent ids.

## [0.1.0]

### Added
- Initial async client `AsyncCominty` covering threads, chat, messages
  (send/stream/export/cancel), files (upload/download), usage, and API tokens.

[Unreleased]: https://github.com/cominty/python-sdk/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/cominty/python-sdk/compare/v0.5.0...v1.0.0
[0.5.0]: https://github.com/cominty/python-sdk/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/cominty/python-sdk/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/cominty/python-sdk/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/cominty/python-sdk/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/cominty/python-sdk/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/cominty/python-sdk/releases/tag/v0.1.0