"""Pydantic models for chat API messages."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cominty_sdk._qa import (
    extract_cite_tags,
    extract_tool_names,
    parse_document_citations,
    parse_web_citations,
)


class Question(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str
    options: list[str] = Field(default_factory=list)


class HumanMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., max_length=30000)
    file_ids: list[str] | None = None
    source_ids: list[int] | None = None
    document_ids: list[str] | None = None
    disabled_tools: list[str] | None = None

    @field_validator("disabled_tools")
    @classmethod
    def validate_disabled_tools(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        allowed = {"web", "company_documents"}
        for tool in value:
            if tool not in allowed and not tool.startswith("mcp:"):
                raise ValueError(
                    f"Invalid disabled tool {tool!r}. "
                    'Expected "web", "company_documents", or "mcp:<name>".'
                )
        return value


class DocumentCitation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str
    pages: str
    name: str


class WebCitation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str


class MessageOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    thread_id: UUID
    role: str
    content: str
    questions: list[Question] | None = None
    live: bool
    status: str
    events: list[dict[str, Any]] | None = None
    structured_output: dict[str, Any] | None = None
    files: list[Any] = Field(default_factory=list)

    @property
    def tool_names(self) -> list[str]:
        """Tool names invoked during this message, extracted from events."""
        return extract_tool_names(self.events)

    @property
    def cite_tags(self) -> list[str]:
        """Raw <cite .../> tags present in the response content."""
        return extract_cite_tags(self.content)

    @property
    def document_citations(self) -> list[DocumentCitation]:
        """Parsed document citations from content."""
        return [DocumentCitation.model_validate(c) for c in parse_document_citations(self.content)]

    @property
    def web_citations(self) -> list[WebCitation]:
        """Parsed web citations from content."""
        return [WebCitation.model_validate(c) for c in parse_web_citations(self.content)]

    def is_terminal(self) -> bool:
        """Return True when the message has finished processing."""
        from cominty_sdk.config import NON_TERMINAL_STATUSES

        return not self.live and self.status.lower() not in NON_TERMINAL_STATUSES


class ChatOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str


class StartChatOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    user_id: str | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: HumanMessage
    options: ChatOptions


class StartChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: HumanMessage
    options: StartChatOptions
    name: str | None = None


class PartialMessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    __server_is_shutting_down: Literal[True]
    partial: MessageOut


def parse_message_response(data: dict[str, Any]) -> MessageOut:
    """Parse a message response, handling partial shutdown payloads."""
    from cominty_sdk.exceptions import ComintyServerShuttingDownError

    if data.get("__server_is_shutting_down"):
        partial = PartialMessageResponse.model_validate(data)
        raise ComintyServerShuttingDownError(
            "Server is shutting down; partial message returned.",
            body=partial.partial.model_dump(),
        )
    return MessageOut.model_validate(data)
