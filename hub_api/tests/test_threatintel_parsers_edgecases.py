"""Edge-case tests for feeds/parsers.py branch coverage.

Complements tests/test_threatintel_parsers.py (happy-path MISP/OpenIOC/CSV/
STIX parsing) with malformed-record skip branches, validation helper
boundaries, and the STIX object/IP/range extraction helpers that the
happy-path suite doesn't reach.
"""

from __future__ import annotations

import pytest

from hub_api.modules.threatintel.feeds.parsers import (
    _extract_from_stix_pattern,
    _extract_ips_from_openioc_value,
    _is_valid_domain,
    _is_valid_indicator,
    _is_valid_ip,
    _misp_type_to_indicator_type,
    _parse_misp_date,
    parse_misp_feed,
    parse_openioc_feed,
    parse_stix_bundle,
    parse_threat_csv,
)
from hub_api.modules.threatintel.feeds.sources import FeedSource

# --- parse_misp_feed edge cases ---------------------------------------------


def test_parse_misp_feed_malformed_event_skipped() -> None:
    """An event that isn't a dict (AttributeError on .get) is skipped, not fatal."""
    payload = {"response": ["not-a-dict-event", {"id": "2", "info": "ok", "Attribute": []}]}

    indicators = parse_misp_feed(payload)

    assert indicators == []


def test_parse_misp_feed_malformed_attribute_skipped() -> None:
    """An attribute whose confidence can't int()-convert is skipped, not fatal."""
    payload = {
        "Event": {
            "id": "1",
            "info": "test event",
            "Attribute": [
                {"type": "domain", "value": "bad.example.com", "confidence": "not-a-number"},
                {"type": "domain", "value": "good.example.com", "confidence": "80"},
            ],
        }
    }

    indicators = parse_misp_feed(payload)

    assert len(indicators) == 1
    assert indicators[0].value == "good.example.com"


def test_parse_misp_feed_non_iterable_payload_caught() -> None:
    """A payload that can't be iterated as events is caught by the outer except."""
    indicators = parse_misp_feed(payload=12345)  # type: ignore[arg-type]

    assert indicators == []


def test_misp_type_to_indicator_type_unknown_returns_none() -> None:
    """_misp_type_to_indicator_type() returns None for unmapped MISP types."""
    assert _misp_type_to_indicator_type("registry-key") is None


def test_parse_misp_date_invalid_returns_none() -> None:
    """_parse_misp_date() returns None for an unparseable date string."""
    assert _parse_misp_date("not-a-date") is None


def test_parse_misp_date_none_returns_none() -> None:
    """_parse_misp_date() returns None when given no date string."""
    assert _parse_misp_date(None) is None


def test_parse_misp_date_valid_iso() -> None:
    """_parse_misp_date() parses a valid ISO8601 date with a Z suffix."""
    parsed = _parse_misp_date("2024-01-15T10:30:00Z")
    assert parsed is not None
    assert parsed.year == 2024


# --- parse_openioc_feed edge cases ------------------------------------------


def test_parse_openioc_feed_empty_content_element_skipped() -> None:
    """An IndicatorItem with an empty <Content> is skipped (not appended)."""
    xml = """<?xml version="1.0"?>
<ioc id="ioc-1">
  <short_description>test</short_description>
  <definition>
    <Indicator operator="OR">
      <IndicatorItem>
        <Context document="Network" search="DnsEntryItem/Hostname" type="DnsEntryItem"/>
        <Content type="string"></Content>
      </IndicatorItem>
    </Indicator>
  </definition>
</ioc>
"""
    indicators = parse_openioc_feed(xml)
    assert indicators == []


def test_parse_openioc_feed_invalid_ip_in_network_item_skipped() -> None:
    """An IP-type IndicatorItem whose value doesn't resolve to a valid IP is skipped."""
    xml = """<?xml version="1.0"?>
<ioc id="ioc-2">
  <definition>
    <Indicator operator="OR">
      <IndicatorItem>
        <Context document="Network" search="NetworkItem/IP" type="NetworkItem"/>
        <Content type="string">not-an-ip-address</Content>
      </IndicatorItem>
    </Indicator>
  </definition>
</ioc>
"""
    indicators = parse_openioc_feed(xml)
    assert indicators == []


