"""Integration tests for reporting pipeline (V-NS-023).

End-to-end tests for: Generate report → Archive → Query → Export → Email
Tests all report types (daily, weekly, monthly) and export formats.

For V-NS-023: Report generates → delivers → displays
"""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for report output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_influxdb():
    """Create a mock InfluxDB client."""
    mock = Mock()
    mock.query = AsyncMock(return_value=[])
    mock.write = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def report_scheduler(mock_influxdb, temp_output_dir):
    """Create a ReportScheduler instance with mocked dependencies."""
    from src.reporting.scheduler import ReportScheduler

    scheduler = ReportScheduler(
        influxdb_client=mock_influxdb,
        output_dir=temp_output_dir,
        default_discord_webhook=None,  # No Discord in tests
    )
    return scheduler


class TestReportingPipeline:
    """Test the full reporting pipeline."""

    @pytest.mark.asyncio
    async def test_daily_report_generation(self, report_scheduler, temp_output_dir):
        """Test V-NS-023.1: Daily report generation."""
        # Generate daily report
        report = await report_scheduler.generate_report_now(
            report_type="daily",
            use_mock_data=True,
        )

        # Verify report structure
        assert report is not None
        assert hasattr(report, "date")
        assert hasattr(report, "total_trades")
        assert hasattr(report, "total_pnl")
        assert hasattr(report, "win_rate")

        # Verify report has required methods
        assert hasattr(report, "to_dict")
        assert hasattr(report, "to_markdown")

        print(f"✓ Daily report generated: date={report.date}, pnl={report.total_pnl}")

    @pytest.mark.asyncio
    async def test_weekly_report_generation(self, report_scheduler):
        """Test V-NS-023.2: Weekly report generation."""
        # Generate weekly report
        report = await report_scheduler.generate_report_now(
            report_type="weekly",
            use_mock_data=True,
        )

        # Verify report structure
        assert report is not None
        assert hasattr(report, "start_date")
        assert hasattr(report, "end_date")
        assert hasattr(report, "total_pnl")

        # Verify report has required export methods
        assert hasattr(report, "to_dict")
        assert hasattr(report, "to_markdown")

        print(f"✓ Weekly report generated: {report.start_date} to {report.end_date}")

    @pytest.mark.asyncio
    async def test_report_archival(self, report_scheduler, temp_output_dir):
        """Test V-NS-023.3: Report archival to disk."""
        # Add a daily schedule (triggers immediate run in test)
        schedule = report_scheduler.add_schedule(
            name="test_daily",
            report_type="daily",
            cron_expression="0 9 * * *",
            enabled=True,
        )

        # Generate and save a report
        report = await report_scheduler.generate_report_now(
            report_type="daily",
            use_mock_data=True,
        )

        # Simulate archival
        await report_scheduler._save_report(report, "daily", schedule)

        # Verify file was created
        daily_dir = Path(temp_output_dir) / "daily"
        assert daily_dir.exists()

        # Find the saved report
        report_files = list(daily_dir.glob("daily_*.json"))
        assert len(report_files) > 0

        # Verify report content
        with open(report_files[0]) as f:
            saved_data = json.load(f)
            assert "date" in saved_data
            assert "total_pnl" in saved_data

        print(f"✓ Report archived to: {report_files[0]}")

    @pytest.mark.asyncio
    async def test_report_export_json(self, report_scheduler):
        """Test V-NS-023.4: JSON export format."""
        report = await report_scheduler.generate_report_now(
            report_type="daily",
            use_mock_data=True,
        )

        # Export to dict (JSON-serializable)
        report_dict = report.to_dict()

        # Verify JSON serialization
        json_str = json.dumps(report_dict)
        assert json_str is not None

        # Verify key fields
        assert "date" in report_dict
        assert "total_pnl" in report_dict
        assert "win_rate" in report_dict

        print(f"✓ JSON export verified: {len(json_str)} characters")

    @pytest.mark.asyncio
    async def test_report_export_markdown(self, report_scheduler):
        """Test V-NS-023.5: Markdown export format."""
        report = await report_scheduler.generate_report_now(
            report_type="daily",
            use_mock_data=True,
        )

        # Export to markdown
        markdown = report.to_markdown()

        # Verify markdown content
        assert markdown is not None
        assert len(markdown) > 0
        assert "Daily" in markdown or "Report" in markdown

        print(f"✓ Markdown export verified: {len(markdown)} characters")

    @pytest.mark.asyncio
    async def test_email_delivery_graceful_degradation(self, report_scheduler):
        """Test V-NS-023.6: Email delivery with missing SMTP credentials."""
        # Generate a report
        report = await report_scheduler.generate_report_now(
            report_type="daily",
            use_mock_data=True,
        )

        # Try to send email without SMTP credentials
        result = await report_scheduler._send_email(
            recipients=["test@example.com"],
            content=report.to_markdown(),
            subject=f"Test Report - {datetime.now(UTC).date()}",
        )

        # Should gracefully handle missing credentials
        assert result is True  # Logs warning instead of failing

        print("✓ Email delivery graceful degradation verified")


