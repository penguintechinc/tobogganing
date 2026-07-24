"""Configuration module for Tobogganing Core."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Config:
    """Application configuration with environment variable support."""

    # Database configuration
    db_type: str = os.getenv("DB_TYPE", "sqlite")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "tobogganing")
    db_pass: str = os.getenv("DB_PASS", "")
    db_name: str = os.getenv("DB_NAME", "tobogganing")
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))

    # JWT configuration
    jwt_expiration_hours: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

    # CORS configuration
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    # PostHog configuration
    posthog_key: str = os.getenv("POSTHOG_KEY", "")
    posthog_host: str = os.getenv("POSTHOG_HOST", "https://license.penguintech.io")

    # License configuration
    license_key: str = os.getenv("LICENSE_KEY", "")

    # Product configuration
    product_name: str = os.getenv("PRODUCT_NAME", "tobogganing")

    # Logging configuration
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Environment (dev/staging/production)
    env: str = os.getenv("ENV", "dev")

    # Hub-router deployment count for HA checks
    # NOTE: in P-B this re-binds to the live hub-router registry count
    hub_router_count: int = int(os.getenv("HUB_ROUTER_COUNT", "1"))


def build_db_uri(cfg: Config) -> str:
    """Build database connection URI based on DB_TYPE.

    Args:
        cfg: Configuration object.

    Returns:
        Database URI string for async database driver.
    """
    if cfg.db_type == "mysql":
        return (
            f"mysql+aiomysql://{cfg.db_user}:{cfg.db_pass}@"
            f"{cfg.db_host}:{cfg.db_port}/{cfg.db_name}"
        )
    if cfg.db_type in ("postgresql", "postgres"):
        return (
            f"postgresql+asyncpg://{cfg.db_user}:{cfg.db_pass}@"
            f"{cfg.db_host}:{cfg.db_port}/{cfg.db_name}"
        )
    return f"sqlite+aiosqlite:///{cfg.db_name}"
