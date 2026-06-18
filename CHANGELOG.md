# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Public `cominty_sdk.qa` namespace exposing stable QA helpers
  (`is_stream_terminal_event`, cite-tag patterns, tool/citation extractors) so
  external test suites no longer import the private `_qa` module.

## [0.1.1] - 2026-06-18

### Added
- `agents.list()` (`GET /agents`) with fallback discovery (`list_discovered()`).
- `py.typed` marker so downstream type checkers see the SDK's types.
- Tag-driven release pipeline publishing to TestPyPI (pre-release tags) and
  PyPI (final tags) via Trusted Publishing (OIDC).

### Changed
- `__version__` is now sourced from package metadata instead of being hardcoded.
- Fixed API-key authentication mode and end-user id handling.

### Docs
- Setup now points to [platform.cominty.com](https://platform.cominty.com) for
  creating API keys and finding agent ids.

## [0.1.0]

### Added
- Initial async client `AsyncCominty` covering threads, chat, messages
  (send/stream/export/cancel), files (upload/download), usage, and API tokens.

[Unreleased]: https://github.com/cominty/python-sdk/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/cominty/python-sdk/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/cominty/python-sdk/releases/tag/v0.1.0
