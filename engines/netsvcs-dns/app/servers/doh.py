"""DNS over HTTPS (DoH) server.

Implements both Google DoH-JSON (GET /dns/query) and RFC 8484 wireformat
(GET/POST /dns-query) endpoints over HTTP/2.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import dns.message
import dns.name
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.rrset
from quart import Blueprint, request, jsonify

from app.pipeline import ResolvePipeline

logger = logging.getLogger(__name__)


def init_doh(app: Any, pipeline: ResolvePipeline) -> Blueprint:
    """Initialize DoH endpoints on the Quart app.

    Args:
        app: Quart application instance.
        pipeline: ResolvePipeline instance for query resolution.

    Returns:
        Blueprint with DoH routes registered on app.
    """
    bp = Blueprint("doh", __name__)

    @bp.route("/dns/query", methods=["GET"])
    async def dns_json_query() -> tuple[dict, int]:
        """DNS-over-HTTPS JSON endpoint (Google DoH-JSON format).

        Query parameters:
            name: Domain name to resolve (required).
            type: DNS record type (A, AAAA, CNAME, etc.); default A.

        Headers:
            Authorization: Bearer <token> (optional DNS client token).

        Returns:
            JSON response in Google DoH format with status 200, or error status 400.
        """
        domain = request.args.get("name")
        record_type = request.args.get("type", "A")
        auth_header = request.headers.get("Authorization", "")

        if not domain:
            return jsonify({"Status": 2, "error": "Missing 'name' parameter"}), 400

        # Extract token if present (remove "Bearer " prefix)
        token = auth_header.replace("Bearer ", "") if auth_header else None

        try:
            # Determine operational mode (normal/cached/degraded)
            mode = "normal"  # S3: wire to resilience check

            # Resolve via pipeline
            result = await pipeline.resolve_query(
                domain, record_type, token=token, mode=mode
            )

            return jsonify(result), 200

        except Exception as e:
            logger.error(f"DoH JSON query error: {e}")
            return (
                jsonify(
                    {
                        "Status": 2,
                        "Question": [{"name": domain, "type": record_type}],
                        "Answer": [],
                    }
                ),
                200,
            )

    @bp.route("/dns-query", methods=["GET"])
    async def dns_wireformat_get() -> tuple[bytes, int, dict]:
        """RFC 8484 DNS-over-HTTPS (wireformat) GET endpoint.

        Query parameters:
            dns: Base64url-encoded DNS wire message (required).

        Headers:
            Authorization: Bearer <token> (optional).

        Returns:
            Binary DNS wireformat response with Content-Type: application/dns-message.
        """
        dns_param = request.args.get("dns")

        if not dns_param:
            return b"", 400, {"Content-Type": "application/dns-message"}

        try:
            # Decode base64url wire message
            dns_wire = base64.urlsafe_b64decode(dns_param + "==")  # Add padding
            query_msg = dns.message.from_wire(dns_wire)

            # Extract query (assume single question)
            if not query_msg.question:
                return b"", 400, {"Content-Type": "application/dns-message"}

            question = query_msg.question[0]
            domain = str(question.name).rstrip(".")
            record_type = dns.rdatatype.to_text(question.rdtype)

            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "") if auth_header else None

            # Resolve via pipeline
            mode = "normal"
            json_result = await pipeline.resolve_query(
                domain, record_type, token=token, mode=mode
            )

            # Convert to DNS wireformat response
            response_msg = _json_to_dns_message(query_msg, json_result)
            response_wire = response_msg.to_wire()

            return response_wire, 200, {"Content-Type": "application/dns-message"}

        except Exception as e:
            logger.error(f"DoH wireformat GET error: {e}")
            return b"", 500, {"Content-Type": "application/dns-message"}

    @bp.route("/dns-query", methods=["POST"])
    async def dns_wireformat_post() -> tuple[bytes, int, dict]:
        """RFC 8484 DNS-over-HTTPS (wireformat) POST endpoint.

        Body: Binary DNS wireformat message (application/dns-message).

        Headers:
            Authorization: Bearer <token> (optional).

        Returns:
            Binary DNS wireformat response with Content-Type: application/dns-message.
        """
        try:
            # Read body as binary
            dns_wire = await request.get_data()

            if not dns_wire:
                return b"", 400, {"Content-Type": "application/dns-message"}

            # Parse DNS wire message
            query_msg = dns.message.from_wire(dns_wire)

            if not query_msg.question:
                return b"", 400, {"Content-Type": "application/dns-message"}

            question = query_msg.question[0]
            domain = str(question.name).rstrip(".")
            record_type = dns.rdatatype.to_text(question.rdtype)

            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "") if auth_header else None

            # Resolve via pipeline
            mode = "normal"
            json_result = await pipeline.resolve_query(
                domain, record_type, token=token, mode=mode
            )

            # Convert to DNS wireformat response
            response_msg = _json_to_dns_message(query_msg, json_result)
            response_wire = response_msg.to_wire()

            return response_wire, 200, {"Content-Type": "application/dns-message"}

        except Exception as e:
            logger.error(f"DoH wireformat POST error: {e}")
            return b"", 500, {"Content-Type": "application/dns-message"}

    app.register_blueprint(bp)
    return bp


def _json_to_dns_message(
    query_msg: dns.message.Message, json_result: dict[str, Any]
) -> dns.message.Message:
    """Convert JSON DoH response to DNS wireformat message.

    Args:
        query_msg: Original DNS query message.
        json_result: JSON response from pipeline (Google DoH format).

    Returns:
        DNS message with response data.
    """
    # Create response message with same ID and recursion flags
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
            logger.warning(f"Failed to add answer record: {e}")

    return response
