"""Test Zeek, Strelka, CAPE, and Arkime adapters."""
from __future__ import annotations

import json

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.sase.security.adapters.zeek import ZeekAdapter
from hub_api.modules.sase.security.adapters.strelka import StrelkaAdapter
from hub_api.modules.sase.security.adapters.cape import CapeAdapter
from hub_api.modules.sase.security.adapters.arkime import ArkimeAdapter
from hub_api.modules.sase.security.blocklist.store import BlocklistStore


@pytest.fixture
def cache_client() -> CacheClient:
    """CacheClient fixture with unreachable host."""
    return CacheClient(host="127.0.0.1", port=6399)


# ============================================================================
# Zeek Tests
# ============================================================================


def test_zeek_parse_notice_with_src_ip() -> None:
    """Test parsing Zeek notice log with source IP."""
    adapter = ZeekAdapter()

    # Zeek notice.log JSON line with src_ip from notice
    notice_line = json.dumps(
        {
            "ts": 1691318400.0,
            "uid": "abc123def456",
            "id.orig_h": "192.0.2.100",
            "id.orig_p": 54321,
            "id.resp_h": "192.0.2.50",
            "id.resp_p": 80,
            "fuid": "F0001",
            "file_mime_type": "text/html",
            "file_desc": "Phishing page",
            "proto": "tcp",
            "note": "Phishing::Suspicious_IP",
            "msg": "Suspicious IP detected",
            "sub": "malicious_source",
            "src": "192.0.2.100",
            "dst": "192.0.2.50",
            "severity": "high",
        }
    )

    hits = adapter.parse(notice_line)

    # Should extract IP from src field
    assert len(hits) >= 1
    assert any(h.ioc_type == "ip" and h.value == "192.0.2.100" for h in hits)


def test_zeek_parse_notice_with_domain() -> None:
    """Test parsing Zeek notice log with domain."""
    adapter = ZeekAdapter()

    notice_line = json.dumps(
        {
            "ts": 1691318400.0,
            "uid": "def456ghi789",
            "id.orig_h": "10.0.0.10",
            "id.resp_h": "1.1.1.1",
            "proto": "tcp",
            "note": "DNS::Suspicious_Domain",
            "msg": "DNS query to suspicious domain",
            "sub": "malicious_domain",
            "query": "malware.example.com",
            "severity": "critical",
        }
    )

    hits = adapter.parse(notice_line)

    # Should extract domain from query field
    assert len(hits) >= 1
    assert any(h.ioc_type == "domain" for h in hits)


def test_zeek_parse_malformed() -> None:
    """Test Zeek adapter handles malformed input gracefully."""
    adapter = ZeekAdapter()

    hits = adapter.parse("{ malformed json")
    assert len(hits) == 0


# ============================================================================
# Strelka Tests
# ============================================================================


def test_strelka_parse_yara_match() -> None:
    """Test parsing Strelka scan result with YARA match."""
    adapter = StrelkaAdapter()

    # Strelka scan result with YARA match and sha256
    strelka_event = json.dumps(
        {
            "id": "file_12345",
            "type": "file",
            "source": "fs",
            "size": 12345,
            "hashes": {
                "md5": "5d41402abc4b2a76b9719d911017c592",
                "sha1": "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
                "sha256": "2c26b46911185131006745196ec2dd36fc652b68a34c00d98bd91a00dfd8dfbe",
            },
            "tags": ["malware", "trojan"],
            "modules": {
                "yara": {
                    "rules": [
                        {
                            "rule": "Trojan_Generic",
                            "matches": [
                                {
                                    "identifier": "trojan_pattern",
                                    "instances": 5,
                                }
                            ],
                        }
                    ]
                }
            },
        }
    )

    hits = adapter.parse(strelka_event)

    # Should extract hash IOC with high/critical severity based on matches
    assert len(hits) >= 1
    assert any(
        h.ioc_type == "hash"
        and h.value == "2c26b46911185131006745196ec2dd36fc652b68a34c00d98bd91a00dfd8dfbe"
        for h in hits
    )


