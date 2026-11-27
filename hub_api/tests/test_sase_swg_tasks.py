"""Coverage tests for SWG Celery tasks (_categorize_domain_async, categorize_domain,
refresh_categories_daily).

All heavy dependencies (fetcher, scraper, classifier, DAL, cache, config) are
imported locally inside these functions, so each is patched at its own
source module for the duration of each test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.sase.security.swg.tasks import (
    _categorize_domain_async,
    categorize_domain,
    refresh_categories_daily,
)

TASKS_MOD = "hub_api.modules.sase.security.swg.tasks"


def _patch_config() -> object:
    """Patch Config/build_db_uri/AsyncDB at their source modules for tasks.py's
    local imports; returns a context-manager stack via ExitStack-friendly usage.
    """
    return (
        patch("hub_api.config.Config", return_value=MagicMock()),
        patch("hub_api.config.build_db_uri", return_value="sqlite:///:memory:"),
        patch("penguin_dal.AsyncDB"),
    )


class TestCategorizeDomainAsync:
    """Covers _categorize_domain_async's fetch/scrape/classify/write-back pipeline."""

    @pytest.mark.asyncio
    async def test_no_html_returns_early(self) -> None:
        """An empty fetch result stops the pipeline before scraping."""
        with patch(
            "hub_api.modules.sase.security.swg.tier2.fetcher.fetch",
            new=AsyncMock(return_value=""),
        ):
            await _categorize_domain_async("example.com", "tenant-a")  # must not raise

    @pytest.mark.asyncio
    async def test_no_metadata_returns_early(self) -> None:
        """Empty scraped metadata stops the pipeline before classification."""
        with (
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.fetch",
                new=AsyncMock(return_value="<html></html>"),
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.scraper.extract_metadata",
                return_value="",
            ),
        ):
            await _categorize_domain_async("example.com", "tenant-a")  # must not raise

    @pytest.mark.asyncio
    async def test_low_confidence_returns_early(self) -> None:
        """A classification below the confidence threshold does not write back."""
        with (
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.fetch",
                new=AsyncMock(return_value="<html>content</html>"),
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.scraper.extract_metadata",
                return_value="some page text",
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.classifier.DomainClassifier"
            ) as MockClassifier,
        ):
            MockClassifier.return_value.classify.return_value = ("gambling", 0.1)
            await _categorize_domain_async("example.com", "tenant-a")  # must not raise

    @pytest.mark.asyncio
    async def test_confident_classification_inserts_new_row(self) -> None:
        """A confident classification with no existing row triggers an insert + cache write."""
        mock_db = MagicMock()
        mock_db.domain_categories.select = AsyncMock(return_value=[])
        mock_db.domain_categories.insert = AsyncMock(return_value="row-1")
        mock_cache = MagicMock()
        mock_cache.set = AsyncMock()

        with (
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.fetch",
                new=AsyncMock(return_value="<html>content</html>"),
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.scraper.extract_metadata",
                return_value="some page text",
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.classifier.DomainClassifier"
            ) as MockClassifier,
            patch("hub_api.config.Config", return_value=MagicMock()),
            patch("hub_api.config.build_db_uri", return_value="sqlite:///:memory:"),
            patch("penguin_dal.AsyncDB", return_value=mock_db),
            patch("hub_api.cache.CacheClient", return_value=mock_cache),
        ):
            MockClassifier.return_value.classify.return_value = ("gambling", 0.95)
            await _categorize_domain_async("example.com", "tenant-a")

        mock_db.domain_categories.insert.assert_called_once()
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_confident_classification_updates_existing_row(self) -> None:
        """A confident classification with an existing AI row updates it instead."""
        existing_row = MagicMock(updated_at=None)
        mock_db = MagicMock()
        mock_db.domain_categories.select = AsyncMock(return_value=[existing_row])
        mock_db.domain_categories.update = AsyncMock()
        mock_cache = MagicMock()
        mock_cache.set = AsyncMock()

        with (
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.fetch",
                new=AsyncMock(return_value="<html>content</html>"),
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.scraper.extract_metadata",
                return_value="some page text",
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.classifier.DomainClassifier"
            ) as MockClassifier,
            patch("hub_api.config.Config", return_value=MagicMock()),
            patch("hub_api.config.build_db_uri", return_value="sqlite:///:memory:"),
            patch("penguin_dal.AsyncDB", return_value=mock_db),
            patch("hub_api.cache.CacheClient", return_value=mock_cache),
        ):
            MockClassifier.return_value.classify.return_value = ("gambling", 0.95)
            await _categorize_domain_async("example.com", "tenant-a")

        mock_db.domain_categories.update.assert_called_once_with(existing_row)

    @pytest.mark.asyncio
    async def test_write_back_exception_is_swallowed(self) -> None:
        """A DB failure during write-back is caught, not raised."""
        mock_db = MagicMock()
        mock_db.domain_categories.select = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.fetch",
                new=AsyncMock(return_value="<html>content</html>"),
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.scraper.extract_metadata",
                return_value="some page text",
            ),
            patch(
                "hub_api.modules.sase.security.swg.tier2.classifier.DomainClassifier"
            ) as MockClassifier,
            patch("hub_api.config.Config", return_value=MagicMock()),
            patch("hub_api.config.build_db_uri", return_value="sqlite:///:memory:"),
            patch("penguin_dal.AsyncDB", return_value=mock_db),
        ):
            MockClassifier.return_value.classify.return_value = ("gambling", 0.95)
            await _categorize_domain_async("example.com", "tenant-a")  # must not raise

    @pytest.mark.asyncio
    async def test_outer_fetch_exception_is_swallowed(self) -> None:
        """An exception raised by fetch() itself is caught by the outer handler."""
        with patch(
            "hub_api.modules.sase.security.swg.tier2.fetcher.fetch",
            new=AsyncMock(side_effect=RuntimeError("network down")),
        ):
            await _categorize_domain_async("example.com", "tenant-a")  # must not raise


