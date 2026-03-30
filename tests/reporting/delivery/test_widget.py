"""Tests for ReportWidget dashboard component."""

from datetime import UTC, datetime

import pytest

from dashboard.reports.widget import (
    ReportStatus,
    ReportWidget,
    ReportWidgetConfig,
    ReportWidgetData,
)


class TestReportStatus:
    """Tests for ReportStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert ReportStatus.GENERATED.value == "generated"
        assert ReportStatus.DELIVERED.value == "delivered"
        assert ReportStatus.FAILED.value == "failed"
        assert ReportStatus.PENDING.value == "pending"


class TestReportWidgetData:
    """Tests for ReportWidgetData dataclass."""

    def test_default_status(self):
        """Test default status is GENERATED."""
        data = ReportWidgetData(
            report_id="test_123",
            report_type="daily",
            title="Daily Report",
            summary="Test summary",
            date=datetime.now(UTC),
        )
        assert data.status == ReportStatus.GENERATED

    def test_custom_status(self):
        """Test custom status can be set."""
        data = ReportWidgetData(
            report_id="test_123",
            report_type="daily",
            title="Daily Report",
            summary="Test summary",
            date=datetime.now(UTC),
            status=ReportStatus.DELIVERED,
        )
        assert data.status == ReportStatus.DELIVERED

    def test_download_urls_default_empty(self):
        """Test download_urls defaults to empty dict."""
        data = ReportWidgetData(
            report_id="test_123",
            report_type="daily",
            title="Daily Report",
            summary="Test summary",
            date=datetime.now(UTC),
        )
        assert data.download_urls == {}

    def test_download_urls_custom(self):
        """Test custom download URLs."""
        urls = {"json": "/download/1.json", "csv": "/download/1.csv"}
        data = ReportWidgetData(
            report_id="test_123",
            report_type="daily",
            title="Daily Report",
            summary="Test summary",
            date=datetime.now(UTC),
            download_urls=urls,
        )
        assert data.download_urls["json"] == "/download/1.json"


class TestReportWidgetConfig:
    """Tests for ReportWidgetConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ReportWidgetConfig()
        assert config.max_reports == 10
        assert config.show_download_links is True
        assert config.auto_refresh == 300
        assert config.default_format == "json"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ReportWidgetConfig(
            max_reports=20,
            show_download_links=False,
            auto_refresh=600,
            default_format="csv",
        )
        assert config.max_reports == 20
        assert config.show_download_links is False
        assert config.auto_refresh == 600
        assert config.default_format == "csv"


