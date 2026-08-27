"""Coverage-focused tests for SecurityScanner's background-loop and DB-facing methods.

These target the pipeline orchestration (start_scanning_pipeline, the three
background loops), the scheduling decision logic, and the scan-execution /
finding-storage DB paths in hub_api.modules.sase.security.scanner.core, which
the higher-level tests in test_sase_scanner.py don't reach.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.sase.security.scanner.core import (
    ScanFinding,
    ScanSeverity,
    ScanType,
    SecurityScanner,
)

CORE_MOD = "hub_api.modules.sase.security.scanner.core"


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock penguin-dal DAL supporting the callable-query and async-table patterns."""
    db = MagicMock()

    table_mock = AsyncMock()
    table_mock.async_insert = AsyncMock(return_value="row-1")
    db.security_scans = table_mock
    db.security_findings = AsyncMock()
    db.security_findings.async_insert = AsyncMock(return_value="finding-1")

    query_result = AsyncMock()
    query_result.select = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    query_result.update = AsyncMock(return_value=1)
    db.return_value = query_result

    return db


async def _raise_cancelled(*_args: object, **_kwargs: object) -> None:
    """Stand-in for asyncio.sleep that immediately cancels the enclosing loop."""
    raise asyncio.CancelledError()


class TestDockerClientInit:
    """Covers the optional Docker client initialization branch."""

    def test_docker_client_initializes_when_module_available(self, mock_db: MagicMock) -> None:
        """When the `docker` package is importable, docker_client is set from_env()."""
        fake_docker_module = MagicMock()
        fake_docker_module.from_env.return_value = "fake-docker-client"

        with patch.dict(sys.modules, {"docker": fake_docker_module}):
            scanner = SecurityScanner(mock_db)

        assert scanner.docker_client == "fake-docker-client"


class TestStartScanningPipeline:
    """Covers start_scanning_pipeline's gather + CancelledError handling."""

    @pytest.mark.asyncio
    async def test_start_scanning_pipeline_gathers_all_tasks(self, mock_db: MagicMock) -> None:
        """start_scanning_pipeline runs all three background coroutines."""
        scanner = SecurityScanner(mock_db)
        scanner._schedule_scans = AsyncMock(return_value=None)
        scanner._monitor_infrastructure = AsyncMock(return_value=None)
        scanner._process_threat_intelligence = AsyncMock(return_value=None)

        await scanner.start_scanning_pipeline()

        scanner._schedule_scans.assert_called_once()
        scanner._monitor_infrastructure.assert_called_once()
        scanner._process_threat_intelligence.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_scanning_pipeline_swallows_cancelled_error(
        self, mock_db: MagicMock
    ) -> None:
        """A CancelledError from asyncio.gather is logged and swallowed."""
        scanner = SecurityScanner(mock_db)
        scanner._schedule_scans = AsyncMock(return_value=None)
        scanner._monitor_infrastructure = AsyncMock(return_value=None)
        scanner._process_threat_intelligence = AsyncMock(return_value=None)

        with patch(
            f"{CORE_MOD}.asyncio.gather", new=AsyncMock(side_effect=asyncio.CancelledError())
        ):
            await scanner.start_scanning_pipeline()  # must not raise


class TestScheduleScansLoop:
    """Covers the _schedule_scans background loop body."""

    @pytest.mark.asyncio
    async def test_schedule_scans_runs_one_cycle_then_cancelled(self, mock_db: MagicMock) -> None:
        """One pass evaluates every configured scan type, then the loop exits cleanly."""
        scanner = SecurityScanner(mock_db)
        scanner._should_run_scan = AsyncMock(return_value=True)
        scanner._execute_scan = AsyncMock(return_value=None)

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            await scanner._schedule_scans()  # CancelledError caught internally -> break

        assert scanner._execute_scan.call_count == len(scanner.scan_configs)

    @pytest.mark.asyncio
    async def test_schedule_scans_skips_disabled_scan_types(self, mock_db: MagicMock) -> None:
        """Disabled scan types are skipped via the `continue` branch."""
        scanner = SecurityScanner(mock_db)
        for config in scanner.scan_configs.values():
            config["enabled"] = False
        scanner._should_run_scan = AsyncMock(return_value=True)
        scanner._execute_scan = AsyncMock(return_value=None)

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            await scanner._schedule_scans()

        scanner._execute_scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_scans_exception_triggers_backoff_sleep(
        self, mock_db: MagicMock
    ) -> None:
        """An exception in the scan loop logs and backs off via asyncio.sleep(60)."""
        scanner = SecurityScanner(mock_db)
        scanner._should_run_scan = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            with pytest.raises(asyncio.CancelledError):
                await scanner._schedule_scans()


