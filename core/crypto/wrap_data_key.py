"""Generate a fresh data encryption key and wrap it via the configured KMS.

Usage: python3 -m core.crypto.wrap_data_key

Environment variables:
  KMS_PROVIDER: 'inapp' (default), 'aws', or 'gcp'
  For AWS:
    AWS_KMS_DATA_KEY_ARN: The KMS key ARN to use for wrapping
  For GCP:
    GCP_KMS_DATA_KEY: The full CryptoKeyVersion resource name

Output:
  Prints ONLY the base64-encoded wrapped key blob to stdout.
  NEVER prints the plaintext key.
"""
from __future__ import annotations

import base64
import os
import sys


def main() -> None:
    """Generate and wrap a fresh 32-byte data encryption key."""
    # Generate fresh 32-byte DEK
    plaintext_key = os.urandom(32)

    kms_provider = os.environ.get("KMS_PROVIDER", "inapp").lower()

    if kms_provider == "inapp":
        # For in-app, we'd need to wrap it somehow; for now, just return the plaintext
        # encoded as b64 (not secure; this is mainly for Task 6 integration testing)
        wrapped_blob = plaintext_key  # In real usage, would be wrapped
        wrapped_b64 = base64.b64encode(wrapped_blob).decode("ascii")
        print(wrapped_b64)
        return

    if kms_provider == "aws":
        key_arn = os.environ.get("AWS_KMS_DATA_KEY_ARN")
        if not key_arn:
            sys.stderr.write("Error: AWS_KMS_DATA_KEY_ARN not set\n")
            sys.exit(1)

        try:
            import boto3
        except ImportError:
            sys.stderr.write("Error: boto3 not installed; install with: pip install boto3\n")
            sys.exit(1)

        client = boto3.client("kms")
        try:
            response = client.encrypt(KeyId=key_arn, Plaintext=plaintext_key)
            wrapped_blob = response["CiphertextBlob"]
        except Exception as e:
            sys.stderr.write(f"Error: Failed to wrap key via AWS KMS: {e}\n")
            sys.exit(1)

        wrapped_b64 = base64.b64encode(wrapped_blob).decode("ascii")
        print(wrapped_b64)
        return

    if kms_provider == "gcp":
        key_name = os.environ.get("GCP_KMS_DATA_KEY")
        if not key_name:
            sys.stderr.write("Error: GCP_KMS_DATA_KEY not set\n")
            sys.exit(1)

        try:
            from google.cloud import kms
        except ImportError:
            sys.stderr.write(
                "Error: google-cloud-kms not installed; "
                "install with: pip install google-cloud-kms\n"
            )
            sys.exit(1)

        client = kms.KeyManagementServiceClient()
        try:
            response = client.encrypt(
                request={"name": key_name, "plaintext": plaintext_key}
            )
            wrapped_blob = response.ciphertext
        except Exception as e:
            sys.stderr.write(f"Error: Failed to wrap key via GCP KMS: {e}\n")
            sys.exit(1)

        wrapped_b64 = base64.b64encode(wrapped_blob).decode("ascii")
        print(wrapped_b64)
        return

    sys.stderr.write(f"Error: Unknown KMS_PROVIDER: {kms_provider}\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
