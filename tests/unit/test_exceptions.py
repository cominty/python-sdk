from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from cominty_sdk import (
    APIError,
    AuthError,
    ConflictError,
    InvalidParams,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
)
from cominty_sdk.exceptions import error_from_response
from cominty_sdk.models.chat import HumanMessage


# --------------------------------------------------------------------------- #
# error_from_response: status-code mapping
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "status_code, expected_cls",
    [
        (401, AuthError),
        (403, PermissionError),
        (404, NotFoundError),
        (409, ConflictError),
        (500, ServerError),
        (503, ServerError),
        (418, APIError),  # unmapped 4xx falls back to the base class
    ],
)
def test_error_from_response_maps_status_code(status_code: int, expected_cls: type) -> None:
    err = error_from_response(status_code, {"detail": "boom"})

    assert isinstance(err, expected_cls)
    assert err.status_code == status_code
    assert err.detail == "boom"
    assert str(err) == "boom"


def test_error_from_response_maps_429_to_rate_limit_error() -> None:
    # 429's message is composed separately (see the dedicated tests below), so
    # it's excluded from the generic mapping test above.
    err = error_from_response(429, {"detail": "boom"})
    assert isinstance(err, RateLimitError)
    assert err.status_code == 429


def test_error_from_response_falls_back_to_generic_message_without_detail() -> None:
    err = error_from_response(404, {"other_field": "x"})

    assert err.detail is None
    assert str(err) == "HTTP 404"


def test_error_from_response_handles_non_dict_body() -> None:
    err = error_from_response(500, "plain text error page")

    assert err.detail is None
    assert err.body == "plain text error page"
    assert str(err) == "HTTP 500"


def test_error_from_response_handles_missing_body() -> None:
    err = error_from_response(500, None)

    assert err.detail is None
    assert err.body is None


# --------------------------------------------------------------------------- #
# RateLimitError.scope
# --------------------------------------------------------------------------- #
def test_scope_reads_quota_reached_from_detail() -> None:
    err = RateLimitError("x", status_code=429, detail={"quota_reached": "organization"})
    assert err.scope == "organization"


def test_scope_detects_concurrency_string() -> None:
    err = RateLimitError("x", status_code=429, detail="Too many concurrent requests")
    assert err.scope == "concurrency"


def test_scope_none_when_undeterminable() -> None:
    assert RateLimitError("x", status_code=429, detail=None).scope is None
    assert RateLimitError("x", status_code=429, detail={"other": 1}).scope is None
    assert RateLimitError("x", status_code=429, detail="unrelated message").scope is None


# --------------------------------------------------------------------------- #
# RateLimitError.retry_after
# --------------------------------------------------------------------------- #
def test_retry_after_reads_header() -> None:
    err = RateLimitError("x", status_code=429, headers={"Retry-After": "12.5"})
    assert err.retry_after == 12.5


def test_retry_after_accepts_lowercase_header() -> None:
    err = RateLimitError("x", status_code=429, headers={"retry-after": "3"})
    assert err.retry_after == 3.0


def test_retry_after_none_without_headers() -> None:
    assert RateLimitError("x", status_code=429, headers=None).retry_after is None


def test_retry_after_none_on_malformed_header() -> None:
    err = RateLimitError("x", status_code=429, headers={"Retry-After": "soon"})
    assert err.retry_after is None


def test_retry_after_none_when_header_absent_from_present_headers() -> None:
    err = RateLimitError("x", status_code=429, headers={"Content-Type": "application/json"})
    assert err.retry_after is None


# --------------------------------------------------------------------------- #
# RateLimitError.reset_at
# --------------------------------------------------------------------------- #
def test_reset_at_reads_detail_field() -> None:
    err = RateLimitError(
        "x", status_code=429, detail={"reset_at": "2026-06-28T10:00:00+00:00"}
    )
    assert err.reset_at == datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc)


def test_reset_at_falls_back_to_locked_until() -> None:
    err = RateLimitError(
        "x", status_code=429, detail={"locked_until": "2026-06-28T10:00:00+00:00"}
    )
    assert err.reset_at is not None


def test_reset_at_falls_back_to_header_without_detail() -> None:
    err = RateLimitError(
        "x",
        status_code=429,
        detail="Too many concurrent requests",
        headers={"X-RateLimit-Reset": "2026-06-28T10:00:00+00:00"},
    )
    assert err.reset_at is not None


