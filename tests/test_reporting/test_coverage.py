"""Additional tests to improve coverage for the reporting module.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.reporting.anomaly_detector import AnomalyDetector
from src.reporting.daily_generator import DailyReportGenerator
from src.reporting.weekly_generator import WeeklyPerformanceReport
from src.reporting.scheduler import ReportScheduler
from src.reporting.models import (
    AnomalyAlert,
    AnomalySeverity,
    AnomalyType,
    DailyReport,
    WeeklyReport,
    ReportSchedule,
)


class TestAnomalyDetectorCoverage:
    """Additional tests for AnomalyDetector coverage."""

    @pytest.fixture
    def detector(self):
        """Create an anomaly detector instance."""
        return AnomalyDetector()

    @pytest.mark.asyncio
    async def test_query_baseline_metric_with_client(self, detector):
        """Test _query_baseline_metric with mock client."""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_tables = [Mock()]
        mock_record = Mock()
        mock_record.get_value.return_value = 100.0
        mock_tables[0].records = [mock_record]
        mock_query_api.query.return_value = mock_tables
        mock_client.query_api.return_value = mock_query_api

        detector._client = mock_client
        detector._query_api = None

        result = await detector._query_baseline_metric("test_measurement", "test_field")

        assert len(result) == 1
        assert result[0] == 100.0

    @pytest.mark.asyncio
    async def test_query_baseline_metric_no_client(self, detector):
        """Test _query_baseline_metric without client."""
        detector._client = None
        result = await detector._query_baseline_metric("test", "field")
        assert result == []

    @pytest.mark.asyncio
    async def test_query_current_metric_with_client(self, detector):
        """Test _query_current_metric with mock client."""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_tables = [Mock()]
        mock_record = Mock()
        mock_record.get_value.return_value = 150.0
        mock_tables[0].records = [mock_record]
        mock_query_api.query.return_value = mock_tables
        mock_client.query_api.return_value = mock_query_api

        detector._client = mock_client
        detector._query_api = None

        result = await detector._query_current_metric("test", "field", 1)

        assert result == 150.0

    @pytest.mark.asyncio
    async def test_query_current_metric_no_client(self, detector):
        """Test _query_current_metric without client."""
        detector._client = None
        result = await detector._query_current_metric("test", "field", 1)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_query_baseline_pnls(self, detector):
        """Test _query_baseline_pnls method."""
        detector._query_baseline_metric = AsyncMock(return_value=[100.0, 200.0])
        result = await detector._query_baseline_pnls()
        assert result == [100.0, 200.0]

    @pytest.mark.asyncio
    async def test_query_current_pnl(self, detector):
        """Test _query_current_pnl method."""
        detector._query_current_metric = AsyncMock(return_value=150.0)
        result = await detector._query_current_pnl(1)
        assert result == 150.0


class TestDailyGeneratorCoverage:
    """Additional tests for DailyReportGenerator coverage."""

    @pytest.fixture
    def generator(self):
        """Create a report generator instance."""
        return DailyReportGenerator()

    def test_get_query_api_with_client(self, generator):
        """Test _get_query_api with client."""
        mock_client = Mock()
        mock_client.query_api.return_value = Mock()
        generator._client = mock_client
        generator._query_api = None

        result = generator._get_query_api()

        assert result is not None

    def test_get_query_api_no_client(self, generator):
        """Test _get_query_api without client."""
        generator._client = None
        result = generator._get_query_api()
        assert result is None

    @pytest.mark.asyncio
    async def test_query_trades_no_client(self, generator):
        """Test _query_trades without client."""
        generator._client = None
        result = await generator._query_trades(datetime.now(UTC))
        assert result == []

    @pytest.mark.asyncio
    async def test_query_portfolio_no_client(self, generator):
        """Test _query_portfolio without client."""
        generator._client = None
        result = await generator._query_portfolio(datetime.now(UTC))
        assert result == {}

    @pytest.mark.asyncio
    async def test_query_positions_no_client(self, generator):
        """Test _query_positions without client."""
        generator._client = None
        result = await generator._query_positions(datetime.now(UTC))
        assert result == {"open_count": 0}


class TestWeeklyGeneratorCoverage:
    """Additional tests for WeeklyPerformanceReport coverage."""

    @pytest.fixture
    def generator(self):
        """Create a report generator instance."""
        return WeeklyPerformanceReport()

    def test_get_query_api_with_client(self, generator):
        """Test _get_query_api with client."""
        mock_client = Mock()
        mock_client.query_api.return_value = Mock()
        generator._client = mock_client
        generator._query_api = None

        result = generator._get_query_api()

        assert result is not None

    def test_get_query_api_no_client(self, generator):
        """Test _get_query_api without client."""
        generator._client = None
        result = generator._get_query_api()
        assert result is None

    @pytest.mark.asyncio
    async def test_query_daily_metrics_no_client(self, generator):
        """Test _query_daily_metrics without client."""
        generator._client = None
        start = datetime.now(UTC)
        end = start + timedelta(days=7)
        result = await generator._query_daily_metrics(start, end)
        assert result == []

    @pytest.mark.asyncio
    async def test_query_strategy_performance_no_client(self, generator):
        """Test _query_strategy_performance without client."""
        generator._client = None
        start = datetime.now(UTC)
        end = start + timedelta(days=7)
        result = await generator._query_strategy_performance(start, end)
        assert result == {}

    @pytest.mark.asyncio
    async def test_query_previous_week(self, generator):
        """Test _query_previous_week method."""
        generator._query_daily_metrics = AsyncMock(return_value=[{"pnl": 100.0}])
        start = datetime(2026, 2, 10, tzinfo=UTC)
        result = await generator._query_previous_week(start)
        assert result == [{"pnl": 100.0}]


class TestSchedulerCoverage:
    """Additional tests for ReportScheduler coverage."""

    @pytest.fixture
    def scheduler(self, tmp_path):
        """Create a report scheduler instance."""
        return ReportScheduler(output_dir=str(tmp_path / "reports"))

    @pytest.mark.asyncio
    async def test_check_schedules(self, scheduler):
        """Test _check_schedules method."""
        schedule = ReportSchedule(
            name="test",
            report_type="daily",
            cron_expression="0 9 * * *",
            enabled=False,  # Disabled so it won't execute
        )
        scheduler._schedules.append(schedule)

        # Should not raise
        await scheduler._check_schedules()

    @pytest.mark.asyncio
    async def test_execute_schedule_daily(self, scheduler):
        """Test _execute_schedule for daily report."""
        schedule = ReportSchedule(
            name="daily_test",
            report_type="daily",
            cron_expression="0 9 * * *",
        )

        scheduler._generate_and_send_daily = AsyncMock()
        scheduler._run_anomaly_detection = AsyncMock()

        now = datetime.now(UTC)
        await scheduler._execute_schedule(schedule, now)

        assert schedule.last_run == now
        scheduler._generate_and_send_daily.assert_called_once()
        scheduler._run_anomaly_detection.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_schedule_weekly(self, scheduler):
        """Test _execute_schedule for weekly report."""
        schedule = ReportSchedule(
            name="weekly_test",
            report_type="weekly",
            cron_expression="0 9 * * 1",
        )

        scheduler._generate_and_send_weekly = AsyncMock()
        scheduler._run_anomaly_detection = AsyncMock()

        now = datetime.now(UTC)
        await scheduler._execute_schedule(schedule, now)

        assert schedule.last_run == now
        scheduler._generate_and_send_weekly.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_reports(self, scheduler, tmp_path):
        """Test _cleanup_old_reports method."""
        report_dir = tmp_path / "reports" / "test"
        report_dir.mkdir(parents=True)

        # Create an old file
        old_file = report_dir / "old_report.json"
        old_file.write_text("{}")

        # Set modification time to 40 days ago
        old_time = (datetime.now(UTC) - timedelta(days=40)).timestamp()
        import os

        os.utime(old_file, (old_time, old_time))

        await scheduler._cleanup_old_reports(str(report_dir), 30)

        assert not old_file.exists()

    @pytest.mark.asyncio
    async def test_send_email(self, scheduler):
        """Test _send_email method (placeholder)."""
        result = await scheduler._send_email(
            ["test@example.com"],
            "Test content",
            "Test subject",
        )
        assert result is True


class TestDailyReportCoverage:
    """Additional tests for DailyReport model coverage."""

    def test_daily_report_with_zero_trades(self):
        """Test DailyReport with zero trades."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        report = DailyReport(
            date=date,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
        )

        assert report.win_rate == 0.0
        markdown = report.to_markdown()
        assert "0%" in markdown or "0.0%" in markdown


