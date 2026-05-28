#!/usr/bin/env python3
"""List agents using COMINTY_API_KEY (command-line smoke test)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

from cominty_sdk._auth import build_auth_headers
from cominty_sdk.config import DEFAULT_API_URL


def required_env() -> tuple[str, str, str]:
    api_key = os.environ.get("COMINTY_API_KEY")
    api_url = os.environ.get("COMINTY_API_URL", DEFAULT_API_URL).rstrip("/")
    user_id = os.environ.get("COMINTY_USER_ID", "user_123")

    if not api_key:
        print("Missing COMINTY_API_KEY")
        print()
        print("Example:")
        print('  export COMINTY_API_KEY="<access_token from POST /api-tokens>"')
        print(f'  # optional: COMINTY_API_URL (default: {DEFAULT_API_URL})')
        print('  export COMINTY_USER_ID="user_123"')
        print("  uv run python scripts/list_agents.py")
        sys.exit(1)

    return api_key, api_url, user_id


def print_section(title: str, response: httpx.Response) -> None:
    print(f"\n=== {title} ===")
    print(f"HTTP {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(response.text)


async def main() -> int:
    api_key, base_url, user_id = required_env()
    headers = build_auth_headers(api_key=api_key)

    print(f"Base URL: {base_url}")
    print(f"User ID:  {user_id}")
    print("Auth:     x-cominty-token / Authorization (auto-detected)")

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        agents_response = await client.get("/agents", headers=headers)
        print_section("GET /agents", agents_response)

        chat_no_user = await client.get("/chat", headers=headers, params={"limit": 10})
        print_section("GET /chat (no user_id)", chat_no_user)

        chat_response = await client.get(
            "/chat",
            headers=headers,
            params={"limit": 50, "user_id": user_id},
        )
        print_section(f"GET /chat?user_id={user_id}", chat_response)

        agents: dict[str, str] = {}
        if chat_response.is_success:
            for item in chat_response.json():
                agent = item.get("agent") or {}
                agent_id = agent.get("id")
                if agent_id:
                    agents[str(agent_id)] = str(agent.get("name") or agent_id)

        print("\n=== Agents deduced from threads ===")
        if agents:
            for agent_id, name in agents.items():
                print(f"- {name} ({agent_id})")
        else:
            print("No agents found (empty thread list for this user_id).")

    if agents_response.is_success:
        return 0
    if agents:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
