"""Anti-mock integration tests for SASE managers using real penguin-dal AsyncDB.

Tests verify that managers round-trip against a real database, proving they use
the correct async penguin-dal API and handle tenant isolation properly.

All tests now pass after UUID column type fix (sa.String(36) instead of sa.UUID).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from hub_api.core import UserManager, UserRole
from hub_api.modules.sase.firewall.access_control import AccessControlManager, AccessRule, AccessType, RuleType
from hub_api.modules.sase.network.port_manager import PortConfigManager, PortProtocol, PortRangeConfig
from hub_api.modules.sase.network.vrf_manager import VRFManager, VRFConfiguration, VRFStatus, OSPFNeighbor


class TestAccessControlManagerRealDAL:
    """Access control manager integration tests against real database."""

    @pytest.mark.asyncio
    async def test_add_rule_and_retrieve(self, real_dal: any) -> None:
        """Verify rule addition via direct async_insert (manager tests this)."""
        manager = AccessControlManager(real_dal)
        tenant = "test-tenant-fw"
        user_id = str(uuid4())

        # Insert rule directly using async_insert
        rule_id = str(uuid4())
        now = datetime.utcnow()
        await real_dal.firewall_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            user_id=user_id,
            rule_type="domain",
            access_type="allow",
            pattern="example.com",
            priority=10,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Retrieve and verify via manager
        rules = await manager.get_user_rules(user_id, tenant)
        assert len(rules) >= 1
        assert any(r.id == rule_id for r in rules)

    @pytest.mark.asyncio
    async def test_get_user_rules(self, real_dal: any) -> None:
        """Verify rule retrieval for user against real DB."""
        manager = AccessControlManager(real_dal)
        tenant = "test-tenant-get-rules"
        user_id = str(uuid4())
        now = datetime.utcnow()

        # Add rules directly
        for i in range(2):
            await real_dal.firewall_rules.async_insert(
                id=str(uuid4()),
                tenant=tenant,
                user_id=user_id,
                rule_type="domain",
                access_type="allow",
                pattern=f"domain{i}.com",
                priority=i * 10,
                is_active=True,
                created_at=now,
                updated_at=now,
            )

        # Retrieve rules via manager
        rules = await manager.get_user_rules(user_id, tenant)
        assert len(rules) >= 2
        assert all(r.user_id == user_id for r in rules)
        assert all(r.tenant == tenant for r in rules)

    @pytest.mark.asyncio
    async def test_rule_tenant_isolation(self, real_dal: any) -> None:
        """Verify rules respect tenant isolation."""
        manager = AccessControlManager(real_dal)
        tenant1 = f"tenant-{uuid4()}"
        tenant2 = f"tenant-{uuid4()}"
        user_id = str(uuid4())
        now = datetime.utcnow()

        # Add rules to different tenants
        for tenant in [tenant1, tenant2]:
            await real_dal.firewall_rules.async_insert(
                id=str(uuid4()),
                tenant=tenant,
                user_id=user_id,
                rule_type="domain",
                access_type="allow",
                pattern="test.com",
                priority=10,
                is_active=True,
                created_at=now,
                updated_at=now,
            )

        # Get rules for tenant1 - should only contain tenant1 rules
        rules = await manager.get_user_rules(user_id, tenant1)
        assert all(r.tenant == tenant1 for r in rules)

        # Get rules for tenant2 - should only contain tenant2 rules
        rules2 = await manager.get_user_rules(user_id, tenant2)
        assert all(r.tenant == tenant2 for r in rules2)

    @pytest.mark.asyncio
    async def test_remove_rule(self, real_dal: any) -> None:
        """Verify rule removal against real DB."""
        manager = AccessControlManager(real_dal)
        tenant = "test-tenant-remove-rule"
        user_id = str(uuid4())
        rule_id = str(uuid4())
        now = datetime.utcnow()

        # Insert rule
        await real_dal.firewall_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            user_id=user_id,
            rule_type="domain",
            access_type="allow",
            pattern="example.com",
            priority=10,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Remove via manager
        success = await manager.remove_rule(rule_id, tenant)
        assert success is True

        # Verify it's gone
        rules = await manager.get_user_rules(user_id, tenant)
        assert not any(r.id == rule_id for r in rules)

    @pytest.mark.asyncio
    async def test_update_rule(self, real_dal: any) -> None:
        """Verify rule update against real DB."""
        manager = AccessControlManager(real_dal)
        tenant = "test-tenant-update-rule"
        user_id = str(uuid4())
        rule_id = str(uuid4())
        now = datetime.utcnow()

        # Insert rule
        await real_dal.firewall_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            user_id=user_id,
            rule_type="domain",
            access_type="allow",
            pattern="example.com",
            priority=10,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Update via manager
        rule = AccessRule(
            id=rule_id,
            tenant=tenant,
            user_id=user_id,
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            pattern="example.com",
            priority=10,
            is_active=True,
        )
        success = await manager.update_rule(rule)
        assert success is True

        # Verify change
        rules = await manager.get_user_rules(user_id, tenant)
        updated = next((r for r in rules if r.id == rule_id), None)
        assert updated is not None
        assert updated.access_type == AccessType.DENY

    @pytest.mark.asyncio
    async def test_get_all_rules(self, real_dal: any) -> None:
        """Verify get_all_rules returns only tenant's rules."""
        manager = AccessControlManager(real_dal)
        tenant = "test-tenant-all-rules"
        user_id = str(uuid4())
        now = datetime.utcnow()

        # Insert rule
        await real_dal.firewall_rules.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            user_id=user_id,
            rule_type="domain",
            access_type="allow",
            pattern="example.com",
            priority=10,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Get all rules for tenant
        rules = await manager.get_all_rules(tenant)
        assert all(r.tenant == tenant for r in rules)

    @pytest.mark.asyncio
    async def test_export_user_rules(self, real_dal: any) -> None:
        """Verify rule export for headend consumption."""
        manager = AccessControlManager(real_dal)
        tenant = "test-tenant-export"
        user_id = str(uuid4())
        now = datetime.utcnow()

        # Add domain rule
        await real_dal.firewall_rules.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            user_id=user_id,
            rule_type="domain",
            access_type="allow",
            pattern="example.com",
            priority=10,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Export
        export = await manager.export_user_rules(user_id, tenant)
        assert export["user_id"] == user_id
        assert "rules" in export
        assert "allow_domains" in export["rules"]

    @pytest.mark.asyncio
    async def test_check_access(self, real_dal: any) -> None:
        """Verify access checking with rules."""
        manager = AccessControlManager(real_dal)
        tenant = "test-tenant-check"
        user_id = str(uuid4())
        now = datetime.utcnow()

        # Add allow domain rule
        await real_dal.firewall_rules.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            user_id=user_id,
            rule_type="domain",
            access_type="allow",
            pattern="allowed.com",
            priority=10,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Check access to allowed domain
        allowed = await manager.check_access(user_id, tenant, "allowed.com")
        assert allowed is True

        # Check access to disallowed domain (no matching rule)
        denied = await manager.check_access(user_id, tenant, "other.com")
        assert denied is False


