"""Single source of truth for the package version.

This file is read both at runtime (re-exported as ``cominty_sdk.__version__``)
and at build time by hatchling (see ``[tool.hatch.version]`` in pyproject.toml).
Bump it via the invoke tasks: ``invoke bump --part=patch|minor|major``.
"""

from __future__ import annotations

__version__ = "0.3.0"
