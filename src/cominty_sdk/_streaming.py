from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from cominty_sdk._qa import StreamEvent, iter_jsonl_events

if TYPE_CHECKING:
    from cominty_sdk._http import AsyncHTTPClient


async def stream_message_events(
    http: AsyncHTTPClient,
    message_id: str,
    *,
    last_event_id: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream JSONL events for a message."""
    headers: dict[str, str] = {}
    if last_event_id is not None:
        headers["last-event-id"] = last_event_id

    response = await http.stream_request(
        "GET",
        f"/chat/messages/{message_id}/stream",
        headers=headers or None,
    )
    try:
        async for event in iter_jsonl_events(response):
            yield event
    finally:
        await response.aclose()
