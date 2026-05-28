from __future__ import annotations

import os
from typing import Self

from pydantic_settings import BaseSettings, SettingsConfigDict

from cominty_sdk._auth import is_api_access_token
from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.config import (
    DEFAULT_AGENT_ID,
    DEFAULT_MAX_RETRIES,
    DEFAULT_STREAM_TIMEOUT,
    DEFAULT_TIMEOUT,
    ComintyEnvironment,
)
from cominty_sdk.exceptions import resolve_base_url
from cominty_sdk.resources.api_tokens import ApiTokensResource
from cominty_sdk.resources.chat import ChatResource
from cominty_sdk.resources.files import FilesResource
from cominty_sdk.resources.messages import MessagesResource
from cominty_sdk.resources.threads import ThreadsResource
from cominty_sdk.resources.usage import UsageResource


class ClientSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COMINTY_",
        env_file=".env",
        extra="ignore",
    )

    api_key: str | None = None
    api_url: str | None = None
    session_token: str | None = None
    environment: ComintyEnvironment = ComintyEnvironment.PRODUCTION
    agent_id: str | None = None
    user_id: str | None = None
    org_id: str | None = None
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout: float = DEFAULT_TIMEOUT
    stream_timeout: float = DEFAULT_STREAM_TIMEOUT


class AsyncCominty:
    """Async client for the Cominty managed agent chat API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        environment: ComintyEnvironment | str | None = None,
        session_token: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        org_id: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        settings = ClientSettings()
        resolved_api_key = api_key or settings.api_key or os.environ.get("COMINTY_API_KEY")
        resolved_session_token = (
            session_token or settings.session_token or os.environ.get("COMINTY_SESSION_TOKEN")
        )
        if not resolved_api_key and not resolved_session_token:
            raise ValueError(
                "Credentials required. Pass api_key= / COMINTY_API_KEY for chat, "
                "or session_token= / COMINTY_SESSION_TOKEN for admin token management."
            )
        resolved_base_url = resolve_base_url(
            base_url=base_url or settings.api_url,
            environment=environment or settings.environment,
        )
        resolved_agent_id = (
            agent_id
            or settings.agent_id
            or os.environ.get("COMINTY_AGENT_ID")
            or DEFAULT_AGENT_ID
        )
        resolved_user_id = user_id or settings.user_id or os.environ.get("COMINTY_USER_ID")
        resolved_org_id = org_id or settings.org_id or os.environ.get("COMINTY_ORG_ID")
        if max_retries != DEFAULT_MAX_RETRIES:
            resolved_max_retries = max_retries
        else:
            resolved_max_retries = settings.max_retries
        resolved_timeout = timeout if timeout != DEFAULT_TIMEOUT else settings.timeout
        resolved_stream_timeout = (
            stream_timeout
            if stream_timeout != DEFAULT_STREAM_TIMEOUT
            else settings.stream_timeout
        )
        api_mode = bool(resolved_api_key and is_api_access_token(resolved_api_key))

        if resolved_api_key:
            http = AsyncHTTPClient(
                base_url=resolved_base_url,
                api_key=resolved_api_key,
                org_id=resolved_org_id if not api_mode else None,
                max_retries=resolved_max_retries,
                timeout=resolved_timeout,
                stream_timeout=resolved_stream_timeout,
            )
            self._http: AsyncHTTPClient | None = http

            self.threads = ThreadsResource(
                http,
                default_user_id=resolved_user_id,
                api_mode=api_mode,
            )
            self.messages = MessagesResource(
                http,
                default_agent_id=resolved_agent_id,
                threads=self.threads,
            )
            self.chat = ChatResource(
                http,
                default_agent_id=resolved_agent_id,
                default_user_id=resolved_user_id,
                api_mode=api_mode,
                threads=self.threads,
                messages=self.messages,
            )
            self.files = FilesResource(http)
            self.usage = UsageResource(http)
        else:
            self._http = None
            self.threads = None  # type: ignore[assignment]
            self.messages = None  # type: ignore[assignment]
            self.chat = None  # type: ignore[assignment]
            self.files = None  # type: ignore[assignment]
            self.usage = None  # type: ignore[assignment]
        self.api_tokens: ApiTokensResource | None = None
        self._admin_http: AsyncHTTPClient | None = None
        if resolved_session_token:
            admin_http = AsyncHTTPClient(
                base_url=resolved_base_url,
                api_key=resolved_session_token,
                org_id=resolved_org_id,
                max_retries=resolved_max_retries,
                timeout=resolved_timeout,
                stream_timeout=resolved_stream_timeout,
            )
            self.api_tokens = ApiTokensResource(admin_http)
            self._admin_http = admin_http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()
        if self._admin_http is not None:
            await self._admin_http.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