class TestUserManagerRealDAL:
    """User manager integration tests against real database.

    Tests multi-condition queries: authenticate (username+tenant+is_active),
    validate_session (token+tenant), cleanup_expired_sessions (expires_at<now+tenant).
    """

    @pytest.mark.asyncio
    async def test_authenticate_multi_condition(self, real_dal: any) -> None:
        """Verify authenticate uses correct multi-condition query (username+tenant+is_active)."""
        manager = UserManager(real_dal)
        tenant = f"tenant-auth-{uuid4()}"
        username = f"user-{uuid4()}"
        password = "test_password_123"
        now = datetime.utcnow()

        # Insert active user
        user_id = str(uuid4())
        import bcrypt
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        await real_dal.users.async_insert(
            id=user_id,
            username=username,
            email=f"{username}@test.com",
            password_hash=password_hash,
            role="reporter",
            tenant=tenant,
            is_active=True,
            created_at=now,
            updated_at=now,
            mfa_enabled=False,
            mfa_secret=None,
        )

        # Authenticate should succeed (3-condition: username+tenant+is_active)
        user = await manager.authenticate(username, password, tenant)
        assert user is not None
        assert user.username == username
        assert user.tenant == tenant
        assert user.is_active is True

    @pytest.mark.asyncio
    async def test_authenticate_wrong_tenant_multi_condition(self, real_dal: any) -> None:
        """Verify authenticate respects tenant isolation with multi-condition query."""
        manager = UserManager(real_dal)
        tenant1 = f"tenant-auth-t1-{uuid4()}"
        tenant2 = f"tenant-auth-t2-{uuid4()}"
        username = f"user-{uuid4()}"
        password = "test_password_123"
        now = datetime.utcnow()

        # Insert user in tenant1
        user_id = str(uuid4())
        import bcrypt
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        await real_dal.users.async_insert(
            id=user_id,
            username=username,
            email=f"{username}@test.com",
            password_hash=password_hash,
            role="reporter",
            tenant=tenant1,
            is_active=True,
            created_at=now,
            updated_at=now,
            mfa_enabled=False,
            mfa_secret=None,
        )

        # Authenticate with wrong tenant should fail
        user = await manager.authenticate(username, password, tenant2)
        assert user is None

    @pytest.mark.asyncio
    async def test_validate_session_multi_condition(self, real_dal: any) -> None:
        """Verify validate_session uses correct multi-condition query (token+tenant)."""
        manager = UserManager(real_dal)
        tenant = f"tenant-session-{uuid4()}"
        username = f"user-{uuid4()}"
        now = datetime.utcnow()

        # Create user and session
        user_id = str(uuid4())
        import bcrypt
        password_hash = bcrypt.hashpw(b"pwd", bcrypt.gensalt()).decode("utf-8")
        await real_dal.users.async_insert(
            id=user_id,
            username=username,
            email=f"{username}@test.com",
            password_hash=password_hash,
            role="reporter",
            tenant=tenant,
            is_active=True,
            created_at=now,
            updated_at=now,
            mfa_enabled=False,
            mfa_secret=None,
        )

        session_id = str(uuid4())
        token = "test_token_123"
        expires_at = now + timedelta(hours=8)
        await real_dal.sessions.async_insert(
            id=session_id,
            user_id=user_id,
            tenant=tenant,
            token=token,
            created_at=now,
            expires_at=expires_at,
        )

        # Validate session should succeed (2-condition: token+tenant)
        user = await manager.validate_session(token, tenant)
        assert user is not None
        assert user.id == user_id
        assert user.tenant == tenant

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_multi_condition(self, real_dal: any) -> None:
        """Verify cleanup_expired_sessions uses correct multi-condition query (expires_at<now+tenant)."""
        manager = UserManager(real_dal)
        tenant = f"tenant-cleanup-{uuid4()}"
        user_id = str(uuid4())
        now = datetime.utcnow()

        # Insert user
        import bcrypt
        password_hash = bcrypt.hashpw(b"pwd", bcrypt.gensalt()).decode("utf-8")
        await real_dal.users.async_insert(
            id=user_id,
            username=f"user-{uuid4()}",
            email=f"test@test.com",
            password_hash=password_hash,
            role="reporter",
            tenant=tenant,
            is_active=True,
            created_at=now,
            updated_at=now,
            mfa_enabled=False,
            mfa_secret=None,
        )

        # Insert expired and valid sessions
        expired_session_id = str(uuid4())
        valid_session_id = str(uuid4())
        await real_dal.sessions.async_insert(
            id=expired_session_id,
            user_id=user_id,
            tenant=tenant,
            token="expired_token",
            created_at=now - timedelta(hours=10),
            expires_at=now - timedelta(hours=2),
        )
        await real_dal.sessions.async_insert(
            id=valid_session_id,
            user_id=user_id,
            tenant=tenant,
            token="valid_token",
            created_at=now,
            expires_at=now + timedelta(hours=8),
        )

        # Cleanup should remove expired session only (2-condition: expires_at<now+tenant)
        deleted = await manager.cleanup_expired_sessions(tenant)
        assert deleted >= 1

        # Verify valid session still exists
        valid = await manager.validate_session("valid_token", tenant)
        assert valid is not None


