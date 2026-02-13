"""Tests for execution telemetry calculator.

For ST-EX-001: KPI calculation tests.
"""

from datetime import UTC, datetime, timedelta

import pytest

from execution.telemetry.calculator import KPICalculator
from execution.telemetry.metrics import PositionSide, Trade


class TestCalculateSharpe:
    """Tests for Sharpe ratio calculation."""

    def test_sharpe_with_valid_returns(self):
        """Test Sharpe calculation with valid returns."""
        # Daily returns of 1% with low volatility
        returns = [0.01, 0.012, 0.008, 0.015, 0.009, 0.011, 0.013]
        sharpe = KPICalculator.calculate_sharpe(returns, risk_free_rate=0.02)

        # Should be positive and reasonable
        assert sharpe > 0
        assert sharpe <= 10  # Shouldn't be extreme (clamped at 10)

    def test_sharpe_with_insufficient_data(self):
        """Test Sharpe with less than 2 data points."""
        assert KPICalculator.calculate_sharpe([]) == 0.0
        assert KPICalculator.calculate_sharpe([0.01]) == 0.0

    def test_sharpe_with_zero_std(self):
        """Test Sharpe when all returns are identical."""
        returns = [0.01, 0.01, 0.01, 0.01]
        assert KPICalculator.calculate_sharpe(returns) == 0.0

    def test_sharpe_with_negative_returns(self):
        """Test Sharpe with negative average returns."""
        returns = [-0.01, -0.02, -0.015, -0.01]
        sharpe = KPICalculator.calculate_sharpe(returns)
        assert sharpe < 0

    def test_sharpe_clamped_extremes(self):
        """Test that extreme Sharpe values are clamped."""
        # Very high returns with tiny std dev
        returns = [1.0, 1.001, 0.999, 1.0001]
        sharpe = KPICalculator.calculate_sharpe(returns)
        assert -10 <= sharpe <= 10

    def test_sharpe_with_nan_values(self):
        """Test Sharpe with NaN values in returns."""
        returns = [0.01, float("nan"), 0.012, 0.008]
        sharpe = KPICalculator.calculate_sharpe(returns)
        # Should handle NaN gracefully
        assert isinstance(sharpe, float)


class TestCalculateMaxDrawdown:
    """Tests for max drawdown calculation."""

    def test_max_drawdown_normal_case(self):
        """Test max drawdown with typical equity curve."""
        # Equity goes up then down
        equity = [10000, 10500, 11000, 10800, 10500, 10900]
        mdd = KPICalculator.calculate_max_drawdown(equity)

        # Peak at 11000, trough at 10500 = ~4.5% drawdown
        assert mdd > 0
        assert mdd < 10

    def test_max_drawdown_no_drawdown(self):
        """Test when equity only goes up."""
        equity = [10000, 10500, 11000, 11500, 12000]
        assert KPICalculator.calculate_max_drawdown(equity) == 0.0

    def test_max_drawdown_insufficient_data(self):
        """Test with less than 2 data points."""
        assert KPICalculator.calculate_max_drawdown([]) == 0.0
        assert KPICalculator.calculate_max_drawdown([10000]) == 0.0

    def test_max_drawdown_full_loss(self):
        """Test with total loss scenario."""
        equity = [10000, 8000, 6000, 4000, 2000, 1000]
        mdd = KPICalculator.calculate_max_drawdown(equity)
        assert mdd == 90.0  # 90% drawdown

    def test_max_drawdown_multiple_peaks(self):
        """Test with multiple peaks and troughs."""
        equity = [10000, 12000, 9000, 13000, 8000, 14000]
        mdd = KPICalculator.calculate_max_drawdown(equity)
        # Max drawdown is from 13000 to 8000 = ~38.5%
        assert mdd > 30
        assert mdd < 45


