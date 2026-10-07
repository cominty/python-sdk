from __future__ import annotations

from typing import TYPE_CHECKING, Union

from pydantic import TypeAdapter, ValidationError

from cominty_sdk.exceptions import InvalidParams
from cominty_sdk.models.memory import (
    MemoryFileCreate,
    MemoryFileOut,
    MemoryFileQueryParams,
    MemoryFileSummaryOut,
    MemoryFileUpdate,
    MemoryNamespaceParam,
)

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

__all__ = ["MemoryResource"]

# Ellipsis distinguishes "argument omitted" from "passed as None" on update().
# typing.Sentinel would be the natural fit, but it's 3.13+, above the floor.
# "ellipsis" (the type of `...`) is typeshed's synthesized name for it: no
# import needed, and unlike types.EllipsisType it's available on Python 3.9.
_OptionalField = Union[str, None, "ellipsis"]  # noqa: F821 - typeshed-only, not a real name

_namespaces_adapter: TypeAdapter[list[str]] = TypeAdapter(list[str])


class MemoryResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    @staticmethod
    def _validate_query(path: str, namespace: str, *, context: str) -> tuple[str, str]:
        try:
            validated = MemoryFileQueryParams(path=path, namespace=namespace)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context=context) from None
        return validated.path, validated.namespace

    async def list(self, *, namespace: str | None = None) -> list[MemoryFileSummaryOut]:
        """
        List memory files.

        Sends ``GET /memory``. Omit ``namespace`` to list every file visible
        to this API key; pass one to filter to a single bag.

        Args:
            namespace (str | None): Bag to filter to. Omit to list every bag.

        Returns:
            list[MemoryFileSummaryOut]: One summary per file.

        Raises:
            InvalidParams: ``namespace`` is longer than 128 characters.
        """
        params: dict[str, object] = {}
        if namespace is not None:
            try:
                params["namespace"] = MemoryNamespaceParam(namespace=namespace).namespace
            except ValidationError as exc:
                raise InvalidParams.from_validation_error(exc, context="memory.list") from None
        raw = await self._transport.request("GET", "/memory", params=params)
        return [MemoryFileSummaryOut.model_validate(item) for item in raw]

    async def list_namespaces(self) -> list[str]:
        """
        List the distinct namespaces that already have files.

        Sends ``GET /memory/namespaces``. Read-only: there is no call to
        create a namespace, since the first read or write against a name is
        enough to bring that bag into existence.

        Returns:
            list[str]: Logical namespace names.
        """
        raw = await self._transport.request("GET", "/memory/namespaces")
        return _namespaces_adapter.validate_python(raw)

    async def create(
        self, *, path: str, namespace: str, purpose: str, content: str
    ) -> MemoryFileOut:
        """
        Create a memory file in a namespace.

        Sends ``POST /memory`` (201). ``path`` may have at most one folder
        segment (``"folder/file.md"``). ``content`` may be empty.

        Args:
            path (str): File path, at most one folder deep.
            namespace (str): Bag this file belongs to, at most 128 characters.
            purpose (str): Why the file exists. The agent reads this.
            content (str): File body. An empty string is allowed.

        Returns:
            MemoryFileOut: The created file, including its ``version`` token.

        Raises:
            InvalidParams: ``path`` or ``namespace`` failed local validation.
            ConflictError: A file already exists at ``path`` in ``namespace``.
        """
        try:
            params = MemoryFileCreate(
                path=path, namespace=namespace, purpose=purpose, content=content
            )
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="memory.create") from None
        raw = await self._transport.request(
            "POST", "/memory", json_body=params.model_dump(mode="json")
        )
        return MemoryFileOut.model_validate(raw)

    async def get(self, path: str, *, namespace: str) -> MemoryFileOut:
        """
        Fetch one memory file, including its content.

        Sends ``GET /memory/file``.

        Args:
            path (str): File path, at most one folder deep.
            namespace (str): Bag this file belongs to.

        Returns:
            MemoryFileOut: The file, including ``content`` and ``version``.

        Raises:
            InvalidParams: ``path`` or ``namespace`` failed local validation.
            NotFoundError: No file exists at ``path`` in ``namespace``.
        """
        path, namespace = self._validate_query(path, namespace, context="memory.get")
        raw = await self._transport.request(
            "GET", "/memory/file", params={"path": path, "namespace": namespace}
        )
        return MemoryFileOut.model_validate(raw)

    async def update(
        self,
        path: str,
        *,
        namespace: str,
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
            namespace (str): Bag this file belongs to.
            version (str): Opaque token from a previous read. Pass it back unchanged.
            content (str | None): New body. Omit the argument to leave it unchanged.
            purpose (str | None): New purpose. Omit the argument to leave it unchanged.

        Returns:
            MemoryFileOut: The updated file, including the new ``version``.

        Raises:
            InvalidParams: ``path``/``namespace`` failed local validation,
                neither field was passed, or a field was passed as ``None``.
            ConflictError: ``version`` is well formed but stale.
            APIError: ``version`` is malformed (422).
        """
        path, namespace = self._validate_query(path, namespace, context="memory.update")
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
        params = {"path": path, "namespace": namespace, "version": version}
        raw = await self._transport.request("PUT", "/memory/file", params=params, json_body=body)
        return MemoryFileOut.model_validate(raw)

    async def delete(self, path: str, *, namespace: str) -> None:
        """
        Delete a memory file.

        Sends ``DELETE /memory/file`` (204). Not idempotent: a missing path
        raises, it does not succeed again.

        Args:
            path (str): File path, at most one folder deep.
            namespace (str): Bag this file belongs to.

        Returns:
            None: The file is deleted.

        Raises:
            InvalidParams: ``path`` or ``namespace`` failed local validation.
            NotFoundError: The path does not exist in ``namespace``.
        """
        path, namespace = self._validate_query(path, namespace, context="memory.delete")
        await self._transport.request(
            "DELETE", "/memory/file", params={"path": path, "namespace": namespace}
        )
