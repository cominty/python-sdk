from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from . import events
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
    SERVER_DEFAULT,
    Agent,
    ContentOrigin,
    ConversationFile,
    DisablableTool,
    HumanMessage,
    MaxSteps,
    Message,
    MessageRole,
    MessageStatus,
    Question,
    ShareLink,
    StartChatOptions,
    StartChatParams,
    Thread,
    ThreadInception,
    ThreadSummary,
    UpdateThreadParams,
)
from .models.memory import (
    MemoryFileCreate,
    MemoryFileOut,
    MemoryFileSummaryOut,
    MemoryFileUpdate,
)
from .streaming import AssistantRun, StartedChat

try:
    __version__ = version("cominty-sdk")
except PackageNotFoundError:
    __version__ = "unknown"

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
    "MaxSteps",
    "Message",
    "MessageRole",
    "MessageStatus",
    "Question",
    "SERVER_DEFAULT",
    "ShareLink",
    "StartChatOptions",
    "StartChatParams",
    "Thread",
    "ThreadInception",
    "ThreadSummary",
    "UpdateThreadParams",
    "MemoryFileCreate",
    "MemoryFileOut",
    "MemoryFileSummaryOut",
    "MemoryFileUpdate",
]