class TestWeeklyReportCoverage:
    """Additional tests for WeeklyReport model coverage."""

    def test_weekly_report_without_strategies(self):
        """Test WeeklyReport without strategy performance."""
        start = datetime(2026, 2, 10, tzinfo=UTC)
        end = datetime(2026, 2, 16, tzinfo=UTC)
        report = WeeklyReport(
            start_date=start,
            end_date=end,
            total_trades=100,
            total_pnl=1000.0,
            strategy_performance=[],
        )

        markdown = report.to_markdown()
        assert "Weekly Performance Report" in markdown
        # Should not have strategy table when empty
        assert "Strategy Performance" not in markdown


class TestAnomalyAlertCoverage:
    """Additional tests for AnomalyAlert model coverage."""

    def test_anomaly_alert_info_severity(self):
        """Test AnomalyAlert with INFO severity."""
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            severity=AnomalySeverity.INFO,
            message="Info message",
            detected_at=datetime.now(UTC),
            metric_name="Latency",
            current_value=100.0,
            expected_value=50.0,
            deviation=1.0,
        )

        markdown = alert.to_markdown()
        assert "ℹ️" in markdown or "Latency" in markdown

    def test_anomaly_alert_without_details(self):
        """Test AnomalyAlert without details."""
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.ERROR_RATE_SPIKE,
            severity=AnomalySeverity.WARNING,
            message="Warning message",
            detected_at=datetime.now(UTC),
            metric_name="Error Rate",
            current_value=0.1,
            expected_value=0.01,
            deviation=9.0,
            details={},
        )

        markdown = alert.to_markdown()
        assert "Error Rate" in markdown
