"""Direct unit tests for feed source ingestion (fetch -> parse -> store).

Uses real_dal for storage (per repo convention: real DB, never mocked) and a
minimal fake aiohttp session for the network fetch (the one layer that must
be faked — no real network calls in unit tests).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.threatintel.feeds.ingestor import FEED_SOURCE_TYPES, ingest_feed_source


class _FakeResponse:
    """Minimal async-context-manager stand-in for aiohttp.ClientResponse."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def text(self) -> str:
        return self._body

    async def json(self, content_type: Any = None) -> Any:
        return json.loads(self._body)


class _FakeSession:
    """Minimal stand-in for aiohttp.ClientSession exposing only .get()."""

    def __init__(self, status: int, body: str) -> None:
        self._status = status
        self._body = body
        self.last_url: str | None = None

    def get(self, url: str, timeout: Any = None) -> _FakeResponse:
        self.last_url = url
        return _FakeResponse(self._status, self._body)


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
                "pattern": "[ipv4-addr:value = '8.8.8.8']",
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
        & (real_dal.threat_indicators.value == "8.8.8.8")
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
