"""
Attestation validation for Tobogganing hub-api.

Validates system fingerprints from native clients, computes confidence
scores based on available attestation signals, and detects hardware drift
between registrations.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()

# Signal weights for confidence scoring
SIGNAL_WEIGHTS = {
    "tpm_quote": 40,
    "cloud_iid": 35,
    "product_uuid": 10,
    "board_serial": 8,
    "fleetdm": 7,
    "mac_addresses": 5,
    "disk_serials": 4,
    "sys_vendor_product": 3,
    "cpu_info": 3,
}

MAX_POSSIBLE_SCORE = sum(SIGNAL_WEIGHTS.values())  # 115

# Drift field weights (how much each field change contributes to drift score)
DRIFT_WEIGHTS = {
    "product_uuid": 1.0,  # Critical — immediate reject
    "board_serial": 0.25,
    "sys_vendor": 0.15,
    "product_name": 0.15,
    "cpu_model": 0.10,
    "mac_addresses": 0.05,
    "disk_serials": 0.05,
}


@dataclass(slots=True)
class AttestationResult:
    """Result of attestation validation."""

    confidence_score: int  # 0-115 raw weighted score
    confidence_percent: int  # 0-100 normalised
    confidence_level: str  # high / medium / low / minimal
    method: str  # tpm / cloud_iid / fingerprint / minimal
    composite_hash: str
    signals_present: list[str] = field(default_factory=list)
    drift_detected: bool = False
    drift_score: float = 0.0  # 0.0-1.0
    drift_fields: list[str] = field(default_factory=list)
    fleetdm_verified: bool = False


class AttestationValidator:
    """Validates attestation data from native infrastructure clients."""

    def __init__(self, fleetdm_client=None):
        self.fleetdm_client = fleetdm_client

    async def validate(
        self,
        data: dict,
        stored: dict | None = None,
    ) -> AttestationResult:
        """
        Validate attestation data and compute confidence score.

        Args:
            data: Incoming attestation fingerprint from the client.
            stored: Previously stored fingerprint (for drift detection).

        Returns:
            AttestationResult with confidence and drift information.
        """
        # Server-side hash recomputation (never trust client-provided hash)
        composite_hash = self._recompute_composite_hash(data)

        # Compute confidence score
        score, method, signals = self._compute_confidence(data)

        # Normalise to percentage (capped at 100)
        percent = min(100, int(score * 100 / MAX_POSSIBLE_SCORE))

        # Confidence level thresholds
        if score >= 90:
            level = "high"
        elif score >= 60:
            level = "medium"
        elif score >= 30:
            level = "low"
        else:
            level = "minimal"

        result = AttestationResult(
            confidence_score=score,
            confidence_percent=percent,
            confidence_level=level,
            method=method,
            composite_hash=composite_hash,
            signals_present=signals,
        )

        # FleetDM cross-reference (if client + server configured)
        if self.fleetdm_client and data.get("fleetdm_host_uuid"):
            try:
                verified, matches = await self.fleetdm_client.verify_host_hardware(
                    data["fleetdm_host_uuid"], data
                )
                result.fleetdm_verified = verified
                if verified:
                    result.confidence_score += SIGNAL_WEIGHTS["fleetdm"]
                    result.signals_present.append("fleetdm")
                    result.confidence_percent = min(
                        100,
                        int(result.confidence_score * 100 / MAX_POSSIBLE_SCORE),
                    )
            except Exception:
                logger.warning("fleetdm_verification_failed", exc_info=True)

        # Drift detection (only if we have a stored fingerprint)
        if stored:
            drift_detected, drift_score, drift_fields = self._detect_drift(
                data, stored
            )
            result.drift_detected = drift_detected
            result.drift_score = drift_score
            result.drift_fields = drift_fields

        logger.info(
            "attestation_validated",
            score=result.confidence_score,
            level=result.confidence_level,
            method=result.method,
            signals=result.signals_present,
            drift=result.drift_detected,
        )

        return result

    def _compute_confidence(
        self, data: dict
    ) -> tuple[int, str, list[str]]:
        """Compute confidence score based on available signals."""
        score = 0
        signals: list[str] = []
        method = "minimal"

        # TPM quote
        if data.get("tpm_quote") and data["tpm_quote"].get("pcr_values"):
            score += SIGNAL_WEIGHTS["tpm_quote"]
            signals.append("tpm_quote")
            method = "tpm"

        # Cloud instance identity document
        if data.get("cloud_identity") and data["cloud_identity"].get("signed_document"):
            score += SIGNAL_WEIGHTS["cloud_iid"]
            signals.append("cloud_iid")
            if method != "tpm":
                method = "cloud_iid"

        # DMI product_uuid
        if data.get("product_uuid"):
            score += SIGNAL_WEIGHTS["product_uuid"]
            signals.append("product_uuid")

        # DMI board_serial
        if data.get("board_serial"):
            score += SIGNAL_WEIGHTS["board_serial"]
            signals.append("board_serial")

        # MAC addresses
        if data.get("mac_addresses") and len(data["mac_addresses"]) > 0:
            score += SIGNAL_WEIGHTS["mac_addresses"]
            signals.append("mac_addresses")

        # Disk serials
        if data.get("disk_serials") and len(data["disk_serials"]) > 0:
            score += SIGNAL_WEIGHTS["disk_serials"]
            signals.append("disk_serials")

        # Sys vendor + product name (both must be present)
        if data.get("sys_vendor") and data.get("product_name"):
            score += SIGNAL_WEIGHTS["sys_vendor_product"]
            signals.append("sys_vendor_product")

        # CPU model + count
        if data.get("cpu_model") and data.get("cpu_count", 0) > 0:
            score += SIGNAL_WEIGHTS["cpu_info"]
            signals.append("cpu_info")

        if method == "minimal" and score >= 30:
            method = "fingerprint"

        return score, method, signals

    def _recompute_composite_hash(self, data: dict) -> str:
        """Recompute the composite hash server-side from stable fields."""
        stable = {
            "product_uuid": data.get("product_uuid", ""),
            "board_serial": data.get("board_serial", ""),
            "sys_vendor": data.get("sys_vendor", ""),
            "product_name": data.get("product_name", ""),
            "cpu_model": data.get("cpu_model", ""),
            "cpu_count": data.get("cpu_count", 0),
            "mac_addresses": sorted(data.get("mac_addresses", [])),
            "disk_serials": sorted(data.get("disk_serials", [])),
        }

        # json.dumps with sort_keys matches Go's encoding/json (sorts map keys)
        canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _detect_drift(
        self, incoming: dict, stored: dict
    ) -> tuple[bool, float, list[str]]:
        """
        Compare incoming fingerprint against stored fingerprint.

        Returns (drift_detected, drift_score 0.0-1.0, changed_fields).
        """
        drift_score = 0.0
        changed_fields: list[str] = []

        for field_name, weight in DRIFT_WEIGHTS.items():
            incoming_val = incoming.get(field_name, "")
            stored_val = stored.get(field_name, "")

            # Normalise list fields for comparison
            if isinstance(incoming_val, list) and isinstance(stored_val, list):
                if sorted(incoming_val) != sorted(stored_val):
                    drift_score += weight
                    changed_fields.append(field_name)
            elif str(incoming_val) != str(stored_val):
                drift_score += weight
                changed_fields.append(field_name)

        drift_detected = drift_score > 0
        return drift_detected, round(drift_score, 3), changed_fields

    async def verify_cloud_iid(self, cloud_identity: dict) -> bool:
        """Verify a cloud instance identity document signature.

        Placeholder — real implementation would verify AWS PKCS7 / GCP JWT /
        Azure attested document against the provider's public certificate.
        """
        if not cloud_identity or not cloud_identity.get("signed_document"):
            return False

        provider = cloud_identity.get("provider", "")
        if provider not in ("aws", "gcp", "azure"):
            return False

        # TODO: implement per-provider cryptographic verification
        # For now, presence of a signed document is accepted
        logger.info("cloud_iid_verification", provider=provider, status="accepted")
        return True

    async def verify_tpm_quote(self, tpm_data: dict, nonce: bytes) -> bool:
        """Verify a TPM PCR quote against the server nonce.

        Placeholder — real implementation would verify the quote signature
        using the EK public key and confirm the nonce is embedded.
        """
        if not tpm_data or not tpm_data.get("quote_blob"):
            return False

        # TODO: implement TPM quote cryptographic verification
        logger.info("tpm_quote_verification", status="accepted")
        return True
