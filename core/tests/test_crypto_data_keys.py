"""Tests for DataKeyProvider and envelope encryption."""
from __future__ import annotations

import base64
import os
import sys
from unittest.mock import patch
from typing import Any

import pytest

from core.crypto.data_keys import (
    DataKeyProvider,
    InAppDataKeyProvider,
    AwsKmsDataKeyProvider,
    GcpKmsDataKeyProvider,
)
from core.crypto.secrets import SecretEncryptor


def generate_test_data_key() -> bytes:
    """Generate a fresh 32-byte data key for testing."""
    return os.urandom(32)


class TestInAppDataKeyProvider:
    """Tests for InAppDataKeyProvider."""

    def test_env_key_round_trip(self) -> None:
        """Test (a): in-app provider round-trips env key (regression: fernet env-key construction).

        Previously, when DATA_ENCRYPTION_KEY was set from env as b64(32 bytes),
        SecretEncryptor would fail because it passed raw 32 bytes to Fernet
        instead of base64-encoding them first. This test verifies the fix.
        """
        test_key = generate_test_data_key()
        key_b64 = base64.b64encode(test_key).decode("ascii")

        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": key_b64}, clear=True):
            provider = InAppDataKeyProvider()
            retrieved_key = provider.get_data_key()

            # Should successfully construct SecretEncryptor and encrypt/decrypt
            encryptor = SecretEncryptor(retrieved_key)
            plaintext = "test-secret-data"
            ciphertext = encryptor.encrypt(plaintext)
            decrypted = encryptor.decrypt(ciphertext)

            assert decrypted == plaintext

    def test_ephemeral_key_generation(self) -> None:
        """Test that ephemeral key is generated when env is not set."""
        with patch.dict(os.environ, {}, clear=True):
            provider = InAppDataKeyProvider()
            key = provider.get_data_key()

            # Should be 32 bytes
            assert isinstance(key, bytes)
            assert len(key) == 32

    def test_returns_32_bytes(self) -> None:
        """Test that get_data_key always returns exactly 32 bytes."""
        test_key = generate_test_data_key()
        key_b64 = base64.b64encode(test_key).decode("ascii")

        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": key_b64}, clear=True):
            provider = InAppDataKeyProvider()
            key = provider.get_data_key()
            assert isinstance(key, bytes)
            assert len(key) == 32


class TestDataKeyProviderInterchangeability:
    """Tests for provider interchangeability."""

    def test_two_encryptors_same_key(self) -> None:
        """Test (b): two encryptors from same key can decrypt each other's ciphertext."""
        test_key = generate_test_data_key()

        encryptor1 = SecretEncryptor(test_key)
        encryptor2 = SecretEncryptor(test_key)

        plaintext = "secret-message"
        ciphertext1 = encryptor1.encrypt(plaintext)
        decrypted_by_2 = encryptor2.decrypt(ciphertext1)

        assert decrypted_by_2 == plaintext

        # And vice versa
        ciphertext2 = encryptor2.encrypt(plaintext)
        decrypted_by_1 = encryptor1.decrypt(ciphertext2)

        assert decrypted_by_1 == plaintext


