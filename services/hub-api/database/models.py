"""SQLAlchemy schema definitions for Tobogganing Hub API.

This module is the single source of truth for table structure.

- Alembic uses ``metadata`` here for autogenerate and migration tracking.
- penguin-dal uses ``AsyncDB(reflect=True)`` to discover tables at runtime;
  it does NOT read these models directly — they exist solely for migration
  authoring and IDE/mypy introspection.

DO NOT use SQLAlchemy ORM sessions for runtime queries.  All runtime
data access goes through ``penguin_dal.AsyncDB`` (see database/__init__.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
)

# Naming convention keeps Alembic constraint names deterministic across DBs.
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# ---------------------------------------------------------------------------
# Core tables (matching the original PyDAL schema)
# ---------------------------------------------------------------------------

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(255), nullable=False, unique=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("full_name", String(255)),
    Column("role", String(50), nullable=False, default="viewer"),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("last_login", DateTime),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

clusters = Table(
    "clusters",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False, unique=True),
    Column("region", String(100)),
    Column("datacenter", String(100)),
    Column("status", String(50), nullable=False, default="active"),
    Column("config", JSON),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

clients = Table(
    "clients",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("client_id", String(255), nullable=False, unique=True),
    Column("name", String(255), nullable=False),
    Column("type", String(50)),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
    Column("cluster_id", Integer, ForeignKey("clusters.id", ondelete="CASCADE")),
    Column("status", String(50), nullable=False, default="active"),
    Column("public_key", Text),
    Column("config", JSON),
    Column("tunnel_mode", String(20), nullable=False, default="full"),
    Column("split_tunnel_routes", JSON),
    Column("last_seen", DateTime),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

policy_rules = Table(
    "policy_rules",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("action", String(20), nullable=False, default="allow"),
    Column("priority", Integer, nullable=False, default=100),
    Column("domain_pattern", String(500)),
    Column("port_range", String(255)),
    Column("protocol", String(20), nullable=False, default="any"),
    Column("src_cidr", String(100)),
    Column("dst_cidr", String(100)),
    Column("user_group", String(255)),
    Column("identity_provider", String(50), nullable=False, default="local"),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

identity_providers = Table(
    "identity_providers",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False, unique=True),
    Column("provider_type", String(50)),
    Column("config", JSON),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("license_required", Boolean, nullable=False, default=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

firewall_rules = Table(
    "firewall_rules",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
    Column("rule_type", String(50)),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("action", String(20), nullable=False, default="allow"),
    Column("direction", String(20), nullable=False, default="both"),
    Column("priority", Integer, nullable=False, default=100),
    Column("src_ip", String(100)),
    Column("dst_ip", String(100)),
    Column("protocol", String(20)),
    Column("src_port", String(100)),
    Column("dst_port", String(100)),
    Column("domain", String(255)),
    Column("url_pattern", Text),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

vrfs = Table(
    "vrfs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False, unique=True),
    Column("description", Text),
    Column("rd", String(100), nullable=False, unique=True),
    Column("ip_ranges", JSON),
    Column("area_type", String(50), nullable=False, default="normal"),
    Column("area_id", String(50)),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

ospf_config = Table(
    "ospf_config",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("vrf_id", Integer, ForeignKey("vrfs.id", ondelete="CASCADE")),
    Column("area_id", String(50), nullable=False),
    Column("area_type", String(50), nullable=False, default="normal"),
    Column("networks", JSON),
    Column("interfaces", JSON),
    Column("auth_type", String(50), nullable=False, default="none"),
    Column("auth_key", String(255)),
    Column("hello_interval", Integer, nullable=False, default=10),
    Column("dead_interval", Integer, nullable=False, default=40),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

port_configs = Table(
    "port_configs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("headend_id", String(255), nullable=False),
    Column("cluster_id", Integer, ForeignKey("clusters.id", ondelete="CASCADE")),
    Column("tcp_ranges", Text),
    Column("udp_ranges", Text),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

port_ranges = Table(
    "port_ranges",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("port_config_id", Integer, ForeignKey("port_configs.id", ondelete="CASCADE")),
    Column("start_port", Integer),
    Column("end_port", Integer),
    Column("protocol", String(10)),
    Column("description", Text),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

certificates = Table(
    "certificates",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cert_type", String(50)),
    Column("subject", String(500)),
    Column("issuer", String(500)),
    Column("serial_number", String(100), unique=True),
    Column("not_before", DateTime),
    Column("not_after", DateTime),
    Column("certificate_pem", Text),
    Column("private_key_pem", Text),
    Column("client_id", Integer, ForeignKey("clients.id")),
    Column("revoked", Boolean, nullable=False, default=False),
    Column("revoked_at", DateTime),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), nullable=False, unique=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
    Column("ip_address", String(45)),
    Column("user_agent", Text),
    Column("expires_at", DateTime),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)

jwt_tokens = Table(
    "jwt_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("token_id", String(255), nullable=False, unique=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
    Column("token_type", String(50)),
    Column("expires_at", DateTime),
    Column("revoked", Boolean, nullable=False, default=False),
    Column("revoked_at", DateTime),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)

# ---------------------------------------------------------------------------
# Analytics tables (previously dynamic define_table in analytics/__init__.py)
# ---------------------------------------------------------------------------

client_analytics = Table(
    "client_analytics",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("client_id", String(64), nullable=False),
    Column("hostname", String(255)),
    Column("os_name", String(64)),
    Column("os_version", String(128)),
    Column("architecture", String(32)),
    Column("client_version", String(64)),
    Column("ip_address", String(45)),
    Column("connected_headend", String(128)),
    Column("connection_duration", Integer),
    Column("bytes_sent", BigInteger, default=0),
    Column("bytes_received", BigInteger, default=0),
    Column("packets_sent", BigInteger, default=0),
    Column("packets_received", BigInteger, default=0),
    Column("last_seen", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

headend_analytics = Table(
    "headend_analytics",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("headend_id", String(128), nullable=False),
    Column("hostname", String(255)),
    Column("region", String(64)),
    Column("cluster_id", String(128)),
    Column("version", String(64)),
    Column("active_connections", Integer, default=0),
    Column("total_connections", BigInteger, default=0),
    Column("bytes_proxied", BigInteger, default=0),
    Column("packets_proxied", BigInteger, default=0),
    Column("cpu_usage_percent", String(10)),  # stored as string for cross-DB compat
    Column("memory_usage_mb", Integer),
    Column("disk_usage_percent", String(10)),
    Column("network_errors", Integer, default=0),
    Column("auth_successes", Integer, default=0),
    Column("auth_failures", Integer, default=0),
    Column("last_heartbeat", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

traffic_stats = Table(
    "traffic_stats",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("stat_type", String(32)),
    Column("timestamp", DateTime, nullable=False),
    Column("headend_id", String(128)),
    Column("client_count", Integer, default=0),
    Column("total_bytes", BigInteger, default=0),
    Column("total_packets", BigInteger, default=0),
    Column("unique_users", Integer, default=0),
    Column("avg_connection_duration", Integer, default=0),
    Column("peak_concurrent_connections", Integer, default=0),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)
