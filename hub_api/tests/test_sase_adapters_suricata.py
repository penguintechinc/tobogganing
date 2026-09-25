"""Test Suricata EVE adapter."""

from __future__ import annotations

import json

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.sase.security.adapters.suricata import SuricataAdapter
from hub_api.modules.threatintel.blocklist.store import BlocklistStore


@pytest.fixture
def cache_client() -> CacheClient:
    """CacheClient fixture with unreachable host."""
    return CacheClient(host="127.0.0.1", port=6399)


@pytest.fixture
def suricata_adapter() -> SuricataAdapter:
    """Suricata adapter fixture."""
    return SuricataAdapter()


def test_suricata_parse_alert_with_dest_ip_and_http_hostname() -> None:
    """Test parsing EVE alert with dest_ip and http.hostname -> 2 hits."""
    adapter = SuricataAdapter()

    # EVE alert with dest_ip and http.hostname
    eve_line = json.dumps(
        {
            "timestamp": "2026-08-06T12:00:00.000000+0000",
            "flow_id": 1234567890,
            "in_iface": "eth0",
            "event_type": "alert",
            "src_ip": "192.0.2.100",
            "src_port": 54321,
            "dest_ip": "192.0.2.10",
            "dest_port": 80,
            "proto": "TCP",
            "alert": {
                "action": "allowed",
                "gid": 1,
                "signature_id": 12345,
                "rev": 1,
                "signature": "ET USER Test Alert",
                "category": "Potentially Bad Traffic",
                "severity": 2,  # high (1=critical, 2=high, 3=medium, else=low)
            },
            "http": {
                "hostname": "example.com",
                "url": "/test",
                "method": "GET",
            },
        }
    )

    hits = adapter.parse(eve_line)

    # Should extract 3 hits: dest_ip (ip) + hostname (domain) + url
    assert len(hits) == 3
    assert hits[0].ioc_type == "ip"
    assert hits[0].value == "192.0.2.10"
    assert hits[0].severity == "high"
    assert hits[1].ioc_type == "domain"
    assert hits[1].value == "example.com"
    assert hits[1].severity == "high"
    assert hits[2].ioc_type == "url"
    assert hits[2].value == "http://example.com/test"
    assert hits[2].severity == "high"


def test_suricata_parse_alert_with_tls_sni() -> None:
    """Test parsing EVE alert with tls.sni -> domain hit."""
    adapter = SuricataAdapter()

    eve_line = json.dumps(
        {
            "timestamp": "2026-08-06T12:00:00.000000+0000",
            "event_type": "alert",
            "src_ip": "192.0.2.100",
            "dest_ip": "1.1.1.1",
            "proto": "TCP",
            "alert": {
                "action": "allowed",
                "gid": 1,
                "signature_id": 12345,
                "severity": 1,  # critical
                "signature": "ET USER Test Alert",
                "category": "Test",
            },
            "tls": {
                "sni": "secure.example.com",
                "version": "TLSv1.2",
            },
        }
    )

    hits = adapter.parse(eve_line)

    # Should extract 2 hits: dest_ip (ip) + sni (domain)
    assert len(hits) == 2
    assert hits[0].ioc_type == "ip"
    assert hits[0].value == "1.1.1.1"
    assert hits[0].severity == "critical"
    assert hits[1].ioc_type == "domain"
    assert hits[1].value == "secure.example.com"
    assert hits[1].severity == "critical"


def test_suricata_parse_alert_with_fileinfo_sha256() -> None:
    """Test parsing EVE alert with fileinfo.sha256 -> hash hit."""
    adapter = SuricataAdapter()

    eve_line = json.dumps(
        {
            "timestamp": "2026-08-06T12:00:00.000000+0000",
            "event_type": "alert",
            "src_ip": "192.0.2.100",
            "dest_ip": "192.0.2.10",
            "alert": {
                "action": "allowed",
                "gid": 1,
                "signature_id": 12345,
                "severity": 3,  # medium
                "signature": "ET USER Test Alert",
                "category": "Test",
            },
            "fileinfo": {
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "md5": "d41d8cd98f00b204e9800998ecf8427e",
                "size": 0,
                "state": "CLOSED",
            },
        }
    )

    hits = adapter.parse(eve_line)

    # Should extract 2 hits: dest_ip + hash
    assert len(hits) == 2
    assert hits[0].ioc_type == "ip"
    assert hits[0].value == "192.0.2.10"
    assert hits[0].severity == "medium"
    assert hits[1].ioc_type == "hash"
    assert hits[1].value == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert hits[1].severity == "medium"


def test_suricata_parse_alert_severity_mapping() -> None:
    """Test Suricata severity mapping to standard levels."""
    adapter = SuricataAdapter()

    severities = [
        (1, "critical"),
        (2, "high"),
        (3, "medium"),
        (4, "low"),
        (5, "low"),  # anything >= 4 is low
    ]

    for severity_int, expected_str in severities:
        eve_line = json.dumps(
            {
                "event_type": "alert",
                "dest_ip": "1.1.1.1",
                "alert": {
                    "action": "allowed",
                    "signature": "Test",
                    "severity": severity_int,
                },
            }
        )
        hits = adapter.parse(eve_line)
        assert len(hits) == 1
        assert (
            hits[0].severity == expected_str
        ), f"severity {severity_int} should map to {expected_str}"


