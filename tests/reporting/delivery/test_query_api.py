"""Tests for ReportQueryAPI."""

import json
import os
import tempfile
from datetime import UTC, datetime

import pytest

from reporting.delivery.query_api import (
    ReportQuery,
    ReportQueryAPI,
    ReportQueryResult,
    ReportType,
    SortOrder,
)


class TestReportQuery:
    """Tests for ReportQuery dataclass."""

    def test_default_values(self):
        """Test default query values."""
        query = ReportQuery()
        assert query.report_type == ReportType.ALL
        assert query.start_date is None
        assert query.end_date is None
        assert query.limit == 50
        assert query.offset == 0
        assert query.sort_by == "date"
        assert query.sort_order == SortOrder.DESC

    def test_custom_values(self):
        """Test custom query values."""
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 31, tzinfo=UTC)
        query = ReportQuery(
            report_type=ReportType.DAILY,
            start_date=start,
            end_date=end,
            limit=25,
            offset=10,
            sort_by="total_pnl",
            sort_order=SortOrder.ASC,
        )
        assert query.report_type == ReportType.DAILY
        assert query.start_date == start
        assert query.end_date == end
        assert query.limit == 25
        assert query.offset == 10
        assert query.sort_by == "total_pnl"
        assert query.sort_order == SortOrder.ASC


class TestReportQueryResult:
    """Tests for ReportQueryResult dataclass."""

    def test_has_more_true(self):
        """Test has_more returns True when more results available."""
        result = ReportQueryResult(
            reports=[{"id": 1}, {"id": 2}],
            total=10,
            limit=2,
            offset=0,
        )
        assert result.has_more is True

    def test_has_more_false(self):
        """Test has_more returns False when no more results."""
        result = ReportQueryResult(
            reports=[{"id": 1}, {"id": 2}],
            total=2,
            limit=2,
            offset=0,
        )
        assert result.has_more is False

    def test_has_more_partial_page(self):
        """Test has_more with partial page."""
        result = ReportQueryResult(
            reports=[{"id": 1}],
            total=10,
            limit=5,
            offset=5,
        )
        assert result.has_more is True

    def test_to_dict(self):
        """Test to_dict conversion."""
        result = ReportQueryResult(
            reports=[{"id": 1}],
            total=1,
            limit=50,
            offset=0,
        )
        d = result.to_dict()
        assert d["reports"] == [{"id": 1}]
        assert d["total"] == 1
        assert d["limit"] == 50
        assert d["offset"] == 0
        assert d["has_more"] is False


