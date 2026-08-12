"""DNS over TLS (DoT) server.

Implements RFC 7858: DNS over Transport Layer Security (TLS).
Standalone async TLS listener on port 853 with 2-byte length prefix.
"""
from __future__ import annotations

import os
import asyncio
import ssl
import struct
from typing import Any

import structlog

import dns.message
import dns.name
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.rrset

from app.pipeline import ResolvePipeline

logger = structlog.get_logger()


async def serve_dot(
    pipeline: ResolvePipeline, port: int = 853, cert_path: str | None = None, key_path: str | None = None
) -> None:
    """Start a DoT (DNS-over-TLS) listener.

    Listens on the specified port with TLS encryption.
    Handles multiple DNS queries per connection using RFC 7858 2-byte length prefix.

    Args:
        pipeline: ResolvePipeline instance for query resolution.
        port: Port to listen on (default 853).
        cert_path: Path to TLS certificate file.
        key_path: Path to TLS private key file.

    Raises:
        FileNotFoundError: If cert or key files are missing.
        ssl.SSLError: If TLS context setup fails.
    """
    # Create TLS context
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    if not cert_path or not key_path:
        logger.warning(
            "DoT TLS cert/key not configured; skipping DoT listener",
            cert_path=cert_path,
            key_path=key_path,
        )
        return

    try:
        ssl_context.load_cert_chain(cert_path, key_path)
        logger.info("DoT TLS context loaded", cert_path=cert_path)
    except FileNotFoundError as e:
        logger.error(f"DoT TLS cert/key not found: {e}")
        # Fail closed: skip DoT if certs are missing
        return
    except ssl.SSLError as e:
        logger.error(f"DoT TLS context error: {e}")
        return

    # Start server
    try:
        server = await asyncio.start_server(
            lambda r, w: _handle_dot_connection(r, w, pipeline),
            os.getenv("BIND_HOST", "0.0.0.0"),  # nosec B104 - containerized DNS service must bind all interfaces
            port,
            ssl=ssl_context,
        )

        async with server:
            logger.info(f"DoT listener started on port {port}")
            await server.serve_forever()
    except Exception as e:
        logger.error(f"DoT server error: {e}")


async def _handle_dot_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, pipeline: ResolvePipeline
) -> None:
    """Handle a single DoT client connection.

    Reads multiple DNS queries (each prefixed with 2-byte length),
    resolves them via the pipeline, and sends back DNS responses.

    Args:
        reader: AsyncIO StreamReader for the TLS connection.
        writer: AsyncIO StreamWriter for the TLS connection.
        pipeline: ResolvePipeline for query resolution.
    """
    client_addr = writer.get_extra_info("peername")
    logger.info(f"DoT connection from {client_addr}")

    try:
        while True:
            # Read 2-byte length prefix (RFC 7858)
            length_data = await asyncio.wait_for(reader.readexactly(2), timeout=30.0)
            query_length = struct.unpack("!H", length_data)[0]

            if query_length == 0 or query_length > 65535:
                logger.warning(f"Invalid DoT query length: {query_length}")
                break

            # Read DNS query
            query_data = await asyncio.wait_for(reader.readexactly(query_length), timeout=30.0)

            try:
                # Parse DNS query
                query_msg = dns.message.from_wire(query_data)

                if not query_msg.question:
                    logger.warning("DoT query with no questions")
                    continue

                question = query_msg.question[0]
                domain = str(question.name).rstrip(".")
                record_type = dns.rdatatype.to_text(question.rdtype)

                logger.info(f"DoT query: {domain} {record_type}")

                # Resolve via pipeline (no token for DoT in S2; S3 may add client certs)
                mode = "normal"
                json_result = await pipeline.resolve_query(
                    domain, record_type, token=None, mode=mode
                )

                # Convert to DNS wireformat
                response_msg = _json_to_dns_message(query_msg, json_result)
                response_wire = response_msg.to_wire()

                # Write response with 2-byte length prefix
                response_data = struct.pack("!H", len(response_wire)) + response_wire
                writer.write(response_data)
                await writer.drain()

            except Exception as e:
                logger.error(f"DoT query processing error: {e}")
                # Try to send SERVFAIL response
                try:
                    error_response = dns.message.make_response(query_msg)
                    error_response.set_rcode(dns.rcode.SERVFAIL)
                    error_wire = error_response.to_wire()
                    error_data = struct.pack("!H", len(error_wire)) + error_wire
                    writer.write(error_data)
                    await writer.drain()
                except Exception as e2:
                    logger.error(f"Failed to send DoT error response: {e2}")

    except asyncio.TimeoutError:
        logger.info(f"DoT connection timeout from {client_addr}")
    except asyncio.IncompleteReadError:
        logger.info(f"DoT connection closed by {client_addr}")
    except Exception as e:
        logger.error(f"DoT connection error from {client_addr}: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info(f"DoT connection closed from {client_addr}")


def _json_to_dns_message(
    query_msg: dns.message.Message, json_result: dict[str, Any]
) -> dns.message.Message:
    """Convert JSON response to DNS wireformat message.

    Args:
        query_msg: Original DNS query message.
        json_result: JSON response from pipeline (Google DoH format).

    Returns:
        DNS message with response data.
    """
    # Create response message with same ID
    response = dns.message.make_response(query_msg)

    # Set RCODE from Status field
    status = json_result.get("Status", 2)
    response.set_rcode(status)

    # Add answer records from JSON response
    for answer in json_result.get("Answer", []):
        try:
            rname = dns.name.from_text(answer.get("name", ""))
            rdtype = dns.rdatatype.from_text(answer.get("type", "A"))
            ttl = answer.get("TTL", 300)
            rdata_text = answer.get("data", "")

            # Parse rdata from text representation
            rdata = dns.rdata.from_text(dns.rdataclass.IN, rdtype, rdata_text)
            rrset = dns.rrset.from_rdata(rname, ttl, rdata)
            response.answer.append(rrset)
        except Exception as e:
            logger.warning(f"Failed to add DoT answer record: {e}")

    return response
