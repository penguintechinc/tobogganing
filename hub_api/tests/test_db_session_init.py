"""Tests for hub_api.db.session and hub_api.db.__init__ (penguin-dal wiring)."""

from __future__ import annotations

import sys

import pytest
from sqlalchemy.engine import Engine

from hub_api.db.session import Base, create_engine_for_uri, get_metadata, metadata


class TestCreateEngineForUri:
    """Tests for create_engine_for_uri()."""

    def test_returns_sqlalchemy_engine(self) -> None:
        """Returns a configured SQLAlchemy Engine for a sqlite URI."""
        engine = create_engine_for_uri("sqlite:///:memory:")
        assert isinstance(engine, Engine)
        engine.dispose()

    def test_respects_pool_size_param(self) -> None:
        """Accepts a pool_size argument without raising."""
        engine = create_engine_for_uri("sqlite:///:memory:", pool_size=3)
        assert isinstance(engine, Engine)
        engine.dispose()


def test_get_metadata_returns_shared_metadata() -> None:
    """get_metadata() returns the same MetaData object used by Base."""
    assert get_metadata() is metadata
    assert Base.metadata is metadata


def test_module_exports() -> None:
    """__all__ exposes the expected symbols."""
    import hub_api.db.session as session_module

    assert set(session_module.__all__) == {
        "create_engine_for_uri",
        "get_metadata",
        "Base",
        "metadata",
    }


class TestDbInitModule:
    """Tests for hub_api.db.__init__'s penguin-dal ImportError guard."""

    def test_init_dal_and_get_db_exported(self) -> None:
        """When penguin-dal is installed, init_dal/get_db are real callables."""
        import hub_api.db as db_module

        assert set(db_module.__all__) == {"init_dal", "get_db"}
        # In this environment penguin-dal is installed, so both should be callable.
        assert callable(db_module.init_dal)
        assert callable(db_module.get_db)

    def test_import_error_guard_sets_none(self) -> None:
        """Simulates penguin_dal.quart_ext being unimportable; init_dal/get_db become None.

        Restoration must happen only after sys.modules is restored (mp.undo()),
        otherwise the restoring reload() would re-hit the same fake ImportError.
        """
        import importlib

        import hub_api.db as db_module

        mp = pytest.MonkeyPatch()
        mp.setitem(sys.modules, "penguin_dal.quart_ext", None)
        try:
            reloaded = importlib.reload(db_module)
            assert reloaded.init_dal is None
            assert reloaded.get_db is None
        finally:
            mp.undo()
            # Restore the real module for any subsequent tests in this process.
            importlib.reload(db_module)
