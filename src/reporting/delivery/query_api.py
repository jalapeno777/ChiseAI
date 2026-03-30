"""Report query API for historical report retrieval.

Provides REST-style API for querying historical reports
with filtering, pagination, and sorting support.

For ST-NS-023-T2: Report Delivery & Dashboard Integration
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReportType(Enum):
    """Supported report types."""

    DAILY = "daily"
    WEEKLY = "weekly"
    PAPER_HEALTH = "paper_health"
    ANOMALY = "anomaly"
    ALL = "all"


class SortOrder(Enum):
    """Sort order options."""

    ASC = "asc"
    DESC = "desc"


@dataclass
class ReportQuery:
    """Query parameters for report search.

    Attributes:
        report_type: Type of report to query
        start_date: Start of date range
        end_date: End of date range
        limit: Maximum number of results
        offset: Pagination offset
        sort_by: Field to sort by
        sort_order: Sort direction
    """

    report_type: ReportType = ReportType.ALL
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int = 50
    offset: int = 0
    sort_by: str = "date"
    sort_order: SortOrder = SortOrder.DESC


@dataclass
class ReportQueryResult:
    """Result of a report query.

    Attributes:
        reports: List of report dictionaries
        total: Total number of matching reports
        limit: Applied limit
        offset: Applied offset
        has_more: Whether more results are available
    """

    reports: list[dict[str, Any]]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        """Check if more results are available."""
        return self.offset + len(self.reports) < self.total

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "reports": self.reports,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "has_more": self.has_more,
        }


class ReportQueryAPI:
    """REST-style API for querying historical reports.

    Features:
    - Filter by date range and report type
    - Pagination with offset and limit
    - Configurable sort field and order
    - File-based storage with directory scanning

    Attributes:
        reports_dir: Base directory for stored reports
    """

    def __init__(self, reports_dir: str | None = None) -> None:
        """Initialize report query API.

        Args:
            reports_dir: Base directory for reports (default: ./reports)
        """
        self.reports_dir = reports_dir or os.getenv("REPORTS_DIR", "./reports")

    def _get_report_directories(self, report_type: ReportType) -> list[str]:
        """Get directories to scan for report type.

        Args:
            report_type: Type of report

        Returns:
            List of directory paths
        """
        if report_type == ReportType.ALL:
            return [
                os.path.join(self.reports_dir, "daily"),
                os.path.join(self.reports_dir, "weekly"),
                os.path.join(self.reports_dir, "paper"),
                os.path.join(self.reports_dir, "alerts"),
            ]

        type_map = {
            ReportType.DAILY: "daily",
            ReportType.WEEKLY: "weekly",
            ReportType.PAPER_HEALTH: "paper/daily",
            ReportType.ANOMALY: "alerts",
        }

        return [os.path.join(self.reports_dir, type_map.get(report_type, ""))]

    def _parse_report_filename(self, filename: str) -> datetime | None:
        """Parse datetime from report filename.

        Args:
            filename: Report filename

        Returns:
            Parsed datetime or None
        """
        import re

        # Expected format: daily_20260329_123045.json
        match = re.search(r"_(\d{8})_(\d{6})", filename)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            try:
                return datetime.strptime(
                    f"{date_str}_{time_str}", "%Y%m%d_%H%M%S"
                ).replace(tzinfo=UTC)
            except ValueError:
                pass

        # Try parsing just date: anomaly_pnl_spike_20260329.json
        match = re.search(r"_(\d{8})", filename)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=UTC)
            except ValueError:
                pass

        return None

    def _load_report_file(self, filepath: str) -> dict[str, Any] | None:
        """Load report from JSON file.

        Args:
            filepath: Path to report file

        Returns:
            Report dictionary or None
        """
        try:
            with open(filepath) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load report {filepath}: {e}")
            return None

    def _filter_report(
        self,
        report: dict[str, Any],
        query: ReportQuery,
    ) -> bool:
        """Check if report matches query filters.

        Args:
            report: Report dictionary
            query: Query parameters

        Returns:
            True if report matches filters
        """
        # Parse date from report
        report_date_str = report.get("date") or report.get("start_date")
        if report_date_str:
            try:
                report_date = datetime.strptime(report_date_str, "%Y-%m-%d").replace(
                    tzinfo=UTC
                )
            except ValueError:
                report_date = None
        else:
            report_date = None

        # Date range filter - return False if outside date range
        return not (
            (query.start_date and report_date and report_date < query.start_date)
            or (query.end_date and report_date and report_date > query.end_date)
        )

    def _sort_reports(
        self,
        reports: list[dict[str, Any]],
        sort_by: str,
        sort_order: SortOrder,
    ) -> list[dict[str, Any]]:
        """Sort reports by field.

        Args:
            reports: List of report dictionaries
            sort_by: Field to sort by
            sort_order: Sort direction

        Returns:
            Sorted list
        """
        reverse = sort_order == SortOrder.DESC

        def get_sort_key(report: dict[str, Any]) -> Any:
            if sort_by == "date":
                date_str = report.get("date") or report.get("start_date")
                if date_str:
                    try:
                        return datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        return datetime.min.replace(tzinfo=UTC)
                return datetime.min.replace(tzinfo=UTC)
            elif sort_by == "total_pnl":
                return report.get("total_pnl", 0)
            elif sort_by == "generated_at":
                gen_str = report.get("generated_at", "")
                if gen_str:
                    try:
                        return datetime.fromisoformat(gen_str.replace("Z", "+00:00"))
                    except ValueError:
                        return datetime.min.replace(tzinfo=UTC)
                return datetime.min.replace(tzinfo=UTC)
            return report.get(sort_by, "")

        return sorted(reports, key=get_sort_key, reverse=reverse)

    async def query_reports(self, query: ReportQuery) -> ReportQueryResult:
        """Query historical reports.

        Args:
            query: Query parameters

        Returns:
            ReportQueryResult with matching reports
        """
        all_reports: list[dict[str, Any]] = []

        # Scan directories
        directories = self._get_report_directories(query.report_type)

        for directory in directories:
            if not os.path.exists(directory):
                continue

            try:
                for filename in os.listdir(directory):
                    if not filename.endswith(".json"):
                        continue

                    filepath = os.path.join(directory, filename)
                    report = self._load_report_file(filepath)

                    if report:
                        # Add source info
                        report["_source_file"] = filepath
                        all_reports.append(report)

            except Exception as e:
                logger.error(f"Error scanning directory {directory}: {e}")

        # Filter
        filtered = [r for r in all_reports if self._filter_report(r, query)]

        # Sort
        sorted_reports = self._sort_reports(filtered, query.sort_by, query.sort_order)

        # Paginate
        total = len(sorted_reports)
        start = query.offset
        end = start + query.limit
        paginated = sorted_reports[start:end]

        # Remove internal fields
        for report in paginated:
            report.pop("_source_file", None)

        return ReportQueryResult(
            reports=paginated,
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    async def get_report_by_id(
        self,
        report_id: str,
        report_type: ReportType | None = None,
    ) -> dict[str, Any] | None:
        """Get specific report by ID.

        Args:
            report_id: Report identifier (usually filename)
            report_type: Optional report type to narrow search

        Returns:
            Report dictionary or None
        """
        if report_type is None:
            types_to_search = list(ReportType)
        else:
            types_to_search = [report_type]

        for rtype in types_to_search:
            if rtype == ReportType.ALL:
                continue

            directories = self._get_report_directories(rtype)
            for directory in directories:
                filepath = os.path.join(directory, report_id)
                if os.path.exists(filepath):
                    return self._load_report_file(filepath)

                # Also try with .json extension
                if not filepath.endswith(".json"):
                    filepath_json = filepath + ".json"
                    if os.path.exists(filepath_json):
                        return self._load_report_file(filepath_json)

        return None

    async def get_latest_reports(
        self,
        report_type: ReportType,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get latest reports of a type.

        Args:
            report_type: Type of report
            limit: Maximum number of reports

        Returns:
            List of latest reports
        """
        query = ReportQuery(
            report_type=report_type,
            limit=limit,
            sort_by="date",
            sort_order=SortOrder.DESC,
        )
        result = await self.query_reports(query)
        return result.reports

    async def get_report_count(self, report_type: ReportType) -> int:
        """Get count of reports by type.

        Args:
            report_type: Type of report

        Returns:
            Number of reports
        """
        query = ReportQuery(report_type=report_type, limit=1)
        result = await self.query_reports(query)
        return result.total
