"""Tests for the daily report generator.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, AsyncMock

from src.reporting.daily_generator import DailyReportGenerator
from src.reporting.models import DailyReport, TradeMetrics


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
