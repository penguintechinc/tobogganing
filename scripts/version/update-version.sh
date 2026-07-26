#!/usr/bin/env bash
# Version Management Script for Tobogganing
# Format: vMajor.Minor.Patch.build (build = epoch64 timestamp)
#
# Usage:
#   ./scripts/version/update-version.sh          # Increment build timestamp only
#   ./scripts/version/update-version.sh patch    # Increment patch version
#   ./scripts/version/update-version.sh minor    # Increment minor version
#   ./scripts/version/update-version.sh major    # Increment major version

set -euo pipefail

VERSION_FILE="$(git rev-parse --show-toplevel)/.version"

if [[ ! -f "$VERSION_FILE" ]]; then
    echo "Error: Version file not found at $VERSION_FILE"
    exit 1
fi

CURRENT_VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
echo "Current version: $CURRENT_VERSION"

# Parse version components (strip leading 'v')
VERSION_BODY="${CURRENT_VERSION#v}"
IFS='.' read -r MAJOR MINOR PATCH BUILD <<< "$VERSION_BODY"

# Default BUILD to epoch if not present
BUILD=$(date +%s)

BUMP_TYPE="${1:-build}"

case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
    build)
        # Only update build timestamp
        ;;
    *)
        echo "Usage: $0 [major|minor|patch|build]"
        exit 1
        ;;
esac

NEW_VERSION="v${MAJOR}.${MINOR}.${PATCH}.${BUILD}"
echo "$NEW_VERSION" > "$VERSION_FILE"
echo "Updated version: $NEW_VERSION"
