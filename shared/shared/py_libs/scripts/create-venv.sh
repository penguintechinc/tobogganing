#!/bin/bash
# Create Python virtual environment for shared py_libs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")"

echo "🐍 Creating virtual environment for py_libs..."

cd "$LIB_DIR"

# Remove existing venv if present
if [ -d ".venv" ]; then
    echo "Removing existing .venv..."
    rm -rf .venv
fi

# Create new venv
python3 -m venv .venv

# Activate and install dependencies
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

echo ""
echo "✅ Virtual environment created successfully!"
echo ""
echo "To activate, run:"
echo "  source $LIB_DIR/.venv/bin/activate"
echo ""
echo "Or use direnv (recommended):"
echo "  cd $LIB_DIR && direnv allow"
