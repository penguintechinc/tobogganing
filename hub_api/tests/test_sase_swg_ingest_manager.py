"""Coverage-focused tests for CategoryIngestManager's fetch/parse/upsert pipeline.

The pre-existing test_sase_swg_ingest.py only covers the IngestStats dataclass
and a real-CacheClient write path; these tests drive ingest_source,
ingest_all, upsert_custom, and the private DB-facing helper methods directly,
including their exception-swallowing branches.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.sase.security.swg.ingest import CategoryIngestManager, IngestStats


class _FakeResponse:
    """Minimal aiohttp response stand-in."""

    def __init__(self, status: int = 200, text: str = "") -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text


class _FakeGetCM:
    """Async context manager returned by FakeSession.get()."""

    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    """Minimal aiohttp.ClientSession stand-in supporting session.get(url)."""

    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response
        self.urls: list[str] = []

    def get(self, url: str) -> _FakeGetCM:
        self.urls.append(url)
        return _FakeGetCM(self._response)


class _Source:
    """Minimal CategorySource stand-in with a configurable parse function."""

    def __init__(self, name: str, url: str, entries: object) -> None:
        self.name = name
        self.url = url
        self._entries = entries

    def parse(self, content: str) -> object:
        if isinstance(self._entries, Exception):
            raise self._entries
        return self._entries


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.domain_categories = MagicMock()
    db.domain_categories.select = AsyncMock(return_value=[])
    db.domain_categories.insert = AsyncMock(return_value="row-1")
    db.domain_categories.update = AsyncMock(return_value=1)
    return db


class TestGetSession:
    """Covers _get_session's lazy-init/reuse behavior."""

    @pytest.mark.asyncio
    async def test_creates_session_once_and_reuses(self) -> None:
        """A session is created on first call and reused on subsequent calls."""
        manager = CategoryIngestManager(_mock_db(), CacheClient(host="127.0.0.1", port=6399))

        session1 = await manager._get_session()
        session2 = await manager._get_session()

        assert session1 is session2
        await session1.close()


class TestIngestSource:
    """Covers ingest_source's fetch/parse/upsert pipeline and error handling."""

    @pytest.mark.asyncio
    async def test_fetch_non_200_status_returns_early(self) -> None:
        """A non-200 response returns stats with nothing scanned."""
        manager = CategoryIngestManager(_mock_db(), CacheClient(host="127.0.0.1", port=6399))
        manager._get_session = AsyncMock(return_value=_FakeSession(_FakeResponse(status=503)))
        source = _Source("feed1", "https://example.com/feed", [("a.com", "news")])

        stats = await manager.ingest_source(source)

        assert stats.scanned == 0
        assert stats.stored == 0

    @pytest.mark.asyncio
    async def test_fetch_exception_is_swallowed(self) -> None:
        """A session.get() exception is caught, returning empty stats."""
        manager = CategoryIngestManager(_mock_db(), CacheClient(host="127.0.0.1", port=6399))
        manager._get_session = AsyncMock(
            return_value=_FakeSession(RuntimeError("connection refused"))
        )
        source = _Source("feed1", "https://example.com/feed", [("a.com", "news")])

        stats = await manager.ingest_source(source)

        assert stats == IngestStats(source="feed1", scanned=0, stored=0, skipped=0)

    @pytest.mark.asyncio
    async def test_parse_exception_is_swallowed(self) -> None:
        """A source.parse() exception is caught, returning empty stats."""
        manager = CategoryIngestManager(_mock_db(), CacheClient(host="127.0.0.1", port=6399))
        manager._get_session = AsyncMock(
            return_value=_FakeSession(_FakeResponse(status=200, text="data"))
        )
        source = _Source("feed1", "https://example.com/feed", ValueError("bad format"))

        stats = await manager.ingest_source(source)

        assert stats.scanned == 0

    @pytest.mark.asyncio
    async def test_entries_processed_with_skip_and_error_branches(self) -> None:
        """Blank entries are skipped; per-entry exceptions are caught and skipped."""
        db = _mock_db()
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))
        manager._get_session = AsyncMock(
            return_value=_FakeSession(_FakeResponse(status=200, text="data"))
        )
        entries = [
            ("good.com", "news"),  # valid -> stored
            ("", "news"),  # blank domain -> skipped
            (None, "news"),  # None.lower() raises -> caught, skipped
        ]
        source = _Source("feed1", "https://example.com/feed", entries)

        stats = await manager.ingest_source(source)

        assert stats.scanned == 3
        assert stats.stored == 1
        assert stats.skipped == 2

    @pytest.mark.asyncio
    async def test_all_valid_entries_stored(self) -> None:
        """All-valid entries are all stored via _upsert_category + _write_cache."""
        db = _mock_db()
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))
        manager._get_session = AsyncMock(
            return_value=_FakeSession(_FakeResponse(status=200, text="data"))
        )
        entries = [("good.com", "news"), ("other.com", "shopping")]
        source = _Source("feed1", "https://example.com/feed", entries)

        stats = await manager.ingest_source(source)

        assert stats.scanned == 2
        assert stats.stored == 2
        assert stats.skipped == 0


