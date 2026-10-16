# Auth, JSON, errors, and JSONL framing. Resources own the domain objects.

from __future__ import annotations

import html
import json
import re
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx

from ._config import Config
from .exceptions import APIConnectionError, SDKError, error_from_response

__all__ = ["AsyncTransport"]

_TOKEN_HEADER = "x-cominty-token"


class AsyncTransport:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={_TOKEN_HEADER: config.api_token},
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,  # noqa: ANN401 - arbitrary JSON request body
        params: Mapping[str, Any] | None = None,
    ) -> Any:  # noqa: ANN401 - decoded JSON; resources validate into models
        response = await _send(
            self._client, method, path, action="Request to", json=json_body, params=params
        )
        return _safe_json(response)

    async def request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> bytes:
        response = await _send(self._client, method, path, action="Request to", params=params)
        return response.content

    async def upload_to_presigned_url(
        self,
        url: str,
        *,
        fields: Mapping[str, str],
        filename: str,
        content: bytes,
        mimetype: str,
    ) -> str:
        # Never reuse self._client here: it carries x-cominty-token, which must not
        # reach the storage host. See AGENTS.md section 7.4.
        async with httpx.AsyncClient(timeout=self._config.timeout) as storage_client:
            response = await _send(
                storage_client,
                "POST",
                url,
                action="Upload to",
                data=dict(fields),
                files={"file": (filename, content, mimetype)},
            )
        _require_success(response)
        etag = response.headers.get("ETag")
        if etag is None:
            raise SDKError("the storage backend accepted the upload but sent no ETag header")
        return etag

    async def download_from_presigned_url(self, url: str) -> bytes:
        # Fresh client for the same reason as upload_to_presigned_url.
        async with httpx.AsyncClient(timeout=self._config.timeout) as storage_client:
            response = await _send(storage_client, "GET", url, action="Download from")
        _require_success(response)
        return response.content

    @asynccontextmanager
    async def stream_lines(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncGenerator[AsyncIterator[dict[str, Any]]]:
        try:
            async with self._client.stream(
                method, path, params=params, headers=headers
            ) as response:
                if response.is_error:
                    await response.aread()
                    raise error_from_response(
                        response.status_code, _safe_json(response), response.headers
                    )
                yield _iter_json_lines(response)
        except httpx.TimeoutException as exc:
            raise APIConnectionError(f"Stream to {path} timed out") from exc
        except httpx.RequestError as exc:
            raise APIConnectionError(f"Stream to {path} failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


async def _send(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    action: str,
    **kwargs: Any,  # noqa: ANN401 - forwarded untouched to httpx.AsyncClient.request
) -> httpx.Response:
    # A presigned URL carries its signature in the query string: keep it out of errors.
    target = url.split("?", 1)[0].split("#", 1)[0]
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise APIConnectionError(f"{action} {target} timed out") from exc
    except httpx.RequestError as exc:
        raise APIConnectionError(f"{action} {target} failed: {exc}") from exc

    if response.is_error:
        body = _safe_json(response)
        if body is None:
            body = _storage_error_body(response)
        raise error_from_response(response.status_code, body, response.headers)
    return response


async def _iter_json_lines(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        stripped = line.strip()
        if not stripped:
            # Blank line: a candidate keep-alive shape (heartbeat format is not
            # yet confirmed). Skipping blanks is always safe.
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            # Tolerate non-JSON keep-alive lines rather than killing the stream.
            continue
        if isinstance(obj, dict):
            yield obj


_STORAGE_ERROR_CODE = re.compile(r"<Code>(.*?)</Code>", re.DOTALL)
_STORAGE_ERROR_MESSAGE = re.compile(r"<Message>(.*?)</Message>", re.DOTALL)


def _storage_error_body(response: httpx.Response) -> dict[str, str] | None:
    # S3 answers errors with XML, not JSON: surface its Code and Message as the detail.
    if "xml" not in response.headers.get("content-type", ""):
        return None
    code = _STORAGE_ERROR_CODE.search(response.text)
    if code is None:
        return None
    message = _STORAGE_ERROR_MESSAGE.search(response.text)
    detail = html.unescape(code.group(1))
    if message is not None:
        detail = f"{detail}: {html.unescape(message.group(1))}"
    return {"detail": detail}


def _require_success(response: httpx.Response) -> None:
    # The storage client does not follow redirects, and a presigned URL cannot survive
    # one: a 3xx is a failure, not an empty success.
    if not response.is_success:
        body = {"detail": "the storage backend answered with a redirect instead of the file"}
        raise error_from_response(response.status_code, body, response.headers)


def _safe_json(response: httpx.Response) -> Any:  # noqa: ANN401 - decoded JSON
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return None
