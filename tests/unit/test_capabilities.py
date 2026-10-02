from __future__ import annotations

import pytest

from cominty_sdk import (
    ALL,
    AgentCapabilities,
    ImageGenerationCapability,
    ImageGenerationScope,
    IndexedDocumentsCapability,
    IndexedDocumentsScope,
    InvalidParams,
    McpCapability,
    McpScope,
    MemoryCapability,
    MessageScope,
    MusicGenerationCapability,
    MusicGenerationScope,
    SkillsCapability,
    VideoGenerationCapability,
    VideoGenerationScope,
    WebCapability,
    WebScope,
)


def test_all_is_the_wildcard_string() -> None:
    assert ALL == "*"


def test_agent_capabilities_wire_shape() -> None:
    caps = AgentCapabilities(
        web=WebCapability(activation="always"),
        indexed_documents=IndexedDocumentsCapability(activation="always", source_ids=[1, 2]),
        mcp=McpCapability(activation="on_request", connections=["linear"]),
        skills=SkillsCapability(activation="always"),
        image_generation=ImageGenerationCapability(activation="on_request"),
        video_generation=VideoGenerationCapability(activation="never"),
        music_generation=MusicGenerationCapability(activation="always"),
        memory=MemoryCapability(activation="always", namespace="support-bot"),
    )

    assert caps.model_dump(mode="json") == {
        "web": {"activation": "always"},
        "indexed_documents": {"activation": "always", "source_ids": [1, 2], "document_ids": "*"},
        "mcp": {"activation": "on_request", "connections": ["linear"]},
        "skills": {"activation": "always", "include": "*"},
        "image_generation": {"activation": "on_request"},
        "video_generation": {"activation": "never"},
        "music_generation": {"activation": "always"},
        "memory": {"activation": "always", "namespace": "support-bot"},
    }


def test_empty_agent_capabilities_is_empty_object() -> None:
    assert AgentCapabilities().model_dump(mode="json") == {}


@pytest.mark.parametrize(
    ("field", "shortcut", "expected"),
    [
        ("web", "on_request", "WebCapability"),
        ("web", True, "WebCapability"),
        ("memory", "never", "MemoryCapability"),
    ],
)
def test_shortcuts_are_rejected(field: str, shortcut: object, expected: str) -> None:
    with pytest.raises(InvalidParams) as exc:
        AgentCapabilities(**{field: shortcut})

    assert expected in str(exc.value)


@pytest.mark.parametrize(
    "capability",
    [
        WebCapability,
        ImageGenerationCapability,
        VideoGenerationCapability,
        MusicGenerationCapability,
        IndexedDocumentsCapability,
        McpCapability,
        SkillsCapability,
        MemoryCapability,
    ],
)
def test_activation_is_required(capability: type) -> None:
    with pytest.raises(InvalidParams) as exc:
        capability()

    assert exc.value.errors[0]["param"] == "activation"


@pytest.mark.parametrize("bad", ["on", "ALWAYS", True, None])
def test_activation_rejects_unknown_values(bad: object) -> None:
    with pytest.raises(InvalidParams):
        WebCapability(activation=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("activation", ["always", "on_request", "never"])
def test_toggle_capabilities_accept_every_activation(activation: str) -> None:
    caps = AgentCapabilities(
        web=WebCapability(activation=activation),  # type: ignore[arg-type]
    )

    assert caps.model_dump(mode="json") == {"web": {"activation": activation}}


def test_skills_reject_on_request() -> None:
    with pytest.raises(InvalidParams):
        SkillsCapability(activation="on_request")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("capability", "field"),
    [
        (IndexedDocumentsCapability, "source_ids"),
        (IndexedDocumentsCapability, "document_ids"),
        (McpCapability, "connections"),
        (SkillsCapability, "include"),
    ],
)
def test_filters_default_to_all_and_accept_it_explicitly(capability: type, field: str) -> None:
    default = capability(activation="always")
    explicit = capability(activation="always", **{field: ALL})

    assert default.model_dump(mode="json") == explicit.model_dump(mode="json")
    assert default.model_dump(mode="json")[field] == "*"


@pytest.mark.parametrize(
    ("capability", "field", "value"),
    [
        (IndexedDocumentsCapability, "source_ids", [1]),
        (IndexedDocumentsCapability, "document_ids", ["d"]),
        (McpCapability, "connections", ["linear"]),
        (SkillsCapability, "include", ["skl_a"]),
        (McpCapability, "connections", ALL),
    ],
)
def test_filter_is_refused_when_never(capability: type, field: str, value: object) -> None:
    with pytest.raises(InvalidParams) as exc:
        capability(activation="never", **{field: value})

    assert exc.value.errors[0]["param"] == field


def test_never_sends_only_the_activation() -> None:
    caps = AgentCapabilities(
        indexed_documents=IndexedDocumentsCapability(activation="never"),
        mcp=McpCapability(activation="never"),
        skills=SkillsCapability(activation="never"),
    )

    assert caps.model_dump(mode="json") == {
        "indexed_documents": {"activation": "never"},
        "mcp": {"activation": "never"},
        "skills": {"activation": "never"},
    }


@pytest.mark.parametrize("bad", [None, []])
def test_filter_rejects_none_and_empty_list(bad: object) -> None:
    with pytest.raises(InvalidParams) as exc:
        McpCapability(activation="always", connections=bad)  # type: ignore[arg-type]

    assert "ALL" in str(exc.value)
    assert exc.value.errors[0]["param"] == "connections"


