"""Cominty SDK — async Python client for the managed agent chat API."""

from cominty_sdk.client import AsyncCominty
from cominty_sdk.config import DEFAULT_AGENT_ID, DEFAULT_API_URL, ComintyEnvironment
from cominty_sdk.exceptions import (
    AuthenticationError,
    ComintyAPIError,
    ComintyError,
    ComintyServerShuttingDownError,
    ComintyTimeoutError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from cominty_sdk.models.files import ConversationFileOut
from cominty_sdk.models.messages import (
    DocumentCitation,
    HumanMessage,
    MessageOut,
    Question,
    WebCitation,
)
from cominty_sdk.models.threads import ThreadOut, ThreadSummaryOut
from cominty_sdk.models.usage import UsageReport

__all__ = [
    "AsyncCominty",
    "AuthenticationError",
    "ComintyAPIError",
    "ComintyEnvironment",
    "DEFAULT_AGENT_ID",
    "DEFAULT_API_URL",
    "ComintyError",
    "ComintyServerShuttingDownError",
    "ComintyTimeoutError",
    "ConversationFileOut",
    "DocumentCitation",
    "HumanMessage",
    "MessageOut",
    "NotFoundError",
    "Question",
    "RateLimitError",
    "ServerError",
    "ThreadOut",
    "ThreadSummaryOut",
    "UsageReport",
    "ValidationError",
    "WebCitation",
]

__version__ = "0.1.0"
