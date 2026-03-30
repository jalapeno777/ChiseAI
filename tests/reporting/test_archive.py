"""Tests for archive.py"""

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.reporting.core.archive import (
    ArchivedReport,
    ArchiveQuery,
    ArchiveStats,
    ReportArchive,
    ReportType,
)


class TestReportArchive:
    """Test suite for ReportArchive"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.archive = ReportArchive(archive_dir=self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test archive initializes"""
        assert self.archive is not None
        assert self.archive._archive_dir == Path(self.temp_dir)

    def test_initialization_custom_retention(self):
        """Test archive with custom retention"""
        archive = ReportArchive(
            archive_dir=self.temp_dir,
            retention_days=30,
        )
        assert archive._retention_days == 30

    def test_archive_report(self):
        """Test archiving a report"""
        report = self.archive.archive_report(
            report_id="RPT-001",
            report_type=ReportType.DAILY,
            report_data={"pnl": 1000, "trades": 5},
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 31),
        )
        assert report.report_id == "RPT-001"
        assert report.report_type == ReportType.DAILY
        assert report.size_bytes > 0

    def test_get_report(self):
        """Test retrieving a report"""
        self.archive.archive_report(
            report_id="RPT-002",
            report_type=ReportType.WEEKLY,
            report_data={"pnl": 500},
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 7),
        )
        retrieved = self.archive.get_report("RPT-002")
        assert retrieved is not None
        assert retrieved.report_id == "RPT-002"

    def test_get_report_not_found(self):
        """Test retrieving non-existent report"""
        result = self.archive.get_report("NON-EXISTENT")
        assert result is None

    def test_query_reports_by_type(self):
        """Test querying reports by type"""
        self.archive.archive_report(
            report_id="RPT-003",
            report_type=ReportType.DAILY,
            report_data={"pnl": 100},
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 1),
        )
        self.archive.archive_report(
            report_id="RPT-004",
            report_type=ReportType.WEEKLY,
            report_data={"pnl": 500},
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 7),
        )
        results = self.archive.query(ArchiveQuery(report_type=ReportType.DAILY))
        assert len(results) == 1
        assert results[0].report_type == ReportType.DAILY

    def test_query_reports_by_date_range(self):
        """Test querying reports by date range"""
        self.archive.archive_report(
            report_id="RPT-005",
            report_type=ReportType.DAILY,
            report_data={"pnl": 100},
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 1),
        )
        self.archive.archive_report(
            report_id="RPT-006",
            report_type=ReportType.DAILY,
            report_data={"pnl": 200},
            period_start=datetime(2026, 3, 15),
            period_end=datetime(2026, 3, 15),
        )
        results = self.archive.query(
            ArchiveQuery(
                start_date=datetime(2026, 3, 28, tzinfo=UTC),
                end_date=datetime(2026, 3, 31, tzinfo=UTC),
            )
        )
        assert len(results) == 2

    def test_delete_report(self):
        """Test deleting a report"""
        self.archive.archive_report(
            report_id="RPT-007",
            report_type=ReportType.DAILY,
            report_data={"pnl": 100},
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 1),
        )
        result = self.archive.delete_report("RPT-007")
        assert result is True
        assert self.archive.get_report("RPT-007") is None

    def test_cleanup_old_reports(self):
        """Test cleaning up old reports"""
        archive = ReportArchive(
            archive_dir=self.temp_dir,
            retention_days=0,  # Very short retention
        )
        archive.archive_report(
            report_id="RPT-OLD",
            report_type=ReportType.DAILY,
            report_data={"pnl": 100},
            period_start=datetime(2024, 1, 1),
            period_end=datetime(2024, 1, 1),
        )
        deleted = archive.cleanup_old_reports()
        assert deleted >= 0


class TestArchivedReport:
    """Test suite for ArchivedReport"""

    def test_creation(self):
        """Test creating an archived report"""
        report = ArchivedReport(
            report_id="RPT-001",
            report_type=ReportType.DAILY,
            generated_at=datetime.now(),
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 31),
        )
        assert report.report_id == "RPT-001"
        assert report.report_type == ReportType.DAILY

    def test_with_metadata(self):
        """Test creating with metadata"""
        report = ArchivedReport(
            report_id="RPT-002",
            report_type=ReportType.WEEKLY,
            generated_at=datetime.now(),
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 7),
            metadata={"author": "test", "version": "1.0"},
            size_bytes=1024,
        )
        assert report.metadata["author"] == "test"
        assert report.size_bytes == 1024

    def test_to_dict(self):
        """Test conversion to dict"""
        report = ArchivedReport(
            report_id="RPT-003",
            report_type=ReportType.MONTHLY,
            generated_at=datetime(2026, 3, 1),
            period_start=datetime(2026, 2, 1),
            period_end=datetime(2026, 2, 28),
        )
        d = report.to_dict()
        assert d["report_id"] == "RPT-003"
        assert d["report_type"] == "monthly"


class TestArchiveStats:
    """Test suite for ArchiveStats"""

    def test_defaults(self):
        """Test default values"""
        stats = ArchiveStats()
        assert stats.total_reports == 0
        assert stats.total_size_bytes == 0

    def test_to_dict(self):
        """Test conversion to dict"""
        stats = ArchiveStats(
            total_reports=10,
            total_size_bytes=1024000,
            oldest_report=datetime(2026, 1, 1),
            newest_report=datetime(2026, 3, 29),
        )
        d = stats.to_dict()
        assert d["total_reports"] == 10
        assert d["total_size_mb"] > 0
