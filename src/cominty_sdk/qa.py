"""Public, stable helpers for QA / automated testing of Cominty agents.

These re-export the internal stream/citation/tool utilities under a supported
namespace so external test suites don't have to import from ``cominty_sdk._qa``
(private, no stability guarantee). Prefer the high-level methods on
``AsyncCominty`` and the properties on ``MessageOut`` (``tool_names``,
``document_citations``, ``web_citations``, ``cite_tags``) where they suffice;
reach for this module only for stream-event inspection and cite-tag format
validation.
"""

from __future__ import annotations

from cominty_sdk._qa import (
    CITE_TAG_PATTERN,
    DOCUMENT_CITE_PATTERN,
    WEB_CITE_PATTERN,
    StreamEvent,
    extract_cite_tags,
    extract_stream_reply,
    extract_tool_names,
    is_stream_terminal_event,
    parse_document_citations,
    parse_web_citations,
    stream_event_id,
)

__all__ = [
    "CITE_TAG_PATTERN",
    "DOCUMENT_CITE_PATTERN",
    "WEB_CITE_PATTERN",
    "StreamEvent",
    "extract_cite_tags",
    "extract_stream_reply",
    "extract_tool_names",
    "is_stream_terminal_event",
    "parse_document_citations",
    "parse_web_citations",
    "stream_event_id",
]
