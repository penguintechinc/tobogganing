"""Pluggable JWT/at-rest key providers. In-app default now; KMS in Phase 4b."""
from __future__ import annotations
import os
from typing import Protocol, runtime_checkable
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


@runtime_checkable
class KeyProvider(Protocol):
    private_pem: bytes
    public_pem: bytes


class InAppKeyProvider:
    """RSA keypair loaded from a PEM or generated in-process."""

    def __init__(self, private_pem: bytes | None = None) -> None:
        if private_pem:
            key = serialization.load_pem_private_key(
                private_pem, password=None, backend=default_backend()
            )
        else:
            key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048, backend=default_backend()
            )
        self.private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


def build_key_provider() -> KeyProvider:
    """Env-driven: JWT_PRIVATE_KEY_PEM inline, or JWT_PRIVATE_KEY_PATH file, else generate."""
    pem = os.getenv("JWT_PRIVATE_KEY_PEM")
    if pem:
        return InAppKeyProvider(pem.encode())
    path = os.getenv("JWT_PRIVATE_KEY_PATH")
    if path and os.path.exists(path):
        with open(path, "rb") as fh:
            return InAppKeyProvider(fh.read())
    provider = InAppKeyProvider()
    if path:
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as fh:
            fh.write(provider.private_pem)
    return provider
