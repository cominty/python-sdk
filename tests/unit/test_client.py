"""Client construction: user_id is mandatory and validated up front."""

from __future__ import annotations

import pytest

from cominty_sdk import AsyncCominty

VALID_USER_ID = "user_31HPTBuBvX20xlQNAbvxjOxPbKB"


def test_user_id_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMINTY_USER_ID", raising=False)
    with pytest.raises(ValueError, match="user_id is required"):
        AsyncCominty(api_token="t")


def test_user_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMINTY_USER_ID", VALID_USER_ID)
    client = AsyncCominty(api_token="t", base_url="https://x.test")
    assert client.user_id == VALID_USER_ID


def test_explicit_user_id_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMINTY_USER_ID", "user_envenvenvenvenvenvenv")
    client = AsyncCominty(api_token="t", user_id=VALID_USER_ID, base_url="https://x.test")
    assert client.user_id == VALID_USER_ID


@pytest.mark.parametrize("bad", ["", "nope", "user_short", "31HPTBuBvX20xlQNAbvx" * 2])
def test_malformed_user_id_rejected_locally(
    bad: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COMINTY_USER_ID", raising=False)
    with pytest.raises(ValueError):
        AsyncCominty(api_token="t", user_id=bad, base_url="https://x.test")


def test_api_token_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMINTY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="api_token is required"):
        AsyncCominty(user_id=VALID_USER_ID)


def test_base_url_exposed_and_defaulted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMINTY_BASE_URL", raising=False)
    explicit = AsyncCominty(api_token="t", user_id=VALID_USER_ID, base_url="https://x.test/")
    assert explicit.base_url == "https://x.test"  # trailing slash stripped

    default = AsyncCominty(api_token="t", user_id=VALID_USER_ID)
    assert default.base_url == "https://ds.cominty.com"
