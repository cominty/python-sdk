"""Official async Python client for the Cominty managed agent chat API."""

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
from .models.agents import (
    CreateAgentParams,
    CustomAgent,
    CustomAgentSummary,
    LLMModelSummary,
    SetAgentModelsParams,
    UpdateAgentParams,
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
    "CreateAgentParams",
    "CustomAgent",
    "CustomAgentSummary",
    "DisablableTool",
    "HumanMessage",
    "LLMModelSummary",
    "Message",
    "MessageRole",
    "MessageStatus",
    "Question",
    "SetAgentModelsParams",
    "ShareLink",
    "StartChatOptions",
    "StartChatParams",
    "Thread",
    "ThreadSummary",
    "UpdateAgentParams",
    "UpdateThreadParams",
]