def test_parse_openioc_feed_url_item_extracts_domain() -> None:
    """A URL-type IndicatorItem extracts and validates the netloc as a domain."""
    xml = """<?xml version="1.0"?>
<ioc id="ioc-3">
  <definition>
    <Indicator operator="OR">
      <IndicatorItem>
        <Context document="Network" search="Network/URI" type="Network/URI"/>
        <Content type="string">http://evil.example.com/payload.exe</Content>
      </IndicatorItem>
    </Indicator>
  </definition>
</ioc>
"""
    indicators = parse_openioc_feed(xml)
    assert len(indicators) == 1
    assert indicators[0].value == "evil.example.com"
    assert indicators[0].indicator_type == "domain"


def test_parse_openioc_feed_url_item_invalid_domain_skipped() -> None:
    """A URL-type IndicatorItem whose netloc isn't a valid domain is skipped."""
    xml = """<?xml version="1.0"?>
<ioc id="ioc-4">
  <definition>
    <Indicator operator="OR">
      <IndicatorItem>
        <Context document="Network" search="Network/URI" type="Network/URI"/>
        <Content type="string">not a url at all</Content>
      </IndicatorItem>
    </Indicator>
  </definition>
</ioc>
"""
    indicators = parse_openioc_feed(xml)
    assert indicators == []


def test_parse_openioc_feed_invalid_xml_returns_empty() -> None:
    """Malformed XML is caught by ET.ParseError and returns an empty list."""
    indicators = parse_openioc_feed("<not valid xml")
    assert indicators == []


def test_parse_openioc_feed_unexpected_error_caught() -> None:
    """A non-string xml_text triggers the generic exception handler, not a crash."""
    indicators = parse_openioc_feed(xml_text=None)  # type: ignore[arg-type]
    assert indicators == []


def test_parse_openioc_feed_cidr_network_item() -> None:
    """A NetworkItem with a small public CIDR value expands to individual host IPs."""
    xml = """<?xml version="1.0"?>
<ioc id="ioc-5">
  <definition>
    <Indicator operator="OR">
      <IndicatorItem>
        <Context document="Network" search="NetworkItem/IP" type="NetworkItem"/>
        <Content type="string">1.1.1.0/30</Content>
      </IndicatorItem>
    </Indicator>
  </definition>
</ioc>
"""
    indicators = parse_openioc_feed(xml)
    assert len(indicators) >= 1
    assert all(ind.indicator_type == "ip" for ind in indicators)


# --- parse_threat_csv edge cases --------------------------------------------


def test_parse_threat_csv_domain_bad_confidence_defaults_to_50() -> None:
    """A domain row with a non-numeric confidence value falls back to 50."""
    csv_text = "domain,confidence\nweird.example.com,not-a-number\n"

    indicators = parse_threat_csv(csv_text)

    assert len(indicators) == 1
    assert indicators[0].confidence == 50


def test_parse_threat_csv_ip_fallback_after_invalid_first_column() -> None:
    """An invalid value in the first IP-candidate column falls through to a later one."""
    csv_text = "ip,address\nnot-an-ip,8.8.4.4\n"

    indicators = parse_threat_csv(csv_text)

    assert len(indicators) == 1
    assert indicators[0].value == "8.8.4.4"
    assert indicators[0].indicator_type == "ip"


def test_parse_threat_csv_ip_bad_confidence_defaults_to_50() -> None:
    """An IP row with a non-numeric confidence value falls back to 50."""
    csv_text = "ip,confidence\n8.8.8.8,garbage\n"

    indicators = parse_threat_csv(csv_text)

    assert len(indicators) == 1
    assert indicators[0].confidence == 50


def test_parse_threat_csv_none_text_caught_by_outer_except() -> None:
    """Passing non-string text is caught by the outer exception handler."""
    indicators = parse_threat_csv(text=None)  # type: ignore[arg-type]
    assert indicators == []


