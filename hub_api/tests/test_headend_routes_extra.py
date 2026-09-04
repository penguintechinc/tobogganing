"""Additional coverage for api/headend_routes.py: error branches, client-node auth,
refresh-rotation, list_clusters_flat, validate_auth_token, and port-range formatting.

test_headend_policy_routes.py, test_machine_jwt_routes.py, and
test_machine_jwt_issuance.py exercise the dual-accept auth paths and the
cluster-node happy paths; this file fills in the manager-not-configured (500)
branches, client-node auth, refresh-token rotation, cluster listing, and the
tcp/udp port-range formatting helpers with non-empty ranges.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.api.headend_routes import (
    _extract_bearer_token,
    _extract_bearer_token_from_header,
    _get_tcp_ranges_string,
    _get_udp_ranges_string,
    _port_range_to_dict,
    _verify_headend_token,
    get_access_control_manager,
    get_certificate_manager,
    get_port_config_manager,
    get_user_manager,
)
from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair


class TestFactoryGetters:
    """Direct tests for the trivial manager-factory functions."""

    def test_get_access_control_manager(self) -> None:
        """Returns an AccessControlManager bound to the given db."""
        db = MagicMock()
        mgr = get_access_control_manager(db)
        assert mgr.db is db

    def test_get_user_manager(self) -> None:
        """Returns a UserManager bound to the given db."""
        db = MagicMock()
        mgr = get_user_manager(db)
        assert mgr.db is db

    def test_get_port_config_manager(self) -> None:
        """Returns a PortConfigManager bound to the given db."""
        db = MagicMock()
        mgr = get_port_config_manager(db)
        assert mgr.db is db

    def test_get_certificate_manager_passthrough(self) -> None:
        """Passes through the given CertificateManager (or None) unchanged."""
        cert_mgr = MagicMock()
        assert get_certificate_manager(cert_mgr) is cert_mgr
        assert get_certificate_manager(None) is None


class TestLocalTokenHelpers:
    """Direct unit tests for the module-local token-extraction helpers."""

    def test_verify_headend_token_no_env_var(self) -> None:
        """Returns False when HEADEND_API_TOKEN is unset."""
        with patch.dict("os.environ", {}, clear=True):
            assert _verify_headend_token("anything") is False

    def test_verify_headend_token_match(self) -> None:
        """Returns True on an exact constant-time match."""
        with patch.dict("os.environ", {"HEADEND_API_TOKEN": "secret"}):
            assert _verify_headend_token("secret") is True

    def test_verify_headend_token_mismatch(self) -> None:
        """Returns False on mismatch."""
        with patch.dict("os.environ", {"HEADEND_API_TOKEN": "secret"}):
            assert _verify_headend_token("wrong") is False

    @pytest.mark.asyncio
    async def test_extract_bearer_token_no_header(self, app: Quart) -> None:
        """_extract_bearer_token() returns None with no Authorization header."""
        async with app.test_request_context("/x"):
            assert _extract_bearer_token() is None

    def test_extract_bearer_token_from_header_non_bearer(self) -> None:
        """Returns None for a non-Bearer Authorization header value."""
        assert _extract_bearer_token_from_header("Basic abc123") is None

    def test_extract_bearer_token_from_header_empty(self) -> None:
        """Returns None for an empty header value."""
        assert _extract_bearer_token_from_header("") is None


class TestPortRangeFormatting:
    """Tests for _get_tcp_ranges_string / _get_udp_ranges_string / _port_range_to_dict."""

    def _make_range(self, start: int, end: int) -> MagicMock:
        r = MagicMock()
        r.start_port = start
        r.end_port = end
        return r

    def test_tcp_ranges_string_single_port_and_range(self) -> None:
        """Formats a mix of single ports and ranges as comma-separated."""
        ranges = [self._make_range(80, 80), self._make_range(443, 8443)]
        assert _get_tcp_ranges_string(ranges) == "80,443-8443"

    def test_tcp_ranges_string_empty(self) -> None:
        """Returns empty string for no ranges."""
        assert _get_tcp_ranges_string([]) == ""

    def test_udp_ranges_string_single_port_and_range(self) -> None:
        """Formats a mix of single ports and ranges as comma-separated."""
        ranges = [self._make_range(53, 53), self._make_range(5353, 5400)]
        assert _get_udp_ranges_string(ranges) == "53,5353-5400"

    def test_udp_ranges_string_empty(self) -> None:
        """Returns empty string for no ranges."""
        assert _get_udp_ranges_string([]) == ""

    def test_port_range_to_dict(self) -> None:
        """Converts a PortRangeConfig-like object into a plain dict."""
        now = datetime.now(timezone.utc)
        pr = MagicMock(
            id="pr-1",
            start_port=80,
            end_port=80,
            description="http",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        pr.protocol.value = "tcp"

        result = _port_range_to_dict(pr)

        assert result == {
            "id": "pr-1",
            "start_port": 80,
            "end_port": 80,
            "protocol": "tcp",
            "description": "http",
            "enabled": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }


@pytest.fixture
def app_with_headend(app: Quart) -> Quart:
    """App with KEY_PROVIDER + machine-JWT-ready managers configured."""
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    cluster_manager = MagicMock()
    cluster_manager.authenticate_cluster = AsyncMock()
    client_registry = MagicMock()
    client_registry.authenticate_client = AsyncMock()
    app.config["CLUSTER_MANAGER"] = cluster_manager
    app.config["CLIENT_REGISTRY"] = client_registry

    return app


def _flag_off() -> object:
    """Force dual-accept legacy-token flag OFF isn't needed for machine-JWT paths."""
    import shared.licensing.entitlements

    return patch.object(shared.licensing.entitlements, "_flag_on", return_value=True)