@pytest.mark.parametrize("value", [["*"], ["*", "id_1"]])
@pytest.mark.parametrize(
    ("model", "base", "field"),
    [
        (IndexedDocumentsCapability, {"activation": "always"}, "document_ids"),
        (McpCapability, {"activation": "always"}, "connections"),
        (SkillsCapability, {"activation": "always"}, "include"),
        (IndexedDocumentsScope, {"enabled": True}, "document_ids"),
        (McpScope, {"enabled": True}, "connections"),
    ],
)
def test_wildcard_inside_a_list_is_rejected(
    model: type, base: dict[str, object], field: str, value: list[str]
) -> None:
    with pytest.raises(InvalidParams) as exc:
        model(**base, **{field: value})

    assert "ALL" in str(exc.value)
    assert exc.value.errors[0]["param"] == field


def test_capability_rejects_unknown_field() -> None:
    with pytest.raises(InvalidParams):
        WebCapability(activation="always", connections=ALL)  # type: ignore[call-arg]


@pytest.mark.parametrize("extra", [{}, {"namespace": None}])
def test_memory_always_requires_a_namespace(extra: dict[str, object]) -> None:
    with pytest.raises(InvalidParams) as exc:
        MemoryCapability(activation="always", **extra)

    assert "namespace is required" in str(exc.value)


def test_memory_never_sends_only_the_activation() -> None:
    caps = AgentCapabilities(memory=MemoryCapability(activation="never"))

    assert caps.model_dump(mode="json") == {"memory": {"activation": "never"}}


@pytest.mark.parametrize("namespace", ["x", None])
def test_memory_never_refuses_a_namespace(namespace: str | None) -> None:
    with pytest.raises(InvalidParams) as exc:
        MemoryCapability(activation="never", namespace=namespace)

    assert "namespace is not accepted" in str(exc.value)


def test_memory_rejects_on_request() -> None:
    with pytest.raises(InvalidParams):
        MemoryCapability(activation="on_request")  # type: ignore[arg-type]


@pytest.mark.parametrize("namespace", ["", "x" * 129])
def test_memory_namespace_length_is_bounded(namespace: str) -> None:
    with pytest.raises(InvalidParams) as exc:
        MemoryCapability(activation="always", namespace=namespace)

    assert exc.value.errors[0]["param"] == "namespace"


def test_memory_namespace_at_the_limit_is_accepted() -> None:
    caps = MemoryCapability(activation="always", namespace="x" * 128)

    assert caps.model_dump(mode="json") == {"activation": "always", "namespace": "x" * 128}


def test_message_scope_wire_shape() -> None:
    scope = MessageScope(
        web=WebScope(enabled=False),
        indexed_documents=IndexedDocumentsScope(
            enabled=True, source_ids=[101], document_ids=["101#a"]
        ),
        mcp=McpScope(enabled=True, connections=["linear"]),
        image_generation=ImageGenerationScope(enabled=True),
        video_generation=VideoGenerationScope(enabled=False),
        music_generation=MusicGenerationScope(enabled=True),
    )

    assert scope.model_dump(mode="json") == {
        "web": {"enabled": False},
        "indexed_documents": {"enabled": True, "source_ids": [101], "document_ids": ["101#a"]},
        "mcp": {"enabled": True, "connections": ["linear"]},
        "image_generation": {"enabled": True},
        "video_generation": {"enabled": False},
        "music_generation": {"enabled": True},
    }


def test_empty_message_scope_is_empty_object() -> None:
    assert MessageScope().model_dump(mode="json") == {}


@pytest.mark.parametrize("scope", [WebScope, IndexedDocumentsScope, McpScope])
def test_scope_requires_enabled(scope: type) -> None:
    with pytest.raises(InvalidParams) as exc:
        scope()

    assert exc.value.errors[0]["param"] == "enabled"


@pytest.mark.parametrize(
    ("scope", "field"),
    [
        (IndexedDocumentsScope, "source_ids"),
        (IndexedDocumentsScope, "document_ids"),
        (McpScope, "connections"),
    ],
)
def test_scope_filters_default_to_all_and_accept_it_explicitly(scope: type, field: str) -> None:
    default = scope(enabled=True)
    explicit = scope(enabled=True, **{field: ALL})

    assert default.model_dump(mode="json") == explicit.model_dump(mode="json")
    assert default.model_dump(mode="json")[field] == "*"


@pytest.mark.parametrize(
    ("scope", "field", "value"),
    [
        (IndexedDocumentsScope, "source_ids", [1]),
        (IndexedDocumentsScope, "document_ids", ALL),
        (McpScope, "connections", ["linear"]),
    ],
)
def test_scope_filter_is_refused_when_disabled(scope: type, field: str, value: object) -> None:
    with pytest.raises(InvalidParams) as exc:
        scope(enabled=False, **{field: value})

    assert exc.value.errors[0]["param"] == field


def test_disabled_scope_sends_only_enabled() -> None:
    scope = MessageScope(
        indexed_documents=IndexedDocumentsScope(enabled=False),
        mcp=McpScope(enabled=False),
    )

    assert scope.model_dump(mode="json") == {
        "indexed_documents": {"enabled": False},
        "mcp": {"enabled": False},
    }


@pytest.mark.parametrize("bad", [[], "linear", 1, None])
def test_scope_mcp_rejects_bad_connections(bad: object) -> None:
    with pytest.raises(InvalidParams):
        McpScope(enabled=True, connections=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["yes", 1, None])
def test_scope_enabled_must_be_a_bool(bad: object) -> None:
    with pytest.raises(InvalidParams):
        WebScope(enabled=bad)  # type: ignore[arg-type]


def test_message_scope_has_no_skills_or_memory() -> None:
    with pytest.raises(InvalidParams):
        MessageScope(skills=WebScope(enabled=True))  # type: ignore[call-arg]
    with pytest.raises(InvalidParams):
        MessageScope(memory=WebScope(enabled=True))  # type: ignore[call-arg]
