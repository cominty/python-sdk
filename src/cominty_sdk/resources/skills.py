from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING
from urllib.parse import quote

from pydantic import ValidationError

from cominty_sdk._uploads import invalid_upload, resolve_upload, zip_folder
from cominty_sdk.exceptions import InvalidParams
from cominty_sdk.models.common import Scope
from cominty_sdk.models.skills import CreateSkillParams, SkillOut, UpdateSkillParams

if TYPE_CHECKING:
    from cominty_sdk._transport import AsyncTransport

__all__ = ["SkillsResource"]

# MAX_SKILL_ZIP_SIZE of the hosted API (30 MB). Checked locally so an oversized archive
# fails before any request; a lower limit elsewhere is still reported as a 413.
_MAX_ZIP_BYTES = 30 * 1024 * 1024
_ZIP_MIMETYPE = "application/zip"
_SKILL_MD = "SKILL.md"


class SkillsResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(self) -> list[SkillOut]:
        """
        List the skills this API key can give to an agent.

        Sends ``GET /skills``: the built-in Cominty skills (``source="cominty"``),
        the organization-scoped custom skills, and the custom skills owned by the
        key's creator. Pass a skill's ``id`` in ``SkillsCapability.include``.

        Returns:
            list[SkillOut]: The visible skills, each with its default version's frontmatter.
        """
        raw = await self._transport.request("GET", "/skills")
        return [SkillOut.model_validate(item) for item in raw]

    async def create(
        self,
        file: bytes | os.PathLike[str],
        *,
        display_name: str,
        scope: Scope = "private",
    ) -> SkillOut:
        """
        Upload a new custom skill.

        Sends ``POST /skills`` as multipart (201). A skill is a folder whose
        ``SKILL.md`` opens with YAML frontmatter (``name``, ``description``, and
        optionally ``license``, ``compatibility``, ``metadata``, ``allowed-tools``, per
        <https://agentskills.io/specification>), plus any supporting files.

        Args:
            file (bytes | os.PathLike[str]): The skill. A folder path is zipped in
                memory (``SKILL.md`` must sit at its root); a ``.zip`` path or raw zip
                bytes are sent as they are. A plain ``str`` is rejected.
            display_name (str): Name shown in the console, 1 to 100 characters.
            scope (Scope): ``"private"`` (default) or ``"organization"``.

        Returns:
            SkillOut: The new skill, its frontmatter parsed by the server.

        Raises:
            InvalidParams: ``file`` is neither bytes nor a path, a folder without
                ``SKILL.md``, or over 30 MB; or ``display_name`` is out of range.
            OSError: ``file`` is a path that cannot be read.
            APIError: The server rejected the archive layout or the frontmatter
                (422, with the reason), or the archive is too large (413).
        """
        context = "skills.create"
        try:
            params = CreateSkillParams(display_name=display_name, scope=scope)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context=context) from None
        filename, content = await _zip_bytes(file, context=context)
        raw = await self._transport.request(
            "POST",
            "/skills",
            data=params.model_dump(mode="json"),
            files={"file": (filename, content, _ZIP_MIMETYPE)},
        )
        return SkillOut.model_validate(raw)

    async def update(
        self,
        skill_id: str,
        *,
        display_name: str | None = None,
        active: bool | None = None,
        scope: Scope | None = None,
    ) -> SkillOut:
        """
        Rename, enable/disable, or re-scope a custom skill.

        Sends ``PUT /skills/{skill_id}``. Only the fields you pass are sent.

        Args:
            skill_id (str): Skill to update.
            display_name (str | None): New name. Omit it to leave the name unchanged.
            active (bool | None): Whether agents may use the skill. Omit to leave it.
            scope (Scope | None): ``"private"`` or ``"organization"``. Omit to leave it.

        Returns:
            SkillOut: The updated skill.

        Raises:
            InvalidParams: No field was passed, or ``display_name`` is out of range.
            NotFoundError: No such custom skill owned by the key's creator (built-in
                skills included).
        """
        try:
            params = UpdateSkillParams(display_name=display_name, active=active, scope=scope)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context="skills.update") from None
        raw = await self._transport.request(
            "PUT",
            f"/skills/{_path(skill_id)}",
            json_body=params.model_dump(mode="json", exclude_none=True),
        )
        return SkillOut.model_validate(raw)

    async def upload_version(self, skill_id: str, file: bytes | os.PathLike[str]) -> SkillOut:
        """
        Upload a new version of a custom skill and make it the default.

        Sends ``POST /skills/{skill_id}/versions`` as multipart (201). Versions are
        tagged to the second: two uploads of the same skill within one second
        collide (500), so space them out.

        Args:
            skill_id (str): Skill to update.
            file (bytes | os.PathLike[str]): Same shapes as :meth:`create`.

        Returns:
            SkillOut: The skill, now describing the new version.

        Raises:
            InvalidParams: Same local checks on ``file`` as :meth:`create`.
            OSError: ``file`` is a path that cannot be read.
            NotFoundError: No such custom skill owned by the key's creator.
            APIError: The server rejected the archive (422 or 413).
        """
        filename, content = await _zip_bytes(file, context="skills.upload_version")
        raw = await self._transport.request(
            "POST",
            f"/skills/{_path(skill_id)}/versions",
            files={"file": (filename, content, _ZIP_MIMETYPE)},
        )
        return SkillOut.model_validate(raw)

    async def delete(self, skill_id: str) -> None:
        """
        Delete a custom skill and every version of it. This is permanent.

        Sends ``DELETE /skills/{skill_id}``.

        Args:
            skill_id (str): Skill to delete.

        Returns:
            None: The skill is gone.

        Raises:
            NotFoundError: No such custom skill owned by the key's creator.
        """
        await self._transport.request("DELETE", f"/skills/{_path(skill_id)}")


async def _zip_bytes(file: object, *, context: str) -> tuple[str, bytes]:
    source, filename = resolve_upload(file, "skill.zip", context=context)
    if isinstance(source, bytes):
        return _checked(filename, source, context=context)
    if source.is_dir():
        if not (source / _SKILL_MD).is_file():
            raise invalid_upload("file", f"folder {source} has no {_SKILL_MD}", context=context)
        content = await asyncio.to_thread(zip_folder, source)
        return _checked(f"{source.name}.zip", content, context=context)
    if source.stat().st_size > _MAX_ZIP_BYTES:
        raise _too_large(context)
    return filename, await asyncio.to_thread(source.read_bytes)


def _checked(filename: str, content: bytes, *, context: str) -> tuple[str, bytes]:
    if len(content) > _MAX_ZIP_BYTES:
        raise _too_large(context)
    return filename, content


def _too_large(context: str) -> InvalidParams:
    return invalid_upload(
        "file", f"is over the {_MAX_ZIP_BYTES} bytes (30 MB) the API accepts", context=context
    )


def _path(segment: str) -> str:
    return quote(segment, safe="")
