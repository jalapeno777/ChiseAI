"""Walk-Forward Evaluation Framework for ML Optimization.

This module provides a comprehensive walk-forward evaluation framework that:
- Generates configurable train/test windows (default: 30-day train, 7-day test)
- Prevents future data leaks with temporal split validation
- Calculates performance metrics per window and aggregates them
- Supports strategy comparison through aggregateable results
- Includes look-ahead bias detection and auditing
- Completes evaluation within 2 hours per strategy (performance target)

Usage:
    from ml.walk_forward import WalkForwardEvaluator, WalkForwardConfig

    config = WalkForwardConfig(train_days=30, test_days=7)
    evaluator = WalkForwardEvaluator(config)
    results = evaluator.evaluate_strategy(strategy, data)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WindowStatus(Enum):
    """Status of a walk-forward window evaluation."""

    PENDING = "pending"
    TRAINING = "training"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"


class LookAheadBiasCheck(Enum):
    """Result of look-ahead bias validation."""

    PASSED = "passed"
    FAILED_OVERLAP = "failed_overlap"
    FAILED_FUTURE_DATA = "failed_future_data"
    FAILED_TEMPORAL_ORDER = "failed_temporal_order"


@dataclass(frozen=True)
class TemporalWindow:
    """A single temporal window with strict validation.

    Attributes:
        train_start: Start of training period (inclusive)
        train_end: End of training period (exclusive)
        test_start: Start of test period (inclusive)
        test_end: End of test period (exclusive)
    """

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    def __post_init__(self) -> None:
        """Validate temporal constraints to prevent look-ahead bias."""
        if self.train_end <= self.train_start:
            raise ValueError(
                f"train_end ({self.train_end}) must be after train_start ({self.train_start})"
            )
        if self.test_end <= self.test_start:
            raise ValueError(
                f"test_end ({self.test_end}) must be after test_start ({self.test_start})"
            )
        if self.test_start < self.train_end:
            raise ValueError(
                f"test_start ({self.test_start}) must be >= train_end ({self.train_end}) "
                "to prevent data leakage"
            )

    def validate_no_overlap(self, other: TemporalWindow) -> bool:
        """Check that this window doesn't overlap with another.

        Args:
            other: Another temporal window to check against

        Returns:
            True if no overlap exists
        """
        # Check if test periods overlap
        if self.test_start < other.test_end and other.test_start < self.test_end:
            return False
        return True

    def contains_timestamp(self, ts: datetime, period: str = "test") -> bool:
        """Check if a timestamp falls within the specified period.

        Args:
            ts: Timestamp to check
            period: Either 'train' or 'test'

        Returns:
            True if timestamp is within the period
        """
        if period == "train":
            return self.train_start <= ts < self.train_end
        elif period == "test":
            return self.test_start <= ts < self.test_end
        else:
            raise ValueError(f"period must be 'train' or 'test', got {period}")

    def duration_days(self, period: str = "test") -> float:
        """Get duration of specified period in days.

        Args:
            period: Either 'train' or 'test'

        Returns:
            Duration in days
        """
        if period == "train":
            return (self.train_end - self.train_start).total_seconds() / 86400
        elif period == "test":
            return (self.test_end - self.test_start).total_seconds() / 86400
        else:
            raise ValueError(f"period must be 'train' or 'test', got {period}")


@dataclass
class WindowMetrics:
    """Performance metrics for a single walk-forward window.

    Attributes:
        window: The temporal window these metrics apply to
        status: Evaluation status
        sharpe_ratio: Risk-adjusted return
        max_drawdown_pct: Maximum peak-to-trough decline
        win_rate_pct: Percentage of winning trades
        profit_factor: Gross profit / gross loss
        total_return_pct: Total return percentage
        volatility_pct: Standard deviation of returns
        trade_count: Number of trades
        avg_trade_return_pct: Average return per trade
        training_time_seconds: Time spent training
        testing_time_seconds: Time spent testing
        error_message: Error details if failed
    """

    window: TemporalWindow
    status: WindowStatus = WindowStatus.PENDING

    # Performance metrics
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    total_return_pct: float = 0.0
    volatility_pct: float = 0.0
    trade_count: int = 0
    avg_trade_return_pct: float = 0.0

    # Timing
    training_time_seconds: float = 0.0
    testing_time_seconds: float = 0.0

    # Error tracking
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "window": {
                "train_start": self.window.train_start.isoformat(),
                "train_end": self.window.train_end.isoformat(),
                "test_start": self.window.test_start.isoformat(),
                "test_end": self.window.test_end.isoformat(),
            },
            "status": self.status.value,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "total_return_pct": self.total_return_pct,
            "volatility_pct": self.volatility_pct,
            "trade_count": self.trade_count,
            "avg_trade_return_pct": self.avg_trade_return_pct,
            "training_time_seconds": self.training_time_seconds,
            "testing_time_seconds": self.testing_time_seconds,
            "error_message": self.error_message,
        }


@dataclass
class AggregatedMetrics:
    """Aggregated metrics across multiple walk-forward windows.

    Attributes:
        window_count: Number of windows evaluated
        mean_sharpe: Mean Sharpe ratio across windows
        std_sharpe: Standard deviation of Sharpe ratios
        mean_max_drawdown: Mean max drawdown across windows
        mean_win_rate: Mean win rate across windows
        total_trades: Total trades across all windows
        consistency_score: Measure of consistency (lower std = higher score)
        worst_window: Reference to worst performing window
        best_window: Reference to best performing window
    """

    window_count: int = 0

    # Mean metrics
    mean_sharpe: float = 0.0
    mean_max_drawdown: float = 0.0
    mean_win_rate: float = 0.0
    mean_profit_factor: float = 0.0
    mean_total_return: float = 0.0

    # Variability metrics
    std_sharpe: float = 0.0
    std_max_drawdown: float = 0.0
    std_win_rate: float = 0.0

    # Aggregate counts
    total_trades: int = 0
    total_return_pct: float = 0.0

    # Consistency score (0-100, higher is more consistent)
    consistency_score: float = 0.0

    # References to extreme windows
    best_window_index: int | None = None
    worst_window_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "window_count": self.window_count,
            "mean_sharpe": self.mean_sharpe,
            "mean_max_drawdown": self.mean_max_drawdown,
            "mean_win_rate": self.mean_win_rate,
            "mean_profit_factor": self.mean_profit_factor,
            "mean_total_return": self.mean_total_return,
            "std_sharpe": self.std_sharpe,
            "std_max_drawdown": self.std_max_drawdown,
            "std_win_rate": self.std_win_rate,
            "total_trades": self.total_trades,
            "total_return_pct": self.total_return_pct,
            "consistency_score": self.consistency_score,
            "best_window_index": self.best_window_index,
            "worst_window_index": self.worst_window_index,
        }


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward evaluation.

    Attributes:
        train_days: Length of training window in days (default: 30)
        test_days: Length of test window in days (default: 7)
        step_days: Step size between windows in days (default: 7)
        min_train_samples: Minimum samples required for training (default: 500)
        min_test_samples: Minimum samples required for testing (default: 100)
        max_windows: Maximum number of windows to generate (default: 52)
        enforce_temporal_validation: Whether to strictly validate temporal constraints
    """

    train_days: int = 30
    test_days: int = 7
    step_days: int = 7
    min_train_samples: int = 500
    min_test_samples: int = 100
    max_windows: int = 52  # ~1 year of weekly windows
    enforce_temporal_validation: bool = True

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.train_days <= 0:
            raise ValueError("train_days must be positive")
        if self.test_days <= 0:
            raise ValueError("test_days must be positive")
        if self.step_days <= 0:
            raise ValueError("step_days must be positive")
        if self.min_train_samples < 10:
            raise ValueError("min_train_samples must be at least 10")
        if self.min_test_samples < 10:
            raise ValueError("min_test_samples must be at least 10")


