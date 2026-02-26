"""Pydantic schemas for policy rule create and update endpoints."""
from __future__ import annotations

import ipaddress
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class PolicyRuleCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    description: Optional[str] = None
    action: Literal["allow", "deny"] = "allow"
    priority: int = 100
    scope: Literal["wireguard", "k8s", "openziti", "both"] = "both"
    direction: Literal["inbound", "outbound", "both"] = "both"
    domains: Optional[list[str]] = None
    ports: Optional[list[str]] = None
    protocol: Literal["tcp", "udp", "icmp", "any"] = "any"
    src_cidrs: Optional[list[str]] = None
    dst_cidrs: Optional[list[str]] = None
    users: Optional[list[str]] = None
    groups: Optional[list[str]] = None
    identity_provider: Literal["local", "oidc", "saml", "scim"] = "local"
    enabled: bool = True
    tenant_id: Optional[str] = None

    @field_validator("src_cidrs", "dst_cidrs", mode="before")
    @classmethod
    def validate_cidrs(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        for cidr in v:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                raise ValueError(f"Invalid CIDR notation: {cidr}")
        return v

    @field_validator("ports", mode="before")
    @classmethod
    def validate_ports(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        for port_str in v:
            if "-" in str(port_str):
                parts = str(port_str).split("-")
                if len(parts) != 2:
                    raise ValueError(f"Invalid port range: {port_str}")
                start, end = int(parts[0]), int(parts[1])
                if not (1 <= start <= 65535 and 1 <= end <= 65535 and start <= end):
                    raise ValueError(f"Invalid port range: {port_str}")
            else:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError(f"Invalid port: {port_str}")
        return v


class PolicyRuleUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: Optional[str] = None
    description: Optional[str] = None
    action: Optional[Literal["allow", "deny"]] = None
    priority: Optional[int] = None
    scope: Optional[Literal["wireguard", "k8s", "openziti", "both"]] = None
    direction: Optional[Literal["inbound", "outbound", "both"]] = None
    domains: Optional[list[str]] = None
    ports: Optional[list[str]] = None
    protocol: Optional[Literal["tcp", "udp", "icmp", "any"]] = None
    src_cidrs: Optional[list[str]] = None
    dst_cidrs: Optional[list[str]] = None
    users: Optional[list[str]] = None
    groups: Optional[list[str]] = None
    identity_provider: Optional[Literal["local", "oidc", "saml", "scim"]] = None
    enabled: Optional[bool] = None
    tenant_id: Optional[str] = None

    @field_validator("src_cidrs", "dst_cidrs", mode="before")
    @classmethod
    def validate_cidrs(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        for cidr in v:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                raise ValueError(f"Invalid CIDR notation: {cidr}")
        return v

    @field_validator("ports", mode="before")
    @classmethod
    def validate_ports(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        for port_str in v:
            if "-" in str(port_str):
                parts = str(port_str).split("-")
                if len(parts) != 2:
                    raise ValueError(f"Invalid port range: {port_str}")
                start, end = int(parts[0]), int(parts[1])
                if not (1 <= start <= 65535 and 1 <= end <= 65535 and start <= end):
                    raise ValueError(f"Invalid port range: {port_str}")
            else:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError(f"Invalid port: {port_str}")
        return v
