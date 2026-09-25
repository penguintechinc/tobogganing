"""Coverage-focused tests for hub_api.modules.sase.security.scanner.scans.

Exercises execute_scan_by_type's dispatch table and each individual
_run_*_scan implementation's success, tool-missing, and error-handling
branches by mocking subprocess.run / optional third-party imports.
"""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from hub_api.modules.sase.security.scanner.core import ScanType
from hub_api.modules.sase.security.scanner.scans import (
    _run_compliance_scan,
    _run_configuration_scan,
    _run_container_scan,
    _run_dependency_scan,
    _run_port_scan,
    _run_threat_intel_scan,
    _run_vulnerability_scan,
    execute_scan_by_type,
)

SCANS_MOD = "hub_api.modules.sase.security.scanner.scans"


def _fake_scanner(docker_client: object = None) -> SimpleNamespace:
    """Minimal stand-in for SecurityScanner, exposing just what scans.py reads."""
    return SimpleNamespace(docker_client=docker_client)


class TestExecuteScanByType:
    """Covers the dispatch table in execute_scan_by_type."""

    @pytest.mark.asyncio
    async def test_dispatches_each_known_type(self) -> None:
        """Every ScanType member routes to its corresponding _run_* function."""
        expected = {
            ScanType.VULNERABILITY_SCAN: f"{SCANS_MOD}._run_vulnerability_scan",
            ScanType.PORT_SCAN: f"{SCANS_MOD}._run_port_scan",
            ScanType.DEPENDENCY_SCAN: f"{SCANS_MOD}._run_dependency_scan",
            ScanType.CONTAINER_SCAN: f"{SCANS_MOD}._run_container_scan",
            ScanType.CONFIGURATION_SCAN: f"{SCANS_MOD}._run_configuration_scan",
            ScanType.THREAT_INTEL_SCAN: f"{SCANS_MOD}._run_threat_intel_scan",
            ScanType.COMPLIANCE_SCAN: f"{SCANS_MOD}._run_compliance_scan",
        }

        for scan_type, target in expected.items():
            with patch(target, new=AsyncMock(return_value=["marker"])) as mocked:
                result = await execute_scan_by_type(scan_type, "scan-1", _fake_scanner())
                assert result == ["marker"]
                mocked.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_scan_type_returns_empty_list(self) -> None:
        """A scan_type that doesn't match any known ScanType returns []."""
        result = await execute_scan_by_type(None, "scan-1", _fake_scanner())  # type: ignore[arg-type]
        assert result == []


class TestRunVulnerabilityScan:
    """Covers _run_vulnerability_scan's image and filesystem scan paths."""

    @pytest.mark.asyncio
    async def test_no_docker_client_filesystem_scan_succeeds(self) -> None:
        """Without a docker_client, only the filesystem Trivy scan runs."""
        trivy_json = json.dumps(
            {
                "Results": [
                    {
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2024-0001",
                                "Severity": "HIGH",
                                "PkgName": "libfoo",
                            }
                        ]
                    }
                ]
            }
        )
        fake_result = MagicMock(returncode=0, stdout=trivy_json)

        with patch(f"{SCANS_MOD}.subprocess.run", return_value=fake_result):
            findings = await _run_vulnerability_scan("scan-1", _fake_scanner())

        assert len(findings) == 1
        assert findings[0].finding_type == "vulnerability"

    @pytest.mark.asyncio
    async def test_filesystem_scan_timeout_is_swallowed(self) -> None:
        """A Trivy timeout on the filesystem scan is caught and yields no findings."""
        with patch(
            f"{SCANS_MOD}.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="trivy", timeout=600),
        ):
            findings = await _run_vulnerability_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_filesystem_scan_unexpected_exception_is_swallowed(self) -> None:
        """A non-timeout, non-JSON exception during the filesystem scan is swallowed."""
        with patch(f"{SCANS_MOD}.subprocess.run", side_effect=RuntimeError("boom")):
            findings = await _run_vulnerability_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_docker_client_scans_images_then_filesystem(self) -> None:
        """With a docker_client, up to 5 images are scanned before the filesystem."""
        image1 = MagicMock(id="sha256:image1")
        image2 = MagicMock(id="sha256:image2")
        image3 = MagicMock(id="sha256:image3")
        docker_client = MagicMock()
        docker_client.images.list.return_value = [image1, image2, image3]

        good_json = json.dumps({"Results": []})
        image1_result = MagicMock(returncode=0, stdout=good_json)
        fs_result = MagicMock(returncode=0, stdout=good_json)

        with patch(
            f"{SCANS_MOD}.subprocess.run",
            side_effect=[
                image1_result,
                subprocess.TimeoutExpired(cmd="trivy", timeout=300),  # image2 times out
                RuntimeError("unexpected image scan failure"),  # image3 hits generic except
                fs_result,
            ],
        ):
            findings = await _run_vulnerability_scan(
                "scan-1", _fake_scanner(docker_client=docker_client)
            )

        assert findings == []  # empty Results in every mocked response

    @pytest.mark.asyncio
    async def test_outer_exception_from_docker_client_access_is_swallowed(self) -> None:
        """A raise while merely accessing docker_client hits the outer except."""

        class RaisingScanner:
            @property
            def docker_client(self) -> object:
                raise RuntimeError("docker client broken")

        findings = await _run_vulnerability_scan("scan-1", RaisingScanner())

        assert findings == []


