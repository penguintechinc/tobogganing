#!/usr/bin/env bash
# =============================================================================
# install-pre-commit.sh — Install the pre-commit framework and wire up hooks
#
# Installs pre-commit system-wide (macOS, Ubuntu/Debian, WSL, Fedora/RHEL) and
# registers both hook types in the current repo:
#   pre-commit — fast lint + secrets checks
#   pre-push   — heavier security scans
#
# Usage:
#   ./install-pre-commit.sh              # Install framework + hooks
#   ./install-pre-commit.sh --hooks-only # Skip the framework install
#   ./install-pre-commit.sh --verify     # Report state, change nothing
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/detect-os.sh
source "$SCRIPT_DIR/lib/detect-os.sh"
detect_os

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR]${NC}   $*" >&2; exit 1; }

install_framework() {
    if command -v pre-commit >/dev/null 2>&1; then
        ok "pre-commit already installed ($(pre-commit --version))"
        return
    fi

    info "Installing pre-commit via $PKG_MANAGER..."
    case "$PKG_MANAGER" in
        brew)
            brew install pre-commit
            ;;
        apt)
            # Same path for native Ubuntu/Debian and WSL — no WSL special-casing needed.
            sudo apt-get update -q
            sudo apt-get install -y -q pre-commit
            ;;
        dnf|yum)
            sudo "$PKG_MANAGER" install -y pre-commit
            ;;
        *)
            warn "Unknown package manager '$PKG_MANAGER' — falling back to uv"
            ;;
    esac

    # Distro packages lag; fall back to a userspace install rather than failing.
    if ! command -v pre-commit >/dev/null 2>&1; then
        if command -v uv >/dev/null 2>&1; then
            info "Package manager did not provide pre-commit — installing via uv"
            uv tool install pre-commit
        else
            python3 -m pip install --user pre-commit
        fi
    fi

    command -v pre-commit >/dev/null 2>&1 || err "pre-commit install failed"
    ok "pre-commit installed ($(pre-commit --version))"
}

install_hooks() {
    local root
    root="$(git rev-parse --show-toplevel 2>/dev/null)" \
        || err "Not inside a git repository"
    cd "$root"

    [[ -f .pre-commit-config.yaml ]] \
        || err "No .pre-commit-config.yaml at $root — create one before installing hooks"

    pre-commit install
    pre-commit install --hook-type pre-push
    ok "Hooks registered in $root (pre-commit + pre-push)"

    info "Validating configuration..."
    pre-commit validate-config
    ok "Configuration valid"
}

verify() {
    local root hook target
    root="$(git rev-parse --show-toplevel 2>/dev/null)" || err "Not inside a git repository"

    command -v pre-commit >/dev/null 2>&1 \
        && ok "framework: $(pre-commit --version)" \
        || warn "framework: NOT INSTALLED"

    [[ -f "$root/.pre-commit-config.yaml" ]] \
        && ok "config: .pre-commit-config.yaml present" \
        || warn "config: MISSING"

    # A hook that exists but is empty is a silent no-op — treat it as a failure.
    for hook in pre-commit pre-push; do
        target="$root/.git/hooks/$hook"
        if [[ ! -f "$target" ]]; then
            warn "$hook: NOT INSTALLED"
        elif [[ ! -s "$target" ]]; then
            warn "$hook: EMPTY (0 bytes) — silent no-op, reports success and checks nothing"
        elif [[ ! -x "$target" ]]; then
            warn "$hook: not executable"
        else
            ok "$hook: installed"
        fi
    done
}

case "${1:-install}" in
    install|"")     install_framework; install_hooks ;;
    --hooks-only)   install_hooks ;;
    --verify)       verify ;;
    *)              err "Unknown argument: $1 (use: install | --hooks-only | --verify)" ;;
esac
