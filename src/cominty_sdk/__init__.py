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
    SourceSyncFailed,
    StreamInterrupted,
)
from .models.agents import AgentOut, AgentSummaryOut, LLMModelSummaryOut
from .models.capabilities import (
    ALL,
    AgentCapabilities,
    ImageGenerationCapability,
    ImageGenerationScope,
    IndexedDocumentsCapability,
    IndexedDocumentsScope,
    McpCapability,
    McpScope,
    MemoryCapability,
    MessageScope,
    MusicGenerationCapability,
    MusicGenerationScope,
    SkillsCapability,
    VideoGenerationCapability,
    VideoGenerationScope,
    WebCapability,
    WebScope,
)
from .models.chat import (
    SERVER_DEFAULT,
    Agent,
    ContentOrigin,
    ConversationFile,
    ExportFormat,
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
from .models.common import Scope
from .models.documents import DocumentMetadataOut
from .models.mcp import McpServerOut
from .models.memory import (
    MemoryFileCreate,
    MemoryFileOut,
    MemoryFileSummaryOut,
    MemoryFileUpdate,
)
from .models.skills import SkillFrontmatter, SkillOut, SkillSource
from .models.sources import FileOut, SourceOut, SourceStatus, SourceStore
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
    "SourceSyncFailed",
    "SDKError",
    "InvalidParam",
    "InvalidParams",
    # models
    "AgentOut",
    "AgentSummaryOut",
    "LLMModelSummaryOut",
    "ALL",
    "AgentCapabilities",
    "ImageGenerationCapability",
    "ImageGenerationScope",
    "IndexedDocumentsCapability",
    "IndexedDocumentsScope",
    "McpCapability",
    "McpScope",
    "MemoryCapability",
    "MessageScope",
    "MusicGenerationCapability",
    "MusicGenerationScope",
    "SkillsCapability",
    "VideoGenerationCapability",
    "VideoGenerationScope",
    "WebCapability",
    "WebScope",
    "Agent",
    "ContentOrigin",
    "ConversationFile",
    "ExportFormat",
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
    "McpServerOut",
    "MemoryFileCreate",
    "MemoryFileOut",
    "MemoryFileSummaryOut",
    "MemoryFileUpdate",
    "Scope",
    "FileOut",
    "SourceOut",
    "SourceStatus",
    "SourceStore",
    "DocumentMetadataOut",
    "SkillFrontmatter",
    "SkillOut",
    "SkillSource",
]
