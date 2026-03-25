"""Pydantic schemas for performance metric submission and query endpoints."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class PerfMetricSubmission(BaseModel):
    model_config = ConfigDict(strict=True)

    source_id: str
    source_type: Literal["hub-router", "client"]
    target_id: str
    protocol: str
    latency_ms: float
    jitter_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    throughput_mbps: Optional[float] = None
    timestamp: Optional[str] = None


class PerfMetricQuery(BaseModel):
    model_config = ConfigDict(strict=True)

    cluster_id: Optional[str] = None
    time_range_start: Optional[str] = None
    time_range_end: Optional[str] = None
    protocol: Optional[str] = None
    limit: int = 100