class TestReportQueryAPI:
    """Tests for ReportQueryAPI."""

    @pytest.fixture
    def temp_reports_dir(self):
        """Create temporary reports directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create subdirectories
            os.makedirs(os.path.join(tmpdir, "daily"))
            os.makedirs(os.path.join(tmpdir, "weekly"))
            os.makedirs(os.path.join(tmpdir, "paper"))
            os.makedirs(os.path.join(tmpdir, "alerts"))
            yield tmpdir

    @pytest.fixture
    def api(self, temp_reports_dir):
        """Create API instance with temp directory."""
        return ReportQueryAPI(reports_dir=temp_reports_dir)

    def test_init_default(self):
        """Test API initialization with defaults."""
        api = ReportQueryAPI()
        assert api.reports_dir == os.getenv("REPORTS_DIR", "./reports")

    def test_init_custom_dir(self):
        """Test API initialization with custom directory."""
        api = ReportQueryAPI(reports_dir="/custom/path")
        assert api.reports_dir == "/custom/path"

    def test_get_report_directories_all(self, api):
        """Test _get_report_directories for ALL type."""
        dirs = api._get_report_directories(ReportType.ALL)
        assert len(dirs) == 4
        assert "daily" in dirs[0]
        assert "weekly" in dirs[1]
        assert "paper" in dirs[2]
        assert "alerts" in dirs[3]

    def test_get_report_directories_daily(self, api):
        """Test _get_report_directories for DAILY type."""
        dirs = api._get_report_directories(ReportType.DAILY)
        assert len(dirs) == 1
        assert "daily" in dirs[0]

    def test_get_report_directories_weekly(self, api):
        """Test _get_report_directories for WEEKLY type."""
        dirs = api._get_report_directories(ReportType.WEEKLY)
        assert len(dirs) == 1
        assert "weekly" in dirs[0]

    def test_parse_report_filename_standard(self, api):
        """Test _parse_report_filename with standard format."""
        dt = api._parse_report_filename("daily_20260329_123045.json")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 29
        assert dt.hour == 12
        assert dt.minute == 30
        assert dt.second == 45

    def test_parse_report_filename_anomaly(self, api):
        """Test _parse_report_filename with anomaly format."""
        dt = api._parse_report_filename("anomaly_pnl_spike_20260329.json")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 29

    def test_parse_report_filename_invalid(self, api):
        """Test _parse_report_filename with invalid filename."""
        dt = api._parse_report_filename("invalid_file.json")
        assert dt is None

    def test_load_report_file(self, api, temp_reports_dir):
        """Test _load_report_file."""
        filepath = os.path.join(temp_reports_dir, "daily", "test_report.json")
        test_data = {"date": "2026-03-29", "total_pnl": 1000.0}
        with open(filepath, "w") as f:
            json.dump(test_data, f)

        result = api._load_report_file(filepath)
        assert result == test_data

    def test_load_report_file_missing(self, api):
        """Test _load_report_file with missing file."""
        result = api._load_report_file("/nonexistent/file.json")
        assert result is None

    def test_filter_report_date_range(self, api):
        """Test _filter_report with date range."""
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 3, 31, tzinfo=UTC)
        query = ReportQuery(start_date=start, end_date=end)

        # Within range
        report = {"date": "2026-02-15"}
        assert api._filter_report(report, query) is True

        # Before range
        report = {"date": "2025-12-15"}
        assert api._filter_report(report, query) is False

        # After range
        report = {"date": "2026-04-15"}
        assert api._filter_report(report, query) is False

    def test_filter_report_no_dates(self, api):
        """Test _filter_report with no date fields."""
        query = ReportQuery()
        report = {"total_pnl": 1000.0}
        assert api._filter_report(report, query) is True

    def test_sort_reports_by_date_desc(self, api):
        """Test _sort_reports by date descending."""
        reports = [
            {"date": "2026-01-01"},
            {"date": "2026-03-01"},
            {"date": "2026-02-01"},
        ]
        sorted_reports = api._sort_reports(reports, "date", SortOrder.DESC)
        assert sorted_reports[0]["date"] == "2026-03-01"
        assert sorted_reports[1]["date"] == "2026-02-01"
        assert sorted_reports[2]["date"] == "2026-01-01"

    def test_sort_reports_by_date_asc(self, api):
        """Test _sort_reports by date ascending."""
        reports = [
            {"date": "2026-01-01"},
            {"date": "2026-03-01"},
            {"date": "2026-02-01"},
        ]
        sorted_reports = api._sort_reports(reports, "date", SortOrder.ASC)
        assert sorted_reports[0]["date"] == "2026-01-01"
        assert sorted_reports[1]["date"] == "2026-02-01"
        assert sorted_reports[2]["date"] == "2026-03-01"

    def test_sort_reports_by_total_pnl(self, api):
        """Test _sort_reports by total_pnl."""
        reports = [
            {"date": "2026-01-01", "total_pnl": 1000.0},
            {"date": "2026-02-01", "total_pnl": 3000.0},
            {"date": "2026-03-01", "total_pnl": 2000.0},
        ]
        sorted_reports = api._sort_reports(reports, "total_pnl", SortOrder.DESC)
        assert sorted_reports[0]["total_pnl"] == 3000.0
        assert sorted_reports[1]["total_pnl"] == 2000.0
        assert sorted_reports[2]["total_pnl"] == 1000.0

    @pytest.mark.asyncio
    async def test_query_reports_empty(self, api):
        """Test query_reports with empty directory."""
        result = await api.query_reports(ReportQuery())
        assert result.total == 0
        assert result.reports == []

    @pytest.mark.asyncio
    async def test_query_reports_with_files(self, api, temp_reports_dir):
        """Test query_reports with actual files."""
        # Create test report
        filepath = os.path.join(temp_reports_dir, "daily", "daily_20260329_120000.json")
        test_report = {
            "date": "2026-03-29",
            "total_pnl": 1500.0,
            "total_trades": 25,
            "generated_at": "2026-03-29T12:00:00Z",
        }
        with open(filepath, "w") as f:
            json.dump(test_report, f)

        result = await api.query_reports(ReportQuery(report_type=ReportType.DAILY))
        assert result.total == 1
        assert len(result.reports) == 1
        assert result.reports[0]["total_pnl"] == 1500.0

    @pytest.mark.asyncio
    async def test_query_reports_pagination(self, api, temp_reports_dir):
        """Test query_reports with pagination."""
        # Create multiple reports
        for i in range(5):
            filepath = os.path.join(
                temp_reports_dir, "daily", f"daily_202603{29 - i:02d}_120000.json"
            )
            with open(filepath, "w") as f:
                json.dump({"date": f"2026-03-{29 - i:02d}", "total_pnl": 100.0 * i}, f)

        # Test limit
        result = await api.query_reports(ReportQuery(limit=2))
        assert result.total == 5
        assert len(result.reports) == 2

        # Test offset
        result = await api.query_reports(ReportQuery(limit=2, offset=2))
        assert result.offset == 2

    @pytest.mark.asyncio
    async def test_query_reports_date_filter(self, api, temp_reports_dir):
        """Test query_reports with date filter."""
        # Create reports at different dates
        dates = ["2026-03-20", "2026-03-25", "2026-03-30"]
        for i, date in enumerate(dates):
            filepath = os.path.join(
                temp_reports_dir, "daily", f"daily_{date.replace('-', '')}_120000.json"
            )
            with open(filepath, "w") as f:
                json.dump({"date": date, "total_pnl": 100.0 * i}, f)

        # Filter by date range
        query = ReportQuery(
            start_date=datetime(2026, 3, 23, tzinfo=UTC),
            end_date=datetime(2026, 3, 28, tzinfo=UTC),
        )
        result = await api.query_reports(query)
        assert result.total == 1
        assert result.reports[0]["date"] == "2026-03-25"

    @pytest.mark.asyncio
    async def test_get_report_by_id(self, api, temp_reports_dir):
        """Test get_report_by_id."""
        filepath = os.path.join(temp_reports_dir, "daily", "daily_20260329_120000.json")
        test_report = {"date": "2026-03-29", "total_pnl": 1500.0}
        with open(filepath, "w") as f:
            json.dump(test_report, f)

        result = await api.get_report_by_id(
            "daily_20260329_120000.json", ReportType.DAILY
        )
        assert result is not None
        assert result["total_pnl"] == 1500.0

    @pytest.mark.asyncio
    async def test_get_report_by_id_not_found(self, api):
        """Test get_report_by_id with non-existent report."""
        result = await api.get_report_by_id("nonexistent_report.json")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_reports(self, api, temp_reports_dir):
        """Test get_latest_reports."""
        # Create reports
        for i in range(3):
            date = f"2026-03-{27 + i:02d}"
            filepath = os.path.join(
                temp_reports_dir, "daily", f"daily_{date.replace('-', '')}_120000.json"
            )
            with open(filepath, "w") as f:
                json.dump({"date": date, "total_pnl": 100.0 * i}, f)

        result = await api.get_latest_reports(ReportType.DAILY, limit=2)
        assert len(result) == 2
        # Should be sorted by date descending
        assert result[0]["date"] == "2026-03-29"

    @pytest.mark.asyncio
    async def test_get_report_count(self, api, temp_reports_dir):
        """Test get_report_count."""
        # Create multiple reports
        for i in range(3):
            filepath = os.path.join(
                temp_reports_dir, "daily", f"daily_202603{27 + i:02d}_120000.json"
            )
            with open(filepath, "w") as f:
                json.dump({"date": f"2026-03-{27 + i:02d}"}, f)

        count = await api.get_report_count(ReportType.DAILY)
        assert count == 3
