"""Tests for the SASE scanner's real host checks, threat-feed lookup and infra monitor.

Host checks run against temp files; the threat-feed lookup runs against a fake
DAL-shaped feeds manager; failure paths assert the scan fails loudly.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.sase.security.scanner import host_checks, infra_monitor, scans
from hub_api.modules.sase.security.scanner.core import ScanSeverity, ScanType, SecurityScanner
from hub_api.modules.sase.security.scanner.host_checks import CheckNotApplicable
from hub_api.modules.sase.security.scanner.telemetry import ScannerDependencyError

SCANS = "hub_api.modules.sase.security.scanner.scans"


def _write(path: Path, text: str, mode: int = 0o644) -> Path:
    """Write ``text`` to ``path`` with ``mode`` and return the path."""
    path.write_text(text)
    os.chmod(path, mode)  # nosec B103 - test fixture: modes under test on tmp files
    return path


# ---- sshd ----------------------------------------------------------------


def test_ssh_missing_config_not_applicable(tmp_path: Path) -> None:
    """No sshd_config means sshd is not installed."""
    with pytest.raises(CheckNotApplicable):
        host_checks.check_ssh_configuration(tmp_path / "nope")


def test_ssh_insecure_settings_flagged(tmp_path: Path) -> None:
    """Root login, empty passwords, protocol 1 and default password auth are flagged."""
    cfg = _write(
        tmp_path / "sshd",
        "# c\n\nPermitRootLogin yes\nPermitEmptyPasswords yes\n"
        "Protocol 1\nPermitRootLogin no\nMatch User x\n  PasswordAuthentication no\n",
    )
    opts = {i.metadata["option"] for i in host_checks.check_ssh_configuration(cfg)}
    assert opts == {"permitrootlogin", "permitemptypasswords", "protocol", "passwordauthentication"}


def test_ssh_hardened_config_passes(tmp_path: Path) -> None:
    """A hardened config yields no issues; bare keys parse to empty values."""
    cfg = _write(tmp_path / "sshd", "PermitRootLogin no\nPasswordAuthentication no\nBanner\n")
    assert host_checks.check_ssh_configuration(cfg) == []


def test_soc2_only_reports_access_options(tmp_path: Path) -> None:
    """SOC2 CC6.1 maps to root-login / empty-password options only."""
    cfg = _write(tmp_path / "sshd", "PermitRootLogin yes\n")
    issues = host_checks.check_soc2_cc61_logical_access(cfg)
    assert [i.metadata["option"] for i in issues] == ["permitrootlogin"]


# ---- file / service permissions -----------------------------------------


def test_file_permissions_flags_world_access(tmp_path: Path) -> None:
    """World-readable shadow and world-writable passwd are flagged; group is fine."""
    shadow = _write(tmp_path / "shadow", "x", 0o644)
    passwd = _write(tmp_path / "passwd", "x", 0o666)
    group = _write(tmp_path / "group", "x", 0o644)
    issues = host_checks.check_file_permissions(shadow, passwd, group)
    assert {i.component for i in issues} == {str(shadow), str(passwd)}


def test_file_permissions_secure(tmp_path: Path) -> None:
    """Correct modes pass; missing files are skipped."""
    shadow = _write(tmp_path / "shadow", "x", 0o640)
    assert host_checks.check_file_permissions(shadow, tmp_path / "a", tmp_path / "b") == []


def test_file_permissions_none_present(tmp_path: Path) -> None:
    """No account files at all is not applicable."""
    with pytest.raises(CheckNotApplicable):
        host_checks.check_file_permissions(tmp_path / "a", tmp_path / "b", tmp_path / "c")


def test_service_configuration(tmp_path: Path) -> None:
    """World-writable docker socket flagged; 0660 passes; absent is not applicable."""
    sock = _write(tmp_path / "docker.sock", "", 0o666)
    assert len(host_checks.check_service_configuration(sock)) == 1
    os.chmod(sock, 0o660)  # nosec B103 - test fixture: tmp file
    assert host_checks.check_service_configuration(sock) == []
    with pytest.raises(CheckNotApplicable):
        host_checks.check_service_configuration(tmp_path / "missing")


# ---- compliance controls -------------------------------------------------


def test_cis_freevxfs_disabled_passes(tmp_path: Path) -> None:
    """Module not loaded and install-disabled -> compliant."""
    mods = _write(tmp_path / "modules", "ext4 1 0 - Live 0x0\n\n")
    d = tmp_path / "modprobe.d"
    d.mkdir()
    _write(d / "cis.conf", "install freevxfs /bin/false\nshort\n")
    assert host_checks.check_cis_freevxfs_disabled(mods, d) == []


def test_cis_freevxfs_loaded_or_not_disabled(tmp_path: Path) -> None:
    """Loaded module or missing modprobe.d -> violation."""
    mods = _write(tmp_path / "modules", "freevxfs 1 0 - Live 0x0\n")
    issues = host_checks.check_cis_freevxfs_disabled(mods, tmp_path / "none")
    assert issues[0].metadata == {"loaded": True, "install_disabled": False}


def test_cis_unreadable_proc_raises(tmp_path: Path) -> None:
    """Unreadable /proc/modules propagates (scan must fail loudly)."""
    with pytest.raises(FileNotFoundError):
        host_checks.check_cis_freevxfs_disabled(tmp_path / "nope", tmp_path)


def test_nist_ac2(tmp_path: Path) -> None:
    """Extra UID-0 and empty-password accounts flagged; comments/short lines ignored."""
    p = _write(
        tmp_path / "passwd",
        "#c\nroot:x:0:0::/root:/bin/sh\ntoor:x:0:0::/:/bin/sh\nguest::1001:1001::/:/bin/sh\nbad\n",
    )
    titles = sorted(i.title for i in host_checks.check_nist_ac2_accounts(p))
    assert titles == ["Account without password", "Non-root account with UID 0"]


# ---- scan orchestration ---------------------------------------------------


@pytest.mark.asyncio
async def test_configuration_scan_produces_findings_and_metrics() -> None:
    """Issues become findings; outcome metric recorded per check status."""
    issue = host_checks.CheckIssue("t", "d", "c", "r", {"option": "x"})
    checks = [
        ("A", ScanSeverity.HIGH, lambda: [issue]),
        ("B", ScanSeverity.MEDIUM, lambda: []),
        ("C", ScanSeverity.MEDIUM, MagicMock(side_effect=CheckNotApplicable("n/a"))),
    ]
    with patch(f"{SCANS}.CONFIG_CHECKS", checks), patch(f"{SCANS}.CHECK_RESULTS") as m:
        findings = await scans._run_configuration_scan("s1", None)
    assert len(findings) == 1 and findings[0].severity == ScanSeverity.HIGH
    statuses = sorted(c.args[1]["status"] for c in m.add.call_args_list)
    assert statuses == ["fail", "not_applicable", "pass"]


@pytest.mark.asyncio
async def test_configuration_scan_error_fails_loudly() -> None:
    """A check that cannot run raises ScannerDependencyError after the rest run."""
    ran = MagicMock(return_value=[])
    checks = [
        ("A", ScanSeverity.HIGH, MagicMock(side_effect=PermissionError("denied"))),
        ("B", ScanSeverity.MEDIUM, ran),
    ]
    with patch(f"{SCANS}.CONFIG_CHECKS", checks):
        with pytest.raises(ScannerDependencyError, match="A: denied"):
            await scans._run_configuration_scan("s1", None)
    ran.assert_called_once()


@pytest.mark.asyncio
async def test_compliance_scan_finding_per_failing_control() -> None:
    """Only failing controls produce findings."""
    issue = host_checks.CheckIssue("t", "d", "c", "r", {})
    checks = [("CIS", "1", "x", lambda: [issue, issue]), ("NIST", "2", "y", lambda: [])]
    with patch(f"{SCANS}.COMPLIANCE_CHECKS", checks):
        findings = await scans._run_compliance_scan("s1", None)
    assert [f.metadata["control"] for f in findings] == ["1"]
    assert findings[0].metadata["framework"] == "CIS"


@pytest.mark.asyncio
async def test_compliance_scan_error_fails_loudly() -> None:
    """A control that cannot be evaluated fails the scan."""
    checks = [("CIS", "1", "x", MagicMock(side_effect=OSError("io")))]
    with patch(f"{SCANS}.COMPLIANCE_CHECKS", checks):
        with pytest.raises(ScannerDependencyError, match="compliance"):
            await scans._run_compliance_scan("s1", None)


@pytest.mark.asyncio
async def test_default_check_tables_execute(tmp_path: Path) -> None:
    """The real default check tables run end-to-end against this host."""
    try:
        await scans._run_configuration_scan("s1", None)
        await scans._run_compliance_scan("s1", None)
    except ScannerDependencyError as e:  # unreadable host files: accepted loud outcome
        assert "checks failed" in str(e)


# ---- threat intel ----------------------------------------------------------


class _FakeFeeds:
    """Fake SecurityFeedsManager returning canned matches per (tenant, value)."""

    def __init__(self, db: Any) -> None:
        self.calls: list[tuple[str, str, str]] = []
        _FakeFeeds.instance = self

    instance: "_FakeFeeds"
    hits: dict[tuple[str, str], list[dict[str, Any]]] = {}

    async def check_threat_indicator(
        self, tenant: str, value: str, itype: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Record the call and return configured matches."""
        self.calls.append((tenant, value, itype))
        d = self.hits.get((tenant, value), [])
        return bool(d), d