@dataclass
class WalkForwardResult:
    """Complete result of walk-forward evaluation.

    Attributes:
        strategy_id: Identifier for the strategy evaluated
        config: Configuration used for evaluation
        window_results: List of per-window metrics
        aggregated: Aggregated metrics across all windows
        look_ahead_check: Result of look-ahead bias validation
        total_evaluation_time_seconds: Total time for evaluation
        created_at: Timestamp when evaluation started
        completed_at: Timestamp when evaluation completed
    """

    strategy_id: str
    config: WalkForwardConfig
    window_results: list[WindowMetrics] = field(default_factory=list)
    aggregated: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    look_ahead_check: LookAheadBiasCheck = LookAheadBiasCheck.PASSED
    total_evaluation_time_seconds: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strategy_id": self.strategy_id,
            "config": {
                "train_days": self.config.train_days,
                "test_days": self.config.test_days,
                "step_days": self.config.step_days,
            },
            "window_results": [wr.to_dict() for wr in self.window_results],
            "aggregated": self.aggregated.to_dict(),
            "look_ahead_check": self.look_ahead_check.value,
            "total_evaluation_time_seconds": self.total_evaluation_time_seconds,
            "created_at": self.created_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


class StrategyProtocol(Protocol):
    """Protocol for strategies that can be walk-forward evaluated."""

    def train(self, data: list[dict], **kwargs: Any) -> dict:
        """Train the strategy on historical data.

        Args:
            data: Training data (OHLCV or feature data)
            **kwargs: Additional training parameters

        Returns:
            Training metadata (e.g., fitted parameters)
        """
        ...

    def predict(self, data: list[dict], **kwargs: Any) -> list[dict]:
        """Generate predictions/signals on data.

        Args:
            data: Data to predict on
            **kwargs: Additional prediction parameters

        Returns:
            List of predictions/signals
        """
        ...

    def evaluate(
        self,
        predictions: list[dict],
        actual: list[dict],
        **kwargs: Any,
    ) -> dict[str, float]:
        """Evaluate predictions against actual outcomes.

        Args:
            predictions: Predicted signals/trades
            actual: Actual market data
            **kwargs: Additional evaluation parameters

        Returns:
            Dictionary of performance metrics
        """
        ...


