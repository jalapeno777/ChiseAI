"""Prediction-Outcome Matcher for ML Feedback Loop.

This module provides functionality to match predictions from signal history
with actual outcomes for performance analysis and model improvement.

Features:
- Match predictions with outcomes using time-window based matching
- Handle multiple outcome types (TP hit, SL hit, manual close, timeout)
- Track match confidence and resolution status
- Support configurable matching windows per signal type

Usage:
    from ml.feedback.matcher import PredictionOutcomeMatcher, MatchConfig

    config = MatchConfig(matching_window_hours=24.0)
    matcher = PredictionOutcomeMatcher(signal_tracker, config)
    matches = await matcher.match_predictions(signals, outcomes)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_storage.models import (
        OutcomeRecord,
        SignalRecord,
        SignalWithOutcome,
    )

logger = logging.getLogger(__name__)


class MatchStatus(Enum):
    """Status of a prediction-outcome match."""

    MATCHED = "matched"  # Successfully matched with outcome
    UNRESOLVED = "unresolved"  # No outcome yet within window
    EXPIRED = "expired"  # Matching window expired without outcome
    AMBIGUOUS = "ambiguous"  # Multiple possible outcomes found


class MatchConfidence(Enum):
    """Confidence level for a match."""

    HIGH = "high"  # Clear single outcome within expected window
    MEDIUM = "medium"  # Outcome found but timing is borderline
    LOW = "low"  # Multiple outcomes or unclear resolution
    UNKNOWN = "unknown"  # No outcome data available


@dataclass
class MatchConfig:
    """Configuration for prediction-outcome matching.

    Attributes:
        matching_window_hours: Default time window for matching (hours)
        min_confidence_threshold: Minimum confidence for valid match
        allow_multiple_outcomes: Whether to allow matching multiple outcomes
        token_specific_windows: Per-token matching window overrides
        signal_type_windows: Per-signal-type matching window overrides
    """

    matching_window_hours: float = 24.0
    min_confidence_threshold: float = 0.5
    allow_multiple_outcomes: bool = False
    token_specific_windows: dict[str, float] = field(default_factory=dict)
    signal_type_windows: dict[str, float] = field(default_factory=dict)

    def get_window_for_signal(self, signal: SignalRecord) -> float:
        """Get matching window for a specific signal.

        Args:
            signal: Signal record to get window for

        Returns:
            Matching window in hours
        """
        # Check signal type specific window
        signal_type = signal.signal_type
        if signal_type in self.signal_type_windows:
            return self.signal_type_windows[signal_type]

        # Check token specific window
        if signal.token in self.token_specific_windows:
            return self.token_specific_windows[signal.token]

        # Return default
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
        match_time_ms: Time when match was made (Unix ms)
        match_latency_hours: Hours between signal and outcome
        resolution_quality: Quality score 0.0-1.0
        metadata: Additional match metadata
    """

    signal_id: str
    signal: SignalRecord
    outcome: Any | None = None  # OutcomeRecord or None
    status: MatchStatus = MatchStatus.UNRESOLVED
    confidence: MatchConfidence = MatchConfidence.UNKNOWN
    match_time_ms: int = 0
    match_latency_hours: float = 0.0
    resolution_quality: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

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
            "match_time_ms": self.match_time_ms,
            "match_latency_hours": round(self.match_latency_hours, 2),
            "resolution_quality": round(self.resolution_quality, 4),
            "metadata": self.metadata,
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
        matches: List of all match results
        batch_time_ms: Time when batch was processed
    """

    total_signals: int = 0
    matched: int = 0
    unresolved: int = 0
    expired: int = 0
    ambiguous: int = 0
    matches: list[PredictionOutcomeMatch] = field(default_factory=list)
    batch_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_signals": self.total_signals,
            "matched": self.matched,
            "unresolved": self.unresolved,
            "expired": self.expired,
            "ambiguous": self.ambiguous,
            "matches": [m.to_dict() for m in self.matches],
            "batch_time_ms": self.batch_time_ms,
        }


class PredictionOutcomeMatcher:
    """Matches predictions with outcomes for feedback loop analysis.

    This class provides methods to:
    - Match signals with their outcomes within configurable time windows
    - Handle various outcome types and resolution scenarios
    - Calculate match confidence and quality metrics
    - Support batch matching operations
    """

    def __init__(
        self,
        signal_tracker: Any | None = None,
        config: MatchConfig | None = None,
    ):
        """Initialize the matcher.

        Args:
            signal_tracker: SignalTracker instance for signal storage
            config: Matching configuration
        """
        self.signal_tracker = signal_tracker
        self.config = config or MatchConfig()
        self._match_history: list[PredictionOutcomeMatch] = []

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
            current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

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
                match_time_ms=current_time_ms,
                metadata={
                    "window_hours": window_hours,
                    "window_expires_ms": window_end,
                },
            )

        # Fetch outcomes if not provided
        if outcomes is None and self.signal_tracker is not None:
            outcomes = await self._fetch_outcomes_for_signal(signal)

        if not outcomes:
            # Window expired with no outcomes
            return PredictionOutcomeMatch(
                signal_id=signal.signal_id,
                signal=signal,
                status=MatchStatus.EXPIRED,
                confidence=MatchConfidence.UNKNOWN,
                match_time_ms=current_time_ms,
                match_latency_hours=window_hours,
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
                match_time_ms=current_time_ms,
                metadata={
                    "window_hours": window_hours,
                    "reason": "outcomes_outside_window",
                },
            )

        # Handle multiple outcomes
        if len(valid_outcomes) > 1 and not self.config.allow_multiple_outcomes:
            # Select the earliest outcome
            best_outcome = min(valid_outcomes, key=lambda o: o.exit_timestamp)
            status = MatchStatus.MATCHED
            confidence = MatchConfidence.LOW
        elif len(valid_outcomes) > 1:
            best_outcome = min(valid_outcomes, key=lambda o: o.exit_timestamp)
            status = MatchStatus.AMBIGUOUS
            confidence = MatchConfidence.LOW
        else:
            best_outcome = valid_outcomes[0]
            status = MatchStatus.MATCHED
            confidence = MatchConfidence.HIGH

        # Calculate latency
        latency_ms = best_outcome.exit_timestamp - signal_time
        latency_hours = latency_ms / (3600 * 1000)

        # Calculate resolution quality
        resolution_quality = self._calculate_resolution_quality(
            signal, best_outcome, latency_hours, window_hours
        )

        match_result = PredictionOutcomeMatch(
            signal_id=signal.signal_id,
            signal=signal,
            outcome=best_outcome,
            status=status,
            confidence=confidence,
            match_time_ms=current_time_ms,
            match_latency_hours=latency_hours,
            resolution_quality=resolution_quality,
            metadata={
                "window_hours": window_hours,
                "outcomes_considered": len(outcomes),
                "outcomes_in_window": len(valid_outcomes),
            },
        )

        self._match_history.append(match_result)
        return match_result

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
            current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

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

        logger.info(
            f"Batch matching complete: {result.matched}/{result.total_signals} matched, "
            f"{result.unresolved} unresolved, {result.expired} expired"
        )

        return result

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
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
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
            from market_analysis.signal_storage.models import OutcomeType

            if outcome.outcome_type in (OutcomeType.TP_HIT, OutcomeType.SL_HIT):
                quality = min(1.0, quality * 1.1)

        # Penalize for manual closes (less clear signal)
        if hasattr(outcome, "outcome_type"):
            from market_analysis.signal_storage.models import OutcomeType

            if outcome.outcome_type == OutcomeType.MANUAL_CLOSE:
                quality *= 0.9

        return round(max(0.0, min(1.0, quality)), 4)

    async def _fetch_outcomes_for_signal(
        self,
        signal: SignalRecord,
    ) -> list[Any]:
        """Fetch outcomes for a signal from storage.

        Args:
            signal: Signal to fetch outcomes for

        Returns:
            List of outcomes
        """
        if self.signal_tracker is None:
            return []

        try:
            # Get signal with outcome from tracker
            signal_with_outcome = await self.signal_tracker.get_signal_with_outcome(
                signal.signal_id
            )
            if signal_with_outcome and signal_with_outcome.outcome:
                return [signal_with_outcome.outcome]
        except Exception as e:
            logger.warning(f"Failed to fetch outcomes for {signal.signal_id}: {e}")

        return []

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
