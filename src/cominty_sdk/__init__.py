"""Official async Python client for the Cominty managed agent chat API."""

from __future__ import annotations

from . import events
from ._version import __version__
from .client import AsyncCominty
from .exceptions import (
    APIConnectionError,
    APIError,
    AuthError,
    ComintyError,
    ConflictError,
    InvalidParam,
    InvalidParams,
    NotFoundError,
    PermissionError,
    RateLimitError,
    SDKError,
    ServerError,
    StreamInterrupted,
)
from .models.chat import (
    Agent,
    ContentOrigin,
    ConversationFile,
    DisablableTool,
    HumanMessage,
    Message,
    MessageRole,
    MessageStatus,
    Question,
    ShareLink,
    StartChatOptions,
    StartChatParams,
    Thread,
    ThreadSummary,
    UpdateThreadParams,
)
from .streaming import AssistantRun, StartedChat

__all__ = [
    "__version__",
    "AsyncCominty",
    "AssistantRun",
    "StartedChat",
    "events",
    # exceptions
    "ComintyError",
    "APIError",
    "AuthError",
    "PermissionError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
    "APIConnectionError",
    "StreamInterrupted",
    "SDKError",
    "InvalidParam",
    "InvalidParams",
    # models
    "Agent",
    "ContentOrigin",
    "ConversationFile",
    "DisablableTool",
    "HumanMessage",
    "Message",
    "MessageRole",
    "MessageStatus",
    "Question",
    "ShareLink",
    "StartChatOptions",
    "StartChatParams",
    "Thread",
    "ThreadSummary",
    "UpdateThreadParams",
]
