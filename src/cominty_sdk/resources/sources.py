from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote

from pydantic import TypeAdapter, ValidationError

from cominty_sdk._uploads import LocalFiles, expand_local_files, guess_mimetype, invalid_upload
from cominty_sdk.exceptions import InvalidParams, NotFoundError, SDKError, SourceSyncFailed
from cominty_sdk.models.chat import ConfirmFileUploadParams, FileUploadPermission, UploadFileParams
from cominty_sdk.models.sources import (
    CreateSourceParams,
    DriveOut,
    FileOut,
    SourceConfig,
    SourceOut,
    SourceStatus,
    UpdateSourceParams,
)

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

__all__ = ["SourcesResource"]

# MAX_COMINTY_FILES_PER_DRIVE of the hosted API. Checked locally so a folder of 60 files
# fails before the first upload instead of after the 50th; a lower limit on another
# deployment is still reported by the API as a 400 "Too many files".
_MAX_FILES_PER_SOURCE = 50

_Operation = Literal["start", "pause", "archive", "sync"]

# PUT /dc/sources/{pid}/status?operation=sync is only valid from these statuses.
_SYNCABLE = frozenset(
    {
        SourceStatus.synced,
        SourceStatus.error,
        SourceStatus.out_of_sync,
        SourceStatus.daily_quota_reached,
    }
)
# A sync is still in flight, or about to start, in these statuses: keep waiting.
_IN_PROGRESS = frozenset(
    {
        SourceStatus.pending,
        SourceStatus.syncing,
        SourceStatus.out_of_sync,
        SourceStatus.cancelling,
        SourceStatus.pausing,
    }
)

_url_adapter: TypeAdapter[str] = TypeAdapter(str)


class SourcesResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def create(self, files: LocalFiles, *, name: str | None = None) -> SourceOut:
        """
        Turn local files into an indexed document source.

        One call does the whole flow: ``POST /drives`` creates the container, every
        file goes through the presigned upload (``GET /drives/{id}/upload``, a direct
        upload to storage, ``POST /drives/upload``), then ``POST /dc/sources``
        creates a private drag-and-drop source over the drive. Its first sync starts
        at once; await :meth:`wait_synced` before searching it. Files are uploaded
        one after the other and read off the event loop.

        Chats that search this source must run with ``user_id`` set to the Clerk id
        of the admin who minted the API key (``AgentOut.owner`` on any agent the key
        created). With another ``user_id`` the agent's document tool finds no
        authorized source.

        Args:
            files (LocalFiles): A file path, a folder path (its top-level files, hidden
                ones skipped), or an iterable of file paths. A plain ``str`` is rejected.
            name (str | None): Source name shown in the console. Omit for the server default.

        Returns:
            SourceOut: The new source, ``status`` is ``pending`` or ``syncing``. Use
                ``pid`` with the other methods and ``id`` in agent capabilities.

        Raises:
            InvalidParams: ``files`` is not a path or iterable of paths, is empty, names
                a missing file or two files with the same name, or has more than 50 files.
            OSError: A file cannot be read.
            APIError: The API refused a step (for instance ``Too many drives``) or the
                storage backend refused an upload. The source is not created; the
                drive is left to the server's orphan cleanup.
            SDKError: The API answered with an upload permission the SDK cannot use.
        """
        context = "sources.create"
        paths = expand_local_files(files, context=context)
        _check_file_count(len(paths), context=context)
        drive = DriveOut.model_validate(await self._transport.request("POST", "/drives"))
        for path in paths:
            await self._upload(drive.id, path)
        try:
            params = CreateSourceParams(name=name, config=SourceConfig(drive_id=drive.id))
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context=context) from None
        raw = await self._transport.request(
            "POST", "/dc/sources", json_body=params.model_dump(mode="json", exclude_none=True)
        )
        return SourceOut.model_validate(raw)

    async def list(self) -> list[SourceOut]:
        """
        List the sources visible to this API key.

        Sends ``GET /dc/sources``: the organization-scoped sources plus the ones the
        key created, archived ones included.

        Returns:
            list[SourceOut]: Every visible source.
        """
        raw = await self._transport.request("GET", "/dc/sources")
        return [SourceOut.model_validate(item) for item in raw]

    async def get(self, source_pid: str) -> SourceOut:
        """
        Fetch one source by public id.

        The API has no single-source read for keys, so this lists and picks: it costs
        the same as :meth:`list`.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.

        Returns:
            SourceOut: The source.

        Raises:
            NotFoundError: No visible source has this ``pid``.
        """
        for source in await self.list():
            if source.pid == source_pid:
                return source
        raise NotFoundError(
            f"no source with pid {source_pid!r} is visible to this API key",
            status_code=404,
            detail="Not Found",
        )

    async def update(self, source_pid: str, *, name: str) -> SourceOut:
        """
        Rename a source.

        Sends ``PUT /dc/sources/{pid}``. The name is the only mutable field of a
        drag-and-drop source: its drive cannot change.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.
            name (str): New name.

        Returns:
            SourceOut: The updated source.

        Raises:
            InvalidParams: ``name`` is not a string.
            NotFoundError: No writable source has this ``pid``.
        """
        try:
            params = UpdateSourceParams(name=name)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="sources.update") from None
        raw = await self._transport.request(
            "PUT", f"/dc/sources/{_path(source_pid)}", json_body=params.model_dump(mode="json")
        )
        return SourceOut.model_validate(raw)

    async def add_files(self, source_pid: str, files: LocalFiles) -> list[FileOut]:
        """
        Upload more files into a source and have it re-indexed.

        Each file goes through the presigned upload into the source's drive. A sync
        is then requested when the source is in a state that accepts one
        (``synced``, ``error``, ``out_of_sync``, ``daily_quota_reached``); while a
        sync is already running the new files are left for it, or for the daily
        one, to pick up.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.
            files (LocalFiles): Same shapes as :meth:`create`.

        Returns:
            list[FileOut]: The files just added, in upload order.

        Raises:
            InvalidParams: Same local checks as :meth:`create`; the 50-file cap counts
                the files already in the source.
            NotFoundError: No visible source has this ``pid``.
            APIError: The API or the storage backend refused an upload. Files uploaded
                before the failure stay in the source.
        """
        context = "sources.add_files"
        paths = expand_local_files(files, context=context)
        source = await self.get(source_pid)
        drive = await self._drive(source)
        _check_file_count(len(drive.files) + len(paths), context=context)
        added = [await self._upload(drive.id, path) for path in paths]
        await self._sync_if_allowed(source)
        return added

    async def list_files(self, source_pid: str) -> list[FileOut]:
        """
        List the files a source is built from.

        Sends ``GET /drives/{drive_id}`` for the source's drive.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.

        Returns:
            list[FileOut]: The files in the source.

        Raises:
            NotFoundError: No visible source has this ``pid``.
        """
        return (await self._drive(await self.get(source_pid))).files

    async def remove_file(self, source_pid: str, file_id: str) -> None:
        """
        Remove a file from a source and have it re-indexed.

        Sends ``DELETE /files/{file_id}`` (the row and the stored object), then
        requests a sync under the same rule as :meth:`add_files`.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source the file belongs to.
            file_id (str): ``FileOut.id`` of the file.

        Returns:
            None: The file is removed.

        Raises:
            ValueError: ``file_id`` is empty.
            NotFoundError: No visible source has this ``pid``, or no such file.
        """
        source = await self.get(source_pid)
        await self._transport.request("DELETE", f"/files/{_file_path(file_id)}")
        await self._sync_if_allowed(source)

    async def download_file(self, file_id: str) -> bytes:
        """
        Download a file of a source.

        Sends ``GET /files/{file_id}``, which answers with a short-lived presigned URL
        (5 minutes), then fetches the bytes from it without your API key. The whole
        file is held in memory.

        Args:
            file_id (str): ``FileOut.id`` of the file.

        Returns:
            bytes: The file content.

        Raises:
            ValueError: ``file_id`` is empty.
            NotFoundError: No such file for this API key.
            APIError: The storage backend refused the download.
            SDKError: The API did not answer with a download URL.
        """
        raw = await self._transport.request("GET", f"/files/{_file_path(file_id)}")
        try:
            url = _url_adapter.validate_python(raw)
        except ValidationError:
            raise SDKError(
                f"GET /files/{file_id} did not answer with a download URL string"
            ) from None
        return await self._transport.download_from_presigned_url(url)

    async def start(self, source_pid: str) -> SourceOut:
        """
        Resume a paused source.

        Sends ``PUT /dc/sources/{pid}/status?operation=start``. Only valid from
        ``paused``.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.

        Returns:
            SourceOut: The source, leaving ``paused``.

        Raises:
            APIError: The source is not paused (400 ``Operation is not valid``).
        """
        return await self._manage(source_pid, "start")

    async def pause(self, source_pid: str) -> SourceOut:
        """
        Pause a source: no more syncs until :meth:`start`.

        Sends ``PUT /dc/sources/{pid}/status?operation=pause``. A running sync is
        cancelled.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.

        Returns:
            SourceOut: The source, ``pausing`` or ``paused``.

        Raises:
            APIError: The source cannot be paused from its current status (400).
        """
        return await self._manage(source_pid, "pause")

    async def sync(self, source_pid: str) -> SourceOut:
        """
        Force a sync now instead of waiting for the daily one.

        Sends ``PUT /dc/sources/{pid}/status?operation=sync``. Valid from ``synced``,
        ``error``, ``out_of_sync`` and ``daily_quota_reached``.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.

        Returns:
            SourceOut: The source, ``syncing``.

        Raises:
            APIError: A sync is already running or the source is paused (400).
        """
        return await self._manage(source_pid, "sync")

    async def archive(self, source_pid: str) -> SourceOut:
        """
        Archive a source and its drive. This is terminal.

        Sends ``PUT /dc/sources/{pid}/status?operation=archive``. The indexed
        documents are removed; the source stays listed with ``status="archived"``.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.

        Returns:
            SourceOut: The archived source.

        Raises:
            APIError: The source is already archived (400).
        """
        return await self._manage(source_pid, "archive")

    async def wait_synced(
        self, source_pid: str, *, timeout: float = 600.0, interval: float = 5.0
    ) -> SourceOut:
        """
        Block until a source has finished indexing.

        Polls :meth:`get` every ``interval`` seconds while a sync is pending or
        running, and returns as soon as the source is ``synced``.

        Args:
            source_pid (str): ``SourceOut.pid`` of the source.
            timeout (float): Seconds to wait at most. Default is 600.
            interval (float): Seconds between two polls. Default is 5.

        Returns:
            SourceOut: The source, ``synced``.

        Raises:
            SourceSyncFailed: The source settled in a status other than ``synced``
                (``error``, ``paused``, ``archived``, ``daily_quota_reached``, ...).
                The source is available as ``exc.source``.
            asyncio.TimeoutError: ``timeout`` elapsed while the sync was still running.
            NotFoundError: No visible source has this ``pid``.
        """
        return await asyncio.wait_for(self._poll_until_synced(source_pid, interval), timeout)

    async def _poll_until_synced(self, source_pid: str, interval: float) -> SourceOut:
        while True:
            source = await self.get(source_pid)
            if source.status is SourceStatus.synced:
                return source
            if source.status not in _IN_PROGRESS:
                raise SourceSyncFailed(
                    f"source {source_pid!r} stopped in status {source.status.value!r} "
                    "instead of reaching 'synced'",
                    source=source,
                )
            await asyncio.sleep(interval)

    async def _manage(self, source_pid: str, operation: _Operation) -> SourceOut:
        raw = await self._transport.request(
            "PUT", f"/dc/sources/{_path(source_pid)}/status", params={"operation": operation}
        )
        return SourceOut.model_validate(raw)

    async def _sync_if_allowed(self, source: SourceOut) -> None:
        if source.status in _SYNCABLE:
            await self._manage(source.pid, "sync")

    async def _drive(self, source: SourceOut) -> DriveOut:
        drive_id = source.drive_id
        if drive_id is None:
            raise SDKError(
                f"source {source.pid!r} ({source.store.value}) has no drive_id in its config: "
                "only drag-and-drop sources hold files"
            )
        raw = await self._transport.request("GET", f"/drives/{_path(drive_id)}")
        return DriveOut.model_validate(raw)

    async def _upload(self, drive_id: str, path: Path) -> FileOut:
        # Cannot fail: a Path name never holds "/", the filesystem caps its length, and
        # the mimetype always has a fallback. A ValidationError here would be an SDK bug.
        params = UploadFileParams(filename=path.name, mimetype=guess_mimetype(path.name))
        # Read off the event loop: a large file would otherwise freeze every task.
        content = await asyncio.to_thread(path.read_bytes)
        raw = await self._transport.request(
            "GET", f"/drives/{_path(drive_id)}/upload", params=params.model_dump(mode="json")
        )
        try:
            permission = FileUploadPermission.model_validate(raw)
        except ValidationError:
            # Not InvalidParams, and not the raw error: its input holds the presigned fields.
            raise SDKError(
                f"GET /drives/{drive_id}/upload did not answer with a presigned upload "
                "(expected a url and fields containing a key)"
            ) from None
        etag = await self._transport.upload_to_presigned_url(
            permission.url,
            fields=permission.fields,
            filename=params.filename,
            content=content,
            mimetype=params.mimetype,
        )
        confirmation = ConfirmFileUploadParams(etag=etag, key=permission.fields["key"])
        confirmed = await self._transport.request(
            "POST", "/drives/upload", json_body=confirmation.model_dump(mode="json")
        )
        return FileOut.model_validate(confirmed)


def _check_file_count(count: int, *, context: str) -> None:
    if count > _MAX_FILES_PER_SOURCE:
        raise invalid_upload(
            "files",
            f"a source holds at most {_MAX_FILES_PER_SOURCE} files, this would make {count}",
            context=context,
        )


def _path(segment: str) -> str:
    return quote(segment, safe="")


def _file_path(file_id: str) -> str:
    if not file_id:
        raise ValueError("file_id must be a non-empty string")
    return _path(file_id)
