"""Tests for DoH (DNS-over-HTTPS) server."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import dns.message
import dns.name
import dns.rdataclass
import dns.rdatatype
import dns.rrset
import pytest
from app.pipeline import ResolvePipeline
from app.servers import doh
from quart import Quart


@pytest.fixture
def quart_app() -> Quart:
    """Create a test Quart app."""
    return Quart(__name__)


@pytest.fixture
def mock_pipeline() -> ResolvePipeline:
    """Create a mock pipeline."""
    return AsyncMock(spec=ResolvePipeline)


@pytest.fixture
def app_with_doh(quart_app: Quart, mock_pipeline: ResolvePipeline) -> Quart:
    """Create a Quart app with DoH routes registered."""
    quart_app.config["TESTING"] = True
    doh.init_doh(quart_app, mock_pipeline)
    return quart_app


@pytest.mark.asyncio
async def test_doh_json_query_success(app_with_doh: Quart, mock_pipeline: AsyncMock) -> None:
    """Test successful DoH JSON query."""
    client = app_with_doh.test_client()

    # Mock pipeline response
    mock_pipeline.resolve_query.return_value = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "93.184.216.34"}],
    }

    response = await client.get("/dns/query?name=example.com&type=A")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["Status"] == 0
    assert len(data["Answer"]) == 1
    assert data["Answer"][0]["data"] == "93.184.216.34"


@pytest.mark.asyncio
async def test_doh_json_query_missing_name(app_with_doh: Quart) -> None:
    """Test DoH JSON query without 'name' parameter."""
    client = app_with_doh.test_client()

    response = await client.get("/dns/query?type=A")

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_doh_json_query_with_token(app_with_doh: Quart, mock_pipeline: AsyncMock) -> None:
    """Test DoH JSON query with Authorization token."""
    client = app_with_doh.test_client()

    mock_pipeline.resolve_query.return_value = {
        "Status": 0,
        "Question": [{"name": "internal.example.com", "type": "A"}],
        "Answer": [{"name": "internal.example.com", "type": "A", "TTL": 300, "data": "10.0.0.1"}],
    }

    response = await client.get(
        "/dns/query?name=internal.example.com&type=A",
        headers={"Authorization": "Bearer test_token_123"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["Status"] == 0

    # Verify token was passed to pipeline
    call_args = mock_pipeline.resolve_query.call_args
    assert call_args.kwargs.get("token") == "test_token_123"


@pytest.mark.asyncio
async def test_doh_json_query_refused(app_with_doh: Quart, mock_pipeline: AsyncMock) -> None:
    """Test DoH JSON query that returns REFUSED."""
    client = app_with_doh.test_client()

    mock_pipeline.resolve_query.return_value = {
        "Status": 5,  # REFUSED
        "Question": [{"name": "restricted.example.com", "type": "A"}],
        "Answer": [],
    }

    response = await client.get("/dns/query?name=restricted.example.com&type=A")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["Status"] == 5
    assert len(data["Answer"]) == 0


@pytest.mark.asyncio
async def test_doh_wireformat_get_success(app_with_doh: Quart, mock_pipeline: AsyncMock) -> None:
    """Test RFC 8484 DoH GET with wireformat."""
    client = app_with_doh.test_client()

    # Create a test DNS query (example.com A record)
    query = dns.message.make_query("example.com", "A")
    query_wire = query.to_wire()
    dns_param = base64.urlsafe_b64encode(query_wire).decode().rstrip("=")

    # Mock pipeline response
    mock_pipeline.resolve_query.return_value = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "93.184.216.34"}],
    }

    response = await client.get(f"/dns-query?dns={dns_param}")

    assert response.status_code == 200
    assert response.content_type == "application/dns-message"

    # Response should be valid wireformat
    response_data = await response.get_data()
    response_msg = dns.message.from_wire(response_data)
    assert response_msg.rcode() == 0  # NOERROR


@pytest.mark.asyncio
async def test_doh_wireformat_get_missing_dns_param(app_with_doh: Quart) -> None:
    """Test RFC 8484 DoH GET without 'dns' parameter."""
    client = app_with_doh.test_client()

    response = await client.get("/dns-query")

    assert response.status_code == 400
    assert response.content_type == "application/dns-message"


@pytest.mark.asyncio
async def test_doh_wireformat_post_success(app_with_doh: Quart, mock_pipeline: AsyncMock) -> None:
    """Test RFC 8484 DoH POST with wireformat."""
    client = app_with_doh.test_client()

    # Create a test DNS query
    query = dns.message.make_query("example.com", "A")
    query_wire = query.to_wire()

    # Mock pipeline response
    mock_pipeline.resolve_query.return_value = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "1.2.3.4"}],
    }

    response = await client.post(
        "/dns-query",
        data=query_wire,
        headers={"Content-Type": "application/dns-message"},
    )

    assert response.status_code == 200
    assert response.content_type == "application/dns-message"

    # Response should be valid wireformat
    response_data = await response.get_data()
    response_msg = dns.message.from_wire(response_data)
    assert response_msg.rcode() == 0  # NOERROR


@pytest.mark.asyncio
async def test_doh_wireformat_post_with_token(
    app_with_doh: Quart, mock_pipeline: AsyncMock
) -> None:
    """Test RFC 8484 DoH POST with Authorization token."""
    client = app_with_doh.test_client()

    query = dns.message.make_query("internal.example.com", "A")
    query_wire = query.to_wire()

    mock_pipeline.resolve_query.return_value = {
        "Status": 0,
        "Question": [{"name": "internal.example.com", "type": "A"}],
        "Answer": [{"name": "internal.example.com", "type": "A", "TTL": 300, "data": "10.0.0.1"}],
    }

    response = await client.post(
        "/dns-query",
        data=query_wire,
        headers={
            "Content-Type": "application/dns-message",
            "Authorization": "Bearer test_token",
        },
    )

    assert response.status_code == 200

    # Verify token was passed
    call_args = mock_pipeline.resolve_query.call_args
    assert call_args.kwargs.get("token") == "test_token"


@pytest.mark.asyncio
async def test_doh_wireformat_post_nxdomain(app_with_doh: Quart, mock_pipeline: AsyncMock) -> None:
    """Test RFC 8484 DoH POST that returns NXDOMAIN."""
    client = app_with_doh.test_client()

    query = dns.message.make_query("nonexistent.example.com", "A")
    query_wire = query.to_wire()

    mock_pipeline.resolve_query.return_value = {
        "Status": 3,  # NXDOMAIN
        "Question": [{"name": "nonexistent.example.com", "type": "A"}],
        "Answer": [],
    }

    response = await client.post(
        "/dns-query",
        data=query_wire,
        headers={"Content-Type": "application/dns-message"},
    )

    assert response.status_code == 200

    response_data = await response.get_data()
    response_msg = dns.message.from_wire(response_data)
    # NXDOMAIN rcode is 3
    assert response_msg.rcode() == 3


# P5 coverage backfill: exception/edge branches


@pytest.mark.asyncio
async def test_doh_json_query_pipeline_exception(
    app_with_doh: Quart, mock_pipeline: AsyncMock
) -> None:
    """DoH JSON query returns a soft-fail Status=2 body when the pipeline raises."""
    client = app_with_doh.test_client()
    mock_pipeline.resolve_query.side_effect = Exception("pipeline boom")

    response = await client.get("/dns/query?name=example.com&type=A")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["Status"] == 2
    assert data["Answer"] == []


@pytest.mark.asyncio
async def test_doh_wireformat_get_no_question(app_with_doh: Quart) -> None:
    """Wireformat GET with a query message that has no question section returns 400."""
    client = app_with_doh.test_client()

    empty_msg = dns.message.Message()
    dns_param = base64.urlsafe_b64encode(empty_msg.to_wire()).decode().rstrip("=")

    response = await client.get(f"/dns-query?dns={dns_param}")

    assert response.status_code == 400
    assert response.content_type == "application/dns-message"


@pytest.mark.asyncio
async def test_doh_wireformat_get_pipeline_exception(
    app_with_doh: Quart, mock_pipeline: AsyncMock
) -> None:
    """Wireformat GET returns 500 when the pipeline raises."""
    client = app_with_doh.test_client()
    query = dns.message.make_query("example.com", "A")
    dns_param = base64.urlsafe_b64encode(query.to_wire()).decode().rstrip("=")
    mock_pipeline.resolve_query.side_effect = Exception("pipeline boom")

    response = await client.get(f"/dns-query?dns={dns_param}")

    assert response.status_code == 500
    assert response.content_type == "application/dns-message"


@pytest.mark.asyncio
async def test_doh_wireformat_post_empty_body(app_with_doh: Quart) -> None:
    """Wireformat POST with an empty body returns 400."""
    client = app_with_doh.test_client()

    response = await client.post(
        "/dns-query",
        data=b"",
        headers={"Content-Type": "application/dns-message"},
    )

    assert response.status_code == 400
    assert response.content_type == "application/dns-message"


@pytest.mark.asyncio
async def test_doh_wireformat_post_no_question(app_with_doh: Quart) -> None:
    """Wireformat POST with a message that has no question section returns 400."""
    client = app_with_doh.test_client()

    empty_msg = dns.message.Message()

    response = await client.post(
        "/dns-query",
        data=empty_msg.to_wire(),
        headers={"Content-Type": "application/dns-message"},
    )

    assert response.status_code == 400
    assert response.content_type == "application/dns-message"


@pytest.mark.asyncio
async def test_doh_wireformat_post_pipeline_exception(
    app_with_doh: Quart, mock_pipeline: AsyncMock
) -> None:
    """Wireformat POST returns 500 when the pipeline raises."""
    client = app_with_doh.test_client()
    query = dns.message.make_query("example.com", "A")
    mock_pipeline.resolve_query.side_effect = Exception("pipeline boom")

    response = await client.post(
        "/dns-query",
        data=query.to_wire(),
        headers={"Content-Type": "application/dns-message"},
    )

    assert response.status_code == 500
    assert response.content_type == "application/dns-message"


def test_json_to_dns_message_skips_malformed_answer() -> None:
    """_json_to_dns_message logs and skips an answer record that fails to parse."""
    query = dns.message.make_query("example.com", "A")
    json_result = {
        "Status": 0,
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "not-an-ip"}],
    }

    response = doh._json_to_dns_message(query, json_result)

    assert response.rcode() == 0
    assert len(response.answer) == 0