def test_parse_threat_csv_row_with_no_domain_or_ip_skipped() -> None:
    """A row with neither a recognizable domain nor IP column yields no indicator."""
    csv_text = "unrelated_column\nsomevalue\n"

    indicators = parse_threat_csv(csv_text)

    assert indicators == []


# --- parse_stix_bundle edge cases -------------------------------------------


def test_parse_stix_bundle_bare_list_payload() -> None:
    """A bundle payload that's a bare list (not wrapped in 'objects') is accepted."""
    payload = [
        {
            "type": "indicator",
            "id": "indicator--1",
            "pattern": "[domain-name:value = 'listpayload.example.com']",
            "labels": ["malicious-activity"],
        }
    ]

    indicators = parse_stix_bundle(payload)

    assert len(indicators) == 1
    assert indicators[0].value == "listpayload.example.com"


def test_parse_stix_bundle_unrecognized_shape_returns_empty() -> None:
    """A payload that's neither a dict-with-objects nor a list returns empty."""
    indicators = parse_stix_bundle({"unexpected": "shape"})
    assert indicators == []


def test_parse_stix_bundle_object_with_to_dict_method() -> None:
    """A STIX-library-style object exposing to_dict() is converted and parsed."""

    class FakeStixObject:
        def to_dict(self) -> dict:
            return {
                "type": "indicator",
                "id": "indicator--fake-1",
                "pattern": "[domain-name:value = 'fakeobj.example.com']",
                "labels": [],
            }

    indicators = parse_stix_bundle({"objects": [FakeStixObject()]})

    assert len(indicators) == 1
    assert indicators[0].value == "fakeobj.example.com"


def test_parse_stix_bundle_non_indicator_type_skipped() -> None:
    """A STIX object whose type isn't 'indicator' is skipped."""
    indicators = parse_stix_bundle({"objects": [{"type": "malware", "id": "malware--1"}]})
    assert indicators == []


def test_parse_stix_bundle_missing_pattern_skipped() -> None:
    """An indicator object without a pattern is skipped."""
    indicators = parse_stix_bundle({"objects": [{"type": "indicator", "id": "indicator--2"}]})
    assert indicators == []


def test_parse_stix_bundle_non_string_confidence_defaults_medium() -> None:
    """A numeric (non-string) confidence value falls back to the 'medium' mapping."""
    payload = {
        "objects": [
            {
                "type": "indicator",
                "id": "indicator--3",
                "pattern": "[domain-name:value = 'numericconf.example.com']",
                "confidence": 99,
            }
        ]
    }

    indicators = parse_stix_bundle(payload)

    assert len(indicators) == 1
    assert indicators[0].confidence == 70  # "medium" mapping


def test_parse_stix_bundle_object_without_get_caught_per_object() -> None:
    """An object that's neither dict nor to_dict-able is caught by the per-object except."""
    indicators = parse_stix_bundle({"objects": ["just-a-string", {"type": "malware"}]})
    assert indicators == []


def test_parse_stix_bundle_non_iterable_objects_caught_by_outer_except() -> None:
    """objects being non-iterable (e.g. an int) is caught by the outer except."""
    indicators = parse_stix_bundle({"objects": 12345})
    assert indicators == []


# --- _extract_from_stix_pattern edge cases ----------------------------------


def test_extract_from_stix_pattern_ipv6() -> None:
    """_extract_from_stix_pattern() extracts a valid public IPv6 address."""
    pattern = "[ipv6-addr:value = '2606:4700:4700::1111']"
    results = _extract_from_stix_pattern(pattern)
    assert ("2606:4700:4700::1111", "ip") in results


def test_extract_from_stix_pattern_none_caught() -> None:
    """_extract_from_stix_pattern() fails open (empty list) on a non-string pattern."""
    results = _extract_from_stix_pattern(None)  # type: ignore[arg-type]
    assert results == []


# --- _extract_ips_from_openioc_value edge cases -----------------------------


def test_extract_ips_small_cidr_expands_hosts() -> None:
    """A small CIDR block expands to individual host addresses."""
    ips = _extract_ips_from_openioc_value("198.51.100.0/30")
    assert len(ips) == 2  # /30 has 2 usable hosts


