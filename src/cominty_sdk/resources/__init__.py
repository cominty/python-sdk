"""Resource namespaces hung off the client."""

from __future__ import annotations

from .agents import AgentsResource
from .chat import ChatResource
from .threads import ThreadsResource

__all__ = ["AgentsResource", "ChatResource", "ThreadsResource"]
