"""Unit tests for attestation validation."""
import pytest
from auth.attestation import AttestationValidator, AttestationResult, SIGNAL_WEIGHTS


@pytest.fixture
def validator():
    return AttestationValidator()


@pytest.fixture
def full_fingerprint():
    """A fingerprint with all signals present (except TPM and cloud)."""
    return {
        "product_uuid": "12345678-1234-1234-1234-123456789012",
        "board_serial": "SN-TEST-001",
        "sys_vendor": "TestVendor Inc",
        "product_name": "TestServer 3000",
        "cpu_model": "Intel Xeon E5-2680 v4",
        "cpu_count": 4,
        "mac_addresses": ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"],
        "disk_serials": ["WDTEST001", "WDTEST002"],
        "kernel_version": "6.1.0-generic",
        "os_release": "Ubuntu 24.04",
        "architecture": "amd64",
        "platform": "linux",
        "hostname": "test-host",
        "composite_hash": "ignored-recomputed-server-side",
        "collected_at": "2026-02-28T00:00:00Z",
    }


class TestConfidenceScoring:
    @pytest.mark.asyncio
    async def test_hw_only_fingerprint_score(self, validator, full_fingerprint):
        result = await validator.validate(full_fingerprint)
        # product_uuid(10) + board_serial(8) + mac(5) + disk(4) + vendor(3) + cpu(3) = 33
        assert result.confidence_score == 33
        assert result.confidence_level == "low"
        assert result.method == "fingerprint"

    @pytest.mark.asyncio
    async def test_tpm_adds_40_points(self, validator, full_fingerprint):
        full_fingerprint["tpm_quote"] = {
            "pcr_values": {0: "abc", 1: "def"},
            "quote_blob": "base64data",
            "signature_blob": "base64sig",
            "ek_public_hash": "ekhash",
        }
        result = await validator.validate(full_fingerprint)
        assert result.confidence_score == 33 + SIGNAL_WEIGHTS["tpm_quote"]
        assert result.confidence_level == "medium"
        assert result.method == "tpm"

    @pytest.mark.asyncio
    async def test_cloud_iid_adds_35_points(self, validator, full_fingerprint):
        full_fingerprint["cloud_identity"] = {
            "provider": "aws",
            "instance_id": "i-1234567890",
            "region": "us-east-1",
            "account_id": "123456789012",
            "signed_document": "pkcs7-signature-data",
        }
        result = await validator.validate(full_fingerprint)
        assert result.confidence_score == 33 + SIGNAL_WEIGHTS["cloud_iid"]
        assert result.confidence_level == "medium"
        assert "cloud_iid" in result.signals_present

    @pytest.mark.asyncio
    async def test_empty_fingerprint_minimal(self, validator):
        result = await validator.validate({})
        assert result.confidence_score == 0
        assert result.confidence_level == "minimal"
        assert result.method == "minimal"

    @pytest.mark.asyncio
    async def test_high_confidence_with_tpm_and_hw(self, validator, full_fingerprint):
        full_fingerprint["tpm_quote"] = {
            "pcr_values": {0: "a"},
            "quote_blob": "b",
            "signature_blob": "c",
        }
        full_fingerprint["cloud_identity"] = {
            "provider": "aws",
            "signed_document": "doc",
        }
        result = await validator.validate(full_fingerprint)
        # tpm(40) + cloud(35) + uuid(10) + serial(8) + mac(5) + disk(4) + vendor(3) + cpu(3) = 108
        assert result.confidence_score >= 90
        assert result.confidence_level == "high"


class TestCompositeHash:
    @pytest.mark.asyncio
    async def test_server_recomputes_hash(self, validator, full_fingerprint):
        """Server should not trust client-provided hash."""
        result = await validator.validate(full_fingerprint)
        assert result.composite_hash != "ignored-recomputed-server-side"
        assert len(result.composite_hash) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_hash_deterministic(self, validator, full_fingerprint):
        r1 = await validator.validate(full_fingerprint)
        r2 = await validator.validate(full_fingerprint)
        assert r1.composite_hash == r2.composite_hash

    @pytest.mark.asyncio
    async def test_volatile_fields_excluded_from_hash(self, validator, full_fingerprint):
        fp1 = full_fingerprint.copy()
        fp2 = full_fingerprint.copy()
        fp2["kernel_version"] = "different-kernel"
        fp2["hostname"] = "different-host"

        r1 = await validator.validate(fp1)
        r2 = await validator.validate(fp2)
        assert r1.composite_hash == r2.composite_hash


class TestDriftDetection:
    @pytest.mark.asyncio
    async def test_no_drift_when_identical(self, validator, full_fingerprint):
        result = await validator.validate(full_fingerprint, stored=full_fingerprint)
        assert not result.drift_detected
        assert result.drift_score == 0.0

    @pytest.mark.asyncio
    async def test_product_uuid_drift_critical(self, validator, full_fingerprint):
        stored = full_fingerprint.copy()
        incoming = full_fingerprint.copy()
        incoming["product_uuid"] = "different-uuid"

        result = await validator.validate(incoming, stored=stored)
        assert result.drift_detected
        assert "product_uuid" in result.drift_fields
        assert result.drift_score >= 1.0  # product_uuid weight is 1.0

    @pytest.mark.asyncio
    async def test_mac_drift_minor(self, validator, full_fingerprint):
        stored = full_fingerprint.copy()
        incoming = full_fingerprint.copy()
        incoming["mac_addresses"] = ["ff:ff:ff:ff:ff:ff"]

        result = await validator.validate(incoming, stored=stored)
        assert result.drift_detected
        assert "mac_addresses" in result.drift_fields
        assert result.drift_score < 0.3  # MAC weight is 0.05

    @pytest.mark.asyncio
    async def test_multiple_field_drift(self, validator, full_fingerprint):
        stored = full_fingerprint.copy()
        incoming = full_fingerprint.copy()
        incoming["board_serial"] = "DIFFERENT-SERIAL"
        incoming["sys_vendor"] = "DifferentVendor"

        result = await validator.validate(incoming, stored=stored)
        assert result.drift_detected
        assert len(result.drift_fields) == 2
        assert result.drift_score > 0.3
