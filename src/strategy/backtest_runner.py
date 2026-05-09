"""Strategy-aware backtest runner - executes strategies against historical data.

ST-MVP-011: Provides a clean API for loading strategies from DSL
definitions, running them against historical OHLCV data, and collecting
ExecutionResult-format results.

This runner lives in src/strategy/ (not src/backtesting/) because it
uses the NEW protocol system. It is self-contained and does NOT replace
src/operations/backtest_runner.py (the operational one).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy.adapter import StrategyAdapter
from strategy.contracts import ExecutionResult


@dataclass(frozen=True)
class WalkForwardWindow:
    """A single window in a walk-forward analysis.

    Attributes:
        window_index: Zero-based index of this window.
        train_start: Start index of training data.
        train_end: End index of training data (exclusive).
        test_start: Start index of test data.
        test_end: End index of test data (exclusive).
        result: Execution result for this window (set after run).
    """

    window_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


class StrategyBacktestRunner:
    """Run backtests using registered strategies.

    Provides a clean API for:
    1. Loading strategy from DSL definition
    2. Loading historical data (accepts data as parameter)
    3. Running strategy execution
    4. Collecting results (ExecutionResult format)

    Usage::

        adapter = StrategyAdapter(registry)
        runner = StrategyBacktestRunner(adapter)
        result = runner.run_backtest(strategy_dsl, data, initial_capital=10000.0)
    """

    def __init__(self, adapter: StrategyAdapter) -> None:
        self._adapter = adapter

    @property
    def adapter(self) -> StrategyAdapter:
        """The strategy adapter used for DSL resolution."""
        return self._adapter

    def run_backtest(
        self,
        strategy_dsl: dict[str, Any],
        data: list[dict[str, Any]],
        initial_capital: float = 10000.0,
    ) -> ExecutionResult:
        """Run a single backtest.

        Args:
            strategy_dsl: Strategy definition as dict.
            data: Historical OHLCV data
                ``[{timestamp, open, high, low, close, volume}, ...]``.
            initial_capital: Starting capital.

        Returns:
            ExecutionResult with trades, pnl, metrics.
        """
        self._validate_data(data)

        strategy = self._adapter.adapt(strategy_dsl)
        config = self._adapter.adapt_config(strategy_dsl)

        if not strategy.validate_config(config):
            msg = "Invalid strategy configuration from DSL"
            raise ValueError(msg)

        raw_result = strategy.execute(
            strategy_config=config,
            data=data,
            initial_capital=initial_capital,
        )

        return self._to_execution_result(raw_result)

    def run_walk_forward(
        self,
        strategy_dsl: dict[str, Any],
        data: list[dict[str, Any]],
        train_window: int = 100,
        test_window: int = 25,
        initial_capital: float = 10000.0,
    ) -> list[ExecutionResult]:
        """Run walk-forward analysis.

        Splits data into train/test windows and runs sequential
        backtests, carrying forward the capital.

        Args:
            strategy_dsl: Strategy definition as dict.
            data: Historical OHLCV data.
            train_window: Number of bars in each training window.
            test_window: Number of bars in each test window.
            initial_capital: Starting capital.

        Returns:
            List of ExecutionResult, one per test window.
        """
        self._validate_data(data)

        if len(data) < train_window + test_window:
            msg = (
                f"Data length ({len(data)}) must be >= "
                f"train_window + test_window ({train_window + test_window})"
            )
            raise ValueError(msg)

        windows = self._create_windows(data, train_window, test_window)
        results: list[ExecutionResult] = []
        current_capital = initial_capital

        for wf_window in windows:
            test_data = data[wf_window.test_start : wf_window.test_end]

            strategy = self._adapter.adapt(strategy_dsl)
            config = self._adapter.adapt_config(strategy_dsl)

            if not strategy.validate_config(config):
                msg = "Invalid strategy configuration from DSL"
                raise ValueError(msg)

            raw_result = strategy.execute(
                strategy_config=config,
                data=test_data,
                initial_capital=current_capital,
            )

            result = self._to_execution_result(
                raw_result,
                extra_metadata={
                    "walk_forward_window": wf_window.window_index,
                    "train_start": wf_window.train_start,
                    "train_end": wf_window.train_end,
                    "test_start": wf_window.test_start,
                    "test_end": wf_window.test_end,
                },
            )
            results.append(result)

            # Carry forward capital for next window
            current_capital += result.pnl

        return results

    def _validate_data(self, data: list[dict[str, Any]]) -> None:
        """Validate that data has minimum required structure."""
        if not isinstance(data, list):
            msg = "data must be a list of dicts"
            raise TypeError(msg)

        if len(data) == 0:
            msg = "data must not be empty"
            raise ValueError(msg)

    def _create_windows(
        self,
        data: list[dict[str, Any]],
        train_window: int,
        test_window: int,
    ) -> list[WalkForwardWindow]:
        """Create walk-forward windows from data.

        Uses a simple sliding window approach:
        - Each window has a train period followed by a test period
        - Windows slide by test_window increments
        - The last window may have a smaller test period
        """
        windows: list[WalkForwardWindow] = []
        total_bars = len(data)
        step = test_window
        index = 0

        pos = train_window
        while pos < total_bars:
            test_end = min(pos + test_window, total_bars)
            # Skip if test window is too small (less than 1 bar)
            if test_end - pos < 1:
                break

            train_start = max(0, pos - train_window)

            windows.append(
                WalkForwardWindow(
                    window_index=index,
                    train_start=train_start,
                    train_end=pos,
                    test_start=pos,
                    test_end=test_end,
                )
            )
            index += 1
            pos += step

        return windows

    def _to_execution_result(
        self,
        raw_result: dict[str, Any],
        extra_metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Convert raw result dict to ExecutionResult dataclass."""
        metadata = raw_result.get("metadata", {})
        if extra_metadata:
            merged = dict(metadata)
            merged.update(extra_metadata)
            metadata = merged

        return ExecutionResult(
            trades=raw_result.get("trades", 0),
            pnl=raw_result.get("pnl", 0.0),
            sharpe=raw_result.get("sharpe", 0.0),
            max_drawdown=raw_result.get("max_drawdown", 0.0),
            win_rate=raw_result.get("win_rate", 0.0),
            metadata=metadata,
        )
