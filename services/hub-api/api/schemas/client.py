"""Pydantic schemas for client registration and update endpoints."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class ClientRegisterRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    type: Literal["native", "docker", "mobile", "client_native", "client_docker"]
    public_key: str
    location: Optional[dict] = None
    attestation: Optional[dict] = None


class ClientUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: Optional[str] = None
    tunnel_mode: Optional[Literal["full", "split"]] = None
    split_tunnel_routes: Optional[list[str]] = None
