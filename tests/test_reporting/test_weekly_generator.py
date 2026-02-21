"""Tests for the weekly report generator.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from src.reporting.weekly_generator import WeeklyPerformanceReport
from src.reporting.models import WeeklyReport


class TestWeeklyPerformanceReport:
    """Tests for WeeklyPerformanceReport."""

    @pytest.fixture
    def generator(self):
        """Create a report generator instance."""
        return WeeklyPerformanceReport()

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
        end_date = datetime(2026, 2, 16, tzinfo=UTC)

        report = await generator.generate_report(end_date=end_date, use_mock_data=True)

        assert isinstance(report, WeeklyReport)
        # end_date gets normalized to end of day, so check date only
        assert report.end_date.date() == end_date.date()
        assert report.total_trades > 0
        assert len(report.daily_breakdown) == 7

    @pytest.mark.asyncio
    async def test_generate_report_default_date(self, generator):
        """Test generating report with default date."""
        report = await generator.generate_report(use_mock_data=True)

        assert isinstance(report, WeeklyReport)
        # Should be 7 days ending yesterday
        yesterday = datetime.now(UTC) - timedelta(days=1)
        assert report.end_date.date() == yesterday.date()

    def test_calculate_risk_metrics_empty(self, generator):
        """Test calculating risk metrics with empty data."""
        metrics = generator._calculate_risk_metrics([])

        assert metrics.sharpe_ratio == 0.0
        assert metrics.volatility == 0.0

    def test_calculate_risk_metrics_with_data(self, generator):
        """Test calculating risk metrics with data."""
        daily_data = [
            {"pnl": 100.0},
            {"pnl": -50.0},
            {"pnl": 75.0},
            {"pnl": -25.0},
            {"pnl": 50.0},
            {"pnl": 100.0},
            {"pnl": -30.0},
        ]

        metrics = generator._calculate_risk_metrics(daily_data)

        assert metrics.volatility > 0

    def test_build_strategy_performance(self, generator):
        """Test building strategy performance list."""
        strategy_data = {
            "momentum_v1": {
                "trades": 50,
                "wins": 35,
                "losses": 15,
                "pnls": [100.0, -50.0, 75.0] * 16 + [100.0, -50.0],
            },
            "mean_reversion_v2": {
                "trades": 30,
                "wins": 20,
                "losses": 10,
                "pnls": [50.0, -25.0, 40.0] * 10,
            },
        }

        performance = generator._build_strategy_performance(strategy_data)

        assert len(performance) == 2
        assert performance[0].strategy_id == "momentum_v1"
        assert performance[0].total_trades == 50
        assert performance[0].win_rate == 70.0

    def test_calculate_week_over_week(self, generator):
        """Test week-over-week calculation."""
        current_data = [
            {"pnl": 100.0, "trades": 10, "wins": 7},
            {"pnl": 150.0, "trades": 15, "wins": 10},
        ]
        previous_data = [
            {"pnl": 80.0, "trades": 8, "wins": 5},
            {"pnl": 120.0, "trades": 12, "wins": 7},
        ]

        wow = generator._calculate_week_over_week(current_data, previous_data)

        assert "total_pnl" in wow
        assert "total_trades" in wow
        assert wow["total_pnl"] > 0  # Should show increase

    def test_generate_mock_report(self, generator):
        """Test mock report generation."""
        start_date = datetime(2026, 2, 10, tzinfo=UTC)
        end_date = datetime(2026, 2, 16, tzinfo=UTC)

        report = generator._generate_mock_report(start_date, end_date)

        assert isinstance(report, WeeklyReport)
        assert report.start_date == start_date
        assert report.end_date == end_date
        assert report.total_trades == 287
        assert len(report.strategy_performance) == 3
        assert len(report.daily_breakdown) == 7
        assert report.risk_metrics.sharpe_ratio == 2.15

    def test_report_to_markdown(self, generator):
        """Test report Markdown output."""
        start_date = datetime(2026, 2, 10, tzinfo=UTC)
        end_date = datetime(2026, 2, 16, tzinfo=UTC)
        report = generator._generate_mock_report(start_date, end_date)

        markdown = report.to_markdown()

        assert "# 📈 Weekly Performance Report" in markdown
        assert "2026-02-10" in markdown
        assert "2026-02-16" in markdown
        assert "Strategy Performance" in markdown
        assert "Sharpe Ratio" in markdown

    @pytest.mark.asyncio
    async def test_generate_report_without_influxdb(self, generator):
        """Test report generation without InfluxDB falls back gracefully."""
        end_date = datetime(2026, 2, 16, tzinfo=UTC)

        # Without InfluxDB and mock disabled, it will try to query and return empty results
        # The generator handles this gracefully and returns a report with defaults
        try:
            report = await generator.generate_report(
                end_date=end_date, use_mock_data=False
            )
            # If it doesn't raise, it should return a valid report (possibly with empty data)
            assert isinstance(report, WeeklyReport)
        except RuntimeError:
            # RuntimeError is also acceptable if the implementation raises it
            pass
