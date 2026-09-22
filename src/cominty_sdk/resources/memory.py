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
    # types.EllipsisType is 3.10+; this import is annotation-only so the
    # future import keeps it from ever running on the 3.9 floor.
    from types import EllipsisType

    from .._transport import AsyncTransport

__all__ = ["MemoryResource"]

# Ellipsis distinguishes "argument omitted" from "passed as None" on update().
# typing.Sentinel would be the natural fit, but it's 3.13+, above the floor.
_OptionalField = Union[str, None, "EllipsisType"]


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
        """
        List the current user's memory files.

        Sends ``GET /memory``. Summaries do not include file content.

        Returns:
            list[MemoryFileSummaryOut]: One summary per file.
        """
        raw = await self._transport.request(
            "GET", "/memory", params={"user_id": self._user_id}
        )
        return [MemoryFileSummaryOut.model_validate(item) for item in raw]

    async def create(self, *, path: str, purpose: str, content: str) -> MemoryFileOut:
        """
        Create a memory file.

        Sends ``POST /memory`` (201). ``user_id`` is sent in the body, unlike
        the other memory calls, which send it as a query parameter. ``path``
        may have at most one folder segment (``"folder/file.md"``). ``content``
        may be empty.

        Args:
            path (str): File path, at most one folder deep.
            purpose (str): Why the file exists. The agent reads this.
            content (str): File body. An empty string is allowed.

        Returns:
            MemoryFileOut: The created file, including its ``version`` token.

        Raises:
            InvalidParams: ``path`` is deeper than one folder.
            ConflictError: A file already exists at ``path``.
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
        """
        Fetch one memory file, including its content.

        Sends ``GET /memory/file``.

        Args:
            path (str): File path, at most one folder deep.

        Returns:
            MemoryFileOut: The file, including ``content`` and ``version``.

        Raises:
            InvalidParams: ``path`` is deeper than one folder.
            NotFoundError: No file exists at ``path``.
        """
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
        content: _OptionalField = ...,
        purpose: _OptionalField = ...,
    ) -> MemoryFileOut:
        """
        Update a memory file's content and/or purpose.

        Sends ``PUT /memory/file``. Only the fields you pass are sent. Omit a
        field to leave it unchanged. Passing ``None`` is rejected locally: the
        API ignores a null and would leave the stored value in place.

        Args:
            path (str): File path, at most one folder deep.
            version (str): Opaque token from a previous read. Pass it back unchanged.
            content (str | None): New body. Omit the argument to leave it unchanged.
            purpose (str | None): New purpose. Omit the argument to leave it unchanged.

        Returns:
            MemoryFileOut: The updated file, including the new ``version``.

        Raises:
            InvalidParams: ``path`` is too deep, neither field was passed, or a
                field was passed as ``None``.
            ConflictError: ``version`` is well formed but stale.
            APIError: ``version`` is malformed (422).
        """
        path = self._validate_path(path, context="memory.update")
        fields: dict[str, object] = {}
        if content is not ...:
            fields["content"] = content
        if purpose is not ...:
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
        """
        Delete a memory file.

        Sends ``DELETE /memory/file`` (204). Not idempotent: a missing path
        raises, it does not succeed again.

        Args:
            path (str): File path, at most one folder deep.

        Returns:
            None: The file is deleted.

        Raises:
            InvalidParams: ``path`` is deeper than one folder.
            NotFoundError: The path does not exist.
        """
        path = self._validate_path(path, context="memory.delete")
        await self._transport.request(
            "DELETE", "/memory/file", params={"path": path, "user_id": self._user_id}
        )