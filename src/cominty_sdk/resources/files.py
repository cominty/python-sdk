from __future__ import annotations

import mimetypes
from pathlib import Path

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.exceptions import raise_for_status
from cominty_sdk.models.files import (
    ConversationFileOut,
    FileUploadConfirmation,
    FileUploadPermission,
)


class FilesResource:
    """Conversation file upload and download."""

    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http

    async def upload(
        self,
        source: str | Path | bytes,
        *,
        filename: str | None = None,
        mimetype: str | None = None,
    ) -> str:
        """Upload a file and return its file_id.

        Accepts a file path or raw bytes. For bytes, filename is required.
        """
        if isinstance(source, bytes):
            if not filename:
                raise ValueError("filename is required when uploading bytes.")
            data = source
        else:
            path = Path(source)
            data = path.read_bytes()
            filename = filename or path.name

        assert filename is not None
        resolved_mimetype = (
            mimetype
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )

        permission = await self._http.request_model(
            "GET",
            "/chat/files/upload",
            FileUploadPermission,
            params={"mimetype": resolved_mimetype, "filename": filename},
        )

        form_fields = dict(permission.fields)
        files = {"file": (filename, data, resolved_mimetype)}
        s3_response = await self._http.raw_client.post(
            permission.url,
            data=form_fields,
            files=files,
        )
        if s3_response.status_code >= 400:
            raise_for_status(s3_response.status_code, s3_response.text, "S3 upload failed")

        etag = s3_response.headers.get("ETag", "").strip('"')
        key = permission.fields.get("key") or permission.fields.get("Key", "")
        if not key:
            raise ValueError("Upload permission did not include an S3 object key.")

        confirmation = FileUploadConfirmation(etag=etag, key=key)
        file_out = await self._http.request_model(
            "POST",
            "/chat/files/upload",
            ConversationFileOut,
            json=confirmation.model_dump(),
        )
        return file_out.id

    async def download(self, file_pid: str) -> str:
        """Download a conversation file; returns the signed URL or content string."""
        result = await self._http.request("GET", f"/chat/files/{file_pid}", parse_json=True)
        if isinstance(result, str):
            return result
        raise ValueError(f"Unexpected download response type: {type(result)!r}")
