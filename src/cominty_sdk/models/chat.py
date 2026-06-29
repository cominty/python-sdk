"""Request and response models for the chat resource.

Request models are strict (``strict=True, extra="forbid"``) so caller mistakes
surface immediately. Response models are lenient (``extra="ignore"``) so the SDK
tolerates additive API changes without a release.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

__all__ = [
    # enums / aliases
    "MessageRole",
    "MessageStatus",
    "ContentOrigin",
    "DisablableTool",
    "UserId",
    "DISABLE_MCP_PREFIX",
    "DISABLE_ALL_MCP",
    # request models
    "HumanMessage",
    "StartChatOptions",
    "StartChatParams",
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
class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"


class MessageStatus(StrEnum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class ContentOrigin(StrEnum):
    user = "user"
    agent = "agent"


# Cominty user ids are Clerk-issued: "user_" + a base58-ish token,
# e.g. "user_31HPTBuBvX20xlQNAbvxjOxPbKB".
_USER_ID_PATTERN = re.compile(r"^user_[A-Za-z0-9]{20,}$")


def _validate_user_id(value: str) -> str:
    if not _USER_ID_PATTERN.match(value):
        raise ValueError(
            "expected a Cominty user id like 'user_xxxxxxxxxxxxxxxxxPbKB' "
            "('user_' prefix + alphanumeric token). Find yours at "
            "platform.cominty.com -> avatar (top right) -> Profile"
        )
    return value


type UserId = Annotated[str, AfterValidator(_validate_user_id)]
"""A Cominty (Clerk) user id, pattern-checked before any request is sent so a
typo'd or malformed id fails locally instead of as a server 400/404."""


DISABLE_MCP_PREFIX = "mcp:"
"""Prefix for disabling a single MCP server, e.g. ``"mcp:slack"``."""
# TODO(mcp): how is this used ?
DISABLE_ALL_MCP = f"{DISABLE_MCP_PREFIX}*"
"""Wildcard token that disables every connected MCP server at once."""

# TODO: include the wildcard * for disable all, can it be with the other literals?
type DisablableTool = (
    Literal["web", "company_documents"]
    | Annotated[str, StringConstraints(pattern=rf"^{DISABLE_MCP_PREFIX}.+")]
)
"""A tool the agent may disable: the built-in ``"web"`` / ``"company_documents"``,
or an MCP token ``"mcp:<server>"`` (``"mcp:*"`` for all). The MCP arm is regex-
validated, so arbitrary strings are rejected rather than silently sent."""


# --------------------------------------------------------------------------- #
# Request models  (strict — reject unknown fields, no coercion)
# --------------------------------------------------------------------------- #
class HumanMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    content: str = Field(max_length=_CONTENT_MAX_LENGTH)
    file_ids: list[str] | None = Field(default=None, max_length=_MAX_FILES)
    source_ids: list[int] | None = None
    document_ids: list[str] | None = None
    disabled_tools: list[DisablableTool] | None = None


class StartChatOptions(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    agent_id: str
    user_id: UserId
    """Required: the API-token endpoint rejects a missing ``user_id`` with 400."""


class StartChatParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    message: HumanMessage
    options: StartChatOptions
    name: str | None = None


# --------------------------------------------------------------------------- #
# Response models  (lenient — ignore unknown fields)
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
    questions: list[Question] | None
    live: bool
    status: MessageStatus
    events: list[dict[str, Any]] | None
    """Raw persisted event log (not the typed stream events)."""
    structured_output: dict[str, Any] | None
    files: list[ConversationFile]


class ThreadSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    created_at: datetime
    live: bool
    agent: Agent
    starred: bool
    project_id: str | None = None


class Thread(ThreadSummary):
    messages: list[Message]
