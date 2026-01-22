#!/usr/bin/env bash
# Go linter script - runs all applicable lint checks
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
echo "Go Linting Suite for go_libs"
echo "========================================"
echo ""

ERRORS=0

# Check if golangci-lint is installed
if ! command -v golangci-lint &> /dev/null; then
    echo "📦 Installing golangci-lint..."
    go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
fi

# Check if gosec is installed
if ! command -v gosec &> /dev/null; then
    echo "📦 Installing gosec..."
    go install github.com/securego/gosec/v2/cmd/gosec@latest
fi

# 1. go fmt - Code formatting
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 Running go fmt (code formatter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FIX_MODE" == true ]]; then
    gofmt -w .
    echo "✓ Formatted all Go files"
else
    UNFORMATTED=$(gofmt -l .)
    if [[ -n "$UNFORMATTED" ]]; then
        echo "❌ The following files need formatting:"
        echo "$UNFORMATTED"
        ERRORS=$((ERRORS + 1))
    else
        echo "✓ All files are properly formatted"
    fi
fi

# 2. go vet - Static analysis
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Running go vet (static analysis)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
go vet ./... || ERRORS=$((ERRORS + 1))

# 3. go mod verify - Module verification
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Running go mod verify..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
go mod verify || ERRORS=$((ERRORS + 1))

# 4. golangci-lint - Comprehensive linting
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ Running golangci-lint (comprehensive linter)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FIX_MODE" == true ]]; then
    golangci-lint run --fix ./... || ERRORS=$((ERRORS + 1))
else
    golangci-lint run ./... \
        --enable=gofmt,goimports,govet,errcheck,staticcheck,gosimple,ineffassign,unused \
        --enable=misspell,revive,exportloopref,bodyclose,noctx,prealloc \
        --timeout=5m \
        || ERRORS=$((ERRORS + 1))
fi

# 5. gosec - Security scanning
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔒 Running gosec (security scanner)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
gosec -quiet ./... || ERRORS=$((ERRORS + 1))

# 6. go build - Verify compilation
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏗️  Running go build (compilation check)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
go build ./... || ERRORS=$((ERRORS + 1))

# 7. go test - Run tests
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 Running go test (unit tests)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
go test -v -race ./... || ERRORS=$((ERRORS + 1))

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
