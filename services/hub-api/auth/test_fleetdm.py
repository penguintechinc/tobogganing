"""Unit tests for FleetDM client integration."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from auth.fleetdm import FleetDMClient


class TestFleetDMClient:
    def test_disabled_when_no_config(self):
        client = FleetDMClient(base_url="", api_key="")
        assert not client.enabled

    def test_enabled_when_configured(self):
        client = FleetDMClient(
            base_url="http://fleet.local:8080",
            api_key="test-api-key",
        )
        assert client.enabled

    @pytest.mark.asyncio
    async def test_get_host_disabled(self):
        client = FleetDMClient(base_url="", api_key="")
        result = await client.get_host("some-uuid")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_host_hardware_matching(self):
        """All three fields match → verified=True."""
        client = FleetDMClient(base_url="http://fleet.local", api_key="key")

        mock_host = {
            "hardware_serial": "SN-001",
            "hardware_model": "TestServer 3000",
            "primary_mac": "aa:bb:cc:dd:ee:ff",
        }

        with patch.object(client, "get_host", new_callable=AsyncMock, return_value=mock_host):
            verified, matches = await client.verify_host_hardware(
                "test-uuid",
                {
                    "board_serial": "SN-001",
                    "product_name": "TestServer 3000",
                    "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
                },
            )
            assert verified
            assert len(matches) == 3

    @pytest.mark.asyncio
    async def test_verify_host_hardware_partial_match(self):
        """Only 1/3 fields match → verified=False (need >=2)."""
        client = FleetDMClient(base_url="http://fleet.local", api_key="key")

        mock_host = {
            "hardware_serial": "SN-001",
            "hardware_model": "DifferentModel",
            "primary_mac": "ff:ff:ff:ff:ff:ff",
        }

        with patch.object(client, "get_host", new_callable=AsyncMock, return_value=mock_host):
            verified, matches = await client.verify_host_hardware(
                "test-uuid",
                {
                    "board_serial": "SN-001",
                    "product_name": "TestServer 3000",
                    "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
                },
            )
            assert not verified
            assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_verify_host_not_found(self):
        client = FleetDMClient(base_url="http://fleet.local", api_key="key")

        with patch.object(client, "get_host", new_callable=AsyncMock, return_value=None):
            verified, matches = await client.verify_host_hardware("missing", {})
            assert not verified
            assert len(matches) == 0
