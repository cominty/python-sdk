API_TOKEN_HEADER = "x-cominty-token"
ORG_ID_HEADER = "x-cmt-current-org-id"


def strip_bearer_prefix(token: str) -> str:
    value = token.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def normalize_bearer_token(token: str) -> str:
    """Return a Bearer authorization value."""
    return f"Bearer {strip_bearer_prefix(token)}"


def is_clerk_session_jwt(token: str) -> bool:
    """Detect short-lived Clerk JWTs used by the web app."""
    parts = strip_bearer_prefix(token).split(".")
    if len(parts) != 3:
        return False
    # Clerk JWT payloads are large base64 blobs; API tokens are compact signed values.
    return len(parts[1]) > 100


def is_api_access_token(token: str) -> bool:
    """Return True for API access tokens created via POST /api-tokens."""
    return not is_clerk_session_jwt(token)


def build_auth_headers(*, api_key: str, org_id: str | None = None) -> dict[str, str]:
    """Build auth headers for Cominty API tokens or Clerk session JWTs."""
    headers: dict[str, str] = {}
    if is_clerk_session_jwt(api_key):
        headers["Authorization"] = normalize_bearer_token(api_key)
    else:
        headers[API_TOKEN_HEADER] = normalize_bearer_token(api_key)
    if org_id:
        headers[ORG_ID_HEADER] = org_id.strip()
    return headers