class TestReportWidget:
    """Tests for ReportWidget."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return ReportWidgetConfig(
            max_reports=5,
            show_download_links=True,
            auto_refresh=300,
        )

    @pytest.fixture
    def widget(self, config, tmp_path):
        """Create widget instance with temp directory."""
        return ReportWidget(config=config, reports_dir=str(tmp_path))

    @pytest.fixture
    def sample_widget_data(self):
        """Create sample widget data."""
        return [
            ReportWidgetData(
                report_id="report_1",
                report_type="daily",
                title="Daily Report - 2026-03-29",
                summary="PnL: $1,500.00 | Trades: 25",
                date=datetime(2026, 3, 29, tzinfo=UTC),
                status=ReportStatus.DELIVERED,
                download_urls={
                    "json": "/reports/download/report_1.json",
                    "csv": "/reports/download/report_1.csv",
                    "pdf": "/reports/download/report_1.pdf",
                },
            ),
            ReportWidgetData(
                report_id="report_2",
                report_type="weekly",
                title="Weekly Report - 2026-12",
                summary="PnL: $10,000.00 | Trades: 150",
                date=datetime(2026, 3, 22, tzinfo=UTC),
                status=ReportStatus.GENERATED,
                download_urls={
                    "json": "/reports/download/report_2.json",
                    "csv": "/reports/download/report_2.csv",
                    "pdf": "/reports/download/report_2.pdf",
                },
            ),
        ]

    def test_init_defaults(self):
        """Test widget initialization with defaults."""
        widget = ReportWidget()
        assert widget.config.max_reports == 10
        assert widget.reports_dir == "./reports"

    def test_init_custom(self, config, tmp_path):
        """Test widget initialization with custom values."""
        widget = ReportWidget(config=config, reports_dir=str(tmp_path))
        assert widget.config.max_reports == 5
        assert widget.reports_dir == str(tmp_path)

    def test_render_widget_html_empty(self, widget):
        """Test rendering HTML with no reports."""
        html = widget.render_widget_html([])
        assert "no-reports" in html or "No reports" in html

    def test_render_widget_html_with_reports(self, widget, sample_widget_data):
        """Test rendering HTML with reports."""
        html = widget.render_widget_html(sample_widget_data)
        assert "Daily Report" in html
        assert "Weekly Report" in html
        assert "DELIVERED" in html or "Delivered" in html
        assert "GENERATED" in html or "Generated" in html

    def test_render_widget_html_download_links(self, widget, sample_widget_data):
        """Test that HTML includes download links when configured."""
        html = widget.render_widget_html(sample_widget_data)
        assert "/reports/download/" in html
        assert "JSON" in html
        assert "CSV" in html
        assert "PDF" in html

    def test_render_widget_html_no_download_links_when_disabled(
        self, widget, sample_widget_data
    ):
        """Test that HTML excludes download links when disabled."""
        widget.config.show_download_links = False
        html = widget.render_widget_html(sample_widget_data)
        assert "/reports/download/" not in html

    def test_render_widget_markdown_empty(self, widget):
        """Test rendering Markdown with no reports."""
        md = widget.render_widget_markdown([])
        assert "No reports" in md or "##" in md

    def test_render_widget_markdown_with_reports(self, widget, sample_widget_data):
        """Test rendering Markdown with reports."""
        md = widget.render_widget_markdown(sample_widget_data)
        assert "Daily Report" in md
        assert "Weekly Report" in md
        assert "PnL:" in md

    def test_render_widget_markdown_status_emoji(self, widget, sample_widget_data):
        """Test that Markdown includes status emoji."""
        md = widget.render_widget_markdown(sample_widget_data)
        # Status emoji should be present
        assert "✅" in md or "🔵" in md or "⚪" in md

    def test_render_widget_markdown_download_links(self, widget, sample_widget_data):
        """Test that Markdown includes download links."""
        md = widget.render_widget_markdown(sample_widget_data)
        assert "[JSON]" in md or "(/reports/" in md
        assert "[CSV]" in md or "(/reports/" in md

    @pytest.mark.asyncio
    async def test_search_reports_no_cache(self, widget):
        """Test search_reports when cache is empty."""
        results = await widget.search_reports("test")
        assert results == []  # No reports in cache

    @pytest.mark.asyncio
    async def test_search_reports_by_title(self, widget, sample_widget_data):
        """Test searching reports by title."""
        # Manually populate cache
        widget._cache = sample_widget_data

        results = await widget.search_reports("Daily")
        assert len(results) == 1
        assert results[0].title == "Daily Report - 2026-03-29"

    @pytest.mark.asyncio
    async def test_search_reports_by_summary(self, widget, sample_widget_data):
        """Test searching reports by summary content."""
        widget._cache = sample_widget_data

        results = await widget.search_reports("Trades: 150")
        assert len(results) == 1
        assert results[0].report_id == "report_2"

    @pytest.mark.asyncio
    async def test_search_reports_case_insensitive(self, widget, sample_widget_data):
        """Test search is case insensitive."""
        widget._cache = sample_widget_data

        results = await widget.search_reports("daily")
        assert len(results) == 1

        results = await widget.search_reports("WEEKLY")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_reports_with_type_filter(self, widget, sample_widget_data):
        """Test searching with report type filter."""
        widget._cache = sample_widget_data

        results = await widget.search_reports("Report", report_type="weekly")
        assert len(results) == 1
        assert results[0].report_type == "weekly"

    @pytest.mark.asyncio
    async def test_search_reports_no_match(self, widget, sample_widget_data):
        """Test search with no matching reports."""
        widget._cache = sample_widget_data

        results = await widget.search_reports("nonexistent search term")
        assert results == []

    def test_get_report_stats(self, widget, sample_widget_data):
        """Test get_report_stats returns correct structure."""
        widget._cache = sample_widget_data

        stats = widget.get_report_stats()
        assert stats["total_cached"] == 2
        assert "cache_timestamp" in stats
        assert "config" in stats
        assert stats["config"]["max_reports"] == 5

    def test_get_report_stats_empty_cache(self, widget):
        """Test get_report_stats with empty cache."""
        stats = widget.get_report_stats()
        assert stats["total_cached"] == 0
        assert stats["cache_timestamp"] is None

    def test_cache_initialization(self, widget):
        """Test cache starts empty."""
        assert widget._cache == []
        assert widget._cache_timestamp is None
