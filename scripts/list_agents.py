#!/usr/bin/env python3
"""List org agents via the SDK (GET /agents, with thread fallback)."""

from __future__ import annotations

import asyncio
import json
import os

from cominty_sdk import AsyncCominty
from cominty_sdk._auth import (
    clerk_jwt_org_id,
    clerk_jwt_user_id,
    decode_jwt_payload_unverified,
    is_clerk_session_jwt,
)
from cominty_sdk.exceptions import ComintyAPIError


def _print_agents(agents, *, source: str) -> None:
    print(f"\n{source}: {len(agents)} agent(s)\n")
    for agent in agents:
        print(f"- {agent.name}")
        print(f"  id:   {agent.id}")
        print(f"  mode: {agent.mode}")
        if agent.description:
            print(f"  note: {agent.description[:160]}")
        print()


def _print_session_hints(session_token: str, base_url: str) -> None:
    if not is_clerk_session_jwt(session_token):
        print("COMINTY_SESSION_TOKEN does not look like a Clerk JWT (short token?).")
        print("Use the browser session JWT (long), not the COMINTY_API_KEY access token.")
        return

    payload = decode_jwt_payload_unverified(session_token)
    issuer = str(payload.get("iss", ""))
    org_id = clerk_jwt_org_id(session_token)
    user_id = clerk_jwt_user_id(session_token)

    print("Session JWT detected:")
    if issuer:
        print(f"  issuer: {issuer}")
    if org_id:
        print(f"  org_id: {org_id}")
    if user_id:
        print(f"  user_id: {user_id}")

    if "clerk.accounts.dev" in issuer and "dev.cominty.com" not in base_url:
        print(
            "\nLikely mismatch: dev Clerk JWT but API base is not dev."
            "\n  export COMINTY_ENVIRONMENT=dev"
            "\n  # or COMINTY_API_URL=https://ds-dev.cominty.com"
        )


async def main() -> int:
    api_key = os.environ.get("COMINTY_API_KEY")
    session_token = os.environ.get("COMINTY_SESSION_TOKEN")

    if not api_key and not session_token:
        print("Missing COMINTY_API_KEY or COMINTY_SESSION_TOKEN")
        print('  export COMINTY_SESSION_TOKEN="<Clerk JWT from browser>"')
        print("  export COMINTY_ENVIRONMENT=dev   # if using dev Clerk")
        print("  uv run python scripts/list_agents.py")
        return 1

    async with AsyncCominty() as client:
        print(f"API base URL: {client.base_url}")
        print(f"COMINTY_API_KEY set: {bool(api_key)}")
        print(f"COMINTY_SESSION_TOKEN set: {bool(session_token)}")
        if session_token:
            _print_session_hints(session_token, client.base_url)

        try:
            agents = await client.agents.list()
            _print_agents(agents, source="GET /agents")
            return 0
        except ComintyAPIError as exc:
            print(f"\nGET /agents failed: {exc}")
            if exc.body is not None:
                print(json.dumps(exc.body, indent=2, ensure_ascii=False))
            if (
                session_token
                and exc.status_code == 403
                and is_clerk_session_jwt(session_token)
            ):
                issuer = str(
                    decode_jwt_payload_unverified(session_token).get("iss", "")
                )
                if "clerk.accounts.dev" in issuer and "dev.cominty.com" not in client.base_url:
                    print(
                        "\nFix: your Clerk JWT is from dev but the API URL is not."
                        "\n  export COMINTY_ENVIRONMENT=dev"
                        "\n  # or COMINTY_API_URL=https://ds-dev.cominty.com"
                    )

        user_id = os.environ.get("COMINTY_USER_ID")
        if not user_id and session_token:
            user_id = clerk_jwt_user_id(session_token)

        if not user_id:
            print("\nSet COMINTY_USER_ID for thread fallback, or fix session/API URL above.")
            return 1

        if client.threads is None:
            print("\nThread fallback unavailable (chat client not initialized).")
            return 1

        try:
            discovered = await client.agents.list_discovered(user_id=user_id)
        except Exception as exc:
            print(f"\nThread fallback failed: {exc}")
            return 1

        if not discovered:
            print(f"\nNo agents found in recent threads for user_id={user_id}.")
            return 1

        _print_agents(discovered, source="Discovered from threads")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