@pytest.mark.asyncio
async def test_get_firewall_rules_no_db(app_with_headend: Quart) -> None:
    """GET /firewall/rules returns 500 when get_db() returns None."""
    from hub_api.auth.machine_claims import build_machine_claims

    claims = build_machine_claims(
        sub_id="c1", node_type="kubernetes_node", tenant="acme", iss="tobogganing", aud="headend"
    )
    token = await encode_access_token(claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1)

    with _flag_off():
        with patch("hub_api.api.headend_routes.get_db", return_value=None):
            client = app_with_headend.test_client()
            resp = await client.get(
                "/api/v1/firewall/rules", headers={"Authorization": f"Bearer {token}"}
            )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_firewall_rules_partial_export_failure_continues(
    app_with_headend: Quart, mock_db: MagicMock
) -> None:
    """GET /firewall/rules continues past a per-user export failure."""
    from hub_api.auth.machine_claims import build_machine_claims

    claims = build_machine_claims(
        sub_id="c1", node_type="kubernetes_node", tenant="acme", iss="tobogganing", aud="headend"
    )
    token = await encode_access_token(claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1)

    user1 = MagicMock(id="u1", is_active=True)
    fake_um = MagicMock()
    fake_um.list_users = AsyncMock(return_value=[user1])
    fake_acm = MagicMock()
    fake_acm.export_user_rules = AsyncMock(side_effect=RuntimeError("export failed"))

    with _flag_off():
        with (
            patch("hub_api.api.headend_routes.get_db", return_value=mock_db),
            patch("hub_api.api.headend_routes.get_user_manager", return_value=fake_um),
            patch("hub_api.api.headend_routes.get_access_control_manager", return_value=fake_acm),
        ):
            client = app_with_headend.test_client()
            resp = await client.get(
                "/api/v1/firewall/rules", headers={"Authorization": f"Bearer {token}"}
            )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["rules_count"] == 0


