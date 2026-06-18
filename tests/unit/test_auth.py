from cominty_sdk._auth import (
    build_auth_headers,
    is_api_access_token,
    is_clerk_session_jwt,
    normalize_bearer_token,
)

API_ACCESS_TOKEN = (
    "eyJ0b2tlbl9pZCI6Ijg4MjkxM2I3LTE3YTktNDJjYy05OTk3LWIxZjhjYTNkMDZmYyJ9"
    ".ahha0Q.6R-o8oGnGefSFeDZ-5mc7OXrDMc"
)
CLERK_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + ("a" * 120) + ".signature"


def test_api_token_uses_x_cominty_token_with_bearer_prefix() -> None:
    headers = build_auth_headers(api_key=API_ACCESS_TOKEN, org_id="8")
    assert headers["x-cominty-token"] == f"Bearer {API_ACCESS_TOKEN}"
    assert headers["x-cmt-current-org-id"] == "8"
    assert "Authorization" not in headers


def test_plain_api_token_gets_bearer_prefix_on_cominty_header() -> None:
    headers = build_auth_headers(api_key="secret-token")
    assert headers == {"x-cominty-token": "Bearer secret-token"}


def test_clerk_session_jwt_uses_authorization_header() -> None:
    headers = build_auth_headers(api_key=CLERK_JWT, org_id="8")
    assert headers["Authorization"] == f"Bearer {CLERK_JWT}"
    assert headers["x-cmt-current-org-id"] == "8"
    assert "x-cominty-token" not in headers


def test_bearer_prefix_normalization() -> None:
    assert normalize_bearer_token("Bearer abc") == "Bearer abc"
    assert normalize_bearer_token("abc") == "Bearer abc"


def test_clerk_session_detection() -> None:
    assert is_clerk_session_jwt(CLERK_JWT) is True
    assert is_clerk_session_jwt(API_ACCESS_TOKEN) is False
    assert is_api_access_token(API_ACCESS_TOKEN) is True
    assert is_api_access_token(CLERK_JWT) is False
