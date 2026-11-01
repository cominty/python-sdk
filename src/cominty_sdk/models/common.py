from __future__ import annotations

from typing import Literal

from typing_extensions import TypeAlias

__all__ = ["Scope"]

Scope: TypeAlias = Literal["private", "organization"]
"""Who sees a resource: its creator only, or every member of the organization."""
