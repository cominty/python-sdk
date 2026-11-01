from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import cast

import httpx
import pytest
import respx

from cominty_sdk import APIError, AsyncCominty, InvalidParams, NotFoundError, SkillOut, SkillSource
from cominty_sdk._uploads import zip_folder
from cominty_sdk.resources.skills import _MAX_ZIP_BYTES

SKILL_ID = "skl_V1StGXR8_Z5jdHi6B"
FRONTMATTER = "---\nname: release-notes\ndescription: Write release notes from a diff.\n---\n"


def _skill(**overrides: object) -> dict[str, object]:
    return {
        "id": SKILL_ID,
        "created_at": "2026-06-28T10:00:00Z",
        "updated_at": "2026-06-28T10:00:00Z",
        "display_name": "Release notes",
        "active": True,
        "scope": "private",
        "source": "custom",
        "frontmatter": {
            "name": "release-notes",
            "description": "Write release notes from a diff.",
            "license": None,
            "compatibility": None,
            "metadata": {},
            "allowed_tools": [],
        },
        **overrides,
    }


def _zip_part(request: httpx.Request) -> tuple[str, bytes]:
    # Pull the "file" part out of the multipart body: its filename and raw bytes.
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    for part in request.content.split(b"--" + boundary):
        if b'name="file"' in part:
            headers, _, body = part.partition(b"\r\n\r\n")
            match = re.search(rb'filename="([^"]+)"', headers)
            assert match is not None
            return match.group(1).decode(), body.rstrip(b"\r\n")
    raise AssertionError("no file part in the multipart body")


def _form_fields(request: httpx.Request) -> dict[str, str]:
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields: dict[str, str] = {}
    for part in request.content.split(b"--" + boundary):
        if b'name="' in part and b'name="file"' not in part:
            headers, _, body = part.partition(b"\r\n\r\n")
            match = re.search(rb'name="([^"]+)"', headers)
            assert match is not None
            fields[match.group(1).decode()] = body.rstrip(b"\r\n").decode()
    return fields