class FakeAwsKmsClient:
    """Fake AWS KMS client for testing (signs with real local RSA key)."""

    def __init__(self) -> None:
        """Initialize with a real RSA key pair for signing."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        # Generate a test RSA key for signing verification
        from cryptography.hazmat.primitives.asymmetric import rsa

        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        self._pub_der = self._private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # For wrap/unwrap, we use Fernet internally
        self._fernet_key = base64.b64encode(os.urandom(32))
        from cryptography.fernet import Fernet

        self._fernet = Fernet(self._fernet_key)
        self.decrypt_calls: list[dict] = []
        self.get_public_key_calls: int = 0

    def get_public_key(self, KeyId: str) -> dict:
        """Simulate AWS KMS GetPublicKey."""
        self.get_public_key_calls += 1
        return {
            "PublicKey": self._pub_der,
            "SigningAlgorithms": ["RSASSA_PKCS1_V1_5_SHA_256"],
        }

    def decrypt(self, KeyId: str, CiphertextBlob: bytes) -> dict:
        """Simulate AWS KMS Decrypt."""
        self.decrypt_calls.append({"KeyId": KeyId, "CiphertextBlob": CiphertextBlob})
        # Decrypt using Fernet
        plaintext = self._fernet.decrypt(CiphertextBlob)
        return {"Plaintext": plaintext}

    def encrypt(self, KeyId: str, Plaintext: bytes) -> dict:
        """Simulate AWS KMS Encrypt (for wrap_data_key testing)."""
        ciphertext = self._fernet.encrypt(Plaintext)
        return {"CiphertextBlob": ciphertext}


class FakeGcpKmsClient:
    """Fake GCP KMS client for testing."""

    def __init__(self) -> None:
        """Initialize with encryption capability."""
        import types

        self._fernet_key = base64.b64encode(os.urandom(32))
        from cryptography.fernet import Fernet

        self._fernet = Fernet(self._fernet_key)
        self.decrypt_calls: list[dict] = []
        self.get_public_key_calls: int = 0

        # Generate a test RSA key for public key retrieval
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        self._pub_pem = (
            self._private_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )

        self.types = types

    def get_public_key(self, request: dict) -> Any:
        """Simulate GCP KMS GetPublicKey."""
        self.get_public_key_calls += 1
        response = self.types.SimpleNamespace()
        response.pem = self._pub_pem
        return response

    def decrypt(self, request: dict) -> Any:
        """Simulate GCP KMS Decrypt."""
        self.decrypt_calls.append(request)
        plaintext = self._fernet.decrypt(request["ciphertext"])
        response = self.types.SimpleNamespace()
        response.plaintext = plaintext
        return response

    def encrypt(self, request: dict) -> Any:
        """Simulate GCP KMS Encrypt."""
        ciphertext = self._fernet.encrypt(request["plaintext"])
        response = self.types.SimpleNamespace()
        response.ciphertext = ciphertext
        return response


class TestAwsKmsDataKeyProvider:
    """Tests for AwsKmsDataKeyProvider."""

    def test_unwrap_via_kms(self) -> None:
        """Test (c): AWS provider returns unwrapped 32 bytes via fake client."""
        fake_client = FakeAwsKmsClient()
        test_key = os.urandom(32)

        # "Wrap" the key using the fake client
        wrapped_response = fake_client.encrypt(
            KeyId="arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012",
            Plaintext=test_key,
        )
        wrapped_b64 = base64.b64encode(wrapped_response["CiphertextBlob"]).decode("ascii")

        provider = AwsKmsDataKeyProvider(
            key_arn="arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012",
            wrapped_key_b64=wrapped_b64,
            client=fake_client,
        )

        retrieved_key = provider.get_data_key()

        assert retrieved_key == test_key
        assert len(retrieved_key) == 32

    def test_decrypt_called_once_and_cached(self) -> None:
        """Test that Decrypt is called exactly once (cached)."""
        fake_client = FakeAwsKmsClient()
        test_key = os.urandom(32)
        wrapped_response = fake_client.encrypt(
            KeyId="arn:aws:kms:us-east-1:123456789012:key/test",
            Plaintext=test_key,
        )
        wrapped_b64 = base64.b64encode(wrapped_response["CiphertextBlob"]).decode("ascii")

        provider = AwsKmsDataKeyProvider(
            key_arn="arn:aws:kms:us-east-1:123456789012:key/test",
            wrapped_key_b64=wrapped_b64,
            client=fake_client,
        )

        # First call
        key1 = provider.get_data_key()
        assert len(fake_client.decrypt_calls) == 1

        # Second call (should use cached value)
        key2 = provider.get_data_key()
        assert len(fake_client.decrypt_calls) == 1
        assert key1 == key2


class TestGcpKmsDataKeyProvider:
    """Tests for GcpKmsDataKeyProvider."""

    def test_unwrap_via_kms(self) -> None:
        """Test (c): GCP provider returns unwrapped 32 bytes via fake client."""
        fake_client = FakeGcpKmsClient()
        test_key = os.urandom(32)

        # "Wrap" the key using the fake client
        wrapped_response = fake_client.encrypt(
            {"name": "projects/p/locations/global/keyRings/kr/cryptoKeys/ck/versions/1", "plaintext": test_key}
        )
        wrapped_b64 = base64.b64encode(wrapped_response.ciphertext).decode("ascii")

        provider = GcpKmsDataKeyProvider(
            key_name="projects/p/locations/global/keyRings/kr/cryptoKeys/ck/versions/1",
            wrapped_key_b64=wrapped_b64,
            client=fake_client,
        )

        retrieved_key = provider.get_data_key()

        assert retrieved_key == test_key
        assert len(retrieved_key) == 32

    def test_decrypt_called_once_and_cached(self) -> None:
        """Test that Decrypt is called exactly once (cached)."""
        fake_client = FakeGcpKmsClient()
        test_key = os.urandom(32)
        wrapped_response = fake_client.encrypt(
            {
                "name": "projects/p/locations/global/keyRings/kr/cryptoKeys/ck/versions/1",
                "plaintext": test_key,
            }
        )
        wrapped_b64 = base64.b64encode(wrapped_response.ciphertext).decode("ascii")

        provider = GcpKmsDataKeyProvider(
            key_name="projects/p/locations/global/keyRings/kr/cryptoKeys/ck/versions/1",
            wrapped_key_b64=wrapped_b64,
            client=fake_client,
        )

        # First call
        key1 = provider.get_data_key()
        assert len(fake_client.decrypt_calls) == 1

        # Second call (should use cached value)
        key2 = provider.get_data_key()
        assert len(fake_client.decrypt_calls) == 1
        assert key1 == key2


class TestTamperedCiphertext:
    """Tests for error handling."""

    def test_tampered_ciphertext_raises_valueerror(self) -> None:
        """Test (d): tampered ciphertext raises ValueError."""
        test_key = os.urandom(32)
        encryptor = SecretEncryptor(test_key)

        ciphertext = encryptor.encrypt("test-secret")
        # Tamper with the ciphertext
        tampered = ciphertext[:-5] + "xxxxx"

        with pytest.raises(ValueError, match="Invalid or tampered"):
            encryptor.decrypt(tampered)


class TestWrapDataKey:
    """Tests for wrap_data_key script."""

    def test_wrap_data_key_output_can_be_unwrapped(self) -> None:
        """Test (e): wrap_data_key output can be unwrapped by provider."""
        import subprocess
        import tempfile

        fake_client = FakeAwsKmsClient()

        # Simulate running wrap_data_key by directly calling the main function
        # with monkeypatched boto3.client
        from unittest.mock import patch

        def fake_boto3_client(*args, **kwargs):
            return fake_client

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "KMS_PROVIDER": "aws",
                    "AWS_KMS_DATA_KEY_ARN": "arn:aws:kms:us-east-1:123456789012:key/test",
                },
                clear=True,
            ):
                with patch("boto3.client", side_effect=fake_boto3_client):
                    # Import and call main after patching
                    from core.crypto.wrap_data_key import main
                    from io import StringIO

                    old_stdout = sys.stdout
                    sys.stdout = StringIO()

                    try:
                        main()
                        output = sys.stdout.getvalue().strip()
                    finally:
                        sys.stdout = old_stdout

        # The output should be a base64-encoded wrapped key
        assert output, "wrap_data_key should output wrapped key blob"

        # Create a provider with this wrapped key and verify it can unwrap
        provider = AwsKmsDataKeyProvider(
            key_arn="arn:aws:kms:us-east-1:123456789012:key/test",
            wrapped_key_b64=output,
            client=fake_client,
        )

        unwrapped_key = provider.get_data_key()
        assert isinstance(unwrapped_key, bytes)
        assert len(unwrapped_key) == 32
