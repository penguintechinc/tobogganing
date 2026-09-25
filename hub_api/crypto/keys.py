"""RS256 key provider protocol and implementations."""

from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any, Protocol

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class KeyProvider(Protocol):
    """Protocol for RS256 signing-key providers (operation-based; no private-key export)."""

    async def sign(self, data: bytes) -> bytes:
        """Sign data with RSASSA-PKCS1-v1_5 / SHA-256 and return the raw signature."""
        ...

    @property
    def public_pem(self) -> str:
        """Return the public key in PEM (SubjectPublicKeyInfo) format."""
        ...

    @property
    def kid(self) -> str:
        """Return the Key ID (sha256(public_pem)[:16])."""
        ...


class InAppKeyProvider:
    """In-application RS256 key provider using a persistent PEM-encoded key pair."""

    def __init__(self, private_key_pem: str, public_key_pem: str) -> None:
        """Initialize with PEM-encoded keys and parse private key for signing."""
        self._private_key_pem = private_key_pem
        self._public_key_pem = public_key_pem
        # Parse private key once during init for fast signing
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )

    async def sign(self, data: bytes) -> bytes:
        """Sign locally with the in-app RSA private key (fast; no thread hop needed)."""
        return self._private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())

    @property
    def public_pem(self) -> str:
        """Return the public key in PEM format."""
        return self._public_key_pem

    @property
    def kid(self) -> str:
        """Return the Key ID derived from public key hash."""
        return hashlib.sha256(self._public_key_pem.encode()).hexdigest()[:16]

    @classmethod
    def _build_from_env(cls) -> InAppKeyProvider:
        """Build InAppKeyProvider from environment configuration.

        Checks JWT_PRIVATE_KEY_PEM env var first; if not found,
        attempts to read from JWT_PRIVATE_KEY_PATH file.
        Falls back to generating a new key pair for development.

        Returns:
            InAppKeyProvider instance.

        Raises:
            ValueError: If private key cannot be loaded or generated.
        """
        private_pem_env = os.getenv("JWT_PRIVATE_KEY_PEM")
        if private_pem_env:
            # Extract public key from private key
            private_key = serialization.load_pem_private_key(
                private_pem_env.encode(),
                password=None,
            )
            public_key = private_key.public_key()
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
            return cls(private_pem_env, public_pem)

        private_key_path = os.getenv("JWT_PRIVATE_KEY_PATH")
        if private_key_path:
            try:
                with open(private_key_path, "r") as f:
                    private_pem = f.read()
                private_key = serialization.load_pem_private_key(
                    private_pem.encode(),
                    password=None,
                )
                public_key = private_key.public_key()
                public_pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("utf-8")
                return cls(private_pem, public_pem)
            except (IOError, ValueError) as e:
                raise ValueError(f"Failed to load private key from {private_key_path}: {e}")

        # Development fallback: generate new key pair
        private_pem, public_pem = generate_rsa_key_pair()
        return cls(private_pem, public_pem)


