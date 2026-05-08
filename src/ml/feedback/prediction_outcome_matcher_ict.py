"""Prediction-Outcome Matcher for ICT Signals.

This module provides functionality to match ICT signal predictions
with actual trade outcomes for performance analysis.

Features:
- Match ICT signal predictions with actual outcomes
- Calculate accuracy per signal type (CVD, FVG, Order Block)
- Track ECE (Expected Calibration Error) for ICT signals
- Exclude BOS/CHoCH signals per BL-BOS-CHOCH-001

Usage:
    from ml.feedback.prediction_outcome_matcher_ict import (
        ICTPredictionOutcomeMatcher,
        ICTMatchConfig,
        ICTSignalMetrics,
    )

    matcher = ICTPredictionOutcomeMatcher()
    result = await matcher.match_signal_with_outcome(signal, outcome)
    metrics = matcher.get_ict_metrics()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from signal_generation.registry.signal_types import ICTSignalType

if TYPE_CHECKING:
    from ml.feedback.ict_signal_tracker import ICTSignalRecord

logger = logging.getLogger(__name__)


class ICTMatchStatus(Enum):
    """Status of an ICT prediction-outcome match."""

    MATCHED = "matched"
    UNRESOLVED = "unresolved"
    EXPIRED = "expired"
    EXCLUDED = "excluded"  # BOS/CHoCH was filtered


class ICTMatchConfidence(Enum):
    """Confidence level for an ICT match."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class ICTMatchConfig:
    """Configuration for ICT prediction-outcome matching.

    Attributes:
        matching_window_hours: Time window for matching (hours)
        min_confidence_threshold: Minimum confidence for valid match
        enable_ece_tracking: Whether to track ECE metrics
    """

    matching_window_hours: float = 24.0
    min_confidence_threshold: float = 0.5
    enable_ece_tracking: bool = True


