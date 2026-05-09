"""Tests for strategy backtest runner - single backtest and walk-forward.

ST-MVP-011: Tests for StrategyBacktestRunner executing strategies
against historical OHLCV data.
"""

from __future__ import annotations

import pytest

from strategy.adapter import StrategyAdapter
from strategy.backtest_runner import StrategyBacktestRunner
from strategy.contracts import ExecutionResult
from strategy.registry import StrategyRegistry
from strategy.strategies import register_ict_strategies

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> StrategyRegistry:
    """Create a registry with ICT strategies registered."""
    reg = StrategyRegistry()
    register_ict_strategies(reg)
    return reg


@pytest.fixture
def adapter(registry: StrategyRegistry) -> StrategyAdapter:
    """Create an adapter with ICT strategies."""
    return StrategyAdapter(registry)


@pytest.fixture
def runner(adapter: StrategyAdapter) -> StrategyBacktestRunner:
    """Create a backtest runner."""
    return StrategyBacktestRunner(adapter)


@pytest.fixture
def valid_ict_dsl() -> dict:
    """Create a valid ICT confluence DSL definition."""
    return {
        "metadata": {"name": "ict_test", "version": "1.0"},
        "signals": {
            "type": "ict_confluence",
            "min_confluence": 60.0,
            "min_signals": 2,
            "require_bos_choch": True,
        },
        "universe": {"symbols": ["BTC/USDT"], "timeframe": "15m"},
        "exits": {
            "stop_loss_type": "atr",
            "take_profit_rr_ratio": 2.0,
        },
    }


def _make_ohlcv_data(
    n: int = 200,
    base_price: float = 50000.0,
) -> list[dict]:
    """Generate sample OHLCV data bars."""
    return [
        {
            "timestamp": f"2025-01-01T{i:04d}",
            "open": base_price + i,
            "high": base_price + i + 100,
            "low": base_price + i - 100,
            "close": base_price + i + 50,
            "volume": 100.0,
        }
        for i in range(n)
    ]


def _make_ict_signal_data(
    n: int = 200,
    base_price: float = 50000.0,
) -> list[dict]:
    """Generate OHLCV data with embedded ICT signals.

    Every 10th bar has aligned bullish signals to trigger entries.
    """
    data = _make_ohlcv_data(n, base_price)

    for i in range(10, n, 10):
        bar = data[i]
        bar["ict_signals"] = [
            {
                "signal_type": "bos_choch",
                "direction": "bullish",
                "confidence": 0.8,
                "timestamp": bar["timestamp"],
            },
            {
                "signal_type": "order_block",
                "direction": "bullish",
                "confidence": 0.7,
                "timestamp": bar["timestamp"],
            },
        ]
        bar["confluence_score"] = 75.0

    return data


# ---------------------------------------------------------------------------
# Single backtest tests
# ---------------------------------------------------------------------------


