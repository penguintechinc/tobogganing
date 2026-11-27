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


class _Cond:
    """Conjunction of DAL-style conditions evaluated against dict rows."""

    def __init__(self, preds: list[Any]) -> None:
        self.preds = preds

    def __and__(self, other: "_Cond") -> "_Cond":
        return _Cond(self.preds + other.preds)

    def __call__(self, row: dict[str, Any]) -> bool:
        return all(p(row) for p in self.preds)


class _Field:
    """DAL-style field supporting ``==`` and ``belongs``."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> _Cond:  # type: ignore[override]
        return _Cond([lambda r: r[self.name] == other])

    def __hash__(self) -> int:
        return hash(self.name)

    def belongs(self, values: list[str]) -> _Cond:
        vs = set(values)
        return _Cond([lambda r: r[self.name] in vs])


class _FakeDAL:
    """Minimal penguin-dal stand-in over an in-memory threat_indicators table."""

    def __init__(self, rows: list[dict[str, Any]], fail: bool = False) -> None:
        self.rows = rows
        self.fail = fail
        self.queries = 0
        self.threat_indicators = SimpleNamespace(
            **{n: _Field(n) for n in ("value", "active", "tenant_id", "indicator_type")}
        )

    def __call__(self, cond: _Cond) -> Any:
        dal = self

        async def select() -> list[dict[str, Any]]:
            dal.queries += 1
            if dal.fail:
                raise RuntimeError("db down")
            return [r for r in dal.rows if cond(r)]

        return SimpleNamespace(select=select)


def _row(value: str, itype: str, tenant: str, conf: int = 80, src: str = "feed") -> dict[str, Any]:
    """Build an active threat_indicators row."""
    return {
        "value": value,
        "indicator_type": itype,
        "tenant_id": tenant,
        "active": True,
        "threat_types": '["c2"]',
        "source": src,
        "confidence": conf,
    }


async def _scan(tmp_path: Path, text: str, dal: Any, tenant: str | None = "t1") -> list[Any]:
    """Run the threat-intel scan over one temp log file."""
    log = _write(tmp_path / "a.log", text)
    with patch(f"{SCANS}.THREAT_LOG_FILES", [str(log), str(tmp_path / "missing")]):
        return await scans._run_threat_intel_scan("s1", SimpleNamespace(db=dal, tenant_id=tenant))


@pytest.mark.asyncio
async def test_threat_intel_requires_db() -> None:
    """No DB -> loud failure."""
    with pytest.raises(ScannerDependencyError):
        await scans._run_threat_intel_scan("s1", SimpleNamespace(db=None, tenant_id=None))


@pytest.mark.asyncio
async def test_threat_intel_hits_tenant_and_global(tmp_path: Path) -> None:
    """Tenant and global-feed hits become findings; other tenants never match."""
    g = scans.GLOBAL_FEED_TENANT
    dal = _FakeDAL(
        [
            _row("203.0.113.9", "ip", "t1", 95, "spamhaus"),
            _row("evil.example.com", "domain", g, 80, "blackweb"),
            _row("198.51.100.1", "ip", "other-tenant", 99),
        ]
    )
    with patch(f"{SCANS}.THREAT_LOOKUPS") as lookups:
        findings = await _scan(
            tmp_path, "from 203.0.113.9 to evil.example.com\nok 198.51.100.1\n", dal
        )
    by = {f.metadata["indicator"]: f for f in findings}
    assert set(by) == {"203.0.113.9", "evil.example.com"}
    assert by["203.0.113.9"].severity == ScanSeverity.HIGH
    assert by["evil.example.com"].severity == ScanSeverity.MEDIUM
    assert sorted(c.args[1]["result"] for c in lookups.add.call_args_list) == [
        "hit",
        "hit",
        "miss",
    ]


@pytest.mark.asyncio
async def test_threat_intel_normalization_and_parent_match(tmp_path: Path) -> None:
    """Mixed-case, trailing-dot, IDN and subdomain indicators match canonical feed rows."""
    g = scans.GLOBAL_FEED_TENANT
    idn = "bücher.example".encode("idna").decode()
    dal = _FakeDAL(
        [
            _row("evil.com", "domain", g),
            _row("malware.org", "domain", g),
            _row(idn, "domain", g),
        ]
    )
    findings = await _scan(
        tmp_path,
        "a A.B.Evil.COM. b\nMALWARE.ORG. x\nget bücher.example\n",
        dal,
        tenant=None,
    )
    vals = {f.metadata["indicator"]: f.metadata["matched_values"] for f in findings}
    assert vals == {
        "a.b.evil.com": ["evil.com"],
        "malware.org": ["malware.org"],
        idn: [idn],
    }


def test_normalizers() -> None:
    """IPs canonicalized (non-canonical forms fixed, invalid skipped); domains IDNA'd."""
    assert scans._normalize_ip("2001:DB8:0:0::1") == "2001:db8::1"
    assert scans._normalize_ip(" 10.0.0.1 ") == "10.0.0.1"
    assert scans._normalize_ip("999.1.1.1") is None
    assert scans._normalize_domain("Ex.COM.") == "ex.com"
    assert scans._normalize_domain(".") is None
    assert scans._normalize_domain("a" * 70 + ".com") is None  # label too long for IDNA
    deep = scans._domain_candidates("a.b.c.d.e.f.g.h.com")
    assert deep[0] == "a.b.c.d.e.f.g.h.com"  # exact name always kept
    assert deep[-1] == "h.com"  # registrable end always kept
    assert len(deep) == scans.MAX_PARENT_DEPTH + 1
    assert scans._domain_candidates("evil.com") == ["evil.com"]


