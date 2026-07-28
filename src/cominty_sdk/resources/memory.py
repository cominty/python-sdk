"""The memory resource: list, create, read, update, and delete memory files."""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from pydantic import ValidationError

from ..exceptions import InvalidParams
from ..models.memory import (
    MemoryFileCreate,
    MemoryFileOut,
    MemoryFileSummaryOut,
    MemoryFileUpdate,
)

if TYPE_CHECKING:
    from .._transport import AsyncTransport

__all__ = ["MemoryResource"]


class _Unset:
    """Sentinel default for :meth:`MemoryResource.update`'s optional fields.

    Lets the method tell "argument not passed" (leave untouched) apart from
    "argument passed as ``None``" (clear the field) — a plain ``None`` default
    can't make that distinction.
    """

    def __repr__(self) -> str:
        return "UNSET"


_UNSET = _Unset()
_OptionalField = Union[str, None, _Unset]


class MemoryResource:
    def __init__(self, transport: AsyncTransport, *, user_id: str) -> None:
        self._transport = transport
        self._user_id = user_id

    async def list(self) -> list[MemoryFileSummaryOut]:
        """List the current user's memory files (``GET /memory``)."""
        raw = await self._transport.request(
            "GET", "/memory", params={"user_id": self._user_id}
        )
        return [MemoryFileSummaryOut.model_validate(item) for item in raw]

    async def create(self, *, path: str, purpose: str, content: str) -> MemoryFileOut:
        """Create a memory file (``POST /memory``, 201 Created).

        Unlike every other memory endpoint, ``user_id`` is injected into the
        request body here rather than sent as a query param.
        """
        try:
            params = MemoryFileCreate(
                path=path, purpose=purpose, content=content, user_id=self._user_id
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="memory.create") from None
        raw = await self._transport.request(
            "POST", "/memory", json_body=params.model_dump(mode="json")
        )
        return MemoryFileOut.model_validate(raw)

    async def get(self, path: str) -> MemoryFileOut:
        """Fetch a single memory file (``GET /memory/file``)."""
        raw = await self._transport.request(
            "GET", "/memory/file", params={"path": path, "user_id": self._user_id}
        )
        return MemoryFileOut.model_validate(raw)

    async def update(
        self,
        path: str,
        *,
        version: str,
        content: _OptionalField = _UNSET,
        purpose: _OptionalField = _UNSET,
    ) -> MemoryFileOut:
        """Update a memory file's content and/or purpose (``PUT /memory/file``).

        ``version`` is the opaque token from a previously fetched
        :class:`~.models.memory.MemoryFileOut` — round-tripped unchanged as a
        query param. Raises :class:`~.exceptions.ConflictError` (409) if it no
        longer matches the file's current version.

        Only the fields you pass are sent: an omitted ``content``/``purpose``
        leaves that field untouched server-side, while an explicit ``None``
        clears it — the two are not equivalent. Omitting both raises
        :class:`~.exceptions.InvalidParams` before any request is sent, since
        that call would be a no-op.
        """
        fields: dict[str, object] = {}
        if not isinstance(content, _Unset):
            fields["content"] = content
        if not isinstance(purpose, _Unset):
            fields["purpose"] = purpose
        try:
            body_model = MemoryFileUpdate.model_validate(fields)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="memory.update") from None
        body = body_model.model_dump(mode="json", exclude_unset=True)
        params = {"path": path, "version": version, "user_id": self._user_id}
        raw = await self._transport.request(
            "PUT", "/memory/file", params=params, json_body=body
        )
        return MemoryFileOut.model_validate(raw)

    async def delete(self, path: str) -> None:
        """Delete a memory file (``DELETE /memory/file``, 204 No Content)."""
        await self._transport.request(
            "DELETE", "/memory/file", params={"path": path, "user_id": self._user_id}
        )