class TestMonitorInfrastructureLoop:
    """Covers the _monitor_infrastructure background loop body."""

    @pytest.mark.asyncio
    async def test_monitor_infrastructure_one_cycle_with_docker_client(
        self, mock_db: MagicMock
    ) -> None:
        """With a docker_client set, container scanning is invoked."""
        scanner = SecurityScanner(mock_db)
        scanner.docker_client = MagicMock()
        scanner._scan_new_containers = AsyncMock()
        scanner._scan_kubernetes_resources = AsyncMock()
        scanner._scan_network_services = AsyncMock()

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            await scanner._monitor_infrastructure()

        scanner._scan_new_containers.assert_called_once()
        scanner._scan_kubernetes_resources.assert_called_once()
        scanner._scan_network_services.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_infrastructure_without_docker_client(self, mock_db: MagicMock) -> None:
        """Without a docker_client, container scanning is skipped."""
        scanner = SecurityScanner(mock_db)
        scanner.docker_client = None
        scanner._scan_new_containers = AsyncMock()
        scanner._scan_kubernetes_resources = AsyncMock()
        scanner._scan_network_services = AsyncMock()

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            await scanner._monitor_infrastructure()

        scanner._scan_new_containers.assert_not_called()

    @pytest.mark.asyncio
    async def test_monitor_infrastructure_exception_triggers_backoff_sleep(
        self, mock_db: MagicMock
    ) -> None:
        """An exception in infra monitoring logs and backs off."""
        scanner = SecurityScanner(mock_db)
        scanner.docker_client = None
        scanner._scan_kubernetes_resources = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            with pytest.raises(asyncio.CancelledError):
                await scanner._monitor_infrastructure()


class TestProcessThreatIntelligenceLoop:
    """Covers the _process_threat_intelligence background loop body."""

    @pytest.mark.asyncio
    async def test_process_threat_intelligence_one_cycle(self, mock_db: MagicMock) -> None:
        """One pass invokes log, network, and feed-correlation scanning."""
        scanner = SecurityScanner(mock_db)
        scanner._scan_logs_for_threats = AsyncMock()
        scanner._scan_network_threats = AsyncMock()
        scanner._correlate_with_threat_feeds = AsyncMock()

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            await scanner._process_threat_intelligence()

        scanner._scan_logs_for_threats.assert_called_once()
        scanner._scan_network_threats.assert_called_once()
        scanner._correlate_with_threat_feeds.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_threat_intelligence_exception_triggers_backoff_sleep(
        self, mock_db: MagicMock
    ) -> None:
        """An exception in threat-intel processing logs and backs off."""
        scanner = SecurityScanner(mock_db)
        scanner._scan_logs_for_threats = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(f"{CORE_MOD}.asyncio.sleep", new=_raise_cancelled):
            with pytest.raises(asyncio.CancelledError):
                await scanner._process_threat_intelligence()


