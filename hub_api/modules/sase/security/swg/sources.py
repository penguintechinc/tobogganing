"""Category feed sources for SWG domain categorization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

__all__ = ["CategorySource", "CATEGORY_SOURCES"]


@dataclass(slots=True)
class CategorySource:
    """A feed source for domain categories.

    Provides the URL, license, and parser for a specific category database.
    """

    name: str
    url: str
    license: str
    parse: callable


def _parse_ut1_cc(content: str) -> Iterable[tuple[str, str]]:
    """Parse UT1 Unified Blocklist categories."""
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) >= 2:
            domain = parts[0].strip()
            category = parts[1].strip()
            if domain and category:
                yield (domain, category)


def _parse_blocklistproject(content: str) -> Iterable[tuple[str, str]]:
    """Parse Blocklist Project format (one domain per line with category)."""
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: domain category
        parts = line.split()
        if len(parts) >= 2:
            domain = parts[0].strip()
            category = parts[1].strip()
            if domain and category:
                yield (domain, category)


def _parse_hagenzi_oisd(content: str) -> Iterable[tuple[str, str]]:
    """Parse HaGeZi OISD combined domain list with categories."""
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Assume format: domain|category
        if "|" in line:
            domain, category = line.split("|", 1)
            domain = domain.strip()
            category = category.strip()
            if domain and category:
                yield (domain, category)
        else:
            # Fallback: treat as "malware" category
            if line:
                yield (line, "malware")


def _parse_steven_black(content: str) -> Iterable[tuple[str, str]]:
    """Parse StevenBlack blocklist (hosts format -> adware category)."""
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # hosts format: 0.0.0.0 domain OR 127.0.0.1 domain
        parts = line.split()
        if len(parts) >= 2:
            domain = parts[1].strip()
            if domain:
                yield (domain, "adware")


def _parse_urlhaus_phishing(content: str) -> Iterable[tuple[str, str]]:
    """Parse URLhaus/PhishTank combined threat list."""
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Assume format: domain,threat_type
        if "," in line:
            domain, threat_type = line.split(",", 1)
            domain = domain.strip()
            threat_type = threat_type.strip().lower()
            if domain:
                category = "phishing" if "phishing" in threat_type else "malware"
                yield (domain, category)
        else:
            # Default to malware
            if line:
                yield (line, "malware")


def _parse_cipher_oos(content: str) -> Iterable[tuple[str, str]]:
    """Parse Cipher OOS blocklist (one domain per line -> suspicious category)."""
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line:
            yield (line, "suspicious")


# Category feed source registry
CATEGORY_SOURCES: list[CategorySource] = [
    CategorySource(
        name="ut1_cc",
        url="https://raw.githubusercontent.com/ut1cc/blocklist/main/domains.txt",
        license="CC0",
        parse=_parse_ut1_cc,
    ),
    CategorySource(
        name="blocklistproject",
        url="https://raw.githubusercontent.com/blocklistproject/Lists/master/malware.txt",
        license="MIT",
        parse=_parse_blocklistproject,
    ),
    CategorySource(
        name="hagenzi_oisd",
        url="https://raw.githubusercontent.com/HaGeZi/dns-blocklists/main/domains/ultimate.txt",
        license="CC0",
        parse=_parse_hagenzi_oisd,
    ),
    CategorySource(
        name="steven_black",
        url="https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        license="MIT",
        parse=_parse_steven_black,
    ),
    CategorySource(
        name="urlhaus_phishing",
        url="https://raw.githubusercontent.com/abuse.ch/urlhaus-dataset/master/urlhaus_feed.txt",
        license="CC0",
        parse=_parse_urlhaus_phishing,
    ),
    CategorySource(
        name="cipher_oos",
        url="https://raw.githubusercontent.com/Cipher387/Blocklist_Blocklists/master/domains_only.txt",
        license="CC0",
        parse=_parse_cipher_oos,
    ),
]
