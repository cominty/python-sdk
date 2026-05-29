from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from cominty_sdk._auth import build_auth_headers
from cominty_sdk.config import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT
from cominty_sdk.exceptions import ComintyTimeoutError, raise_for_status
from cominty_sdk.retry import compute_backoff, is_retryable_exception, maybe_raise_for_status

T = TypeVar("T", bound=BaseModel)


class AsyncHTTPClient:
    """Internal async HTTP client with auth, retries, and error mapping."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        org_id: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.org_id = org_id
        self.max_retries = max_retries
        self.timeout = timeout
        self.stream_timeout = stream_timeout or timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers=build_auth_headers(api_key=api_key, org_id=org_id),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        parse_json: bool = True,
    ) -> Any:
        """Send a request with retries and return parsed JSON or raw response."""
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=headers,
                )
                body: Any
                if parse_json:
                    body = response.json() if response.content else None
                else:
                    body = response.content

                if response.status_code >= 400:
                    maybe_raise_for_status(
                        response.status_code,
                        body,
                        f"{method} {path} failed",
                    )
                return body
            except Exception as exc:
                if not is_retryable_exception(exc) or attempt >= self.max_retries:
                    if isinstance(exc, httpx.TimeoutException):
                        raise ComintyTimeoutError(str(exc)) from exc
                    raise
                last_exc = exc
                await asyncio.sleep(compute_backoff(attempt))
        assert last_exc is not None
        raise last_exc

    async def request_model(
        self,
        method: str,
        path: str,
        model: type[T],
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> T:
        data = await self.request(method, path, params=params, json=json, headers=headers)
        return model.model_validate(data)

    async def request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=params,
                    headers=headers,
                )
                if response.status_code >= 400:
                    body: Any = None
                    if response.content:
                        try:
                            body = response.json()
                        except Exception:
                            body = response.text
                    raise_for_status(
                        response.status_code,
                        body,
                        f"{method} {path} failed",
                    )
                return response.content
            except Exception as exc:
                if not is_retryable_exception(exc) or attempt >= self.max_retries:
                    if isinstance(exc, httpx.TimeoutException):
                        raise ComintyTimeoutError(str(exc)) from exc
                    raise
                last_exc = exc
                await asyncio.sleep(compute_backoff(attempt))
        assert last_exc is not None
        raise last_exc

    @asynccontextmanager
    async def stream_context(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AsyncIterator[httpx.Response]:
        """Open a streaming HTTP response (use as async context manager)."""
        request_headers = dict(headers or {})
        request_headers.setdefault("Accept", "application/jsonl, application/x-ndjson")
        # No read timeout: the caller enforces its own deadline while waiting for events.
        timeout = httpx.Timeout(
            connect=self.timeout,
            read=None,
            write=self.timeout,
            pool=self.timeout,
        )
        async with self._client.stream(
            method,
            path,
            params=params,
            headers=request_headers,
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                body: Any = None
                if response.content:
                    try:
                        body = response.json()
                    except Exception:
                        body = response.text
                raise_for_status(response.status_code, body, f"{method} {path} failed")
            yield response

    @property
    def raw_client(self) -> httpx.AsyncClient:
        """Expose the underlying httpx client for non-API requests (e.g. S3 upload)."""
        return self._client
