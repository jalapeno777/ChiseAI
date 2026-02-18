"""Tests for the daily report generator.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, AsyncMock

from src.reporting.daily_generator import DailyReportGenerator
from src.reporting.models import (
    DailyReport,
    TradeMetrics,
    PaperHealthMetrics,
    PaperHealthReport,
)


class TestDailyReportGenerator:
    """Tests for DailyReportGenerator."""

    @pytest.fixture
    def generator(self):
        """Create a report generator instance."""
        return DailyReportGenerator()

    @pytest.fixture
    def mock_influx_client(self):
        """Create a mock InfluxDB client."""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_client.query_api.return_value = mock_query_api
        return mock_client

    @pytest.mark.asyncio
    async def test_generate_report_with_mock_data(self, generator):
        """Test generating report with mock data."""
        date = datetime(2026, 2, 17, tzinfo=UTC)

        report = await generator.generate_report(date=date, use_mock_data=True)

        assert isinstance(report, DailyReport)
        assert report.date == date
        assert report.total_trades > 0
        assert report.total_pnl != 0.0
        assert report.win_rate >= 0

    @pytest.mark.asyncio
    async def test_generate_report_default_date(self, generator):
        """Test generating report with default date (yesterday)."""
        report = await generator.generate_report(use_mock_data=True)

        assert isinstance(report, DailyReport)
        # Should be yesterday
        yesterday = datetime.now(UTC) - timedelta(days=1)
        assert report.date.date() == yesterday.date()

    def test_calculate_trade_metrics_empty(self, generator):
        """Test calculating trade metrics with empty trades."""
        metrics = generator._calculate_trade_metrics([])

        assert isinstance(metrics, TradeMetrics)
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0

    def test_calculate_trade_metrics_with_data(self, generator):
        """Test calculating trade metrics with data."""
        trades = [
            {"pnl": 100.0, "quantity": 1.0, "price": 50000.0},
            {"pnl": -50.0, "quantity": 0.5, "price": 51000.0},
            {"pnl": 75.0, "quantity": 1.0, "price": 50500.0},
        ]

        metrics = generator._calculate_trade_metrics(trades)

        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate == pytest.approx(66.67, rel=0.01)
        assert metrics.avg_pnl_per_trade == pytest.approx(41.67, rel=0.01)
        assert metrics.largest_win == 100.0
        assert metrics.largest_loss == -50.0

    def test_calculate_risk_metrics_empty(self, generator):
        """Test calculating risk metrics with empty data."""
        metrics = generator._calculate_risk_metrics([], {})

        assert metrics.sharpe_ratio == 0.0
        assert metrics.volatility == 0.0

    def test_calculate_risk_metrics_with_data(self, generator):
        """Test calculating risk metrics with data."""
        trades = [
            {"pnl": 100.0},
            {"pnl": -50.0},
            {"pnl": 75.0},
            {"pnl": -25.0},
            {"pnl": 50.0},
        ]
        portfolio = {"max_drawdown": 150.0, "drawdown_pct": 2.5}

        metrics = generator._calculate_risk_metrics(trades, portfolio)

        assert metrics.max_drawdown == 150.0
        assert metrics.max_drawdown_pct == 2.5
        assert metrics.volatility > 0

    def test_generate_mock_report(self, generator):
        """Test mock report generation."""
        date = datetime(2026, 2, 17, tzinfo=UTC)

        report = generator._generate_mock_report(date)

        assert isinstance(report, DailyReport)
        assert report.date == date
        assert report.total_trades == 42
        assert report.total_pnl == 1250.50
        assert report.win_rate == 66.7
        assert report.open_positions == 5
        assert report.portfolio_value == 50000.0
        assert report.risk_metrics.sharpe_ratio == 1.85

    def test_report_to_markdown(self, generator):
        """Test report Markdown output."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        report = generator._generate_mock_report(date)

        markdown = report.to_markdown()

        assert "# 📊 Daily Trading Summary" in markdown
        assert "2026-02-17" in markdown
        assert "Total PnL" in markdown
        assert "Win Rate" in markdown
        assert "Sharpe Ratio" in markdown

    @pytest.mark.asyncio
    async def test_generate_report_without_influxdb(self, generator):
        """Test report generation without InfluxDB falls back gracefully."""
        date = datetime(2026, 2, 17, tzinfo=UTC)

        # Without InfluxDB and mock disabled, it will try to query and return empty results
        # The generator handles this gracefully and returns a report with defaults
        try:
            report = await generator.generate_report(date=date, use_mock_data=False)
            # If it doesn't raise, it should return a valid report (possibly with empty data)
            assert isinstance(report, DailyReport)
        except RuntimeError:
            # RuntimeError is also acceptable if the implementation raises it
            pass


