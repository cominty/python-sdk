from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from typing_extensions import TypeAlias

from .capabilities import AgentCapabilities, MessageScope

__all__ = [
    # enums / aliases
    "MessageRole",
    "MessageStatus",
    "ContentOrigin",
    "ThreadInception",
    "UserId",
    "validate_user_id",
    "SERVER_DEFAULT",
    "MaxSteps",
    # request models
    "HumanMessage",
    "StartChatOptions",
    "StartChatParams",
    "UpdateThreadParams",
    # response models
    "Question",
    "Agent",
    "ShareLink",
    "ConversationFile",
    "Message",
    "ThreadSummary",
    "Thread",
]

# Max content length enforced server-side (settings.CHAT_MESSAGE_MAX_LENGTH).
_CONTENT_MAX_LENGTH = 30_000
# Max files per message (settings.CHAT_MESSAGE_MAX_FILES).
_MAX_FILES = 5


# --------------------------------------------------------------------------- #
# Enums & aliases
# --------------------------------------------------------------------------- #
class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class MessageStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class ContentOrigin(str, Enum):
    user = "user"
    agent = "agent"


class ThreadInception(str, Enum):
    conversational = "conversational"
    routine = "routine"


# Cominty user ids are Clerk-issued: "user_" + a base58-ish token,
# e.g. "user_31HPTBuBvX20xlQNAbvxjOxPbKB".
_USER_ID_PATTERN = re.compile(r"^user_[A-Za-z0-9]{20,}$")


def validate_user_id(value: str) -> str:
    if not _USER_ID_PATTERN.match(value):
        raise ValueError(
            "expected a Cominty user id like 'user_xxxxxxxxxxxxxxxxxPbKB' "
            "('user_' prefix + alphanumeric token). Find yours at "
            "platform.cominty.ai -> avatar (top right) -> Profile"
        )
    return value


UserId: TypeAlias = Annotated[str, AfterValidator(validate_user_id)]
"""A Cominty (Clerk) user id, pattern-checked before any request is sent so a
typo'd or malformed id fails locally instead of as a server 400/404."""


# Single-member enum: the one sentinel idiom pyright narrows with `is`.
# typing_extensions.sentinel is not understood by pyright's bundled typeshed.
class _ServerDefaultType(Enum):
    SERVER_DEFAULT = "SERVER_DEFAULT"


SERVER_DEFAULT = _ServerDefaultType.SERVER_DEFAULT
"""Default of ``max_steps``: the field is left out of the request and the server
applies its own default (60 today, subject to change)."""

MaxSteps: TypeAlias = Union[int, Literal[_ServerDefaultType.SERVER_DEFAULT]]
"""A tool-round cap: an integer ``>= 1``, or ``SERVER_DEFAULT`` to omit it."""


# --------------------------------------------------------------------------- #
# Request models  (strict: reject unknown fields, no coercion)
# --------------------------------------------------------------------------- #
class HumanMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    content: str = Field(max_length=_CONTENT_MAX_LENGTH)
    file_ids: list[str] | None = Field(default=None, max_length=_MAX_FILES)
    scope: MessageScope | None = None


class StartChatOptions(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    agent_id: str
    user_id: UserId
    """Required: the API-token endpoint rejects a missing ``user_id`` with 400."""
    capabilities: AgentCapabilities | None = None
    """Thread-level override, frozen once the thread starts. ``start`` only."""
    max_steps: int | None = Field(default=None, ge=1)
    """Tool-round cap for this message only. Omit to let the server apply its
    default. ``None`` is the "omitted" state, never a value: an explicit ``None``
    is rejected, since the API has no "unlimited" and answers ``null`` with a 422."""

    @field_validator("max_steps", mode="before")
    @classmethod
    def _reject_explicit_none(cls, value: object) -> object:
        # Validators skip defaults, so this only fires on an explicit None.
        if value is None:
            raise ValueError("expected an integer >= 1, or leave it unset for the server default")
        return value


class StartChatParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    message: HumanMessage
    options: StartChatOptions
    name: str | None = None


class UpdateThreadParams(BaseModel):
    """Mutable thread fields. Only the fields you pass are sent (``exclude_none``),
    so updates are partial: omitted fields keep their current value."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str | None = None
    starred: bool | None = None


# --------------------------------------------------------------------------- #
# Response models  (lenient: ignore unknown fields)
# --------------------------------------------------------------------------- #
class Question(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str
    options: list[str] = Field(default_factory=list)


class Agent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class ShareLink(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: datetime
    last_accessed_at: datetime | None
    access_count: int
    revoked: bool
    expires_at: datetime | None
    expired: bool
    protected: bool
    url: str


class ConversationFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    size: int
    mimetype: str
    origin: ContentOrigin
    share_links: list[ShareLink]
    url: str


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    thread_id: UUID
    role: MessageRole
    content: str
    error_code: str | None
    """Set when the message failed for a known reason (e.g. ``"budget_exhausted"``).
    Left as ``str`` rather than a closed enum since the API adds new codes
    over time and this is a lenient response model."""
    questions: list[Question] | None
    live: bool
    status: MessageStatus
    events: list[dict[str, Any]] | None
    """Raw persisted event log (not the typed stream events)."""
    structured_output: dict[str, Any] | None
    files: list[ConversationFile]
    agent: Agent | Literal["ARCHIVED"] | None
    """The agent that handled this message. ``"ARCHIVED"`` if the original
    agent has since been deleted; ``None`` before one is assigned."""


class ThreadSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    created_at: datetime
    live: bool
    starred: bool
    inception: ThreadInception
    project_id: str | None = None


class Thread(ThreadSummary):
    messages: list[Message]