@pytest.mark.asyncio
async def test_threat_intel_deep_subdomain_matches_feed_domain(tmp_path: Path) -> None:
    """a.b.c.d.e.f.evil.com matches an evil.com feed entry despite the depth bound."""
    dal = _FakeDAL([_row("evil.com", "domain", scans.GLOBAL_FEED_TENANT)])
    findings = await _scan(tmp_path, "GET a.b.c.d.e.f.g.evil.com\n", dal, tenant=None)
    assert findings[0].metadata["matched_values"] == ["evil.com"]


def test_collect_indicators_newest_first() -> None:
    """Indicators are ordered from the most recent log line backwards."""
    got = scans._collect_indicators(["10.0.0.1", "10.0.0.2 x.example.com", "10.0.0.1"])
    assert got == [("10.0.0.1", "ip"), ("10.0.0.2", "ip"), ("x.example.com", "domain")]


def test_allocate_fairly_across_files() -> None:
    """A padded file cannot crowd out others; duplicates across files count once."""
    a = [(f"10.0.0.{i}", "ip") for i in range(100)]
    b = [("10.9.9.9", "ip"), ("10.0.0.0", "ip")]
    kept, dropped = scans._allocate_fairly({"a": a, "b": b}, 6)
    assert ("10.9.9.9", "ip") in kept and kept[("10.9.9.9", "ip")] == "b"
    assert len(kept) == 6 and dropped == 95
    kept, dropped = scans._allocate_fairly({"a": a[:2], "b": b}, 10)
    assert dropped == 0 and len(kept) == 3
    b3 = [("10.7.0.1", "ip"), ("10.7.0.2", "ip"), ("10.7.0.3", "ip")]
    kept, _ = scans._allocate_fairly({"a": a, "b": b3}, 5)  # cap hit mid-round
    assert len(kept) == 5


@pytest.mark.asyncio
async def test_threat_intel_ipv6_non_canonical(tmp_path: Path) -> None:
    """A feed IPv6 row matches regardless of extraction (IPv4 regex only); IPv4 canonical."""
    dal = _FakeDAL([_row("192.0.2.5", "ip", scans.GLOBAL_FEED_TENANT)])
    findings = await _scan(tmp_path, "src=192.0.2.5 bad=300.1.1.1\n", dal, tenant=None)
    assert [f.metadata["indicator"] for f in findings] == ["192.0.2.5"]


