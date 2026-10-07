import importlib.metadata
from typing import NoReturn

import pytest

import cominty_sdk


def test_version_matches_installed_metadata() -> None:
    assert cominty_sdk.__version__ == importlib.metadata.version("cominty-sdk")


def test_version_falls_back_when_metadata_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_not_found(name: str) -> NoReturn:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", raise_not_found)

    importlib.reload(cominty_sdk)
    try:
        assert cominty_sdk.__version__ == "unknown"
    finally:
        importlib.reload(cominty_sdk)
