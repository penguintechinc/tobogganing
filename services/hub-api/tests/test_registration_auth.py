"""Tests for registration endpoint authentication."""
from auth.http_auth import verify_bootstrap_token


def test_bootstrap_rejects_wrong_token(monkeypatch):
    """Test that wrong token is rejected."""
    monkeypatch.setenv("ENROLLMENT_BOOTSTRAP_TOKEN", "secret-xyz")
    assert verify_bootstrap_token("nope") is False


def test_bootstrap_accepts_correct_token(monkeypatch):
    """Test that correct token is accepted."""
    monkeypatch.setenv("ENROLLMENT_BOOTSTRAP_TOKEN", "secret-xyz")
    assert verify_bootstrap_token("secret-xyz") is True


def test_bootstrap_unset_denies(monkeypatch):
    """Test that unset bootstrap token always denies."""
    monkeypatch.delenv("ENROLLMENT_BOOTSTRAP_TOKEN", raising=False)
    assert verify_bootstrap_token("anything") is False