@pytest.mark.asyncio
async def test_threat_intel_requires_db() -> None:
    """No DB -> loud failure."""
    with pytest.raises(ScannerDependencyError):
        await scans._run_threat_intel_scan("s1", SimpleNamespace(db=None, tenant_id=None))


@pytest.mark.asyncio
async def test_threat_intel_hits_produce_findings(tmp_path: Path) -> None:
    """Indicators in logs are looked up in tenant + global feeds; hits become findings."""
    log = _write(tmp_path / "a.log", "conn from 203.0.113.9 to evil.example.com\nok 198.51.100.1\n")
    _FakeFeeds.hits = {
        ("t1", "203.0.113.9"): [
            {"confidence": 95, "source": "spamhaus", "threat_types": ["botnet"]}
        ],
        (scans.GLOBAL_FEED_TENANT, "evil.example.com"): [{"confidence": 80, "source": "blackweb"}],
    }
    with (
        patch(f"{SCANS}.THREAT_LOG_FILES", [str(log), str(tmp_path / "missing")]),
        patch("hub_api.modules.threatintel.feeds.manager.SecurityFeedsManager", _FakeFeeds),
        patch(f"{SCANS}.THREAT_LOOKUPS") as lookups,
    ):
        findings = await scans._run_threat_intel_scan(
            "s1", SimpleNamespace(db=object(), tenant_id="t1")
        )
    by_value = {f.metadata["indicator"]: f for f in findings}
    assert by_value["203.0.113.9"].severity == ScanSeverity.HIGH
    assert by_value["203.0.113.9"].metadata["threat_types"] == ["botnet"]
    assert by_value["evil.example.com"].severity == ScanSeverity.MEDIUM
    assert len(findings) == 2
    tenants = {c[0] for c in _FakeFeeds.instance.calls}
    assert tenants == {"t1", scans.GLOBAL_FEED_TENANT}
    results = sorted(c.args[1]["result"] for c in lookups.add.call_args_list)
    assert results == ["hit", "hit", "miss"]


