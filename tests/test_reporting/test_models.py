"""Tests for the reporting models.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from datetime import UTC, datetime, timedelta

from src.reporting.models import (
    AnomalyAlert,
    AnomalySeverity,
    AnomalyType,
    DailyReport,
    ReportSchedule,
    RiskMetrics,
    StrategyPerformance,
    TradeMetrics,
    WeeklyReport,
)


class TestTradeMetrics:
    """Tests for TradeMetrics model."""

    def test_default_values(self):
        """Test default values."""
        metrics = TradeMetrics()
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = TradeMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=60.0,
            avg_pnl_per_trade=100.5,
        )
        d = metrics.to_dict()
        assert d["total_trades"] == 10
        assert d["win_rate"] == 60.0
        assert d["avg_pnl_per_trade"] == 100.5


class TestRiskMetrics:
    """Tests for RiskMetrics model."""

    def test_default_values(self):
        """Test default values."""
        metrics = RiskMetrics()
        assert metrics.sharpe_ratio == 0.0
        assert metrics.max_drawdown == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = RiskMetrics(
            sharpe_ratio=1.85,
            volatility=0.025,
            max_drawdown=150.0,
        )
        d = metrics.to_dict()
        assert d["sharpe_ratio"] == 1.85
        assert d["volatility"] == 0.025


class TestStrategyPerformance:
    """Tests for StrategyPerformance model."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        perf = StrategyPerformance(
            strategy_id="test_v1",
            strategy_name="Test Strategy V1",
            total_trades=50,
            win_rate=65.0,
            total_pnl=1000.0,
        )
        d = perf.to_dict()
        assert d["strategy_id"] == "test_v1"
        assert d["win_rate"] == 65.0


class TestDailyReport:
    """Tests for DailyReport model."""

    def test_default_values(self):
        """Test default values."""
        date = datetime.now(UTC)
        report = DailyReport(date=date)
        assert report.date == date
        assert report.total_trades == 0
        assert report.total_pnl == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        date = datetime.now(UTC)
        report = DailyReport(
            date=date,
            total_trades=42,
            total_pnl=1250.50,
            win_rate=66.7,
        )
        d = report.to_dict()
        assert d["total_trades"] == 42
        assert d["total_pnl"] == 1250.50
        assert d["win_rate"] == 66.7

    def test_to_markdown(self):
        """Test Markdown generation."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        report = DailyReport(
            date=date,
            total_trades=42,
            total_pnl=1250.50,
            win_rate=66.7,
            trade_metrics=TradeMetrics(total_trades=42, win_rate=66.7),
            risk_metrics=RiskMetrics(sharpe_ratio=1.85, max_drawdown_pct=2.5),
        )
        md = report.to_markdown()
        assert "Daily Trading Summary" in md
        assert "2026-02-17" in md
        assert "$1,250.50" in md
        assert "66.7%" in md


class TestWeeklyReport:
    """Tests for WeeklyReport model."""

    def test_default_values(self):
        """Test default values."""
        start = datetime.now(UTC)
        end = start + timedelta(days=6)
        report = WeeklyReport(start_date=start, end_date=end)
        assert report.start_date == start
        assert report.end_date == end
        assert report.total_trades == 0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        start = datetime(2026, 2, 10, tzinfo=UTC)
        end = datetime(2026, 2, 16, tzinfo=UTC)
        report = WeeklyReport(
            start_date=start,
            end_date=end,
            total_trades=287,
            total_pnl=5000.0,
        )
        d = report.to_dict()
        assert d["total_trades"] == 287
        assert d["total_pnl"] == 5000.0
        assert d["start_date"] == "2026-02-10"

    def test_to_markdown(self):
        """Test Markdown generation."""
        start = datetime(2026, 2, 10, tzinfo=UTC)
        end = datetime(2026, 2, 16, tzinfo=UTC)
        report = WeeklyReport(
            start_date=start,
            end_date=end,
            total_trades=287,
            total_pnl=5000.0,
            strategy_performance=[
                StrategyPerformance(
                    strategy_id="test_v1",
                    strategy_name="Test V1",
                    total_trades=100,
                    win_rate=70.0,
                    total_pnl=3000.0,
                )
            ],
        )
        md = report.to_markdown()
        assert "Weekly Performance Report" in md
        assert "2026-02-10" in md
        assert "2026-02-16" in md
        assert "Test V1" in md


class TestAnomalyAlert:
    """Tests for AnomalyAlert model."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.PNL_SPIKE,
            severity=AnomalySeverity.WARNING,
            message="Test anomaly",
            detected_at=datetime.now(UTC),
            metric_name="PnL",
            current_value=1000.0,
            expected_value=100.0,
            deviation=10.0,
        )
        d = alert.to_dict()
        assert d["anomaly_type"] == "pnl_spike"
        assert d["severity"] == "warning"
        assert d["metric_name"] == "PnL"

    def test_to_markdown(self):
        """Test Markdown generation."""
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.VOLUME_SPIKE,
            severity=AnomalySeverity.CRITICAL,
            message="Volume spike detected",
            detected_at=datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC),
            metric_name="Volume",
            current_value=10000.0,
            expected_value=1000.0,
            deviation=9.0,
        )
        md = alert.to_markdown()
        assert "Volume Spike" in md
        assert "CRITICAL" in md
        assert "10000.0000" in md


class TestReportSchedule:
    """Tests for ReportSchedule model."""

    def test_default_values(self):
        """Test default values."""
        schedule = ReportSchedule(
            name="daily_test",
            report_type="daily",
            cron_expression="0 9 * * *",
        )
        assert schedule.name == "daily_test"
        assert schedule.enabled is True
        assert schedule.archive_days == 30

    def test_to_dict(self):
        """Test conversion to dictionary."""
        schedule = ReportSchedule(
            name="daily_test",
            report_type="daily",
            cron_expression="0 9 * * *",
            discord_webhook="https://discord.com/webhook",
            email_recipients=["test@example.com"],
        )
        d = schedule.to_dict()
        assert d["name"] == "daily_test"
        assert d["cron_expression"] == "0 9 * * *"
        assert d["discord_webhook"] == "https://discord.com/webhook"
        assert d["email_recipients"] == ["test@example.com"]
