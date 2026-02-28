"""
FleetDM integration for attestation cross-reference.

When configured, queries the FleetDM API to verify that hardware details
reported by the native client match what FleetDM (via osquery) observes
on the same host.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()


class FleetDMClient:
    """HTTP client for the FleetDM REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("FLEETDM_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("FLEETDM_API_KEY", "")
        self.enabled = bool(self.base_url and self.api_key)

        if self.enabled:
            logger.info("fleetdm_client_enabled", base_url=self.base_url)
        else:
            logger.debug("fleetdm_client_disabled")

    async def get_host(self, host_uuid: str) -> dict | None:
        """Fetch host details from FleetDM by UUID."""
        if not self.enabled:
            return None

        url = f"{self.base_url}/api/v1/fleet/hosts/identifier/{host_uuid}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "fleetdm_host_lookup_failed",
                        status=resp.status_code,
                        host_uuid=host_uuid,
                    )
                    return None
                return resp.json().get("host")
        except Exception:
            logger.warning("fleetdm_request_failed", exc_info=True)
            return None

    async def verify_host_hardware(
        self,
        host_uuid: str,
        attestation: dict,
    ) -> tuple[bool, list[str]]:
        """
        Cross-reference attestation data with FleetDM host record.

        Checks:
        - hardware_serial ↔ board_serial
        - hardware_model ↔ product_name
        - primary_mac ↔ mac_addresses[0]

        Returns (all_matched, list_of_matched_fields).
        """
        host = await self.get_host(host_uuid)
        if not host:
            return False, []

        matches: list[str] = []

        # board_serial ↔ hardware_serial
        fleet_serial = (host.get("hardware_serial") or "").strip()
        client_serial = (attestation.get("board_serial") or "").strip()
        if fleet_serial and client_serial and fleet_serial == client_serial:
            matches.append("hardware_serial")

        # product_name ↔ hardware_model
        fleet_model = (host.get("hardware_model") or "").strip()
        client_model = (attestation.get("product_name") or "").strip()
        if fleet_model and client_model and fleet_model == client_model:
            matches.append("hardware_model")

        # primary_mac ↔ mac_addresses[0]
        fleet_mac = (host.get("primary_mac") or "").strip().lower()
        client_macs = attestation.get("mac_addresses") or []
        if fleet_mac and client_macs and fleet_mac == client_macs[0].lower():
            matches.append("primary_mac")

        all_matched = len(matches) >= 2  # require at least 2/3 fields

        logger.info(
            "fleetdm_hw_verification",
            host_uuid=host_uuid,
            matches=matches,
            verified=all_matched,
        )

        return all_matched, matches