@pytest.mark.asyncio
async def test_threat_intel_global_only_without_tenant(tmp_path: Path) -> None:
    """No scanner tenant -> only the global feed tenant is queried."""
    log = _write(tmp_path / "a.log", "198.51.100.1\n")
    _FakeFeeds.hits = {}
    with (
        patch(f"{SCANS}.THREAT_LOG_FILES", [str(log)]),
        patch("hub_api.modules.threatintel.feeds.manager.SecurityFeedsManager", _FakeFeeds),
    ):
        assert (
            await scans._run_threat_intel_scan("s1", SimpleNamespace(db=object(), tenant_id=None))
            == []
        )
    assert {c[0] for c in _FakeFeeds.instance.calls} == {scans.GLOBAL_FEED_TENANT}


@pytest.mark.asyncio
async def test_threat_intel_store_failure_fails_loudly(tmp_path: Path) -> None:
    """A DB error during lookup raises ScannerDependencyError and records an error metric."""
    log = _write(tmp_path / "a.log", "198.51.100.1\n")
    feeds = MagicMock()
    feeds.return_value.check_threat_indicator = AsyncMock(side_effect=RuntimeError("db down"))
    with (
        patch(f"{SCANS}.THREAT_LOG_FILES", [str(log)]),
        patch("hub_api.modules.threatintel.feeds.manager.SecurityFeedsManager", feeds),
        patch(f"{SCANS}.THREAT_LOOKUPS") as lookups,
    ):
        with pytest.raises(ScannerDependencyError, match="db down"):
            await scans._run_threat_intel_scan("s1", SimpleNamespace(db=object(), tenant_id="t"))
    assert lookups.add.call_args.args[1]["result"] == "error"


