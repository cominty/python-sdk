from __future__ import annotations

from typing import TYPE_CHECKING

from cominty_sdk.models.documents import DocumentMetadataOut

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

__all__ = ["DocumentsResource"]


class DocumentsResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def get(self, document_id: str) -> DocumentMetadataOut:
        """
        Resolve a document id from a chat citation to its source and file.

        Sends ``GET /documents?id=...``. Document ids may contain ``#``; they are
        sent URL-encoded.

        Args:
            document_id (str): The composite id as it appears in an agent citation.

        Returns:
            DocumentMetadataOut: The document's source, name, and type.

        Raises:
            ValueError: ``document_id`` is empty.
            NotFoundError: Unknown to this API key's organization.
        """
        if not document_id:
            raise ValueError("document_id must be a non-empty string")
        raw = await self._transport.request("GET", "/documents", params={"id": document_id})
        return DocumentMetadataOut.model_validate(raw)
