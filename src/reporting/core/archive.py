"""Report Archive for the core report generation engine.

Provides:
- Store generated reports with metadata
- Query reports by date range, type
- Archive retention policy

For ST-NS-023-T1: Core Report Generation Engine
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReportType(Enum):
    """Types of reports."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


@dataclass
class ArchivedReport:
    """An archived report.

    Attributes:
        report_id: Unique report identifier
        report_type: Type of report
        generated_at: When the report was generated
        period_start: Start of the reporting period
        period_end: End of the reporting period
        file_path: Path to the archived report file
        metadata: Additional report metadata
        size_bytes: Size of the report file
    """

    report_id: str
    report_type: ReportType
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    file_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "report_type": self.report_type.value,
            "generated_at": self.generated_at.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "file_path": self.file_path,
            "metadata": self.metadata,
            "size_bytes": self.size_bytes,
        }


@dataclass
class ArchiveQuery:
    """Query parameters for archive search.

    Attributes:
        report_type: Filter by report type
        start_date: Filter reports after this date
        end_date: Filter reports before this date
        limit: Maximum number of results
        offset: Offset for pagination
    """

    report_type: ReportType | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int = 100
    offset: int = 0


@dataclass
class ArchiveStats:
    """Archive statistics.

    Attributes:
        total_reports: Total number of archived reports
        total_size_bytes: Total size of archived reports
        reports_by_type: Count of reports by type
        oldest_report: Oldest report date
        newest_report: Newest report date
    """

    total_reports: int = 0
    total_size_bytes: int = 0
    reports_by_type: dict[str, int] = field(default_factory=dict)
    oldest_report: datetime | None = None
    newest_report: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_reports": self.total_reports,
            "total_size_mb": round(self.total_size_bytes / 1024 / 1024, 2),
            "reports_by_type": self.reports_by_type,
            "oldest_report": (
                self.oldest_report.isoformat() if self.oldest_report else None
            ),
            "newest_report": (
                self.newest_report.isoformat() if self.newest_report else None
            ),
        }


