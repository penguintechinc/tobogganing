"""Coverage tests for SWG category feed source parsers (pure functions, no I/O)."""

from __future__ import annotations

from hub_api.modules.sase.security.swg.sources import (
    CATEGORY_SOURCES,
    CategorySource,
    _parse_blocklistproject,
    _parse_cipher_oos,
    _parse_hagenzi_oisd,
    _parse_steven_black,
    _parse_urlhaus_phishing,
    _parse_ut1_cc,
)


class TestCategorySourcesRegistry:
    """Covers the CATEGORY_SOURCES registry itself."""

    def test_registry_has_six_sources_with_callable_parsers(self) -> None:
        """Every registered source has a name, url, license, and callable parser."""
        assert len(CATEGORY_SOURCES) == 6
        for source in CATEGORY_SOURCES:
            assert isinstance(source, CategorySource)
            assert source.name
            assert source.url.startswith("https://")
            assert source.license
            assert callable(source.parse)


class TestParseUt1Cc:
    """Covers _parse_ut1_cc's line/comment/malformed-entry handling."""

    def test_parses_valid_entries_skips_comments_and_blanks(self) -> None:
        content = "# comment\n\nbad.com;gambling\nno-semicolon-here\nsingle;\n"
        result = list(_parse_ut1_cc(content))
        assert result == [("bad.com", "gambling")]


class TestParseBlocklistProject:
    """Covers _parse_blocklistproject's whitespace-delimited format."""

    def test_parses_valid_entries_skips_comments_and_blanks(self) -> None:
        content = "# comment\n\nbad.com malware\nsingleword\n"
        result = list(_parse_blocklistproject(content))
        assert result == [("bad.com", "malware")]


class TestParseHagenziOisd:
    """Covers _parse_hagenzi_oisd's pipe-delimited and fallback-to-malware paths."""

    def test_pipe_delimited_entry(self) -> None:
        content = "bad.com|gambling"
        result = list(_parse_hagenzi_oisd(content))
        assert result == [("bad.com", "gambling")]

    def test_fallback_defaults_to_malware(self) -> None:
        content = "# comment\n\nplain-domain.com"
        result = list(_parse_hagenzi_oisd(content))
        assert result == [("plain-domain.com", "malware")]


class TestParseStevenBlack:
    """Covers _parse_steven_black's hosts-format parsing."""

    def test_hosts_format_maps_to_adware(self) -> None:
        content = "# comment\n\n0.0.0.0 bad.com\n127.0.0.1 also-bad.com\nsingle-token\n"
        result = list(_parse_steven_black(content))
        assert result == [("bad.com", "adware"), ("also-bad.com", "adware")]


class TestParseUrlhausPhishing:
    """Covers _parse_urlhaus_phishing's comma-delimited and fallback paths."""

    def test_phishing_threat_type(self) -> None:
        content = "bad.com,phishing-kit"
        result = list(_parse_urlhaus_phishing(content))
        assert result == [("bad.com", "phishing")]

    def test_non_phishing_threat_type_defaults_to_malware(self) -> None:
        content = "bad.com,trojan"
        result = list(_parse_urlhaus_phishing(content))
        assert result == [("bad.com", "malware")]

    def test_no_comma_fallback_defaults_to_malware(self) -> None:
        content = "# comment\n\nplain-domain.com"
        result = list(_parse_urlhaus_phishing(content))
        assert result == [("plain-domain.com", "malware")]


class TestParseCipherOos:
    """Covers _parse_cipher_oos's single-column suspicious mapping."""

    def test_maps_every_domain_to_suspicious(self) -> None:
        content = "# comment\n\nbad.com\nother.com\n"
        result = list(_parse_cipher_oos(content))
        assert result == [("bad.com", "suspicious"), ("other.com", "suspicious")]
