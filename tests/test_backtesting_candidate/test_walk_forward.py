"""Tests for walk-forward backtesting engine."""

from datetime import datetime, timedelta

import pytest

from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    WalkForwardWindow,
)
from backtesting.candidate.walk_forward import (
    WalkForwardConfig,
    WalkForwardEngine,
)


class TestWalkForwardConfig:
    """Tests for WalkForwardConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = WalkForwardConfig()

        assert config.train_days == 30
        assert config.test_days == 7
        assert config.step_days == 7
        assert config.min_train_samples == 100
        assert config.min_test_samples == 20

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = WalkForwardConfig(
            train_days=60,
            test_days=14,
            step_days=14,
            min_train_samples=200,
        )

        assert config.train_days == 60
        assert config.test_days == 14
        assert config.step_days == 14
        assert config.min_train_samples == 200

    def test_invalid_train_days(self) -> None:
        """Test that invalid train_days raises error."""
        with pytest.raises(ValueError, match="train_days must be positive"):
            WalkForwardConfig(train_days=0)

    def test_invalid_test_days(self) -> None:
        """Test that invalid test_days raises error."""
        with pytest.raises(ValueError, match="test_days must be positive"):
            WalkForwardConfig(test_days=-1)

    def test_invalid_step_days(self) -> None:
        """Test that invalid step_days raises error."""
        with pytest.raises(ValueError, match="step_days must be positive"):
            WalkForwardConfig(step_days=0)


class TestWalkForwardEngine:
    """Tests for WalkForwardEngine."""

    def test_generate_windows_basic(self) -> None:
        """Test basic window generation."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        engine = WalkForwardEngine(config=config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)

        windows = engine.generate_windows(start, end)

        assert len(windows) > 0

        # Check first window
        first = windows[0]
        assert first.train_start == start
        assert first.train_end == start + timedelta(days=30)
        assert first.test_start == first.train_end
        assert first.test_end == first.test_start + timedelta(days=7)

    def test_generate_windows_non_overlapping(self) -> None:
        """Test that windows don't overlap."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        engine = WalkForwardEngine(config=config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)

        windows = engine.generate_windows(start, end)

        # Check no overlap between consecutive windows
        for i in range(len(windows) - 1):
            current = windows[i]
            next_window = windows[i + 1]
            # Next train should start at or after current test end minus step
            assert next_window.train_start >= current.train_start

    def test_generate_windows_step_size(self) -> None:
        """Test that windows respect step size."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=14)
        engine = WalkForwardEngine(config=config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)

        windows = engine.generate_windows(start, end)

        if len(windows) >= 2:
            # Check that consecutive windows are step_days apart
            first_start = windows[0].train_start
            second_start = windows[1].train_start
            assert (second_start - first_start).days == 14

    def test_generate_windows_insufficient_time(self) -> None:
        """Test that insufficient time range returns empty list."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        engine = WalkForwardEngine(config=config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 10)  # Only 9 days, need at least 37

        windows = engine.generate_windows(start, end)

        assert len(windows) == 0

    def test_calculate_max_drawdown(self) -> None:
        """Test max drawdown calculation."""
        engine = WalkForwardEngine()

        # Simple case: peak then drop
        equity = [100, 110, 105, 95, 100]
        max_dd = engine._calculate_max_drawdown(equity)

        # Peak at 110, trough at 95: (110-95)/110 = 13.64%
        assert max_dd > 0
        assert max_dd < 20

    def test_calculate_max_drawdown_no_drawdown(self) -> None:
        """Test max drawdown with no drawdown."""
        engine = WalkForwardEngine()

        equity = [100, 105, 110, 115, 120]
        max_dd = engine._calculate_max_drawdown(equity)

        assert max_dd == 0.0

    def test_calculate_max_drawdown_empty(self) -> None:
        """Test max drawdown with empty equity curve."""
        engine = WalkForwardEngine()

        max_dd = engine._calculate_max_drawdown([])
        assert max_dd == 0.0

        max_dd = engine._calculate_max_drawdown([100])
        assert max_dd == 0.0

    def test_calculate_metrics_empty_trades(self) -> None:
        """Test metrics calculation with empty trades."""
        engine = WalkForwardEngine()

        execution_result = {"trades": [], "equity_curve": []}
        metrics = engine._calculate_metrics(execution_result)

        assert isinstance(metrics, BacktestMetrics)
        assert metrics.trade_count == 0

    def test_calculate_metrics_with_trades(self) -> None:
        """Test metrics calculation with sample trades."""
        engine = WalkForwardEngine()

        trades = [
            {"pnl": 100, "pnl_pct": 1.0},
            {"pnl": -50, "pnl_pct": -0.5},
            {"pnl": 150, "pnl_pct": 1.5},
            {"pnl": -30, "pnl_pct": -0.3},
        ]
        equity_curve = [10000, 10100, 10050, 10200, 10170]

        execution_result = {"trades": trades, "equity_curve": equity_curve}
        metrics = engine._calculate_metrics(execution_result)

        assert metrics.trade_count == 4
        assert metrics.win_rate_pct == 50.0  # 2 wins out of 4
        assert (
            abs(metrics.total_return_pct - 1.7) < 0.01
        )  # (10170 - 10000) / 10000 * 100

    def test_run_backtest_no_provider(self) -> None:
        """Test backtest run without data provider fails gracefully."""
        engine = WalkForwardEngine()

        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 1, 31),
            test_start=datetime(2024, 1, 31),
            test_end=datetime(2024, 2, 7),
        )

        result = CandidateResult(
            candidate_id="test-001",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.PENDING,
            window=window,
        )

        result = engine.run_backtest(result, {})

        assert result.status == CandidateStatus.FAILED
        assert "not configured" in result.error_message

    def test_run_backtest_insufficient_data(self) -> None:
        """Test backtest with insufficient data fails gracefully."""
        config = WalkForwardConfig(min_test_samples=100)
        engine = WalkForwardEngine(config=config)

        # Mock data provider that returns insufficient data
        class MockProvider:
            def get_ohlcv(self, **kwargs):
                return [{"close": 100}] * 10  # Only 10 samples

        class MockExecutor:
            def execute(self, **kwargs):
                return {"trades": [], "equity_curve": []}

        engine.data_provider = MockProvider()
        engine.strategy_executor = MockExecutor()

        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 1, 31),
            test_start=datetime(2024, 1, 31),
            test_end=datetime(2024, 2, 7),
        )

        result = CandidateResult(
            candidate_id="test-001",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.PENDING,
            window=window,
        )

        result = engine.run_backtest(result, {})

        assert result.status == CandidateStatus.FAILED
        assert "Insufficient data" in result.error_message