@pytest.mark.asyncio
async def test_threat_intel_real_manager_against_fake_dal(tmp_path: Path) -> None:
    """Exercise the real SecurityFeedsManager.check_threat_indicator query path."""
    log = _write(tmp_path / "a.log", "198.51.100.7\n")
    row = {
        "value": "198.51.100.7",
        "threat_types": '["c2"]',
        "source": "spamhaus",
        "confidence": 99,
        "first_seen": None,
        "last_seen": None,
        "metadata": None,
    }
    query = MagicMock()
    query.select = AsyncMock(return_value=[row])
    db = MagicMock(return_value=query)
    with patch(f"{SCANS}.THREAT_LOG_FILES", [str(log)]):
        findings = await scans._run_threat_intel_scan("s1", SimpleNamespace(db=db, tenant_id=None))
    assert findings[0].metadata["threat_types"] == ["c2"]
    assert findings[0].confidence == 99


def test_is_ipv4() -> None:
    """Dotted quads are IPv4; hostnames and invalid octets are not."""
    assert scans._is_ipv4("10.0.0.1")
    assert not scans._is_ipv4("example.com")
    assert not scans._is_ipv4("999.1.1.1")


# ---- infra monitor ---------------------------------------------------------


def test_containers_requires_docker() -> None:
    """No Docker client -> loud failure."""
    with pytest.raises(ScannerDependencyError):
        infra_monitor.discover_new_containers(SimpleNamespace(docker_client=None))


def test_containers_listing_failure() -> None:
    """Docker API error -> loud failure."""
    client = MagicMock()
    client.containers.list.side_effect = RuntimeError("socket")
    with pytest.raises(ScannerDependencyError, match="socket"):
        infra_monitor.discover_new_containers(SimpleNamespace(docker_client=client))


def test_containers_reports_only_new() -> None:
    """First cycle reports all; next cycle reports only newly started containers."""
    client = MagicMock()
    s = SimpleNamespace(docker_client=client)
    client.containers.list.return_value = [SimpleNamespace(id="a"), SimpleNamespace(id="b")]
    assert infra_monitor.discover_new_containers(s) == ["a", "b"]
    client.containers.list.return_value = [SimpleNamespace(id="b"), SimpleNamespace(id="c")]
    assert infra_monitor.discover_new_containers(s) == ["c"]


