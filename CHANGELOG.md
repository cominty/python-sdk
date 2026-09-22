# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `client.memory`: full async CRUD for per-user memory files: `list()`,
  `create()`, `get()`, `update()`, `delete()` (`GET/POST /memory`,
  `GET/PUT/DELETE /memory/file`). New models `MemoryFileCreate`,
  `MemoryFileUpdate`, `MemoryFileOut`, `MemoryFileSummaryOut`. `update()` is a
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
- `uv run invoke release --patch|--minor|--major|--version X.Y.Z`: a dev-only
  task that bumps `pyproject.toml`, regenerates `uv.lock`, runs the lint/
  type-check/test/build gate, then creates one release commit and one
  annotated `vX.Y.Z` tag. Never pushes or creates the GitHub Release; prints
  the exact next commands instead. See `AGENTS.md` §12.3.

### Changed
- `__version__` is now resolved at runtime from installed package metadata
  (`importlib.metadata.version("cominty-sdk")`) instead of the removed
  `src/cominty_sdk/_version.py`. Falls back to `"unknown"` when the package
  isn't installed (e.g. a raw source checkout). The single source of truth
  for the version is now `pyproject.toml`'s `[project] version`.

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