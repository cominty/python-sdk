"""Developer tasks. Run with `uv run invoke <task>` (e.g. `uv run invoke publish-test`).

List tasks:        uv run invoke --list
Build + validate:  uv run invoke check
Dry-run to TestPyPI: uv run invoke publish-test
Real release:      done via CI on GitHub Release (see .github/workflows/release.yml)
"""

from __future__ import annotations

from invoke import task

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
    """Upload to TestPyPI (rehearsal — never burns a real PyPI version)."""
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
