"""Pydantic schemas for authentication endpoints."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class TokenRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    node_id: str
    node_type: Literal[
        "kubernetes_node", "raw_compute", "client_docker", "client_native"
    ]
    api_key: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    username: str
    password: str


class TokenExchangeRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    token: str
    provider: str
    tenant_id: Optional[str] = None
