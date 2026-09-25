"""Additional coverage for hub_api.core.certificates: initialize(), persistence,
exception handlers, expiry check, and issuer-mismatch validation.

test_core_certs.py covers cert generation/validation happy+basic-error paths;
this file fills in CertificateManager.initialize()'s file-load/persist/exception
branches, _persist_ca()'s atomic-write success and cleanup-on-failure paths,
_is_certificate_expiring(), and the remaining exception handlers.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from hub_api.core.certificates import CertificateManager


@pytest.fixture
def cert_manager() -> CertificateManager:
    """Fresh CertificateManager instance."""
    return CertificateManager()


class TestInitialize:
    """Tests for CertificateManager.initialize()."""

    @pytest.mark.asyncio
    async def test_no_paths_configured_uses_inmemory_ca(
        self, cert_manager: CertificateManager
    ) -> None:
        """initialize() without CA_CERT_PATH/CA_KEY_PATH keeps the in-memory CA."""
        with patch.dict(os.environ, {}, clear=True):
            await cert_manager.initialize()

        assert cert_manager._initialized is True
        assert cert_manager.ca_cert is not None

    @pytest.mark.asyncio
    async def test_persists_ca_when_paths_configured_but_files_absent(
        self, cert_manager: CertificateManager, tmp_path: Path
    ) -> None:
        """initialize() persists the in-memory CA to disk when paths are set but empty."""
        cert_path = tmp_path / "ca.crt"
        key_path = tmp_path / "ca.key"

        with patch.dict(
            os.environ,
            {"CA_CERT_PATH": str(cert_path), "CA_KEY_PATH": str(key_path)},
            clear=True,
        ):
            await cert_manager.initialize()

        assert cert_path.exists()
        assert key_path.exists()
        assert cert_manager._initialized is True

    @pytest.mark.asyncio
    async def test_loads_existing_ca_from_files(
        self, cert_manager: CertificateManager, tmp_path: Path
    ) -> None:
        """initialize() loads an existing CA when both files are already present."""
        cert_path = tmp_path / "ca.crt"
        key_path = tmp_path / "ca.key"

        # Persist the freshly-generated CA first (simulates a prior run).
        cert_manager._persist_ca(str(cert_path), str(key_path))

        # New manager instance generates its own CA in __init__, but initialize()
        # should discard it in favor of loading the files.
        second_manager = CertificateManager()
        original_serial = second_manager.ca_cert.serial_number

        with patch.dict(
            os.environ,
            {"CA_CERT_PATH": str(cert_path), "CA_KEY_PATH": str(key_path)},
            clear=True,
        ):
            await second_manager.initialize()

        assert second_manager.ca_cert.serial_number == cert_manager.ca_cert.serial_number
        assert second_manager.ca_cert.serial_number != original_serial

    @pytest.mark.asyncio
    async def test_loading_invalid_ca_raises(
        self, cert_manager: CertificateManager, tmp_path: Path
    ) -> None:
        """initialize() raises when the loaded CA cert lacks BasicConstraints(ca=True)."""
        # Generate a leaf (non-CA) cert/key and persist those as if they were the CA.
        leaf_cert_dict = await cert_manager.generate_certificate("leaf", "client")

        cert_path = tmp_path / "ca.crt"
        key_path = tmp_path / "ca.key"
        cert_path.write_text(leaf_cert_dict["certificate"])
        key_path.write_text(leaf_cert_dict["private_key"])

        with patch.dict(
            os.environ,
            {"CA_CERT_PATH": str(cert_path), "CA_KEY_PATH": str(key_path)},
            clear=True,
        ):
            with pytest.raises(ValueError):
                await cert_manager.initialize()


class TestGenerateCertificateNoCa:
    """Tests for generate_certificate() when CA is missing."""

    @pytest.mark.asyncio
    async def test_raises_when_ca_not_initialized(self, cert_manager: CertificateManager) -> None:
        """generate_certificate() raises ValueError when ca_cert/ca_key are None."""
        cert_manager.ca_cert = None
        cert_manager.ca_key = None

        with pytest.raises(ValueError, match="CA not initialized"):
            await cert_manager.generate_certificate("node-1", "client")


class TestExceptionHandlers:
    """Tests forcing the various exception-wrapping branches."""

    @pytest.mark.asyncio
    async def test_generate_certificate_wraps_unexpected_error(
        self, cert_manager: CertificateManager
    ) -> None:
        """generate_certificate() re-raises unexpected signing errors."""
        with patch(
            "hub_api.core.certificates.x509.random_serial_number",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await cert_manager.generate_certificate("node-1", "client")

    @pytest.mark.asyncio
    async def test_generate_headend_certificate_wraps_unexpected_error(
        self, cert_manager: CertificateManager
    ) -> None:
        """generate_headend_certificate() re-raises unexpected errors."""
        with patch("hub_api.core.certificates.x509.DNSName", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                await cert_manager.generate_headend_certificate(
                    "cluster-1", "headend.local", ["headend.local"]
                )

    @pytest.mark.asyncio
    async def test_generate_client_certificate_wraps_unexpected_error(
        self, cert_manager: CertificateManager
    ) -> None:
        """generate_client_certificate() re-raises unexpected errors."""
        cert_manager.ca_key = None  # forces ValueError inside generate_certificate
        cert_manager.ca_cert = None

        with pytest.raises(ValueError):
            await cert_manager.generate_client_certificate("client-1", "name", "docker")


class TestValidateCertificateIssuerMismatch:
    """Tests for validate_certificate()'s issuer-mismatch branch."""

    @pytest.mark.asyncio
    async def test_issuer_mismatch_rejected(self, cert_manager: CertificateManager) -> None:
        """A certificate signed by a different CA is rejected (issuer mismatch)."""
        other_manager = CertificateManager()
        # Sign a cert with a DIFFERENT CA's key, then swap the resulting cert's
        # issuer verification against our original cert_manager (whose CA differs).
        foreign_cert_dict = await other_manager.generate_certificate("node-x", "client")

        result = await cert_manager.validate_certificate(foreign_cert_dict["certificate"])

        assert result["valid"] is False
        assert result["node_id"] is None


