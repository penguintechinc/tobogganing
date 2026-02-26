"""Pydantic schemas for VRF and port configuration endpoints."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class VRFCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    rd: str
    ip_ranges: Optional[list[str]] = None
    area_type: Literal["ospf", "bgp", "static"] = "ospf"
    area_id: Optional[str] = None


class PortConfigRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    headend_id: str
    cluster_id: int
    tcp_ranges: Optional[str] = None
    udp_ranges: Optional[str] = None
