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
    MemoryPathParam,
)

if TYPE_CHECKING:
    from .._transport import AsyncTransport

__all__ = ["MemoryResource"]


class _Unset:
    """Sentinel default distinguishing "not passed" from "passed as ``None``"
    for :meth:`MemoryResource.update`'s optional fields."""

    def __repr__(self) -> str:
        return "UNSET"


_UNSET = _Unset()
_OptionalField = Union[str, None, _Unset]


class MemoryResource:
    def __init__(self, transport: AsyncTransport, *, user_id: str) -> None:
        self._transport = transport
        self._user_id = user_id

    @staticmethod
    def _validate_path(path: str, *, context: str) -> str:
        try:
            return MemoryPathParam(path=path).path
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context=context) from None

    async def list(self) -> list[MemoryFileSummaryOut]:
        """List the current user's memory files (``GET /memory``)."""
        raw = await self._transport.request(
            "GET", "/memory", params={"user_id": self._user_id}
        )
        return [MemoryFileSummaryOut.model_validate(item) for item in raw]

    async def create(self, *, path: str, purpose: str, content: str) -> MemoryFileOut:
        """Create a memory file (``POST /memory``, 201 Created).

        Unlike every other memory endpoint, ``user_id`` is injected into the
        request body here rather than sent as a query param. ``path`` may have
        at most one folder segment (``"folder/file.md"``, not
        ``"a/b/file.md"``); a deeper path raises
        :class:`~.exceptions.InvalidParams` locally. ``content`` may be an
        empty string — the API doesn't enforce a minimum length. Creating at a
        ``path`` that already exists raises
        :class:`~.exceptions.ConflictError` (409).
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
        path = self._validate_path(path, context="memory.get")
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

        Partial: only the fields you pass are sent. ``version`` is the opaque
        token from a previous read; a stale one raises
        :class:`~.exceptions.ConflictError` (409).

        The API does not currently support clearing ``content``/``purpose``
        once set — passing ``content=None`` or ``purpose=None`` raises
        :class:`~.exceptions.InvalidParams` locally rather than silently
        sending a ``null`` the server would ignore. Omit the argument to
        leave a field untouched.

        ``version`` must be a real version token from a previous read, not an
        arbitrary string — a well-formed but stale one raises
        :class:`~.exceptions.ConflictError` (409), a malformed one raises
        :class:`~.exceptions.APIError` (422).
        """
        path = self._validate_path(path, context="memory.update")
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
        """Delete a memory file (``DELETE /memory/file``, 204 No Content).

        Not idempotent: deleting an already-deleted (or never-existing) path
        raises :class:`~.exceptions.NotFoundError` (404) rather than
        succeeding again.
        """
        path = self._validate_path(path, context="memory.delete")
        await self._transport.request(
            "DELETE", "/memory/file", params={"path": path, "user_id": self._user_id}
        )