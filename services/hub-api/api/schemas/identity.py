"""Pydantic schemas for tenant, team, and SPIFFE identity endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TenantCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    tenant_id: str
    name: str
    domain: Optional[str] = None
    spiffe_trust_domain: Optional[str] = None
    config: Optional[dict] = None


class TeamCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    team_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None


class SpiffeEntryRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    spiffe_id: str
    tenant_id: str
    parent_id: Optional[str] = None
    selectors: Optional[dict] = None
    ttl: int = 0
    dns_names: Optional[list[str]] = None