@pytest.mark.asyncio
async def test_threat_intel_batches_queries(tmp_path: Path) -> None:
    """Lookups are one IN-query per chunk per indicator type, not one per indicator."""
    dal = _FakeDAL([])
    text = "".join(f"10.0.{i // 250}.{i % 250} host{i}.example.com\n" for i in range(600))
    with patch(f"{SCANS}.LOOKUP_BATCH_SIZE", 500):
        assert await _scan(tmp_path, text, dal) == []
    # 600 IPs -> 2 chunks; 600 hosts + parent example.com = 601 domains -> 2 chunks
    assert dal.queries == 4


@pytest.mark.asyncio
async def test_threat_intel_caps_indicators_loudly(tmp_path: Path) -> None:
    """Over-cap: newest indicators kept; warning, metric and a coverage finding emitted."""
    dal = _FakeDAL([_row("10.1.0.19", "ip", scans.GLOBAL_FEED_TENANT)])
    text = "".join(f"10.1.0.{i}\n" for i in range(20))
    with (
        patch(f"{SCANS}.MAX_INDICATORS_PER_SCAN", 5),
        patch(f"{SCANS}.INDICATORS_TRUNCATED") as trunc,
        patch(f"{SCANS}.THREAT_LOOKUPS") as lookups,
        patch(f"{SCANS}.logger") as log,
    ):
        findings = await _scan(tmp_path, text, dal)
    trunc.add.assert_called_once_with(15)
    assert lookups.add.call_count == 5
    warnings = [c.args[0] for c in log.warning.call_args_list]
    assert "threat_intel_indicators_truncated" in warnings
    cov = [f for f in findings if f.finding_type == "threat_intel_coverage"]
    assert len(cov) == 1 and cov[0].severity == ScanSeverity.MEDIUM
    assert cov[0].metadata == {"observed": 20, "dropped": 15, "limit": 5}
    # newest line (10.1.0.19) survived the cap and was matched
    assert [f.metadata["indicator"] for f in findings if f.finding_type != cov[0].finding_type] == [
        "10.1.0.19"
    ]


def test_cap_exceeds_tail_yield() -> None:
    """The cap comfortably exceeds the indicators 3 x 256KB tails can produce."""
    assert scans.MAX_INDICATORS_PER_SCAN >= 3 * scans.LOG_TAIL_BYTES // 7


def test_read_tail_is_bounded(tmp_path: Path) -> None:
    """Only the last max_bytes are read and a leading partial line is dropped."""
    p = _write(tmp_path / "big.log", "".join(f"line-{i:04d}\n" for i in range(1000)))
    lines = scans._read_tail(str(p), max_bytes=35)
    assert lines == ["line-0997", "line-0998", "line-0999"]
    assert len(scans._read_tail(str(p))) == 1000


@pytest.mark.asyncio
async def test_threat_intel_store_failure_fails_loudly(tmp_path: Path) -> None:
    """A DB error raises ScannerDependencyError and records an error metric."""
    with patch(f"{SCANS}.THREAT_LOOKUPS") as lookups:
        with pytest.raises(ScannerDependencyError, match="db down"):
            await _scan(tmp_path, "198.51.100.1\n", _FakeDAL([], fail=True))
    assert lookups.add.call_args.args[1]["result"] == "error"


def test_row_to_match_bad_types_json() -> None:
    """Malformed threat_types JSON degrades to an empty list; non-dict rows supported."""

    class _R:
        def __getitem__(self, k: str) -> Any:
            return {"value": "v", "source": "s", "confidence": 1, "threat_types": "{bad"}[k]

    assert scans._row_to_match(_R())["threat_types"] == []


@pytest.mark.asyncio
async def test_batch_lookup_empty() -> None:
    """No values -> no query."""
    dal = _FakeDAL([])
    assert await scans._batch_lookup(dal, ["t"], [], "ip") == {}
    assert dal.queries == 0


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
