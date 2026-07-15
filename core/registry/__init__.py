"""Module registry package for Tobogganing Core."""
from core.registry.contract import Entitlement, ModuleContext, ModuleContract, NavEntry
from core.registry.registry import ModuleRegistry

__all__ = [
    "ModuleRegistry",
    "ModuleContract",
    "ModuleContext",
    "NavEntry",
    "Entitlement",
]
