"""File encryption and decryption for backups."""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)

# Scrypt KDF parameters per OWASP recommendation
# n=2**17 (131072): CPU cost factor; r=8, p=1 are standard
# Memory usage ~128MB per derivation; acceptable for backup tool
# These must match between encrypt and decrypt operations
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1


def _derive_key(password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
    """
    Derive a Fernet key from a password using scrypt KDF.

    Args:
        password: Encryption password
        salt: Optional salt (generated if not provided)

    Returns:
        Tuple of (key, salt) where key is Fernet-compatible

    Raises:
        ImportError: If cryptography library is not available
    """
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography library required for encryption")

    if salt is None:
        salt = os.urandom(16)

    # Scrypt-based key derivation with OWASP-aligned parameters
    # n=2**17: CPU cost; higher is slower but stronger against brute-force
    # r=8, p=1: Memory and parallelization factors (standard values)
    kdf = Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    derived = kdf.derive(password.encode())

    # Fernet requires base64-encoded 32 bytes
    key = base64.urlsafe_b64encode(derived)
    return key, salt


def encrypt_file(file_path: Path, key: str) -> Path:
    """
    Encrypt a file using Fernet (AES-128 CBC with HMAC).

    Stores salt as first 16 bytes; file format: [16-byte salt][Fernet token].
    Renames file to .enc suffix and returns new path.

    Args:
        file_path: Path to file to encrypt
        key: Encryption password

    Returns:
        Path to encrypted file (.enc)
    """
    if not CRYPTO_AVAILABLE:
        logger.warning("cryptography not available; encryption skipped")
        return file_path

    try:
        # Derive key and generate salt
        fernet_key, salt = _derive_key(key)
        cipher = Fernet(fernet_key)

        # Read plaintext
        with open(file_path, "rb") as f:
            plaintext = f.read()

        # Encrypt
        encrypted_token = cipher.encrypt(plaintext)

        # Write salt + encrypted token to .enc file
        enc_path = file_path.parent / f"{file_path.name}.enc"
        with open(enc_path, "wb") as f:
            f.write(salt + encrypted_token)

        # Remove plaintext
        file_path.unlink()

        logger.info(f"File encrypted: {file_path} -> {enc_path}")
        return enc_path

    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise


def decrypt_file(file_path: Path, key: str) -> Path:
    """
    Decrypt a Fernet-encrypted file.

    Expects file format: [16-byte salt][Fernet token].
    Removes .enc suffix and returns decrypted path.

    Args:
        file_path: Path to encrypted file (.enc)
        key: Decryption password

    Returns:
        Path to decrypted file (without .enc)
    """
    if not CRYPTO_AVAILABLE:
        logger.warning("cryptography not available; assuming unencrypted")
        return file_path

    try:
        # Read encrypted file
        with open(file_path, "rb") as f:
            data = f.read()

        # Extract salt (first 16 bytes) and encrypted token (remainder)
        if len(data) < 16:
            raise ValueError("Invalid encrypted file format (too short)")

        salt = data[:16]
        encrypted_token = data[16:]

        # Derive key using extracted salt
        fernet_key, _ = _derive_key(key, salt)
        cipher = Fernet(fernet_key)

        # Decrypt
        plaintext = cipher.decrypt(encrypted_token)

        # Write to file without .enc suffix
        dec_path = Path(str(file_path).replace(".enc", ""))
        with open(dec_path, "wb") as f:
            f.write(plaintext)

        # Remove encrypted file
        file_path.unlink()

        logger.info(f"File decrypted: {file_path} -> {dec_path}")
        return dec_path

    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise
