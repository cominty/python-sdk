from __future__ import annotations

import re
from pathlib import Path

from invoke import Exit, task
from packaging.version import InvalidVersion, Version

TESTPYPI_URL = "https://test.pypi.org/legacy/"


@task
def clean(c):
    """Remove build artifacts so we never ship/inspect stale files."""
    c.run("rm -rf dist build src/*.egg-info *.egg-info", echo=True)


@task(pre=[clean])
def build(c):
    """Build the sdist and wheel into dist/."""
    c.run("uv build", echo=True)


@task(pre=[build])
def check(c):
    """Build, validate metadata/README rendering, and print artifact contents."""
    c.run("uv run twine check dist/*", echo=True)
    print("\n--- sdist contents (should contain NO legacy/, .env, test.py) ---")
    c.run("tar tzf dist/*.tar.gz", echo=True)
    print("\n--- wheel contents (confirm py.typed is present) ---")
    c.run("unzip -l dist/*.whl", echo=True)


@task(
    pre=[check],
    help={"token": "TestPyPI API token. Or set UV_PUBLISH_TOKEN in the env."},
)
def publish_test(c, token=None):
    """Upload to TestPyPI (rehearsal: never burns a real PyPI version)."""
    cmd = f"uv publish --publish-url {TESTPYPI_URL}"
    if token:
        cmd += f" --token {token}"
    c.run(cmd, echo=True)
    print(
        "\nVerify the upload in a clean env:\n"
        "  uv run --isolated --no-project \\\n"
        "    --index https://test.pypi.org/simple/ \\\n"
        "    --index-strategy unsafe-best-match \\\n"
        '    --with cominty-sdk python -c "import cominty_sdk; print(cominty_sdk.__version__)"'
    )


@task(
    pre=[check],
    help={"token": "PyPI API token. Or set UV_PUBLISH_TOKEN. Prefer CI/OIDC instead."},
)
def publish(c, token=None):
    """Upload to real PyPI. Prefer the GitHub Release CI flow (OIDC) over this."""
    cmd = "uv publish"
    if token:
        cmd += f" --token {token}"
    c.run(cmd, echo=True)


# --------------------------------------------------------------------------- #
# release
# --------------------------------------------------------------------------- #
PYPROJECT_PATH = Path("pyproject.toml")
UV_LOCK_PATH = Path("uv.lock")

_VERSION_LINE_RE = re.compile(r'(?m)^(version = ")([^"]+)(")')
_XYZ_RE = re.compile(r"\d+\.\d+\.\d+")


def _read_version(text: str) -> str:
    match = _VERSION_LINE_RE.search(text)
    if match is None:
        raise Exit('could not find `version = "..."` in pyproject.toml')
    current = match.group(2)
    if not _XYZ_RE.fullmatch(current):
        raise Exit(
            f"pyproject.toml's version {current!r} isn't X.Y.Z: fix it manually first"
        )
    return current


def _write_version(text: str, new_version: str) -> str:
    return _VERSION_LINE_RE.sub(rf"\g<1>{new_version}\g<3>", text, count=1)


def _bump(current: str, part: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _validate_explicit_version(value: str) -> None:
    if not _XYZ_RE.fullmatch(value):
        raise Exit(f"--version must be X.Y.Z (three dot-separated integers), got {value!r}")
    try:
        Version(value)
    except InvalidVersion as exc:
        raise Exit(f"{value!r} is not a valid PEP 440 version: {exc}") from exc


def _git_is_dirty(c) -> bool:
    result = c.run("git status --porcelain", hide=True, warn=True, in_stream=False)
    return bool(result.stdout.strip())


def _tag_exists(c, tag: str) -> bool:
    result = c.run(
        f"git rev-parse -q --verify refs/tags/{tag}", hide=True, warn=True, in_stream=False
    )
    return result.ok


def _run_validation(c) -> None:
    c.run("uv run ruff check .", echo=True, in_stream=False)
    c.run("uv run pyright", echo=True, in_stream=False)
    c.run("uv run pytest", echo=True, in_stream=False)
    c.run("uv run invoke check", echo=True, in_stream=False)


@task(
    help={
        "patch": "Bump the patch version: X.Y.Z -> X.Y.(Z+1)",
        "minor": "Bump the minor version: X.Y.Z -> X.(Y+1).0",
        "major": "Bump the major version: X.Y.Z -> (X+1).0.0",
        "version": "Set an explicit target version X.Y.Z instead of incrementing",
    }
)
def release(c, patch=False, minor=False, major=False, version=None):
    """Bump the version and cut a release commit + tag.

    WARNING: this modifies repository files and CREATES A GIT COMMIT AND TAG.
    It never pushes and never creates a GitHub Release: run the commands it
    prints at the end to do that yourself.

    Exactly one of --patch/--minor/--major/--version is required.
    """
    modes = {"patch": patch, "minor": minor, "major": major, "version": version is not None}
    selected = [name for name, on in modes.items() if on]
    if len(selected) != 1:
        raise Exit(
            "exactly one of --patch/--minor/--major/--version is required "
            f"(got {selected or 'none'})"
        )

    if not PYPROJECT_PATH.exists():
        raise Exit("pyproject.toml not found: run this from the repo root")

    original_pyproject = PYPROJECT_PATH.read_text()
    current = _read_version(original_pyproject)

    if version is not None:
        _validate_explicit_version(version)
        target = version
    else:
        target = _bump(current, selected[0])

    if Version(target) <= Version(current):
        raise Exit(f"target version {target} is not greater than the current version {current}")

    tag = f"v{target}"

    if _git_is_dirty(c):
        raise Exit("git working tree is dirty: commit or stash changes before releasing")
    if _tag_exists(c, tag):
        raise Exit(f"tag {tag} already exists")

    original_uv_lock = UV_LOCK_PATH.read_text() if UV_LOCK_PATH.exists() else None

    def _rollback() -> None:
        PYPROJECT_PATH.write_text(original_pyproject)
        if original_uv_lock is not None:
            UV_LOCK_PATH.write_text(original_uv_lock)
        elif UV_LOCK_PATH.exists():
            UV_LOCK_PATH.unlink()

    PYPROJECT_PATH.write_text(_write_version(original_pyproject, target))
    try:
        c.run("uv lock", echo=True, in_stream=False)
        _run_validation(c)
    except Exception:
        _rollback()
        raise

    c.run(f"git add {PYPROJECT_PATH} {UV_LOCK_PATH}", echo=True, in_stream=False)
    c.run(f'git commit -m "chore(release): version {target}"', echo=True, in_stream=False)
    c.run(f'git tag -a {tag} -m "{tag}"', echo=True, in_stream=False)

    print(
        f"\nCreated commit and tag {tag} locally. Nothing was pushed. Next steps:\n\n"
        f"  git push origin HEAD\n"
        f"  git push origin {tag}\n"
        f"  gh release create {tag} --title {tag} --generate-notes\n"
    )
