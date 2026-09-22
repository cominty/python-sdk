from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["Config"]

_DEFAULT_BASE_URL = "https://ds.cominty.com"
_DEFAULT_TIMEOUT = 60.0
_TOKEN_ENV = "COMINTY_API_KEY"
_BASE_URL_ENV = "COMINTY_BASE_URL"
_USER_ID_ENV = "COMINTY_USER_ID"


@dataclass(frozen=True)
class Config:
    # Frozen dataclass, not a pydantic model: this layer only resolves values.

    api_token: str
    user_id: str
    base_url: str
    timeout: float

    @classmethod
    def resolve(
        cls,
        *,
        api_token: str | None,
        user_id: str | None,
        base_url: str | None,
        timeout: float | None,
    ) -> Config:
        # Precedence: explicit argument -> environment -> default.
        token = api_token or os.getenv(_TOKEN_ENV)
        if not token:
            raise ValueError(
                f"api_token is required: pass api_token=... or set {_TOKEN_ENV} in the environment."
            )
        resolved_user_id = user_id or os.getenv(_USER_ID_ENV)
        if not resolved_user_id:
            raise ValueError(
                f"user_id is required: pass user_id=... or set {_USER_ID_ENV} in "
                "the environment. Find yours at platform.cominty.ai -> avatar "
                "(top right) -> Profile."
            )
        return cls(
            api_token=token,
            user_id=resolved_user_id,
            base_url=(base_url or os.getenv(_BASE_URL_ENV) or _DEFAULT_BASE_URL).rstrip("/"),
            timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
        )
