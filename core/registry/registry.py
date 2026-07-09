"""Module registry for managing module contracts and registration."""
from __future__ import annotations

from typing import TYPE_CHECKING

from quart import Quart

from core.registry.contract import Entitlement, ModuleContract, ModuleContext, NavEntry

if TYPE_CHECKING:
    from typing import Callable, Optional

# API major version constant
API_MAJOR = 1


class ModuleRegistry:
    """Registry for managing module contracts and their integration with the Quart app."""

    def __init__(self) -> None:
        """Initialize the module registry."""
        self._modules: dict[str, ModuleContract] = {}
        self._flags: list[str] = []
        self._nav: list[NavEntry] = []
        self._entitlements: list[Entitlement] = []

    def register(self, contract: ModuleContract) -> None:
        """Register a module contract.

        Args:
            contract: The ModuleContract to register.
        """
        self._modules[contract.name] = contract
        self._flags.extend(contract.flags)
        self._nav.extend(contract.nav)
        self._entitlements.extend(contract.entitlements)

    def apply_to(self, app: Quart, ctx: ModuleContext) -> None:
        """Apply all registered modules to the Quart application.

        Registers blueprints under /api/v{major}/{name} paths and wires health checks.
        Each blueprint's url_prefix is combined with the module prefix.

        Args:
            app: The Quart application instance.
            ctx: The ModuleContext providing config, db, and key_provider.
        """
        for module_name, contract in self._modules.items():
            # Register blueprints under versioned API paths
            for blueprint in contract.blueprints:
                module_prefix = f"/api/v{API_MAJOR}/{module_name}"
                blueprint_prefix = blueprint.url_prefix or ""
                combined = module_prefix + blueprint_prefix
                app.register_blueprint(blueprint, url_prefix=combined)

    def declared_flags(self) -> list[str]:
        """Get all declared feature flags from registered modules.

        Returns:
            List of feature flag strings.
        """
        return self._flags.copy()

    def nav_manifest(self) -> list[NavEntry]:
        """Get the navigation manifest from all registered modules.

        Returns:
            List of NavEntry objects.
        """
        return self._nav.copy()

    def entitlement_for(self, feature: str) -> Optional[Entitlement]:
        """Get the entitlement specification for a feature.

        Args:
            feature: The feature name to look up.

        Returns:
            The Entitlement if found, None otherwise.
        """
        for entitlement in self._entitlements:
            if entitlement.feature == feature:
                return entitlement
        return None
