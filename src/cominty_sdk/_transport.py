"""Low-level async HTTP transport.

The dumb bottom layer: it knows the auth header, JSON request/response, error
mapping, and JSONL stream framing — and nothing about threads, messages, or
events. Resource code builds requests and parses responses; it never touches
``httpx`` directly.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx

from ._config import Config
from .exceptions import APIConnectionError, error_from_response

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
        """Send a request and return the decoded JSON body.

        Raises an :class:`~.exceptions.APIError` subclass on 4xx/5xx and
        :class:`~.exceptions.APIConnectionError` when no response arrives.
        """
        try:
            response = await self._client.request(
                method, path, json=json_body, params=params
            )
        except httpx.TimeoutException as exc:
            raise APIConnectionError(f"Request to {path} timed out") from exc
        except httpx.RequestError as exc:
            raise APIConnectionError(f"Request to {path} failed: {exc}") from exc

        if response.is_error:
            raise error_from_response(
                response.status_code, _safe_json(response), response.headers
            )
        return _safe_json(response)

    @asynccontextmanager
    async def stream_lines(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncGenerator[AsyncIterator[dict[str, Any]]]:
        """Open a streaming response and yield an iterator of decoded JSONL objects.

        Must be used as an async context manager so the connection is released::

            async with transport.stream_lines("GET", path) as lines:
                async for obj in lines:
                    ...

        Blank keep-alive lines and any non-JSON lines are skipped here; deciding
        what each JSON object *means* is the caller's job.
        """
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


async def _iter_json_lines(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        stripped = line.strip()
        if not stripped:
            # Blank line — a candidate keep-alive shape (heartbeat format is not
            # yet confirmed). Skipping blanks is always safe.
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            # Tolerate non-JSON keep-alive lines rather than killing the stream.
            continue
        if isinstance(obj, dict):
            yield obj


def _safe_json(response: httpx.Response) -> Any:  # noqa: ANN401 - decoded JSON
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return None