class TestCalculateWinRate:
    """Tests for win rate calculation."""

    def test_win_rate_all_wins(self):
        """Test with all winning trades."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id=f"t{i}",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            )
            for i in range(5)
        ]
        assert KPICalculator.calculate_win_rate(trades) == 100.0

    def test_win_rate_all_losses(self):
        """Test with all losing trades."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id=f"t{i}",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=49000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=-1000,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            )
            for i in range(5)
        ]
        assert KPICalculator.calculate_win_rate(trades) == 0.0

    def test_win_rate_mixed(self):
        """Test with mixed wins and losses."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=2),
                exit_time=now - timedelta(hours=1),
            ),
            Trade(
                trade_id="t2",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=49000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=-1000,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]
        assert KPICalculator.calculate_win_rate(trades) == 50.0

    def test_win_rate_empty(self):
        """Test with no trades."""
        assert KPICalculator.calculate_win_rate([]) == 0.0


class TestCalculateProfitFactor:
    """Tests for profit factor calculation."""

    def test_profit_factor_normal(self):
        """Test with normal win/loss mix."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=2),
                exit_time=now - timedelta(hours=1),
            ),
            Trade(
                trade_id="t2",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=49500,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=-500,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]
        pf = KPICalculator.calculate_profit_factor(trades)
        assert pf == 2.0  # 1000 / 500

    def test_profit_factor_no_losses(self):
        """Test with no losing trades."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]
        pf = KPICalculator.calculate_profit_factor(trades)
        assert pf > 0

    def test_profit_factor_empty(self):
        """Test with no trades."""
        assert KPICalculator.calculate_profit_factor([]) == 0.0


class TestCalculateAverageTrade:
    """Tests for average trade calculation."""

    def test_average_trade_normal(self):
        """Test average trade calculation."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=2),
                exit_time=now - timedelta(hours=1),
            ),
            Trade(
                trade_id="t2",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=49000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=-500,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]
        avg = KPICalculator.calculate_average_trade(trades)
        assert avg == 250.0  # (1000 - 500) / 2

    def test_average_trade_empty(self):
        """Test with no trades."""
        assert KPICalculator.calculate_average_trade([]) == 0.0


class TestCalculateExpectancy:
    """Tests for expectancy calculation."""

    def test_expectancy_normal(self):
        """Test expectancy calculation."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=2),
                exit_time=now - timedelta(hours=1),
            ),
            Trade(
                trade_id="t2",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=49000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=-500,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]
        exp = KPICalculator.calculate_expectancy(trades)
        # Win rate 50%, avg win 1000, avg loss 500
        # Expectancy = 0.5 * 1000 - 0.5 * 500 = 250
        assert exp == 250.0

    def test_expectancy_empty(self):
        """Test with no trades."""
        assert KPICalculator.calculate_expectancy([]) == 0.0


class TestCalculateReturnsFromTrades:
    """Tests for returns calculation from trades."""

    def test_returns_from_trades(self):
        """Test returns calculation."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]
        returns = KPICalculator.calculate_returns_from_trades(trades)
        # Return = 1000 / (50000 * 1) = 0.02
        assert len(returns) == 1
        assert abs(returns[0] - 0.02) < 0.001

    def test_returns_empty(self):
        """Test with no trades."""
        assert KPICalculator.calculate_returns_from_trades([]) == []


class TestCalculateEquityCurve:
    """Tests for equity curve calculation."""

    def test_equity_curve(self):
        """Test equity curve calculation."""
        now = datetime.now(UTC)
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=2),
                exit_time=now - timedelta(hours=1),
            ),
            Trade(
                trade_id="t2",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=49000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=-500,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]
        curve = KPICalculator.calculate_equity_curve(trades, initial_equity=10000)
        assert curve[0] == 10000
        assert curve[1] == 11000
        assert curve[2] == 10500

    def test_equity_curve_empty(self):
        """Test with no trades."""
        curve = KPICalculator.calculate_equity_curve([], initial_equity=10000)
        assert curve == [10000]
