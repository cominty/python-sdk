# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `agents.list()` (`GET /agents`) with API-token fallback (`list_discovered()`).
- `py.typed` marker so downstream type checkers see the SDK's types.
- Tag-driven release pipeline publishing to TestPyPI (pre-release tags) and
  PyPI (final tags) via Trusted Publishing (OIDC).

### Changed
- `__version__` is now sourced from package metadata instead of being hardcoded.
- Auth: auto-fill `org_id` / `user_id` from a Clerk session JWT; fixed API-token
  authentication mode.

## [0.1.0]

### Added
- Initial async client `AsyncCominty` covering threads, chat, messages
  (send/stream/export/cancel), files (upload/download), usage, and API tokens.

[Unreleased]: https://github.com/cominty/python-sdk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cominty/python-sdk/releases/tag/v0.1.0
