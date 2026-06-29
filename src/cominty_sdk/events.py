"""Typed events emitted by ``GET /chat/messages/{message_id}/stream``.

The chat stream is **progress streaming, not token streaming** — there is no
text-delta event. The assistant's reply arrives whole, once, inside the
``result`` event (``data.reply``) and again in the terminal message snapshot.
These models cover the events a client actually receives; the three
server-intercepted names (``execution_failed``, ``cancelled``,
``end_of_stream``) never reach the wire as events — they are converted to a
terminal ``Message`` snapshot by the backend, handled in the stream layer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .models.chat import Question

__all__ = [
    "EventStatus",
    "File",
    "Cost",
    "WaitingForStart",
    "SettingUpSandbox",
    "UploadingFile",
    "LlmStep",
    "IntermediaryUpdate",
    "ToolCall",
    "Result",
    "UnknownEvent",
    "AnyEvent",
    "parse_event",
]

type EventStatus = Literal["running", "success", "error"]


class _EventBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    """Redis stream id, e.g. ``"1718000000000-0"``. Track the last one seen to
    resume via the ``last-event-id`` header on reconnect."""
    correlation_id: int
    at: datetime
    status: EventStatus


# --------------------------------------------------------------------------- #
# Data payloads
# --------------------------------------------------------------------------- #
class File(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    mimetype: str


class Cost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    failed: bool
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    # Wire sends these as strings (Decimal-serialized); pydantic coerces them.
    input_cost: Decimal = Decimal(0)
    output_cost: Decimal = Decimal(0)
    total: Decimal = Decimal(0)


class _UploadingFileData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filename: str


class _LlmData(BaseModel):
    # protected_namespaces=() so the field literally named ``model`` does not
    # collide with pydantic's reserved ``model_*`` namespace.
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    description: str
    model: str


class _IntermediaryUpdateData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str


class _ToolCallData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str
    message: str | None = None
    """Present when ``status == "success"``."""
    error: str | None = None
    """Present when ``status == "error"``."""


class _ResultData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reply: str
    files: list[File] = Field(default_factory=list[File])
    questions: list[Question] | None = None
    metadata: dict[str, Any] | None = None
    """Agent-specific. ``agent.planner`` -> ``{"canvas": str | None}``;
    ``agent.hive`` -> ``None``."""
    cost: Cost


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
class WaitingForStart(_EventBase):
    name: Literal["waiting_for_start"]


class SettingUpSandbox(_EventBase):
    name: Literal["setting_up_sandbox"]


class UploadingFile(_EventBase):
    name: Literal["uploading_file"]
    data: _UploadingFileData


class LlmStep(_EventBase):
    name: Literal["llm"]
    data: _LlmData


class IntermediaryUpdate(_EventBase):
    name: Literal["intermediary_update"]
    data: _IntermediaryUpdateData


class ToolCall(_EventBase):
    name: Literal["tool_call"]
    """``status`` discriminates the phase: ``running`` / ``success`` / ``error``."""
    data: _ToolCallData


class Result(_EventBase):
    name: Literal["result"]
    data: _ResultData


class UnknownEvent(_EventBase):
    """Forward-compat fallback for an event ``name`` this SDK version does not
    model yet. The server can add events without breaking old clients."""

    name: str
    data: dict[str, Any] | None = None


type _Known = Annotated[
    WaitingForStart
    | SettingUpSandbox
    | UploadingFile
    | LlmStep
    | IntermediaryUpdate
    | ToolCall
    | Result,
    Field(discriminator="name"),
]
type AnyEvent = _Known | UnknownEvent

_known_adapter: TypeAdapter[_Known] = TypeAdapter(_Known)


def parse_event(obj: dict[str, Any]) -> AnyEvent:
    """Parse one decoded JSONL event line into a typed event.

    Unknown event names degrade to :class:`UnknownEvent` rather than raising, so
    server-side additions never break existing SDK versions.

    Note: this handles *event* lines only. Distinguishing events from terminal
    ``Message`` / ``Partial`` lines (and skipping heartbeats) is the stream
    layer's job — events are the lines carrying a ``correlation_id``.
    """
    try:
        return _known_adapter.validate_python(obj)
    except ValidationError:
        return UnknownEvent.model_validate(obj)
