# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Capabilities. `chat.start(..., thread_capabilities=AgentCapabilities(...))` overrides some
  of the agent's capabilities for the thread, frozen for its lifetime (not accepted on
  `chat.send`). `message_scope=MessageScope(...)` on `start` and `send` turns a
  capability on or off, or narrows its allowlist, for one message. Filterable capabilities
  (`indexed_documents`, `mcp`, `skills`) take a bare activation or a policy
  (`IndexedDocumentsPolicy`, `McpPolicy`, `SkillsPolicy`) whose filters default to the new
  `ALL` (`"*"`, no restriction); `None`, `[]` and `"*"` inside a list raise `InvalidParams`.
  New exports: `ALL`, `AgentCapabilities`, `MessageScope`, `IndexedDocumentsFilter`,
  `IndexedDocumentsPolicy`, `McpPolicy`, `SkillsPolicy`, `Activation`.
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
- BREAKING: `source_ids`, `document_ids` and `disabled_tools` on `chat.start` / `chat.send`,
  plus `DisablableTool`, `HumanMessage.source_ids/document_ids/disabled_tools`. Migrate to
  `message_scope`:
  `disabled_tools=["web"]` -> `MessageScope(web=False)`;
  `"company_documents"` -> `indexed_documents=False`; `"mcp:*"` -> `mcp=False`;
  `"mcp:notion"` -> `mcp=[<connections to keep>]`;
  `source_ids=[101]` -> `indexed_documents=IndexedDocumentsFilter(source_ids=[101])`;
  `document_ids=[...]` -> `IndexedDocumentsFilter(document_ids=[...])`.
- `client.memory`'s methods no longer send `user_id`: memory files are
  scoped by `namespace`, not by the end user.
- `ThreadSummary.agent` (and `Thread.agent`, since `Thread` extends it): the API no longer
  returns an agent on the thread itself. Use `Message.agent` on each message instead.

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
> `importlib.metadata` ships under [Unreleased] above.

### Docs
- Setup now points to [platform.cominty.ai](https://platform.cominty.ai) for
  creating API keys and finding agent ids.

## [0.1.0]

### Added
- Initial async client `AsyncCominty` covering threads, chat, messages
  (send/stream/export/cancel), files (upload/download), usage, and API tokens.

[Unreleased]: https://github.com/cominty/python-sdk/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/cominty/python-sdk/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/cominty/python-sdk/releases/tag/v0.1.0