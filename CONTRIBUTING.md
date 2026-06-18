# Contributing

Thanks for contributing to the Cominty Python SDK!

## Development setup

This project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras --dev
```

## Checks

All three must pass before opening a PR (CI runs them on Python 3.11–3.13):

```bash
uv run ruff check .   # lint + import order
uv run mypy           # strict type checking
uv run pytest         # unit tests
```

Integration tests are opt-in and require live credentials:

```bash
cp .env.example .env  # fill COMINTY_API_KEY / COMINTY_USER_ID
uv run pytest -m integration
```

## Pull requests

- Keep changes focused; add or update tests for behavior changes.
- Update `CHANGELOG.md` under `## [Unreleased]`.
- Public API changes should keep type hints accurate (the package ships `py.typed`).

## Releasing (maintainers)

Releases are driven by git tags — see the "Releasing" section in the
[README](README.md). In short: bump `version` in `pyproject.toml`, push a
pre-release tag (`vX.Y.Zrc1`) to validate on TestPyPI, then a final tag
(`vX.Y.Z`) to publish to PyPI.