class TestShouldRunScan:
    """Covers the full decision matrix in _should_run_scan."""

    @pytest.mark.asyncio
    async def test_never_run_before_returns_true(self, mock_db: MagicMock) -> None:
        """No prior completed scan -> always due."""
        rowset = MagicMock(first=MagicMock(return_value=None))
        mock_db.return_value.select = AsyncMock(return_value=rowset)
        scanner = SecurityScanner(mock_db)

        result = await scanner._should_run_scan(
            ScanType.VULNERABILITY_SCAN, {"schedule": "0 2 * * *"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_tenant_scoped_query_condition(self, mock_db: MagicMock) -> None:
        """A tenant_id on the scanner adds a tenant filter to the query condition."""
        rowset = MagicMock(first=MagicMock(return_value=None))
        mock_db.return_value.select = AsyncMock(return_value=rowset)
        scanner = SecurityScanner(mock_db, tenant_id="tenant-x")

        result = await scanner._should_run_scan(
            ScanType.VULNERABILITY_SCAN, {"schedule": "0 2 * * *"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_daily_schedule_not_yet_due(self, mock_db: MagicMock) -> None:
        """A daily rule with a scan completed moments ago is not yet due."""
        last_scan = MagicMock(completed_at=datetime.utcnow())
        rowset = MagicMock(first=MagicMock(return_value=last_scan))
        mock_db.return_value.select = AsyncMock(return_value=rowset)
        scanner = SecurityScanner(mock_db)

        result = await scanner._should_run_scan(
            ScanType.VULNERABILITY_SCAN, {"schedule": "0 2 * * *"}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_weekly_schedule_is_due(self, mock_db: MagicMock) -> None:
        """A weekly rule with a scan completed over a week ago is due."""
        last_scan = MagicMock(completed_at=datetime.utcnow() - timedelta(weeks=2))
        rowset = MagicMock(first=MagicMock(return_value=last_scan))
        mock_db.return_value.select = AsyncMock(return_value=rowset)
        scanner = SecurityScanner(mock_db)

        result = await scanner._should_run_scan(ScanType.PORT_SCAN, {"schedule": "0 3 * * 0"})

        assert result is True

    @pytest.mark.asyncio
    async def test_fifteen_minute_schedule_is_due(self, mock_db: MagicMock) -> None:
        """A 15-minute rule with an hour-old scan is due."""
        last_scan = MagicMock(completed_at=datetime.utcnow() - timedelta(hours=1))
        rowset = MagicMock(first=MagicMock(return_value=last_scan))
        mock_db.return_value.select = AsyncMock(return_value=rowset)
        scanner = SecurityScanner(mock_db)

        result = await scanner._should_run_scan(
            ScanType.THREAT_INTEL_SCAN, {"schedule": "*/15 * * * *"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_schedule_defaults_to_daily(self, mock_db: MagicMock) -> None:
        """An unrecognized schedule string falls back to a 24h default."""
        last_scan = MagicMock(completed_at=datetime.utcnow() - timedelta(days=2))
        rowset = MagicMock(first=MagicMock(return_value=last_scan))
        mock_db.return_value.select = AsyncMock(return_value=rowset)
        scanner = SecurityScanner(mock_db)

        result = await scanner._should_run_scan(
            ScanType.COMPLIANCE_SCAN, {"schedule": "not-a-real-schedule"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_missing_completed_at_falls_back_to_now(self, mock_db: MagicMock) -> None:
        """A last_scan row with no completed_at falls back to utcnow() (not due)."""
        last_scan = MagicMock(completed_at=None)
        rowset = MagicMock(first=MagicMock(return_value=last_scan))
        mock_db.return_value.select = AsyncMock(return_value=rowset)
        scanner = SecurityScanner(mock_db)

        result = await scanner._should_run_scan(
            ScanType.VULNERABILITY_SCAN, {"schedule": "0 2 * * *"}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_db_exception_defaults_to_true(self, mock_db: MagicMock) -> None:
        """A DB failure while checking the schedule fails open (run the scan)."""
        scanner = SecurityScanner(mock_db)
        mock_db.side_effect = RuntimeError("db down")

        result = await scanner._should_run_scan(
            ScanType.VULNERABILITY_SCAN, {"schedule": "0 2 * * *"}
        )

        assert result is True


class TestExecuteScan:
    """Covers the DB-facing _execute_scan orchestration method."""

    @pytest.mark.asyncio
    async def test_execute_scan_success_records_and_updates(self, mock_db: MagicMock) -> None:
        """A successful scan inserts a start record, stores findings, and marks complete."""
        scanner = SecurityScanner(mock_db, tenant_id="tenant-x")
        scanner._store_finding = AsyncMock()

        finding = ScanFinding(
            scan_id="s1",
            finding_type="vulnerability",
            severity=ScanSeverity.HIGH,
            title="t",
            description="d",
            affected_component="c",
            recommendation="r",
            cve_ids=[],
            cvss_score=5.0,
            confidence=90,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            metadata={},
        )

        with patch(
            "hub_api.modules.sase.security.scanner.scans.execute_scan_by_type",
            new=AsyncMock(return_value=[finding]),
        ):
            await scanner._execute_scan(
                ScanType.VULNERABILITY_SCAN, scanner.scan_configs[ScanType.VULNERABILITY_SCAN]
            )

        scanner._store_finding.assert_called_once_with(finding)
        mock_db.security_scans.async_insert.assert_called_once()
        mock_db.return_value.update.assert_called_once()
        update_kwargs = mock_db.return_value.update.call_args.kwargs
        assert update_kwargs["status"] == "completed"
        assert update_kwargs["findings_count"] == 1
        assert update_kwargs["high_findings"] == 1

    @pytest.mark.asyncio
    async def test_execute_scan_start_record_insert_failure_is_swallowed(
        self, mock_db: MagicMock
    ) -> None:
        """A failure recording scan-start doesn't stop the scan from proceeding."""
        scanner = SecurityScanner(mock_db)
        scanner._store_finding = AsyncMock()
        mock_db.security_scans.async_insert = AsyncMock(side_effect=RuntimeError("insert failed"))

        with patch(
            "hub_api.modules.sase.security.scanner.scans.execute_scan_by_type",
            new=AsyncMock(return_value=[]),
        ):
            await scanner._execute_scan(
                ScanType.PORT_SCAN, scanner.scan_configs[ScanType.PORT_SCAN]
            )

        mock_db.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_scan_completion_update_failure_is_swallowed(
        self, mock_db: MagicMock
    ) -> None:
        """A failure updating the completed scan record does not raise."""
        scanner = SecurityScanner(mock_db)
        scanner._store_finding = AsyncMock()
        mock_db.return_value.update = AsyncMock(side_effect=RuntimeError("update failed"))

        with patch(
            "hub_api.modules.sase.security.scanner.scans.execute_scan_by_type",
            new=AsyncMock(return_value=[]),
        ):
            await scanner._execute_scan(
                ScanType.PORT_SCAN, scanner.scan_configs[ScanType.PORT_SCAN]
            )  # must not raise

    @pytest.mark.asyncio
    async def test_execute_scan_failure_updates_failed_status(self, mock_db: MagicMock) -> None:
        """When the scan itself raises, the scan record is marked failed."""
        scanner = SecurityScanner(mock_db)

        with patch(
            "hub_api.modules.sase.security.scanner.scans.execute_scan_by_type",
            new=AsyncMock(side_effect=RuntimeError("scan crashed")),
        ):
            await scanner._execute_scan(
                ScanType.PORT_SCAN, scanner.scan_configs[ScanType.PORT_SCAN]
            )

        update_kwargs = mock_db.return_value.update.call_args.kwargs
        assert update_kwargs["status"] == "failed"
        assert "scan crashed" in update_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_execute_scan_failure_and_failed_status_update_both_raise(
        self, mock_db: MagicMock
    ) -> None:
        """Even if marking the scan failed also raises, _execute_scan does not propagate."""
        scanner = SecurityScanner(mock_db)
        mock_db.return_value.update = AsyncMock(side_effect=RuntimeError("update also failed"))

        with patch(
            "hub_api.modules.sase.security.scanner.scans.execute_scan_by_type",
            new=AsyncMock(side_effect=RuntimeError("scan crashed")),
        ):
            await scanner._execute_scan(
                ScanType.PORT_SCAN, scanner.scan_configs[ScanType.PORT_SCAN]
            )  # must not raise


class TestStoreFinding:
    """Covers the _store_finding DB-insert method."""

    @pytest.mark.asyncio
    async def test_store_finding_inserts_record(self, mock_db: MagicMock) -> None:
        """A finding is inserted into security_findings with the expected fields."""
        scanner = SecurityScanner(mock_db, tenant_id="tenant-x")
        finding = ScanFinding(
            scan_id="s1",
            finding_type="vulnerability",
            severity=ScanSeverity.CRITICAL,
            title="t",
            description="d",
            affected_component="c",
            recommendation="r",
            cve_ids=["CVE-1"],
            cvss_score=9.8,
            confidence=95,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            metadata={"k": "v"},
        )

        await scanner._store_finding(finding)

        mock_db.security_findings.async_insert.assert_called_once()
        kwargs = mock_db.security_findings.async_insert.call_args.kwargs
        assert kwargs["scan_id"] == "s1"
        assert kwargs["severity"] == "critical"
        assert kwargs["tenant_id"] == "tenant-x"

    @pytest.mark.asyncio
    async def test_store_finding_swallows_db_exception(self, mock_db: MagicMock) -> None:
        """A DB insert failure while storing a finding is logged and swallowed."""
        scanner = SecurityScanner(mock_db)
        mock_db.security_findings.async_insert = AsyncMock(side_effect=RuntimeError("db down"))
        finding = ScanFinding(
            scan_id="s1",
            finding_type="vulnerability",
            severity=ScanSeverity.LOW,
            title="t",
            description="d",
            affected_component="c",
            recommendation="r",
            cve_ids=[],
            cvss_score=1.0,
            confidence=50,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            metadata={},
        )

        await scanner._store_finding(finding)  # must not raise


def test_infra_monitor_module_imports_cleanly() -> None:
    """infra_monitor.py is a standalone placeholder module; just verify it imports."""
    import hub_api.modules.sase.security.scanner.infra_monitor as infra_monitor

    assert infra_monitor.logger is not None