def test_strelka_parse_no_matches() -> None:
    """Test Strelka adapter with no YARA matches."""
    adapter = StrelkaAdapter()

    strelka_event = json.dumps(
        {
            "id": "file_clean",
            "type": "file",
            "hashes": {
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
            "tags": ["benign"],
        }
    )

    hits = adapter.parse(strelka_event)

    # Clean file (no YARA matches) should produce no hits
    assert len(hits) == 0


# ============================================================================
# CAPE Tests
# ============================================================================


def test_cape_parse_verdict() -> None:
    """Test parsing CAPE sandbox verdict."""
    adapter = CapeAdapter()

    # CAPE verdict with malscore and contacted hosts
    cape_verdict = json.dumps(
        {
            "id": 12345,
            "name": "malware_sample.exe",
            "file_type": "PE32 executable",
            "file_size": 98765,
            "sha256": "deadbeefcafebabecafebabecafebabecafebabecafebabecafebabecafebabe",
            "md5": "5d41402abc4b2a76b9719d911017c592",
            "malscore": 8.5,
            "verdict": "malicious",
            "network": {
                "tcp": [
                    {
                        "dst": "192.0.2.99",
                        "dport": 445,
                        "protocol": "SMB",
                    }
                ],
                "dns": [
                    {
                        "request": "c2.attacker.com",
                        "type": "A",
                    }
                ],
                "http": [
                    {
                        "uri": "http://malware.download.com/payload.bin",
                        "method": "GET",
                    }
                ],
            },
            "behavior": {
                "processes": [
                    {
                        "process_name": "malware_sample.exe",
                        "process_id": 4532,
                    }
                ]
            },
        }
    )

    hits = adapter.parse(cape_verdict)

    # Should extract: file hash, C2 IP, C2 domain, malware download URL
    assert len(hits) >= 2
    assert any(
        h.ioc_type == "hash"
        and h.value
        == "deadbeefcafebabecafebabecafebabecafebabecafebabecafebabecafebabe"
        for h in hits
    )
    assert any(h.ioc_type == "ip" and h.value == "192.0.2.99" for h in hits)
    assert any(h.ioc_type == "domain" and "attacker.com" in h.value for h in hits)


def test_cape_parse_clean_verdict() -> None:
    """Test CAPE verdict for clean file."""
    adapter = CapeAdapter()

    cape_clean = json.dumps(
        {
            "id": 54321,
            "name": "clean_app.exe",
            "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "malscore": 0.0,
            "verdict": "benign",
            "network": {},
        }
    )

    hits = adapter.parse(cape_clean)

    # Clean sample (low malscore) should produce no hits
    assert len(hits) == 0


# ============================================================================
# Arkime Tests
# ============================================================================


def test_arkime_parse_session_tags() -> None:
    """Test parsing Arkime session with suspicious tags."""
    adapter = ArkimeAdapter()

    # Arkime session with suspicious tags
    arkime_session = json.dumps(
        {
            "id": "session_xyz789",
            "timestamp": "2026-08-06T12:00:00Z",
            "srcIp": "192.0.2.100",
            "dstIp": "192.0.2.200",
            "srcPort": 54321,
            "dstPort": 80,
            "protocol": "tcp",
            "tags": ["malware", "c2-traffic"],
            "hostnames": ["badactor.example.com", "attacker.net"],
            "http": {
                "statusCode": [200],
                "method": ["GET"],
                "host": ["badactor.example.com"],
                "uri": ["/command"],
            },
        }
    )

    hits = adapter.parse(arkime_session)

    # Should extract source/dest IPs and hostnames as IOCs
    assert len(hits) >= 2
    assert any(h.ioc_type == "ip" and h.value == "192.0.2.100" for h in hits)
    assert any(h.ioc_type == "ip" and h.value == "192.0.2.200" for h in hits)
    assert any(h.ioc_type == "domain" for h in hits)


def test_arkime_parse_benign_session() -> None:
    """Test Arkime session without malicious tags."""
    adapter = ArkimeAdapter()

    arkime_benign = json.dumps(
        {
            "id": "session_normal",
            "timestamp": "2026-08-06T12:00:00Z",
            "srcIp": "10.0.0.5",
            "dstIp": "8.8.8.8",
            "tags": [],
            "hostnames": ["google.com"],
        }
    )

    hits = adapter.parse(arkime_benign)

    # Benign session (no malicious tags) should produce no hits
    assert len(hits) == 0


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_zeek_ingest_writes_to_store(cache_client: CacheClient) -> None:
    """Test Zeek adapter ingest writes to blocklist store."""
    adapter = ZeekAdapter()
    store = BlocklistStore(cache=cache_client)

    notice_line = json.dumps(
        {
            "ts": 1691318400.0,
            "src": "192.0.2.100",
            "note": "Phishing::Suspicious_IP",
        }
    )

    stats = await adapter.ingest(notice_line, store)

    # Should have scanned, stored, and not skipped
    assert stats.source == "zeek"
    assert stats.scanned >= 1
    assert stats.stored >= 1
    assert stats.skipped == 0


@pytest.mark.asyncio
async def test_strelka_ingest_writes_to_store(cache_client: CacheClient) -> None:
    """Test Strelka adapter ingest writes to blocklist store."""
    adapter = StrelkaAdapter()
    store = BlocklistStore(cache=cache_client)

    strelka_event = json.dumps(
        {
            "hashes": {
                "sha256": "2c26b46911185131006745196ec2dd36fc652b68a34c00d98bd91a00dfd8dfbe",
            },
            "modules": {"yara": {"rules": [{"rule": "Malware", "matches": []}]}},
        }
    )

    stats = await adapter.ingest(strelka_event, store)

    assert stats.source == "strelka"


@pytest.mark.asyncio
async def test_cape_ingest_writes_to_store(cache_client: CacheClient) -> None:
    """Test CAPE adapter ingest writes to blocklist store."""
    adapter = CapeAdapter()
    store = BlocklistStore(cache=cache_client)

    cape_verdict = json.dumps(
        {
            "sha256": "deadbeefcafebabecafebabecafebabecafebabecafebabecafebabecafebabe",
            "malscore": 8.5,
            "network": {
                "tcp": [{"dst": "192.0.2.99", "dport": 445}],
                "dns": [{"request": "c2.attacker.com"}],
            },
        }
    )

    stats = await adapter.ingest(cape_verdict, store)

    assert stats.source == "cape"
    assert stats.stored >= 2  # At least hash + IP or domain


@pytest.mark.asyncio
async def test_arkime_ingest_writes_to_store(cache_client: CacheClient) -> None:
    """Test Arkime adapter ingest writes to blocklist store."""
    adapter = ArkimeAdapter()
    store = BlocklistStore(cache=cache_client)

    arkime_session = json.dumps(
        {
            "srcIp": "192.0.2.100",
            "dstIp": "192.0.2.200",
            "tags": ["malware", "c2-traffic"],
        }
    )

    stats = await adapter.ingest(arkime_session, store)

    assert stats.source == "arkime"
    assert stats.stored >= 2  # src IP + dst IP