def test_suricata_parse_non_alert_event() -> None:
    """Test that non-alert events (e.g., flow) produce no hits."""
    adapter = SuricataAdapter()

    eve_line = json.dumps(
        {
            "timestamp": "2026-08-06T12:00:00.000000+0000",
            "event_type": "flow",
            "src_ip": "192.0.2.100",
            "dest_ip": "192.0.2.10",
            "flow": {
                "pkts_toserver": 10,
                "pkts_toclient": 5,
                "bytes_toserver": 500,
                "bytes_toclient": 250,
            },
        }
    )

    hits = adapter.parse(eve_line)

    # Non-alert events should produce 0 hits
    assert len(hits) == 0


def test_suricata_parse_malformed_json() -> None:
    """Test that malformed JSON lines are skipped gracefully."""
    adapter = SuricataAdapter()

    # Malformed JSON (should be skipped, no exception)
    hits = adapter.parse("{ invalid json")
    assert len(hits) == 0


def test_suricata_parse_multiline_eve() -> None:
    """Test parsing multiple EVE lines in one call."""
    adapter = SuricataAdapter()

    eve_lines = "\n".join(
        [
            json.dumps(
                {
                    "event_type": "alert",
                    "dest_ip": "192.0.2.1",
                    "alert": {
                        "signature": "Alert 1",
                        "severity": 2,
                    },
                }
            ),
            json.dumps(
                {
                    "event_type": "flow",
                    "dest_ip": "192.0.2.2",
                }
            ),
            json.dumps(
                {
                    "event_type": "alert",
                    "dest_ip": "192.0.2.3",
                    "alert": {
                        "signature": "Alert 2",
                        "severity": 1,
                    },
                }
            ),
        ]
    )

    hits = adapter.parse(eve_lines)

    # Should extract 2 hits from 2 alert events
    assert len(hits) == 2
    assert hits[0].value == "192.0.2.1"
    assert hits[1].value == "192.0.2.3"


def test_suricata_map_severity_none_and_negative() -> None:
    """Severity mapping falls back to low for falsy/None and <=0 values."""
    adapter = SuricataAdapter()

    assert adapter._map_severity(None) == "low"
    assert adapter._map_severity(0) == "low"
    assert adapter._map_severity(-1) == "low"


def test_suricata_parse_url_without_hostname_uses_dest_ip() -> None:
    """URL construction falls back to dest_ip:port when no hostname/sni present."""
    adapter = SuricataAdapter()

    eve_line = json.dumps(
        {
            "event_type": "alert",
            "dest_ip": "192.0.2.55",
            "dest_port": 8080,
            "alert": {"signature": "Test", "severity": 2},
            "http": {"url": "/payload"},
        }
    )

    hits = adapter.parse(eve_line)

    url_hits = [h for h in hits if h.ioc_type == "url"]
    assert len(url_hits) == 1
    assert url_hits[0].value == "http://192.0.2.55:8080/payload"


def test_suricata_parse_blank_line_and_exception() -> None:
    """Suricata parse skips blank lines and swallows per-event exceptions."""
    adapter = SuricataAdapter()

    # alert.severity is a non-numeric string -> "<=" comparison raises TypeError.
    # Blank line placed mid-string since raw.strip() would eat a leading one.
    raw = "\n".join(
        [
            json.dumps(
                {
                    "event_type": "alert",
                    "dest_ip": "192.0.2.1",
                    "alert": {"signature": "Test", "severity": "bad"},
                }
            ),
            "",
            "x",
        ]
    )

    hits = adapter.parse(raw)
    assert hits == []


@pytest.mark.asyncio
async def test_suricata_ingest_writes_to_store(cache_client: CacheClient) -> None:
    """Test that ingest writes parsed hits to the blocklist store."""
    adapter = SuricataAdapter()
    store = BlocklistStore(cache=cache_client)

    eve_line = json.dumps(
        {
            "event_type": "alert",
            "dest_ip": "192.0.2.10",
            "http": {"hostname": "test.example.com"},
            "alert": {
                "signature": "Test Alert",
                "severity": 2,
            },
        }
    )

    stats = await adapter.ingest(eve_line, store)

    # Should have parsed 1 line, scanned and stored 2 hits (ip + domain)
    assert stats.source == "suricata"
    assert stats.scanned == 2
    assert stats.stored == 2
    assert stats.skipped == 0

    # Verify stored verdicts
    verdict_ip = await store.check("ip", "192.0.2.10")
    assert verdict_ip is not None
    assert verdict_ip.source == "suricata"

    verdict_domain = await store.check("domain", "test.example.com")
    assert verdict_domain is not None
    assert verdict_domain.source == "suricata"
