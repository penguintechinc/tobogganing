"""
Tests for audit/__init__.py — AuditLogger, compliance, integrity.

audit/__init__.py creates a module-level AuditLogger() which calls get_db().
We patch database before the first import so the singleton construction succeeds.
"""
import hashlib
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Patch database before importing audit so the module-level AuditLogger() succeeds.
_mock_db_for_audit = MagicMock()
_mock_db_for_audit.tables = []
_mock_db_for_audit.define_table = MagicMock(return_value=MagicMock())
_mock_db_for_audit.commit = MagicMock()
_mock_db_for_audit.executesql = MagicMock(return_value=[])

if "audit" not in sys.modules:
    with patch("database.get_db", return_value=_mock_db_for_audit), \
         patch("database.initialize_database", return_value=None):
        from audit import AuditEventType, AuditLogger, AuditEvent, ComplianceFramework
else:
    from audit import AuditEventType, AuditLogger, AuditEvent, ComplianceFramework


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Build a comprehensive mock DAL object for audit tests."""
    _db = MagicMock()
    _db.tables = []
    _db.commit = MagicMock()
    _db.executesql = MagicMock(return_value=[])

    stored_events = []

    def define_table(name, *args, **kwargs):
        _db.tables.append(name)
        tbl = MagicMock()
        tbl.insert = MagicMock(side_effect=lambda **kw: stored_events.append(kw) or 1)
        tbl.bulk_insert = MagicMock()
        setattr(_db, name, tbl)
        return tbl

    _db.define_table = define_table

    query_result = MagicMock()
    query_result.select = MagicMock(return_value=[])
    query_result.count = MagicMock(return_value=0)
    query_result.delete = MagicMock(return_value=0)
    query_result.update = MagicMock(return_value=0)
    _db.__call__ = MagicMock(return_value=query_result)

    _db._stored = stored_events
    return _db


@pytest.fixture
def audit_logger_inst(db):
    """AuditLogger with mocked DB, bypassing __init__."""
    with patch("database.get_db", return_value=db):
        logger = AuditLogger.__new__(AuditLogger)
        logger.db = db
        logger._ensure_audit_tables = MagicMock()
        logger.compliance_mapping = {
            ComplianceFramework.SOC2: [
                AuditEventType.USER_LOGIN,
                AuditEventType.USER_LOGIN_FAILED,
                AuditEventType.RESOURCE_ACCESS,
                AuditEventType.CONFIG_CHANGED,
            ],
            ComplianceFramework.HIPAA: [
                AuditEventType.USER_LOGIN,
                AuditEventType.RESOURCE_ACCESS,
            ],
        }
        return logger


# ---------------------------------------------------------------------------
# AuditEventType
# ---------------------------------------------------------------------------

class TestAuditEventType:
    def test_user_login_type_exists(self):
        assert AuditEventType.USER_LOGIN is not None

    def test_user_login_failed_type_exists(self):
        assert AuditEventType.USER_LOGIN_FAILED is not None

    def test_resource_access_type_exists(self):
        assert AuditEventType.RESOURCE_ACCESS is not None

    def test_config_changed_type_exists(self):
        assert AuditEventType.CONFIG_CHANGED is not None

    def test_resource_deleted_type_exists(self):
        assert AuditEventType.RESOURCE_DELETED is not None


# ---------------------------------------------------------------------------
# AuditEvent dataclass
# ---------------------------------------------------------------------------

class TestAuditEvent:
    def test_audit_event_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(AuditEvent)

    def test_audit_event_has_required_fields(self):
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AuditEvent)}
        assert "event_type" in fields
        assert "action" in fields
        assert "ip_address" in fields


# ---------------------------------------------------------------------------
# ComplianceFramework
# ---------------------------------------------------------------------------

class TestComplianceFramework:
    def test_soc2_exists(self):
        assert ComplianceFramework.SOC2 is not None

    def test_hipaa_exists(self):
        assert ComplianceFramework.HIPAA is not None


# ---------------------------------------------------------------------------
# Log event
# ---------------------------------------------------------------------------

class TestLogEvent:
    def test_log_event_calls_db_insert(self, audit_logger_inst, db):
        audit_logger_inst.log_event(
            event_type=AuditEventType.USER_LOGIN,
            action="User login successful",
            ip_address="192.168.1.10",
            user_id="user-001",
            user_email="user@example.com",
            outcome="success",
        )
        # The audit_events table insert should have been called
        if hasattr(db, "audit_events"):
            db.audit_events.insert.assert_called()

    def test_log_event_does_not_raise(self, audit_logger_inst):
        try:
            audit_logger_inst.log_event(
                event_type=AuditEventType.RESOURCE_ACCESS,
                action="Read cluster config",
                ip_address="10.0.0.1",
                outcome="success",
            )
        except Exception as exc:
            pytest.fail(f"log_event raised: {exc}")

    def test_log_event_with_details(self, audit_logger_inst):
        try:
            audit_logger_inst.log_event(
                event_type=AuditEventType.CONFIG_CHANGED,
                action="Update firewall rule",
                ip_address="10.0.0.2",
                details={"rule_id": "rule-001", "old_value": "ALLOW", "new_value": "DENY"},
                outcome="success",
                severity="high",
            )
        except Exception as exc:
            pytest.fail(f"log_event with details raised: {exc}")


# ---------------------------------------------------------------------------
# Risk score calculation
# ---------------------------------------------------------------------------

class TestRiskScore:
    def test_calculate_risk_score_returns_int(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.USER_LOGIN_FAILED,
            outcome="failure",
            severity="high",
        )
        assert isinstance(score, int)

    def test_failed_login_has_higher_risk(self, audit_logger_inst):
        failed = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.USER_LOGIN_FAILED,
            outcome="failure",
            severity="high",
        )
        success = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.USER_LOGIN,
            outcome="success",
            severity="low",
        )
        assert failed >= success

    def test_risk_score_non_negative(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.RESOURCE_ACCESS,
            outcome="success",
            severity="low",
        )
        assert score >= 0


# ---------------------------------------------------------------------------
# Get audit events
# ---------------------------------------------------------------------------

class TestGetAuditEvents:
    def test_get_audit_events_returns_list(self, audit_logger_inst, db):
        query_result = MagicMock()
        query_result.select = MagicMock(return_value=[])
        db.__call__ = MagicMock(return_value=query_result)

        result = audit_logger_inst.get_audit_events()
        assert isinstance(result, list)

    def test_get_audit_events_with_filters(self, audit_logger_inst):
        try:
            result = audit_logger_inst.get_audit_events(
                user_id="user-001",
                event_types=[AuditEventType.USER_LOGIN],
                limit=50,
            )
            assert isinstance(result, list)
        except Exception as exc:
            pytest.fail(f"get_audit_events with filters raised: {exc}")


# ---------------------------------------------------------------------------
# Audit statistics
# ---------------------------------------------------------------------------

class TestGetAuditStatistics:
    def test_get_audit_statistics_returns_dict(self, audit_logger_inst, db):
        query_result = MagicMock()
        query_result.select = MagicMock(return_value=[])
        query_result.count = MagicMock(return_value=0)
        db.__call__ = MagicMock(return_value=query_result)
        db.executesql = MagicMock(return_value=[])

        # PyDAL field comparisons (>=, <=, ==, !=) return NotImplemented by default
        # in MagicMock, causing datetime's fallback comparison to raise TypeError.
        # Configure each field's comparison operators to return a query mock.
        _q = MagicMock()
        for field_name in ("timestamp", "archived", "risk_score", "outcome", "user_id", "ip_address"):
            field = getattr(db.audit_events, field_name)
            field.__ge__ = MagicMock(return_value=_q)
            field.__le__ = MagicMock(return_value=_q)
            field.__eq__ = MagicMock(return_value=_q)
            field.__ne__ = MagicMock(return_value=_q)

        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        result = audit_logger_inst.get_audit_statistics(start_date=start, end_date=end)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Integrity checking
# ---------------------------------------------------------------------------

class TestIntegrity:
    def test_calculate_daily_integrity_returns_string(self, audit_logger_inst, db):
        query_result = MagicMock()
        query_result.select = MagicMock(return_value=[])
        db.__call__ = MagicMock(return_value=query_result)
        db.executesql = MagicMock(return_value=[])

        # Configure timestamp field comparisons to avoid NotImplemented / TypeError.
        _q = MagicMock()
        db.audit_events.timestamp.__ge__ = MagicMock(return_value=_q)
        db.audit_events.timestamp.__le__ = MagicMock(return_value=_q)
        db.audit_integrity.day_date.__eq__ = MagicMock(return_value=_q)

        try:
            result = audit_logger_inst.calculate_daily_integrity(
                date=datetime.utcnow().date()
            )
            assert result is None or isinstance(result, (str, dict))
        except Exception as exc:
            pytest.fail(f"calculate_daily_integrity raised: {exc}")

    def test_verify_audit_integrity_returns_bool_or_dict(self, audit_logger_inst, db):
        query_result = MagicMock()
        query_result.select = MagicMock(return_value=[])
        db.__call__ = MagicMock(return_value=query_result)

        # Configure timestamp field comparisons to avoid NotImplemented / TypeError.
        _q = MagicMock()
        db.audit_events.timestamp.__ge__ = MagicMock(return_value=_q)
        db.audit_events.timestamp.__le__ = MagicMock(return_value=_q)
        db.audit_integrity.day_date.__ge__ = MagicMock(return_value=_q)
        db.audit_integrity.day_date.__le__ = MagicMock(return_value=_q)
        db.audit_integrity.day_date.__eq__ = MagicMock(return_value=_q)

        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=7)

        try:
            result = audit_logger_inst.verify_audit_integrity(start_date=start, end_date=end)
            assert result is None or isinstance(result, (bool, dict))
        except Exception as exc:
            pytest.fail(f"verify_audit_integrity raised: {exc}")


# ---------------------------------------------------------------------------
# Additional tests for missing coverage
# ---------------------------------------------------------------------------

class TestAuditEventTypeCompleteness:
    """Test all AuditEventType enum values."""

    def test_user_session_expired_exists(self):
        assert AuditEventType.USER_SESSION_EXPIRED is not None

    def test_resource_created_exists(self):
        assert AuditEventType.RESOURCE_CREATED is not None

    def test_resource_modified_exists(self):
        assert AuditEventType.RESOURCE_MODIFIED is not None

    def test_resource_accessed_unauthorized_exists(self):
        assert AuditEventType.RESOURCE_ACCESSED_UNAUTHORIZED is not None

    def test_system_config_changed_exists(self):
        assert AuditEventType.SYSTEM_CONFIG_CHANGED is not None

    def test_user_created_exists(self):
        assert AuditEventType.USER_CREATED is not None

    def test_user_modified_exists(self):
        assert AuditEventType.USER_MODIFIED is not None

    def test_user_deleted_exists(self):
        assert AuditEventType.USER_DELETED is not None

    def test_role_assigned_exists(self):
        assert AuditEventType.ROLE_ASSIGNED is not None

    def test_role_revoked_exists(self):
        assert AuditEventType.ROLE_REVOKED is not None

    def test_ip_blocked_exists(self):
        assert AuditEventType.IP_BLOCKED is not None

    def test_ip_unblocked_exists(self):
        assert AuditEventType.IP_UNBLOCKED is not None

    def test_rate_limit_exceeded_exists(self):
        assert AuditEventType.RATE_LIMIT_EXCEEDED is not None

    def test_ddos_detected_exists(self):
        assert AuditEventType.DDOS_DETECTED is not None

    def test_data_import_exists(self):
        assert AuditEventType.DATA_IMPORT is not None

    def test_data_backup_exists(self):
        assert AuditEventType.DATA_BACKUP is not None

    def test_data_restore_exists(self):
        assert AuditEventType.DATA_RESTORE is not None

    def test_system_start_exists(self):
        assert AuditEventType.SYSTEM_START is not None

    def test_system_stop_exists(self):
        assert AuditEventType.SYSTEM_STOP is not None

    def test_service_start_exists(self):
        assert AuditEventType.SERVICE_START is not None

    def test_service_stop_exists(self):
        assert AuditEventType.SERVICE_STOP is not None


class TestComplianceFrameworkCompleteness:
    """Test all ComplianceFramework enum values."""

    def test_gdpr_exists(self):
        assert ComplianceFramework.GDPR is not None

    def test_hipaa_exists(self):
        assert ComplianceFramework.HIPAA is not None

    def test_pci_dss_exists(self):
        assert ComplianceFramework.PCI_DSS is not None

    def test_iso27001_exists(self):
        assert ComplianceFramework.ISO27001 is not None

    def test_nist_exists(self):
        assert ComplianceFramework.NIST is not None


class TestLogEventWithVariations:
    """Test log_event with different parameter combinations."""

    def test_log_event_with_severity_high(self, audit_logger_inst):
        try:
            event_id = audit_logger_inst.log_event(
                event_type=AuditEventType.SECURITY_INCIDENT,
                action="Malicious activity detected",
                ip_address="192.168.1.100",
                severity="critical",
                outcome="failure",
            )
            assert isinstance(event_id, str)
            assert len(event_id) > 0
        except Exception as exc:
            pytest.fail(f"log_event with critical severity raised: {exc}")

    def test_log_event_with_custom_risk_score(self, audit_logger_inst):
        try:
            event_id = audit_logger_inst.log_event(
                event_type=AuditEventType.PRIVILEGE_ESCALATION,
                action="Admin escalated privileges",
                ip_address="10.0.0.5",
                custom_risk_score=9,
                outcome="success",
            )
            assert isinstance(event_id, str)
        except Exception as exc:
            pytest.fail(f"log_event with custom_risk_score raised: {exc}")

    def test_log_event_with_session_and_request_ids(self, audit_logger_inst):
        try:
            event_id = audit_logger_inst.log_event(
                event_type=AuditEventType.USER_LOGIN,
                action="User logged in",
                ip_address="10.0.0.1",
                session_id="sess-abc123",
                request_id="req-def456",
                user_id="user-001",
                outcome="success",
            )
            assert isinstance(event_id, str)
        except Exception as exc:
            pytest.fail(f"log_event with session/request IDs raised: {exc}")

    def test_log_event_with_resource_access(self, audit_logger_inst):
        try:
            event_id = audit_logger_inst.log_event(
                event_type=AuditEventType.RESOURCE_ACCESS,
                action="Accessed cluster configuration",
                ip_address="10.1.1.1",
                resource_type="cluster",
                resource_id="cluster-prod-001",
                outcome="success",
            )
            assert isinstance(event_id, str)
        except Exception as exc:
            pytest.fail(f"log_event with resource access raised: {exc}")

    def test_log_event_partial_outcome(self, audit_logger_inst):
        try:
            event_id = audit_logger_inst.log_event(
                event_type=AuditEventType.DATA_EXPORT,
                action="Exported audit logs",
                ip_address="10.2.2.2",
                outcome="partial",
                severity="warning",
            )
            assert isinstance(event_id, str)
        except Exception as exc:
            pytest.fail(f"log_event with partial outcome raised: {exc}")


class TestRiskScoreCalculationVariations:
    """Test risk score calculation with different combinations."""

    def test_privilege_escalation_has_high_base_score(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.PRIVILEGE_ESCALATION,
            severity="info",
            outcome="success",
        )
        assert score >= 6  # Privilege escalation has high base score

    def test_security_incident_highest_score(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.SECURITY_INCIDENT,
            severity="critical",
            outcome="failure",
        )
        assert score >= 8  # Security incident should be high risk

    def test_ddos_detected_high_score(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.DDOS_DETECTED,
            severity="critical",
            outcome="failure",
        )
        assert score >= 6

    def test_user_logout_lowest_score(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.USER_LOGOUT,
            severity="debug",
            outcome="success",
        )
        assert score <= 2  # User logout should be low risk

    def test_risk_score_respects_severity_multiplier(self, audit_logger_inst):
        debug_score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.USER_LOGIN_FAILED,
            severity="debug",
            outcome="failure",
        )
        critical_score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.USER_LOGIN_FAILED,
            severity="critical",
            outcome="failure",
        )
        assert critical_score > debug_score

    def test_risk_score_respects_outcome_multiplier(self, audit_logger_inst):
        success_score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity="info",
            outcome="success",
        )
        failure_score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity="info",
            outcome="failure",
        )
        assert failure_score > success_score

    def test_risk_score_clamped_to_max_10(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.SECURITY_INCIDENT,
            severity="critical",
            outcome="failure",
        )
        assert score <= 10

    def test_risk_score_clamped_to_min_1(self, audit_logger_inst):
        score = audit_logger_inst._calculate_risk_score(
            event_type=AuditEventType.USER_LOGIN,
            severity="debug",
            outcome="success",
        )
        assert score >= 1


class TestGetAuditEventsFiltering:
    """Test get_audit_events with various filters."""

    def test_get_audit_events_with_date_range(self, audit_logger_inst, db):
        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)

        # Mock the query field comparisons
        _q = MagicMock()
        db.audit_events.timestamp.__ge__ = MagicMock(return_value=_q)
        db.audit_events.timestamp.__le__ = MagicMock(return_value=_q)
        db.audit_events.archived.__eq__ = MagicMock(return_value=_q)
        _q.__and__ = MagicMock(return_value=_q)

        query_result = MagicMock()
        query_result.select = MagicMock(return_value=[])
        db.__call__ = MagicMock(return_value=query_result)

        try:
            result = audit_logger_inst.get_audit_events(
                start_date=start,
                end_date=end,
            )
            assert isinstance(result, list)
        except Exception as exc:
            pytest.fail(f"get_audit_events with date range raised: {exc}")

    def test_get_audit_events_with_severity_filter(self, audit_logger_inst):
        try:
            result = audit_logger_inst.get_audit_events(
                severity_filter=["error", "critical"],
                limit=100,
            )
            assert isinstance(result, list)
        except Exception as exc:
            pytest.fail(f"get_audit_events with severity_filter raised: {exc}")

    def test_get_audit_events_with_offset(self, audit_logger_inst):
        try:
            result = audit_logger_inst.get_audit_events(
                limit=50,
                offset=100,
            )
            assert isinstance(result, list)
        except Exception as exc:
            pytest.fail(f"get_audit_events with offset raised: {exc}")


class TestIntegrityCalculation:
    """Test audit integrity checksum calculations."""

    def test_recalculate_daily_checksum_returns_hex_string(self, audit_logger_inst, db):
        from datetime import date, datetime

        # Mock the query field comparisons
        _q = MagicMock()
        db.audit_events.timestamp.__ge__ = MagicMock(return_value=_q)
        db.audit_events.timestamp.__le__ = MagicMock(return_value=_q)
        _q.__and__ = MagicMock(return_value=_q)

        query_result = MagicMock()
        query_result.select = MagicMock(return_value=[])
        db.__call__ = MagicMock(return_value=query_result)

        checksum = audit_logger_inst._recalculate_daily_checksum(date.today())
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA-256 hex digest length
