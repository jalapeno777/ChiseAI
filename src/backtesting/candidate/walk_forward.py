"""Walk-forward backtesting engine for candidate strategies.

This module implements walk-forward backtesting with configurable train/test
windows to prevent look-ahead bias and ensure robust strategy evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    WalkForwardWindow,
)


class DataProvider(Protocol):
    """Protocol for market data provider."""

    def get_ohlcv(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1h",
    ) -> list[dict]:
        """Fetch OHLCV data for a symbol and time range.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            start: Start timestamp
            end: End timestamp
            timeframe: Candle timeframe (default: 1h)

        Returns:
            List of OHLCV candles
        """
        ...


class StrategyExecutor(Protocol):
    """Protocol for strategy execution engine."""

    def execute(
        self,
        strategy_config: dict,
        data: list[dict],
        initial_capital: float = 10000.0,
    ) -> dict:
        """Execute strategy on historical data.

        Args:
            strategy_config: Strategy configuration dictionary
            data: OHLCV data to backtest on
            initial_capital: Starting capital for backtest

        Returns:
            Execution results with trades and equity curve
        """
        ...


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward backtesting.

    Attributes:
        train_days: Length of training window in days (default: 30)
        test_days: Length of test window in days (default: 7)
        step_days: Step size between windows in days (default: 7)
        min_train_samples: Minimum samples required for training
        min_test_samples: Minimum samples required for testing
    """

    train_days: int = 30
    test_days: int = 7
    step_days: int = 7
    min_train_samples: int = 100
    min_test_samples: int = 20

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.train_days <= 0:
            raise ValueError("train_days must be positive")
        if self.test_days <= 0:
            raise ValueError("test_days must be positive")
        if self.step_days <= 0:
            raise ValueError("step_days must be positive")


