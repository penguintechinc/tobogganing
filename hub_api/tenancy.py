"""Reserved tenant identifiers shared across hub-api modules.

Per org rules the ``system`` tenant is the operator plane: it owns
platform-wide data such as global threat feeds. Customer tenants may read
that data but must never write it.
"""

from __future__ import annotations

#: Operator-plane reserved tenant; owner of global (platform-wide) data.
SYSTEM_TENANT = "system"

#: Legacy nil-UUID tenant formerly used for global threat feeds (migrated by 0030).
LEGACY_GLOBAL_TENANT = "00000000-0000-0000-0000-000000000000"


class ReservedTenantWriteError(PermissionError):
    """Raised when a tenant-scoped write targets the reserved system tenant."""


def assert_not_system_tenant(tenant_id: str) -> None:
    """Reject a tenant-scoped write aimed at the reserved ``system`` tenant.

    Tenant write paths call this so customer data can never land in (or
    overwrite) global data; only explicit system jobs write there.
    """
    if tenant_id == SYSTEM_TENANT:
        raise ReservedTenantWriteError("writes to the reserved system tenant are not allowed")
