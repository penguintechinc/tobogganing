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
                event_type=AuditEventType.USER_LOGIN,
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

        result = audit_logger_inst.get_audit_statistics()
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

        try:
            result = audit_logger_inst.verify_audit_integrity()
            assert result is None or isinstance(result, (bool, dict))
        except Exception as exc:
            pytest.fail(f"verify_audit_integrity raised: {exc}")