class TestIngestAll:
    """Covers ingest_all's aggregation across multiple sources."""

    @pytest.mark.asyncio
    async def test_aggregates_stats_across_sources(self) -> None:
        """Stats from each source are summed into the aggregate result."""
        db = _mock_db()
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))
        manager._get_session = AsyncMock(
            return_value=_FakeSession(_FakeResponse(status=200, text="data"))
        )
        source1 = _Source("feed1", "https://example.com/1", [("a.com", "news")])
        source2 = _Source("feed2", "https://example.com/2", [("b.com", "shopping")])

        aggregate = await manager.ingest_all([source1, source2])

        assert aggregate.source == "all"
        assert aggregate.scanned == 2
        assert aggregate.stored == 2


class TestUpsertCustom:
    """Covers upsert_custom's validation and delegation to _upsert_category."""

    @pytest.mark.asyncio
    async def test_invalid_domain_or_category_is_skipped(self) -> None:
        """A blank domain/category logs a warning and returns without writing."""
        db = _mock_db()
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        await manager.upsert_custom("", "news", tenant="tenant-a")

        db.domain_categories.insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_upsert_writes_category_and_cache(self) -> None:
        """A valid custom category is upserted and the cache is refreshed."""
        db = _mock_db()
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        await manager.upsert_custom("Example.com", " Gambling ", tenant="tenant-a")

        db.domain_categories.insert.assert_called_once()
        inserted = db.domain_categories.insert.call_args[0][0]
        assert inserted["domain"] == "example.com"
        assert inserted["tenant"] == "tenant-a"


class TestUpsertCategory:
    """Covers _upsert_category's insert/update/exception branches."""

    @pytest.mark.asyncio
    async def test_inserts_when_no_existing_row(self) -> None:
        """No matching row -> a new row is inserted."""
        db = _mock_db()
        db.domain_categories.select = AsyncMock(return_value=[])
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        await manager._upsert_category("example.com", "news", source="feed1")

        db.domain_categories.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_when_existing_row_found(self) -> None:
        """A matching existing row is updated instead of inserted."""
        db = _mock_db()
        existing_row = MagicMock(categories=json.dumps(["news"]), updated_at=None)
        db.domain_categories.select = AsyncMock(return_value=[existing_row])
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        await manager._upsert_category("example.com", "news", source="feed1")

        db.domain_categories.update.assert_called_once()
        db.domain_categories.insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_exception_is_swallowed(self) -> None:
        """A DB failure during upsert is logged and swallowed, not raised."""
        db = _mock_db()
        db.domain_categories.select = AsyncMock(side_effect=RuntimeError("db down"))
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        await manager._upsert_category("example.com", "news")  # must not raise


class TestGetCategory:
    """Covers _get_category's row-matching and exception branches."""

    @pytest.mark.asyncio
    async def test_returns_matching_row(self) -> None:
        """A row whose categories JSON contains the target category is returned."""
        db = _mock_db()
        row = MagicMock(categories=json.dumps(["news", "shopping"]))
        db.domain_categories.select = AsyncMock(return_value=[row])
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        result = await manager._get_category("example.com", "shopping", "feed1", None)

        assert result is row

    @pytest.mark.asyncio
    async def test_malformed_row_json_is_skipped(self) -> None:
        """A row with malformed categories JSON is skipped, not raised."""
        db = _mock_db()
        bad_row = MagicMock(categories="not-json")
        db.domain_categories.select = AsyncMock(return_value=[bad_row])
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        result = await manager._get_category("example.com", "news", "feed1", None)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self) -> None:
        """Rows present but none contain the target category -> None."""
        db = _mock_db()
        row = MagicMock(categories=json.dumps(["shopping"]))
        db.domain_categories.select = AsyncMock(return_value=[row])
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        result = await manager._get_category("example.com", "news", "feed1", None)

        assert result is None

    @pytest.mark.asyncio
    async def test_select_exception_returns_none(self) -> None:
        """A DB failure while selecting returns None rather than raising."""
        db = _mock_db()
        db.domain_categories.select = AsyncMock(side_effect=RuntimeError("db down"))
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        result = await manager._get_category("example.com", "news", "feed1", None)

        assert result is None


class TestWriteCache:
    """Covers _write_cache's exception-swallowing branch."""

    @pytest.mark.asyncio
    async def test_db_exception_is_swallowed(self) -> None:
        """A DB failure while gathering categories for cache write is swallowed."""
        db = _mock_db()
        db.domain_categories.select = AsyncMock(side_effect=RuntimeError("db down"))
        manager = CategoryIngestManager(db, CacheClient(host="127.0.0.1", port=6399))

        await manager._write_cache("example.com")  # must not raise

    @pytest.mark.asyncio
    async def test_no_categories_skips_cache_write(self) -> None:
        """When no rows/categories exist, the cache is left untouched."""
        db = _mock_db()
        db.domain_categories.select = AsyncMock(return_value=[])
        cache = CacheClient(host="127.0.0.1", port=6399)
        manager = CategoryIngestManager(db, cache)

        await manager._write_cache("example.com")

        cached = await cache.get("sase:catcache", "example.com")
        assert cached is None