class TestPaperHealthReport:
    """Tests for paper health report generation."""

    @pytest.fixture
    def generator(self):
        """Create a report generator instance."""
        return DailyReportGenerator()

    @pytest.fixture
    def mock_paper_tracker(self):
        """Create a mock PaperTracker."""
        mock = Mock()
        mock.get_redis_health.return_value = {
            "error_rate_pct": 2.0,
            "circuit_breaker_open": False,
            "last_successful_operation": datetime.now(UTC).isoformat(),
        }
        mock.get_sync_status.return_value = {
            "redis_connected": True,
            "divergence_pct": 0.5,
            "memory_positions": 5,
            "redis_positions": 5,
        }
        mock.get_validation_failure_summary.return_value = {
            "failure_rate_pct": 5.0,
            "total_failures": 2,
            "total_orders": 40,
        }
        mock.get_circuit_breaker_state.return_value = {
            "state": "closed",
        }
        mock.kill_switch_armed = False
        return mock

    @pytest.mark.asyncio
    async def test_generate_paper_health_report(self, generator, mock_paper_tracker):
        """Test generating paper health report."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        thresholds = {
            "redis_error_rate_max_pct": 5.0,
            "validation_failure_max_pct": 10.0,
            "data_freshness_max_seconds": 60.0,
        }

        report = await generator.generate_paper_health_report(
            paper_tracker=mock_paper_tracker,
            date=date,
            thresholds=thresholds,
        )

        assert isinstance(report, PaperHealthReport)
        assert report.date == date
        assert isinstance(report.health_metrics, PaperHealthMetrics)
        assert report.health_metrics.redis_error_rate_pct == 2.0
        assert report.health_metrics.validation_failure_rate_pct == 5.0
        assert report.health_metrics.circuit_breaker_state == "closed"
        assert report.health_metrics.kill_switch_armed is False

    @pytest.mark.asyncio
    async def test_paper_health_report_all_pass(self, generator, mock_paper_tracker):
        """Test that all health checks pass with healthy metrics."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        thresholds = {
            "redis_error_rate_max_pct": 5.0,
            "validation_failure_max_pct": 10.0,
            "data_freshness_max_seconds": 60.0,
        }

        report = await generator.generate_paper_health_report(
            paper_tracker=mock_paper_tracker,
            date=date,
            thresholds=thresholds,
        )

        assert report.health_metrics.all_pass is True
        assert report.health_metrics.redis_sync_pass is True
        assert report.health_metrics.validation_pass is True
        assert report.health_metrics.circuit_breaker_pass is True
        assert report.health_metrics.kill_switch_pass is True
        assert report.health_metrics.data_freshness_pass is True
        assert report.health_metrics.overall_health == "HEALTHY"

    @pytest.mark.asyncio
    async def test_paper_health_report_validation_fail(
        self, generator, mock_paper_tracker
    ):
        """Test health check fails with high validation failure rate."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        thresholds = {
            "redis_error_rate_max_pct": 5.0,
            "validation_failure_max_pct": 10.0,
            "data_freshness_max_seconds": 60.0,
        }

        # Set high validation failure rate
        mock_paper_tracker.get_validation_failure_summary.return_value = {
            "failure_rate_pct": 15.0,  # Above threshold
            "total_failures": 15,
            "total_orders": 100,
        }

        report = await generator.generate_paper_health_report(
            paper_tracker=mock_paper_tracker,
            date=date,
            thresholds=thresholds,
        )

        assert report.health_metrics.validation_pass is False
        assert report.health_metrics.all_pass is False
        assert len(report.warnings) > 0

    @pytest.mark.asyncio
    async def test_paper_health_report_circuit_breaker_open(
        self, generator, mock_paper_tracker
    ):
        """Test health check fails with open circuit breaker."""
        date = datetime(2026, 2, 17, tzinfo=UTC)

        # Set circuit breaker to open
        mock_paper_tracker.get_circuit_breaker_state.return_value = {
            "state": "open",
        }
        mock_paper_tracker.get_redis_health.return_value = {
            "error_rate_pct": 10.0,
            "circuit_breaker_open": True,
            "last_successful_operation": datetime.now(UTC).isoformat(),
        }

        report = await generator.generate_paper_health_report(
            paper_tracker=mock_paper_tracker,
            date=date,
        )

        assert report.health_metrics.circuit_breaker_state == "open"
        assert report.health_metrics.circuit_breaker_pass is False
        assert report.health_metrics.all_pass is False

    @pytest.mark.asyncio
    async def test_paper_health_report_kill_switch_armed(
        self, generator, mock_paper_tracker
    ):
        """Test health check fails when kill switch is armed."""
        date = datetime(2026, 2, 17, tzinfo=UTC)

        # Arm kill switch
        mock_paper_tracker.kill_switch_armed = True

        report = await generator.generate_paper_health_report(
            paper_tracker=mock_paper_tracker,
            date=date,
        )

        assert report.health_metrics.kill_switch_armed is True
        assert report.health_metrics.kill_switch_pass is False
        assert report.health_metrics.all_pass is False
        assert any("Kill switch" in w for w in report.warnings)

    @pytest.mark.asyncio
    async def test_paper_health_report_redis_disconnected(
        self, generator, mock_paper_tracker
    ):
        """Test health check fails when Redis is disconnected."""
        date = datetime(2026, 2, 17, tzinfo=UTC)

        # Set Redis disconnected
        mock_paper_tracker.get_sync_status.return_value = {
            "redis_connected": False,
            "divergence_pct": 100.0,
        }

        report = await generator.generate_paper_health_report(
            paper_tracker=mock_paper_tracker,
            date=date,
        )

        assert report.health_metrics.redis_sync_status == "disconnected"
        assert report.health_metrics.redis_sync_pass is False
        assert report.health_metrics.all_pass is False

    @pytest.mark.asyncio
    async def test_paper_health_report_without_tracker(self, generator):
        """Test generating report without PaperTracker."""
        date = datetime(2026, 2, 17, tzinfo=UTC)

        report = await generator.generate_paper_health_report(
            paper_tracker=None,
            date=date,
        )

        assert isinstance(report, PaperHealthReport)
        assert report.health_metrics.redis_sync_status == "unknown"
        assert report.health_metrics.all_pass is False

    def test_paper_health_metrics_to_dict(self):
        """Test PaperHealthMetrics to_dict method."""
        metrics = PaperHealthMetrics(
            redis_sync_status="synced",
            redis_error_rate_pct=2.5,
            validation_failure_rate_pct=5.0,
            circuit_breaker_state="closed",
            kill_switch_armed=False,
            data_freshness_seconds=30.0,
            redis_sync_pass=True,
            validation_pass=True,
            circuit_breaker_pass=True,
            kill_switch_pass=True,
            data_freshness_pass=True,
        )

        data = metrics.to_dict()

        assert data["redis_sync_status"] == "synced"
        assert data["redis_error_rate_pct"] == 2.5
        assert data["validation_failure_rate_pct"] == 5.0
        assert data["circuit_breaker_state"] == "closed"
        assert data["kill_switch_armed"] is False
        assert data["health_checks"]["redis_sync"] == "PASS"

    def test_paper_health_report_to_markdown(self, generator, mock_paper_tracker):
        """Test PaperHealthReport Markdown output."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        report = PaperHealthReport(
            date=date,
            health_metrics=PaperHealthMetrics(
                redis_sync_status="synced",
                redis_error_rate_pct=2.0,
                validation_failure_rate_pct=5.0,
                circuit_breaker_state="closed",
                kill_switch_armed=False,
                data_freshness_seconds=30.0,
                redis_sync_pass=True,
                validation_pass=True,
                circuit_breaker_pass=True,
                kill_switch_pass=True,
                data_freshness_pass=True,
            ),
            portfolio_value=50000.0,
            total_pnl=1250.50,
            open_positions=5,
            active_strategies=3,
        )

        markdown = report.to_markdown()

        assert "# 🏥 Paper Trading Health Report" in markdown
        assert "2026-02-17" in markdown
        assert "✅ HEALTHY" in markdown
        assert "Redis Sync" in markdown
        assert "Validation" in markdown
        assert "$50,000.00" in markdown or "$50000.00" in markdown

    def test_paper_health_report_to_dict(self):
        """Test PaperHealthReport to_dict method."""
        date = datetime(2026, 2, 17, tzinfo=UTC)
        report = PaperHealthReport(
            date=date,
            health_metrics=PaperHealthMetrics(
                redis_sync_status="synced",
                redis_sync_pass=True,
                validation_pass=True,
                circuit_breaker_pass=True,
                kill_switch_pass=True,
                data_freshness_pass=True,
            ),
            portfolio_value=50000.0,
            total_pnl=1250.50,
            open_positions=5,
            active_strategies=3,
        )

        data = report.to_dict()

        assert data["date"] == "2026-02-17"
        assert data["health_status"] == "HEALTHY"
        assert data["all_checks_pass"] is True
        assert data["portfolio"]["value"] == 50000.0
        assert data["portfolio"]["open_positions"] == 5
        assert data["active_strategies"] == 3
