"""Prediction-Outcome Matcher for ML Feedback Loop.

This module provides functionality to match predictions from signal history
with actual outcomes for performance analysis and model improvement.

Features:
- Match predictions with outcomes using time-window based matching
- Handle multiple outcome types (TP hit, SL hit, manual close, timeout)
- Track match confidence and resolution status
- Support configurable matching windows per signal type
- Calculate match quality metrics (precision, recall, F1) per signal type
- Batch processing with graceful partial failure handling
- Integration with outcome capture service from ST-LAUNCH-006

Usage:
    from ml.feedback.matcher import (
        PredictionOutcomeMatcher,
        MatchConfig,
        MatchQualityMetrics,
        SignalType,
    )

    config = MatchConfig(matching_window_hours=24.0)
    matcher = PredictionOutcomeMatcher(signal_tracker, config)

    # Match predictions with outcomes
    matches = await matcher.match_predictions(signals, outcomes)

    # Get quality metrics
    metrics = matcher.calculate_match_quality_metrics()

    # Batch process with partial failure handling
    batch_result = await matcher.match_batch_with_partial_failure_handling(
        signals, outcomes
    )
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_storage.models import (
        SignalRecord,
    )

logger = logging.getLogger(__name__)


class MatchStatus(Enum):
    """Status of a prediction-outcome match."""

    MATCHED = "matched"  # Successfully matched with outcome
    UNRESOLVED = "unresolved"  # No outcome yet within window
    EXPIRED = "expired"  # Matching window expired without outcome
    AMBIGUOUS = "ambiguous"  # Multiple possible outcomes found
    ERROR = "error"  # Error during matching process


class MatchConfidence(Enum):
    """Confidence level for a match."""

    HIGH = "high"  # Clear single outcome within expected window (>=95%)
    MEDIUM = "medium"  # Outcome found but timing is borderline (80-95%)
    LOW = "low"  # Multiple outcomes or unclear resolution (<80%)
    UNKNOWN = "unknown"  # No outcome data available


class SignalType(Enum):
    """Type of trading signal for metrics calculation."""

    ENTRY = "entry"
    EXIT = "exit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    UNKNOWN = "unknown"


# Timeframe-specific matching windows (in hours)
# Based on acceptance criteria:
# - 1m: 30 minutes (0.5h)
# - 5m: 2 hours
# - 15m: 6 hours
# - 1h: 24 hours
# - 4h: 72 hours (3 days)
# - 1d: 168 hours (7 days)
DEFAULT_MATCHING_WINDOWS: dict[str, float] = {
    "1m": 0.5,
    "3m": 1.0,
    "5m": 2.0,
    "15m": 6.0,
    "30m": 12.0,
    "1h": 24.0,
    "2h": 36.0,
    "4h": 72.0,  # 3 days
    "6h": 96.0,
    "8h": 120.0,
    "12h": 144.0,
    "1d": 168.0,  # 7 days
    "3d": 336.0,
    "1w": 504.0,
}


@dataclass
class MatchConfig:
    """Configuration for prediction-outcome matching.

    Attributes:
        matching_window_hours: Default time window for matching (hours)
        min_confidence_threshold: Minimum confidence for valid match (0.0-1.0)
        allow_multiple_outcomes: Whether to allow matching multiple outcomes
        token_specific_windows: Per-token matching window overrides
        signal_type_windows: Per-signal-type matching window overrides
        timeframe_windows: Per-timeframe matching window overrides
        enable_partial_failure_handling: Whether to enable graceful partial failure
        max_concurrent_matches: Maximum concurrent matching operations
        batch_size: Number of signals to process in a batch
    """

    matching_window_hours: float = 24.0
    min_confidence_threshold: float = 0.95  # >95% accuracy requirement
    allow_multiple_outcomes: bool = False
    token_specific_windows: dict[str, float] = field(default_factory=dict)
    signal_type_windows: dict[str, float] = field(default_factory=dict)
    timeframe_windows: dict[str, float] = field(default_factory=dict)
    enable_partial_failure_handling: bool = True
    max_concurrent_matches: int = 10
    batch_size: int = 100

    def __post_init__(self) -> None:
        """Merge default timeframe windows with custom windows."""
        merged = DEFAULT_MATCHING_WINDOWS.copy()
        merged.update(self.timeframe_windows)
        self.timeframe_windows = merged

    def get_window_for_signal(self, signal: SignalRecord) -> float:
        """Get matching window for a specific signal.

        Args:
            signal: Signal record to get window for

        Returns:
            Matching window in hours
        """
        # Check signal type specific window
        signal_type = getattr(signal, "signal_type", None)
        if signal_type and signal_type in self.signal_type_windows:
            return self.signal_type_windows[signal_type]

        # Check timeframe specific window
        timeframe = getattr(signal, "timeframe", None)
        if timeframe and timeframe in self.timeframe_windows:
            return self.timeframe_windows[timeframe]

        # Check token specific window
        if hasattr(signal, "token") and signal.token in self.token_specific_windows:
            return self.token_specific_windows[signal.token]

        # Return default
        return self.matching_window_hours

    def get_window_for_timeframe(self, timeframe: str | None) -> float:
        """Get matching window for a specific timeframe.

        Args:
            timeframe: Timeframe string (e.g., "1h", "4h")

        Returns:
            Matching window in hours
        """
        if timeframe and timeframe in self.timeframe_windows:
            return self.timeframe_windows[timeframe]
        return self.matching_window_hours


@dataclass
class PredictionOutcomeMatch:
    """Result of matching a prediction with an outcome.

    Attributes:
        signal_id: Unique signal identifier
        signal: Original signal record
        outcome: Matched outcome record (if any)
        status: Match status
        confidence: Match confidence level
        confidence_score: Numeric confidence score (0.0-1.0)
        match_time_ms: Time when match was made (Unix ms)
        match_latency_hours: Hours between signal and outcome
        resolution_quality: Quality score 0.0-1.0
        signal_type: Type of signal for metrics
        metadata: Additional match metadata
        error: Error message if match failed
    """

    signal_id: str
    signal: SignalRecord
    outcome: Any | None = None  # OutcomeRecord or None
    status: MatchStatus = MatchStatus.UNRESOLVED
    confidence: MatchConfidence = MatchConfidence.UNKNOWN
    confidence_score: float = 0.0
    match_time_ms: int = 0
    match_latency_hours: float = 0.0
    resolution_quality: float = 0.0
    signal_type: SignalType = SignalType.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        outcome_dict = None
        if self.outcome is not None and hasattr(self.outcome, "to_dict"):
            outcome_dict = self.outcome.to_dict()

        return {
            "signal_id": self.signal_id,
            "signal": self.signal.to_dict() if hasattr(self.signal, "to_dict") else {},
            "outcome": outcome_dict,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "confidence_score": round(self.confidence_score, 4),
            "match_time_ms": self.match_time_ms,
            "match_latency_hours": round(self.match_latency_hours, 2),
            "resolution_quality": round(self.resolution_quality, 4),
            "signal_type": self.signal_type.value,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class MatchBatchResult:
    """Results from a batch matching operation.

    Attributes:
        total_signals: Total number of signals processed
        matched: Number of successfully matched signals
        unresolved: Number of unresolved signals
        expired: Number of expired signals
        ambiguous: Number of ambiguous matches
        errors: Number of signals with errors
        matches: List of all match results
        batch_time_ms: Time when batch was processed
        failed_signal_ids: List of signal IDs that failed processing
        partial_failure: Whether partial failure occurred
    """

    total_signals: int = 0
    matched: int = 0
    unresolved: int = 0
    expired: int = 0
    ambiguous: int = 0
    errors: int = 0
    matches: list[PredictionOutcomeMatch] = field(default_factory=list)
    batch_time_ms: int = 0
    failed_signal_ids: list[str] = field(default_factory=list)
    partial_failure: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_signals": self.total_signals,
            "matched": self.matched,
            "unresolved": self.unresolved,
            "expired": self.expired,
            "ambiguous": self.ambiguous,
            "errors": self.errors,
            "matches": [m.to_dict() for m in self.matches],
            "batch_time_ms": self.batch_time_ms,
            "failed_signal_ids": self.failed_signal_ids,
            "partial_failure": self.partial_failure,
        }

    @property
    def match_rate(self) -> float:
        """Calculate match rate (0.0-1.0)."""
        if self.total_signals == 0:
            return 0.0
        return self.matched / self.total_signals

    @property
    def success_rate(self) -> float:
        """Calculate success rate (excluding errors)."""
        if self.total_signals == 0:
            return 0.0
        return (self.total_signals - self.errors) / self.total_signals


@dataclass
class MatchQualityMetrics:
    """Match quality metrics per signal type.

    Attributes:
        signal_type: Type of signal
        true_positives: Correctly matched signals
        false_positives: Incorrectly matched signals
        false_negatives: Missed matches
        precision: Precision score (TP / (TP + FP))
        recall: Recall score (TP / (TP + FN))
        f1_score: F1 score (2 * (precision * recall) / (precision + recall))
        accuracy: Overall accuracy
        total_predictions: Total predictions made
        total_outcomes: Total outcomes available
    """

    signal_type: SignalType
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    accuracy: float = 0.0
    total_predictions: int = 0
    total_outcomes: int = 0

    def calculate(self) -> None:
        """Calculate precision, recall, F1, and accuracy."""
        tp = self.true_positives
        fp = self.false_positives
        fn = self.false_negatives

        # Precision: TP / (TP + FP)
        if tp + fp > 0:
            self.precision = tp / (tp + fp)
        else:
            self.precision = 0.0

        # Recall: TP / (TP + FN)
        if tp + fn > 0:
            self.recall = tp / (tp + fn)
        else:
            self.recall = 0.0

        # F1 Score: 2 * (precision * recall) / (precision + recall)
        if self.precision + self.recall > 0:
            self.f1_score = (
                2 * (self.precision * self.recall) / (self.precision + self.recall)
            )
        else:
            self.f1_score = 0.0

        # Accuracy: TP / total_predictions
        if self.total_predictions > 0:
            self.accuracy = tp / self.total_predictions
        else:
            self.accuracy = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "accuracy": round(self.accuracy, 4),
            "total_predictions": self.total_predictions,
            "total_outcomes": self.total_outcomes,
        }


class PredictionOutcomeMatcher:
    """Matches predictions with outcomes for feedback loop analysis.

    This class provides methods to:
    - Match signals with their outcomes within configurable time windows
    - Handle various outcome types and resolution scenarios
    - Calculate match confidence and quality metrics
    - Support batch matching operations with partial failure handling
    - Calculate precision, recall, F1 per signal type
    - Integrate with outcome capture service from ST-LAUNCH-006
    """

    def __init__(
        self,
        signal_tracker: Any | None = None,
        config: MatchConfig | None = None,
        outcome_capture_service: Any | None = None,
    ):
        """Initialize the matcher.

        Args:
            signal_tracker: SignalTracker instance for signal storage
            config: Matching configuration
            outcome_capture_service: OutcomeCaptureService from ST-LAUNCH-006
        """
        self.signal_tracker = signal_tracker
        self.config = config or MatchConfig()
        self.outcome_capture_service = outcome_capture_service
        self._match_history: list[PredictionOutcomeMatch] = []
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_matches)

        # Metrics tracking per signal type
        self._metrics_by_signal_type: dict[SignalType, MatchQualityMetrics] = {
            signal_type: MatchQualityMetrics(signal_type=signal_type)
            for signal_type in SignalType
        }

    async def match_single(
        self,
        signal: SignalRecord,
        outcomes: list[Any] | None = None,
        current_time_ms: int | None = None,
    ) -> PredictionOutcomeMatch:
        """Match a single signal with its outcome.

        Args:
            signal: Signal to match
            outcomes: Optional list of outcomes to search (uses tracker if None)
            current_time_ms: Current time for window calculation (defaults to now)

        Returns:
            PredictionOutcomeMatch with match result
        """
        if current_time_ms is None:
            current_time_ms = int(datetime.now(UTC).timestamp() * 1000)

        try:
            # Get matching window for this signal
            window_hours = self.config.get_window_for_signal(signal)
            window_ms = int(window_hours * 3600 * 1000)

            # Calculate window boundaries
            signal_time = signal.timestamp
            window_end = signal_time + window_ms

            # If window hasn't expired, mark as unresolved
            if current_time_ms < window_end:
                return PredictionOutcomeMatch(
                    signal_id=signal.signal_id,
                    signal=signal,
                    status=MatchStatus.UNRESOLVED,
                    confidence=MatchConfidence.UNKNOWN,
                    confidence_score=0.0,
                    match_time_ms=current_time_ms,
                    signal_type=self._detect_signal_type(signal),
                    metadata={
                        "window_hours": window_hours,
                        "window_expires_ms": window_end,
                    },
                )

            # Fetch outcomes if not provided
            if outcomes is None:
                outcomes = await self._fetch_outcomes_for_signal(signal)

            if not outcomes:
                # Window expired with no outcomes
                return PredictionOutcomeMatch(
                    signal_id=signal.signal_id,
                    signal=signal,
                    status=MatchStatus.EXPIRED,
                    confidence=MatchConfidence.UNKNOWN,
                    confidence_score=0.0,
                    match_time_ms=current_time_ms,
                    match_latency_hours=window_hours,
                    signal_type=self._detect_signal_type(signal),
                    metadata={
                        "window_hours": window_hours,
                        "reason": "no_outcomes_found",
                    },
                )

            # Filter outcomes within window
            valid_outcomes = [
                o for o in outcomes if signal_time <= o.exit_timestamp <= window_end
            ]

            if not valid_outcomes:
                return PredictionOutcomeMatch(
                    signal_id=signal.signal_id,
                    signal=signal,
                    status=MatchStatus.EXPIRED,
                    confidence=MatchConfidence.UNKNOWN,
                    confidence_score=0.0,
                    match_time_ms=current_time_ms,
                    signal_type=self._detect_signal_type(signal),
                    metadata={
                        "window_hours": window_hours,
                        "reason": "outcomes_outside_window",
                    },
                )

            # Calculate confidence scores for each outcome
            scored_outcomes = []
            for outcome in valid_outcomes:
                confidence_score = self._calculate_match_confidence_score(
                    signal, outcome, window_hours
                )
                scored_outcomes.append((outcome, confidence_score))

            # Sort by confidence score (highest first)
            scored_outcomes.sort(key=lambda x: x[1], reverse=True)

            # Determine best match and status
            best_outcome, best_confidence_score = scored_outcomes[0]

            # Determine confidence level based on score
            if best_confidence_score >= 0.95:
                confidence = MatchConfidence.HIGH
            elif best_confidence_score >= 0.80:
                confidence = MatchConfidence.MEDIUM
            else:
                confidence = MatchConfidence.LOW

            # Handle multiple outcomes
            if len(valid_outcomes) > 1 and not self.config.allow_multiple_outcomes:
                status = MatchStatus.MATCHED
            elif len(valid_outcomes) > 1:
                status = MatchStatus.AMBIGUOUS
            else:
                status = MatchStatus.MATCHED

            # Calculate latency
            latency_ms = best_outcome.exit_timestamp - signal_time
            latency_hours = latency_ms / (3600 * 1000)

            # Calculate resolution quality
            resolution_quality = self._calculate_resolution_quality(
                signal, best_outcome, latency_hours, window_hours
            )

            signal_type = self._detect_signal_type(signal)

            match_result = PredictionOutcomeMatch(
                signal_id=signal.signal_id,
                signal=signal,
                outcome=best_outcome,
                status=status,
                confidence=confidence,
                confidence_score=best_confidence_score,
                match_time_ms=current_time_ms,
                match_latency_hours=latency_hours,
                resolution_quality=resolution_quality,
                signal_type=signal_type,
                metadata={
                    "window_hours": window_hours,
                    "outcomes_considered": len(outcomes),
                    "outcomes_in_window": len(valid_outcomes),
                    "all_confidence_scores": [round(s, 4) for _, s in scored_outcomes],
                },
            )

            self._match_history.append(match_result)
            self._update_metrics(match_result)
            return match_result

        except Exception as e:
            logger.error(f"Error matching signal {signal.signal_id}: {e}")
            return PredictionOutcomeMatch(
                signal_id=signal.signal_id,
                signal=signal,
                status=MatchStatus.ERROR,
                confidence=MatchConfidence.UNKNOWN,
                confidence_score=0.0,
                match_time_ms=current_time_ms
                or int(datetime.now(UTC).timestamp() * 1000),
                signal_type=self._detect_signal_type(signal),
                error=str(e),
            )

    async def match_batch(
        self,
        signals: list[SignalRecord],
        outcomes: dict[str, list[Any]] | None = None,
        current_time_ms: int | None = None,
    ) -> MatchBatchResult:
        """Match multiple signals with their outcomes.

        Args:
            signals: List of signals to match
            outcomes: Optional dict mapping signal_id to outcomes
            current_time_ms: Current time for window calculation

        Returns:
            MatchBatchResult with all match results
        """
        if current_time_ms is None:
            current_time_ms = int(datetime.now(UTC).timestamp() * 1000)

        result = MatchBatchResult(
            total_signals=len(signals),
            batch_time_ms=current_time_ms,
        )

        for signal in signals:
            signal_outcomes = None
            if outcomes and signal.signal_id in outcomes:
                signal_outcomes = outcomes[signal.signal_id]

            match = await self.match_single(signal, signal_outcomes, current_time_ms)

            result.matches.append(match)

            # Update counters
            if match.status == MatchStatus.MATCHED:
                result.matched += 1
            elif match.status == MatchStatus.UNRESOLVED:
                result.unresolved += 1
            elif match.status == MatchStatus.EXPIRED:
                result.expired += 1
            elif match.status == MatchStatus.AMBIGUOUS:
                result.ambiguous += 1
            elif match.status == MatchStatus.ERROR:
                result.errors += 1

        logger.info(
            f"Batch matching complete: {result.matched}/{result.total_signals} matched, "
            f"{result.unresolved} unresolved, {result.expired} expired, "
            f"{result.errors} errors"
        )

        return result

    async def match_batch_with_partial_failure_handling(
        self,
        signals: list[SignalRecord],
        outcomes: dict[str, list[Any]] | None = None,
        current_time_ms: int | None = None,
    ) -> MatchBatchResult:
        """Match multiple signals with graceful partial failure handling.

        This method processes signals in batches and continues processing
        even if individual signals fail to match. Failed signals are tracked
        and reported without stopping the batch.

        Args:
            signals: List of signals to match
            outcomes: Optional dict mapping signal_id to outcomes
            current_time_ms: Current time for window calculation

        Returns:
            MatchBatchResult with all match results including partial failures
        """
        if current_time_ms is None:
            current_time_ms = int(datetime.now(UTC).timestamp() * 1000)

        result = MatchBatchResult(
            total_signals=len(signals),
            batch_time_ms=current_time_ms,
        )

        # Process signals with semaphore for concurrency control
        async def match_with_semaphore(signal: SignalRecord) -> PredictionOutcomeMatch:
            async with self._semaphore:
                signal_outcomes = None
                if outcomes and signal.signal_id in outcomes:
                    signal_outcomes = outcomes[signal.signal_id]
                return await self.match_single(signal, signal_outcomes, current_time_ms)

        # Create tasks for all signals
        tasks = [match_with_semaphore(signal) for signal in signals]

        # Process with return_exceptions=True for partial failure handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for i, match_result in enumerate(results):
            if isinstance(match_result, Exception):
                # Handle exception - log and track
                signal = signals[i]
                logger.error(
                    f"Failed to match signal {signal.signal_id}: {match_result}"
                )
                result.failed_signal_ids.append(signal.signal_id)
                result.errors += 1
                result.partial_failure = True

                # Create error match result
                error_match = PredictionOutcomeMatch(
                    signal_id=signal.signal_id,
                    signal=signal,
                    status=MatchStatus.ERROR,
                    confidence=MatchConfidence.UNKNOWN,
                    confidence_score=0.0,
                    match_time_ms=current_time_ms,
                    signal_type=self._detect_signal_type(signal),
                    error=str(match_result),
                )
                result.matches.append(error_match)
            else:
                # Normal match result
                result.matches.append(match_result)

                # Update counters
                if match_result.status == MatchStatus.MATCHED:
                    result.matched += 1
                elif match_result.status == MatchStatus.UNRESOLVED:
                    result.unresolved += 1
                elif match_result.status == MatchStatus.EXPIRED:
                    result.expired += 1
                elif match_result.status == MatchStatus.AMBIGUOUS:
                    result.ambiguous += 1
                elif match_result.status == MatchStatus.ERROR:
                    result.errors += 1
                    result.failed_signal_ids.append(match_result.signal_id)
                    result.partial_failure = True

        logger.info(
            f"Batch matching with partial failure handling complete: "
            f"{result.matched}/{result.total_signals} matched, "
            f"{result.unresolved} unresolved, {result.expired} expired, "
            f"{result.errors} errors, partial_failure={result.partial_failure}"
        )

        return result

    def calculate_match_quality_metrics(
        self,
        signal_type: SignalType | None = None,
    ) -> dict[SignalType, MatchQualityMetrics] | MatchQualityMetrics:
        """Calculate match quality metrics (precision, recall, F1) per signal type.

        Args:
            signal_type: Optional specific signal type to get metrics for.
                        If None, returns metrics for all signal types.

        Returns:
            MatchQualityMetrics for specific type, or dict of all metrics
        """
        if signal_type:
            metrics = self._metrics_by_signal_type[signal_type]
            metrics.calculate()
            return metrics

        # Calculate and return all metrics
        all_metrics = {}
        for st, metrics in self._metrics_by_signal_type.items():
            metrics.calculate()
            all_metrics[st] = metrics
        return all_metrics

    def get_high_confidence_match_rate(self) -> float:
        """Get the rate of high confidence matches (>=95%).

        Returns:
            Rate of high confidence matches (0.0-1.0)
        """
        if not self._match_history:
            return 0.0

        high_confidence_matches = sum(
            1 for m in self._match_history if m.confidence == MatchConfidence.HIGH
        )
        return high_confidence_matches / len(self._match_history)

    def get_overall_accuracy(self) -> float:
        """Get overall matching accuracy.

        Returns:
            Overall accuracy (0.0-1.0)
        """
        total_tp = sum(m.true_positives for m in self._metrics_by_signal_type.values())
        total_predictions = sum(
            m.total_predictions for m in self._metrics_by_signal_type.values()
        )

        if total_predictions == 0:
            return 0.0
        return total_tp / total_predictions

    async def find_unresolved_signals(
        self,
        token: str | None = None,
        max_age_hours: float = 48.0,
    ) -> list[SignalRecord]:
        """Find signals that need outcome resolution.

        Args:
            token: Optional token filter
            max_age_hours: Maximum age of signals to check

        Returns:
            List of unresolved signals
        """
        if self.signal_tracker is None:
            return []

        # Calculate time range
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        min_time_ms = now_ms - int(max_age_hours * 3600 * 1000)

        # Get signals without outcomes
        signals = await self.signal_tracker.get_signal_history(
            token=token,
            start_time_ms=min_time_ms,
            end_time_ms=now_ms,
            with_outcomes_only=False,
        )

        # Filter to unresolved only
        unresolved = []
        for signal_with_outcome in signals:
            if signal_with_outcome.outcome is None:
                unresolved.append(signal_with_outcome.signal)

        return unresolved

    def _detect_signal_type(self, signal: SignalRecord) -> SignalType:
        """Detect signal type from signal record.

        Args:
            signal: Signal record

        Returns:
            Detected signal type
        """
        signal_type_str = getattr(signal, "signal_type", "").lower()

        if "entry" in signal_type_str or "open" in signal_type_str:
            return SignalType.ENTRY
        elif "exit" in signal_type_str or "close" in signal_type_str:
            return SignalType.EXIT
        elif "sl" in signal_type_str or "stop" in signal_type_str:
            return SignalType.STOP_LOSS
        elif "tp" in signal_type_str or "profit" in signal_type_str:
            return SignalType.TAKE_PROFIT

        return SignalType.UNKNOWN

    def _calculate_match_confidence_score(
        self,
        signal: SignalRecord,
        outcome: Any,
        window_hours: float,
    ) -> float:
        """Calculate match confidence score between signal and outcome.

        Args:
            signal: Signal record
            outcome: Outcome record
            window_hours: Matching window in hours

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.0

        # Symbol match (30% weight)
        signal_symbol = getattr(signal, "token", "").upper()
        outcome_symbol = getattr(outcome, "symbol", "").replace("USDT", "").upper()
        if signal_symbol == outcome_symbol:
            confidence += 0.3

        # Direction match (30% weight)
        signal_direction = getattr(signal, "direction", None)
        if signal_direction:
            direction_value = (
                signal_direction.value.upper()
                if hasattr(signal_direction, "value")
                else str(signal_direction).upper()
            )
            outcome_side = getattr(outcome, "side", "").upper()

            if (direction_value == "LONG" and outcome_side == "BUY") or (
                direction_value == "SHORT" and outcome_side == "SELL"
            ):
                confidence += 0.3

        # Time proximity (40% weight)
        signal_time_ms = getattr(signal, "timestamp", 0)
        outcome_time_ms = getattr(outcome, "exit_timestamp", 0)

        if signal_time_ms and outcome_time_ms:
            time_diff_seconds = abs(outcome_time_ms - signal_time_ms) / 1000
            window_seconds = window_hours * 3600

            # Full weight if within 10% of window, linear decay after
            if time_diff_seconds < window_seconds * 0.1:
                confidence += 0.4
            elif time_diff_seconds < window_seconds:
                time_score = 1.0 - (time_diff_seconds / window_seconds)
                confidence += 0.4 * time_score

        return round(min(confidence, 1.0), 4)

    def _calculate_resolution_quality(
        self,
        signal: SignalRecord,
        outcome: Any,
        latency_hours: float,
        window_hours: float,
    ) -> float:
        """Calculate resolution quality score.

        Args:
            signal: Original signal
            outcome: Resolved outcome
            latency_hours: Hours to resolution
            window_hours: Matching window hours

        Returns:
            Quality score 0.0-1.0
        """
        quality = 1.0

        # Penalize long resolution times
        if window_hours > 0:
            time_ratio = latency_hours / window_hours
            if time_ratio > 0.9:
                quality *= 0.7  # Near window expiration
            elif time_ratio > 0.5:
                quality *= 0.85  # Half window used

        # Boost for clear outcomes (TP/SL hit)
        if hasattr(outcome, "outcome_type"):
            from ml.models.signal_outcome import OutcomeType

            if outcome.outcome_type in (OutcomeType.TP_HIT, OutcomeType.SL_HIT):
                quality = min(1.0, quality * 1.1)

        # Penalize for manual closes (less clear signal)
        if hasattr(outcome, "outcome_type"):
            from ml.models.signal_outcome import OutcomeType

            if outcome.outcome_type == OutcomeType.MANUAL_CLOSE:
                quality *= 0.9

        return round(max(0.0, min(1.0, quality)), 4)

    def _update_metrics(self, match: PredictionOutcomeMatch) -> None:
        """Update quality metrics based on match result.

        Args:
            match: Match result to record
        """
        signal_type = match.signal_type
        metrics = self._metrics_by_signal_type[signal_type]
        metrics.total_predictions += 1

        if match.status == MatchStatus.MATCHED:
            if match.confidence == MatchConfidence.HIGH:
                metrics.true_positives += 1
            else:
                # Medium/Low confidence counts as false positive for quality metrics
                metrics.false_positives += 1
        elif match.status == MatchStatus.EXPIRED:
            metrics.false_negatives += 1
        elif match.status == MatchStatus.ERROR:
            metrics.false_negatives += 1

        if match.outcome:
            metrics.total_outcomes += 1

    async def _fetch_outcomes_for_signal(
        self,
        signal: SignalRecord,
    ) -> list[Any]:
        """Fetch outcomes for a signal from storage or outcome capture service.

        Args:
            signal: Signal to fetch outcomes for

        Returns:
            List of outcomes
        """
        outcomes = []

        # Try signal tracker first
        if self.signal_tracker is not None:
            try:
                signal_with_outcome = await self.signal_tracker.get_signal_with_outcome(
                    signal.signal_id
                )
                if signal_with_outcome and signal_with_outcome.outcome:
                    outcomes.append(signal_with_outcome.outcome)
            except Exception as e:
                logger.warning(f"Failed to fetch outcomes from tracker: {e}")

        # Try outcome capture service if available
        if self.outcome_capture_service is not None and not outcomes:
            try:
                # Query outcomes from outcome capture service
                window_hours = self.config.get_window_for_signal(signal)
                from datetime import timedelta

                window_start = datetime.fromtimestamp(
                    signal.timestamp / 1000, tz=UTC
                ) - timedelta(hours=1)
                window_end = datetime.fromtimestamp(
                    signal.timestamp / 1000, tz=UTC
                ) + timedelta(hours=window_hours)

                # This assumes outcome_capture_service has a method to query outcomes
                # Implementation depends on the service interface
                if hasattr(self.outcome_capture_service, "get_outcomes_for_symbol"):
                    service_outcomes = (
                        await self.outcome_capture_service.get_outcomes_for_symbol(
                            symbol=signal.token,
                            start_time=window_start,
                            end_time=window_end,
                        )
                    )
                    outcomes.extend(service_outcomes)
            except Exception as e:
                logger.warning(f"Failed to fetch outcomes from capture service: {e}")

        return outcomes

    def get_match_history(
        self,
        status: MatchStatus | None = None,
        limit: int = 100,
    ) -> list[PredictionOutcomeMatch]:
        """Get match history with optional filtering.

        Args:
            status: Optional status filter
            limit: Maximum number of results

        Returns:
            List of matches
        """
        matches = self._match_history
        if status:
            matches = [m for m in matches if m.status == status]
        return matches[-limit:]

    def clear_history(self) -> None:
        """Clear match history."""
        self._match_history.clear()
        for metrics in self._metrics_by_signal_type.values():
            metrics.true_positives = 0
            metrics.false_positives = 0
            metrics.false_negatives = 0
            metrics.total_predictions = 0
            metrics.total_outcomes = 0

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of all metrics.

        Returns:
            Dictionary with metrics summary
        """
        all_metrics = self.calculate_match_quality_metrics()

        return {
            "overall_accuracy": round(self.get_overall_accuracy(), 4),
            "high_confidence_match_rate": round(
                self.get_high_confidence_match_rate(), 4
            ),
            "total_matches": len(self._match_history),
            "metrics_by_signal_type": {
                st.value: m.to_dict() for st, m in all_metrics.items()
            },
        }
