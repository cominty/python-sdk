from __future__ import annotations

from typing import Any

from cominty_sdk.config import DEFAULT_BASE_URLS, ComintyEnvironment


class ComintyError(Exception):
    """Base exception for all Cominty SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body


class ComintyAPIError(ComintyError):
    """Raised when the API returns an error response."""


class AuthenticationError(ComintyAPIError):
    """Raised on 401 Unauthorized."""


class NotFoundError(ComintyAPIError):
    """Raised on 404 Not Found."""


class ValidationError(ComintyAPIError):
    """Raised on 422 Unprocessable Entity."""


class RateLimitError(ComintyAPIError):
    """Raised on 429 Too Many Requests."""


class ServerError(ComintyAPIError):
    """Raised on 5xx server errors."""


class ComintyTimeoutError(ComintyError):
    """Raised when a request or poll operation times out."""


class ComintyServerShuttingDownError(ComintyError):
    """Raised when the API returns a partial response due to server shutdown."""


def raise_for_status(status_code: int, body: Any, message: str | None = None) -> None:
    """Map HTTP status codes to typed exceptions."""
    msg = message or f"API request failed with status {status_code}"
    if status_code == 401:
        raise AuthenticationError(msg, status_code=status_code, body=body)
    if status_code == 404:
        raise NotFoundError(msg, status_code=status_code, body=body)
    if status_code == 422:
        raise ValidationError(msg, status_code=status_code, body=body)
    if status_code == 429:
        raise RateLimitError(msg, status_code=status_code, body=body)
    if 500 <= status_code < 600:
        raise ServerError(msg, status_code=status_code, body=body)
    if 400 <= status_code < 500:
        raise ComintyAPIError(msg, status_code=status_code, body=body)


def resolve_base_url(
    *,
    base_url: str | None = None,
    environment: ComintyEnvironment | str | None = None,
) -> str:
    """Resolve the API base URL from explicit override or environment name."""
    if base_url is not None:
        return base_url.rstrip("/")
    env = environment or ComintyEnvironment.PRODUCTION
    env_name = env.value if isinstance(env, ComintyEnvironment) else env
    try:
        return DEFAULT_BASE_URLS[env_name].rstrip("/")
    except KeyError as exc:
        raise ValueError(
            f"Unknown environment {env_name!r}. "
            f"Expected one of: {', '.join(DEFAULT_BASE_URLS)}"
        ) from exc
