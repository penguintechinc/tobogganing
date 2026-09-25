"""Test module import boundaries (sdwan/sase/ziti isolation).

Enforces that each module does not import its forbidden siblings.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

import pytest


# Import _violations from scripts/audit_imports.py
_audit_script = Path(__file__).parent.parent.parent / "scripts" / "audit_imports.py"
spec = importlib.util.spec_from_file_location("audit_imports", _audit_script)
audit_module = importlib.util.module_from_spec(spec)
sys.modules["audit_imports"] = audit_module
spec.loader.exec_module(audit_module)
_violations = audit_module._violations


@pytest.mark.parametrize(
    "module_name,forbidden",
    [
        ("sdwan", ["sase", "ziti"]),
        ("sase", ["sdwan", "ziti"]),
        ("ziti", ["sdwan", "sase"]),
    ],
)
def test_module_boundaries(module_name: str, forbidden: list[str]) -> None:
    """Assert each module does not import its forbidden siblings."""
    module_dir = Path("hub_api/modules") / module_name
    if not module_dir.is_dir():
        pytest.skip(f"{module_name} not present yet")

    viols = _violations(module_dir, forbidden)
    assert viols == [], f"Module {module_name} has forbidden imports: {viols}"
