from __future__ import annotations

from typing import Annotated, Final, Literal, TypeVar, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    ModelWrapValidatorHandler,
    Tag,
    ValidationError,
    model_serializer,
    model_validator,
)
from typing_extensions import Self, TypeAlias

from cominty_sdk.exceptions import InvalidParams

__all__ = [
    "ALL",
    "Activation",
    "IndexedDocumentsPolicy",
    "McpPolicy",
    "SkillsPolicy",
    "AgentCapabilities",
    "IndexedDocumentsFilter",
    "MessageScope",
]

T = TypeVar("T")


ALL: Final = "*"
"""Allowlist marker meaning "no restriction": every id the end user can access."""

Activation: TypeAlias = Literal["always", "on_request", "never"]
"""``always``: on by default. ``on_request``: installed but off until a message
turns it on. ``never``: not installed."""

_EMPTY_LIST_HINT = (
    "an empty list is ambiguous: pass ALL for no restriction, or turn the capability off instead"
)


def _reject_none(value: object) -> object:
    if value is None:
        raise ValueError(
            "None is not accepted: pass ALL ('*') for no restriction, or a non-empty list"
        )
    return value


def _non_empty(value: list[T]) -> list[T]:
    if not value:
        raise ValueError(_EMPTY_LIST_HINT)
    return value


def _no_wildcard(value: list[str]) -> list[str]:
    if "*" in value:
        raise ValueError("'*' inside a list is not accepted: pass ALL on its own for every id")
    return value


_IntIds: TypeAlias = Annotated[list[int], AfterValidator(_non_empty)]
_StrIds: TypeAlias = Annotated[list[str], AfterValidator(_non_empty)]
_NamedIds: TypeAlias = Annotated[
    list[str], AfterValidator(_non_empty), AfterValidator(_no_wildcard)
]

_IntAllowList: TypeAlias = Annotated[Union[_IntIds, Literal["*"]], BeforeValidator(_reject_none)]
_StrAllowList: TypeAlias = Annotated[Union[_StrIds, Literal["*"]], BeforeValidator(_reject_none)]
_NamedAllowList: TypeAlias = Annotated[
    Union[_NamedIds, Literal["*"]], BeforeValidator(_reject_none)
]


def _wire_allow(value: list[int] | list[str] | Literal["*"]) -> object:
    return value if isinstance(value, str) else list(value)


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    @model_validator(mode="wrap")
    @classmethod
    def _raise_invalid_params(cls, data: object, handler: ModelWrapValidatorHandler[Self]) -> Self:
        try:
            return handler(data)
        except ValidationError as exc:
            raise InvalidParams.from_validation_error(exc, context=cls.__name__) from None


# --------------------------------------------------------------------------- #
# Thread level (saved agent / thread start)
# --------------------------------------------------------------------------- #
class IndexedDocumentsPolicy(_StrictModel):
    activation: Literal["always", "on_request"]
    source_ids: _IntAllowList = ALL
    document_ids: _StrAllowList = ALL

    def _to_wire(self) -> dict[str, object]:
        return {
            "activation": self.activation,
            "source_ids": _wire_allow(self.source_ids),
            "document_ids": _wire_allow(self.document_ids),
        }


class McpPolicy(_StrictModel):
    activation: Literal["always", "on_request"]
    connections: _NamedAllowList = ALL

    def _to_wire(self) -> dict[str, object]:
        return {"activation": self.activation, "connections": _wire_allow(self.connections)}


class SkillsPolicy(_StrictModel):
    activation: Literal["always", "on_request"]
    include: _NamedAllowList = ALL

    def _to_wire(self) -> dict[str, object]:
        return {"activation": self.activation, "include": _wire_allow(self.include)}


def _policy_or_activation(value: object) -> str:
    return "activation" if isinstance(value, str) else "policy"


_DocumentsCapability: TypeAlias = Annotated[
    Union[
        Annotated[IndexedDocumentsPolicy, Tag("policy")],
        Annotated[Activation, Tag("activation")],
    ],
    Discriminator(_policy_or_activation),
]
_McpCapability: TypeAlias = Annotated[
    Union[Annotated[McpPolicy, Tag("policy")], Annotated[Activation, Tag("activation")]],
    Discriminator(_policy_or_activation),
]
_SkillsCapability: TypeAlias = Annotated[
    Union[Annotated[SkillsPolicy, Tag("policy")], Annotated[Activation, Tag("activation")]],
    Discriminator(_policy_or_activation),
]


class AgentCapabilities(_StrictModel):
    web: Activation | None = None
    indexed_documents: _DocumentsCapability | None = None
    mcp: _McpCapability | None = None
    skills: _SkillsCapability | None = None
    image_generation: Activation | None = None
    video_generation: Activation | None = None
    music_generation: Activation | None = None

    @model_serializer(mode="plain")
    def _to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, (IndexedDocumentsPolicy, McpPolicy, SkillsPolicy)):
                wire[name] = value._to_wire()  # pyright: ignore[reportPrivateUsage]
            else:
                wire[name] = {"activation": value}
        return wire


# --------------------------------------------------------------------------- #
# Message level (one message)
# --------------------------------------------------------------------------- #
class IndexedDocumentsFilter(_StrictModel):
    source_ids: _IntIds | None = None
    document_ids: _StrIds | None = None


class MessageScope(_StrictModel):
    web: bool | None = None
    indexed_documents: bool | IndexedDocumentsFilter | None = None
    mcp: bool | _NamedIds | None = None
    skills: bool | _NamedIds | None = None
    image_generation: bool | None = None
    video_generation: bool | None = None
    music_generation: bool | None = None

    @model_serializer(mode="plain")
    def _to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {}
        filter_keys = {"mcp": "connections", "skills": "include"}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool):
                wire[name] = {"enabled": value}
            elif isinstance(value, IndexedDocumentsFilter):
                narrowed: dict[str, object] = {"enabled": True}
                if value.source_ids is not None:
                    narrowed["source_ids"] = list(value.source_ids)
                if value.document_ids is not None:
                    narrowed["document_ids"] = list(value.document_ids)
                wire[name] = narrowed
            else:
                wire[name] = {"enabled": True, filter_keys[name]: list(value)}
        return wire
