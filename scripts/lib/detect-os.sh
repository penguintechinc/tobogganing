#!/usr/bin/env bash
# detect-os.sh — Shared OS/arch detection library
#
# Source this file; do not execute it directly.
# Usage:  source "$(dirname "${BASH_SOURCE[0]}")/lib/detect-os.sh"
#
# Exports after sourcing:
#   OS            — macos | ubuntu | debian | fedora | ...
#   OS_VERSION    — version string (e.g. "24.04", "14.5")
#   PKG_MANAGER   — brew | apt | dnf | yum
#   ARCH          — amd64 | arm64
#   GOOS          — darwin | linux  (matches Go/tool naming)
#   SHELL_RC      — absolute path to user shell RC file
#   PIP_FLAGS     — pip install flags appropriate for the OS
#
# Helper functions (available after sourcing):
#   is_macos()      — returns 0 if macOS
#   is_linux()      — returns 0 if Linux
#   is_wsl2()       — returns 0 if inside WSL2
#   sha256check()   — portable SHA256 verification
#   http_get()      — portable file download (curl-based)

# ── OS + package manager ──────────────────────────────────────────────────────

detect_os() {
    local kernel
    kernel="$(uname -s)"

    case "$kernel" in
        Darwin)
            OS="macos"
            OS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
            PKG_MANAGER="brew"
            GOOS="darwin"
            ;;
        Linux)
            if [[ -f /etc/os-release ]]; then
                # shellcheck source=/dev/null
                . /etc/os-release
                OS="${ID:-linux}"
                OS_VERSION="${VERSION_ID:-unknown}"
            else
                OS="linux"
                OS_VERSION="unknown"
            fi
            GOOS="linux"

            if command -v apt-get &>/dev/null; then
                PKG_MANAGER="apt"
            elif command -v dnf &>/dev/null; then
                PKG_MANAGER="dnf"
            elif command -v yum &>/dev/null; then
                PKG_MANAGER="yum"
            else
                echo "[detect-os] ERROR: No supported package manager found (apt/dnf/yum)" >&2
                return 1
            fi
            ;;
        *)
            echo "[detect-os] ERROR: Unsupported kernel: $kernel" >&2
            return 1
            ;;
    esac

    export OS OS_VERSION PKG_MANAGER GOOS
}

# ── CPU architecture ──────────────────────────────────────────────────────────

detect_arch() {
    case "$(uname -m)" in
        x86_64)        ARCH="amd64" ;;
        aarch64|arm64) ARCH="arm64" ;;
        *)
            echo "[detect-os] ERROR: Unsupported architecture: $(uname -m)" >&2
            return 1
            ;;
    esac
    export ARCH
}

# ── Shell RC file ─────────────────────────────────────────────────────────────

detect_shell_rc() {
    if [[ "$GOOS" == "darwin" ]]; then
        # macOS defaults to zsh since Catalina
        SHELL_RC="$HOME/.zshrc"
    else
        SHELL_RC="$HOME/.bashrc"
    fi
    export SHELL_RC
}

# ── pip install flags ─────────────────────────────────────────────────────────

detect_pip_flags() {
    # Both macOS (Homebrew Python 3.12+) and Ubuntu 22.04+ enforce PEP 668
    PIP_FLAGS="--break-system-packages --user"
    export PIP_FLAGS
}

# ── Helper: portable SHA256 checksum verification ────────────────────────────
#
# Usage: sha256check <archive_file> <checksums_file>
# Returns 0 on match, 1 on mismatch.

sha256check() {
    local archive="$1" checksums="$2"
    local basename
    basename="$(basename "$archive")"

    # Exact-filename match on the last whitespace-separated field, stripping any
    # leading "*" (binary-mode checksum files, e.g. hadolint's checksums.sha256).
    # A plain substring grep is unsafe: some releases (e.g. golangci-lint) also list
    # derived files like "<name>.tar.gz.sbom.json" whose name is a superstring of the
    # binary's, so a substring match pulls in extra lines sha256sum can't find locally.
    local line
    line="$(awk -v f="$basename" '{n=$NF; sub(/^\*/, "", n); if (n == f) print}' "$checksums" 2>/dev/null || true)"

    # On macOS, always prefer shasum — sha256sum may exist (e.g. from coreutils) but
    # the BSD variant doesn't accept GNU flags (--check, --status).
    if [[ "$GOOS" == "darwin" ]]; then
        if ! command -v shasum &>/dev/null; then
            echo "[detect-os] ERROR: shasum not found on macOS" >&2
            return 1
        fi
        if [[ -z "$line" ]]; then
            # Bare-hash format (e.g. hadolint): single hash on first line, no filename
            local hash
            hash="$(head -1 "$checksums" | awk '{print $1}')"
            [[ -z "$hash" ]] && return 1
            echo "${hash}  ${basename}" | ( cd "$(dirname "$archive")" && shasum -a 256 -c --status )
        else
            ( cd "$(dirname "$archive")" && echo "$line" | shasum -a 256 -c --status )
        fi
    elif command -v sha256sum &>/dev/null; then
        if [[ -z "$line" ]]; then
            # Bare-hash format: single hash on first line, no filename
            local hash
            hash="$(head -1 "$checksums" | awk '{print $1}')"
            [[ -z "$hash" ]] && return 1
            echo "${hash}  ${basename}" | ( cd "$(dirname "$archive")" && sha256sum --check --status )
        else
            ( cd "$(dirname "$archive")" && echo "$line" | sha256sum --check --status )
        fi
    else
        echo "[detect-os] ERROR: No sha256sum or shasum found" >&2
        return 1
    fi
}

export -f sha256check

# ── Helper: portable file download ───────────────────────────────────────────
#
# Usage: http_get <url> <output_file>

http_get() {
    local url="$1" out="$2"
    curl -fsSL --retry 2 "$url" -o "$out"
}

export -f http_get

# ── Helper predicates ─────────────────────────────────────────────────────────

is_macos() { [[ "$GOOS" == "darwin" ]]; }
is_linux() { [[ "$GOOS" == "linux" ]]; }
is_wsl2()  { grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; }

export -f is_macos is_linux is_wsl2

# ── Run detection on source ───────────────────────────────────────────────────

detect_os
detect_arch
detect_shell_rc
detect_pip_flags
