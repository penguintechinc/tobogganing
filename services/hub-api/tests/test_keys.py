import os
from auth.keys import InAppKeyProvider, build_key_provider

def test_inapp_provider_generates_valid_pem_pair():
    p = InAppKeyProvider()
    assert p.private_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    assert p.public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

def test_provider_loads_persistent_key_from_env(monkeypatch):
    seed = InAppKeyProvider()
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", seed.private_pem.decode())
    p = build_key_provider()
    assert p.private_pem == seed.private_pem
    assert p.public_pem == seed.public_pem

def test_two_providers_from_same_env_pem_match(monkeypatch):
    seed = InAppKeyProvider()
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", seed.private_pem.decode())
    a, b = build_key_provider(), build_key_provider()
    assert a.public_pem == b.public_pem  # cross-worker stability
