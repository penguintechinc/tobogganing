"""Additional coverage for hub_api.crypto.wrap_data_key main() branches.

test_crypto_data_keys.py already covers the AWS happy path; this file fills
in inapp, gcp, unknown-provider, missing-env-var, and ImportError branches.
"""

from __future__ import annotations

import base64
import builtins
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from hub_api.crypto.wrap_data_key import main

# NOTE: this environment has a pre-existing protobuf/proto-plus version
# mismatch (protobuf==7.35.1 from requirements-kms.txt) that breaks a real
# `import google.cloud.kms` with `AttributeError: module 'proto' has no
# attribute 'module'`. That is an existing dependency-pinning issue, not
# something to work around by relaxing pins here — so these tests inject a
# fake module via sys.modules instead of importing the real google-cloud-kms
# SDK, exactly as main()'s lazy `from google.cloud import kms` would see it.


def _run_main_capture_stdout() -> str:
    """Run main() and capture stdout, returning the printed value."""
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        main()
        return sys.stdout.getvalue().strip()
    finally:
        sys.stdout = old_stdout


class TestInAppProvider:
    """Tests for KMS_PROVIDER=inapp (default)."""

    def test_default_provider_prints_base64_key(self) -> None:
        """Default (unset KMS_PROVIDER) prints a base64-encoded 32-byte key."""
        with patch.dict(os.environ, {}, clear=True):
            output = _run_main_capture_stdout()

        decoded = base64.b64decode(output)
        assert len(decoded) == 32

    def test_explicit_inapp_provider(self) -> None:
        """Explicit KMS_PROVIDER=inapp behaves the same as default."""
        with patch.dict(os.environ, {"KMS_PROVIDER": "inapp"}, clear=True):
            output = _run_main_capture_stdout()

        decoded = base64.b64decode(output)
        assert len(decoded) == 32


class TestAwsProviderErrors:
    """Tests for KMS_PROVIDER=aws error branches."""

    def test_missing_key_arn_exits_1(self) -> None:
        """Missing AWS_KMS_DATA_KEY_ARN causes SystemExit(1)."""
        with patch.dict(os.environ, {"KMS_PROVIDER": "aws"}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    def test_boto3_import_error_exits_1(self) -> None:
        """Missing boto3 causes SystemExit(1)."""
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "boto3":
                raise ImportError("no boto3")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch.dict(
            os.environ,
            {"KMS_PROVIDER": "aws", "AWS_KMS_DATA_KEY_ARN": "arn:aws:kms:us-east-1:1:key/x"},
            clear=True,
        ):
            with patch("builtins.__import__", side_effect=fake_import):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 1

    def test_kms_encrypt_failure_exits_1(self) -> None:
        """KMS encrypt() raising causes SystemExit(1)."""
        fake_client = MagicMock()
        fake_client.encrypt.side_effect = RuntimeError("kms down")

        with patch.dict(
            os.environ,
            {"KMS_PROVIDER": "aws", "AWS_KMS_DATA_KEY_ARN": "arn:aws:kms:us-east-1:1:key/x"},
            clear=True,
        ):
            with patch("boto3.client", return_value=fake_client):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 1


class TestGcpProvider:
    """Tests for KMS_PROVIDER=gcp branches."""

    def test_missing_key_name_exits_1(self) -> None:
        """Missing GCP_KMS_DATA_KEY causes SystemExit(1)."""
        with patch.dict(os.environ, {"KMS_PROVIDER": "gcp"}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    def test_gcp_kms_import_error_exits_1(self) -> None:
        """Missing google-cloud-kms causes SystemExit(1)."""
        with patch.dict(
            os.environ,
            {
                "KMS_PROVIDER": "gcp",
                "GCP_KMS_DATA_KEY": "projects/p/locations/l/keyRings/r/cryptoKeys/k/versions/1",
            },
            clear=True,
        ):
            # sys.modules[name] = None forces `from google.cloud import kms`
            # to raise ImportError, per Python import system semantics.
            with patch.dict(sys.modules, {"google.cloud.kms": None}):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 1

    def test_gcp_success_prints_wrapped_key(self) -> None:
        """Successful GCP wrap prints a base64-encoded ciphertext blob."""
        fake_response = MagicMock()
        fake_response.ciphertext = b"wrapped-bytes-blob"
        fake_client = MagicMock()
        fake_client.encrypt.return_value = fake_response
        fake_kms_module = MagicMock()
        fake_kms_module.KeyManagementServiceClient.return_value = fake_client

        with patch.dict(
            os.environ,
            {
                "KMS_PROVIDER": "gcp",
                "GCP_KMS_DATA_KEY": "projects/p/locations/l/keyRings/r/cryptoKeys/k/versions/1",
            },
            clear=True,
        ):
            with patch.dict(sys.modules, {"google.cloud.kms": fake_kms_module}):
                output = _run_main_capture_stdout()

        assert base64.b64decode(output) == b"wrapped-bytes-blob"

    def test_gcp_kms_encrypt_failure_exits_1(self) -> None:
        """GCP KMS encrypt() raising causes SystemExit(1)."""
        fake_client = MagicMock()
        fake_client.encrypt.side_effect = RuntimeError("kms down")
        fake_kms_module = MagicMock()
        fake_kms_module.KeyManagementServiceClient.return_value = fake_client

        with patch.dict(
            os.environ,
            {
                "KMS_PROVIDER": "gcp",
                "GCP_KMS_DATA_KEY": "projects/p/locations/l/keyRings/r/cryptoKeys/k/versions/1",
            },
            clear=True,
        ):
            with patch.dict(sys.modules, {"google.cloud.kms": fake_kms_module}):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 1


class TestUnknownProvider:
    """Tests for unrecognized KMS_PROVIDER values."""

    def test_unknown_provider_exits_1(self) -> None:
        """Unknown KMS_PROVIDER causes SystemExit(1)."""
        with patch.dict(os.environ, {"KMS_PROVIDER": "azure"}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1