class TestCategorizeDomainTask:
    """Covers the Celery-task wrapper's success and error-swallowing paths."""

    def test_task_invokes_asyncio_run(self) -> None:
        """Calling the task runs asyncio.run() over the async implementation."""
        with patch(f"{TASKS_MOD}.asyncio.run") as mock_run:
            categorize_domain("example.com", "tenant-a")

        mock_run.assert_called_once()

    def test_task_swallows_exceptions(self) -> None:
        """An exception from asyncio.run() is logged and swallowed (no retry)."""
        with patch(f"{TASKS_MOD}.asyncio.run", side_effect=RuntimeError("boom")):
            categorize_domain("example.com", "tenant-a")  # must not raise


def _source(name: str) -> MagicMock:
    """Build a fake CategorySource with only a name."""
    src = MagicMock()
    src.name = name
    return src


def _stats(scanned: int, stored: int = 0, skipped: int = 0) -> MagicMock:
    """Build fake IngestStats."""
    return MagicMock(scanned=scanned, stored=stored, skipped=skipped)


class TestRunCategoryRefresh:
    """Covers _run_category_refresh outcome accounting and failure paths."""

    @pytest.mark.asyncio
    async def test_all_sources_succeed(self) -> None:
        """Every source ingesting entries yields real totals and no failures."""
        from hub_api.modules.sase.security.swg.tasks import _run_category_refresh

        ingester = MagicMock()
        ingester.ingest_source = AsyncMock(side_effect=[_stats(5, 4, 1), _stats(3, 3)])
        result = await _run_category_refresh(ingester, [_source("a"), _source("b")])
        assert result == {"sources": 2, "failed": [], "scanned": 8, "stored": 7, "skipped": 1}

    @pytest.mark.asyncio
    async def test_partial_failure_reported(self) -> None:
        """A source scanning nothing is reported as failed without failing the run."""
        from hub_api.modules.sase.security.swg.tasks import _run_category_refresh

        ingester = MagicMock()
        ingester.ingest_source = AsyncMock(side_effect=[_stats(0), _stats(2, 2)])
        result = await _run_category_refresh(ingester, [_source("dead"), _source("ok")])
        assert result["failed"] == ["dead"]
        assert result["stored"] == 2

    @pytest.mark.asyncio
    async def test_all_sources_fail_raises(self) -> None:
        """When every source ingests nothing, the run raises instead of logging success."""
        from hub_api.modules.sase.security.swg.tasks import _run_category_refresh

        ingester = MagicMock()
        ingester.ingest_source = AsyncMock(return_value=_stats(0))
        with pytest.raises(RuntimeError, match="all 2 sources failed"):
            await _run_category_refresh(ingester, [_source("a"), _source("b")])

    @pytest.mark.asyncio
    async def test_no_sources_raises(self) -> None:
        """An empty source list is a configuration error, not a success."""
        from hub_api.modules.sase.security.swg.tasks import _run_category_refresh

        with pytest.raises(RuntimeError, match="no category sources"):
            await _run_category_refresh(MagicMock(), [])


class TestRefreshCategoriesDaily:
    """Covers refresh_categories_daily wiring to the real source registry."""

    def test_refresh_ingests_registered_sources_and_closes_session(self) -> None:
        """A run ingests every CATEGORY_SOURCES entry and closes the HTTP session."""
        from hub_api.modules.sase.security.swg.sources import CATEGORY_SOURCES

        mock_db = MagicMock()
        mock_cache = MagicMock()
        with (
            patch("hub_api.config.Config", return_value=MagicMock()),
            patch("hub_api.config.build_db_uri", return_value="sqlite:///:memory:"),
            patch("penguin_dal.AsyncDB", return_value=mock_db),
            patch("hub_api.cache.CacheClient", return_value=mock_cache),
            patch("hub_api.modules.sase.security.swg.ingest.CategoryIngestManager") as MockIngester,
        ):
            inst = MockIngester.return_value
            inst.ingest_source = AsyncMock(return_value=_stats(1, 1))
            inst.session = MagicMock(close=AsyncMock())
            refresh_categories_daily()

        MockIngester.assert_called_once_with(mock_db, mock_cache)
        assert inst.ingest_source.await_count == len(CATEGORY_SOURCES) > 0
        inst.session.close.assert_awaited_once()

    def test_refresh_all_failed_propagates(self) -> None:
        """All sources failing propagates so the scheduler records a failed run."""
        with (
            patch("hub_api.config.Config", return_value=MagicMock()),
            patch("hub_api.config.build_db_uri", return_value="sqlite:///:memory:"),
            patch("penguin_dal.AsyncDB"),
            patch("hub_api.cache.CacheClient"),
            patch("hub_api.modules.sase.security.swg.ingest.CategoryIngestManager") as MockIngester,
        ):
            MockIngester.return_value.ingest_source = AsyncMock(return_value=_stats(0))
            MockIngester.return_value.session = None
            with pytest.raises(RuntimeError, match="sources failed"):
                refresh_categories_daily()