class AwsKmsKeyProvider:
    """AWS KMS-backed key provider using GetPublicKey + DIGEST signing."""

    def __init__(self, key_arn: str, client: Any | None = None) -> None:
        """Initialize with AWS KMS key ARN and optional client.

        Args:
            key_arn: AWS KMS key ARN (e.g., 'arn:aws:kms:us-east-1:123456789012:key/12345678')
            client: Optional boto3 KMS client; if None, lazily imported and created.
        """
        self._key_arn = key_arn
        self._client = client
        self._public_pem: str | None = None
        self._kid: str | None = None

    def _get_client(self) -> Any:
        """Lazily import and create boto3 KMS client if not provided."""
        if self._client is None:
            import boto3
            self._client = boto3.client("kms")
        return self._client

    async def sign(self, data: bytes) -> bytes:
        """Sign data using AWS KMS DIGEST signing operation.

        Args:
            data: The data to sign (usually JWS signing input in bytes).

        Returns:
            The raw signature bytes (RSASSA_PKCS1_V1_5_SHA_256).
        """
        client = self._get_client()
        # Compute SHA256 digest of data
        digest = hashlib.sha256(data).digest()

        # Call AWS KMS sign operation in thread pool
        response = await asyncio.to_thread(
            client.sign,
            KeyId=self._key_arn,
            Message=digest,
            MessageType="DIGEST",
            SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256"
        )

        return response["Signature"]

    @property
    def public_pem(self) -> str:
        """Return the public key in PEM (SubjectPublicKeyInfo) format.

        Cached after first access via GetPublicKey operation.
        """
        if self._public_pem is None:
            client = self._get_client()
            # Get public key from AWS KMS
            response = client.get_public_key(KeyId=self._key_arn)
            # response["PublicKey"] is DER-encoded; convert to PEM
            der_key = response["PublicKey"]
            public_key = serialization.load_der_public_key(der_key)
            self._public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode("utf-8")
        return self._public_pem

    @property
    def kid(self) -> str:
        """Return the Key ID derived from SHA256 hash of public key.

        Follows the same rule as InAppKeyProvider: sha256(public_pem)[:16].
        """
        if self._kid is None:
            self._kid = hashlib.sha256(self.public_pem.encode()).hexdigest()[:16]
        return self._kid


class GcpKmsKeyProvider:
    """Google Cloud KMS-backed key provider using GetPublicKey + AsymmetricSign."""

    def __init__(self, key_name: str, client: Any | None = None) -> None:
        """Initialize with GCP KMS key name and optional client.

        Args:
            key_name: Full CryptoKeyVersion resource name (e.g.,
                'projects/p/locations/us/keyRings/r/cryptoKeys/k/versions/1')
            client: Optional google.cloud.kms.KeyManagementServiceClient;
                if None, lazily imported and created.
        """
        self._key_name = key_name
        self._client = client
        self._public_pem: str | None = None
        self._kid: str | None = None

    def _get_client(self) -> Any:
        """Lazily import and create GCP KMS client if not provided."""
        if self._client is None:
            from google.cloud import kms
            self._client = kms.KeyManagementServiceClient()
        return self._client

    async def sign(self, data: bytes) -> bytes:
        """Sign data using GCP KMS AsymmetricSign operation.

        Args:
            data: The data to sign (usually JWS signing input in bytes).

        Returns:
            The raw signature bytes (using the KMS key's signing algorithm).
        """
        client = self._get_client()
        # Compute SHA256 digest of data
        digest = hashlib.sha256(data).digest()

        # Call GCP KMS sign operation in thread pool
        response = await asyncio.to_thread(
            client.asymmetric_sign,
            request={
                "name": self._key_name,
                "digest": {"sha256": digest},
            }
        )

        return response.signature

    @property
    def public_pem(self) -> str:
        """Return the public key in PEM (SubjectPublicKeyInfo) format.

        Cached after first access via GetPublicKey operation.
        """
        if self._public_pem is None:
            client = self._get_client()
            # Get public key from GCP KMS
            response = client.get_public_key(request={"name": self._key_name})
            # response.pem is already in PEM format
            self._public_pem = response.pem
        return self._public_pem

    @property
    def kid(self) -> str:
        """Return the Key ID derived from SHA256 hash of public key.

        Follows the same rule as InAppKeyProvider: sha256(public_pem)[:16].
        """
        if self._kid is None:
            self._kid = hashlib.sha256(self.public_pem.encode()).hexdigest()[:16]
        return self._kid


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
    """Build and return a KeyProvider based on environment configuration.

    Builds an in-app provider from JWT_PRIVATE_KEY_PEM, JWT_PRIVATE_KEY_PATH,
    or a newly generated key pair. For full selection logic including external
    KMS providers, use build_signing_provider from hub_api.crypto.selection instead.

    Returns:
        KeyProvider: Configured key provider instance.

    Raises:
        ValueError: If private key cannot be loaded or generated.
    """
    return InAppKeyProvider._build_from_env()
