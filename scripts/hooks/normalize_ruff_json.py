#!/usr/bin/env python3
"""Normalize `ruff check --output-format=json` on stdin into stable
(relative-path, code, message) lines for baseline comparison in
run-ruff-gate.sh. Line/column numbers are deliberately dropped so unrelated
line shifts elsewhere in a file don't register as new or fixed violations.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> None:
    """Read ruff's JSON diagnostics from stdin, print one normalized line per
    unique (relative filename, rule code, message) tuple, sorted for a stable
    diff against the checked-in baseline."""
    data = json.load(sys.stdin)
    lines: set[str] = set()
    for item in data:
        rel_path = os.path.relpath(item["filename"])
        lines.add(f"{rel_path}:{item['code']}: {item['message']}")
    for line in sorted(lines):
        print(line)


if __name__ == "__main__":
    main()
