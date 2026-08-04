"""Cache key builder with namespace guards."""

from __future__ import annotations

NAMESPACES = frozenset({"auth", "sase:blocklist", "sase:catcache", "rl"})


class NamespaceError(ValueError):
    """Raised when a namespace is not in the allowed set."""

    pass


def prefixed(namespace: str, *parts: str) -> str:
    """Build a namespaced cache key.

    Enforces that namespace is in the allowed NAMESPACES set.
    Returns "{namespace}:{':'.join(parts)}" format.

    Args:
        namespace: Cache namespace (must be in NAMESPACES).
        *parts: Key parts to join.

    Returns:
        Prefixed key string.

    Raises:
        NamespaceError: If namespace is not in NAMESPACES.
    """
    if namespace not in NAMESPACES:
        raise NamespaceError(f"namespace '{namespace}' not in {NAMESPACES}")
    return f"{namespace}:{':'.join(parts)}"