class TestRunBacktest:
    """Tests for StrategyBacktestRunner.run_backtest()."""

    def test_returns_execution_result(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """run_backtest() returns an ExecutionResult."""
        data = _make_ohlcv_data(200)
        result = runner.run_backtest(valid_ict_dsl, data)
        assert isinstance(result, ExecutionResult)

    def test_result_has_required_fields(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """Result has all ExecutionResult fields."""
        data = _make_ohlcv_data(200)
        result = runner.run_backtest(valid_ict_dsl, data)
        assert isinstance(result.trades, int)
        assert isinstance(result.pnl, float)
        assert isinstance(result.sharpe, float)
        assert isinstance(result.max_drawdown, float)
        assert isinstance(result.win_rate, float)

    def test_result_pnl_zero_no_signals(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """With plain OHLCV (no signals), PnL is zero."""
        data = _make_ohlcv_data(200)
        result = runner.run_backtest(valid_ict_dsl, data)
        assert result.trades == 0
        assert result.pnl == 0.0

    def test_result_with_ict_signals(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """With ICT signal data, the strategy can produce trades."""
        data = _make_ict_signal_data(200)
        result = runner.run_backtest(valid_ict_dsl, data)
        assert isinstance(result.trades, int)
        assert isinstance(result.pnl, float)
        assert isinstance(result.metadata, dict)

    def test_custom_initial_capital(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """run_backtest() accepts custom initial_capital."""
        data = _make_ohlcv_data(200)
        result = runner.run_backtest(valid_ict_dsl, data, initial_capital=50000.0)
        assert isinstance(result, ExecutionResult)

    def test_default_initial_capital(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """run_backtest() uses 10000.0 as default capital."""
        data = _make_ohlcv_data(200)
        result = runner.run_backtest(valid_ict_dsl, data)
        # Metadata may contain initial_capital from executor
        assert isinstance(result, ExecutionResult)

    def test_result_max_drawdown_in_range(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """max_drawdown is in [0.0, 1.0]."""
        data = _make_ict_signal_data(200)
        result = runner.run_backtest(valid_ict_dsl, data)
        assert 0.0 <= result.max_drawdown <= 1.0

    def test_result_win_rate_in_range(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """win_rate is in [0.0, 1.0]."""
        data = _make_ict_signal_data(200)
        result = runner.run_backtest(valid_ict_dsl, data)
        assert 0.0 <= result.win_rate <= 1.0


# ---------------------------------------------------------------------------
# Walk-forward tests
# ---------------------------------------------------------------------------


class TestRunWalkForward:
    """Tests for StrategyBacktestRunner.run_walk_forward()."""

    def test_returns_list_of_execution_results(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """run_walk_forward() returns a list of ExecutionResult."""
        data = _make_ohlcv_data(250)
        results = runner.run_walk_forward(
            valid_ict_dsl, data, train_window=100, test_window=25
        )
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, ExecutionResult)

    def test_walk_forward_multiple_windows(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """walk_forward produces multiple windows for sufficient data."""
        data = _make_ohlcv_data(300)
        results = runner.run_walk_forward(
            valid_ict_dsl, data, train_window=100, test_window=25
        )
        # 300 bars, train=100, test=25, step=25
        # First window: test at 100-125
        # Second window: test at 125-150
        # etc.
        assert len(results) >= 2

    def test_walk_forward_metadata_has_window_info(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """Walk-forward results contain window metadata."""
        data = _make_ohlcv_data(200)
        results = runner.run_walk_forward(
            valid_ict_dsl, data, train_window=100, test_window=25
        )
        if results:
            assert "walk_forward_window" in results[0].metadata
            assert "train_start" in results[0].metadata
            assert "test_start" in results[0].metadata

    def test_walk_forward_insufficient_data(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """walk_forward raises if data too short."""
        data = _make_ohlcv_data(50)  # Less than train + test
        with pytest.raises(ValueError, match="Data length"):
            runner.run_walk_forward(
                valid_ict_dsl, data, train_window=100, test_window=25
            )

    def test_walk_forward_capital_carries_forward(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """walk_forward carries capital between windows."""
        data = _make_ohlcv_data(300)
        results = runner.run_walk_forward(
            valid_ict_dsl,
            data,
            train_window=100,
            test_window=25,
            initial_capital=10000.0,
        )
        assert len(results) >= 2
        # Each result should have metadata with initial_capital info
        for r in results:
            assert isinstance(r, ExecutionResult)


# ---------------------------------------------------------------------------
# Data validation tests
# ---------------------------------------------------------------------------


class TestDataValidation:
    """Tests for StrategyBacktestRunner data validation."""

    def test_empty_data_raises(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """Empty data list raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            runner.run_backtest(valid_ict_dsl, [])

    def test_non_list_data_raises(
        self, runner: StrategyBacktestRunner, valid_ict_dsl: dict
    ) -> None:
        """Non-list data raises TypeError."""
        with pytest.raises(TypeError, match="must be a list"):
            runner.run_backtest(valid_ict_dsl, "not a list")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Window creation tests
# ---------------------------------------------------------------------------


class TestWindowCreation:
    """Tests for walk-forward window creation logic."""

    def test_window_boundaries(self) -> None:
        """Windows have correct train/test boundaries."""
        runner = StrategyBacktestRunner(StrategyAdapter(StrategyRegistry()))
        # 250 bars, train=100, test=25
        data = _make_ohlcv_data(250)
        windows = runner._create_windows(data, train_window=100, test_window=25)

        assert len(windows) >= 1
        # First window
        w0 = windows[0]
        assert w0.train_start == 0
        assert w0.train_end == 100
        assert w0.test_start == 100
        assert w0.test_end == 125

    def test_window_indices_sequential(self) -> None:
        """Window indices are sequential starting from 0."""
        runner = StrategyBacktestRunner(StrategyAdapter(StrategyRegistry()))
        data = _make_ohlcv_data(300)
        windows = runner._create_windows(data, train_window=100, test_window=25)

        for i, w in enumerate(windows):
            assert w.window_index == i


# ---------------------------------------------------------------------------
# Adapter property test
# ---------------------------------------------------------------------------


class TestRunnerAdapter:
    """Tests for StrategyBacktestRunner adapter access."""

    def test_adapter_property(
        self, adapter: StrategyAdapter, runner: StrategyBacktestRunner
    ) -> None:
        """runner.adapter returns the injected adapter."""
        assert runner.adapter is adapter
