"""Shared setup for the example scripts.

Every example builds its client through :func:`make_client`, which reads
credentials from the environment:

    export COMINTY_API_KEY="<your API key>"      # platform.cominty.ai -> API keys
    export COMINTY_USER_ID="user_..."            # platform.cominty.ai -> Profile
    export COMINTY_AGENT_ID="__cominty_agents::agent.chat"   # optional, has a default

The SDK reads ``COMINTY_API_KEY``, ``COMINTY_USER_ID``
on its own. ``COMINTY_AGENT_ID`` is an example-only convenience (the SDK has no
agent default), so we resolve it here.
"""

from __future__ import annotations

import os

from cominty_sdk import AsyncCominty

# The platform's general-purpose chat agent. Override with COMINTY_AGENT_ID, or
# copy a specific agent's id from platform.cominty.ai -> Agents.
AGENT_ID = os.environ.get("COMINTY_AGENT_ID", "__cominty_agents::agent.chat")

# A custom agent you created on the platform (model + failover + instructions).
# Used by 07_custom_agent.py. Copy its id from platform.cominty.ai -> Agents.
CUSTOM_AGENT_ID = os.environ.get("COMINTY_CUSTOM_AGENT_ID")


def make_client() -> AsyncCominty:
    """Build a client from env vars (COMINTY_API_KEY + COMINTY_USER_ID)."""
    return AsyncCominty()
