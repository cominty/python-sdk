from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

StreamEvent = dict[str, Any]

STREAM_TERMINAL_EVENT_TYPES = frozenset({"done", "completed", "error", "cancelled"})

DOCUMENT_CITE_PATTERN = re.compile(
    r'<cite\s+document_id="([^"]+)"\s+pages="([^"]+)"\s+name="([^"]+)"\s*/>',
)
WEB_CITE_PATTERN = re.compile(r'<cite\s+url="(https?://[^"]+)"\s*/>')
CITE_TAG_PATTERN = re.compile(r"<cite[^>]*/>")


def is_stream_terminal_event(event: StreamEvent) -> bool:
    """Return True when a JSONL stream event signals the message has finished."""
    event_type = event.get("type") or event.get("event")
    if isinstance(event_type, str) and event_type.lower() in STREAM_TERMINAL_EVENT_TYPES:
        return True

    name = event.get("name")
    status = event.get("status")
    if name == "result" and status == "success":
        return True

    if event.get("role") == "assistant" and event.get("live") is False:
        terminal_status = str(status or "").lower()
        return terminal_status in {"success", "completed", "error", "cancelled"}

    return False


def extract_stream_reply(event: StreamEvent) -> str | None:
    """Extract assistant reply text from a terminal stream event, if present."""
    if event.get("name") == "result" and event.get("status") == "success":
        data = event.get("data")
        if isinstance(data, dict):
            reply = data.get("reply")
            if isinstance(reply, str):
                return reply
    content = event.get("content")
    if event.get("role") == "assistant" and isinstance(content, str):
        return content
    return None


def extract_tool_names(events: list[dict[str, Any]] | None) -> list[str]:
    """Extract tool names from message events, deduplicated preserving order."""
    if not events:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for event in events:
        name = _extract_tool_name_from_event(event)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


GENERIC_EVENT_NAMES = frozenset(
    {
        "tool_call",
        "tool_use",
        "tool",
        "llm",
        "intermediary_update",
        "setting_up_sandbox",
        "result",
    }
)


def _extract_tool_name_from_event(event: dict[str, Any]) -> str | None:
    data = event.get("data")
    if isinstance(data, dict):
        for key in ("tool_name", "tool", "name"):
            value = data.get(key)
            if isinstance(value, str) and value and value not in GENERIC_EVENT_NAMES:
                return value

    for key in ("tool_name", "tool"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value

    name = event.get("name")
    if isinstance(name, str) and name and name not in GENERIC_EVENT_NAMES:
        return name

    return None


def extract_cite_tags(content: str) -> list[str]:
    """Return raw <cite .../> tags found in message content."""
    return CITE_TAG_PATTERN.findall(content)


def parse_document_citations(content: str) -> list[dict[str, str]]:
    """Parse document citation tags from content."""
    return [
        {"document_id": m.group(1), "pages": m.group(2), "name": m.group(3)}
        for m in DOCUMENT_CITE_PATTERN.finditer(content)
    ]


def parse_web_citations(content: str) -> list[dict[str, str]]:
    """Parse web citation tags from content."""
    return [{"url": m.group(1)} for m in WEB_CITE_PATTERN.finditer(content)]


async def iter_jsonl_events(response: httpx.Response) -> AsyncIterator[StreamEvent]:
    """Parse a JSONL stream into async event dicts."""
    try:
        async for line in response.aiter_lines():
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)
    except httpx.StreamClosed:
        return
    except httpx.ReadError:
        # Server closed the connection before any JSONL (common when agent is still pending).
        return