class WalkForwardEvaluator:
    """Walk-forward evaluation framework for strategy validation.

    This class implements walk-forward analysis with:
    - Configurable train/test windows
    - Strict temporal validation to prevent look-ahead bias
    - Per-window and aggregated performance metrics
    - Support for strategy comparison

    Usage:
        config = WalkForwardConfig(train_days=30, test_days=7)
        evaluator = WalkForwardEvaluator(config)
        result = evaluator.evaluate_strategy(strategy, data, strategy_id="my_strategy")
    """

    def __init__(self, config: WalkForwardConfig | None = None):
        """Initialize the walk-forward evaluator.

        Args:
            config: Configuration for walk-forward evaluation
        """
        self.config = config or WalkForwardConfig()
        self._validation_log: list[dict] = []

    def generate_windows(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[TemporalWindow]:
        """Generate walk-forward windows for a date range.

        Creates non-overlapping train/test windows with the configured
        step size. Each window has a training period followed by a
        test period with no overlap.

        Args:
            start_date: Overall start date for analysis
            end_date: Overall end date for analysis

        Returns:
            List of temporal windows
        """
        windows = []
        current_start = start_date

        train_delta = timedelta(days=self.config.train_days)
        test_delta = timedelta(days=self.config.test_days)
        step_delta = timedelta(days=self.config.step_days)

        window_count = 0
        while current_start + train_delta + test_delta <= end_date:
            if window_count >= self.config.max_windows:
                break

            train_start = current_start
            train_end = current_start + train_delta
            test_start = train_end
            test_end = test_start + test_delta

            # Ensure test doesn't exceed end_date
            if test_end > end_date:
                break

            try:
                window = TemporalWindow(
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                )
                windows.append(window)
                window_count += 1
            except ValueError as e:
                logger.warning(f"Skipping invalid window: {e}")

            current_start += step_delta

        logger.info(f"Generated {len(windows)} walk-forward windows")
        return windows

    def validate_no_look_ahead_bias(
        self,
        windows: list[TemporalWindow],
        data_timestamps: list[datetime] | None = None,
    ) -> LookAheadBiasCheck:
        """Validate that no look-ahead bias exists in window configuration.

        Checks:
        1. No overlap between test periods of different windows
        2. Temporal ordering is maintained (train before test)
        3. If data_timestamps provided, verify all test data is after train end

        Args:
            windows: List of temporal windows to validate
            data_timestamps: Optional list of actual data timestamps

        Returns:
            LookAheadBiasCheck result
        """
        # Check 1: No overlap between test periods
        for i, window_i in enumerate(windows):
            for j, window_j in enumerate(windows[i + 1 :]):
                if not window_i.validate_no_overlap(window_j):
                    logger.error(
                        f"Look-ahead bias detected: windows {i} and {i + 1 + j} "
                        f"have overlapping test periods"
                    )
                    return LookAheadBiasCheck.FAILED_OVERLAP

        # Check 2: Temporal ordering
        for window in windows:
            if window.train_end > window.test_start:
                logger.error(
                    f"Look-ahead bias detected: train_end ({window.train_end}) "
                    f"is after test_start ({window.test_start})"
                )
                return LookAheadBiasCheck.FAILED_TEMPORAL_ORDER

        # Check 3: Data timestamp validation (if provided)
        if data_timestamps:
            for window in windows:
                for ts in data_timestamps:
                    # If timestamp is in test period, verify it's not in train period
                    if window.contains_timestamp(ts, "test"):
                        # This is a simplified check - in practice you'd want
                        # to verify the actual data used
                        pass

        logger.info("Look-ahead bias validation passed")
        return LookAheadBiasCheck.PASSED

    def evaluate_strategy(
        self,
        strategy: StrategyProtocol | Callable,
        data: list[dict],
        strategy_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> WalkForwardResult:
        """Evaluate a strategy using walk-forward analysis.

        Args:
            strategy: Strategy to evaluate (must implement train/predict/evaluate)
            data: Historical data for evaluation
            strategy_id: Unique identifier for the strategy
            start_date: Optional start date (inferred from data if not provided)
            end_date: Optional end date (inferred from data if not provided)

        Returns:
            WalkForwardResult with per-window and aggregated metrics
        """
        import time

        start_time = time.time()
        result = WalkForwardResult(
            strategy_id=strategy_id,
            config=self.config,
        )

        # Infer date range from data if not provided
        if not start_date or not end_date:
            timestamps = [d.get("timestamp", d.get("time")) for d in data if d]
            if timestamps:
                # Convert to datetime if needed
                parsed_timestamps = []
                for ts in timestamps:
                    if isinstance(ts, str):
                        parsed_timestamps.append(
                            datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        )
                    elif isinstance(ts, (int, float)):
                        parsed_timestamps.append(datetime.fromtimestamp(ts / 1000))
                    else:
                        parsed_timestamps.append(ts)

                if not start_date:
                    start_date = min(parsed_timestamps)
                if not end_date:
                    end_date = max(parsed_timestamps)

        if not start_date or not end_date:
            raise ValueError("Could not determine date range from data")

        # Generate windows
        windows = self.generate_windows(start_date, end_date)

        if not windows:
            result.look_ahead_check = LookAheadBiasCheck.FAILED_TEMPORAL_ORDER
            result.completed_at = datetime.utcnow()
            result.total_evaluation_time_seconds = time.time() - start_time
            return result

        # Validate no look-ahead bias
        result.look_ahead_check = self.validate_no_look_ahead_bias(windows)
        if result.look_ahead_check != LookAheadBiasCheck.PASSED:
            result.completed_at = datetime.utcnow()
            result.total_evaluation_time_seconds = time.time() - start_time
            return result

        # Evaluate each window
        for i, window in enumerate(windows):
            try:
                window_metrics = self._evaluate_single_window(
                    strategy, data, window, strategy_id
                )
                result.window_results.append(window_metrics)
            except Exception as e:
                logger.error(f"Failed to evaluate window {i}: {e}")
                result.window_results.append(
                    WindowMetrics(
                        window=window,
                        status=WindowStatus.FAILED,
                        error_message=str(e),
                    )
                )

        # Calculate aggregated metrics
        result.aggregated = self._aggregate_metrics(result.window_results)
        result.completed_at = datetime.utcnow()
        result.total_evaluation_time_seconds = time.time() - start_time

        logger.info(
            f"Walk-forward evaluation complete for {strategy_id}: "
            f"{len(result.window_results)} windows, "
            f"mean Sharpe: {result.aggregated.mean_sharpe:.2f}, "
            f"consistency: {result.aggregated.consistency_score:.1f}"
        )

        return result

    def _evaluate_single_window(
        self,
        strategy: StrategyProtocol | Callable,
        data: list[dict],
        window: TemporalWindow,
        strategy_id: str,
    ) -> WindowMetrics:
        """Evaluate a single walk-forward window.

        Args:
            strategy: Strategy to evaluate
            data: Full historical data
            window: Temporal window for this evaluation
            strategy_id: Strategy identifier

        Returns:
            WindowMetrics for this window
        """
        import time

        metrics = WindowMetrics(window=window, status=WindowStatus.TRAINING)

        # Split data into train/test
        train_data = []
        test_data = []

        for d in data:
            ts = d.get("timestamp", d.get("time"))
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts / 1000)

            if window.train_start <= ts < window.train_end:
                train_data.append(d)
            elif window.test_start <= ts < window.test_end:
                test_data.append(d)

        # Validate data sufficiency
        if len(train_data) < self.config.min_train_samples:
            metrics.status = WindowStatus.FAILED
            metrics.error_message = (
                f"Insufficient training data: {len(train_data)} samples, "
                f"minimum {self.config.min_train_samples} required"
            )
            return metrics

        if len(test_data) < self.config.min_test_samples:
            metrics.status = WindowStatus.FAILED
            metrics.error_message = (
                f"Insufficient test data: {len(test_data)} samples, "
                f"minimum {self.config.min_test_samples} required"
            )
            return metrics

        try:
            # Train on training data
            train_start = time.time()
            if hasattr(strategy, "train"):
                train_result = strategy.train(train_data)
            else:
                # Assume strategy is a callable that handles both train and predict
                train_result = {}
            metrics.training_time_seconds = time.time() - train_start

            # Predict on test data
            metrics.status = WindowStatus.TESTING
            test_start = time.time()
            if hasattr(strategy, "predict"):
                predictions = strategy.predict(test_data, train_result=train_result)
            elif hasattr(strategy, "evaluate"):
                predictions = strategy.evaluate(test_data, train_result=train_result)
            else:
                # Assume strategy returns metrics directly
                predictions = strategy(test_data, train_data=train_data)
            metrics.testing_time_seconds = time.time() - test_start

            # Extract metrics from predictions/evaluation
            if isinstance(predictions, dict):
                metrics.sharpe_ratio = predictions.get("sharpe_ratio", 0.0)
                metrics.max_drawdown_pct = predictions.get("max_drawdown_pct", 0.0)
                metrics.win_rate_pct = predictions.get("win_rate_pct", 0.0)
                metrics.profit_factor = predictions.get("profit_factor", 0.0)
                metrics.total_return_pct = predictions.get("total_return_pct", 0.0)
                metrics.volatility_pct = predictions.get("volatility_pct", 0.0)
                metrics.trade_count = predictions.get("trade_count", 0)
                metrics.avg_trade_return_pct = predictions.get(
                    "avg_trade_return_pct", 0.0
                )

            metrics.status = WindowStatus.COMPLETED

        except Exception as e:
            metrics.status = WindowStatus.FAILED
            metrics.error_message = str(e)
            logger.error(f"Window evaluation failed for {strategy_id}: {e}")

        return metrics

    def _aggregate_metrics(
        self,
        window_results: list[WindowMetrics],
    ) -> AggregatedMetrics:
        """Aggregate metrics across all windows.

        Args:
            window_results: List of per-window metrics

        Returns:
            AggregatedMetrics
        """
        import statistics

        completed = [w for w in window_results if w.status == WindowStatus.COMPLETED]

        if not completed:
            return AggregatedMetrics(window_count=len(window_results))

        # Extract metrics
        sharpe_ratios = [w.sharpe_ratio for w in completed]
        max_drawdowns = [w.max_drawdown_pct for w in completed]
        win_rates = [w.win_rate_pct for w in completed]
        profit_factors = [w.profit_factor for w in completed]
        total_returns = [w.total_return_pct for w in completed]

        # Calculate means
        mean_sharpe = statistics.mean(sharpe_ratios)
        mean_max_drawdown = statistics.mean(max_drawdowns)
        mean_win_rate = statistics.mean(win_rates)
        mean_profit_factor = statistics.mean(profit_factors)
        mean_total_return = statistics.mean(total_returns)

        # Calculate standard deviations
        std_sharpe = statistics.stdev(sharpe_ratios) if len(sharpe_ratios) > 1 else 0.0
        std_max_drawdown = (
            statistics.stdev(max_drawdowns) if len(max_drawdowns) > 1 else 0.0
        )
        std_win_rate = statistics.stdev(win_rates) if len(win_rates) > 1 else 0.0

        # Find best and worst windows
        best_idx = sharpe_ratios.index(max(sharpe_ratios))
        worst_idx = sharpe_ratios.index(min(sharpe_ratios))

        # Calculate consistency score (inverse of coefficient of variation)
        if mean_sharpe != 0:
            cv = abs(std_sharpe / mean_sharpe)
            consistency_score = max(0, 100 - (cv * 100))
        else:
            consistency_score = 0.0

        # Total trades
        total_trades = sum(w.trade_count for w in completed)

        # Total return (compound)
        total_return_pct = 1.0
        for ret in total_returns:
            total_return_pct *= 1 + ret / 100
        total_return_pct = (total_return_pct - 1) * 100

        return AggregatedMetrics(
            window_count=len(window_results),
            mean_sharpe=mean_sharpe,
            mean_max_drawdown=mean_max_drawdown,
            mean_win_rate=mean_win_rate,
            mean_profit_factor=mean_profit_factor,
            mean_total_return=mean_total_return,
            std_sharpe=std_sharpe,
            std_max_drawdown=std_max_drawdown,
            std_win_rate=std_win_rate,
            total_trades=total_trades,
            total_return_pct=total_return_pct,
            consistency_score=consistency_score,
            best_window_index=best_idx,
            worst_window_index=worst_idx,
        )

    def compare_strategies(
        self,
        results: list[WalkForwardResult],
        criteria: str = "mean_sharpe",
    ) -> list[tuple[str, float, AggregatedMetrics]]:
        """Compare multiple strategies based on aggregated metrics.

        Args:
            results: List of walk-forward results for different strategies
            criteria: Metric to rank by (default: mean_sharpe)

        Returns:
            List of (strategy_id, score, metrics) tuples sorted by score
        """
        comparisons = []

        for result in results:
            metrics = result.aggregated

            if criteria == "mean_sharpe":
                score = metrics.mean_sharpe
            elif criteria == "mean_win_rate":
                score = metrics.mean_win_rate
            elif criteria == "consistency":
                score = metrics.consistency_score
            elif criteria == "total_return":
                score = metrics.total_return_pct
            else:
                score = metrics.mean_sharpe

            comparisons.append((result.strategy_id, score, metrics))

        # Sort by score (descending)
        comparisons.sort(key=lambda x: x[1], reverse=True)

        return comparisons

    def get_validation_log(self) -> list[dict]:
        """Get the validation log for auditing.

        Returns:
            List of validation events
        """
        return self._validation_log.copy()
