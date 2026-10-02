from __future__ import annotations

import pytest

from cominty_sdk import (
    ALL,
    AgentCapabilities,
    IndexedDocumentsFilter,
    IndexedDocumentsPolicy,
    InvalidParams,
    McpPolicy,
    MessageScope,
    SkillsPolicy,
)


def test_all_is_the_wildcard_string() -> None:
    assert ALL == "*"


def test_agent_capabilities_wire_shape() -> None:
    caps = AgentCapabilities(
        web="always",
        indexed_documents=IndexedDocumentsPolicy(
            activation="always", source_ids=[1, 2], document_ids=ALL
        ),
        mcp=McpPolicy(activation="on_request", connections=["linear"]),
        skills=SkillsPolicy(activation="always", include=ALL),
        image_generation="on_request",
        video_generation="never",
    )

    assert caps.model_dump(mode="json") == {
        "web": {"activation": "always"},
        "indexed_documents": {"activation": "always", "source_ids": [1, 2], "document_ids": "*"},
        "mcp": {"activation": "on_request", "connections": ["linear"]},
        "skills": {"activation": "always", "include": "*"},
        "image_generation": {"activation": "on_request"},
        "video_generation": {"activation": "never"},
    }


def test_agent_capabilities_never_for_filterable_capabilities() -> None:
    caps = AgentCapabilities(indexed_documents="never", mcp="never", skills="never")

    assert caps.model_dump(mode="json") == {
        "indexed_documents": {"activation": "never"},
        "mcp": {"activation": "never"},
        "skills": {"activation": "never"},
    }


def test_empty_agent_capabilities_is_empty_object() -> None:
    assert AgentCapabilities().model_dump(mode="json") == {}


def test_bare_activation_on_filterable_capability_means_no_restriction() -> None:
    caps = AgentCapabilities(indexed_documents="always", mcp="on_request", skills="never")

    assert caps.model_dump(mode="json") == {
        "indexed_documents": {"activation": "always"},
        "mcp": {"activation": "on_request"},
        "skills": {"activation": "never"},
    }


def test_policy_filters_default_to_all() -> None:
    caps = AgentCapabilities(mcp=McpPolicy(activation="always"))

    assert caps.model_dump(mode="json") == {"mcp": {"activation": "always", "connections": "*"}}


def test_policy_rejects_never_activation() -> None:
    with pytest.raises(InvalidParams):
        McpPolicy(activation="never", connections=ALL)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, []])
def test_filter_rejects_none_and_empty_list(bad: object) -> None:
    with pytest.raises(InvalidParams) as exc:
        McpPolicy(activation="always", connections=bad)  # type: ignore[arg-type]

    assert "ALL" in str(exc.value)
    assert exc.value.errors[0]["param"] == "connections"


def test_wildcard_inside_a_list_is_rejected() -> None:
    with pytest.raises(InvalidParams) as exc:
        SkillsPolicy(activation="always", include=["*"])

    assert "ALL" in str(exc.value)


def test_message_scope_wire_shape() -> None:
    caps = MessageScope(
        web=False,
        indexed_documents=IndexedDocumentsFilter(source_ids=[101], document_ids=["101#a"]),
        mcp=["linear"],
        skills=["skl_a"],
        image_generation=True,
    )

    assert caps.model_dump(mode="json") == {
        "web": {"enabled": False},
        "indexed_documents": {"enabled": True, "source_ids": [101], "document_ids": ["101#a"]},
        "mcp": {"enabled": True, "connections": ["linear"]},
        "skills": {"enabled": True, "include": ["skl_a"]},
        "image_generation": {"enabled": True},
    }


def test_message_scope_bool_for_documents_and_mcp() -> None:
    caps = MessageScope(indexed_documents=False, mcp=True)

    assert caps.model_dump(mode="json") == {
        "indexed_documents": {"enabled": False},
        "mcp": {"enabled": True},
    }


def test_documents_filter_only_document_ids() -> None:
    caps = MessageScope(indexed_documents=IndexedDocumentsFilter(document_ids=["d"]))

    assert caps.model_dump(mode="json") == {
        "indexed_documents": {"enabled": True, "document_ids": ["d"]}
    }


@pytest.mark.parametrize("bad", [[], "linear", 1])
def test_message_mcp_rejects_bad_values(bad: object) -> None:
    with pytest.raises(InvalidParams):
        MessageScope(mcp=bad)  # type: ignore[arg-type]