class WalkForwardEngine:
    """Engine for walk-forward backtesting.

        Implements walk-forward analysis with configurable train/test windows
    to ensure no look-ahead bias in strategy evaluation.
    """

    def __init__(
        self,
        config: WalkForwardConfig | None = None,
        data_provider: DataProvider | None = None,
        strategy_executor: StrategyExecutor | None = None,
    ):
        """Initialize walk-forward engine.

        Args:
            config: Walk-forward configuration
            data_provider: Data provider for market data
            strategy_executor: Strategy execution engine
        """
        self.config = config or WalkForwardConfig()
        self.data_provider = data_provider
        self.strategy_executor = strategy_executor

    def generate_windows(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[WalkForwardWindow]:
        """Generate walk-forward windows for a date range.

        Creates non-overlapping train/test windows with the configured
        step size. Each window has a training period followed by a
        test period with no overlap.

        Args:
            start_date: Overall start date for analysis
            end_date: Overall end date for analysis

        Returns:
            List of walk-forward windows
        """
        windows = []
        current_start = start_date

        train_delta = timedelta(days=self.config.train_days)
        test_delta = timedelta(days=self.config.test_days)
        step_delta = timedelta(days=self.config.step_days)

        while current_start + train_delta + test_delta <= end_date:
            train_start = current_start
            train_end = current_start + train_delta
            test_start = train_end
            test_end = test_start + test_delta

            # Ensure test doesn't exceed end_date
            if test_end > end_date:
                break

            windows.append(
                WalkForwardWindow(
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                )
            )

            current_start += step_delta

        return windows

    def run_backtest(
        self,
        candidate_result: CandidateResult,
        strategy_config: dict,
        symbol: str = "BTCUSDT",
    ) -> CandidateResult:
        """Run walk-forward backtest for a candidate.

        Args:
            candidate_result: Candidate result to populate
            strategy_config: Strategy configuration
            symbol: Trading symbol to backtest on

        Returns:
            Updated candidate result with metrics
        """
        if self.data_provider is None or self.strategy_executor is None:
            candidate_result.status = CandidateStatus.FAILED
            candidate_result.error_message = "Data provider or executor not configured"
            return candidate_result

        try:
            candidate_result.status = CandidateStatus.RUNNING

            # Fetch test data
            window = candidate_result.window
            data = self.data_provider.get_ohlcv(
                symbol=symbol,
                start=window.test_start,
                end=window.test_end,
                timeframe="1h",
            )

            if len(data) < self.config.min_test_samples:
                candidate_result.status = CandidateStatus.FAILED
                candidate_result.error_message = (
                    f"Insufficient data: {len(data)} samples, "
                    f"minimum {self.config.min_test_samples} required"
                )
                return candidate_result

            # Execute strategy
            execution_result = self.strategy_executor.execute(
                strategy_config=strategy_config,
                data=data,
                initial_capital=10000.0,
            )

            # Calculate metrics from execution result
            candidate_result.metrics = self._calculate_metrics(execution_result)
            candidate_result.status = CandidateStatus.COMPLETED
            candidate_result.completed_at = datetime.now(UTC)

        except Exception as e:
            candidate_result.status = CandidateStatus.FAILED
            candidate_result.error_message = str(e)

        return candidate_result

    def _calculate_metrics(self, execution_result: dict) -> BacktestMetrics:
        """Calculate backtest metrics from execution results.

        Args:
            execution_result: Raw execution results from strategy executor

        Returns:
            Calculated backtest metrics
        """
        trades = execution_result.get("trades", [])
        equity_curve = execution_result.get("equity_curve", [])

        if not trades or not equity_curve:
            return BacktestMetrics()

        # Calculate returns
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                ret = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                returns.append(ret)

        # Trade analysis
        winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in trades if t.get("pnl", 0) <= 0]

        total_trades = len(trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        # Calculate metrics
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(t.get("pnl", 0) for t in winning_trades)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # Total return
        initial = equity_curve[0] if equity_curve else 10000.0
        final = equity_curve[-1] if equity_curve else initial
        total_return = ((final - initial) / initial * 100) if initial > 0 else 0.0

        # Volatility (annualized)
        import math

        if len(returns) > 1:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            volatility = (
                math.sqrt(variance) * math.sqrt(365 * 24) * 100
            )  # Hourly to annual
        else:
            volatility = 0.0

        # Sharpe ratio (assuming 0% risk-free rate for simplicity)
        if volatility > 0:
            sharpe = (
                (total_return / 100) / (volatility / 100) if volatility > 0 else 0.0
            )
        else:
            sharpe = 0.0

        # Max drawdown
        max_dd = self._calculate_max_drawdown(equity_curve)

        # Calmar ratio
        calmar = (total_return / max_dd) if max_dd > 0 else 0.0

        # Sortino ratio (downside deviation only)
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_std = math.sqrt(
                sum(r**2 for r in downside_returns) / len(downside_returns)
            ) * math.sqrt(365 * 24)
            sortino = (total_return / 100) / downside_std if downside_std > 0 else 0.0
        else:
            sortino = 0.0

        # Trade statistics
        avg_trade = (
            sum(t.get("pnl_pct", 0) for t in trades) / total_trades
            if total_trades > 0
            else 0.0
        )
        avg_win = (
            sum(t.get("pnl_pct", 0) for t in winning_trades) / win_count
            if win_count > 0
            else 0.0
        )
        avg_loss = (
            sum(t.get("pnl_pct", 0) for t in losing_trades) / loss_count
            if loss_count > 0
            else 0.0
        )

        largest_win = max((t.get("pnl_pct", 0) for t in winning_trades), default=0.0)
        largest_loss = min((t.get("pnl_pct", 0) for t in losing_trades), default=0.0)

        # Consecutive trades
        max_consec_wins = 0
        max_consec_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in trades:
            if trade.get("pnl", 0) > 0:
                current_wins += 1
                current_losses = 0
                max_consec_wins = max(max_consec_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consec_losses = max(max_consec_losses, current_losses)

        return BacktestMetrics(
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            total_return_pct=total_return,
            volatility_pct=volatility,
            calmar_ratio=calmar,
            sortino_ratio=sortino,
            trade_count=total_trades,
            avg_trade_return_pct=avg_trade,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            largest_win_pct=largest_win,
            largest_loss_pct=largest_loss,
            consecutive_wins=max_consec_wins,
            consecutive_losses=max_consec_losses,
        )

    def _calculate_max_drawdown(self, equity_curve: list[float]) -> float:
        """Calculate maximum drawdown from equity curve.

        Args:
            equity_curve: List of equity values over time

        Returns:
            Maximum drawdown as percentage
        """
        if not equity_curve or len(equity_curve) < 2:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for equity in equity_curve:
            if equity > peak:
                peak = equity
            elif peak > 0:
                drawdown = (peak - equity) / peak * 100
                max_dd = max(max_dd, drawdown)

        return max_dd