def test_reset_at_falls_back_to_header_when_detail_dates_unparseable() -> None:
    err = RateLimitError(
        "x",
        status_code=429,
        detail={"quota_reached": "user"},  # no reset_at/locked_until
        headers={"X-RateLimit-Reset": "2026-06-28T10:00:00+00:00"},
    )
    assert err.reset_at is not None


def test_reset_at_none_when_date_is_unparseable() -> None:
    err = RateLimitError("x", status_code=429, detail={"reset_at": "not-a-date"})
    assert err.reset_at is None


def test_reset_at_none_when_nothing_available() -> None:
    assert RateLimitError("x", status_code=429).reset_at is None


# --------------------------------------------------------------------------- #
# 429 message composition (via error_from_response)
# --------------------------------------------------------------------------- #
def test_rate_limit_message_for_known_quota_scope() -> None:
    err = error_from_response(429, {"detail": {"quota_reached": "user"}})
    assert "User rate limit reached" in str(err)
    assert "organization admin" in str(err)


def test_rate_limit_message_for_forward_compatible_quota_scope() -> None:
    err = error_from_response(429, {"detail": {"quota_reached": "team"}})
    assert "Team rate limit reached" in str(err)


def test_rate_limit_message_for_concurrency() -> None:
    err = error_from_response(429, {"detail": "Too many concurrent requests"})
    assert "Too many concurrent requests" in str(err)


def test_rate_limit_message_falls_back_to_raw_detail_text() -> None:
    err = error_from_response(429, {"detail": "slow down"})
    assert str(err).startswith("slow down.")


def test_rate_limit_message_with_no_detail_at_all() -> None:
    err = error_from_response(429, {})
    assert str(err).startswith("Rate limit reached.")


def test_rate_limit_message_includes_retry_after_when_present() -> None:
    err = error_from_response(
        429, {"detail": {"quota_reached": "user"}}, headers={"Retry-After": "5"}
    )
    assert "retry in 5s" in str(err)


def test_rate_limit_message_includes_reset_at_when_no_retry_after() -> None:
    err = error_from_response(
        429, {"detail": {"quota_reached": "user", "reset_at": "2026-06-28T10:00:00+00:00"}}
    )
    assert "Quota resets at" in str(err)


def test_rate_limit_message_ignores_malformed_retry_after_header() -> None:
    err = error_from_response(
        429,
        {"detail": {"quota_reached": "user", "reset_at": "2026-06-28T10:00:00+00:00"}},
        headers={"Retry-After": "not-a-number"},
    )
    # Falls through to the reset_at phrasing instead of a "retry in ...s" one.
    assert "retry in" not in str(err)
    assert "Quota resets at" in str(err)


# --------------------------------------------------------------------------- #
# InvalidParams.from_validation_error
# --------------------------------------------------------------------------- #
def _validation_error() -> ValidationError:
    try:
        HumanMessage.model_validate({"content": 123, "file_ids": "not-a-list"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def test_from_validation_error_groups_one_entry_per_field() -> None:
    err = InvalidParams.from_validation_error(_validation_error(), context="chat.start")

    params = {e["param"] for e in err.errors}
    assert params == {"content", "file_ids"}
    assert "chat.start" in str(err)


def test_from_validation_error_deduplicates_repeated_messages_on_same_field() -> None:
    # Two errors at the same location with the identical message collapse into
    # one entry instead of repeating it.
    exc = ValidationError.from_exception_data(
        "Test",
        [
            {"type": "string_type", "loc": ("content",), "input": None},
            {"type": "string_type", "loc": ("content",), "input": None},
        ],
    )

    err = InvalidParams.from_validation_error(exc, context="ctx")

    assert len(err.errors) == 1
    assert err.errors[0]["message"].count("valid string") == 1


def test_from_validation_error_suppresses_input_for_missing_and_extra_forbidden() -> None:
    # "missing"/"extra_forbidden" carry the parent container as `input`, which
    # is noise: it's dropped rather than surfaced as the offending value.
    exc = ValidationError.from_exception_data(
        "Test",
        [
            {"type": "missing", "loc": ("purpose",), "input": {"content": "x"}},
            {"type": "extra_forbidden", "loc": ("bogus",), "input": {"content": "x"}},
        ],
    )

    err = InvalidParams.from_validation_error(exc, context="ctx")

    by_param = {e["param"]: e for e in err.errors}
    assert by_param["purpose"]["input"] is None
    assert by_param["bogus"]["input"] is None
    assert "(got" not in str(err)
