from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

StreamEvent = dict[str, Any]

DOCUMENT_CITE_PATTERN = re.compile(
    r'<cite\s+document_id="([^"]+)"\s+pages="([^"]+)"\s+name="([^"]+)"\s*/>',
)
WEB_CITE_PATTERN = re.compile(r'<cite\s+url="(https?://[^"]+)"\s*/>')
CITE_TAG_PATTERN = re.compile(r"<cite[^>]*/>")


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


def _extract_tool_name_from_event(event: dict[str, Any]) -> str | None:
    for key in ("tool_name", "tool", "name"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    event_type = event.get("type") or event.get("event")
    if event_type in ("tool_call", "tool_use", "tool"):
        for key in ("tool_name", "tool", "name"):
            value = event.get(key)
            if isinstance(value, str) and value:
                return value
    data = event.get("data")
    if isinstance(data, dict):
        return _extract_tool_name_from_event(data)
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
    async for line in response.aiter_lines():
        stripped = line.strip()
        if not stripped:
            continue
        yield json.loads(stripped)
