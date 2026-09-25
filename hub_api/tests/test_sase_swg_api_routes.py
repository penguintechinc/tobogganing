"""HTTP-level coverage tests for hub_api.modules.sase.security.swg.api routes.

The pre-existing test_sase_swg_api.py only exercises the LookupResultDTO
dataclass and blueprint metadata; these tests drive the actual route bodies
(success, validation, auth, and exception paths) through a real Quart test
client, matching the pattern used for blockpages API coverage.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.modules.sase.security.enforcement import EnforcementAction

API_MOD = "hub_api.modules.sase.security.swg.api"


@pytest_asyncio.fixture
async def swg_read_token(app_with_sase: Quart) -> str:
    """JWT with sase:read scope for tenant-a."""
    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "sase:read",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest_asyncio.fixture
async def swg_write_token(app_with_sase: Quart) -> str:
    """JWT with sase:write scope for tenant-a."""
    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "sase:write",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest_asyncio.fixture
async def swg_read_token_with_groups(app_with_sase: Quart) -> str:
    """JWT with sase:read scope and a groups claim, for tenant-a."""
    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "sase:read",
        "groups": ["group-a", "group-b"],
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest_asyncio.fixture
async def machine_jwt_swg_read(app_with_sase: Quart) -> str:
    """Machine-JWT (cluster) with swg:read scope."""
    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = build_machine_claims(
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="tenant-a",
        iss="tobogganing",
        aud="headend",
    )
    return await encode_access_token(claims, provider, ttl_hours=1)


class TestLookupDomain:
    """Covers GET /swg/lookup."""

    @pytest.mark.asyncio
    async def test_missing_domain_400(self, app_with_sase: Quart, swg_read_token: str) -> None:
        """Missing `domain` query param returns 400."""
        client = app_with_sase.test_client()
        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            response = await client.get(
                "/api/v1/sase/swg/lookup",
                headers={"Authorization": f"Bearer {swg_read_token}"},
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_domain_too_long_400(self, app_with_sase: Quart, swg_read_token: str) -> None:
        """A domain over 255 characters returns 400."""
        client = app_with_sase.test_client()
        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            response = await client.get(
                "/api/v1/sase/swg/lookup?domain=" + "a" * 256,
                headers={"Authorization": f"Bearer {swg_read_token}"},
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_lookup_not_configured_500(
        self, app_with_sase: Quart, swg_read_token: str
    ) -> None:
        """No SWG_LOOKUP engine configured returns 500."""
        app_with_sase.config["SWG_LOOKUP"] = None
        client = app_with_sase.test_client()
        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            response = await client.get(
                "/api/v1/sase/swg/lookup?domain=example.com",
                headers={"Authorization": f"Bearer {swg_read_token}"},
            )
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_claims_none_403(self, app_with_sase: Quart, swg_read_token: str) -> None:
        """current_claims() returning None inside the body yields 403."""
        app_with_sase.config["SWG_LOOKUP"] = MagicMock()
        client = app_with_sase.test_client()

        with (
            patch("hub_api.entitlements.gate.feature_enabled", return_value=True),
            patch(f"{API_MOD}.current_claims", return_value=None),
        ):
            response = await client.get(
                "/api/v1/sase/swg/lookup?domain=example.com",
                headers={"Authorization": f"Bearer {swg_read_token}"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_success_without_groups(self, app_with_sase: Quart, swg_read_token: str) -> None:
        """A successful lookup with no groups claim returns the DTO fields."""
        lookup_engine = AsyncMock()
        lookup_result = MagicMock(
            domain="example.com",
            categories=("news",),
            action=EnforcementAction.allow,
            matched_scope="tenant",
            uncategorized=False,
        )
        lookup_engine.lookup.return_value = lookup_result
        app_with_sase.config["SWG_LOOKUP"] = lookup_engine

        client = app_with_sase.test_client()
        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            response = await client.get(
                "/api/v1/sase/swg/lookup?domain=example.com",
                headers={"Authorization": f"Bearer {swg_read_token}"},
            )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["domain"] == "example.com"
        assert data["categories"] == ["news"]
        assert data["action"] == "allow"
        assert data["uncategorized"] is False

        # group_ids should be None since claims carried no "groups"
        _, kwargs = lookup_engine.lookup.call_args
        assert kwargs["group_ids"] is None

    @pytest.mark.asyncio
    async def test_success_with_groups_and_no_categories(
        self, app_with_sase: Quart, swg_read_token_with_groups: str
    ) -> None:
        """Groups claim is forwarded as group_ids; empty categories -> None."""
        lookup_engine = AsyncMock()
        lookup_result = MagicMock(
            domain="uncategorized.example.com",
            categories=None,
            action=EnforcementAction.block,
            matched_scope="global",
            uncategorized=True,
        )
        lookup_engine.lookup.return_value = lookup_result
        app_with_sase.config["SWG_LOOKUP"] = lookup_engine

        client = app_with_sase.test_client()
        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            response = await client.get(
                "/api/v1/sase/swg/lookup?domain=uncategorized.example.com",
                headers={"Authorization": f"Bearer {swg_read_token_with_groups}"},
            )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["categories"] is None
        assert data["uncategorized"] is True

        _, kwargs = lookup_engine.lookup.call_args
        assert kwargs["group_ids"] == ("group-a", "group-b")

    @pytest.mark.asyncio
    async def test_lookup_exception_500(self, app_with_sase: Quart, swg_read_token: str) -> None:
        """An exception from the lookup engine returns 500 with a generic message.

        Regression: error-detail leakage — the raw exception string (which
        can carry internal paths, DSNs, stack detail) must never reach the
        client; it's logged server-side instead.
        """
        lookup_engine = AsyncMock()
        lookup_engine.lookup.side_effect = RuntimeError("engine exploded")
        app_with_sase.config["SWG_LOOKUP"] = lookup_engine

        client = app_with_sase.test_client()
        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            response = await client.get(
                "/api/v1/sase/swg/lookup?domain=example.com",
                headers={"Authorization": f"Bearer {swg_read_token}"},
            )

        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Domain lookup failed"
        assert "engine exploded" not in data["error"]


class TestGetRadixArtifact:
    """Covers GET /swg/radix (machine-JWT protected)."""

    @pytest.mark.asyncio
    async def test_radix_not_configured_500(
        self, app_with_sase: Quart, machine_jwt_swg_read: str
    ) -> None:
        """No SWG_RADIX configured returns 500."""
        app_with_sase.config["SWG_RADIX"] = None
        client = app_with_sase.test_client()
        response = await client.get(
            "/api/v1/sase/swg/radix",
            headers={"Authorization": f"Bearer {machine_jwt_swg_read}"},
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_radix_success_returns_base64_artifact(
        self, app_with_sase: Quart, machine_jwt_swg_read: str
    ) -> None:
        """A configured radix tree is serialized and base64-encoded."""
        radix = MagicMock()
        radix.serialize.return_value = b"raw-artifact-bytes"
        app_with_sase.config["SWG_RADIX"] = radix

        client = app_with_sase.test_client()
        response = await client.get(
            "/api/v1/sase/swg/radix",
            headers={"Authorization": f"Bearer {machine_jwt_swg_read}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["encoding"] == "base64"
        assert base64.b64decode(data["artifact"]) == b"raw-artifact-bytes"

    @pytest.mark.asyncio
    async def test_radix_serialize_exception_500(
        self, app_with_sase: Quart, machine_jwt_swg_read: str
    ) -> None:
        """An exception during serialize() returns 500 with a generic message.

        Regression: error-detail leakage.
        """
        radix = MagicMock()
        radix.serialize.side_effect = RuntimeError("serialize failed")
        app_with_sase.config["SWG_RADIX"] = radix

        client = app_with_sase.test_client()
        response = await client.get(
            "/api/v1/sase/swg/radix",
            headers={"Authorization": f"Bearer {machine_jwt_swg_read}"},
        )
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Failed to generate radix artifact"
        assert "serialize failed" not in data["error"]

    @pytest.mark.asyncio
    async def test_radix_requires_machine_jwt_401(self, app_with_sase: Quart) -> None:
        """A request without any Bearer token is rejected before reaching the body."""
        client = app_with_sase.test_client()
        response = await client.get("/api/v1/sase/swg/radix")
        assert response.status_code == 401


class TestUpsertCategory:
    """Covers POST /swg/categories."""

    @pytest.mark.asyncio
    async def test_missing_fields_400(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """Missing domain/category returns 400."""
        client = app_with_sase.test_client()
        response = await client.post(
            "/api/v1/sase/swg/categories",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_claims_none_403(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """current_claims() returning None inside the body yields 403."""
        client = app_with_sase.test_client()
        with patch(f"{API_MOD}.current_claims", return_value=None):
            response = await client.post(
                "/api/v1/sase/swg/categories",
                headers={"Authorization": f"Bearer {swg_write_token}"},
                json={"domain": "example.com", "category": "news"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_mismatch_403(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """A body tenant that differs from the JWT tenant is rejected."""
        client = app_with_sase.test_client()
        response = await client.post(
            "/api/v1/sase/swg/categories",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={"domain": "example.com", "category": "news", "tenant": "tenant-b"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_ingest_not_configured_500(
        self, app_with_sase: Quart, swg_write_token: str
    ) -> None:
        """No SWG_INGEST_MANAGER configured returns 500."""
        app_with_sase.config["SWG_INGEST_MANAGER"] = None
        client = app_with_sase.test_client()
        response = await client.post(
            "/api/v1/sase/swg/categories",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={"domain": "example.com", "category": "news"},
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_upsert_success(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """A valid upsert calls the ingest manager and returns success."""
        ingest_mgr = AsyncMock()
        app_with_sase.config["SWG_INGEST_MANAGER"] = ingest_mgr

        client = app_with_sase.test_client()
        response = await client.post(
            "/api/v1/sase/swg/categories",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={"domain": "example.com", "category": "news"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "success"
        ingest_mgr.upsert_custom.assert_called_once_with("example.com", "news", tenant="tenant-a")

    @pytest.mark.asyncio
    async def test_upsert_exception_500(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """An exception from the ingest manager returns 500 with a generic message.

        Regression: error-detail leakage.
        """
        ingest_mgr = AsyncMock()
        ingest_mgr.upsert_custom.side_effect = RuntimeError("insert failed")
        app_with_sase.config["SWG_INGEST_MANAGER"] = ingest_mgr

        client = app_with_sase.test_client()
        response = await client.post(
            "/api/v1/sase/swg/categories",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={"domain": "example.com", "category": "news"},
        )
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Category upsert failed"
        assert "insert failed" not in data["error"]


class TestGetPolicies:
    """Covers GET /swg/policy."""

    @pytest.mark.asyncio
    async def test_claims_none_403(self, app_with_sase: Quart, swg_read_token: str) -> None:
        """current_claims() returning None inside the body yields 403."""
        client = app_with_sase.test_client()
        with patch(f"{API_MOD}.current_claims", return_value=None):
            response = await client.get(
                "/api/v1/sase/swg/policy",
                headers={"Authorization": f"Bearer {swg_read_token}"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_policy_manager_not_configured_500(
        self, app_with_sase: Quart, swg_read_token: str
    ) -> None:
        """No SWG_POLICY_MANAGER configured returns 500."""
        app_with_sase.config["SWG_POLICY_MANAGER"] = None
        client = app_with_sase.test_client()
        response = await client.get(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_read_token}"},
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_get_policies_success(self, app_with_sase: Quart, swg_read_token: str) -> None:
        """A configured policy manager returns the tenant's policies."""
        policy_mgr = AsyncMock()
        policy_row = MagicMock(
            id="pol-1", scope="tenant", scope_id=None, category="gambling", action="block"
        )
        policy_mgr.get_policies.return_value = [policy_row]
        app_with_sase.config["SWG_POLICY_MANAGER"] = policy_mgr

        client = app_with_sase.test_client()
        response = await client.get(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["policies"]) == 1
        assert data["policies"][0]["category"] == "gambling"
        policy_mgr.get_policies.assert_called_once_with("tenant-a")

    @pytest.mark.asyncio
    async def test_get_policies_exception_500(
        self, app_with_sase: Quart, swg_read_token: str
    ) -> None:
        """An exception from the policy manager returns 500 with a generic message.

        Regression: error-detail leakage.
        """
        policy_mgr = AsyncMock()
        policy_mgr.get_policies.side_effect = RuntimeError("db down")
        app_with_sase.config["SWG_POLICY_MANAGER"] = policy_mgr

        client = app_with_sase.test_client()
        response = await client.get(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_read_token}"},
        )
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Failed to fetch policies"
        assert "db down" not in data["error"]


