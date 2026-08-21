"""Direct unit tests for feed source ingestion (fetch -> parse -> store).

Uses real_dal for storage (per repo convention: real DB, never mocked) and a
minimal fake aiohttp session for the network fetch (the one layer that must
be faked — no real network calls in unit tests). DNS resolution is mocked
via the `_mock_safe_dns` autouse fixture so ".example" test hostnames (which
do not really resolve) behave as a normal public address by default; SSRF
regression tests below override this per-test to simulate malicious/rebound
resolution.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.threatintel.feeds.ingestor import FEED_SOURCE_TYPES, ingest_feed_source
from hub_api.modules.threatintel.feeds.url_safety import UnsafeFeedURLError


def _fake_resolve_default(host: str) -> list[str]:
    """Pass literal IPs through unchanged; fake hostnames resolve to 8.8.8.8.

    Literal-IP test cases (e.g. http://169.254.169.254/...) exercise the
    real guard logic against a real address with no DNS involved. Fictional
    ".example" test hostnames would otherwise fail real DNS resolution, so
    they're given a safe public stand-in address.
    """
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        return ["8.8.8.8"]


@pytest.fixture(autouse=True)
def _mock_safe_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default all feed URL DNS resolution to a safe public IP (8.8.8.8).

    Individual SSRF regression tests override this to simulate a hostname
    resolving to a private/internal address (DNS rebinding scenario).
    """
    monkeypatch.setattr(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        _fake_resolve_default,
    )


class _FakeResponse:
    """Minimal async-context-manager stand-in for aiohttp.ClientResponse."""

    def __init__(self, status: int, body: str, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def text(self) -> str:
        return self._body

    async def json(self, content_type: Any = None) -> Any:
        return json.loads(self._body)


class _FakeSession:
    """Minimal stand-in for aiohttp.ClientSession exposing only .get().

    Supports a single fixed response, or a list of responses consumed in
    order (one per .get() call) to simulate a redirect chain.
    """

    def __init__(
        self,
        status: int | None = None,
        body: str = "",
        *,
        responses: list[_FakeResponse] | None = None,
    ) -> None:
        self._responses = responses if responses is not None else None
        self._status = status
        self._body = body
        self.calls: list[str] = []

    def get(self, url: str, timeout: Any = None, allow_redirects: bool = True) -> _FakeResponse:
        self.calls.append(url)
        if self._responses is not None:
            return self._responses[len(self.calls) - 1]
        assert self._status is not None
        return _FakeResponse(self._status, self._body)

    @property
    def last_url(self) -> str | None:
        return self.calls[-1] if self.calls else None


@pytest.mark.asyncio
async def test_ingest_feed_source_csv_success(real_dal: AsyncDB) -> None:
    """CSV source: fetched rows are parsed and stored, tagged source='csv'."""
    tenant_id = str(uuid4())
    csv_body = "domain,confidence\nmalicious-csv.example.com,80\n"
    session = _FakeSession(200, csv_body)

    stats = await ingest_feed_source(
        real_dal, tenant_id, "csv", "https://x.example/feed.csv", session
    )

    assert stats == {"added": 1, "updated": 0, "errors": 0}

    rows = await real_dal(
        (real_dal.threat_indicators.tenant_id == tenant_id)
        & (real_dal.threat_indicators.value == "malicious-csv.example.com")
    ).select()
    row = rows.first()
    assert row is not None
    assert row["source"] == "csv"
    assert row["confidence"] == 80


@pytest.mark.asyncio
async def test_ingest_feed_source_misp_success(real_dal: AsyncDB) -> None:
    """MISP source: attributes are parsed and stored, tagged source='misp'."""
    tenant_id = str(uuid4())
    misp_payload = {
        "response": [
            {
                "id": "1",
                "info": "test event",
                "Attribute": [
                    {"type": "domain", "value": "misp-bad.example.com", "confidence": 90}
                ],
            }
        ]
    }
    session = _FakeSession(200, json.dumps(misp_payload))

    stats = await ingest_feed_source(
        real_dal, tenant_id, "misp", "https://misp.example/export.json", session
    )

    assert stats == {"added": 1, "updated": 0, "errors": 0}

    rows = await real_dal(
        (real_dal.threat_indicators.tenant_id == tenant_id)
        & (real_dal.threat_indicators.value == "misp-bad.example.com")
    ).select()
    row = rows.first()
    assert row is not None
    assert row["source"] == "misp"


@pytest.mark.asyncio
async def test_ingest_feed_source_stix_success(real_dal: AsyncDB) -> None:
    """STIX source: bundle indicators are parsed and stored, tagged source='stix'."""
    tenant_id = str(uuid4())
    stix_payload = {
        "objects": [
            {
                "type": "indicator",
                "id": "indicator--abc",
                "pattern": "[domain-name:value = 'stix-bad.example.com']",
                "labels": ["malicious-activity"],
                "confidence": "high",
            }
        ]
    }
    session = _FakeSession(200, json.dumps(stix_payload))

    stats = await ingest_feed_source(
        real_dal, tenant_id, "stix", "https://stix.example/bundle.json", session
    )

    assert stats == {"added": 1, "updated": 0, "errors": 0}

    rows = await real_dal(
        (real_dal.threat_indicators.tenant_id == tenant_id)
        & (real_dal.threat_indicators.value == "stix-bad.example.com")
    ).select()
    row = rows.first()
    assert row is not None
    assert row["source"] == "stix"


@pytest.mark.asyncio
async def test_ingest_feed_source_taxii_parsed_as_stix(real_dal: AsyncDB) -> None:
    """TAXII source: collection payload (STIX bundle) is parsed, tagged source='taxii'."""
    tenant_id = str(uuid4())
    taxii_payload = {
        "objects": [
            {
                "type": "indicator",
                "id": "indicator--def",
                "pattern": "[ipv4-addr:value = '8.8.4.4']",
                "labels": ["malicious-activity"],
                "confidence": "low",
            }
        ]
    }
    session = _FakeSession(200, json.dumps(taxii_payload))

    stats = await ingest_feed_source(
        real_dal, tenant_id, "taxii", "https://taxii.example/collections/1/objects", session
    )

    assert stats == {"added": 1, "updated": 0, "errors": 0}

    rows = await real_dal(
        (real_dal.threat_indicators.tenant_id == tenant_id)
        & (real_dal.threat_indicators.value == "8.8.4.4")
    ).select()
    row = rows.first()
    assert row is not None
    assert row["source"] == "taxii"


@pytest.mark.asyncio
async def test_ingest_feed_source_update_existing(real_dal: AsyncDB) -> None:
    """Re-ingesting the same value updates rather than re-adding it."""
    tenant_id = str(uuid4())
    csv_body = "domain,confidence\nrepeat.example.com,50\n"
    session = _FakeSession(200, csv_body)

    first = await ingest_feed_source(
        real_dal, tenant_id, "csv", "https://x.example/feed.csv", session
    )
    assert first == {"added": 1, "updated": 0, "errors": 0}

    second = await ingest_feed_source(
        real_dal, tenant_id, "csv", "https://x.example/feed.csv", session
    )
    assert second == {"added": 0, "updated": 1, "errors": 0}


@pytest.mark.asyncio
async def test_ingest_feed_source_invalid_source_type_raises(real_dal: AsyncDB) -> None:
    """An unsupported source_type raises ValueError before any fetch."""
    session = _FakeSession(200, "")

    with pytest.raises(ValueError):
        await ingest_feed_source(
            real_dal, str(uuid4()), "openioc", "https://x.example/feed", session
        )


@pytest.mark.asyncio
async def test_ingest_feed_source_http_error_raises(real_dal: AsyncDB) -> None:
    """A non-200 response raises RuntimeError (caller records the failure)."""
    session = _FakeSession(503, "")

    with pytest.raises(RuntimeError):
        await ingest_feed_source(
            real_dal, str(uuid4()), "csv", "https://x.example/feed.csv", session
        )


def test_feed_source_types_matches_valid_source_types() -> None:
    """FEED_SOURCE_TYPES stays in sync with the four supported source types."""
    assert FEED_SOURCE_TYPES == {"misp", "stix", "taxii", "csv"}


# --- SSRF guard -------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_feed_source_rejects_cloud_metadata_ip(real_dal: AsyncDB) -> None:
    """A URL literally targeting the cloud metadata IP is rejected before fetch."""
    # SSRF guard
    session = _FakeSession(200, "domain\nshould-not-be-reached.com\n")

    with pytest.raises(UnsafeFeedURLError):
        await ingest_feed_source(
            real_dal,
            str(uuid4()),
            "csv",
            "http://169.254.169.254/latest/meta-data/",
            session,
        )

    assert session.calls == []  # never attempted the fetch


@pytest.mark.asyncio
async def test_ingest_feed_source_rejects_loopback_ip(real_dal: AsyncDB) -> None:
    """A URL targeting 127.0.0.1 is rejected before fetch."""
    # SSRF guard
    session = _FakeSession(200, "domain\nshould-not-be-reached.com\n")

    with pytest.raises(UnsafeFeedURLError):
        await ingest_feed_source(real_dal, str(uuid4()), "csv", "http://127.0.0.1/x", session)

    assert session.calls == []


@pytest.mark.asyncio
async def test_ingest_feed_source_rejects_private_ip(real_dal: AsyncDB) -> None:
    """A URL targeting an RFC1918 private address is rejected before fetch."""
    # SSRF guard
    session = _FakeSession(200, "domain\nshould-not-be-reached.com\n")

    with pytest.raises(UnsafeFeedURLError):
        await ingest_feed_source(real_dal, str(uuid4()), "csv", "http://10.0.0.1/x", session)

    assert session.calls == []


@pytest.mark.asyncio
async def test_ingest_feed_source_rejects_hostname_resolving_to_private_ip(
    real_dal: AsyncDB,
) -> None:
    """A public-looking hostname that resolves to a private IP is rejected (mocked DNS)."""
    # SSRF guard
    session = _FakeSession(200, "domain\nshould-not-be-reached.com\n")

    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["10.0.0.5"],
    ):
        with pytest.raises(UnsafeFeedURLError):
            await ingest_feed_source(
                real_dal,
                str(uuid4()),
                "csv",
                "https://sneaky-feed.example.com/feed.csv",
                session,
            )

    assert session.calls == []


@pytest.mark.asyncio
async def test_ingest_feed_source_allows_public_url(real_dal: AsyncDB) -> None:
    """A normal public URL (resolves to a public IP via the autouse mock) is fetched."""
    # SSRF guard
    tenant_id = str(uuid4())
    session = _FakeSession(200, "domain,confidence\nallowed.example.com,60\n")

    stats = await ingest_feed_source(
        real_dal, tenant_id, "csv", "https://feeds.example.com/threat.csv", session
    )

    assert stats == {"added": 1, "updated": 0, "errors": 0}
    assert session.calls == ["https://feeds.example.com/threat.csv"]


@pytest.mark.asyncio
async def test_ingest_feed_source_redirect_to_unsafe_target_rejected(real_dal: AsyncDB) -> None:
    """A redirect hop pointing at an internal address is rejected, not followed."""
    # SSRF guard
    responses = [
        _FakeResponse(302, "", headers={"Location": "http://169.254.169.254/latest/meta-data/"}),
    ]
    session = _FakeSession(responses=responses)

    with pytest.raises(UnsafeFeedURLError):
        await ingest_feed_source(
            real_dal, str(uuid4()), "csv", "https://feeds.example.com/redirects", session
        )

    # Only the first (safe) hop was attempted; the unsafe redirect target was
    # validated and rejected before a second request was ever made.
    assert session.calls == ["https://feeds.example.com/redirects"]


@pytest.mark.asyncio
async def test_ingest_feed_source_redirect_missing_location_rejected(real_dal: AsyncDB) -> None:
    """A 3xx response with no Location header fails closed rather than looping."""
    # SSRF guard
    responses = [_FakeResponse(302, "", headers={})]
    session = _FakeSession(responses=responses)

    with pytest.raises(RuntimeError, match="missing Location"):
        await ingest_feed_source(
            real_dal, str(uuid4()), "csv", "https://feeds.example.com/redirects", session
        )


@pytest.mark.asyncio
async def test_ingest_feed_source_follows_safe_redirect(real_dal: AsyncDB) -> None:
    """A redirect to another safe, public URL is validated per-hop and followed."""
    # SSRF guard
    tenant_id = str(uuid4())
    responses = [
        _FakeResponse(302, "", headers={"Location": "https://feeds-cdn.example.com/final.csv"}),
        _FakeResponse(200, "domain,confidence\nredirected.example.com,70\n"),
    ]
    session = _FakeSession(responses=responses)

    stats = await ingest_feed_source(
        real_dal, tenant_id, "csv", "https://feeds.example.com/redirects", session
    )

    assert stats == {"added": 1, "updated": 0, "errors": 0}
    assert session.calls == [
        "https://feeds.example.com/redirects",
        "https://feeds-cdn.example.com/final.csv",
    ]


@pytest.mark.asyncio
async def test_ingest_feed_source_too_many_redirects_rejected(real_dal: AsyncDB) -> None:
    """A redirect chain exceeding the hop limit fails closed."""
    # SSRF guard
    responses = [
        _FakeResponse(302, "", headers={"Location": f"https://feeds.example.com/hop{i}"})
        for i in range(10)
    ]
    session = _FakeSession(responses=responses)

    with pytest.raises(RuntimeError, match="too many redirects"):
        await ingest_feed_source(
            real_dal, str(uuid4()), "csv", "https://feeds.example.com/redirects", session
        )
