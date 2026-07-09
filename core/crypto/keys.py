"""RS256 key provider protocol and implementations."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class KeyProvider(Protocol):
    """Protocol for RS256 key providers."""

    @property
    def private_pem(self) -> str:
        """Return the private key in PEM format."""
        ...

    @property
    def public_pem(self) -> str:
        """Return the public key in PEM format."""
        ...

    @property
    def kid(self) -> str:
        """Return the Key ID (sha256(public_pem)[:16])."""
        ...


@dataclass(slots=True)
class InAppKeyProvider:
    """In-application RS256 key provider using a persistent PEM-encoded key pair."""

    _private_key_pem: str
    _public_key_pem: str

    def __init__(self, private_key_pem: str, public_key_pem: str) -> None:
        """Initialize with PEM-encoded keys."""
        self._private_key_pem = private_key_pem
        self._public_key_pem = public_key_pem

    @property
    def private_pem(self) -> str:
        """Return the private key in PEM format."""
        return self._private_key_pem

    @property
    def public_pem(self) -> str:
        """Return the public key in PEM format."""
        return self._public_key_pem

    @property
    def kid(self) -> str:
        """Return the Key ID derived from public key hash."""
        return hashlib.sha256(self._public_key_pem.encode()).hexdigest()[:16]


class AwsKmsKeyProvider:
    """AWS KMS-backed key provider stub (Phase 4b)."""

    @property
    def private_pem(self) -> str:
        """Raise NotImplementedError as placeholder for Phase 4b."""
        raise NotImplementedError("wired in Phase 4b")

    @property
    def public_pem(self) -> str:
        """Raise NotImplementedError as placeholder for Phase 4b."""
        raise NotImplementedError("wired in Phase 4b")

    @property
    def kid(self) -> str:
        """Raise NotImplementedError as placeholder for Phase 4b."""
        raise NotImplementedError("wired in Phase 4b")


class GcpKmsKeyProvider:
    """Google Cloud KMS-backed key provider stub (Phase 4b)."""

    @property
    def private_pem(self) -> str:
        """Raise NotImplementedError as placeholder for Phase 4b."""
        raise NotImplementedError("wired in Phase 4b")

    @property
    def public_pem(self) -> str:
        """Raise NotImplementedError as placeholder for Phase 4b."""
        raise NotImplementedError("wired in Phase 4b")

    @property
    def kid(self) -> str:
        """Raise NotImplementedError as placeholder for Phase 4b."""
        raise NotImplementedError("wired in Phase 4b")


def generate_rsa_key_pair() -> tuple[str, str]:
    """Generate a new RSA 2048-bit key pair and return as (private_pem, public_pem)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


def build_key_provider() -> KeyProvider:
    """
    Build and return a KeyProvider based on environment configuration.

    Checks for JWT_PRIVATE_KEY_PEM env var first; if not found,
    attempts to read from JWT_PRIVATE_KEY_PATH file.
    Falls back to generating a new key pair for development.

    Returns:
        KeyProvider: Configured key provider instance.

    Raises:
        ValueError: If private key cannot be loaded or generated.
    """
    private_pem_env = os.getenv("JWT_PRIVATE_KEY_PEM")
    if private_pem_env:
        # Extract public key from private key
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        private_key = serialization.load_pem_private_key(
            private_pem_env.encode(),
            password=None,
            backend=default_backend(),
        )
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return InAppKeyProvider(private_pem_env, public_pem)

    private_key_path = os.getenv("JWT_PRIVATE_KEY_PATH")
    if private_key_path:
        try:
            with open(private_key_path, "r") as f:
                private_pem = f.read()
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend

            private_key = serialization.load_pem_private_key(
                private_pem.encode(),
                password=None,
                backend=default_backend(),
            )
            public_key = private_key.public_key()
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
            return InAppKeyProvider(private_pem, public_pem)
        except (IOError, ValueError) as e:
            raise ValueError(f"Failed to load private key from {private_key_path}: {e}")

    # Development fallback: generate new key pair
    private_pem, public_pem = generate_rsa_key_pair()
    return InAppKeyProvider(private_pem, public_pem)
