# Local-file plumbing shared by every resource that sends bytes somewhere: the
# bytes-or-path argument rule of chat.upload_file, folder expansion for sources,
# and the in-memory zip of a skill folder.

from __future__ import annotations

import io
import mimetypes
import os
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Union, cast

from typing_extensions import TypeAlias

from .exceptions import InvalidParam, InvalidParams

__all__ = [
    "DEFAULT_MIMETYPE",
    "LocalFiles",
    "expand_local_files",
    "guess_mimetype",
    "invalid_upload",
    "resolve_upload",
    "zip_folder",
]

DEFAULT_MIMETYPE = "application/octet-stream"

LocalFiles: TypeAlias = Union["os.PathLike[str]", Iterable["os.PathLike[str]"]]
"""Files on disk: a file path, a folder path (its top-level files), or an iterable of
file paths. A plain ``str`` is refused so a path is never mistaken for content."""

_PATH_HINT = ": wrap a path in Path(...)"


def guess_mimetype(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or DEFAULT_MIMETYPE


def resolve_upload(
    source: object, filename: str | None, *, context: str
) -> tuple[bytes | Path, str]:
    # Typed as object on purpose: callers without a type checker can pass anything.
    if isinstance(source, bytes):
        if filename is None:
            raise invalid_upload("filename", "required when `file` is bytes", context=context)
        return source, filename
    if isinstance(source, os.PathLike):
        path = Path(cast("os.PathLike[str]", source))
        return path, filename if filename is not None else path.name
    # A str is refused rather than read as a path: upload_file("hello") would otherwise
    # fail with a baffling FileNotFoundError.
    hint = _PATH_HINT if isinstance(source, str) else ""
    raise invalid_upload(
        "file",
        f"expected bytes or a pathlib.Path, got {type(source).__name__}{hint}",
        context=context,
    )


def expand_local_files(files: object, *, context: str) -> list[Path]:
    # One file, one folder (top level only: file names cannot contain "/" server-side,
    # so a recursive walk would flatten and collide), or an explicit list of files.
    if isinstance(files, os.PathLike):
        root = Path(cast("os.PathLike[str]", files))
        if root.is_dir():
            candidates = sorted(
                child
                for child in root.iterdir()
                if child.is_file() and not child.name.startswith(".")
            )
            if not candidates:
                raise invalid_upload("files", f"folder {root} contains no files", context=context)
        else:
            candidates = [root]
    elif isinstance(files, str):
        raise invalid_upload(
            "files",
            f"expected a pathlib.Path or an iterable of them, got str{_PATH_HINT}",
            context=context,
        )
    elif isinstance(files, Iterable):
        candidates: list[Path] = []
        for index, item in enumerate(cast("Iterable[object]", files)):
            if not isinstance(item, os.PathLike):
                hint = _PATH_HINT if isinstance(item, str) else ""
                raise invalid_upload(
                    f"files[{index}]",
                    f"expected a pathlib.Path, got {type(item).__name__}{hint}",
                    context=context,
                )
            candidates.append(Path(cast("os.PathLike[str]", item)))
        if not candidates:
            raise invalid_upload("files", "expected at least one file", context=context)
    else:
        raise invalid_upload(
            "files",
            f"expected a pathlib.Path or an iterable of them, got {type(files).__name__}",
            context=context,
        )

    seen: dict[str, Path] = {}
    for path in candidates:
        if not path.is_file():
            raise invalid_upload("files", f"{path} is not a readable file", context=context)
        if path.name in seen:
            raise invalid_upload(
                "files",
                f"{path} and {seen[path.name]} share the name {path.name!r}: "
                "file names must be unique within a source",
                context=context,
            )
        seen[path.name] = path
    return candidates


def zip_folder(folder: Path) -> bytes:
    # Layout A of the skills zip: every file of the folder at the root, SKILL.md included.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            # Relative parts only: skills commonly live under a dot folder (~/.claude/skills).
            relative = path.relative_to(folder)
            if path.is_file() and not any(part.startswith(".") for part in relative.parts):
                archive.write(path, arcname=str(relative))
    return buffer.getvalue()


def invalid_upload(param: str, message: str, *, context: str) -> InvalidParams:
    # The offending value is left out: it may be a whole file, or a secret passed by mistake.
    error = InvalidParam(param=param, message=message, input=None)
    return InvalidParams(
        f"Invalid parameters for {context}:\n  - {param}: {message}", errors=[error]
    )
