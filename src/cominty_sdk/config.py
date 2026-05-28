from enum import StrEnum
from typing import Literal

DEFAULT_BASE_URLS: dict[str, str] = {
    "dev": "https://api.dev.cominty.com",
    "staging": "https://api.staging.cominty.com",
    "production": "https://api.cominty.com",
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

# Header used for API key authentication.
AUTH_HEADER = "x-cominty-token"
