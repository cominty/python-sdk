"""Resolved client configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["Config"]

_DEFAULT_BASE_URL = "https://ds.cominty.com"
_DEFAULT_TIMEOUT = 60.0
_TOKEN_ENV = "COMINTY_API_KEY"
_BASE_URL_ENV = "COMINTY_BASE_URL"


@dataclass(frozen=True)
class Config:
    """Immutable, fully-resolved client configuration. Built once at construction.

    Internal plumbing, not an I/O boundary — a frozen dataclass, not a pydantic
    model. Validation belongs on the request/response models.
    """

    api_token: str
    base_url: str
    timeout: float

    @classmethod
    def resolve(
        cls,
        *,
        api_token: str | None,
        base_url: str | None,
        timeout: float | None,
    ) -> Config:
        # Precedence: explicit argument -> environment -> default.
        token = api_token or os.getenv(_TOKEN_ENV)
        if not token:
            raise ValueError(
                f"api_token is required: pass api_token=... or set {_TOKEN_ENV} "
                "in the environment."
            )
        return cls(
            api_token=token,
            base_url=(base_url or os.getenv(_BASE_URL_ENV) or _DEFAULT_BASE_URL).rstrip(
                "/"
            ),
            timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
        )