@pytest.fixture
def skill_folder(tmp_path: Path) -> Path:
    root = tmp_path / "release-notes"
    root.mkdir()
    (root / "SKILL.md").write_text(FRONTMATTER + "Steps...")
    (root / "scripts").mkdir()
    (root / "scripts" / "run.py").write_text("print('hi')")
    (root / ".DS_Store").write_bytes(b"junk")
    return root


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
async def test_list_returns_skills(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    mock_api.get("/skills").mock(
        return_value=httpx.Response(
            200, json=[_skill(), _skill(id="skl_builtin", source="cominty", scope=None)]
        )
    )

    skills = await client.skills.list()

    assert all(isinstance(s, SkillOut) for s in skills)
    assert skills[0].frontmatter.name == "release-notes"
    assert skills[1].source is SkillSource.cominty
    assert skills[1].scope is None


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
async def test_create_zips_a_folder_and_posts_multipart(
    client: AsyncCominty, mock_api: respx.MockRouter, skill_folder: Path
) -> None:
    route = mock_api.post("/skills").mock(return_value=httpx.Response(201, json=_skill()))

    skill = await client.skills.create(skill_folder, display_name="Release notes")

    assert isinstance(skill, SkillOut)
    request = route.calls.last.request
    assert "x-cominty-token" in request.headers
    assert _form_fields(request) == {"display_name": "Release notes", "scope": "private"}
    filename, content = _zip_part(request)
    assert filename == "release-notes.zip"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        # SKILL.md at the root (layout A), nested files kept, hidden files dropped.
        assert sorted(archive.namelist()) == ["SKILL.md", "scripts/run.py"]
        assert archive.read("SKILL.md").startswith(b"---\nname: release-notes")


@pytest.mark.parametrize(
    "parents",
    [
        pytest.param((".claude", "skills"), id="under-a-dot-folder"),
        pytest.param((".cursor", "skills", "team"), id="nested-under-a-dot-folder"),
    ],
)
async def test_create_zips_a_folder_living_under_a_dot_folder(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    tmp_path: Path,
    parents: tuple[str, ...],
) -> None:
    root = tmp_path.joinpath(*parents, "release-notes")
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(FRONTMATTER + "Steps...")
    (root / "scripts" / ".cache").mkdir(parents=True)
    (root / "scripts" / "run.py").write_text("print('hi')")
    (root / "scripts" / ".cache" / "run.pyc").write_bytes(b"junk")
    route = mock_api.post("/skills").mock(return_value=httpx.Response(201, json=_skill()))

    await client.skills.create(root, display_name="Release notes")

    _, content = _zip_part(route.calls.last.request)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        # Only dot entries inside the skill are dropped, never the folders above it.
        assert sorted(archive.namelist()) == ["SKILL.md", "scripts/run.py"]


async def test_create_zips_a_relative_folder_path(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    skill_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = skill_folder.parent / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    route = mock_api.post("/skills").mock(return_value=httpx.Response(201, json=_skill()))

    await client.skills.create(Path("..") / "release-notes", display_name="Release notes")

    filename, content = _zip_part(route.calls.last.request)
    assert filename == "release-notes.zip"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert sorted(archive.namelist()) == ["SKILL.md", "scripts/run.py"]


async def test_create_sends_a_zip_path_as_is(
    client: AsyncCominty, mock_api: respx.MockRouter, skill_folder: Path, tmp_path: Path
) -> None:
    route = mock_api.post("/skills").mock(return_value=httpx.Response(201, json=_skill()))
    archive = tmp_path / "my-skill.zip"
    archive.write_bytes(zip_folder(skill_folder))

    await client.skills.create(archive, display_name="Release notes", scope="organization")

    request = route.calls.last.request
    assert _form_fields(request)["scope"] == "organization"
    filename, content = _zip_part(request)
    assert filename == "skill.zip"
    assert content == archive.read_bytes()


async def test_create_sends_bytes_as_is(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/skills").mock(return_value=httpx.Response(201, json=_skill()))

    await client.skills.create(b"PK\x03\x04fake", display_name="Release notes")

    assert _zip_part(route.calls.last.request) == ("skill.zip", b"PK\x03\x04fake")


async def test_create_rejects_a_folder_without_skill_md(
    client: AsyncCominty, mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    (tmp_path / "README.md").write_text("not a skill")

    with pytest.raises(InvalidParams, match="has no SKILL.md"):
        await client.skills.create(tmp_path, display_name="Nope")

    assert mock_api.calls.call_count == 0


async def test_create_rejects_a_str(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    with pytest.raises(InvalidParams, match="got str: wrap a path in Path"):
        await client.skills.create(cast("bytes", "./skill"), display_name="Nope")

    assert mock_api.calls.call_count == 0


async def test_create_rejects_oversized_bytes_and_paths(
    client: AsyncCominty, mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    with pytest.raises(InvalidParams, match="over the .* the API accepts"):
        await client.skills.create(b"x" * (_MAX_ZIP_BYTES + 1), display_name="Big")

    big = tmp_path / "big.zip"
    big.write_bytes(b"x" * (_MAX_ZIP_BYTES + 1))
    with pytest.raises(InvalidParams, match="over the .* the API accepts"):
        await client.skills.create(big, display_name="Big")

    assert mock_api.calls.call_count == 0


@pytest.mark.parametrize(
    ("kwargs", "param"),
    [({"display_name": ""}, "display_name"), ({"display_name": "x" * 101}, "display_name")],
)
async def test_create_rejects_bad_display_name_before_zipping(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    skill_folder: Path,
    kwargs: dict[str, str],
    param: str,
) -> None:
    with pytest.raises(InvalidParams) as caught:
        await client.skills.create(skill_folder, **kwargs)

    assert [e["param"] for e in caught.value.errors] == [param]
    assert mock_api.calls.call_count == 0


async def test_create_surfaces_the_server_frontmatter_error(
    client: AsyncCominty, mock_api: respx.MockRouter, skill_folder: Path
) -> None:
    mock_api.post("/skills").mock(
        return_value=httpx.Response(
            422, json={"detail": "SKILL.md frontmatter: description is too short"}
        )
    )

    with pytest.raises(APIError, match="description is too short") as caught:
        await client.skills.create(skill_folder, display_name="Release notes")

    assert caught.value.status_code == 422


# --------------------------------------------------------------------------- #
# update / upload_version / delete
# --------------------------------------------------------------------------- #
async def test_update_sends_only_the_passed_fields(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.put(f"/skills/{SKILL_ID}").mock(
        return_value=httpx.Response(200, json=_skill(active=False))
    )

    skill = await client.skills.update(SKILL_ID, active=False)

    assert skill.active is False
    assert json.loads(route.calls.last.request.content) == {"active": False}


async def test_update_without_any_field_is_rejected(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    with pytest.raises(InvalidParams, match="at least one of"):
        await client.skills.update(SKILL_ID)

    assert mock_api.calls.call_count == 0


async def test_update_builtin_skill_raises_not_found(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.put("/skills/skl_builtin").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )

    with pytest.raises(NotFoundError):
        await client.skills.update("skl_builtin", display_name="Mine now")


async def test_upload_version_posts_the_archive(
    client: AsyncCominty, mock_api: respx.MockRouter, skill_folder: Path
) -> None:
    route = mock_api.post(f"/skills/{SKILL_ID}/versions").mock(
        return_value=httpx.Response(201, json=_skill())
    )

    skill = await client.skills.upload_version(SKILL_ID, skill_folder)

    assert isinstance(skill, SkillOut)
    request = route.calls.last.request
    assert _form_fields(request) == {}
    filename, content = _zip_part(request)
    assert filename == "release-notes.zip"
    assert zipfile.is_zipfile(io.BytesIO(content))


async def test_delete_sends_delete(client: AsyncCominty, mock_api: respx.MockRouter) -> None:
    route = mock_api.delete(f"/skills/{SKILL_ID}").mock(return_value=httpx.Response(200))

    assert await client.skills.delete(SKILL_ID) is None
    assert route.call_count == 1
