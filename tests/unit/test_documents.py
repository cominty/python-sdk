from __future__ import annotations

import httpx
import pytest
import respx

from cominty_sdk import AsyncCominty, DocumentMetadataOut, NotFoundError, SourceStore

DOCUMENT_ID = "drv_V1StGXR8#faq.md"


def _document() -> dict[str, object]:
    return {
        "document_id": DOCUMENT_ID,
        "source_id": 42,
        "document_name": "faq.md",
        "document_uri": None,
        "source_pid": "src_PmeJ7Hw1l2Z0QyAbC",
        "source_type": "draganddrop",
        "document_extension": "md",
        "document_mime_type": "text/markdown",
    }


async def test_get_sends_the_id_url_encoded(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/documents").mock(return_value=httpx.Response(200, json=_document()))

    document = await client.documents.get(DOCUMENT_ID)

    assert isinstance(document, DocumentMetadataOut)
    assert document.source_type is SourceStore.draganddrop
    request = route.calls.last.request
    assert request.url.params["id"] == DOCUMENT_ID
    assert "%23" in str(request.url)  # the "#" never becomes a fragment


async def test_get_rejects_an_empty_id(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    with pytest.raises(ValueError, match="document_id must be a non-empty string"):
        await client.documents.get("")

    assert mock_api.calls.call_count == 0


async def test_get_unknown_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/documents").mock(return_value=httpx.Response(404, json={"detail": "Not Found"}))

    with pytest.raises(NotFoundError):
        await client.documents.get("nope")
