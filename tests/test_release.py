"""Tests for the `release` invoke task in tasks.py.

Everything runs inside a disposable temp Git repo (see the `repo` fixture) —
never against this actual repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import tasks
from invoke import Context, Exit

_MINIMAL_PYPROJECT = """\
[project]
name = "scratch-pkg"
version = "{version}"
requires-python = ">=3.9"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def _git_out(*args: str) -> str:
    result = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _is_clean() -> bool:
    return _git_out("status", "--porcelain") == ""


def _pyproject_version() -> str:
    return tasks._read_version(Path("pyproject.toml").read_text())


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    _git("init", "-q")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    (tmp_path / "pyproject.toml").write_text(_MINIMAL_PYPROJECT.format(version="0.1.0"))
    subprocess.run(["uv", "lock"], check=True, capture_output=True)
    _git("add", "-A")
    _git("commit", "-q", "-m", "initial")
    # The SDK's own lint/type-check/test/build gate has nothing to check
    # against a scratch project — stub it out so tests only exercise the
    # version/Git logic.
    monkeypatch.setattr(tasks, "_run_validation", lambda c: None)
    return tmp_path


@pytest.fixture
def c() -> Context:
    return Context()


# --------------------------------------------------------------------------- #
# success
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"patch": True}, "0.1.1"),
        ({"minor": True}, "0.2.0"),
        ({"major": True}, "1.0.0"),
        ({"version": "5.2.1"}, "5.2.1"),
    ],
)
def test_release_success(
    repo: Path, c: Context, capsys: pytest.CaptureFixture[str], kwargs: dict, expected: str
) -> None:
    tasks.release(c, **kwargs)

    assert _pyproject_version() == expected
    assert f'version = "{expected}"' in (repo / "uv.lock").read_text()
    assert _git_out("log", "-1", "--format=%s") == f"chore(release): version {expected}"
    assert _git_out("cat-file", "-t", f"v{expected}") == "tag"  # annotated, not lightweight
    assert _is_clean()

    out = capsys.readouterr().out
    assert f"v{expected}" in out
    assert "git push" in out
    assert "gh release create" in out


# --------------------------------------------------------------------------- #
# failures — each must leave the repo untouched
# --------------------------------------------------------------------------- #
def test_release_no_mode_fails(repo: Path, c: Context) -> None:
    before = _git_out("rev-parse", "HEAD")
    with pytest.raises(Exit):
        tasks.release(c)
    assert _git_out("rev-parse", "HEAD") == before
    assert _is_clean()
    assert _pyproject_version() == "0.1.0"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"patch": True, "minor": True},
        {"patch": True, "version": "9.9.9"},
    ],
    ids=["two-flags", "flag-and-version"],
)
def test_release_multiple_modes_fails(repo: Path, c: Context, kwargs: dict) -> None:
    before = _git_out("rev-parse", "HEAD")
    with pytest.raises(Exit):
        tasks.release(c, **kwargs)
    assert _git_out("rev-parse", "HEAD") == before
    assert _is_clean()


@pytest.mark.parametrize("bad", ["not-a-version", "1.2", "1.2.3.4", "v1.2.3"])
def test_release_invalid_version_format_fails(repo: Path, c: Context, bad: str) -> None:
    before = _git_out("rev-parse", "HEAD")
    with pytest.raises(Exit):
        tasks.release(c, version=bad)
    assert _git_out("rev-parse", "HEAD") == before
    assert _is_clean()
    assert _pyproject_version() == "0.1.0"


def test_release_dirty_tree_fails(repo: Path, c: Context) -> None:
    (repo / "README.md").write_text("uncommitted change")
    before = _git_out("rev-parse", "HEAD")
    with pytest.raises(Exit):
        tasks.release(c, patch=True)
    assert _git_out("rev-parse", "HEAD") == before
    assert _pyproject_version() == "0.1.0"


@pytest.mark.parametrize("target", ["0.1.0", "0.0.9"], ids=["equal", "lower"])
def test_release_non_increasing_version_fails(repo: Path, c: Context, target: str) -> None:
    before = _git_out("rev-parse", "HEAD")
    with pytest.raises(Exit):
        tasks.release(c, version=target)
    assert _git_out("rev-parse", "HEAD") == before
    assert _is_clean()


def test_release_existing_tag_fails(repo: Path, c: Context) -> None:
    _git("tag", "v0.1.1")
    before = _git_out("rev-parse", "HEAD")
    with pytest.raises(Exit):
        tasks.release(c, patch=True)
    assert _git_out("rev-parse", "HEAD") == before
    assert _pyproject_version() == "0.1.0"
