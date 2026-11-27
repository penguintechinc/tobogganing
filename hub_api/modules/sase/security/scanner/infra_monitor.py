"""Infrastructure change detection for the SASE security scanner.

Detects components that appeared since the previous monitoring cycle (new
Docker containers, new listening TCP ports) so ``SecurityScanner`` can trigger
the matching scan immediately rather than waiting for the cron schedule.
State is kept per scanner instance; the first cycle treats everything as new.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from .telemetry import INFRA_MONITOR_RUNS, ScannerDependencyError

logger = structlog.get_logger()

PROC_NET_TCP = (Path("/proc/net/tcp"), Path("/proc/net/tcp6"))
_TCP_LISTEN_STATE = "0A"


def discover_new_containers(scanner: Any) -> list[str]:
    """Return IDs of running containers not seen in a previous cycle.

    Raises:
        ScannerDependencyError: no Docker client, or the Docker API call fails.
    """
    client = getattr(scanner, "docker_client", None)
    if client is None:
        INFRA_MONITOR_RUNS.add(1, {"component": "containers", "status": "error"})
        raise ScannerDependencyError("container monitoring requires a Docker client")
    try:
        current = {c.id for c in client.containers.list()}
    except Exception as e:
        INFRA_MONITOR_RUNS.add(1, {"component": "containers", "status": "error"})
        raise ScannerDependencyError(f"Docker container listing failed: {e}") from e
    seen: set[str] = getattr(scanner, "_seen_container_ids", set())
    new = sorted(current - seen)
    scanner._seen_container_ids = current
    INFRA_MONITOR_RUNS.add(1, {"component": "containers", "status": "ok"})
    logger.info("infra_monitor_containers", running=len(current), new=len(new))
    return new


def list_listening_ports(sources: tuple[Path, ...] = PROC_NET_TCP) -> set[int]:
    """Parse /proc/net/tcp{,6} and return the set of TCP ports in LISTEN state.

    Raises:
        ScannerDependencyError: none of the sources is readable.
    """
    ports: set[int] = set()
    read_any = False
    for src in sources:
        if not src.exists():
            continue
        read_any = True
        for line in src.read_text().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4 or parts[3] != _TCP_LISTEN_STATE:
                continue
            ports.add(int(parts[1].rsplit(":", 1)[1], 16))
    if not read_any:
        raise ScannerDependencyError("no /proc/net/tcp source available for service discovery")
    return ports


def discover_new_listening_ports(
    scanner: Any, sources: tuple[Path, ...] = PROC_NET_TCP
) -> list[int]:
    """Return listening TCP ports that were not listening in the previous cycle."""
    try:
        current = list_listening_ports(sources)
    except Exception:
        INFRA_MONITOR_RUNS.add(1, {"component": "network_services", "status": "error"})
        raise
    seen: set[int] = getattr(scanner, "_seen_listening_ports", set())
    new = sorted(current - seen)
    scanner._seen_listening_ports = current
    INFRA_MONITOR_RUNS.add(1, {"component": "network_services", "status": "ok"})
    logger.info("infra_monitor_network_services", listening=len(current), new=len(new))
    return new


def report_unimplemented(component: str) -> None:
    """Loudly record that a monitoring component has no defined behaviour yet.

    Used instead of a silent no-op: emits an ERROR log and an ``unimplemented`` metric
    every cycle so dashboards show the gap.
    """
    INFRA_MONITOR_RUNS.add(1, {"component": component, "status": "unimplemented"})
    logger.error("infra_monitor_component_unimplemented", component=component)
