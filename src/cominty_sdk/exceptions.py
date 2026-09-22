from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypedDict, cast

from pydantic import ValidationError

if TYPE_CHECKING:
    from .models.chat import Message

__all__ = [
    "ComintyError",
    "APIError",
    "AuthError",
    "PermissionError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
    "APIConnectionError",
    "StreamInterrupted",
    "SDKError",
    "InvalidParam",
    "InvalidParams",
    "error_from_response",
]


class ComintyError(Exception):
    """Base class for every error raised by the SDK."""


class APIError(ComintyError):
    """An HTTP error response (4xx/5xx) from the Cominty API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        detail: str | dict[str, Any] | list[Any] | None = None,
        body: Any = None,  # noqa: ANN401 - raw decoded error body
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        """The parsed ``detail`` field: a string, an object, or a list (422)."""
        self.body = body
        """The full raw decoded response body, if any."""
        self.headers = headers


class AuthError(APIError):
    """401: missing or invalid ``x-cominty-token``."""


class PermissionError(APIError):  # noqa: A001 - intentional, namespaced under the SDK
    """403: authenticated but not allowed."""


class NotFoundError(APIError):
    """404: the resource does not exist."""


class ConflictError(APIError):
    """409: the request conflicts with the current state."""


class RateLimitError(APIError):
    """429: a rate limit was hit.

    The API hits this in one of three ways, surfaced via :attr:`scope`:

    - ``"concurrency"``: too many chat sessions running at once (your plan's
      concurrent-session cap). Transient: retry once an in-flight request finishes.
    - ``"organization"``: your organization's request quota is exhausted.
    - ``"user"``: your user's request quota is exhausted.

    For the quota cases an organization admin must raise the limit; the error
    message says so. :attr:`retry_after` exposes the ``Retry-After`` header if sent.
    """

    @property
    def scope(self) -> str | None:
        """
        Which limit was hit.

        Quota responses carry ``{"quota_reached": "organization" | "user"}``.
        The concurrency cap is the string ``"Too many concurrent requests"``.

        Returns:
            str | None: ``"organization"``, ``"user"``, ``"concurrency"``, or
                ``None`` when the body does not say.
        """
        if isinstance(self.detail, dict):
            quota = self.detail.get("quota_reached")
            if isinstance(quota, str) and quota:
                return quota
        if isinstance(self.detail, str) and "concurrent" in self.detail.lower():
            return "concurrency"
        return None

    @property
    def retry_after(self) -> float | None:
        """
        Seconds to wait before retrying.

        Returns:
            float | None: The ``Retry-After`` header, or ``None`` when it is absent
                or not a number.
        """
        if self.headers:
            raw = self.headers.get("Retry-After") or self.headers.get("retry-after")
            if raw is not None:
                try:
                    return float(raw)
                except ValueError:
                    pass
        return None

    @property
    def reset_at(self) -> datetime | None:
        """
        When the quota clears.

        Returns:
            datetime | None: ``reset_at`` or ``locked_until`` from the body, else
                the ``X-RateLimit-Reset`` header, else ``None``.
        """
        if isinstance(self.detail, dict):
            parsed = _parse_dt(self.detail.get("reset_at") or self.detail.get("locked_until"))
            if parsed is not None:
                return parsed
        if self.headers:
            return _parse_dt(self.headers.get("X-RateLimit-Reset"))
        return None


class ServerError(APIError):
    """5xx: the server failed to handle the request."""


class APIConnectionError(ComintyError):
    """The request never produced an HTTP response (network error or timeout)."""


class StreamInterrupted(ComintyError):
    """The server shut down mid-stream before the message completed.

    ``partial`` is the message as far as it got: its ``status`` reflects how
    much was persisted.
    """

    def __init__(self, message: str, *, partial: Message) -> None:
        super().__init__(message)
        self.partial = partial


class SDKError(ComintyError):
    """A bug inside the SDK. Should never reach users."""


class InvalidParam(TypedDict):
    """One offending parameter in an :class:`InvalidParams` error."""

    param: str
    """The public argument that failed, e.g. ``"disabled_tools[0]"``."""
    message: str
    """Why it failed (the underlying validation message)."""
    input: Any
    """The bad value (``None`` for missing/unexpected params)."""


class InvalidParams(ComintyError):
    """Arguments failed validation before any request was sent.

    Raised by the SDK at the call boundary so callers never see a raw pydantic
    ``ValidationError``. ``errors`` is the structured, typed breakdown: one entry
    per offending parameter.
    """

    def __init__(self, message: str, *, errors: list[InvalidParam]) -> None:
        super().__init__(message)
        self.errors = errors

    @classmethod
    def from_validation_error(cls, exc: ValidationError, *, context: str) -> InvalidParams:
        grouped: dict[str, dict[str, Any]] = {}
        for err in exc.errors(include_url=False):
            path = _clean_param_path(err["loc"])
            group = grouped.setdefault(path, {"msgs": [], "input": None, "show_input": False})
            if err["msg"] not in group["msgs"]:
                group["msgs"].append(err["msg"])
            # "missing"/"extra_forbidden" carry the parent container as input.
            # That value is noise, so don't surface it.
            if err["type"] not in _NO_INPUT_TYPES:
                group["show_input"] = True
                group["input"] = err.get("input")

        errors: list[InvalidParam] = []
        lines: list[str] = []
        for path, group in grouped.items():
            message = " / ".join(group["msgs"])
            errors.append(InvalidParam(param=path, message=message, input=group["input"]))
            suffix = f" (got {group['input']!r})" if group["show_input"] else ""
            lines.append(f"  - {path}: {message}{suffix}")

        body = "\n".join(lines)
        return cls(f"Invalid parameters for {context}:\n{body}", errors=errors)


_NO_INPUT_TYPES = frozenset({"missing", "extra_forbidden"})


def _clean_param_path(loc: tuple[str | int, ...]) -> str:
    # Drop message/options wrappers and pydantic tags such as "literal[...]"
    # or "constrained-str". Those segments contain "[" or "-".
    parts: list[str | int] = [
        seg for seg in loc if isinstance(seg, int) or ("[" not in seg and "-" not in seg)
    ]
    if parts and parts[0] in ("message", "options"):
        parts = parts[1:]

    out = ""
    for part in parts:
        out = f"{out}[{part}]" if isinstance(part, int) else (part if not out else f"{out}.{part}")
    return out or "(request)"


_STATUS_MAP: dict[int, type[APIError]] = {
    401: AuthError,
    403: PermissionError,
    404: NotFoundError,
    409: ConflictError,
    429: RateLimitError,
}


def error_from_response(
    status_code: int,
    body: Any,  # noqa: ANN401 - raw decoded error body
    headers: Mapping[str, str] | None = None,
) -> APIError:
    detail: str | dict[str, Any] | list[Any] | None = None
    if isinstance(body, dict):
        detail = cast("dict[str, Any]", body).get("detail")
    message = detail if isinstance(detail, str) else f"HTTP {status_code}"
    cls = _STATUS_MAP.get(status_code) or (ServerError if status_code >= 500 else APIError)
    # A bare "HTTP 429" is useless. Turn the server's terse detail into a clear,
    # actionable message (which limit was hit + what the caller can do).
    if cls is RateLimitError:
        message = _rate_limit_message(detail, headers)
    return cls(
        message,
        status_code=status_code,
        detail=detail,
        body=body,
        headers=headers,
    )


def _parse_dt(raw: object) -> datetime | None:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


_ADMIN_HINT = "Ask an organization admin to raise your plan's limit."

# Per-scope opener, made explicit so the caller knows *which* limit was hit.
_QUOTA_HEAD = {
    "organization": (
        "Organization rate limit reached: your organization's total request quota is exhausted"
    ),
    "user": "User rate limit reached: your user request quota is exhausted",
}


def _rate_limit_message(
    detail: str | dict[str, Any] | list[Any] | None,
    headers: Mapping[str, str] | None,
) -> str:
    info = detail if isinstance(detail, dict) else {}
    text = detail.strip() if isinstance(detail, str) else ""
    quota = info.get("quota_reached")

    if isinstance(quota, str) and quota in _QUOTA_HEAD:
        head = _QUOTA_HEAD[quota]
    elif isinstance(quota, str) and quota:  # forward-compat for a new scope name
        head = f"{quota.capitalize()} rate limit reached: request quota exhausted"
    elif "concurrent" in text.lower():
        # Concurrency cap (CHAT_MAX_CONCURRENT_SESSIONS_*): transient, the count
        # frees as in-flight requests finish, but raising it needs an admin.
        return (
            "Too many concurrent requests: your plan's limit on simultaneous chat "
            "sessions is reached. Wait for an in-flight request to finish and "
            f"retry, or raise the limit. {_ADMIN_HINT}"
        )
    else:
        head = text or "Rate limit reached"

    when = _when_phrase(_parse_dt(info.get("reset_at") or info.get("locked_until")), headers)
    tail = f" {when}" if when else ""
    return f"{head}. {_ADMIN_HINT}{tail}"


def _when_phrase(reset_at: datetime | None, headers: Mapping[str, str] | None) -> str:
    if headers:
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw is not None:
            try:
                return f"You can retry in {float(raw):g}s."
            except ValueError:
                pass
    if reset_at is not None:
        return f"Quota resets at {reset_at.isoformat()}."
    return ""
