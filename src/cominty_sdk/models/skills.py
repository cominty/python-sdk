from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import Scope

__all__ = [
    "SkillSource",
    # request models
    "CreateSkillParams",
    "UpdateSkillParams",
    # response models
    "SkillFrontmatter",
    "SkillOut",
]

# DISPLAY_NAME_MAX_LENGTH of the hosted API.
_DISPLAY_NAME_MAX_LENGTH = 100


class SkillSource(str, Enum):
    cominty = "cominty"
    """Built in, shared by every organization, read-only."""
    custom = "custom"
    """Uploaded by the organization."""


# --------------------------------------------------------------------------- #
# Request models  (strict: reject unknown fields, no coercion)
# --------------------------------------------------------------------------- #
class CreateSkillParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    display_name: str = Field(min_length=1, max_length=_DISPLAY_NAME_MAX_LENGTH)
    scope: Scope = "private"


class UpdateSkillParams(BaseModel):
    """Partial update body for ``PUT /skills/{id}``: only the fields you pass are sent."""

    model_config = ConfigDict(strict=True, extra="forbid")

    display_name: str | None = Field(
        default=None, min_length=1, max_length=_DISPLAY_NAME_MAX_LENGTH
    )
    active: bool | None = None
    scope: Scope | None = None

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> UpdateSkillParams:
        if all(getattr(self, name) is None for name in ("display_name", "active", "scope")):
            raise ValueError("at least one of `display_name`, `active` or `scope` must be provided")
        return self


# --------------------------------------------------------------------------- #
# Response models  (lenient: ignore unknown fields)
# --------------------------------------------------------------------------- #
class SkillFrontmatter(BaseModel):
    """The YAML frontmatter of the skill's ``SKILL.md`` (agentskills.io specification)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str
    license: str | None
    compatibility: str | None
    metadata: dict[str, str]
    allowed_tools: list[str]


class SkillOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: datetime
    updated_at: datetime
    """When the default version was last uploaded."""
    display_name: str
    active: bool
    scope: Scope | None
    """``None`` for built-in skills."""
    source: SkillSource
    frontmatter: SkillFrontmatter
