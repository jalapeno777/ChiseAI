"""Dashboard report widget for displaying and interacting with reports.

Provides dashboard widget for displaying latest reports,
historical report browser, and quick download links.

For ST-NS-023-T2: Report Delivery & Dashboard Integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReportStatus(Enum):
    """Report status indicators."""

    GENERATED = "generated"
    DELIVERED = "delivered"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class ReportWidgetData:
    """Report data for widget display.

    Attributes:
        report_id: Unique report identifier
        report_type: Type of report
        title: Display title
        summary: Short summary text
        date: Report date
        status: Report status
        download_urls: Dictionary of format to download URL
        generated_at: When report was generated
        delivered_at: When report was delivered
    """

    report_id: str
    report_type: str
    title: str
    summary: str
    date: datetime
    status: ReportStatus = ReportStatus.GENERATED
    download_urls: dict[str, str] = field(default_factory=dict)
    generated_at: datetime | None = None
    delivered_at: datetime | None = None


@dataclass
class ReportWidgetConfig:
    """Configuration for report widget.

    Attributes:
        max_reports: Maximum reports to display
        show_download_links: Show download format links
        auto_refresh: Auto refresh interval in seconds
        default_format: Default download format
    """

    max_reports: int = 10
    show_download_links: bool = True
    auto_refresh: int = 300  # 5 minutes
    default_format: str = "json"


class ReportWidget:
    """Dashboard widget for report display and interaction.

    Features:
    - Display latest reports with status
    - Historical report browser
    - Quick download links (PDF, CSV, JSON)
    - Report filtering by type and date
    - Pagination support

    Attributes:
        config: Widget configuration
        reports_dir: Base directory for reports
    """

    def __init__(
        self,
        config: ReportWidgetConfig | None = None,
        reports_dir: str = "./reports",
    ) -> None:
        """Initialize report widget.

        Args:
            config: Widget configuration
            reports_dir: Base directory for reports
        """
        self.config = config or ReportWidgetConfig()
        self.reports_dir = reports_dir
        self._cache: list[ReportWidgetData] = []
        self._cache_timestamp: datetime | None = None

    async def get_latest_reports(
        self,
        report_type: str | None = None,
        limit: int | None = None,
    ) -> list[ReportWidgetData]:
        """Get latest reports for display.

        Args:
            report_type: Filter by report type
            limit: Maximum reports to return

        Returns:
            List of ReportWidgetData
        """
        limit = limit or self.config.max_reports

        # Refresh cache if needed
        await self._refresh_cache()

        reports = self._cache

        if report_type:
            reports = [r for r in reports if r.report_type == report_type]

        return reports[:limit]

    async def _refresh_cache(self) -> None:
        """Refresh internal cache from disk."""
        from reporting.delivery.query_api import ReportQuery, ReportQueryAPI, ReportType

        now = datetime.now(UTC)
        cache_age = 60  # seconds

        if (
            self._cache_timestamp
            and (now - self._cache_timestamp).total_seconds() < cache_age
        ):
            return

        try:
            api = ReportQueryAPI(self.reports_dir)

            # Query for recent reports
            all_reports = []

            for rtype in [ReportType.DAILY, ReportType.WEEKLY, ReportType.PAPER_HEALTH]:
                result = await api.query_reports(
                    ReportQuery(
                        report_type=rtype,
                        limit=50,
                        sort_by="date",
                    )
                )
                all_reports.extend(result.reports)

            # Convert to widget data
            self._cache = []
            for report in all_reports:
                widget_data = self._convert_to_widget_data(report)
                if widget_data:
                    self._cache.append(widget_data)

            # Sort by date
            self._cache.sort(key=lambda x: x.date, reverse=True)

            self._cache_timestamp = now

        except Exception as e:
            logger.error(f"Failed to refresh report cache: {e}")

    def _convert_to_widget_data(
        self,
        report: dict[str, Any],
    ) -> ReportWidgetData | None:
        """Convert report dict to widget data.

        Args:
            report: Report dictionary

        Returns:
            ReportWidgetData or None
        """
        try:
            date_str = report.get("date") or report.get("start_date", "")
            if isinstance(date_str, str):
                report_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=UTC
                )
            else:
                report_date = date_str

            # Determine report type
            if "health" in report:
                report_type = "paper_health"
            elif "week" in str(report.get("date", "")):
                report_type = "weekly"
            else:
                report_type = "daily"

            # Create title
            title = f"{report_type.title()} Report"
            if report_date:
                title += f" - {report_date.strftime('%Y-%m-%d')}"

            # Create summary
            total_pnl = report.get("total_pnl", 0)
            total_trades = report.get("total_trades", 0)
            summary = f"PnL: ${total_pnl:,.2f} | Trades: {total_trades}"

            # Generate download URLs
            report_id = report.get("_source_file", "")
            download_urls = {
                "json": f"/reports/download/{report_id}.json",
                "csv": f"/reports/download/{report_id}.csv",
                "pdf": f"/reports/download/{report_id}.pdf",
            }

            return ReportWidgetData(
                report_id=report_id,
                report_type=report_type,
                title=title,
                summary=summary,
                date=report_date,
                status=ReportStatus.DELIVERED,
                download_urls=download_urls,
                generated_at=(
                    datetime.fromisoformat(
                        report.get("generated_at", "").replace("Z", "+00:00")
                    )
                    if report.get("generated_at")
                    else None
                ),
            )

        except Exception as e:
            logger.warning(f"Failed to convert report: {e}")
            return None

    def render_widget_html(self, reports: list[ReportWidgetData]) -> str:
        """Render widget as HTML.

        Args:
            reports: List of reports to display

        Returns:
            HTML string
        """
        if not reports:
            return """
            <div class="report-widget">
                <h3>📊 Recent Reports</h3>
                <p class="no-reports">No reports available</p>
            </div>
            """

        status_colors = {
            ReportStatus.GENERATED: "#007bff",
            ReportStatus.DELIVERED: "#28a745",
            ReportStatus.FAILED: "#dc3545",
            ReportStatus.PENDING: "#ffc107",
        }

        rows = []
        for report in reports:
            status_color = status_colors.get(report.status, "#6c757d")
            status_label = report.status.value.capitalize()

            download_html = ""
            if self.config.show_download_links:
                download_html = """
                <div class="download-links">
                    <a href="{json}" class="btn-download">JSON</a>
                    <a href="{csv}" class="btn-download">CSV</a>
                    <a href="{pdf}" class="btn-download">PDF</a>
                </div>
                """.format(
                    json=report.download_urls.get("json", "#"),
                    csv=report.download_urls.get("csv", "#"),
                    pdf=report.download_urls.get("pdf", "#"),
                )

            row = f"""
            <div class="report-item">
                <div class="report-header">
                    <span class="report-title">{report.title}</span>
                    <span class="report-status" style="color: {status_color};">{status_label}</span>
                </div>
                <div class="report-summary">{report.summary}</div>
                {download_html}
            </div>
            """
            rows.append(row)

        return f"""
        <div class="report-widget">
            <h3>📊 Recent Reports</h3>
            <div class="report-list">
                {"".join(rows)}
            </div>
        </div>
        """

    def render_widget_markdown(self, reports: list[ReportWidgetData]) -> str:
        """Render widget as Markdown.

        Args:
            reports: List of reports to display

        Returns:
            Markdown string
        """
        if not reports:
            return "## 📊 Recent Reports\n\n*No reports available*"

        lines = ["## 📊 Recent Reports", ""]

        for report in reports:
            status_emoji = {
                ReportStatus.GENERATED: "🔵",
                ReportStatus.DELIVERED: "✅",
                ReportStatus.FAILED: "❌",
                ReportStatus.PENDING: "⏳",
            }.get(report.status, "⚪")

            lines.append(f"### {status_emoji} {report.title}")
            lines.append(f"- **Summary:** {report.summary}")
            lines.append(f"- **Status:** {report.status.value.capitalize()}")

            if self.config.show_download_links:
                lines.append("- **Downloads:**")
                lines.append(f"  - [JSON]({report.download_urls.get('json', '#')})")
                lines.append(f"  - [CSV]({report.download_urls.get('csv', '#')})")
                lines.append(f"  - [PDF]({report.download_urls.get('pdf', '#')})")

            lines.append("")

        return "\n".join(lines)

    async def search_reports(
        self,
        query: str,
        report_type: str | None = None,
    ) -> list[ReportWidgetData]:
        """Search reports by query string.

        Args:
            query: Search query
            report_type: Optional report type filter

        Returns:
            List of matching reports
        """
        await self._refresh_cache()

        results = []
        query_lower = query.lower()

        for report in self._cache:
            if (
                query_lower in report.title.lower()
                or query_lower in report.summary.lower()
            ):
                if report_type is None or report.report_type == report_type:
                    results.append(report)

        return results

    def get_report_stats(self) -> dict[str, Any]:
        """Get report statistics.

        Returns:
            Dictionary with report stats
        """
        return {
            "total_cached": len(self._cache),
            "cache_timestamp": (
                self._cache_timestamp.isoformat() if self._cache_timestamp else None
            ),
            "config": {
                "max_reports": self.config.max_reports,
                "show_download_links": self.config.show_download_links,
                "auto_refresh": self.config.auto_refresh,
            },
        }
