"""Tests for threat intelligence feed parsers."""
from __future__ import annotations

from datetime import datetime

import pytest

from hub_api.modules.threatintel.feeds import (
    FeedSource,
    ThreatType,
    parse_misp_feed,
    parse_openioc_feed,
    parse_stix_bundle,
    parse_threat_csv,
)


class TestMispFeedParser:
    """Test MISP feed parser."""

    def test_parse_misp_feed_valid_event(self) -> None:
        """Test parsing valid MISP event with attributes."""
        payload = {
            "Event": {
                "id": "12345",
                "info": "Test malware indicators",
                "Attribute": [
                    {
                        "id": "attr-001",
                        "type": "domain",
                        "value": "malware.example.com",
                        "confidence": 85,
                        "category": "malware",
                        "first_seen": "2025-01-01T00:00:00Z",
                        "last_seen": "2025-01-02T00:00:00Z",
                        "Tag": [{"name": "botnet"}],
                    }
                ],
            }
        }

        indicators = parse_misp_feed(payload)

        assert len(indicators) == 1
        indicator = indicators[0]
        assert indicator.value == "malware.example.com"
        assert indicator.indicator_type == "domain"
        assert indicator.confidence == 85
        assert indicator.threat_types == [ThreatType.BLACKLISTED_DOMAIN]

    def test_parse_misp_feed_ip_attribute(self) -> None:
        """Test parsing MISP event with IP indicators."""
        payload = {
            "Event": {
                "id": "12346",
                "info": "Test IP indicators",
                "Attribute": [
                    {
                        "id": "attr-002",
                        "type": "ip-src",
                        "value": "1.1.1.1",
                        "confidence": 90,
                        "category": "malware",
                    }
                ],
            }
        }

        indicators = parse_misp_feed(payload)

        assert len(indicators) == 1
        indicator = indicators[0]
        assert indicator.value == "1.1.1.1"
        assert indicator.indicator_type == "ip"
        assert indicator.threat_types == [ThreatType.BLACKLISTED_IP]

    def test_parse_misp_feed_provenance_in_metadata(self) -> None:
        """Test that MISP provenance keys are populated in metadata."""
        payload = {
            "Event": {
                "id": "evt-123",
                "info": "Security incident",
                "Attribute": [
                    {
                        "id": "attr-456",
                        "type": "domain",
                        "value": "c2.malware.net",
                        "confidence": 75,
                        "category": "malware",
                    }
                ],
            }
        }

        indicators = parse_misp_feed(payload)

        assert len(indicators) == 1
        metadata = indicators[0].metadata
        assert metadata["source_format"] == "misp"
        assert metadata["misp_event_id"] == "evt-123"
        assert metadata["misp_attribute_id"] == "attr-456"
        assert "misp_event" in metadata
        assert "misp_category" in metadata

    def test_parse_misp_feed_malformed_skips_record(self) -> None:
        """Test that malformed MISP attributes are skipped."""
        payload = {
            "Event": {
                "id": "12347",
                "info": "Mixed valid/invalid",
                "Attribute": [
                    {
                        "id": "attr-good",
                        "type": "domain",
                        "value": "valid.example.com",
                        "confidence": 80,
                        "category": "malware",
                    },
                    {
                        "id": "attr-bad",
                        "type": "domain",
                        "value": "invalid",  # Invalid domain (no dot)
                        "confidence": 80,
                        "category": "malware",
                    },
                ],
            }
        }

        indicators = parse_misp_feed(payload)

        # Should have only the valid one
        assert len(indicators) == 1
        assert indicators[0].value == "valid.example.com"

    def test_parse_misp_feed_empty_returns_empty_list(self) -> None:
        """Test that empty or malformed payload returns empty list."""
        indicators = parse_misp_feed({})
        assert indicators == []

        indicators = parse_misp_feed([])
        assert indicators == []