class TestReportSchedulerIntegration:
    """Integration tests for ReportScheduler with all components."""

    def test_scheduler_initialization(self, report_scheduler):
        """Test V-NS-023.7: Scheduler initializes with all components."""
        assert report_scheduler.daily_generator is not None
        assert report_scheduler.weekly_generator is not None
        assert report_scheduler.anomaly_detector is not None

        print("✓ Scheduler initialized with all components")

    def test_schedule_crud(self, report_scheduler):
        """Test V-NS-023.8: Schedule CRUD operations."""
        # Add schedule
        schedule = report_scheduler.add_schedule(
            name="test_schedule",
            report_type="daily",
            cron_expression="0 9 * * *",
        )

        assert schedule is not None
        assert schedule.name == "test_schedule"

        # Get schedules
        schedules = report_scheduler.get_schedules()
        assert len(schedules) > 0

        # Remove schedule
        result = report_scheduler.remove_schedule("test_schedule")
        assert result is True

        # Verify removed
        schedules = report_scheduler.get_schedules()
        assert not any(s.name == "test_schedule" for s in schedules)

        print("✓ Schedule CRUD operations verified")

    @pytest.mark.asyncio
    async def test_anomaly_detection_integration(self, report_scheduler):
        """Test V-NS-023.9: Anomaly detection integration."""
        # Run anomaly detection
        alerts = await report_scheduler.detect_anomalies_now()

        # Should return a list (possibly empty)
        assert isinstance(alerts, list)

        print(f"✓ Anomaly detection integrated: {len(alerts)} alerts")


class TestReportModels:
    """Test report models and their methods."""

    def test_daily_report_model(self):
        """Test V-NS-023.10: DailyReport model."""
        from src.reporting.models import DailyReport, RiskMetrics, TradeMetrics

        # Create a report
        report = DailyReport(
            date=datetime.now(UTC),
            total_trades=10,
            winning_trades=7,
            losing_trades=3,
            win_rate=0.70,
            total_pnl=1500.50,
            trade_metrics=TradeMetrics(
                total_trades=10,
                winning_trades=7,
                losing_trades=3,
                win_rate=0.70,
            ),
            risk_metrics=RiskMetrics(sharpe_ratio=1.5),
        )

        # Test to_dict
        data = report.to_dict()
        assert data["total_trades"] == 10
        assert data["total_pnl"] == 1500.50

        # Test to_markdown
        markdown = report.to_markdown()
        assert "Daily" in markdown or "Report" in markdown

        print("✓ DailyReport model verified")

    def test_weekly_report_model(self):
        """Test V-NS-023.11: WeeklyReport model."""
        from src.reporting.models import WeeklyReport, StrategyPerformance

        # Create strategy performance entries
        strategies = [
            StrategyPerformance(
                strategy_id="momentum",
                strategy_name="Momentum",
                total_trades=30,
                win_rate=0.65,
                total_pnl=5000.00,
                sharpe_ratio=1.8,
            ),
            StrategyPerformance(
                strategy_id="mean_reversion",
                strategy_name="Mean Reversion",
                total_trades=20,
                win_rate=0.55,
                total_pnl=2500.00,
                sharpe_ratio=1.2,
            ),
        ]

        # Create a weekly report
        report = WeeklyReport(
            start_date=datetime.now(UTC),
            end_date=datetime.now(UTC),
            total_trades=50,
            total_pnl=7500.00,
            win_rate=0.60,
            strategy_performance=strategies,
        )

        # Test serialization
        data = report.to_dict()
        assert data["total_trades"] == 50
        assert data["total_pnl"] == 7500.00
        assert len(data["strategy_performance"]) == 2

        markdown = report.to_markdown()
        assert markdown is not None
        assert "Strategy" in markdown or "Performance" in markdown

        print("✓ WeeklyReport model verified")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
