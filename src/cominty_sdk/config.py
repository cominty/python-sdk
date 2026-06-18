from enum import StrEnum
from typing import Literal

DEFAULT_API_URL = "https://ds.cominty.com"
DEFAULT_AGENT_ID = "__cominty_agents::agent.chat"

DEFAULT_BASE_URLS: dict[str, str] = {
    "dev": "https://ds-dev.cominty.com",
    "staging": "https://api.staging.cominty.com",
    "production": DEFAULT_API_URL,
}


class ComintyEnvironment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


EnvironmentName = Literal["dev", "staging", "production"]

DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60.0
DEFAULT_STREAM_TIMEOUT = 300.0
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_POLL_TIMEOUT = 120.0

# Message statuses that indicate the agent is still processing.
NON_TERMINAL_STATUSES = frozenset({"pending", "running", "in_progress", "processing"})

TERMINAL_STATUSES = frozenset({"success", "completed", "error", "cancelled", "failed"})

# Header used for API key authentication.
AUTH_HEADER = "x-cominty-token"
ORG_ID_HEADER = "x-cmt-current-org-id"