def test_extract_ips_large_cidr_returns_network_address_only() -> None:
    """A large CIDR block returns only the network address, not every host."""
    ips = _extract_ips_from_openioc_value("10.0.0.0/8")
    assert ips == ["10.0.0.0"]


def test_extract_ips_invalid_cidr_returns_empty() -> None:
    """An invalid CIDR value is caught and returns an empty list."""
    ips = _extract_ips_from_openioc_value("not-a-cidr/24")
    assert ips == []


def test_extract_ips_small_range_expands() -> None:
    """A small IP range (start-end) expands to every address in between."""
    ips = _extract_ips_from_openioc_value("192.0.2.1-192.0.2.3")
    assert ips == ["192.0.2.1", "192.0.2.2", "192.0.2.3"]


def test_extract_ips_large_range_returns_endpoints_only() -> None:
    """A large IP range returns only the start/end addresses."""
    ips = _extract_ips_from_openioc_value("10.0.0.1-10.1.0.1")
    assert ips == ["10.0.0.1", "10.1.0.1"]


def test_extract_ips_invalid_range_returns_empty() -> None:
    """An unparseable IP range is caught and returns an empty list."""
    ips = _extract_ips_from_openioc_value("192.168.1.oops-192.168.1.5")
    assert ips == []


def test_extract_ips_single_valid_ip() -> None:
    """A bare single valid public IP (no CIDR, no range) is returned as-is."""
    ips = _extract_ips_from_openioc_value("8.8.8.8")
    assert ips == ["8.8.8.8"]


def test_extract_ips_single_invalid_returns_empty() -> None:
    """A bare single invalid value returns an empty list."""
    ips = _extract_ips_from_openioc_value("not-an-ip")
    assert ips == []


def test_extract_ips_none_value_caught_by_outer_except() -> None:
    """A None value is caught by the outer exception handler, not a crash."""
    ips = _extract_ips_from_openioc_value(None)  # type: ignore[arg-type]
    assert ips == []


# --- _is_valid_indicator / _is_valid_domain / _is_valid_ip ------------------


def test_is_valid_indicator_url_type() -> None:
    """_is_valid_indicator() validates 'url' type by length only."""
    assert _is_valid_indicator("http://example.com/x", "url") is True
    assert _is_valid_indicator("ab", "url") is False


def test_is_valid_indicator_unknown_type_returns_false() -> None:
    """_is_valid_indicator() returns False for a completely unknown type."""
    assert _is_valid_indicator("something", "registry-key") is False


def test_is_valid_domain_too_short() -> None:
    """_is_valid_domain() rejects domains shorter than 4 characters."""
    assert _is_valid_domain("a.b") is False


def test_is_valid_domain_too_long() -> None:
    """_is_valid_domain() rejects domains longer than 255 characters."""
    assert _is_valid_domain("a" * 256) is False


def test_is_valid_domain_invalid_characters() -> None:
    """_is_valid_domain() rejects domains with characters outside [a-zA-Z0-9.-]."""
    assert _is_valid_domain("exa_mple.com") is False


def test_is_valid_domain_label_too_long() -> None:
    """_is_valid_domain() rejects a domain whose label exceeds 63 characters."""
    long_label = "a" * 64
    assert _is_valid_domain(f"{long_label}.com") is False


def test_is_valid_domain_label_starts_or_ends_with_hyphen() -> None:
    """_is_valid_domain() rejects labels starting or ending with a hyphen."""
    assert _is_valid_domain("-bad.com") is False
    assert _is_valid_domain("bad-.com") is False


def test_is_valid_ip_rejects_unparseable() -> None:
    """_is_valid_ip() returns False for a string that isn't a valid IP at all."""
    assert _is_valid_ip("definitely-not-an-ip") is False


def test_is_valid_ip_rejects_private() -> None:
    """_is_valid_ip() rejects private-range addresses for threat intelligence."""
    assert _is_valid_ip("10.1.2.3") is False


def test_is_valid_ip_accepts_public() -> None:
    """_is_valid_ip() accepts a public, non-reserved IPv4 address."""
    assert _is_valid_ip("8.8.8.8") is True
