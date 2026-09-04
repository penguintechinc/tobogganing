"""Edge-case coverage for WireGuardKeyManager IP allocation and config lookup."""

from __future__ import annotations

import hashlib

import pytest

from hub_api.modules.sdwan.certs import WireGuardKeyManager


def _compute_ip(node_id: str, attempt: int) -> str:
    """Replicate WireGuardKeyManager._allocate_ip's deterministic hash-to-IP logic.

    Args:
        node_id: Node identifier.
        attempt: Attempt counter used in the hash input.

    Returns:
        The IP address the manager would compute for this node_id/attempt pair.
    """
    hash_input = f"{node_id}#{attempt}".encode()
    hash_bytes = hashlib.sha256(hash_input).digest()
    octet3 = (int.from_bytes(hash_bytes[0:1], "big") % 254) + 1
    octet4 = (int.from_bytes(hash_bytes[1:2], "big") % 254) + 1
    return f"10.200.{octet3}.{octet4}"


@pytest.fixture
def wg_manager() -> WireGuardKeyManager:
    """Create a WireGuardKeyManager instance."""
    return WireGuardKeyManager()


def test_allocate_ip_cached_returns_same_ip(wg_manager: WireGuardKeyManager) -> None:
    """Calling _allocate_ip twice for the same node returns the cached IP."""
    first = wg_manager._allocate_ip("node-cache")
    second = wg_manager._allocate_ip("node-cache")

    assert first == second
    assert wg_manager._ip_allocations["node-cache"] == first


def test_allocate_ip_collision_resolves_to_next_attempt(
    wg_manager: WireGuardKeyManager,
) -> None:
    """A collision on attempt 0 is detected and resolved on attempt 1."""
    target_node = "colliding-node"
    attempt0_ip = _compute_ip(target_node, 0)

    # Pre-occupy the attempt-0 IP with a different node.
    wg_manager._ip_allocations["other-node"] = attempt0_ip

    result_ip = wg_manager._allocate_ip(target_node)

    assert result_ip != attempt0_ip
    assert wg_manager._ip_allocations[target_node] == result_ip


def test_allocate_ip_exhausted_raises_runtime_error(
    wg_manager: WireGuardKeyManager,
) -> None:
    """All 100 attempts colliding raises RuntimeError."""
    target_node = "doomed-node"

    for attempt in range(100):
        ip = _compute_ip(target_node, attempt)
        wg_manager._ip_allocations[f"blocker-{attempt}"] = ip

    with pytest.raises(RuntimeError, match="Failed to allocate collision-free IP"):
        wg_manager._allocate_ip(target_node)


@pytest.mark.asyncio
async def test_generate_wireguard_keys_exhausted_raises(
    wg_manager: WireGuardKeyManager,
) -> None:
    """generate_wireguard_keys propagates the IP-exhaustion RuntimeError."""
    target_node = "doomed-node-2"

    for attempt in range(100):
        ip = _compute_ip(target_node, attempt)
        wg_manager._ip_allocations[f"blocker2-{attempt}"] = ip

    with pytest.raises(RuntimeError, match="Failed to allocate collision-free IP"):
        await wg_manager.generate_wireguard_keys(target_node, "client")


@pytest.mark.asyncio
async def test_get_wireguard_config_unknown_cluster_returns_empty(
    wg_manager: WireGuardKeyManager,
) -> None:
    """get_wireguard_config for an unknown cluster_id returns an empty dict."""
    config = await wg_manager.get_wireguard_config("does-not-exist")

    assert config == {}