class TestOpenIOCFeedParser:
    """Test OpenIOC feed parser."""

    def test_parse_openioc_feed_domain_indicator(self) -> None:
        """Test parsing OpenIOC XML with domain indicator."""
        xml = """<?xml version="1.0"?>
<IOC id="ioc-001" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <short_description>Test IOC</short_description>
    <description>Test indicator</description>
    <IndicatorItem>
        <Context type="Network/DNS" document="DNS" search="DNS" />
        <Content>malicious.example.com</Content>
    </IndicatorItem>
</IOC>"""

        indicators = parse_openioc_feed(xml)

        assert len(indicators) == 1
        indicator = indicators[0]
        assert indicator.value == "malicious.example.com"
        assert indicator.indicator_type == "domain"
        assert indicator.threat_types == [ThreatType.BLACKLISTED_DOMAIN]

    def test_parse_openioc_feed_ip_indicator(self) -> None:
        """Test parsing OpenIOC XML with IP indicator."""
        xml = """<?xml version="1.0"?>
<IOC id="ioc-002">
    <short_description>IP Threat</short_description>
    <IndicatorItem>
        <Context type="Network/IP" />
        <Content>1.2.3.4</Content>
    </IndicatorItem>
</IOC>"""

        indicators = parse_openioc_feed(xml)

        assert len(indicators) == 1
        indicator = indicators[0]
        assert indicator.value == "1.2.3.4"
        assert indicator.indicator_type == "ip"
        assert indicator.threat_types == [ThreatType.BLACKLISTED_IP]

    def test_parse_openioc_feed_provenance_in_metadata(self) -> None:
        """Test that OpenIOC provenance keys are populated in metadata."""
        xml = """<?xml version="1.0"?>
<IOC id="ioc-xyz" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <short_description>My IOC</short_description>
    <description>Test description</description>
    <IndicatorItem>
        <Context type="Network/DNS" document="test-doc" search="test-search" />
        <Content>threat.net</Content>
    </IndicatorItem>
</IOC>"""

        indicators = parse_openioc_feed(xml)

        assert len(indicators) == 1
        metadata = indicators[0].metadata
        assert metadata["source_format"] == "openioc"
        assert metadata["openioc_id"] == "ioc-xyz"
        assert "openioc_context" in metadata
        assert metadata["openioc_name"] == "My IOC"

    def test_parse_openioc_feed_malformed_skips(self) -> None:
        """Test that malformed OpenIOC records are skipped."""
        xml = """<?xml version="1.0"?>
<IOC id="ioc-003">
    <IndicatorItem>
        <Context type="Network/DNS" />
        <Content>valid.example.com</Content>
    </IndicatorItem>
    <IndicatorItem>
        <Context type="Network/DNS" />
        <Content>invalid</Content>
    </IndicatorItem>
</IOC>"""

        indicators = parse_openioc_feed(xml)

        # Should skip the invalid domain
        assert len(indicators) == 1
        assert indicators[0].value == "valid.example.com"

    def test_parse_openioc_feed_invalid_xml_returns_empty(self) -> None:
        """Test that invalid XML returns empty list."""
        xml = "not valid xml"
        indicators = parse_openioc_feed(xml)
        assert indicators == []


