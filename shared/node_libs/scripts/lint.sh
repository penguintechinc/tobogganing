#!/usr/bin/env bash
# TypeScript/Node.js linter script - runs all applicable lint checks
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
echo "TypeScript Linting Suite for node_libs"
echo "========================================"
echo ""

ERRORS=0

# Check if node_modules exists
if [[ ! -d "node_modules" ]]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# 1. TypeScript compilation check
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔬 Running TypeScript (type check)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
npx tsc --noEmit || ERRORS=$((ERRORS + 1))

# 2. ESLint - JavaScript/TypeScript linting
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ Running ESLint (linter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FIX_MODE" == true ]]; then
    npx eslint src/ --ext .ts,.tsx --fix || ERRORS=$((ERRORS + 1))
else
    npx eslint src/ --ext .ts,.tsx || ERRORS=$((ERRORS + 1))
fi

# 3. Prettier - Code formatting
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🖤 Running Prettier (formatter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FIX_MODE" == true ]]; then
    npx prettier --write "src/**/*.ts" || ERRORS=$((ERRORS + 1))
else
    npx prettier --check "src/**/*.ts" || ERRORS=$((ERRORS + 1))
fi

# 4. npm audit - Security vulnerabilities
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔒 Running npm audit (security check)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
npm audit --audit-level=moderate || ERRORS=$((ERRORS + 1))

# 5. Build check
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏗️  Running build (compilation check)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
npm run build || ERRORS=$((ERRORS + 1))

# 6. Test (if tests exist)
if [[ -f "package.json" ]] && grep -q '"test"' package.json; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🧪 Running tests..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    npm test || ERRORS=$((ERRORS + 1))
fi

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