@dataclass
class ICTPredictionMatch:
    """Result of matching an ICT prediction with an outcome.

    Attributes:
        signal_id: Unique signal identifier
        signal_type: ICT signal type (CVD, FVG, Order Block)
        direction: Signal direction
        predicted_direction: Direction that was predicted
        actual_direction: Actual direction from outcome
        confidence: Signal confidence
        outcome_correct: Whether prediction was correct
        match_status: Status of the match
        match_confidence: Confidence level
        timestamp: When the signal was generated
        outcome_timestamp: When the outcome occurred
        latency_hours: Hours between signal and outcome
    """

    signal_id: str
    signal_type: ICTSignalType
    direction: str  # "bullish" or "bearish"
    predicted_direction: str
    actual_direction: str | None = None
    confidence: float = 0.0
    outcome_correct: bool | None = None
    match_status: ICTMatchStatus = ICTMatchStatus.UNRESOLVED
    match_confidence: ICTMatchConfidence = ICTMatchConfidence.UNKNOWN
    timestamp: datetime = field(default_factory=datetime.utcnow)
    outcome_timestamp: datetime | None = None
    latency_hours: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure timestamp is timezone-aware."""
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)
        if self.outcome_timestamp and self.outcome_timestamp.tzinfo is None:
            self.outcome_timestamp = self.outcome_timestamp.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
            "direction": self.direction,
            "predicted_direction": self.predicted_direction,
            "actual_direction": self.actual_direction,
            "confidence": round(self.confidence, 4),
            "outcome_correct": self.outcome_correct,
            "match_status": self.match_status.value,
            "match_confidence": self.match_confidence.value,
            "timestamp": self.timestamp.isoformat(),
            "outcome_timestamp": (
                self.outcome_timestamp.isoformat() if self.outcome_timestamp else None
            ),
            "latency_hours": round(self.latency_hours, 2),
            "metadata": self.metadata,
        }


@dataclass
class ICTSignalMetrics:
    """Metrics for an ICT signal type.

    Attributes:
        signal_type: ICT signal type
        total_signals: Total predictions made
        correct_predictions: Correct predictions
        incorrect_predictions: Incorrect predictions
        accuracy: Accuracy ratio (0.0-1.0)
        avg_confidence: Average signal confidence
        ece: Expected Calibration Error
        calibration_buckets: Calibration bucket counts
    """

    signal_type: ICTSignalType
    total_signals: int = 0
    correct_predictions: int = 0
    incorrect_predictions: int = 0
    accuracy: float = 0.0
    avg_confidence: float = 0.0
    ece: float = 0.0
    calibration_buckets: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        if self.total_signals > 0:
            self.accuracy = self.correct_predictions / self.total_signals

    def calculate_ece(self) -> float:
        """Calculate Expected Calibration Error.

        ECE measures the difference between confidence and accuracy
        across calibration buckets.

        Returns:
            ECE score (lower is better, 0.0 is perfect calibration)
        """
        if self.total_signals == 0:
            return 0.0

        # Note: calibration bucket calculation would be implemented here
        # For now, return the stored ECE
        return self.ece

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "total_signals": self.total_signals,
            "correct_predictions": self.correct_predictions,
            "incorrect_predictions": self.incorrect_predictions,
            "accuracy": round(self.accuracy, 4),
            "avg_confidence": round(self.avg_confidence, 4),
            "ece": round(self.ece, 4),
            "calibration_buckets": self.calibration_buckets,
        }


class ICTPredictionOutcomeMatcher:
    """Matches ICT signal predictions with outcomes.

    This class provides methods to:
    - Match ICT signals (CVD, FVG, Order Block) with trade outcomes
    - Calculate accuracy per signal type
    - Track ECE for calibration analysis
    - Exclude BOS/CHoCH signals per BL-BOS-CHOCH-001

    Attributes:
        VALID_SIGNAL_TYPES: ICT signal types that can be matched (excludes BOS/CHoCH)
    """

    VALID_SIGNAL_TYPES: list[ICTSignalType] = [
        ICTSignalType.CVD,
        ICTSignalType.FVG,
        ICTSignalType.ORDER_BLOCK,
    ]

    def __init__(self, config: ICTMatchConfig | None = None) -> None:
        """Initialize the ICT matcher.

        Args:
            config: Matching configuration
        """
        self.config = config or ICTMatchConfig()
        self._matches: list[ICTPredictionMatch] = []
        self._metrics_by_type: dict[ICTSignalType, ICTSignalMetrics] = {
            signal_type: ICTSignalMetrics(signal_type=signal_type)
            for signal_type in self.VALID_SIGNAL_TYPES
        }

    def is_bos_choch(self, signal_type: ICTSignalType) -> bool:
        """Check if a signal type is BOS/CHoCH.

        Args:
            signal_type: Signal type to check

        Returns:
            True if BOS/CHoCH, False otherwise
        """
        # BOS/CHOCH re-enabled — no longer excluded
        return False

    async def match_signal_with_outcome(
        self,
        signal: ICTSignalRecord,
        outcome: Any,
        current_time_ms: int | None = None,
    ) -> ICTPredictionMatch | None:
        """Match a single ICT signal with an outcome.

        Args:
            signal: ICT signal record to match
            outcome: Trade outcome
            current_time_ms: Current time in milliseconds

        Returns:
            ICTPredictionMatch if matched, None if invalid
        """
        if current_time_ms is None:
            current_time_ms = int(datetime.now(UTC).timestamp() * 1000)

        # Validate signal type
        if signal.signal_type not in self.VALID_SIGNAL_TYPES:
            logger.warning(
                f"Invalid ICT signal type for matching: {signal.signal_type.value}"
            )
            return None

        # Calculate latency
        outcome_timestamp = getattr(outcome, "exit_time", None) or getattr(
            outcome, "timestamp", datetime.now(UTC)
        )
        if hasattr(outcome_timestamp, "timestamp"):
            outcome_ms = int(outcome_timestamp.timestamp() * 1000)
        else:
            outcome_ms = current_time_ms

        signal_ms = int(signal.timestamp.timestamp() * 1000) * 1000
        latency_ms = outcome_ms - signal_ms
        latency_hours = latency_ms / (3600 * 1000)

        # Determine if prediction was correct
        outcome_correct = self._evaluate_outcome(signal, outcome)

        # Determine match confidence
        match_confidence = self._determine_confidence(signal.confidence, latency_hours)

        match_result = ICTPredictionMatch(
            signal_id=signal.signal_id,
            signal_type=signal.signal_type,
            direction=signal.direction.value,
            predicted_direction=signal.direction.value,
            actual_direction=getattr(outcome, "direction", None),
            confidence=signal.confidence,
            outcome_correct=outcome_correct,
            match_status=ICTMatchStatus.MATCHED,
            match_confidence=match_confidence,
            timestamp=signal.timestamp,
            outcome_timestamp=outcome_timestamp,
            latency_hours=latency_hours,
        )

        self._matches.append(match_result)
        self._update_metrics(match_result)

        logger.debug(
            f"Matched ICT signal: {signal.signal_id}, "
            f"type={signal.signal_type.value}, correct={outcome_correct}"
        )

        return match_result

    async def match_batch(
        self,
        signals: list[ICTSignalRecord],
        outcomes: list[Any],
    ) -> list[ICTPredictionMatch]:
        """Match multiple ICT signals with outcomes.

        Args:
            signals: List of ICT signals to match
            outcomes: List of outcomes to match against

        Returns:
            List of match results
        """
        results = []

        for signal in signals:
            # Find matching outcome
            matching_outcome = self._find_matching_outcome(signal, outcomes)
            if matching_outcome:
                match = await self.match_signal_with_outcome(signal, matching_outcome)
                if match:
                    results.append(match)
            else:
                # No matching outcome found
                match = ICTPredictionMatch(
                    signal_id=signal.signal_id,
                    signal_type=signal.signal_type,
                    direction=signal.direction.value,
                    predicted_direction=signal.direction.value,
                    match_status=ICTMatchStatus.UNRESOLVED,
                    match_confidence=ICTMatchConfidence.UNKNOWN,
                    timestamp=signal.timestamp,
                )
                results.append(match)

        return results

    def _evaluate_outcome(self, signal: ICTSignalRecord, outcome: Any) -> bool | None:
        """Evaluate if the prediction was correct.

        Args:
            signal: ICT signal record
            outcome: Trade outcome

        Returns:
            True if correct, False if incorrect, None if unknown
        """
        # Check if outcome has PnL
        if hasattr(outcome, "pnl") and outcome.pnl is not None:
            return outcome.pnl > 0

        # Check outcome type
        if hasattr(outcome, "outcome_type"):
            outcome_type_str = outcome.outcome_type.value.lower()
            if "tp" in outcome_type_str or "win" in outcome_type_str:
                return True
            elif "sl" in outcome_type_str or "loss" in outcome_type_str:
                return False

        # Check direction match
        if hasattr(outcome, "direction") and hasattr(signal, "direction"):
            # Outcome direction matches signal direction
            return outcome.direction.upper() == signal.direction.value.upper()

        return None

    def _find_matching_outcome(
        self, signal: ICTSignalRecord, outcomes: list[Any]
    ) -> Any | None:
        """Find matching outcome for a signal.

        Args:
            signal: ICT signal to find outcome for
            outcomes: List of potential outcomes

        Returns:
            Matching outcome or None
        """
        for outcome in outcomes:
            # Match by token
            outcome_token = getattr(outcome, "token", "") or getattr(
                outcome, "symbol", ""
            )
            signal_token = signal.token

            # Simple token matching (handle USDT suffix)
            if signal_token.replace("USDT", "") in outcome_token.replace("USDT", ""):
                return outcome

        return None

    def _determine_confidence(
        self, signal_confidence: float, latency_hours: float
    ) -> ICTMatchConfidence:
        """Determine match confidence level.

        Args:
            signal_confidence: Original signal confidence
            latency_hours: Time to outcome in hours

        Returns:
            Match confidence level
        """
        # Check if within matching window
        if latency_hours > self.config.matching_window_hours:
            return ICTMatchConfidence.LOW

        # High confidence if high signal confidence and short latency
        if signal_confidence >= 0.8 and latency_hours < 12:
            return ICTMatchConfidence.HIGH
        elif signal_confidence >= 0.6:
            return ICTMatchConfidence.MEDIUM
        else:
            return ICTMatchConfidence.LOW

    def _update_metrics(self, match: ICTPredictionMatch) -> None:
        """Update metrics for a match.

        Args:
            match: Match result to record
        """
        signal_type = match.signal_type
        metrics = self._metrics_by_type.get(signal_type)
        if not metrics:
            return

        metrics.total_signals += 1

        if match.outcome_correct is True:
            metrics.correct_predictions += 1
        elif match.outcome_correct is False:
            metrics.incorrect_predictions += 1

        # Update calibration buckets
        confidence_bucket = self._get_confidence_bucket(match.confidence)
        metrics.calibration_buckets[confidence_bucket] = (
            metrics.calibration_buckets.get(confidence_bucket, 0) + 1
        )

        # Update average confidence
        total = metrics.total_signals
        old_avg = metrics.avg_confidence
        metrics.avg_confidence = ((old_avg * (total - 1)) + match.confidence) / total

    def _get_confidence_bucket(self, confidence: float) -> str:
        """Get calibration bucket for a confidence value.

        Args:
            confidence: Confidence value (0.0-1.0)

        Returns:
            Bucket name
        """
        if confidence < 0.1:
            return "0.0-0.1"
        elif confidence < 0.2:
            return "0.1-0.2"
        elif confidence < 0.3:
            return "0.2-0.3"
        elif confidence < 0.4:
            return "0.3-0.4"
        elif confidence < 0.5:
            return "0.4-0.5"
        elif confidence < 0.6:
            return "0.5-0.6"
        elif confidence < 0.7:
            return "0.6-0.7"
        elif confidence < 0.8:
            return "0.7-0.8"
        elif confidence < 0.9:
            return "0.8-0.9"
        else:
            return "0.9-1.0"

    def get_ict_metrics(
        self, signal_type: ICTSignalType | None = None
    ) -> dict[ICTSignalType, ICTSignalMetrics] | ICTSignalMetrics:
        """Get ICT metrics.

        Args:
            signal_type: Optional specific signal type

        Returns:
            Metrics for specific type or all types
        """
        if signal_type:
            return self._metrics_by_type[signal_type]

        return self._metrics_by_type

    def get_overall_accuracy(self) -> float:
        """Get overall accuracy across all ICT signals.

        Returns:
            Overall accuracy (0.0-1.0)
        """
        total_correct = sum(
            m.correct_predictions for m in self._metrics_by_type.values()
        )
        total_signals = sum(m.total_signals for m in self._metrics_by_type.values())

        if total_signals == 0:
            return 0.0

        return total_correct / total_signals

    def get_matches(
        self,
        signal_type: ICTSignalType | None = None,
        limit: int = 100,
    ) -> list[ICTPredictionMatch]:
        """Get match history.

        Args:
            signal_type: Optional signal type filter
            limit: Maximum number of results

        Returns:
            List of matches
        """
        matches = self._matches
        if signal_type:
            matches = [m for m in matches if m.signal_type == signal_type]
        return matches[-limit:]

    def to_dict(self) -> dict[str, Any]:
        """Convert matcher state to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "total_matches": len(self._matches),
            "overall_accuracy": round(self.get_overall_accuracy(), 4),
            "metrics_by_type": {
                st.value: m.to_dict() for st, m in self._metrics_by_type.items()
            },
        }


# Global matcher instance
_matcher: ICTPredictionOutcomeMatcher | None = None


def get_ict_matcher() -> ICTPredictionOutcomeMatcher:
    """Get or create global ICT matcher instance.

    Returns:
        The global ICT matcher
    """
    global _matcher
    if _matcher is None:
        _matcher = ICTPredictionOutcomeMatcher()
    return _matcher
