"""Unit tests for ``client.chat.cancel`` — cancelling an in-flight message."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import AsyncCominty, Message, MessageStatus, NotFoundError

ASSISTANT_MSG_ID = "33333333-3333-3333-3333-333333333333"

MakeMessage = Callable[..., dict[str, Any]]


async def test_returns_updated_message_with_cancelled_status(
    client: AsyncCominty, mock_api: respx.MockRouter, make_message: MakeMessage
) -> None:
    mock_api.post(f"/chat/messages/{ASSISTANT_MSG_ID}/cancel").mock(
        return_value=httpx.Response(
            200,
            json=make_message(
                id=ASSISTANT_MSG_ID, role="assistant", content="half", status="cancelled"
            ),
        )
    )

    result = await client.chat.cancel(ASSISTANT_MSG_ID)

    assert isinstance(result, Message)
    assert result.status == MessageStatus.cancelled
    assert result.content == "half"


async def test_accepts_uuid_message_id(
    client: AsyncCominty, mock_api: respx.MockRouter, make_message: MakeMessage
) -> None:
    route = mock_api.post(f"/chat/messages/{ASSISTANT_MSG_ID}/cancel").mock(
        return_value=httpx.Response(
            200,
            json=make_message(id=ASSISTANT_MSG_ID, role="assistant", status="cancelled"),
        )
    )

    await client.chat.cancel(UUID(ASSISTANT_MSG_ID))

    assert route.called


async def test_cancel_unknown_message_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.post(f"/chat/messages/{ASSISTANT_MSG_ID}/cancel").mock(
        return_value=httpx.Response(404, json={"detail": "no such message"})
    )

    with pytest.raises(NotFoundError):
        await client.chat.cancel(ASSISTANT_MSG_ID)
