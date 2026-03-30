"""Tests for dashboard reports widget."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dashboard.reports.widget import (
    ReportStatus,
    ReportWidget,
    ReportWidgetConfig,
    ReportWidgetData,
)
from reporting.delivery.query_api import ReportQuery, ReportQueryResult, ReportType


@pytest.fixture
def sample_report_data():
    """Sample report data for testing."""
    return {
        "_source_file": "daily_20260329_123045",
        "report_type": "daily",
        "title": "Daily Report - 2026-03-29",
        "summary": "PnL: $1,234.56 | Trades: 42",
        "date": "2026-03-29",
        "status": "delivered",
        "total_pnl": 1234.56,
        "total_trades": 42,
        "generated_at": "2026-03-29T12:30:45Z",
    }


@pytest.fixture
def sample_widget_data(sample_report_data):
    """Sample widget data for testing."""
    return ReportWidgetData(
        report_id="daily_20260329_123045",
        report_type="daily",
        title="Daily Report - 2026-03-29",
        summary="PnL: $1,234.56 | Trades: 42",
        date=datetime.strptime("2026-03-29", "%Y-%m-%d").replace(tzinfo=UTC),
        status=ReportStatus.DELIVERED,
        download_urls={
            "json": "/reports/download/daily_20260329_123045.json",
            "csv": "/reports/download/daily_20260329_123045.csv",
            "pdf": "/reports/download/daily_20260329_123045.pdf",
        },
        generated_at=datetime.strptime(
            "2026-03-29T12:30:45Z", "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC),
    )


class TestReportWidgetData:
    """Tests for ReportWidgetData."""

    def test_widget_data_creation(self, sample_widget_data):
        """Test widget data can be created with all fields."""
        assert sample_widget_data.report_id == "daily_20260329_123045"
        assert sample_widget_data.report_type == "daily"
        assert sample_widget_data.status == ReportStatus.DELIVERED


class TestReportWidgetConfig:
    """Tests for ReportWidgetConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ReportWidgetConfig()
        assert config.max_reports == 10
        assert config.show_download_links is True
        assert config.auto_refresh == 300
        assert config.default_format == "json"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ReportWidgetConfig(max_reports=25, auto_refresh=60)
        assert config.max_reports == 25
        assert config.auto_refresh == 60