class TestRunPortScan:
    """Covers _run_port_scan's optional nmap dependency and scan loop."""

    @pytest.mark.asyncio
    async def test_nmap_not_installed_returns_empty(self) -> None:
        """If the nmap module cannot be imported, the scan returns no findings."""
        with patch.dict(sys.modules, {"nmap": None}):
            findings = await _run_port_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_nmap_finds_risky_open_port_on_remote_host(self) -> None:
        """An open port 22/3306/6379 on a non-localhost host produces a finding."""

        class FakeHostEntry(dict):
            """dict subclass so nm[host][proto] indexing AND .all_protocols() both work."""

            def all_protocols(self) -> list[str]:
                return list(self.keys())

        fake_nmap_module = MagicMock()
        fake_scanner_instance = MagicMock()
        fake_nmap_module.PortScanner.return_value = fake_scanner_instance

        fake_scanner_instance.all_hosts.return_value = ["10.0.0.5"]
        host_entry = FakeHostEntry({"tcp": {22: {"state": "open", "name": "ssh"}}})
        fake_scanner_instance.__getitem__.return_value = host_entry

        with patch.dict(sys.modules, {"nmap": fake_nmap_module}):
            findings = await _run_port_scan("scan-1", _fake_scanner())

        assert len(findings) == 1
        assert findings[0].finding_type == "open_port"
        assert findings[0].metadata["port"] == 22

    @pytest.mark.asyncio
    async def test_nmap_scan_exception_is_swallowed(self) -> None:
        """An exception raised during the nmap scan is caught, returning no findings."""
        fake_nmap_module = MagicMock()
        fake_scanner_instance = MagicMock()
        fake_nmap_module.PortScanner.return_value = fake_scanner_instance
        fake_scanner_instance.scan.side_effect = RuntimeError("nmap crashed")

        with patch.dict(sys.modules, {"nmap": fake_nmap_module}):
            findings = await _run_port_scan("scan-1", _fake_scanner())

        assert findings == []


class TestRunDependencyScan:
    """Covers _run_dependency_scan's safety + govulncheck paths."""

    @pytest.mark.asyncio
    async def test_safety_check_success(self) -> None:
        """A successful safety-check JSON output is parsed into findings."""
        safety_json = json.dumps([{"package": "reqs", "advisory": "vuln", "cve": "CVE-2024-0002"}])
        fake_result = MagicMock(stdout=safety_json)

        with (
            patch(f"{SCANS_MOD}.subprocess.run", return_value=fake_result),
            patch(f"{SCANS_MOD}.Path.exists", return_value=False),
        ):
            findings = await _run_dependency_scan("scan-1", _fake_scanner())

        assert len(findings) == 1
        assert findings[0].finding_type == "dependency_vulnerability"

    @pytest.mark.asyncio
    async def test_safety_check_timeout_is_swallowed(self) -> None:
        """A safety-check timeout is caught without raising."""
        with (
            patch(
                f"{SCANS_MOD}.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="safety", timeout=120),
            ),
            patch(f"{SCANS_MOD}.Path.exists", return_value=False),
        ):
            findings = await _run_dependency_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_safety_check_unexpected_exception_is_swallowed(self) -> None:
        """A non-timeout exception from safety-check is caught."""
        with (
            patch(f"{SCANS_MOD}.subprocess.run", side_effect=RuntimeError("boom")),
            patch(f"{SCANS_MOD}.Path.exists", return_value=False),
        ):
            findings = await _run_dependency_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_govulncheck_runs_when_go_mod_present(self) -> None:
        """When /go.mod exists, govulncheck is invoked and its output parsed."""
        safety_result = MagicMock(stdout="")
        govulncheck_result = MagicMock(stdout="Vulnerability found: GO-2024-0001")

        with (
            patch(
                f"{SCANS_MOD}.subprocess.run",
                side_effect=[safety_result, govulncheck_result],
            ),
            patch(f"{SCANS_MOD}.Path.exists", return_value=True),
        ):
            findings = await _run_dependency_scan("scan-1", _fake_scanner())

        assert any(f.finding_type == "go_dependency_vulnerability" for f in findings)

    @pytest.mark.asyncio
    async def test_govulncheck_timeout_is_swallowed(self) -> None:
        """A govulncheck timeout/FileNotFoundError is caught without raising."""
        safety_result = MagicMock(stdout="")

        with (
            patch(
                f"{SCANS_MOD}.subprocess.run",
                side_effect=[
                    safety_result,
                    subprocess.TimeoutExpired(cmd="govulncheck", timeout=120),
                ],
            ),
            patch(f"{SCANS_MOD}.Path.exists", return_value=True),
        ):
            findings = await _run_dependency_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_govulncheck_unexpected_exception_is_swallowed(self) -> None:
        """A non-timeout exception from govulncheck is caught."""
        safety_result = MagicMock(stdout="")

        with (
            patch(
                f"{SCANS_MOD}.subprocess.run",
                side_effect=[safety_result, RuntimeError("boom")],
            ),
            patch(f"{SCANS_MOD}.Path.exists", return_value=True),
        ):
            findings = await _run_dependency_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_outer_exception_is_swallowed(self) -> None:
        """A failure constructing the go.mod Path hits the outer except handler."""
        with patch(f"{SCANS_MOD}.Path", side_effect=RuntimeError("boom")):
            findings = await _run_dependency_scan("scan-1", _fake_scanner())

        assert findings == []