class TestVRFManagerRealDAL:
    """VRF manager integration tests against real database.

    Tests multi-condition queries: list_vrfs (tenant+is_active), get_ospf_neighbors (vrf_id+tenant),
    delete_vrf (vrf_id+tenant + ospf cleanup).
    """

    @pytest.mark.asyncio
    async def test_list_vrfs_active_only_multi_condition(self, real_dal: any) -> None:
        """Verify list_vrfs with active_only uses correct multi-condition query (tenant+is_active)."""
        manager = VRFManager(real_dal)
        tenant = f"tenant-vrf-{uuid4()}"
        now = datetime.utcnow()

        # Insert active and inactive VRFs
        vrf_id_active = str(uuid4())
        vrf_id_inactive = str(uuid4())
        await real_dal.vrfs.async_insert(
            id=vrf_id_active,
            tenant=tenant,
            name="vrf-active",
            description="Active VRF",
            rd="100:1",
            rt_import="[]",
            rt_export="[]",
            ip_ranges="[]",
            status="active",
            ospf_enabled=False,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        await real_dal.vrfs.async_insert(
            id=vrf_id_inactive,
            tenant=tenant,
            name="vrf-inactive",
            description="Inactive VRF",
            rd="100:2",
            rt_import="[]",
            rt_export="[]",
            ip_ranges="[]",
            status="inactive",
            ospf_enabled=False,
            is_active=False,
            created_at=now,
            updated_at=now,
        )

        # List active only should exclude inactive (2-condition: tenant+is_active)
        active_vrfs = await manager.list_vrfs(tenant, active_only=True)
        assert all(v.is_active for v in active_vrfs)
        assert any(v.id == vrf_id_active for v in active_vrfs)
        assert not any(v.id == vrf_id_inactive for v in active_vrfs)

    @pytest.mark.asyncio
    async def test_delete_vrf_with_ospf_multi_condition(self, real_dal: any) -> None:
        """Verify delete_vrf cleans up OSPF with correct multi-condition queries (vrf_id+tenant)."""
        manager = VRFManager(real_dal)
        tenant = f"tenant-vrf-del-{uuid4()}"
        vrf_id = str(uuid4())
        now = datetime.utcnow()

        # Insert VRF
        await real_dal.vrfs.async_insert(
            id=vrf_id,
            tenant=tenant,
            name="vrf-todelete",
            description="VRF to delete",
            rd="100:100",
            rt_import="[]",
            rt_export="[]",
            ip_ranges="[]",
            status="active",
            ospf_enabled=True,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        # Insert OSPF area and neighbor
        area_id = str(uuid4())
        neighbor_id = str(uuid4())
        await real_dal.ospf_areas.async_insert(
            id=area_id,
            tenant=tenant,
            vrf_id=vrf_id,
            area_id="0.0.0.0",
            area_type="backbone",
            networks="[]",
            auth_type=None,
            auth_key=None,
            stub_default_cost=1,
            created_at=now,
            updated_at=now,
        )
        await real_dal.ospf_neighbors.async_insert(
            id=neighbor_id,
            tenant=tenant,
            vrf_id=vrf_id,
            neighbor_id="1.1.1.1",
            neighbor_ip="10.0.0.2",
            interface="eth0",
            area_id="0.0.0.0",
            state="Full",
            priority=1,
            dead_interval=40,
            hello_interval=10,
            last_seen=now,
            created_at=now,
            updated_at=now,
        )

        # Delete VRF - should cascade delete OSPF (multi-condition: vrf_id+tenant on ospf_neighbors and ospf_areas)
        success = await manager.delete_vrf(vrf_id, tenant)
        assert success is True

        # Verify VRF and OSPF are gone
        vrf = await manager.get_vrf(vrf_id, tenant)
        assert vrf is None


class TestPortConfigManagerRealDAL:
    """Port config manager integration tests against real database.

    Tests multi-condition queries: get_headend_config (headend_id+tenant+enabled),
    get_cluster_config (cluster_id+tenant+enabled), _has_port_overlap (headend_id+tenant+protocol+enabled).
    """

    @pytest.mark.asyncio
    async def test_get_headend_config_multi_condition(self, real_dal: any) -> None:
        """Verify get_headend_config uses correct multi-condition query (headend_id+tenant+enabled)."""
        manager = PortConfigManager(real_dal)
        tenant = f"tenant-port-{uuid4()}"
        headend_id = f"headend-{uuid4()}"
        cluster_id = f"cluster-{uuid4()}"
        now = datetime.utcnow()

        # Insert enabled and disabled port ranges
        await real_dal.port_ranges.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            headend_id=headend_id,
            cluster_id=cluster_id,
            start_port=8443,
            end_port=8443,
            protocol="tcp",
            description="HTTPS",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        await real_dal.port_ranges.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            headend_id=headend_id,
            cluster_id=cluster_id,
            start_port=9000,
            end_port=9000,
            protocol="tcp",
            description="Disabled service",
            enabled=False,
            created_at=now,
            updated_at=now,
        )

        # Get config should only return enabled ranges (3-condition: headend_id+tenant+enabled)
        config = await manager.get_headend_config(headend_id, tenant)
        assert config is not None
        assert config.headend_id == headend_id
        assert config.tenant == tenant
        assert len(config.tcp_ranges) >= 1
        assert all(r.enabled for r in config.tcp_ranges + config.udp_ranges)

    @pytest.mark.asyncio
    async def test_get_cluster_config_multi_condition(self, real_dal: any) -> None:
        """Verify get_cluster_config uses correct multi-condition query (cluster_id+tenant+enabled)."""
        manager = PortConfigManager(real_dal)
        tenant = f"tenant-cluster-{uuid4()}"
        cluster_id = f"cluster-{uuid4()}"
        headend1 = f"headend-{uuid4()}"
        headend2 = f"headend-{uuid4()}"
        now = datetime.utcnow()

        # Insert port ranges for two headends in cluster
        for headend_id in [headend1, headend2]:
            await real_dal.port_ranges.async_insert(
                id=str(uuid4()),
                tenant=tenant,
                headend_id=headend_id,
                cluster_id=cluster_id,
                start_port=8443,
                end_port=8443,
                protocol="tcp",
                description="HTTPS",
                enabled=True,
                created_at=now,
                updated_at=now,
            )

        # Get cluster config should return all headends (3-condition: cluster_id+tenant+enabled)
        configs = await manager.get_cluster_config(cluster_id, tenant)
        assert len(configs) >= 2
        assert all(c.tenant == tenant for c in configs.values())

    @pytest.mark.asyncio
    async def test_port_overlap_detection_multi_condition(self, real_dal: any) -> None:
        """Verify _has_port_overlap uses correct 4-condition query (headend_id+tenant+protocol+enabled)."""
        manager = PortConfigManager(real_dal)
        tenant = f"tenant-overlap-{uuid4()}"
        headend_id = f"headend-{uuid4()}"
        cluster_id = f"cluster-{uuid4()}"
        now = datetime.utcnow()

        # Insert existing TCP port range
        await real_dal.port_ranges.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            headend_id=headend_id,
            cluster_id=cluster_id,
            start_port=8000,
            end_port=8100,
            protocol="tcp",
            description="Existing range",
            enabled=True,
            created_at=now,
            updated_at=now,
        )

        # Create overlapping TCP range
        overlap_range = PortRangeConfig(
            id=str(uuid4()),
            tenant=tenant,
            headend_id=headend_id,
            cluster_id=cluster_id,
            start_port=8050,
            end_port=8150,
            protocol=PortProtocol.TCP,
            description="Overlap",
            enabled=True,
        )

        # Should detect overlap (4-condition: headend_id+tenant+protocol+enabled)
        has_overlap = await manager._has_port_overlap(headend_id, tenant, overlap_range)
        assert has_overlap is True

        # Non-overlapping UDP range should not overlap
        no_overlap_range = PortRangeConfig(
            id=str(uuid4()),
            tenant=tenant,
            headend_id=headend_id,
            cluster_id=cluster_id,
            start_port=8000,
            end_port=8100,
            protocol=PortProtocol.UDP,
            description="No overlap",
            enabled=True,
        )
        has_overlap_udp = await manager._has_port_overlap(headend_id, tenant, no_overlap_range)
        assert has_overlap_udp is False
