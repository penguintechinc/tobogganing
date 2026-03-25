"""Pydantic API schemas for Tobogganing hub-api.

Each submodule owns schemas for one resource domain.  Import from here to
avoid coupling callers to the internal module layout.
"""
from api.schemas.auth import LoginRequest, TokenExchangeRequest, TokenRequest
from api.schemas.client import ClientRegisterRequest, ClientUpdateRequest
from api.schemas.cluster import ClusterRegisterRequest, ClusterUpdateRequest
from api.schemas.identity import SpiffeEntryRequest, TeamCreateRequest, TenantCreateRequest
from api.schemas.network import PortConfigRequest, VRFCreateRequest
from api.schemas.perf import PerfMetricQuery, PerfMetricSubmission
from api.schemas.policy import PolicyRuleCreateRequest, PolicyRuleUpdateRequest

__all__ = [
    # auth
    "TokenRequest",
    "LoginRequest",
    "TokenExchangeRequest",
    # client
    "ClientRegisterRequest",
    "ClientUpdateRequest",
    # cluster
    "ClusterRegisterRequest",
    "ClusterUpdateRequest",
    # identity
    "TenantCreateRequest",
    "TeamCreateRequest",
    "SpiffeEntryRequest",
    # network
    "VRFCreateRequest",
    "PortConfigRequest",
    # perf
    "PerfMetricSubmission",
    "PerfMetricQuery",
    # policy
    "PolicyRuleCreateRequest",
    "PolicyRuleUpdateRequest",
]