class TestRunContainerScan:
    """Covers _run_container_scan's docker-bench-security invocation."""

    @pytest.mark.asyncio
    async def test_docker_bench_success(self) -> None:
        """Docker Bench output is parsed into findings."""
        bench_output = "[WARN] 1.1.1 Check warning\n[FAIL] 2.1.1 Check failure"
        fake_result = MagicMock(stdout=bench_output)

        with patch(f"{SCANS_MOD}.subprocess.run", return_value=fake_result):
            findings = await _run_container_scan("scan-1", _fake_scanner())

        assert len(findings) == 2

    @pytest.mark.asyncio
    async def test_docker_bench_timeout_is_swallowed(self) -> None:
        """A Docker Bench timeout/FileNotFoundError is caught without raising."""
        with patch(
            f"{SCANS_MOD}.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=300),
        ):
            findings = await _run_container_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_docker_bench_unexpected_exception_is_swallowed(self) -> None:
        """A non-timeout exception from docker-bench is caught."""
        with patch(f"{SCANS_MOD}.subprocess.run", side_effect=RuntimeError("boom")):
            findings = await _run_container_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_outer_exception_handler_via_logging_failure(self) -> None:
        """A failure inside the inner except handler itself hits the outer except."""
        with (
            patch(
                f"{SCANS_MOD}.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=300),
            ),
            patch(f"{SCANS_MOD}.logger.warning", side_effect=RuntimeError("log broke")),
        ):
            findings = await _run_container_scan("scan-1", _fake_scanner())

        assert findings == []


class TestRunConfigurationScan:
    """Covers _run_configuration_scan's placeholder check loop."""

    @pytest.mark.asyncio
    async def test_configuration_checks_run_without_findings(self) -> None:
        """The placeholder checks execute for every configured check (no findings yet)."""
        findings = await _run_configuration_scan("scan-1", _fake_scanner())

        assert findings == []  # `result` is always None in the current placeholder


class TestRunThreatIntelScan:
    """Covers _run_threat_intel_scan's log-file reading loop."""

    @pytest.mark.asyncio
    async def test_reads_existing_log_files_and_extracts_indicators(self) -> None:
        """Existing log files are read and scanned for IPs/domains."""
        log_content = "Connection from 192.168.1.1 to example.com\n"

        with (
            patch(f"{SCANS_MOD}.os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=log_content)),
        ):
            findings = await _run_threat_intel_scan("scan-1", _fake_scanner())

        assert findings == []  # threat-feed lookup is a placeholder (no findings yet)

    @pytest.mark.asyncio
    async def test_missing_log_files_are_skipped(self) -> None:
        """Nonexistent log files are skipped entirely."""
        with patch(f"{SCANS_MOD}.os.path.exists", return_value=False):
            findings = await _run_threat_intel_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_log_file_read_exception_is_swallowed(self) -> None:
        """An exception while reading a log file is caught per-file."""
        with (
            patch(f"{SCANS_MOD}.os.path.exists", return_value=True),
            patch("builtins.open", side_effect=OSError("permission denied")),
        ):
            findings = await _run_threat_intel_scan("scan-1", _fake_scanner())

        assert findings == []

    @pytest.mark.asyncio
    async def test_outer_exception_is_swallowed(self) -> None:
        """A failure enumerating log files hits the outer except handler."""
        with patch(f"{SCANS_MOD}.os.path.exists", side_effect=RuntimeError("boom")):
            findings = await _run_threat_intel_scan("scan-1", _fake_scanner())

        assert findings == []


class TestRunComplianceScan:
    """Covers _run_compliance_scan's placeholder check loop."""

    @pytest.mark.asyncio
    async def test_compliance_checks_produce_a_finding_per_control(self) -> None:
        """Each placeholder compliance control produces one finding."""
        findings = await _run_compliance_scan("scan-1", _fake_scanner())

        assert len(findings) == 3
        assert all(f.finding_type == "compliance" for f in findings)
