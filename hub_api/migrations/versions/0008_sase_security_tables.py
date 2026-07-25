"""Add SASE security module tables (scanner, protection, feeds).

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-09 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create security scanner, protection, and threat feed tables."""
    # Create security_scans table
    op.create_table(
        "security_scans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("scan_id", sa.String(36), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("scan_type", sa.String(32), nullable=False, index=True),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("tools_used", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("findings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_findings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_findings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium_findings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_findings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scan_duration", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("triggered_by", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_security_scans"),
        sa.UniqueConstraint("scan_id", name="uq_security_scans_scan_id"),
    )
    # Create composite and explicit indexes from __table_args__
    op.create_index("idx_security_scans_tenant_status", "security_scans", ["tenant_id", "status"], unique=False)

    # Create security_findings table
    op.create_table(
        "security_findings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("finding_id", sa.String(36), nullable=False, index=True, unique=True),
        sa.Column("scan_id", sa.String(36), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("finding_type", sa.String(64), nullable=False, index=True),
        sa.Column("severity", sa.String(16), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("affected_component", sa.String(255), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("cve_ids", sa.JSON(), nullable=True),
        sa.Column("cvss_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open", index=True),
        sa.Column("remediated_at", sa.DateTime(), nullable=True),
        sa.Column("false_positive", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_security_findings"),
        sa.ForeignKeyConstraint(["scan_id"], ["security_scans.scan_id"], name="fk_security_findings_scan_id"),
    )
    # Create composite and explicit indexes from __table_args__
    op.create_index("idx_security_findings_tenant_severity", "security_findings", ["tenant_id", "severity"], unique=False)

    # Create scan_schedules table
    op.create_table(
        "scan_schedules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("schedule_id", sa.String(36), nullable=False, index=True, unique=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("scan_type", sa.String(32), nullable=False),
        sa.Column("target_pattern", sa.String(255), nullable=False),
        sa.Column("cron_schedule", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_run", sa.DateTime(), nullable=True),
        sa.Column("next_run", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_scan_schedules"),
    )
    # Create composite and explicit indexes from __table_args__
    op.create_index("idx_scan_schedules_tenant_enabled", "scan_schedules", ["tenant_id", "enabled"], unique=False)

    # Create security_events table
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=False, index=True),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, index=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("tenant_id", sa.String(36), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_security_events"),
    )
    # Create composite and explicit indexes from __table_args__
    op.create_index("ix_security_events_event_type_tenant", "security_events", ["event_type", "tenant_id"], unique=False)

    # Create rate_limit_rules table
    op.create_table(
        "rate_limit_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("max_requests", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("block_duration", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("endpoints", sa.JSON(), nullable=True),
        sa.Column("exempt_ips", sa.JSON(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("tenant_id", sa.String(36), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rate_limit_rules"),
    )
    # Create composite and explicit indexes from __table_args__
    op.create_index("ix_rate_limit_rules_tenant_enabled", "rate_limit_rules", ["tenant_id", "enabled"], unique=False)

    # Create threat_indicators table
    op.create_table(
        "threat_indicators",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("indicator_type", sa.String(16), nullable=False, index=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("threat_types", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, index=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("ttl", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1", index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_threat_indicators"),
        sa.UniqueConstraint("value", "source", "tenant_id", name="uq_threat_indicators_value_source_tenant"),
    )

    # Create feed_updates table
    op.create_table(
        "feed_updates",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("update_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("indicators_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indicators_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indicators_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_feed_updates"),
    )
    # Create explicit index for source (not created by index=True)
    op.create_index("ix_feed_updates_source", "feed_updates", ["source"], unique=False)

    # Create threat_detections table
    op.create_table(
        "threat_detections",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("client_ip", sa.String(45), nullable=False),
        sa.Column("requested_domain", sa.String(255), nullable=True),
        sa.Column("requested_ip", sa.String(45), nullable=True),
        sa.Column("threat_indicator_id", sa.String(36), nullable=True),
        sa.Column("action_taken", sa.String(32), nullable=False),
        sa.Column("threat_types", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_threat_detections"),
        sa.ForeignKeyConstraint(["threat_indicator_id"], ["threat_indicators.id"], name="fk_threat_detections_threat_indicator_id"),
    )
    # Create explicit indexes not created by index=True
    op.create_index("ix_threat_detections_client_ip", "threat_detections", ["client_ip"], unique=False)
    op.create_index("ix_threat_detections_detected_at", "threat_detections", ["detected_at"], unique=False)


def downgrade() -> None:
    """Drop security tables."""
    # Drop threat_detections (has FK, must be first)
    op.drop_index("ix_threat_detections_detected_at", table_name="threat_detections")
    op.drop_index("ix_threat_detections_client_ip", table_name="threat_detections")
    op.drop_table("threat_detections")

    # Drop threat_indicators (referenced by threat_detections)
    op.drop_table("threat_indicators")

    # Drop feed_updates
    op.drop_index("ix_feed_updates_source", table_name="feed_updates")
    op.drop_table("feed_updates")

    # Drop rate_limit_rules
    op.drop_index("ix_rate_limit_rules_tenant_enabled", table_name="rate_limit_rules")
    op.drop_table("rate_limit_rules")

    # Drop security_events
    op.drop_index("ix_security_events_event_type_tenant", table_name="security_events")
    op.drop_table("security_events")

    # Drop scan_schedules
    op.drop_index("idx_scan_schedules_tenant_enabled", table_name="scan_schedules")
    op.drop_table("scan_schedules")

    # Drop security_findings (has FK to security_scans)
    op.drop_index("idx_security_findings_tenant_severity", table_name="security_findings")
    op.drop_table("security_findings")

    # Drop security_scans
    op.drop_index("idx_security_scans_tenant_status", table_name="security_scans")
    op.drop_table("security_scans")
