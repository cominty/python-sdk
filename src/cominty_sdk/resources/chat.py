from __future__ import annotations

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk.config import DEFAULT_AGENT_ID, DEFAULT_POLL_INTERVAL, DEFAULT_POLL_TIMEOUT
from cominty_sdk.models.messages import HumanMessage, MessageOut, StartChatOptions, StartChatRequest
from cominty_sdk.models.threads import ThreadOut
from cominty_sdk.resources.messages import MessagesResource
from cominty_sdk.resources.threads import ThreadsResource


class ChatResource:
    """High-level chat operations (start new threads)."""

    def __init__(
        self,
        http: AsyncHTTPClient,
        *,
        default_agent_id: str | None,
        default_user_id: str | None,
        api_mode: bool,
        threads: ThreadsResource,
        messages: MessagesResource,
    ) -> None:
        self._http = http
        self._default_agent_id = default_agent_id
        self._default_user_id = default_user_id
        self._api_mode = api_mode
        self._threads = threads
        self._messages = messages

    def _resolve_agent_id(self, agent_id: str | None) -> str:
        return agent_id or self._default_agent_id or DEFAULT_AGENT_ID

    def _resolve_user_id(self, user_id: str | None) -> str | None:
        resolved = user_id or self._default_user_id
        if self._api_mode and not resolved:
            raise ValueError(
                "user_id is required in API mode. Pass user_id= or set COMINTY_USER_ID."
            )
        return resolved

    async def start(
        self,
        message: HumanMessage,
        *,
        agent_id: str | None = None,
        user_id: str | None = None,
        name: str | None = None,
    ) -> ThreadOut:
        """Create a thread and send the first message."""
        request = StartChatRequest(
            message=message,
            options=StartChatOptions(
                agent_id=self._resolve_agent_id(agent_id),
                user_id=self._resolve_user_id(user_id),
            ),
            name=name,
        )
        return await self._http.request_model(
            "POST",
            "/chat",
            ThreadOut,
            json=request.model_dump(exclude_none=True),
        )

    async def start_and_wait(
        self,
        message: HumanMessage,
        *,
        agent_id: str | None = None,
        user_id: str | None = None,
        name: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> tuple[ThreadOut, MessageOut]:
        """Start a thread and wait for the agent response to complete."""
        thread = await self.start(
            message,
            agent_id=agent_id,
            user_id=user_id,
            name=name,
        )
        if not thread.messages:
            raise ValueError("Thread returned without messages.")
        last_message = thread.messages[-1]
        completed = await self._messages.wait_until_done(
            last_message.id,
            thread_id=thread.id,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        return thread, completed