class ReportArchive:
    """Archive reports with queryable history.

    Supports:
    - Store reports with metadata
    - Query by date range, type
    - Retention policy management
    - Archive statistics

    Attributes:
        archive_dir: Base directory for archived reports
        retention_days: Days to retain reports
        index_filename: Name of the index file
    """

    def __init__(
        self,
        archive_dir: str = "./reports/archive",
        retention_days: int = 90,
    ) -> None:
        """Initialize report archive.

        Args:
            archive_dir: Base directory for archived reports
            retention_days: Days to retain reports (default: 90)
        """
        self._archive_dir = Path(archive_dir)
        self._retention_days = retention_days
        self._index_file = self._archive_dir / "archive_index.json"
        self._reports: list[ArchivedReport] = []

        # Ensure archive directory exists
        self._archive_dir.mkdir(parents=True, exist_ok=True)

        # Load existing index
        self._load_index()

        logger.info(
            f"ReportArchive initialized: dir={archive_dir}, retention={retention_days}days"
        )

    def _load_index(self) -> None:
        """Load the archive index from disk."""
        if self._index_file.exists():
            try:
                with open(self._index_file) as f:
                    data = json.load(f)
                    self._reports = [
                        self._deserialize_report(r) for r in data.get("reports", [])
                    ]
                logger.debug(f"Loaded {len(self._reports)} reports from index")
            except Exception as e:
                logger.warning(f"Failed to load archive index: {e}")
                self._reports = []
        else:
            self._reports = []

    def _save_index(self) -> None:
        """Save the archive index to disk."""
        try:
            data = {
                "reports": [self._serialize_report(r) for r in self._reports],
                "last_updated": datetime.now(UTC).isoformat(),
            }
            with open(self._index_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved index with {len(self._reports)} reports")
        except Exception as e:
            logger.error(f"Failed to save archive index: {e}")

    def _serialize_report(self, report: ArchivedReport) -> dict[str, Any]:
        """Serialize a report to dictionary.

        Args:
            report: Report to serialize

        Returns:
            Dictionary representation
        """
        return report.to_dict()

    def _deserialize_report(self, data: dict[str, Any]) -> ArchivedReport:
        """Deserialize a report from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            ArchivedReport object
        """
        return ArchivedReport(
            report_id=data["report_id"],
            report_type=ReportType(data["report_type"]),
            generated_at=datetime.fromisoformat(data["generated_at"]),
            period_start=datetime.fromisoformat(data["period_start"]),
            period_end=datetime.fromisoformat(data["period_end"]),
            file_path=data.get("file_path", ""),
            metadata=data.get("metadata", {}),
            size_bytes=data.get("size_bytes", 0),
        )

    def archive_report(
        self,
        report_id: str,
        report_type: ReportType,
        report_data: dict[str, Any],
        period_start: datetime,
        period_end: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> ArchivedReport:
        """Archive a report.

        Args:
            report_id: Unique report identifier
            report_type: Type of report
            report_data: Report data to archive
            period_start: Start of the reporting period
            period_end: End of the reporting period
            metadata: Additional metadata

        Returns:
            Created ArchivedReport
        """
        # Create report directory
        type_dir = self._archive_dir / report_type.value
        type_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        filename = f"{report_id}_{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}.json"
        file_path = type_dir / filename

        # Save report data
        with open(file_path, "w") as f:
            json.dump(report_data, f, indent=2)

        # Get file size
        size_bytes = file_path.stat().st_size

        # Create archive record
        report = ArchivedReport(
            report_id=report_id,
            report_type=report_type,
            generated_at=datetime.now(UTC),
            period_start=period_start,
            period_end=period_end,
            file_path=str(file_path),
            metadata=metadata or {},
            size_bytes=size_bytes,
        )

        # Add to index
        self._reports.append(report)
        self._save_index()

        logger.info(
            f"Archived report: {report_id} ({report_type.value}) -> {file_path}"
        )

        return report

    def get_report(self, report_id: str) -> ArchivedReport | None:
        """Get a report by ID.

        Args:
            report_id: Report identifier

        Returns:
            ArchivedReport if found, None otherwise
        """
        for report in self._reports:
            if report.report_id == report_id:
                return report
        return None

    def query(
        self,
        query: ArchiveQuery | None = None,
    ) -> list[ArchivedReport]:
        """Query archived reports.

        Args:
            query: Query parameters (uses default if None)

        Returns:
            List of matching ArchivedReport objects
        """
        if query is None:
            query = ArchiveQuery()

        results = self._reports.copy()

        # Filter by report type
        if query.report_type:
            results = [r for r in results if r.report_type == query.report_type]

        # Filter by start date
        if query.start_date:
            results = [r for r in results if r.generated_at >= query.start_date]

        # Filter by end date
        if query.end_date:
            results = [r for r in results if r.generated_at <= query.end_date]

        # Sort by generated_at descending
        results.sort(key=lambda r: r.generated_at, reverse=True)

        # Apply pagination
        total = len(results)
        results = results[query.offset : query.offset + query.limit]

        logger.debug(f"Query returned {len(results)} of {total} reports")

        return results

    def get_reports_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        report_type: ReportType | None = None,
    ) -> list[ArchivedReport]:
        """Get reports within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            report_type: Optional report type filter

        Returns:
            List of matching reports
        """
        query = ArchiveQuery(
            start_date=start_date,
            end_date=end_date,
            report_type=report_type,
        )
        return self.query(query)

    def delete_report(self, report_id: str) -> bool:
        """Delete a report from the archive.

        Args:
            report_id: Report identifier

        Returns:
            True if deleted, False if not found
        """
        for i, report in enumerate(self._reports):
            if report.report_id == report_id:
                # Delete file if exists
                if report.file_path and os.path.exists(report.file_path):
                    try:
                        os.remove(report.file_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete report file: {e}")

                # Remove from index
                self._reports.pop(i)
                self._save_index()

                logger.info(f"Deleted report: {report_id}")
                return True

        return False

    def cleanup_old_reports(self) -> int:
        """Clean up reports older than retention period.

        Returns:
            Number of reports deleted
        """
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        deleted = 0

        # Find reports to delete
        to_delete = [r for r in self._reports if r.generated_at < cutoff]

        for report in to_delete:
            if self.delete_report(report.report_id):
                deleted += 1

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old reports")

        return deleted

    def get_statistics(self) -> ArchiveStats:
        """Get archive statistics.

        Returns:
            ArchiveStats with current statistics
        """
        if not self._reports:
            return ArchiveStats()

        total_size = sum(r.size_bytes for r in self._reports)
        by_type: dict[str, int] = {}

        for report in self._reports:
            type_key = report.report_type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1

        sorted_reports = sorted(self._reports, key=lambda r: r.generated_at)

        stats = ArchiveStats(
            total_reports=len(self._reports),
            total_size_bytes=total_size,
            reports_by_type=by_type,
            oldest_report=sorted_reports[0].generated_at,
            newest_report=sorted_reports[-1].generated_at,
        )

        return stats

    def load_report_content(self, report_id: str) -> dict[str, Any] | None:
        """Load the content of a report.

        Args:
            report_id: Report identifier

        Returns:
            Report content as dictionary, or None if not found
        """
        report = self.get_report(report_id)
        if not report or not report.file_path:
            return None

        if not os.path.exists(report.file_path):
            logger.warning(f"Report file not found: {report.file_path}")
            return None

        try:
            with open(report.file_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load report content: {e}")
            return None

    def set_retention_days(self, days: int) -> None:
        """Set retention period.

        Args:
            days: Number of days to retain reports
        """
        self._retention_days = days
        logger.info(f"Retention period set to {days} days")