class TestSetPolicy:
    """Covers PUT /swg/policy."""

    @pytest.mark.asyncio
    async def test_missing_fields_400(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """Missing scope/category/action returns 400."""
        client = app_with_sase.test_client()
        response = await client.put(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_claims_none_403(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """current_claims() returning None inside the body yields 403."""
        client = app_with_sase.test_client()
        with patch(f"{API_MOD}.current_claims", return_value=None):
            response = await client.put(
                "/api/v1/sase/swg/policy",
                headers={"Authorization": f"Bearer {swg_write_token}"},
                json={"scope": "tenant", "category": "gambling", "action": "block"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_mismatch_403(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """A body tenant differing from the JWT tenant is rejected."""
        client = app_with_sase.test_client()
        response = await client.put(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={
                "tenant": "tenant-b",
                "scope": "tenant",
                "category": "gambling",
                "action": "block",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_policy_manager_not_configured_500(
        self, app_with_sase: Quart, swg_write_token: str
    ) -> None:
        """No SWG_POLICY_MANAGER configured returns 500."""
        app_with_sase.config["SWG_POLICY_MANAGER"] = None
        client = app_with_sase.test_client()
        response = await client.put(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={"scope": "tenant", "category": "gambling", "action": "block"},
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_set_policy_success(self, app_with_sase: Quart, swg_write_token: str) -> None:
        """A valid set_policy call is forwarded to the manager with the JWT tenant."""
        policy_mgr = AsyncMock()
        app_with_sase.config["SWG_POLICY_MANAGER"] = policy_mgr

        client = app_with_sase.test_client()
        response = await client.put(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={
                "scope": "user",
                "scope_id": "user-42",
                "category": "gambling",
                "action": "block",
            },
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["tenant"] == "tenant-a"
        policy_mgr.set_policy.assert_called_once_with(
            "tenant-a", "user", "user-42", "gambling", "block"
        )

    @pytest.mark.asyncio
    async def test_set_policy_exception_500(
        self, app_with_sase: Quart, swg_write_token: str
    ) -> None:
        """An exception from the policy manager returns 500 with a generic message.

        Regression: error-detail leakage.
        """
        policy_mgr = AsyncMock()
        policy_mgr.set_policy.side_effect = RuntimeError("write failed")
        app_with_sase.config["SWG_POLICY_MANAGER"] = policy_mgr

        client = app_with_sase.test_client()
        response = await client.put(
            "/api/v1/sase/swg/policy",
            headers={"Authorization": f"Bearer {swg_write_token}"},
            json={"scope": "tenant", "category": "gambling", "action": "block"},
        )
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Failed to set policy"
        assert "write failed" not in data["error"]
