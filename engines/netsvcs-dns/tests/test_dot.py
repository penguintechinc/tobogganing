"""Tests for DoT (DNS-over-TLS) server."""
from __future__ import annotations

import asyncio
import struct
import pytest
from unittest.mock import AsyncMock, MagicMock
import dns.message

from app.servers import dot
from app.pipeline import ResolvePipeline


@pytest.fixture
def mock_pipeline() -> ResolvePipeline:
    """Create a mock pipeline."""
    return AsyncMock(spec=ResolvePipeline)


@pytest.mark.asyncio
async def test_dot_connection_single_query(mock_pipeline: AsyncMock) -> None:
    """Test DoT connection handling single query."""
    # Create a test DNS query
    query = dns.message.make_query("example.com", "A")
    query_wire = query.to_wire()

    # Mock pipeline response
    mock_pipeline.resolve_query.return_value = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "1.2.3.4"}],
    }

    # Create a mock reader/writer pair
    reader = AsyncMock()
    writer = AsyncMock()

    # Setup reader to return:
    # 1. Length prefix + query
    # 2. Then raise IncompleteReadError to simulate connection close
    length_prefix = struct.pack("!H", len(query_wire))
    reader.readexactly.side_effect = [
        length_prefix,
        query_wire,
        asyncio.IncompleteReadError(b"", 2),
    ]

    # Mock get_extra_info for client addr
    writer.get_extra_info.return_value = ("127.0.0.1", 12345)

    # Run the handler
    await dot._handle_dot_connection(reader, writer, mock_pipeline)

    # Verify pipeline was called
    mock_pipeline.resolve_query.assert_called_once_with(
        "example.com", "A", token=None, mode="normal"
    )

    # Verify response was written
    writer.write.assert_called_once()
    writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_dot_connection_multiple_queries(mock_pipeline: AsyncMock) -> None:
    """Test DoT connection handling multiple queries."""
    # Create test queries
    query1 = dns.message.make_query("example.com", "A")
    query1_wire = query1.to_wire()

    query2 = dns.message.make_query("example.org", "AAAA")
    query2_wire = query2.to_wire()

    # Mock pipeline responses
    mock_pipeline.resolve_query.side_effect = [
        {
            "Status": 0,
            "Question": [{"name": "example.com", "type": "A"}],
            "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "1.2.3.4"}],
        },
        {
            "Status": 0,
            "Question": [{"name": "example.org", "type": "AAAA"}],
            "Answer": [
                {"name": "example.org", "type": "AAAA", "TTL": 300, "data": "2001:db8::1"}
            ],
        },
    ]

    reader = AsyncMock()
    writer = AsyncMock()

    # Setup reader to return both queries then close
    length1 = struct.pack("!H", len(query1_wire))
    length2 = struct.pack("!H", len(query2_wire))

    reader.readexactly.side_effect = [
        length1,
        query1_wire,
        length2,
        query2_wire,
        asyncio.IncompleteReadError(b"", 2),
    ]

    writer.get_extra_info.return_value = ("127.0.0.1", 12346)

    await dot._handle_dot_connection(reader, writer, mock_pipeline)

    # Verify pipeline was called twice
    assert mock_pipeline.resolve_query.call_count == 2

    # Verify both queries were resolved
    call_args_list = mock_pipeline.resolve_query.call_args_list
    assert call_args_list[0].args[0] == "example.com"
    assert call_args_list[1].args[0] == "example.org"


@pytest.mark.asyncio
async def test_dot_connection_timeout(mock_pipeline: AsyncMock) -> None:
    """Test DoT connection timeout handling."""
    reader = AsyncMock()
    writer = AsyncMock()

    # Setup reader to timeout
    reader.readexactly.side_effect = asyncio.TimeoutError()
    writer.get_extra_info.return_value = ("127.0.0.1", 12347)

    # Should not raise, just log and close
    await dot._handle_dot_connection(reader, writer, mock_pipeline)

    writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_dot_connection_query_processing_error(mock_pipeline: AsyncMock) -> None:
    """Test DoT query processing error recovery."""
    # Create a test query
    query = dns.message.make_query("example.com", "A")
    query_wire = query.to_wire()

    # Mock pipeline to raise an exception
    mock_pipeline.resolve_query.side_effect = Exception("Pipeline error")

    reader = AsyncMock()
    writer = AsyncMock()

    length_prefix = struct.pack("!H", len(query_wire))
    reader.readexactly.side_effect = [
        length_prefix,
        query_wire,
        asyncio.IncompleteReadError(b"", 2),
    ]

    writer.get_extra_info.return_value = ("127.0.0.1", 12348)

    # Should not raise, should attempt to send error response
    await dot._handle_dot_connection(reader, writer, mock_pipeline)

    # Verify error handling attempted (writer.write called at least once for error response)
    writer.write.assert_called()
    writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_dot_connection_invalid_query_length(mock_pipeline: AsyncMock) -> None:
    """Test DoT connection with invalid query length."""
    reader = AsyncMock()
    writer = AsyncMock()

    # Send an invalid length (0)
    length_prefix = struct.pack("!H", 0)
    reader.readexactly.side_effect = [
        length_prefix,
        asyncio.IncompleteReadError(b"", 2),
    ]

    writer.get_extra_info.return_value = ("127.0.0.1", 12349)

    await dot._handle_dot_connection(reader, writer, mock_pipeline)

    # Pipeline should not be called for invalid query
    mock_pipeline.resolve_query.assert_not_called()
    writer.close.assert_called_once()


def test_json_to_dns_message_basic() -> None:
    """Test conversion of JSON response to DNS message."""
    query = dns.message.make_query("example.com", "A")

    json_result = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "1.2.3.4"}],
    }

    response = dot._json_to_dns_message(query, json_result)

    assert response.rcode() == 0
    assert len(response.answer) == 1
    assert str(response.answer[0].name) == "example.com."


def test_json_to_dns_message_nxdomain() -> None:
    """Test conversion of NXDOMAIN response."""
    query = dns.message.make_query("nonexistent.example.com", "A")

    json_result = {
        "Status": 3,  # NXDOMAIN
        "Question": [{"name": "nonexistent.example.com", "type": "A"}],
        "Answer": [],
    }

    response = dot._json_to_dns_message(query, json_result)

    # NXDOMAIN rcode is 3
    assert response.rcode() == 3
    assert len(response.answer) == 0


def test_json_to_dns_message_servfail() -> None:
    """Test conversion of SERVFAIL response."""
    query = dns.message.make_query("example.com", "A")

    json_result = {
        "Status": 2,  # SERVFAIL
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [],
    }

    response = dot._json_to_dns_message(query, json_result)

    # SERVFAIL rcode is 2
    assert response.rcode() == 2
    assert len(response.answer) == 0
