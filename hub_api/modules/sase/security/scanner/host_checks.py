"""Host configuration and compliance checks used by the SASE scanner.

Each check reads real host state (sshd_config, file modes, /proc, /etc/passwd)
and returns a list of issues. A missing subsystem raises ``CheckNotApplicable``;
any other read failure propagates so the caller can fail the scan loudly.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SSHD_CONFIG = Path("/etc/ssh/sshd_config")
SHADOW = Path("/etc/shadow")
PASSWD = Path("/etc/passwd")
GROUP = Path("/etc/group")
DOCKER_SOCK = Path("/var/run/docker.sock")
PROC_MODULES = Path("/proc/modules")
PROC_FILESYSTEMS = Path("/proc/filesystems")
MODPROBE_DIR = Path("/etc/modprobe.d")


class CheckNotApplicable(Exception):
    """The subsystem a check inspects is not present on this host."""


@dataclass(slots=True)
class CheckIssue:
    """One problem detected by a host check."""

    title: str
    description: str
    component: str
    recommendation: str
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_sshd_config(path: Path = SSHD_CONFIG) -> dict[str, str]:
    """Return effective global sshd options (lower-cased keys, first value wins).

    Parsing stops at the first ``Match`` block, mirroring sshd's global scope.
    Raises CheckNotApplicable when sshd is not installed.
    """
    if not path.exists():
        raise CheckNotApplicable(f"{path} not present")
    options: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        key = parts[0].lower()
        if key == "match":
            break
        value = parts[1].strip().lower() if len(parts) > 1 else ""
        options.setdefault(key, value)
    return options


def check_ssh_configuration(path: Path = SSHD_CONFIG) -> list[CheckIssue]:
    """Flag insecure sshd settings (root login, password auth, empty passwords, protocol 1).

    OpenSSH defaults are applied for unset keys (PasswordAuthentication defaults to yes).
    """
    opts = parse_sshd_config(path)
    issues: list[CheckIssue] = []
    rules = [
        (
            "permitrootlogin",
            "prohibit-password",
            {"yes"},
            "Root login over SSH is permitted",
            "Set 'PermitRootLogin no'",
        ),
        (
            "passwordauthentication",
            "yes",
            {"yes"},
            "SSH password authentication is enabled",
            "Set 'PasswordAuthentication no' and use key-based auth",
        ),
        (
            "permitemptypasswords",
            "no",
            {"yes"},
            "SSH permits empty passwords",
            "Set 'PermitEmptyPasswords no'",
        ),
        ("protocol", "2", {"1", "1,2", "2,1"}, "SSH protocol 1 is enabled", "Set 'Protocol 2'"),
    ]
    for key, default, bad, title, rec in rules:
        value = opts.get(key, default)
        if value in bad:
            issues.append(
                CheckIssue(
                    title,
                    f"{key}={value} in {path}",
                    str(path),
                    rec,
                    {"option": key, "value": value},
                )
            )
    return issues


def _mode_issue(path: Path, mask: int, what: str) -> CheckIssue | None:
    """Return an issue when ``path`` has any of the ``mask`` permission bits set."""
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & mask:
        return CheckIssue(
            f"{path} is {what}",
            f"{path} has mode {oct(mode)}",
            str(path),
            f"chmod o-rwx {path}",
            {"mode": oct(mode)},
        )
    return None


def check_file_permissions(
    shadow: Path = SHADOW, passwd: Path = PASSWD, group: Path = GROUP
) -> list[CheckIssue]:
    """Flag world-readable/writable /etc/shadow and world-writable /etc/passwd, /etc/group."""
    targets = [
        (shadow, stat.S_IROTH | stat.S_IWOTH, "world-accessible"),
        (passwd, stat.S_IWOTH, "world-writable"),
        (group, stat.S_IWOTH, "world-writable"),
    ]
    present = [t for t in targets if t[0].exists()]
    if not present:
        raise CheckNotApplicable("no account files present")
    return [i for p, m, w in present if (i := _mode_issue(p, m, w)) is not None]


def check_service_configuration(docker_sock: Path = DOCKER_SOCK) -> list[CheckIssue]:
    """Flag a world-writable Docker daemon socket (equivalent to host root access)."""
    if not docker_sock.exists():
        raise CheckNotApplicable(f"{docker_sock} not present")
    issue = _mode_issue(docker_sock, stat.S_IWOTH, "world-writable (host root equivalent)")
    return [issue] if issue else []


def check_cis_freevxfs_disabled(
    modules: Path = PROC_MODULES, modprobe_dir: Path = MODPROBE_DIR
) -> list[CheckIssue]:
    """CIS 1.1.1.1: freevxfs must not be loaded and must be install-disabled in modprobe.d."""
    loaded = any(
        line.split()[0] == "freevxfs" for line in modules.read_text().splitlines() if line.strip()
    )
    disabled = False
    if modprobe_dir.is_dir():
        for conf in sorted(modprobe_dir.glob("*.conf")):
            for line in conf.read_text().splitlines():
                parts = line.split()
                if (
                    len(parts) >= 3
                    and parts[:2] == ["install", "freevxfs"]
                    and parts[2] in ("/bin/true", "/bin/false", "/usr/bin/true", "/usr/bin/false")
                ):
                    disabled = True
    if loaded or not disabled:
        return [
            CheckIssue(
                "freevxfs filesystem module not disabled",
                f"loaded={loaded}, install-disabled={disabled}",
                "kernel-modules",
                "Add 'install freevxfs /bin/false' to /etc/modprobe.d and rmmod freevxfs",
                {"loaded": loaded, "install_disabled": disabled},
            )
        ]
    return []


def check_nist_ac2_accounts(passwd: Path = PASSWD) -> list[CheckIssue]:
    """NIST AC-2: no non-root UID-0 accounts and no accounts with an empty password field."""
    issues: list[CheckIssue] = []
    for line in passwd.read_text().splitlines():
        fields = line.split(":")
        if len(fields) < 4 or line.startswith("#"):
            continue
        name, pw, uid = fields[0], fields[1], fields[2]
        if uid == "0" and name != "root":
            issues.append(
                CheckIssue(
                    "Non-root account with UID 0",
                    f"account '{name}' has UID 0",
                    str(passwd),
                    "Remove or re-number the account",
                    {"account": name},
                )
            )
        if pw == "":
            issues.append(
                CheckIssue(
                    "Account without password",
                    f"account '{name}' has an empty password field",
                    str(passwd),
                    "Lock the account or set a password",
                    {"account": name},
                )
            )
    return issues


def check_soc2_cc61_logical_access(path: Path = SSHD_CONFIG) -> list[CheckIssue]:
    """SOC2 CC6.1 (logical access): remote root login and empty passwords must be denied."""
    return [
        i
        for i in check_ssh_configuration(path)
        if i.metadata.get("option") in ("permitrootlogin", "permitemptypasswords")
    ]