class TestReportWidget:
    """Tests for ReportWidget."""

    def test_widget_initialization(self):
        """Test widget initializes with empty cache."""
        widget = ReportWidget()
        assert widget._cache == []
        assert widget._cache_timestamp is None
        assert widget.config.max_reports == 10

    def test_widget_with_custom_config(self):
        """Test widget with custom configuration."""
        config = ReportWidgetConfig(max_reports=25)
        widget = ReportWidget(config=config)
        assert widget.config.max_reports == 25

    @pytest.mark.asyncio
    async def test_refresh_cache_calls_query_api(self, sample_report_data):
        """Test that _refresh_cache correctly queries the API with ReportQuery.

        This test verifies that the H-1 fix works - previously the code used
        type(rtype).query(...) which crashed because EnumMeta has no .query()
        method. The fix uses ReportQuery(...) dataclass instead.
        """
        widget = ReportWidget(reports_dir="/tmp/test_reports")

        # Mock ReportQueryResult
        mock_result = MagicMock(spec=ReportQueryResult)
        mock_result.reports = [sample_report_data]

        # Patch the ReportQueryAPI class - import is inside function so patch where it's used
        with patch("reporting.delivery.query_api.ReportQueryAPI") as MockAPI:
            mock_api_instance = MagicMock()
            mock_api_instance.query_reports = AsyncMock(return_value=mock_result)
            MockAPI.return_value = mock_api_instance

            # Clear any cached data to force refresh
            widget._cache_timestamp = None
            widget._cache = []

            # Call _refresh_cache
            await widget._refresh_cache()

            # Verify query_reports was called at least once
            assert mock_api_instance.query_reports.called

            # Verify that a ReportQuery was passed with correct parameters
            # We only check that ANY call uses ReportQuery with the right params
            call_args = mock_api_instance.query_reports.call_args
            query_arg = call_args[0][0]  # First positional argument

            # Verify it's a ReportQuery instance (not a broken type(rtype).query call)
            assert isinstance(query_arg, ReportQuery)
            assert query_arg.limit == 50
            assert query_arg.sort_by == "date"
            # Verify it's one of the expected report types
            assert query_arg.report_type in [
                ReportType.DAILY,
                ReportType.WEEKLY,
                ReportType.PAPER_HEALTH,
            ]

    @pytest.mark.asyncio
    async def test_refresh_cache_queries_all_report_types(self):
        """Test that _refresh_cache queries all three report types."""
        widget = ReportWidget(reports_dir="/tmp/test_reports")

        mock_result = MagicMock(spec=ReportQueryResult)
        mock_result.reports = []

        with patch("reporting.delivery.query_api.ReportQueryAPI") as MockAPI:
            mock_api_instance = MagicMock()
            mock_api_instance.query_reports = AsyncMock(return_value=mock_result)
            MockAPI.return_value = mock_api_instance

            widget._cache_timestamp = None
            widget._cache = []
            await widget._refresh_cache()

            # Should be called 3 times (DAILY, WEEKLY, PAPER_HEALTH)
            assert mock_api_instance.query_reports.call_count == 3

            # Verify each call got a ReportQuery
            for call in mock_api_instance.query_reports.call_args_list:
                query_arg = call[0][0]
                assert isinstance(query_arg, ReportQuery)
                assert query_arg.limit == 50
                assert query_arg.sort_by == "date"

    @pytest.mark.asyncio
    async def test_refresh_cache_respects_cache_age(self):
        """Test that _refresh_cache doesn't re-query within cache age."""
        widget = ReportWidget(reports_dir="/tmp/test_reports")

        # Set cache timestamp to now (within cache age)
        widget._cache_timestamp = datetime.now(UTC)

        with patch("reporting.delivery.query_api.ReportQueryAPI") as MockAPI:
            mock_api_instance = MagicMock()
            MockAPI.return_value = mock_api_instance

            await widget._refresh_cache()

            # Should NOT query because cache is fresh
            assert not mock_api_instance.query_reports.called

    @pytest.mark.asyncio
    async def test_get_latest_reports_returns_cached_data(self, sample_widget_data):
        """Test get_latest_reports returns cached data after refresh."""
        widget = ReportWidget(reports_dir="/tmp/test_reports")
        widget._cache = [sample_widget_data]
        widget._cache_timestamp = datetime.now(UTC)

        reports = await widget.get_latest_reports()

        assert len(reports) == 1
        assert reports[0].report_id == sample_widget_data.report_id

    @pytest.mark.asyncio
    async def test_get_latest_reports_filters_by_type(self, sample_widget_data):
        """Test get_latest_reports filters by report type."""
        widget = ReportWidget(reports_dir="/tmp/test_reports")
        widget._cache = [sample_widget_data]
        widget._cache_timestamp = datetime.now(UTC)

        # Filter by non-matching type should return empty
        reports = await widget.get_latest_reports(report_type="weekly")
        assert len(reports) == 0

        # Filter by matching type should return the report
        reports = await widget.get_latest_reports(report_type="daily")
        assert len(reports) == 1

    @pytest.mark.asyncio
    async def test_get_latest_reports_respects_limit(self, sample_widget_data):
        """Test get_latest_reports respects the limit parameter."""
        widget = ReportWidget(reports_dir="/tmp/test_reports")
        widget._cache = [sample_widget_data]
        widget._cache_timestamp = datetime.now(UTC)

        reports = await widget.get_latest_reports(limit=1)
        assert len(reports) == 1

    def test_convert_to_widget_data(self, sample_report_data):
        """Test _convert_to_widget_data converts report dict correctly."""
        widget = ReportWidget()

        result = widget._convert_to_widget_data(sample_report_data)

        assert result is not None
        assert result.report_id == sample_report_data["_source_file"]
        assert result.report_type == "daily"
        assert result.title == "Daily Report - 2026-03-29"

    def test_render_widget_html_empty(self):
        """Test rendering HTML with no reports."""
        widget = ReportWidget()
        html = widget.render_widget_html([])
        assert "No reports available" in html

    def test_render_widget_html_with_reports(self, sample_widget_data):
        """Test rendering HTML with reports."""
        widget = ReportWidget()
        html = widget.render_widget_html([sample_widget_data])
        assert "report-widget" in html
        assert sample_widget_data.title in html

    def test_render_widget_markdown_empty(self):
        """Test rendering Markdown with no reports."""
        widget = ReportWidget()
        md = widget.render_widget_markdown([])
        assert "No reports available" in md

    def test_render_widget_markdown_with_reports(self, sample_widget_data):
        """Test rendering Markdown with reports."""
        widget = ReportWidget()
        md = widget.render_widget_markdown([sample_widget_data])
        assert "report-widget" in md or "Recent Reports" in md

    def test_get_report_stats(self):
        """Test get_report_stats returns correct statistics."""
        widget = ReportWidget()
        widget._cache = []
        widget._cache_timestamp = datetime.now(UTC).replace(tzinfo=UTC)

        stats = widget.get_report_stats()

        assert stats["total_cached"] == 0
        assert stats["cache_timestamp"] is not None
        assert "max_reports" in stats["config"]

    @pytest.mark.asyncio
    async def test_search_reports(self, sample_widget_data):
        """Test search_reports finds matching reports."""
        widget = ReportWidget(reports_dir="/tmp/test_reports")
        widget._cache = [sample_widget_data]
        widget._cache_timestamp = datetime.now(UTC)

        # Search in title
        results = await widget.search_reports("Daily")
        assert len(results) == 1

        # Search in summary
        results = await widget.search_reports("PnL")
        assert len(results) == 1

        # No match
        results = await widget.search_reports("xyz123")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_reports_with_type_filter(self, sample_widget_data):
        """Test search_reports respects type filter."""
        widget = ReportWidget(reports_dir="/tmp/test_reports")
        widget._cache = [sample_widget_data]
        widget._cache_timestamp = datetime.now(UTC)

        # Match type
        results = await widget.search_reports("Daily", report_type="daily")
        assert len(results) == 1

        # Wrong type
        results = await widget.search_reports("Daily", report_type="weekly")
        assert len(results) == 0