class TestIsCertificateExpiring:
    """Tests for _is_certificate_expiring()."""

    def test_naive_datetime_within_threshold(self, cert_manager: CertificateManager) -> None:
        """Returns True for a naive datetime within the threshold window."""
        expiry = datetime.utcnow() + timedelta(days=10)
        assert cert_manager._is_certificate_expiring(expiry, threshold_days=30) is True

    def test_naive_datetime_outside_threshold(self, cert_manager: CertificateManager) -> None:
        """Returns False for a naive datetime well beyond the threshold."""
        expiry = datetime.utcnow() + timedelta(days=100)
        assert cert_manager._is_certificate_expiring(expiry, threshold_days=30) is False

    def test_aware_datetime_within_threshold(self, cert_manager: CertificateManager) -> None:
        """Returns True for a timezone-aware datetime within the threshold window."""
        expiry = datetime.now(timezone.utc) + timedelta(days=5)
        assert cert_manager._is_certificate_expiring(expiry, threshold_days=30) is True


class TestPersistCa:
    """Tests for _persist_ca()'s atomic-write and failure-cleanup branches."""

    def test_raises_when_ca_not_initialized(self, tmp_path: Path) -> None:
        """_persist_ca() raises ValueError when ca_cert/ca_key are missing."""
        manager = CertificateManager()
        manager.ca_cert = None
        manager.ca_key = None

        with pytest.raises(ValueError, match="CA not initialized"):
            manager._persist_ca(str(tmp_path / "c.crt"), str(tmp_path / "k.key"))

    def test_creates_directories_and_secure_files(
        self, cert_manager: CertificateManager, tmp_path: Path
    ) -> None:
        """_persist_ca() creates parent dirs and writes 0600-permission files."""
        cert_path = tmp_path / "nested" / "ca.crt"
        key_path = tmp_path / "nested" / "ca.key"

        cert_manager._persist_ca(str(cert_path), str(key_path))

        assert cert_path.exists()
        assert key_path.exists()
        assert oct(cert_path.stat().st_mode)[-3:] == "600"
        assert oct(key_path.stat().st_mode)[-3:] == "600"

    def test_cleans_up_temp_file_on_cert_write_failure(
        self, cert_manager: CertificateManager, tmp_path: Path
    ) -> None:
        """_persist_ca() cleans up the temp cert file and re-raises on write failure."""
        cert_path = tmp_path / "ca.crt"
        key_path = tmp_path / "ca.key"

        with patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                cert_manager._persist_ca(str(cert_path), str(key_path))

        # No leftover temp files in the target directory.
        leftover = [f for f in tmp_path.iterdir() if f.name.startswith(".ca_")]
        assert leftover == []
