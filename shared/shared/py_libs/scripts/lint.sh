#!/usr/bin/env bash
# Python linter script - runs all applicable lint checks
# Usage: ./scripts/lint.sh [--fix]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FIX_MODE=false

# Parse arguments
if [[ "$1" == "--fix" ]]; then
    FIX_MODE=true
fi

cd "$PROJECT_DIR"

echo "========================================"
echo "Python Linting Suite for py_libs"
echo "========================================"
echo ""

# Check if virtual environment is active
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "⚠️  Warning: Virtual environment not active"
    echo "   Run 'direnv allow' or activate venv manually"
    echo ""
fi

# Ensure dependencies are installed
echo "📦 Checking lint dependencies..."
pip install -q flake8 black isort mypy bandit ruff 2>/dev/null || true

ERRORS=0

# 1. Black - Code formatting
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🖤 Running Black (code formatter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FIX_MODE" == true ]]; then
    black py_libs/ --line-length 100 || ERRORS=$((ERRORS + 1))
else
    black py_libs/ --check --line-length 100 || ERRORS=$((ERRORS + 1))
fi

# 2. isort - Import sorting
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📑 Running isort (import sorter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FIX_MODE" == true ]]; then
    isort py_libs/ --profile black || ERRORS=$((ERRORS + 1))
else
    isort py_libs/ --check-only --profile black || ERRORS=$((ERRORS + 1))
fi

# 3. Ruff - Fast Python linter (replaces flake8)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ Running Ruff (fast linter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FIX_MODE" == true ]]; then
    ruff check py_libs/ --fix || ERRORS=$((ERRORS + 1))
else
    ruff check py_libs/ || ERRORS=$((ERRORS + 1))
fi

# 4. Flake8 - PEP 8 compliance (additional checks)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Running Flake8 (PEP 8 checker)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
flake8 py_libs/ \
    --max-line-length=100 \
    --extend-ignore=E203,E501,W503 \
    --exclude=__pycache__,.venv,venv,.git \
    || ERRORS=$((ERRORS + 1))

# 5. MyPy - Type checking
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔬 Running MyPy (type checker)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
mypy py_libs/ \
    --ignore-missing-imports \
    --no-strict-optional \
    --allow-untyped-defs \
    || ERRORS=$((ERRORS + 1))

# 6. Bandit - Security linting
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔒 Running Bandit (security linter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
bandit -r py_libs/ \
    --severity-level medium \
    --confidence-level medium \
    --exclude .venv,venv,__pycache__ \
    -q \
    || ERRORS=$((ERRORS + 1))

# Summary
echo ""
echo "========================================"
if [[ $ERRORS -eq 0 ]]; then
    echo "✅ All lint checks passed!"
else
    echo "❌ $ERRORS lint check(s) failed"
    echo "   Run with --fix to auto-fix issues"
fi
echo "========================================"

exit $ERRORS