@pytest.mark.asyncio
async def test_get_firewall_rules_unexpected_exception(
    app_with_headend: Quart, mock_db: MagicMock
) -> None:
    """GET /firewall/rules returns 500 on an unexpected top-level exception."""
    from hub_api.auth.machine_claims import build_machine_claims

    claims = build_machine_claims(
        sub_id="c1", node_type="kubernetes_node", tenant="acme", iss="tobogganing", aud="headend"
    )
    token = await encode_access_token(claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1)

    with _flag_off():
        with (
            patch("hub_api.api.headend_routes.get_db", return_value=mock_db),
            patch("hub_api.api.headend_routes.get_user_manager", side_effect=RuntimeError("boom")),
        ):
            client = app_with_headend.test_client()
            resp = await client.get(
                "/api/v1/firewall/rules", headers={"Authorization": f"Bearer {token}"}
            )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_wireguard_peers_no_cert_manager(app_with_headend: Quart) -> None:
    """GET /wireguard/peers returns 500 without CERT_MANAGER configured."""
    from hub_api.auth.machine_claims import build_machine_claims

    claims = build_machine_claims(
        sub_id="c1", node_type="kubernetes_node", tenant="acme", iss="tobogganing", aud="headend"
    )
    token = await encode_access_token(claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1)

    with _flag_off():
        client = app_with_headend.test_client()
        resp = await client.get(
            "/api/v1/wireguard/peers", headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_wireguard_peers_fetch_failure(app_with_headend: Quart) -> None:
    """GET /wireguard/peers returns 500 when get_all_wireguard_peers() raises."""
    from hub_api.auth.machine_claims import build_machine_claims

    claims = build_machine_claims(
        sub_id="c1", node_type="kubernetes_node", tenant="acme", iss="tobogganing", aud="headend"
    )
    token = await encode_access_token(claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1)

    cert_manager = MagicMock()
    cert_manager.get_all_wireguard_peers = AsyncMock(side_effect=RuntimeError("boom"))
    app_with_headend.config["CERT_MANAGER"] = cert_manager

    with _flag_off():
        client = app_with_headend.test_client()
        resp = await client.get(
            "/api/v1/wireguard/peers", headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_auth_public_key_no_provider(app: Quart) -> None:
    """GET /auth/public-key returns 500 without KEY_PROVIDER configured.

    The base `app` fixture already configures an in-app KEY_PROVIDER via
    create_app()'s default fallback, so it must be explicitly cleared here.
    """
    client = app.test_client()
    with patch.dict(app.config, {"KEY_PROVIDER": None}):
        resp = await client.get("/api/v1/auth/public-key")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_wireguard_peers_unexpected_top_level_exception(
    app_with_headend: Quart,
) -> None:
    """GET /wireguard/peers returns 500 when accessing g.machine_tenant fails unexpectedly."""
    from hub_api.auth.machine_claims import build_machine_claims

    claims = build_machine_claims(
        sub_id="c1", node_type="kubernetes_node", tenant="acme", iss="tobogganing", aud="headend"
    )
    token = await encode_access_token(claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1)

    app_with_headend.config["CERT_MANAGER"] = MagicMock()

    with _flag_off():
        with patch("hub_api.api.headend_routes.datetime") as mock_datetime:
            mock_datetime.now.side_effect = RuntimeError("clock broken")
            client = app_with_headend.test_client()
            resp = await client.get(
                "/api/v1/wireguard/peers", headers={"Authorization": f"Bearer {token}"}
            )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_auth_public_key_unexpected_exception(app_with_headend: Quart) -> None:
    """GET /auth/public-key returns 500 when reading kid raises unexpectedly."""
    provider = app_with_headend.config["KEY_PROVIDER"]
    with patch.object(
        type(provider),
        "kid",
        new_callable=lambda: property(lambda self: (_ for _ in ()).throw(RuntimeError("boom"))),
    ):
        client = app_with_headend.test_client()
        resp = await client.get("/api/v1/auth/public-key")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_auth_public_key_success(app_with_headend: Quart) -> None:
    """GET /auth/public-key returns the public PEM (public, no auth required)."""
    client = app_with_headend.test_client()
    resp = await client.get("/api/v1/auth/public-key")
    assert resp.status_code == 200
    data = await resp.get_json()
    assert "public_key" in data


class TestIssueAuthToken:
    """Tests for POST /auth/token (client-node auth + error branches)."""

    @pytest.mark.asyncio
    async def test_no_key_provider(self, app: Quart) -> None:
        """Returns 500 without KEY_PROVIDER configured (base `app` sets one by default)."""
        client = app.test_client()
        with patch.dict(app.config, {"KEY_PROVIDER": None}):
            resp = await client.post(
                "/api/v1/auth/token",
                json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "k"},
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_client_docker_auth_success(self, app_with_headend: Quart) -> None:
        """Client-docker node authenticates and receives tokens."""
        client_obj = MagicMock(id="cl1", tenant="acme", type="docker", cluster_id="c1")
        app_with_headend.config["CLIENT_REGISTRY"].authenticate_client.return_value = client_obj

        client = app_with_headend.test_client()
        resp = await client.post(
            "/api/v1/auth/token",
            json={"node_id": "cl1", "node_type": "client_docker", "api_key": "k"},
        )
        assert resp.status_code == 200
        data = await resp.get_json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_client_auth_exception_caught(self, app_with_headend: Quart) -> None:
        """A client_registry exception is caught and treated as unauthenticated."""
        app_with_headend.config["CLIENT_REGISTRY"].authenticate_client.side_effect = RuntimeError(
            "boom"
        )

        client = app_with_headend.test_client()
        resp = await client.post(
            "/api/v1/auth/token",
            json={"node_id": "cl1", "node_type": "client_docker", "api_key": "k"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_access_token_encode_failure_returns_500(self, app_with_headend: Quart) -> None:
        """A ValueError from encode_access_token surfaces as 500."""
        from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster

        cluster = Cluster(
            id="c1",
            name="t",
            region="us",
            datacenter="dc1",
            headend_url="https://h",
            status="active",
            last_heartbeat=None,
            client_count=0,
            tenant="acme",
        )
        app_with_headend.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = cluster

        with patch(
            "hub_api.api.headend_routes.encode_access_token",
            side_effect=ValueError("signing failed"),
        ):
            client = app_with_headend.test_client()
            resp = await client.post(
                "/api/v1/auth/token",
                json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "k"},
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_client_registry_not_configured(self, app: Quart) -> None:
        """A client_docker node with no CLIENT_REGISTRY configured is unauthenticated."""
        private_pem, public_pem = generate_rsa_key_pair()
        app.config["KEY_PROVIDER"] = InAppKeyProvider(private_pem, public_pem)
        app.config["CLUSTER_MANAGER"] = None
        app.config["CLIENT_REGISTRY"] = None

        client = app.test_client()
        resp = await client.post(
            "/api/v1/auth/token",
            json={"node_id": "cl1", "node_type": "client_docker", "api_key": "k"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_encode_failure_returns_500(self, app_with_headend: Quart) -> None:
        """A ValueError from encoding the refresh token (2nd encode call) surfaces as 500."""
        from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster

        cluster = Cluster(
            id="c1",
            name="t",
            region="us",
            datacenter="dc1",
            headend_url="https://h",
            status="active",
            last_heartbeat=None,
            client_count=0,
            tenant="acme",
        )
        app_with_headend.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = cluster

        real_encode = encode_access_token
        call_count = {"n": 0}

        async def fake_encode(*args: object, **kwargs: object) -> str:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return await real_encode(*args, **kwargs)  # type: ignore[arg-type]
            raise ValueError("refresh signing failed")

        with patch("hub_api.api.headend_routes.encode_access_token", side_effect=fake_encode):
            client = app_with_headend.test_client()
            resp = await client.post(
                "/api/v1/auth/token",
                json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "k"},
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_outer_value_error_returns_400(self, app_with_headend: Quart) -> None:
        """A ValueError escaping the main try block returns 400 (validation-style error)."""
        with patch(
            "hub_api.api.headend_routes.build_machine_claims",
            side_effect=ValueError("bad claims"),
        ):
            from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster

            cluster = Cluster(
                id="c1",
                name="t",
                region="us",
                datacenter="dc1",
                headend_url="https://h",
                status="active",
                last_heartbeat=None,
                client_count=0,
                tenant="acme",
            )
            app_with_headend.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = cluster

            client = app_with_headend.test_client()
            resp = await client.post(
                "/api/v1/auth/token",
                json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "k"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_fields_returns_400(self, app_with_headend: Quart) -> None:
        """Missing required fields returns 400."""
        client = app_with_headend.test_client()
        resp = await client.post("/api/v1/auth/token", json={"node_id": "c1"})
        assert resp.status_code == 400


class TestRefreshAuthToken:
    """Direct tests for headend_routes.refresh_auth_token().

    NOTE: `/api/v1/auth/refresh` used to be registered by BOTH `auth_bp`
    (api/auth_routes.py) and `headend_bp` (this module) — auth_bp,
    registered first in create_app(), silently shadowed headend_bp's
    handler at that exact path. Fixed by moving auth_bp's user refresh to
    /api/v1/auth/refresh-token (see auth_routes.py:79 and
    test_portal_auth_api.py::test_refresh_routes_do_not_collide /
    test_headend_policy_routes.py::test_post_auth_refresh_dispatches_to_machine_handler
    for HTTP-level dispatch regression coverage). These tests still call
    the handler function directly inside a manually-entered request
    context — that's a deliberate choice to exercise
    refresh_auth_token()'s internal branches (missing dependencies, decode
    failures, rotate_refresh error propagation) without needing a full
    HTTP round trip, not a workaround for the collision anymore.
    """

    async def _call_refresh(
        self, app: Quart, json_body: object = None, raw_data: str | None = None
    ):
        """Call refresh_auth_token() directly within a request context."""
        from hub_api.api.headend_routes import refresh_auth_token

        kwargs: dict[str, object] = {"method": "POST"}
        if raw_data is not None:
            kwargs["data"] = raw_data
        else:
            kwargs["json"] = json_body if json_body is not None else {}

        async with app.test_request_context("/api/v1/auth/refresh", **kwargs):
            return await refresh_auth_token()

    @pytest.mark.asyncio
    async def test_missing_refresh_token(self, app: Quart) -> None:
        """Returns 400 when refresh_token is missing."""
        result, status = await self._call_refresh(app, json_body={})
        assert status == 400

    @pytest.mark.asyncio
    async def test_no_key_provider(self, app: Quart) -> None:
        """Returns 500 without KEY_PROVIDER configured."""
        with patch.dict(app.config, {"KEY_PROVIDER": None}):
            result, status = await self._call_refresh(app, json_body={"refresh_token": "sometoken"})
        assert status == 500

    @pytest.mark.asyncio
    async def test_no_cache_configured(self, app_with_headend: Quart) -> None:
        """Returns 500 when CACHE isn't configured.

        create_app() always sets a real (if disconnected) CacheClient onto
        config["CACHE"], so it must be explicitly nulled here to hit this
        branch.
        """
        with patch.dict(app_with_headend.config, {"CACHE": None}):
            result, status = await self._call_refresh(
                app_with_headend, json_body={"refresh_token": "sometoken"}
            )
        assert status == 500

    @pytest.mark.asyncio
    async def test_no_dal_configured(self, app_with_headend: Quart) -> None:
        """Returns 500 when get_db() returns None.

        DAL-accessor regression: refresh_auth_token() used to read
        db = current_app.config.get("DAL"), a key never set in production
        create_app() (headend_routes.py:551 now uses get_db(), the same
        accessor every other handler in this module uses — see
        get_firewall_rules()/test_get_firewall_rules_no_db above). Forcing
        get_db() itself to return None (rather than merely leaving
        config["DAL"] unset) is what actually exercises this branch now.
        """
        app_with_headend.config["CACHE"] = MagicMock()
        with patch("hub_api.api.headend_routes.get_db", return_value=None):
            result, status = await self._call_refresh(
                app_with_headend, json_body={"refresh_token": "sometoken"}
            )
        assert status == 500

    @pytest.mark.asyncio
    async def test_invalid_refresh_token(self, app_with_headend: Quart) -> None:
        """Returns 401 when the refresh token doesn't decode.

        DAL comes from the real get_db() accessor here (app_with_headend's
        underlying app fixture wires a real, if tableless, AsyncDB) —
        config["DAL"] is intentionally left unset.
        """
        app_with_headend.config["CACHE"] = MagicMock()

        result, status = await self._call_refresh(
            app_with_headend, json_body={"refresh_token": "garbage"}
        )
        assert status == 401

    @pytest.mark.asyncio
    async def test_rotate_refresh_error_propagates_status(self, app_with_headend: Quart) -> None:
        """A RefreshError from rotate_refresh() propagates its status/body."""
        from hub_api.auth.machine_claims import build_machine_claims
        from hub_api.auth.refresh import RefreshError

        provider = app_with_headend.config["KEY_PROVIDER"]
        claims = build_machine_claims(
            sub_id="c1",
            node_type="kubernetes_node",
            tenant="acme",
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

        # DAL intentionally unset in config — the real get_db() accessor
        # supplies it (DAL-accessor regression; see test_no_dal_configured).
        app_with_headend.config["CACHE"] = MagicMock()

        with patch(
            "hub_api.auth.refresh.rotate_refresh",
            new=AsyncMock(side_effect=RefreshError(status=401, body={"error": "superseded"})),
        ):
            result, status = await self._call_refresh(
                app_with_headend, json_body={"refresh_token": refresh_token}
            )
        assert status == 401

    @pytest.mark.asyncio
    async def test_rotate_refresh_success(self, app_with_headend: Quart) -> None:
        """A successful rotate_refresh() returns new access/refresh tokens."""
        from hub_api.auth.machine_claims import build_machine_claims

        provider = app_with_headend.config["KEY_PROVIDER"]
        claims = build_machine_claims(
            sub_id="c1",
            node_type="kubernetes_node",
            tenant="acme",
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

        # DAL intentionally unset in config — the real get_db() accessor
        # supplies it (DAL-accessor regression; see test_no_dal_configured).
        app_with_headend.config["CACHE"] = MagicMock()

        with patch(
            "hub_api.auth.refresh.rotate_refresh",
            new=AsyncMock(
                return_value={"access_token": "new-access", "refresh_token": "new-refresh"}
            ),
        ):
            result, status = await self._call_refresh(
                app_with_headend, json_body={"refresh_token": refresh_token}
            )
        assert status == 200
        assert result["access_token"] == "new-access"

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_500(self, app_with_headend: Quart) -> None:
        """An unexpected exception from request.get_json returns 500."""
        result, status = await self._call_refresh(app_with_headend, raw_data="not json")
        assert status == 500


class TestListClustersFlat:
    """Tests for GET /clusters/."""

    @pytest.mark.asyncio
    async def test_no_claims_returns_403(self, app: Quart) -> None:
        """Returns 403 without a valid Bearer token (require_tenant enforces this)."""
        client = app.test_client()
        resp = await client.get("/api/v1/clusters/")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_success(self, app_with_headend: Quart, mock_db: MagicMock) -> None:
        """Returns a cluster list for the authenticated tenant."""
        provider = app_with_headend.config["KEY_PROVIDER"]
        claims = {
            "sub": "user-1",
            "iss": "tobogganing",
            "aud": "tobogganing",
            "tenant": "acme",
            "scope": "clusters:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        # NOTE: `name=` is reserved by Mock's constructor for the mock's own
        # debug name, not an attribute — set it post-construction instead, or
        # `c.name` in the route returns a runaway auto-generated child Mock
        # that recurses infinitely under JSON encoding.
        fake_cluster = MagicMock(
            id="c1",
            region="us",
            datacenter="dc1",
            status="active",
            client_count=2,
        )
        fake_cluster.name = "Cluster1"
        fake_mgr = MagicMock()
        fake_mgr.initialize = AsyncMock()
        fake_mgr.get_all_clusters = AsyncMock(return_value=[fake_cluster])

        with (
            patch("hub_api.api.headend_routes.get_db", return_value=mock_db),
            patch("hub_api.api.headend_routes.ClusterManager", return_value=fake_mgr),
        ):
            client = app_with_headend.test_client()
            resp = await client.get(
                "/api/v1/clusters/", headers={"Authorization": f"Bearer {token}"}
            )
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["clusters"][0]["id"] == "c1"

    @pytest.mark.asyncio
    async def test_db_unavailable_returns_500(self, app_with_headend: Quart) -> None:
        """Returns 500 when get_db() returns None."""
        provider = app_with_headend.config["KEY_PROVIDER"]
        claims = {
            "sub": "user-1",
            "iss": "tobogganing",
            "aud": "tobogganing",
            "tenant": "acme",
            "scope": "clusters:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        with patch("hub_api.api.headend_routes.get_db", return_value=None):
            client = app_with_headend.test_client()
            resp = await client.get(
                "/api/v1/clusters/", headers={"Authorization": f"Bearer {token}"}
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_500(
        self, app_with_headend: Quart, mock_db: MagicMock
    ) -> None:
        """Returns 500 when ClusterManager construction/use raises."""
        provider = app_with_headend.config["KEY_PROVIDER"]
        claims = {
            "sub": "user-1",
            "iss": "tobogganing",
            "aud": "tobogganing",
            "tenant": "acme",
            "scope": "clusters:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        with (
            patch("hub_api.api.headend_routes.get_db", return_value=mock_db),
            patch("hub_api.api.headend_routes.ClusterManager", side_effect=RuntimeError("boom")),
        ):
            client = app_with_headend.test_client()
            resp = await client.get(
                "/api/v1/clusters/", headers={"Authorization": f"Bearer {token}"}
            )
        assert resp.status_code == 500


class TestValidateAuthToken:
    """Tests for POST /auth/validate."""

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, app: Quart) -> None:
        """Returns 401 without an Authorization header."""
        client = app.test_client()
        resp = await client.post("/api/v1/auth/validate")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_key_provider_returns_500(self, app: Quart) -> None:
        """Returns 500 when KEY_PROVIDER isn't configured (base `app` sets one by default)."""
        client = app.test_client()
        with patch.dict(app.config, {"KEY_PROVIDER": None}):
            resp = await client.post(
                "/api/v1/auth/validate", headers={"Authorization": "Bearer sometoken"}
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_success(self, app_with_headend: Quart) -> None:
        """Returns 200 with decoded claims for a valid token."""
        provider = app_with_headend.config["KEY_PROVIDER"]
        claims = {
            "sub": "cluster:c1",
            "iss": "test",
            "aud": "headend",
            "tenant": "acme",
            "node_type": "kubernetes_node",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        client = app_with_headend.test_client()
        resp = await client.post(
            "/api/v1/auth/validate", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_500(self, app_with_headend: Quart) -> None:
        """Returns 500 when decode_token raises unexpectedly."""
        with patch("hub_api.api.headend_routes.decode_token", side_effect=RuntimeError("boom")):
            client = app_with_headend.test_client()
            resp = await client.post("/api/v1/auth/validate", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 500


class TestGetHeadendPorts:
    """Tests for GET /headend/<headend_id>/ports."""

    @pytest.mark.asyncio
    async def test_no_db(self, app_with_headend: Quart) -> None:
        """Returns 500 when get_db() returns None."""
        from hub_api.auth.machine_claims import build_machine_claims

        claims = build_machine_claims(
            sub_id="c1",
            node_type="kubernetes_node",
            tenant="acme",
            iss="tobogganing",
            aud="headend",
        )
        token = await encode_access_token(
            claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1
        )

        with _flag_off():
            with patch("hub_api.api.headend_routes.get_db", return_value=None):
                client = app_with_headend.test_client()
                resp = await client.get(
                    "/api/v1/headend/h1/ports",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_success_with_populated_ranges(
        self, app_with_headend: Quart, mock_db: MagicMock
    ) -> None:
        """Returns formatted tcp/udp range strings and detail dicts for a real config."""
        from hub_api.auth.machine_claims import build_machine_claims

        claims = build_machine_claims(
            sub_id="c1",
            node_type="kubernetes_node",
            tenant="acme",
            iss="tobogganing",
            aud="headend",
        )
        token = await encode_access_token(
            claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1
        )

        now = datetime.now(timezone.utc)
        tcp_range = MagicMock(
            id="r1",
            start_port=80,
            end_port=80,
            description="http",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        tcp_range.protocol.value = "tcp"
        udp_range = MagicMock(
            id="r2",
            start_port=53,
            end_port=53,
            description="dns",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        udp_range.protocol.value = "udp"

        fake_config = MagicMock(
            headend_id="h1",
            cluster_id="cluster-h1",
            tcp_ranges=[tcp_range],
            udp_ranges=[udp_range],
            updated_at=now,
        )
        fake_pcm = MagicMock()
        fake_pcm.get_headend_config = AsyncMock(return_value=fake_config)

        with _flag_off():
            with (
                patch("hub_api.api.headend_routes.get_db", return_value=mock_db),
                patch("hub_api.api.headend_routes.get_port_config_manager", return_value=fake_pcm),
            ):
                client = app_with_headend.test_client()
                resp = await client.get(
                    "/api/v1/headend/h1/ports",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200
        data = await resp.get_json()
        assert data["tcp_ranges"] == "80"
        assert data["udp_ranges"] == "53"
        assert data["tcp_ranges_detail"][0]["protocol"] == "tcp"

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_500(
        self, app_with_headend: Quart, mock_db: MagicMock
    ) -> None:
        """Returns 500 when the port config manager raises unexpectedly."""
        from hub_api.auth.machine_claims import build_machine_claims

        claims = build_machine_claims(
            sub_id="c1",
            node_type="kubernetes_node",
            tenant="acme",
            iss="tobogganing",
            aud="headend",
        )
        token = await encode_access_token(
            claims, app_with_headend.config["KEY_PROVIDER"], ttl_hours=1
        )

        with _flag_off():
            with (
                patch("hub_api.api.headend_routes.get_db", return_value=mock_db),
                patch(
                    "hub_api.api.headend_routes.get_port_config_manager",
                    side_effect=RuntimeError("boom"),
                ),
            ):
                client = app_with_headend.test_client()
                resp = await client.get(
                    "/api/v1/headend/h1/ports",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 500
