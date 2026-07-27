"""SDWAN WireGuard key management package.

Re-exports the WireGuard key manager so callers can import it from the package
root without reaching into the implementation module.
"""
from __future__ import annotations

from hub_api.modules.sdwan.certs.wireguard_manager import WireGuardKeyManager

__all__ = ["WireGuardKeyManager"]
