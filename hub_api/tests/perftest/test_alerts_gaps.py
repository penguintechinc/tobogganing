"""Coverage backfill for perftest_cluster/api/alerts.py.

test_wpc_alerts.py already covers rule create/list/delete roundtrip and the
webhook licensing trap; this file targets list_events and the
list_channels/delete_channel handlers not exercised elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from penguin_dal import AsyncDB
from quart import Quart


@pytest.mark.asyncio
async def test_create_rule_validation_errors(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create_rule validates each required field and the comparator/window."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    no_body = await client.post("/api/v1/perftest_cluster/alerts/rules", headers=headers)
    assert no_body.status_code == 400

    missing_name = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={"metric": "latency_ms", "comparator": "gt", "threshold": 1},
        headers=headers,
    )
    assert missing_name.status_code == 400
    assert "name" in (await missing_name.get_json())["error"]

    missing_metric = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={"name": "r", "comparator": "gt", "threshold": 1},
        headers=headers,
    )
    assert missing_metric.status_code == 400
    assert "metric" in (await missing_metric.get_json())["error"]

    missing_comparator = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={"name": "r", "metric": "latency_ms", "threshold": 1},
        headers=headers,
    )
    assert missing_comparator.status_code == 400
    assert "comparator" in (await missing_comparator.get_json())["error"]

    missing_threshold = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={"name": "r", "metric": "latency_ms", "comparator": "gt"},
        headers=headers,
    )
    assert missing_threshold.status_code == 400
    assert "threshold" in (await missing_threshold.get_json())["error"]

    invalid_comparator = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={"name": "r", "metric": "latency_ms", "comparator": "nope", "threshold": 1},
        headers=headers,
    )
    assert invalid_comparator.status_code == 400
    assert "comparator" in (await invalid_comparator.get_json())["error"].lower()

    negative_window = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={
            "name": "r",
            "metric": "latency_ms",
            "comparator": "gt",
            "threshold": 1,
            "window_seconds": -1,
        },
        headers=headers,
    )
    assert negative_window.status_code == 400
    assert "window_seconds" in (await negative_window.get_json())["error"]


@pytest.mark.asyncio
async def test_alerts_manager_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """list_rules / delete_rule / list_events all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_cluster.api.alerts as alerts_api

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    async def _boom_get_db() -> Any:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(alerts_api, "get_db", _boom_get_db)

    list_rules_resp = await client.get("/api/v1/perftest_cluster/alerts/rules", headers=headers)
    assert list_rules_resp.status_code == 500

    delete_rule_resp = await client.delete(
        "/api/v1/perftest_cluster/alerts/rules/whatever", headers=headers
    )
    assert delete_rule_resp.status_code == 500

    list_events_resp = await client.get("/api/v1/perftest_cluster/alerts/events", headers=headers)
    assert list_events_resp.status_code == 500


@pytest.mark.asyncio
async def test_channels_manager_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """create_channel / list_channels / delete_channel catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_cluster.api.alerts as alerts_api

    async def _boom(self: Any, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("channel manager exploded")

    monkeypatch.setattr(alerts_api.ChannelManager, "create_channel", _boom)
    monkeypatch.setattr(alerts_api.ChannelManager, "list_channels", _boom)
    monkeypatch.setattr(alerts_api.ChannelManager, "delete_channel", _boom)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_cluster/alerts/channels",
        json={"name": "x", "kind": "email", "config": {"to": ["a@example.com"]}},
        headers=headers,
    )
    assert create_resp.status_code == 500

    list_resp = await client.get("/api/v1/perftest_cluster/alerts/channels", headers=headers)
    assert list_resp.status_code == 500

    delete_resp = await client.delete("/api/v1/perftest_cluster/alerts/channels/x", headers=headers)
    assert delete_resp.status_code == 500


@pytest.mark.asyncio
async def test_list_events_empty(app_all_perftest_realdal: Quart, pf_write_token: str) -> None:
    """Listing alert events with none fired returns an empty list."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/alerts/events",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["events"] == []


@pytest.mark.asyncio
async def test_list_events_after_breach(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: AsyncDB
) -> None:
    """A directly-seeded alert event shows up in list_events with full fields."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    rule_id = str(uuid4())
    await real_dal.alert_rules.async_insert(
        id=rule_id,
        tenant="test-tenant",
        name="seeded-rule",
        metric="latency_ms",
        comparator="gt",
        threshold=10.0,
        window_seconds=300,
        device_id=None,
        test_type=None,
        channel_id=None,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )
    event_id = str(uuid4())
    await real_dal.alert_events.async_insert(
        id=event_id,
        tenant="test-tenant",
        rule_id=rule_id,
        device_id="dev-evt",
        observed_value=150.0,
        fired_at=datetime.now(timezone.utc),
        notified=True,
    )

    events_resp = await client.get("/api/v1/perftest_cluster/alerts/events", headers=headers)
    assert events_resp.status_code == 200
    events = (await events_resp.get_json())["events"]
    assert any(e["id"] == event_id and e["observed_value"] == 150.0 for e in events)


@pytest.mark.asyncio
async def test_list_channels_empty_and_after_create(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """list_channels returns an empty list, then the created channel (redacted)."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    empty = await client.get("/api/v1/perftest_cluster/alerts/channels", headers=headers)
    assert empty.status_code == 200
    assert (await empty.get_json())["channels"] == []

    create_resp = await client.post(
        "/api/v1/perftest_cluster/alerts/channels",
        json={"name": "ops", "kind": "email", "config": {"to": ["a@example.com"]}},
        headers=headers,
    )
    assert create_resp.status_code == 201
    channel_id = (await create_resp.get_json())["id"]

    listed = await client.get("/api/v1/perftest_cluster/alerts/channels", headers=headers)
    assert listed.status_code == 200
    listed_data = await listed.get_json()
    assert any(c["id"] == channel_id for c in listed_data["channels"])


@pytest.mark.asyncio
async def test_delete_channel_success_and_not_found(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """delete_channel removes an existing channel and 404s on repeat/unknown."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_cluster/alerts/channels",
        json={"name": "to-delete", "kind": "email", "config": {"to": ["b@example.com"]}},
        headers=headers,
    )
    channel_id = (await create_resp.get_json())["id"]

    del_resp = await client.delete(
        f"/api/v1/perftest_cluster/alerts/channels/{channel_id}", headers=headers
    )
    assert del_resp.status_code in (200, 204)

    del_again = await client.delete(
        f"/api/v1/perftest_cluster/alerts/channels/{channel_id}", headers=headers
    )
    assert del_again.status_code == 404

    del_unknown = await client.delete(
        "/api/v1/perftest_cluster/alerts/channels/never-existed", headers=headers
    )
    assert del_unknown.status_code == 404


@pytest.mark.asyncio
async def test_create_channel_invalid_kind(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create_channel rejects an unknown 'kind' value with 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/alerts/channels",
        json={"name": "bad", "kind": "carrier-pigeon", "config": {}},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400
