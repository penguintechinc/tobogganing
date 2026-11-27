"""Audit logging for machine-JWT issuance (core/api/jwt.py).

Verifies every successful /jwt/token emits one audit record with masked jti,
metadata keys only, and never a token value or metadata value.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from quart import Quart

from hub_api.core.api import jwt as jwt_routes
from hub_api.core.api.jwt import mask_jti
from hub_api.tests.test_core_api_jwt_routes import _flag_on, app_with_jwt  # noqa: F401


@pytest.mark.parametrize(
    ("jti", "expected"),
    [
        ("0123456789abcdef", "****cdef"),
        ("short", "****"),
        ("", "****"),
        (None, "****"),
        (12345, "****"),
    ],
)
def test_mask_jti(jti: object, expected: str) -> None:
    """mask_jti keeps at most the last 4 chars and only for long string jtis."""
    assert mask_jti(jti) == expected


@pytest.mark.asyncio
async def test_token_issuance_emits_masked_audit(app_with_jwt: Quart) -> None:  # noqa: F811
    """A successful issuance writes one audit record without secrets."""
    from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster

    cluster = Cluster(
        id="c1",
        name="test",
        region="us",
        datacenter="dc1",
        headend_url="https://h.example.com",
        status="active",
        last_heartbeat=None,
        client_count=0,
        tenant="acme",
    )
    app_with_jwt.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = cluster
    client = app_with_jwt.test_client()
    with _flag_on(), patch.object(jwt_routes, "audit_logger") as audit:
        resp = await client.post(
            "/api/v1/jwt/token",
            json={
                "node_id": "c1",
                "node_type": "kubernetes_node",
                "api_key": "key",
                "metadata": {"region": "secret-region", "cluster_id": "x"},
            },
        )
    assert resp.status_code == 200
    body = await resp.get_json()
    assert audit.info.call_count == 1
    event, kwargs = audit.info.call_args.args[0], audit.info.call_args.kwargs
    assert event == "jwt_token_issued"
    assert kwargs["tenant"] == "acme"
    assert kwargs["claims_encrypted"] is False
    keys = kwargs["plaintext_claim_keys"]
    assert keys == sorted(keys) and {"cluster_id", "region"} <= set(keys)
    for key in ("access_jti", "refresh_jti"):
        assert kwargs[key].startswith("****") and len(kwargs[key]) <= 8
    rendered = repr(kwargs)
    assert body["access_token"] not in rendered
    assert body["refresh_token"] not in rendered
    assert "secret-region" not in rendered
