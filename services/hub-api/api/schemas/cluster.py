"""Pydantic schemas for cluster registration and update endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ClusterRegisterRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    region: str
    datacenter: str
    headend_url: str

    @field_validator("headend_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("headend_url must start with http:// or https://")
        return v


class ClusterUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: Optional[str] = None
    region: Optional[str] = None
    datacenter: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("active", "inactive", "maintenance"):
            raise ValueError("status must be active, inactive, or maintenance")
        return v
