"""Resource namespaces hung off the client."""

from __future__ import annotations

from .chat import ChatResource
from .threads import ThreadsResource

__all__ = ["ChatResource", "ThreadsResource"]