class TestCSVFeedParser:
    """Test CSV feed parser."""

    def test_parse_threat_csv_domain_column(self) -> None:
        """Test parsing CSV with domain column."""
        csv_text = """domain,confidence,category
malware.example.com,85,malware
phishing.site.net,75,phishing
"""

        indicators = parse_threat_csv(csv_text)

        assert len(indicators) == 2
        assert indicators[0].value == "malware.example.com"
        assert indicators[0].indicator_type == "domain"
        assert indicators[0].confidence == 85
        assert indicators[1].value == "phishing.site.net"
        assert indicators[1].confidence == 75

    def test_parse_threat_csv_ip_column(self) -> None:
        """Test parsing CSV with IP column."""
        csv_text = """ip,confidence,category
1.1.1.1,90,botnet
2.2.2.2,80,c2
"""

        indicators = parse_threat_csv(csv_text)

        assert len(indicators) == 2
        assert indicators[0].value == "1.1.1.1"
        assert indicators[0].indicator_type == "ip"
        assert indicators[0].threat_types == [ThreatType.BLACKLISTED_IP]

    def test_parse_threat_csv_provenance_in_metadata(self) -> None:
        """Test that CSV provenance keys are populated in metadata."""
        csv_text = """domain,confidence,category
test.example.com,75,spam
"""

        indicators = parse_threat_csv(csv_text)

        assert len(indicators) == 1
        metadata = indicators[0].metadata
        assert metadata["source_format"] == "csv"
        assert "csv_row" in metadata
        assert "category" in metadata

    def test_parse_threat_csv_malformed_rows_skipped(self) -> None:
        """Test that malformed CSV rows are skipped."""
        csv_text = """domain,confidence,category
valid.example.com,85,malware
invalid,90,malware
another.valid.com,75,spam
"""

        indicators = parse_threat_csv(csv_text)

        # Should skip "invalid" (no dot)
        assert len(indicators) == 2
        values = {ind.value for ind in indicators}
        assert "valid.example.com" in values
        assert "another.valid.com" in values

    def test_parse_threat_csv_missing_confidence_defaults(self) -> None:
        """Test that missing confidence defaults to 50."""
        csv_text = """domain
example.com
"""

        indicators = parse_threat_csv(csv_text)

        assert len(indicators) == 1
        assert indicators[0].confidence == 50

    def test_parse_threat_csv_empty_returns_empty_list(self) -> None:
        """Test that empty CSV returns empty list."""
        csv_text = ""
        indicators = parse_threat_csv(csv_text)
        assert indicators == []


class TestSTIXBundleParser:
    """Test STIX bundle parser."""

    def test_parse_stix_bundle_valid_indicator(self) -> None:
        """Test parsing STIX bundle with domain indicator."""
        payload = {
            "type": "bundle",
            "id": "bundle--001",
            "objects": [
                {
                    "type": "indicator",
                    "id": "indicator--001",
                    "pattern": "[domain-name:value = 'malware.example.com']",
                    "labels": ["malicious-activity"],
                    "confidence": "high",
                }
            ],
        }

        indicators = parse_stix_bundle(payload)

        assert len(indicators) == 1
        indicator = indicators[0]
        assert indicator.value == "malware.example.com"
        assert indicator.indicator_type == "domain"
        assert indicator.confidence == 90  # high = 90

    def test_parse_stix_bundle_ipv4_indicator(self) -> None:
        """Test parsing STIX bundle with IPv4 indicator."""
        payload = {
            "type": "bundle",
            "objects": [
                {
                    "type": "indicator",
                    "pattern": "[ipv4-addr:value = '1.1.1.1']",
                    "labels": ["malicious-activity"],
                    "confidence": "medium",
                }
            ],
        }

        indicators = parse_stix_bundle(payload)

        assert len(indicators) == 1
        assert indicators[0].value == "1.1.1.1"
        assert indicators[0].indicator_type == "ip"
        assert indicators[0].confidence == 70  # medium = 70

    def test_parse_stix_bundle_provenance_in_metadata(self) -> None:
        """Test that STIX provenance keys are populated in metadata."""
        payload = {
            "type": "bundle",
            "objects": [
                {
                    "type": "indicator",
                    "id": "indicator--xyz",
                    "pattern": "[domain-name:value = 'stix.test.com']",
                    "labels": ["c2-traffic"],
                    "valid_from": "2025-01-01T00:00:00Z",
                    "valid_until": "2025-12-31T23:59:59Z",
                }
            ],
        }

        indicators = parse_stix_bundle(payload)

        assert len(indicators) == 1
        metadata = indicators[0].metadata
        assert metadata["source_format"] == "stix"
        assert metadata["stix_id"] == "indicator--xyz"
        assert "stix_pattern" in metadata
        assert "stix_labels" in metadata

    def test_parse_stix_bundle_multiple_indicators(self) -> None:
        """Test parsing STIX bundle with multiple indicators."""
        payload = {
            "type": "bundle",
            "objects": [
                {
                    "type": "indicator",
                    "pattern": "[domain-name:value = 'domain1.com']",
                },
                {
                    "type": "indicator",
                    "pattern": "[domain-name:value = 'domain2.com']",
                },
                {
                    "type": "malware",  # Non-indicator object, should be skipped
                    "id": "malware--001",
                },
            ],
        }

        indicators = parse_stix_bundle(payload)

        # Should extract only the two indicators
        assert len(indicators) == 2
        values = {ind.value for ind in indicators}
        assert "domain1.com" in values
        assert "domain2.com" in values

    def test_parse_stix_bundle_json_string_input(self) -> None:
        """Test parsing STIX bundle from JSON string."""
        import json

        payload_dict = {
            "type": "bundle",
            "objects": [
                {
                    "type": "indicator",
                    "pattern": "[domain-name:value = 'string-input.com']",
                }
            ],
        }
        payload_str = json.dumps(payload_dict)

        indicators = parse_stix_bundle(payload_str)

        assert len(indicators) == 1
        assert indicators[0].value == "string-input.com"

    def test_parse_stix_bundle_invalid_json_returns_empty(self) -> None:
        """Test that invalid JSON returns empty list."""
        indicators = parse_stix_bundle("not valid json")
        assert indicators == []

    def test_parse_stix_bundle_confidence_mapping(self) -> None:
        """Test STIX confidence level mapping."""
        for confidence_str, expected_value in [
            ("high", 90),
            ("medium", 70),
            ("low", 30),
            ("unknown", 50),  # Default
        ]:
            payload = {
                "type": "bundle",
                "objects": [
                    {
                        "type": "indicator",
                        "pattern": "[domain-name:value = 'test.com']",
                        "confidence": confidence_str,
                    }
                ],
            }

            indicators = parse_stix_bundle(payload)
            assert len(indicators) == 1
            assert indicators[0].confidence == expected_value, f"Failed for {confidence_str}"


