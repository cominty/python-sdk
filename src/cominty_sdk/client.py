from __future__ import annotations

import os
from typing import Self

from pydantic_settings import BaseSettings, SettingsConfigDict

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.config import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_STREAM_TIMEOUT,
    DEFAULT_TIMEOUT,
    ComintyEnvironment,
)
from cominty_sdk.exceptions import resolve_base_url
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
    environment: ComintyEnvironment = ComintyEnvironment.PRODUCTION
    agent_id: str | None = None
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
        agent_id: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        settings = ClientSettings()
        resolved_api_key = api_key or settings.api_key or os.environ.get("COMINTY_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "API key is required. Pass api_key= or set COMINTY_API_KEY."
            )

        resolved_base_url = resolve_base_url(
            base_url=base_url or settings.api_url,
            environment=environment or settings.environment,
        )
        resolved_agent_id = agent_id or settings.agent_id
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

        self._http = AsyncHTTPClient(
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            max_retries=resolved_max_retries,
            timeout=resolved_timeout,
            stream_timeout=resolved_stream_timeout,
        )

        self.threads = ThreadsResource(self._http)
        self.messages = MessagesResource(
            self._http,
            default_agent_id=resolved_agent_id,
            threads=self.threads,
        )
        self.chat = ChatResource(
            self._http,
            default_agent_id=resolved_agent_id,
            threads=self.threads,
            messages=self.messages,
        )
        self.files = FilesResource(self._http)
        self.usage = UsageResource(self._http)

    async def close(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
