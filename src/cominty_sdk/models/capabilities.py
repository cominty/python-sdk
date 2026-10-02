from __future__ import annotations

from typing import Annotated, Final, Generic, Literal, TypeVar, Union, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    SerializerFunctionWrapHandler,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)
from typing_extensions import Self, TypeAlias

from cominty_sdk.exceptions import InvalidParams

from .memory import validate_memory_namespace

__all__ = [
    "ALL",
    "AgentCapabilities",
    "WebCapability",
    "IndexedDocumentsCapability",
    "McpCapability",
    "SkillsCapability",
    "ImageGenerationCapability",
    "VideoGenerationCapability",
    "MusicGenerationCapability",
    "MemoryCapability",
    "MessageScope",
    "WebScope",
    "IndexedDocumentsScope",
    "McpScope",
    "ImageGenerationScope",
    "VideoGenerationScope",
    "MusicGenerationScope",
]

_T = TypeVar("_T")
_ActivationT = TypeVar("_ActivationT", bound=str)


ALL: Final[Literal["*"]] = "*"
"""Allowlist marker meaning "no restriction": every id the end user can access. It is
the default of every filter, so pass it only to make the intent explicit."""

_Activation: TypeAlias = Literal["always", "on_request", "never"]
"""``always``: on by default. ``on_request``: installed but off until a message turns
it on. ``never``: not installed."""

_EMPTY_LIST_HINT = (
    "an empty list is ambiguous: pass ALL for no restriction, or turn the capability off instead"
)
_NEVER_HINT = "not accepted when the capability is off: it takes no filter"


def _reject_none(value: object) -> object:
    if value is None:
        raise ValueError(
            "None is not accepted: pass ALL ('*') for no restriction, or a non-empty list"
        )
    return value


def _non_empty(value: list[_T]) -> list[_T]:
    if not value:
        raise ValueError(_EMPTY_LIST_HINT)
    return value


def _no_wildcard(value: list[str]) -> list[str]:
    if "*" in value:
        raise ValueError("'*' inside a list is not accepted: pass ALL on its own for every id")
    return value


_IntIds: TypeAlias = Annotated[list[int], AfterValidator(_non_empty)]
_StrIds: TypeAlias = Annotated[list[str], AfterValidator(_non_empty), AfterValidator(_no_wildcard)]

_IntAllowList: TypeAlias = Annotated[Union[_IntIds, Literal["*"]], BeforeValidator(_reject_none)]
_StrAllowList: TypeAlias = Annotated[Union[_StrIds, Literal["*"]], BeforeValidator(_reject_none)]

_MemoryNamespaceValue: TypeAlias = Annotated[
    str, Field(min_length=1), AfterValidator(validate_memory_namespace)
]

_FILTER_FIELDS = ("source_ids", "document_ids", "connections", "include")


def _drop_none(wire: dict[str, object]) -> dict[str, object]:
    return {name: value for name, value in wire.items() if value is not None}


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
class _Capability(_StrictModel, Generic[_ActivationT]):
    # Declared first so that filter validators of the subclasses can read it.
    activation: _ActivationT

    @field_validator(*_FILTER_FIELDS, mode="after", check_fields=False)
    @classmethod
    def _no_filter_when_never(cls, value: _T, info: ValidationInfo) -> _T:
        if info.data.get("activation") == "never":
            raise ValueError(_NEVER_HINT)
        return value

    @model_serializer(mode="wrap")
    def _to_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        wire: dict[str, object] = handler(self)
        return {"activation": "never"} if self.activation == "never" else wire


class WebCapability(_Capability[_Activation]):
    pass


class ImageGenerationCapability(_Capability[_Activation]):
    pass


class VideoGenerationCapability(_Capability[_Activation]):
    pass


class MusicGenerationCapability(_Capability[_Activation]):
    pass


class IndexedDocumentsCapability(_Capability[_Activation]):
    source_ids: _IntAllowList = ALL
    document_ids: _StrAllowList = ALL


class McpCapability(_Capability[_Activation]):
    connections: _StrAllowList = ALL


class SkillsCapability(_Capability[Literal["always", "never"]]):
    include: _StrAllowList = ALL


class MemoryCapability(_StrictModel):
    """``always`` needs a ``namespace`` (the memory bag); ``never`` takes none."""

    activation: Literal["always", "never"]
    namespace: _MemoryNamespaceValue | None = None

    # "before", not "after": a subclass "after" validator runs outside the parent's
    # InvalidParams wrapper, and only the raw input still shows an explicit None.
    @model_validator(mode="before")
    @classmethod
    def _namespace_matches_activation(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        fields = cast("dict[str, object]", data)
        if fields.get("activation") == "always" and fields.get("namespace") is None:
            raise ValueError("namespace is required when activation='always'")
        if fields.get("activation") == "never" and "namespace" in fields:
            raise ValueError("namespace is not accepted with activation='never': memory is off")
        return fields

    @model_serializer(mode="wrap")
    def _to_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        wire: dict[str, object] = handler(self)
        return {"activation": "never"} if self.activation == "never" else wire


class AgentCapabilities(_StrictModel):
    web: WebCapability | None = None
    indexed_documents: IndexedDocumentsCapability | None = None
    mcp: McpCapability | None = None
    skills: SkillsCapability | None = None
    image_generation: ImageGenerationCapability | None = None
    video_generation: VideoGenerationCapability | None = None
    music_generation: MusicGenerationCapability | None = None
    memory: MemoryCapability | None = None

    @model_serializer(mode="wrap")
    def _to_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        return _drop_none(handler(self))


# --------------------------------------------------------------------------- #
# Message level (one message)
# --------------------------------------------------------------------------- #
class _Scope(_StrictModel):
    enabled: bool

    @field_validator(*_FILTER_FIELDS, mode="after", check_fields=False)
    @classmethod
    def _no_filter_when_disabled(cls, value: _T, info: ValidationInfo) -> _T:
        if info.data.get("enabled") is False:
            raise ValueError(_NEVER_HINT)
        return value

    @model_serializer(mode="wrap")
    def _to_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        wire: dict[str, object] = handler(self)
        return wire if self.enabled else {"enabled": False}


class WebScope(_Scope):
    pass


class ImageGenerationScope(_Scope):
    pass


class VideoGenerationScope(_Scope):
    pass


class MusicGenerationScope(_Scope):
    pass


class IndexedDocumentsScope(_Scope):
    source_ids: _IntAllowList = ALL
    document_ids: _StrAllowList = ALL


class McpScope(_Scope):
    connections: _StrAllowList = ALL


class MessageScope(_StrictModel):
    web: WebScope | None = None
    indexed_documents: IndexedDocumentsScope | None = None
    mcp: McpScope | None = None
    image_generation: ImageGenerationScope | None = None
    video_generation: VideoGenerationScope | None = None
    music_generation: MusicGenerationScope | None = None

    @model_serializer(mode="wrap")
    def _to_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        return _drop_none(handler(self))
