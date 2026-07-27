#!/usr/bin/env python3
"""Audit a module's Python files for forbidden cross-module imports.

Enforces the sase/sdwan/ziti decomposition boundary: a module must not import
its siblings. Exits non-zero (listing every offending path:line) on violation.
"""
from __future__ import annotations
import argparse, ast, sys
from pathlib import Path


def _violations(module_dir: Path, forbidden: list[str]) -> list[str]:
    """Return 'path:line: forbidden import <target>' for each cross-module import."""
    forbidden_prefixes = tuple(f"hub_api.modules.{name}" for name in forbidden)
    out: list[str] = []
    for py in module_dir.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                targets.append(node.module)
            elif isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            for t in targets:
                if t.startswith(forbidden_prefixes):
                    out.append(f"{py}:{node.lineno}: forbidden import {t}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--forbid", required=True, help="comma-separated sibling names")
    ap.add_argument("--root", default="hub_api/modules")
    args = ap.parse_args()
    module_dir = Path(args.root) / args.module
    if not module_dir.is_dir():
        print(f"module dir not found: {module_dir}", file=sys.stderr)
        return 2
    viols = _violations(module_dir, [f.strip() for f in args.forbid.split(",") if f.strip()])
    for v in viols:
        print(v)
    return 1 if viols else 0


if __name__ == "__main__":
    raise SystemExit(main())
