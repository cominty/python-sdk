from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from cominty_sdk.exceptions import (
    ComintyAPIError,
    ComintyError,
    ComintyTimeoutError,
    RateLimitError,
    ServerError,
    raise_for_status,
)

T = TypeVar("T")

RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


def is_retryable_exception(exc: BaseException) -> bool:
    """Return True if the exception warrants a retry."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)):
        return True
    if isinstance(exc, RateLimitError | ServerError):
        return True
    return isinstance(exc, ComintyAPIError) and exc.status_code in RETRYABLE_STATUS_CODES


def compute_backoff(attempt: int, *, base: float = 0.5, maximum: float = 8.0) -> float:
    """Compute exponential backoff with jitter."""
    delay = min(base * (2**attempt), maximum)
    return float(delay * (0.5 + random.random()))


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Execute an async callable with retries on transient failures."""
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except ComintyError as exc:
            if not is_retryable_exception(exc) or attempt >= max_retries:
                raise
            last_exc = exc
            if on_retry is not None:
                on_retry(attempt, exc)
        except httpx.HTTPError as exc:
            wrapped = ComintyTimeoutError(str(exc)) if isinstance(
                exc, httpx.TimeoutException
            ) else ComintyError(str(exc))
            if attempt >= max_retries:
                raise wrapped from exc
            last_exc = wrapped
            if on_retry is not None:
                on_retry(attempt, wrapped)
    assert last_exc is not None
    raise last_exc


def check_response_retryable(status_code: int) -> bool:
    """Return True if an HTTP status code should trigger a retry."""
    return status_code in RETRYABLE_STATUS_CODES


def maybe_raise_for_status(status_code: int, body: object, message: str | None = None) -> None:
    """Raise typed exceptions, allowing callers to catch retryable ones."""
    if status_code >= 400:
        raise_for_status(status_code, body, message)
