from __future__ import annotations

import httpx
import pytest
import respx

from cominty_sdk._http import AsyncHTTPClient
from cominty_sdk._qa import (
    extract_cite_tags,
    extract_tool_names,
    parse_document_citations,
    parse_web_citations,
)
from cominty_sdk.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
)
from cominty_sdk.models.messages import HumanMessage, MessageOut, parse_message_response


@pytest.fixture
def http_client() -> AsyncHTTPClient:
    return AsyncHTTPClient(
        base_url="https://api.test.cominty.com",
        api_key="test-key",
        max_retries=2,
        timeout=5.0,
    )


@respx.mock
@pytest.mark.asyncio
async def test_authentication_error(http_client: AsyncHTTPClient) -> None:
    respx.get("https://api.test.cominty.com/chat/usage").mock(
        return_value=httpx.Response(401, json={"detail": "Unauthorized"})
    )
    with pytest.raises(AuthenticationError):
        await http_client.request("GET", "/chat/usage")


@respx.mock
@pytest.mark.asyncio
async def test_not_found_error(http_client: AsyncHTTPClient) -> None:
    respx.get("https://api.test.cominty.com/chat/missing").mock(
        return_value=httpx.Response(404, json={"detail": "Not found"})
    )
    with pytest.raises(NotFoundError):
        await http_client.request("GET", "/chat/missing")


@respx.mock
@pytest.mark.asyncio
async def test_validation_error(http_client: AsyncHTTPClient) -> None:
    respx.post("https://api.test.cominty.com/chat").mock(
        return_value=httpx.Response(422, json={"detail": [{"msg": "invalid"}]})
    )
    with pytest.raises(ValidationError):
        await http_client.request("POST", "/chat", json={"message": {}})


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_server_error(http_client: AsyncHTTPClient) -> None:
    usage_payload = {"period_days": 7, "timeseries": [], "users": {}, "agents": {}}
    route = respx.get("https://api.test.cominty.com/chat/usage").mock(
        side_effect=[
            httpx.Response(503, json={"detail": "unavailable"}),
            httpx.Response(200, json=usage_payload),
        ]
    )
    result = await http_client.request("GET", "/chat/usage")
    assert result["period_days"] == 7
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_no_retry_on_authentication_error(http_client: AsyncHTTPClient) -> None:
    route = respx.get("https://api.test.cominty.com/chat/usage").mock(
        return_value=httpx.Response(401, json={"detail": "Unauthorized"})
    )
    with pytest.raises(AuthenticationError):
        await http_client.request("GET", "/chat/usage")
    assert route.call_count == 1


def test_human_message_disabled_tools_validation() -> None:
    HumanMessage(content="hello", disabled_tools=["web"])
    with pytest.raises(ValueError):
        HumanMessage(content="hello", disabled_tools=["invalid_tool"])


def test_is_stream_terminal_event() -> None:
    from cominty_sdk._qa import extract_stream_reply, is_stream_terminal_event

    assert is_stream_terminal_event({"type": "done"}) is True
    assert is_stream_terminal_event({"type": "delta", "content": "x"}) is False
    assert is_stream_terminal_event(
        {"name": "result", "status": "success", "data": {"reply": "OK"}}
    ) is True
    assert is_stream_terminal_event(
        {
            "role": "assistant",
            "content": "SDK endpoint test OK",
            "live": False,
            "status": "success",
        }
    ) is True
    assert extract_stream_reply(
        {"name": "result", "status": "success", "data": {"reply": "OK"}}
    ) == "OK"


def test_extract_tool_names() -> None:
    events = [
        {"type": "tool_call", "tool_name": "company_documents"},
        {"type": "tool_call", "tool_name": "web"},
        {"type": "tool_call", "tool_name": "company_documents"},
    ]
    assert extract_tool_names(events) == ["company_documents", "web"]


def test_citation_parsing() -> None:
    content = (
        'Answer <cite document_id="doc-1" pages="1-2" name="Report"/> '
        'and <cite url="https://example.com/news"/>'
    )
    assert len(extract_cite_tags(content)) == 2
    doc = parse_document_citations(content)[0]
    assert doc["document_id"] == "doc-1"
    web = parse_web_citations(content)[0]
    assert web["url"] == "https://example.com/news"


def test_message_out_qa_accessors() -> None:
    message = MessageOut.model_validate(
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "thread_id": "550e8400-e29b-41d4-a716-446655440001",
            "role": "assistant",
            "content": '<cite document_id="d1" pages="3" name="Doc"/>',
            "questions": None,
            "live": False,
            "status": "completed",
            "events": [{"type": "tool_call", "tool_name": "web"}],
            "structured_output": None,
            "files": [],
        }
    )
    assert message.tool_names == ["web"]
    assert len(message.document_citations) == 1
    assert message.is_terminal()


def test_parse_message_response_shutdown() -> None:
    from cominty_sdk.exceptions import ComintyServerShuttingDownError

    payload = {
        "__server_is_shutting_down": True,
        "partial": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "thread_id": "550e8400-e29b-41d4-a716-446655440001",
            "role": "assistant",
            "content": "partial",
            "questions": None,
            "live": True,
            "status": "running",
            "events": None,
            "structured_output": None,
            "files": [],
        },
    }
    with pytest.raises(ComintyServerShuttingDownError):
        parse_message_response(payload)


@respx.mock
@pytest.mark.asyncio
async def test_file_upload_flow(http_client: AsyncHTTPClient) -> None:
    from cominty_sdk.resources.files import FilesResource

    respx.get("https://api.test.cominty.com/chat/files/upload").mock(
        return_value=httpx.Response(
            200,
            json={
                "url": "https://s3.example.com/upload",
                "fields": {"key": "uploads/file.pdf", "policy": "abc"},
            },
        )
    )
    respx.post("https://s3.example.com/upload").mock(
        return_value=httpx.Response(204, headers={"ETag": '"etag123"'})
    )
    respx.post("https://api.test.cominty.com/chat/files/upload").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "file-123",
                "name": "file.pdf",
                "size": 10,
                "mimetype": "application/pdf",
                "origin": "user",
            },
        )
    )

    files = FilesResource(http_client)
    file_id = await files.upload(b"pdf-content", filename="file.pdf")
    assert file_id == "file-123"


@respx.mock
@pytest.mark.asyncio
async def test_jsonl_streaming(http_client: AsyncHTTPClient) -> None:
    from cominty_sdk._qa import iter_jsonl_events

    message_id = "550e8400-e29b-41d4-a716-446655440000"
    body = b'{"type":"delta","content":"Hi"}\n{"type":"done"}\n'
    respx.get(f"https://api.test.cominty.com/chat/messages/{message_id}/stream").mock(
        return_value=httpx.Response(200, content=body)
    )

    async with http_client.stream_context(
        "GET",
        f"/chat/messages/{message_id}/stream",
    ) as response:
        events = [event async for event in iter_jsonl_events(response)]
    assert events[0]["type"] == "delta"
    assert events[1]["type"] == "done"