class TestParserMetadata:
    """Test that all parsers populate metadata correctly."""

    def test_all_parsers_populate_metadata(self) -> None:
        """Test that all parsers populate metadata field."""
        # MISP
        misp_payload = {
            "Event": {
                "id": "1",
                "Attribute": [
                    {"type": "domain", "value": "test.com", "confidence": 50}
                ],
            }
        }
        misp_indicators = parse_misp_feed(misp_payload)
        assert len(misp_indicators) > 0
        assert isinstance(misp_indicators[0].metadata, dict)
        assert "source_format" in misp_indicators[0].metadata

        # OpenIOC
        openioc_xml = """<?xml version="1.0"?>
<IOC id="1">
<IndicatorItem>
<Context type="Network/DNS" />
<Content>test.com</Content>
</IndicatorItem>
</IOC>"""
        openioc_indicators = parse_openioc_feed(openioc_xml)
        assert len(openioc_indicators) > 0
        assert isinstance(openioc_indicators[0].metadata, dict)
        assert "source_format" in openioc_indicators[0].metadata

        # CSV
        csv_text = "domain\ntest.com"
        csv_indicators = parse_threat_csv(csv_text)
        assert len(csv_indicators) > 0
        assert isinstance(csv_indicators[0].metadata, dict)
        assert "source_format" in csv_indicators[0].metadata

        # STIX
        stix_payload = {
            "type": "bundle",
            "objects": [
                {
                    "type": "indicator",
                    "pattern": "[domain-name:value = 'test.com']",
                }
            ],
        }
        stix_indicators = parse_stix_bundle(stix_payload)
        assert len(stix_indicators) > 0
        assert isinstance(stix_indicators[0].metadata, dict)
        assert "source_format" in stix_indicators[0].metadata

    def test_all_indicators_have_required_fields(self) -> None:
        """Test that all indicators have required fields populated."""
        misp_payload = {
            "Event": {
                "id": "1",
                "Attribute": [
                    {"type": "domain", "value": "test.com", "confidence": 80}
                ],
            }
        }
        indicators = parse_misp_feed(misp_payload)

        for indicator in indicators:
            assert indicator.indicator_type in ["domain", "ip", "url", "email"]
            assert isinstance(indicator.value, str)
            assert len(indicator.value) > 0
            assert isinstance(indicator.threat_types, list)
            assert len(indicator.threat_types) > 0
            assert isinstance(indicator.confidence, int)
            assert 0 <= indicator.confidence <= 100
            assert isinstance(indicator.first_seen, datetime)
            assert isinstance(indicator.last_seen, datetime)
            assert indicator.ttl > 0
            assert isinstance(indicator.metadata, dict)
