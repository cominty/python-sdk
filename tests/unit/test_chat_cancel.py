from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx

from cominty_sdk import APIError, AsyncCominty, Message, MessageStatus, NotFoundError

MakeMessage = Callable[..., dict[str, Any]]


async def test_posts_to_cancel_endpoint_and_returns_cancelled_message(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    route = mock_api.post(f"/chat/messages/{ids.assistant_msg}/cancel").mock(
        return_value=httpx.Response(
            200,
            json=make_message(
                id=ids.assistant_msg, role="assistant", content="", status="cancelled"
            ),
        )
    )

    result = await client.chat.cancel(ids.assistant_msg)

    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/chat/messages/{ids.assistant_msg}/cancel"
    assert not request.content
    assert isinstance(result, Message)
    assert result.status == MessageStatus.cancelled


async def test_accepts_uuid_message_id(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    make_message: MakeMessage,
    ids: SimpleNamespace,
) -> None:
    route = mock_api.post(f"/chat/messages/{ids.assistant_msg}/cancel").mock(
        return_value=httpx.Response(
            200, json=make_message(id=ids.assistant_msg, role="assistant", status="cancelled")
        )
    )

    await client.chat.cancel(UUID(ids.assistant_msg))

    assert route.called


async def test_unknown_message_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    mock_api.post(f"/chat/messages/{ids.assistant_msg}/cancel").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )

    with pytest.raises(NotFoundError):
        await client.chat.cancel(ids.assistant_msg)


async def test_message_that_is_not_live_raises_api_error(
    client: AsyncCominty, mock_api: respx.MockRouter, ids: SimpleNamespace
) -> None:
    mock_api.post(f"/chat/messages/{ids.assistant_msg}/cancel").mock(
        return_value=httpx.Response(400, json={"detail": "Message is not live"})
    )

    with pytest.raises(APIError, match="Message is not live") as caught:
        await client.chat.cancel(ids.assistant_msg)

    assert caught.value.status_code == 400


@pytest.mark.parametrize("bad_id", ["", "not-a-uuid", "../threads/x"])
async def test_message_id_that_is_not_a_uuid_raises_before_any_request(
    client: AsyncCominty, mock_api: respx.MockRouter, bad_id: str
) -> None:
    with pytest.raises(ValueError, match="message_id must be a UUID"):
        await client.chat.cancel(bad_id)

    assert not mock_api.calls