def test_listening_ports_parsing(tmp_path: Path) -> None:
    """Only LISTEN (0A) sockets are returned; ports decoded from hex."""
    hdr = "  sl  local_address rem_address   st\n"
    tcp = _write(
        tmp_path / "tcp",
        hdr + "0: 00000000:0016 00000000:0000 0A\n1: 0100007F:1F90 0100007F:9999 01\nshort\n",
    )
    tcp6 = _write(tmp_path / "tcp6", hdr + "0: 00000000000000000000000000000000:01BB 0 0A\n")
    assert infra_monitor.list_listening_ports((tcp, tcp6, tmp_path / "x")) == {22, 443}


def test_listening_ports_no_source(tmp_path: Path) -> None:
    """No readable /proc source -> loud failure (also via discover)."""
    with pytest.raises(ScannerDependencyError):
        infra_monitor.discover_new_listening_ports(SimpleNamespace(), (tmp_path / "x",))


def test_new_listening_ports(tmp_path: Path) -> None:
    """Second cycle reports only ports that started listening."""
    tcp = _write(tmp_path / "tcp", "h\n0: 00000000:0016 0 0A\n")
    s = SimpleNamespace()
    assert infra_monitor.discover_new_listening_ports(s, (tcp,)) == [22]
    _write(tcp, "h\n0: 00000000:0016 0 0A\n1: 00000000:0050 0 0A\n")
    assert infra_monitor.discover_new_listening_ports(s, (tcp,)) == [80]


def test_report_unimplemented_is_loud() -> None:
    """Unimplemented components emit an error log and an 'unimplemented' metric."""
    with (
        patch.object(infra_monitor, "INFRA_MONITOR_RUNS") as runs,
        patch.object(infra_monitor, "logger") as log,
    ):
        infra_monitor.report_unimplemented("x")
    assert runs.add.call_args.args[1] == {"component": "x", "status": "unimplemented"}
    log.error.assert_called_once()


# ---- core wiring -------------------------------------------------------------


def _scanner() -> SecurityScanner:
    """SecurityScanner with Docker init suppressed and _execute_scan mocked."""
    with patch.dict("sys.modules", {"docker": None}):
        s = SecurityScanner(db=MagicMock(), tenant_id="t")
    s._execute_scan = AsyncMock()  # type: ignore[method-assign]
    return s


@pytest.mark.asyncio
async def test_core_new_containers_trigger_vuln_scan() -> None:
    """New containers trigger a vulnerability scan; none -> no scan."""
    s = _scanner()
    with patch.object(infra_monitor, "discover_new_containers", return_value=["a"]):
        await s._scan_new_containers()
    assert s._execute_scan.call_args.args[0] == ScanType.VULNERABILITY_SCAN
    s._execute_scan.reset_mock()
    with patch.object(infra_monitor, "discover_new_containers", return_value=[]):
        await s._scan_new_containers()
    s._execute_scan.assert_not_called()


@pytest.mark.asyncio
async def test_core_new_ports_trigger_port_scan() -> None:
    """New listening ports trigger a port scan."""
    s = _scanner()
    with patch.object(infra_monitor, "discover_new_listening_ports", return_value=[22]):
        await s._scan_network_services()
    assert s._execute_scan.call_args.args[0] == ScanType.PORT_SCAN


@pytest.mark.asyncio
async def test_core_logs_trigger_threat_scan_and_unimplemented_are_loud() -> None:
    """Log scanning runs the threat-intel scan; undefined components report loudly."""
    s = _scanner()
    await s._scan_logs_for_threats()
    assert s._execute_scan.call_args.args[0] == ScanType.THREAT_INTEL_SCAN
    with patch.object(infra_monitor, "report_unimplemented") as rep:
        await s._scan_kubernetes_resources()
        await s._scan_network_threats()
        await s._correlate_with_threat_feeds()
    assert [c.args[0] for c in rep.call_args_list] == [
        "kubernetes_resources",
        "network_threats",
        "threat_feed_correlation",
    ]
