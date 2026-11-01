from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from cominty_sdk import AsyncCominty, McpServerOut, ServerError


def _server(**overrides: object) -> dict[str, object]:
    server: dict[str, object] = {
        "name": "linear",
        "title": "Linear",
        "description": "Track issues and projects.",
        "is_enabled": True,
        "origin": "builtin",
        "scope": "organization",
        "requires_oauth_connect": False,
    }
    server.update(overrides)
    return server


def _manifest(*servers: dict[str, object]) -> dict[str, object]:
    return {"servers": list(servers)}


async def test_list_returns_enabled_servers(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get("/mcp/manifest").mock(
        return_value=httpx.Response(
            200,
            json=_manifest(
                _server(),
                _server(name="notion", title="Notion", is_enabled=False),
            ),
        )
    )

    servers = await client.mcp.list()

    assert [server.name for server in servers] == ["linear"]
    assert isinstance(servers[0], McpServerOut)
    assert servers[0].title == "Linear"
    assert servers[0].requires_oauth_connect is False
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == "/mcp/manifest"
    assert not request.url.params
    assert request.headers["x-cominty-token"] == "test-token"


async def test_list_parses_optional_fields_and_ignores_unknown_ones(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/mcp/manifest").mock(
        return_value=httpx.Response(
            200,
            json=_manifest(
                _server(
                    connection_status="connected",
                    icon_uri="https://example.com/linear.png",
                    mcp_url="https://mcp.example.com/linear",
                    owner_id="user_31HPTBuBvX20xlQNAbvxjOxPbKB",
                    created_at="2026-06-28T10:00:00Z",
                    updated_at="2026-06-29T11:30:00Z",
                    scopes=["issues:read"],
                ),
                _server(name="github", origin="partner"),
            ),
        )
    )

    linear, github = await client.mcp.list(enabled=None)

    assert linear.connection_status == "connected"
    assert linear.icon_uri == "https://example.com/linear.png"
    assert linear.mcp_url == "https://mcp.example.com/linear"
    assert linear.owner_id == "user_31HPTBuBvX20xlQNAbvxjOxPbKB"
    assert linear.created_at == datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc)
    assert linear.updated_at == datetime(2026, 6, 29, 11, 30, tzinfo=timezone.utc)
    assert github.origin == "partner"
    assert github.connection_status is None
    assert github.icon_uri is None
    assert github.mcp_url is None
    assert github.owner_id is None
    assert github.created_at is None
    assert github.updated_at is None


@pytest.mark.parametrize(
    ("enabled", "names"),
    [
        (True, ["linear", "github"]),
        (False, ["notion"]),
        (None, ["linear", "notion", "github"]),
    ],
)
async def test_enabled_filters_locally(
    client: AsyncCominty,
    mock_api: respx.MockRouter,
    enabled: bool | None,
    names: list[str],
) -> None:
    mock_api.get("/mcp/manifest").mock(
        return_value=httpx.Response(
            200,
            json=_manifest(
                _server(name="linear", is_enabled=True),
                _server(name="notion", is_enabled=False),
                _server(name="github", is_enabled=True),
            ),
        )
    )

    servers = await client.mcp.list(enabled=enabled)

    assert [server.name for server in servers] == names


async def test_empty_manifest_returns_an_empty_list(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/mcp/manifest").mock(return_value=httpx.Response(200, json=_manifest()))

    assert await client.mcp.list() == []
    assert await client.mcp.list(enabled=None) == []


async def test_plain_text_500_raises_server_error(
    client: AsyncCominty, mock_api: respx.MockRouter
) -> None:
    mock_api.get("/mcp/manifest").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(ServerError):
        await client.mcp.list()
