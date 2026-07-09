"""Tests for HTTP auth helpers."""
from auth.http_auth import extract_bearer_token


def test_extracts_token():
    """Test successful token extraction."""
    assert extract_bearer_token({"Authorization": "Bearer abc.def"}) == "abc.def"


def test_missing_header_returns_none():
    """Test missing Authorization header."""
    assert extract_bearer_token({}) is None


def test_wrong_scheme_returns_none():
    """Test non-Bearer scheme."""
    assert extract_bearer_token({"Authorization": "Basic xxx"}) is None


def test_bearer_with_no_token_returns_none():
    """Test Bearer with no token."""
    assert extract_bearer_token({"Authorization": "Bearer "}) is None
