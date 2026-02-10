"""Prediction accuracy calculation per signal type and confidence bucket.

Provides the PredictionAccuracyCalculator class for calculating accuracy
metrics, win rates, and performance statistics grouped by signal type
and confidence bucket.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_storage.interface import SignalStorageInterface

logger = logging.getLogger(__name__)

# Default confidence buckets (0-10%, 10-20%, ..., 90-100%)
DEFAULT_CONFIDENCE_BUCKETS = [
    "0-10",
    "10-20",
    "20-30",
    "30-40",
    "40-50",
    "50-60",
    "60-70",
    "70-80",
    "80-90",
    "90-100",
]


def get_confidence_bucket(confidence: float) -> str:
    """Get confidence bucket for a confidence value.

    Args:
        confidence: Confidence value (0.0-1.0)

    Returns:
        Bucket string (e.g., "70-80" for 75% confidence)
    """
    confidence_pct = int(confidence * 100)
    lower = (confidence_pct // 10) * 10
    upper = lower + 10
    return f"{lower}-{upper}"


@dataclass
class AccuracyMetrics:
    """Accuracy metrics for a signal type or confidence bucket.

    Attributes:
        total_signals: Total number of signals
        resolved_signals: Number with outcomes recorded
        wins: Number of winning outcomes
        losses: Number of losing outcomes
        accuracy: Win rate (0.0-1.0)
        win_rate: Same as accuracy
        avg_pnl: Average PnL per trade
        total_pnl: Total PnL across all trades
        avg_duration_hours: Average trade duration in hours
        signal_type: Signal type identifier (optional)
        confidence_bucket: Confidence bucket (optional)
    """

    total_signals: int = 0
    resolved_signals: int = 0
    wins: int = 0
    losses: int = 0
    accuracy: float = 0.0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    total_pnl: float = 0.0
    avg_duration_hours: float = 0.0
    signal_type: str | None = None
    confidence_bucket: str | None = None

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        if self.resolved_signals > 0:
            self.accuracy = self.wins / self.resolved_signals
            self.win_rate = self.accuracy
            self.avg_pnl = self.total_pnl / self.resolved_signals

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_signals": self.total_signals,
            "resolved_signals": self.resolved_signals,
            "wins": self.wins,
            "losses": self.losses,
            "accuracy": round(self.accuracy, 4),
            "win_rate": round(self.win_rate, 4),
            "avg_pnl": round(self.avg_pnl, 8),
            "total_pnl": round(self.total_pnl, 8),
            "avg_duration_hours": round(self.avg_duration_hours, 2),
            "signal_type": self.signal_type,
            "confidence_bucket": self.confidence_bucket,
        }


@dataclass
class AccuracyReport:
    """Comprehensive accuracy report across signal types and confidence buckets.

    Attributes:
        overall: Overall accuracy metrics
        by_signal_type: Metrics grouped by signal type
        by_confidence_bucket: Metrics grouped by confidence bucket
        by_combination: Metrics grouped by signal type + confidence bucket
        timeframe: Time range of the report
        filters: Filters applied to generate the report
    """

    overall: AccuracyMetrics = field(default_factory=AccuracyMetrics)
    by_signal_type: dict[str, AccuracyMetrics] = field(default_factory=dict)
    by_confidence_bucket: dict[str, AccuracyMetrics] = field(default_factory=dict)
    by_combination: dict[str, AccuracyMetrics] = field(default_factory=dict)
    timeframe: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall": self.overall.to_dict(),
            "by_signal_type": {k: v.to_dict() for k, v in self.by_signal_type.items()},
            "by_confidence_bucket": {
                k: v.to_dict() for k, v in self.by_confidence_bucket.items()
            },
            "by_combination": {k: v.to_dict() for k, v in self.by_combination.items()},
            "timeframe": self.timeframe,
            "filters": self.filters,
        }

    def get_best_performing(
        self,
        min_signals: int = 10,
        metric: str = "accuracy",
    ) -> list[tuple[str, AccuracyMetrics]]:
        """Get best performing signal types or buckets.

        Args:
            min_signals: Minimum number of signals required
            metric: Metric to sort by ("accuracy", "win_rate", "avg_pnl", "total_pnl")

        Returns:
            List of (key, metrics) tuples sorted by performance
        """
        results = []
        for key, metrics in self.by_combination.items():
            if metrics.total_signals >= min_signals:
                results.append((key, metrics))

        # Sort by specified metric (descending)
        reverse = metric != "avg_duration_hours"  # Lower duration is better
        results.sort(key=lambda x: getattr(x[1], metric, 0), reverse=reverse)

        return results


class PredictionAccuracyCalculator:
    """Calculates prediction accuracy metrics per signal type and confidence bucket.

    Provides methods to:
    - Calculate accuracy for specific signal types
    - Calculate accuracy for confidence buckets
    - Generate comprehensive accuracy reports
    - Compare performance across different configurations
    """

    def __init__(
        self,
        storage: SignalStorageInterface,
        confidence_buckets: list[str] | None = None,
    ):
        """Initialize accuracy calculator.

        Args:
            storage: Storage backend for querying signals
            confidence_buckets: Custom confidence buckets (uses defaults if None)
        """
        self.storage = storage
        self.confidence_buckets = confidence_buckets or DEFAULT_CONFIDENCE_BUCKETS

    async def calculate_accuracy(
        self,
        signal_type: str | None = None,
        confidence_bucket: str | None = None,
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
    ) -> AccuracyMetrics:
        """Calculate accuracy metrics for specified filters.

        Args:
            signal_type: Filter by signal type (e.g., "LONG_rsi_macd")
            confidence_bucket: Filter by confidence bucket (e.g., "70-80")
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used

        Returns:
            AccuracyMetrics for the filtered signals
        """
        result = await self.storage.calculate_prediction_accuracy(
            signal_type=signal_type,
            confidence_bucket=confidence_bucket,
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
        )

        metrics = AccuracyMetrics(
            total_signals=result.get("total_signals", 0),
            resolved_signals=result.get("resolved_signals", 0),
            wins=result.get("wins", 0),
            losses=result.get("losses", 0),
            avg_pnl=result.get("avg_pnl", 0.0),
            total_pnl=result.get("total_pnl", 0.0),
            avg_duration_hours=result.get("avg_duration_hours", 0.0),
            signal_type=signal_type,
            confidence_bucket=confidence_bucket,
        )

        return metrics

    async def calculate_by_signal_type(
        self,
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        min_signals: int = 5,
    ) -> dict[str, AccuracyMetrics]:
        """Calculate accuracy grouped by signal type.

        Args:
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            min_signals: Minimum signals required for inclusion

        Returns:
            Dictionary mapping signal type to AccuracyMetrics
        """
        # Get all signals with outcomes
        signals_with_outcomes = await self.storage.query_signals_with_outcomes(
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
            resolved_only=True,
            limit=10000,
        )

        # Group by signal type
        by_type: dict[str, list] = {}
        for swo in signals_with_outcomes:
            st = swo.signal.signal_type
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(swo)

        # Calculate metrics for each type
        results = {}
        for signal_type, swo_list in by_type.items():
            if len(swo_list) >= min_signals:
                wins = sum(1 for swo in swo_list if swo.outcome and swo.outcome.is_win)
                total_pnl = sum(swo.outcome.pnl for swo in swo_list if swo.outcome)
                avg_duration = sum(
                    swo.outcome.duration_hours for swo in swo_list if swo.outcome
                ) / len(swo_list)

                results[signal_type] = AccuracyMetrics(
                    total_signals=len(swo_list),
                    resolved_signals=len(swo_list),
                    wins=wins,
                    losses=len(swo_list) - wins,
                    total_pnl=total_pnl,
                    avg_duration_hours=avg_duration,
                    signal_type=signal_type,
                )

        return results

    async def calculate_by_confidence_bucket(
        self,
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        min_signals: int = 5,
    ) -> dict[str, AccuracyMetrics]:
        """Calculate accuracy grouped by confidence bucket.

        Args:
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            min_signals: Minimum signals required for inclusion

        Returns:
            Dictionary mapping confidence bucket to AccuracyMetrics
        """
        results = {}

        for bucket in self.confidence_buckets:
            metrics = await self.calculate_accuracy(
                confidence_bucket=bucket,
                token=token,
                start_time=start_time,
                end_time=end_time,
                indicators=indicators,
            )

            if metrics.total_signals >= min_signals:
                metrics.confidence_bucket = bucket
                results[bucket] = metrics

        return results

    async def generate_report(
        self,
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        min_signals: int = 5,
    ) -> AccuracyReport:
        """Generate comprehensive accuracy report.

        Args:
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            min_signals: Minimum signals required for breakdowns

        Returns:
            AccuracyReport with overall and grouped metrics
        """
        # Calculate overall metrics
        overall = await self.calculate_accuracy(
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
        )

        # Calculate by signal type
        by_signal_type = await self.calculate_by_signal_type(
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
            min_signals=min_signals,
        )

        # Calculate by confidence bucket
        by_confidence_bucket = await self.calculate_by_confidence_bucket(
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
            min_signals=min_signals,
        )

        # Calculate by combination (signal type + confidence bucket)
        by_combination = await self._calculate_by_combination(
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
            min_signals=min_signals,
        )

        return AccuracyReport(
            overall=overall,
            by_signal_type=by_signal_type,
            by_confidence_bucket=by_confidence_bucket,
            by_combination=by_combination,
            timeframe={
                "start_time": start_time,
                "end_time": end_time,
            },
            filters={
                "token": token,
                "indicators": indicators,
                "min_signals": min_signals,
            },
        )

    async def _calculate_by_combination(
        self,
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        min_signals: int = 5,
    ) -> dict[str, AccuracyMetrics]:
        """Calculate accuracy grouped by signal type + confidence bucket combination.

        Args:
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            min_signals: Minimum signals required for inclusion

        Returns:
            Dictionary mapping "signal_type|bucket" to AccuracyMetrics
        """
        # Get all signals with outcomes
        signals_with_outcomes = await self.storage.query_signals_with_outcomes(
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
            resolved_only=True,
            limit=10000,
        )

        # Group by combination
        by_combo: dict[str, list] = {}
        for swo in signals_with_outcomes:
            combo_key = f"{swo.signal.signal_type}|{swo.signal.confidence_bucket}"
            if combo_key not in by_combo:
                by_combo[combo_key] = []
            by_combo[combo_key].append(swo)

        # Calculate metrics for each combination
        results = {}
        for combo_key, swo_list in by_combo.items():
            if len(swo_list) >= min_signals:
                wins = sum(1 for swo in swo_list if swo.outcome and swo.outcome.is_win)
                total_pnl = sum(swo.outcome.pnl for swo in swo_list if swo.outcome)
                avg_duration = sum(
                    swo.outcome.duration_hours for swo in swo_list if swo.outcome
                ) / len(swo_list)

                signal_type, bucket = combo_key.split("|")
                results[combo_key] = AccuracyMetrics(
                    total_signals=len(swo_list),
                    resolved_signals=len(swo_list),
                    wins=wins,
                    losses=len(swo_list) - wins,
                    total_pnl=total_pnl,
                    avg_duration_hours=avg_duration,
                    signal_type=signal_type,
                    confidence_bucket=bucket,
                )

        return results

    async def compare_configurations(
        self,
        configurations: list[dict[str, Any]],
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[tuple[dict[str, Any], AccuracyMetrics]]:
        """Compare accuracy across different indicator configurations.

        Args:
            configurations: List of configuration dicts with "indicators" key
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)

        Returns:
            List of (configuration, metrics) tuples
        """
        results = []
        for config in configurations:
            indicators = config.get("indicators", [])
            metrics = await self.calculate_accuracy(
                token=token,
                start_time=start_time,
                end_time=end_time,
                indicators=indicators if indicators else None,
            )
            results.append((config, metrics))

        # Sort by accuracy (descending)
        results.sort(key=lambda x: x[1].accuracy, reverse=True)

        return results
