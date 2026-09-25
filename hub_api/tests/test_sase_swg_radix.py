"""Tests for SASE SWG RadixTree domain lookup."""
from __future__ import annotations

import json

from hub_api.modules.sase.security.swg.radix import RadixTree


def test_exact_domain_and_subdomain_cover() -> None:
    """Test exact match and subdomain coverage."""
    t = RadixTree()
    t.insert("badsite.com", ("gambling",))

    # Exact match
    assert t.lookup("badsite.com") == ("gambling",)

    # Subdomain covered
    assert t.lookup("a.b.badsite.com") == ("gambling",)

    # Not covered
    assert t.lookup("good.com") is None


def test_more_specific_wins() -> None:
    """Test that most-specific node is returned."""
    t = RadixTree()
    t.insert("shop.com", ("shopping",))
    t.insert("evil.shop.com", ("malware",))

    # Most specific node should be returned
    result = t.lookup("evil.shop.com")
    assert result == ("malware",)


def test_multiple_categories_per_domain() -> None:
    """Test domain with multiple categories."""
    t = RadixTree()
    t.insert("multi.com", ("news", "shopping", "gambling"))

    result = t.lookup("multi.com")
    assert set(result) == {"news", "shopping", "gambling"}


def test_serialize_roundtrip() -> None:
    """Test serialization and deserialization."""
    t = RadixTree()
    t.insert("x.com", ("news",))
    t.insert("y.org", ("phishing",))
    t.insert("sub.y.org", ("malware",))

    serialized = t.serialize()
    assert isinstance(serialized, bytes)

    t2 = RadixTree.deserialize(serialized)

    # Verify deserialized tree works correctly
    assert t2.lookup("x.com") == ("news",)
    assert t2.lookup("a.x.com") == ("news",)
    assert t2.lookup("y.org") == ("phishing",)
    assert t2.lookup("sub.y.org") == ("malware",)
    assert t2.lookup("a.sub.y.org") == ("malware",)
    assert t2.lookup("unknown.net") is None


def test_empty_tree() -> None:
    """Test empty tree returns None."""
    t = RadixTree()
    assert t.lookup("anything.com") is None


def test_single_label_domain() -> None:
    """Test handling of single-label domains."""
    t = RadixTree()
    t.insert("localhost", ("local",))

    result = t.lookup("localhost")
    assert result == ("local",)
