"""Stop-loss hit tracking for outcome correlation.

Tracks when stop-losses are hit and correlates with signal outcomes
to improve stop-loss calculation accuracy over time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


class StopLossOutcome(Enum):
    """Outcome type when a stop-loss is triggered."""

    HIT = "hit"  # Stop-loss was hit
    MISSED = "missed"  # Price never reached stop-loss
    ADJUSTED = "adjusted"  # Stop-loss was manually adjusted
    EXPIRED = "expired"  # Signal expired before stop was hit


class SignalResult(Enum):
    """Final result of a signal after monitoring."""

    WIN = "win"  # Target hit before stop
    LOSS = "loss"  # Stop hit before target
    TIMEOUT = "timeout"  # Neither hit within timeframe
    MANUAL_CLOSE = "manual_close"  # Manually closed


@dataclass
class StopLossHitEvent:
    """Record of a stop-loss being hit.

    Attributes:
        signal_id: Unique signal identifier
        token: Trading pair
        direction: Signal direction
        entry_price: Price at signal generation
        stop_loss_price: Stop-loss price level
        hit_price: Actual price when stop was hit
        hit_timestamp: When the stop was hit
        outcome: Type of outcome
        price_action: Price movement description
        metadata: Additional tracking data
    """

    signal_id: str
    token: str
    direction: str
    entry_price: float
    stop_loss_price: float
    hit_price: float
    hit_timestamp: datetime
    outcome: StopLossOutcome
    price_action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 2),
            "stop_loss_price": round(self.stop_loss_price, 2),
            "hit_price": round(self.hit_price, 2),
            "hit_timestamp": self.hit_timestamp.isoformat(),
            "outcome": self.outcome.value,
            "price_action": self.price_action,
            "metadata": self.metadata,
        }


@dataclass
class SignalOutcome:
    """Complete outcome record for a signal.

    Attributes:
        signal_id: Unique signal identifier
        token: Trading pair
        direction: Signal direction
        entry_price: Entry price
        exit_price: Exit price (if closed)
        stop_loss: Original stop-loss price
        target_price: Target price (if set)
        result: Final result (win/loss/timeout)
        pnl_percent: Profit/loss as percentage
        duration_hours: Time from entry to exit
        stop_hit: Whether stop-loss was hit
        metadata: Additional outcome data
    """

    signal_id: str
    token: str
    direction: str
    entry_price: float
    exit_price: float | None
    stop_loss: float
    target_price: float | None
    result: SignalResult
    pnl_percent: float
    duration_hours: float
    stop_hit: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 2),
            "exit_price": round(self.exit_price, 2) if self.exit_price else None,
            "stop_loss": round(self.stop_loss, 2),
            "target_price": round(self.target_price, 2) if self.target_price else None,
            "result": self.result.value,
            "pnl_percent": round(self.pnl_percent, 4),
            "duration_hours": round(self.duration_hours, 2),
            "stop_hit": self.stop_hit,
            "metadata": self.metadata,
        }


@dataclass
class StopLossCorrelationStats:
    """Statistics for stop-loss outcome correlation.

    Attributes:
        total_signals: Total number of signals tracked
        stop_hits: Number of times stop-loss was hit
        wins_before_stop: Number of wins before stop was hit
        avg_stop_distance_pct: Average stop distance as percentage
        avg_time_to_hit_hours: Average time until stop was hit
        correlation_by_method: Stats broken down by stop method
        correlation_by_confidence: Stats by confidence bucket
    """

    total_signals: int = 0
    stop_hits: int = 0
    wins_before_stop: int = 0
    avg_stop_distance_pct: float = 0.0
    avg_time_to_hit_hours: float = 0.0
    correlation_by_method: dict[str, dict[str, Any]] = field(default_factory=dict)
    correlation_by_confidence: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_signals": self.total_signals,
            "stop_hits": self.stop_hits,
            "wins_before_stop": self.wins_before_stop,
            "avg_stop_distance_pct": round(self.avg_stop_distance_pct, 4),
            "avg_time_to_hit_hours": round(self.avg_time_to_hit_hours, 2),
            "stop_hit_rate": (
                round(self.stop_hits / self.total_signals, 4)
                if self.total_signals > 0
                else 0.0
            ),
            "correlation_by_method": self.correlation_by_method,
            "correlation_by_confidence": self.correlation_by_confidence,
        }


class StopLossTracker:
    """Tracks stop-loss hits and correlates with signal outcomes.

    Provides analytics on stop-loss effectiveness to improve
    stop-loss calculation over time.

    Example:
        tracker = StopLossTracker()

        # Record a signal with stop-loss
        tracker.record_signal(signal, entry_price=50000)

        # Later, when stop is hit
        tracker.record_stop_hit(
            signal_id="uuid",
            hit_price=49000,
            outcome=StopLossOutcome.HIT
        )

        # Get correlation stats
        stats = tracker.get_correlation_stats()
    """

    def __init__(self):
        """Initialize stop-loss tracker."""
        self._signals: dict[str, dict[str, Any]] = {}  # signal_id -> signal data
        self._stop_hits: list[StopLossHitEvent] = []
        self._outcomes: list[SignalOutcome] = []

    def record_signal(
        self,
        signal: Signal,
        entry_price: float,
        target_price: float | None = None,
    ) -> None:
        """Record a signal for tracking.

        Args:
            signal: The generated signal
            entry_price: Entry price for the trade
            target_price: Optional target price
        """
        self._signals[signal.signal_id] = {
            "signal": signal,
            "entry_price": entry_price,
            "target_price": target_price,
            "recorded_at": datetime.now(UTC),
            "stop_loss": signal.stop_loss,
            "stop_loss_method": signal.stop_loss_method,
        }

        logger.debug(f"Recorded signal {signal.signal_id} for stop-loss tracking")

    def record_stop_hit(
        self,
        signal_id: str,
        hit_price: float,
        outcome: StopLossOutcome,
        price_action: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StopLossHitEvent | None:
        """Record that a stop-loss was hit.

        Args:
            signal_id: Signal identifier
            hit_price: Price when stop was hit
            outcome: Type of outcome
            price_action: Description of price action
            metadata: Additional tracking data

        Returns:
            StopLossHitEvent if signal was tracked, None otherwise
        """
        if signal_id not in self._signals:
            logger.warning(f"Signal {signal_id} not found for stop-hit recording")
            return None

        signal_data = self._signals[signal_id]
        signal = signal_data["signal"]

        event = StopLossHitEvent(
            signal_id=signal_id,
            token=signal.token,
            direction=signal.direction.value,
            entry_price=signal_data["entry_price"],
            stop_loss_price=signal_data["stop_loss"] or 0.0,
            hit_price=hit_price,
            hit_timestamp=datetime.now(UTC),
            outcome=outcome,
            price_action=price_action,
            metadata=metadata or {},
        )

        self._stop_hits.append(event)

        logger.info(
            f"Stop-loss hit recorded for {signal.token}: "
            f"{hit_price:.2f} (outcome: {outcome.value})"
        )

        return event

    def record_outcome(
        self,
        signal_id: str,
        exit_price: float | None,
        result: SignalResult,
        pnl_percent: float,
        duration_hours: float,
        metadata: dict[str, Any] | None = None,
    ) -> SignalOutcome | None:
        """Record the final outcome of a signal.

        Args:
            signal_id: Signal identifier
            exit_price: Exit price (None if still open)
            result: Final result
            pnl_percent: Profit/loss percentage
            duration_hours: Duration in hours
            metadata: Additional outcome data

        Returns:
            SignalOutcome if signal was tracked, None otherwise
        """
        if signal_id not in self._signals:
            logger.warning(f"Signal {signal_id} not found for outcome recording")
            return None

        signal_data = self._signals[signal_id]
        signal = signal_data["signal"]

        # Determine if stop was hit
        stop_hit = result == SignalResult.LOSS

        outcome = SignalOutcome(
            signal_id=signal_id,
            token=signal.token,
            direction=signal.direction.value,
            entry_price=signal_data["entry_price"],
            exit_price=exit_price,
            stop_loss=signal_data["stop_loss"] or 0.0,
            target_price=signal_data["target_price"],
            result=result,
            pnl_percent=pnl_percent,
            duration_hours=duration_hours,
            stop_hit=stop_hit,
            metadata=metadata or {},
        )

        self._outcomes.append(outcome)

        logger.info(
            f"Outcome recorded for {signal.token}: "
            f"{result.value} (PnL: {pnl_percent:.2%})"
        )

        return outcome

    def check_stop_hit(
        self,
        signal_id: str,
        current_price: float,
    ) -> bool:
        """Check if stop-loss would be hit at current price.

        Args:
            signal_id: Signal identifier
            current_price: Current market price

        Returns:
            True if stop-loss is hit, False otherwise
        """
        if signal_id not in self._signals:
            return False

        signal_data = self._signals[signal_id]
        stop_loss = signal_data.get("stop_loss")
        signal = signal_data["signal"]

        if stop_loss is None:
            return False

        # Check based on direction
        if signal.direction.value == "long":
            return current_price <= stop_loss
        else:  # short
            return current_price >= stop_loss

    def get_correlation_stats(self) -> StopLossCorrelationStats:
        """Calculate correlation statistics.

        Returns:
            StopLossCorrelationStats with aggregated data
        """
        stats = StopLossCorrelationStats()

        if not self._outcomes:
            return stats

        stats.total_signals = len(self._outcomes)
        stats.stop_hits = sum(1 for o in self._outcomes if o.stop_hit)
        stats.wins_before_stop = sum(
            1 for o in self._outcomes if o.result == SignalResult.WIN and not o.stop_hit
        )

        # Calculate average stop distance
        distances = []
        for outcome in self._outcomes:
            if outcome.stop_loss > 0:
                distance = abs(outcome.stop_loss - outcome.entry_price)
                distances.append(distance / outcome.entry_price)

        if distances:
            stats.avg_stop_distance_pct = sum(distances) / len(distances)

        # Calculate average time to hit
        hit_durations = [o.duration_hours for o in self._outcomes if o.stop_hit]
        if hit_durations:
            stats.avg_time_to_hit_hours = sum(hit_durations) / len(hit_durations)

        # Break down by stop-loss method
        method_stats: dict[str, dict[str, Any]] = {}
        for outcome in self._outcomes:
            signal_data = self._signals.get(outcome.signal_id, {})
            method = signal_data.get("stop_loss_method", "unknown")

            if method not in method_stats:
                method_stats[method] = {
                    "total": 0,
                    "stop_hits": 0,
                    "wins": 0,
                    "avg_pnl": 0.0,
                }

            method_stats[method]["total"] += 1
            if outcome.stop_hit:
                method_stats[method]["stop_hits"] += 1
            if outcome.result == SignalResult.WIN:
                method_stats[method]["wins"] += 1

        # Calculate averages for methods
        for method in method_stats:
            total = method_stats[method]["total"]
            if total > 0:
                method_stats[method]["stop_hit_rate"] = (
                    method_stats[method]["stop_hits"] / total
                )
                method_stats[method]["win_rate"] = method_stats[method]["wins"] / total

        stats.correlation_by_method = method_stats

        # Break down by confidence bucket
        confidence_buckets = {
            "75-80%": [],
            "80-85%": [],
            "85-90%": [],
            "90-95%": [],
            "95-100%": [],
        }

        for outcome in self._outcomes:
            signal_data = self._signals.get(outcome.signal_id, {})
            signal = signal_data.get("signal")
            if signal:
                confidence_pct = signal.confidence * 100
                if 75 <= confidence_pct < 80:
                    confidence_buckets["75-80%"].append(outcome)
                elif 80 <= confidence_pct < 85:
                    confidence_buckets["80-85%"].append(outcome)
                elif 85 <= confidence_pct < 90:
                    confidence_buckets["85-90%"].append(outcome)
                elif 90 <= confidence_pct < 95:
                    confidence_buckets["90-95%"].append(outcome)
                elif confidence_pct >= 95:
                    confidence_buckets["95-100%"].append(outcome)

        for bucket, outcomes in confidence_buckets.items():
            if outcomes:
                total = len(outcomes)
                stop_hits = sum(1 for o in outcomes if o.stop_hit)
                wins = sum(1 for o in outcomes if o.result == SignalResult.WIN)

                stats.correlation_by_confidence[bucket] = {
                    "total": total,
                    "stop_hits": stop_hits,
                    "stop_hit_rate": stop_hits / total,
                    "wins": wins,
                    "win_rate": wins / total,
                }

        return stats

    def get_signal_history(self, signal_id: str) -> dict[str, Any] | None:
        """Get complete history for a signal.

        Args:
            signal_id: Signal identifier

        Returns:
            Dictionary with signal data, stop hits, and outcome
        """
        if signal_id not in self._signals:
            return None

        signal_data = self._signals[signal_id]

        # Find related stop hit
        stop_hit = next(
            (sh for sh in self._stop_hits if sh.signal_id == signal_id), None
        )

        # Find related outcome
        outcome = next((o for o in self._outcomes if o.signal_id == signal_id), None)

        return {
            "signal": signal_data["signal"].to_dict(),
            "entry_price": signal_data["entry_price"],
            "target_price": signal_data.get("target_price"),
            "stop_hit": stop_hit.to_dict() if stop_hit else None,
            "outcome": outcome.to_dict() if outcome else None,
        }

    def clear_old_records(self, max_age_hours: float = 168) -> int:
        """Clear records older than specified age.

        Args:
            max_age_hours: Maximum age in hours (default: 1 week)

        Returns:
            Number of records cleared
        """
        cutoff = datetime.now(UTC).timestamp() - (max_age_hours * 3600)
        cleared = 0

        # Clear old signals
        old_signals = [
            sid
            for sid, data in self._signals.items()
            if data["recorded_at"].timestamp() < cutoff
        ]
        for sid in old_signals:
            del self._signals[sid]
            cleared += 1

        # Clear old stop hits
        old_hits = [
            i
            for i, hit in enumerate(self._stop_hits)
            if hit.hit_timestamp.timestamp() < cutoff
        ]
        for i in reversed(old_hits):
            del self._stop_hits[i]
            cleared += 1

        logger.info(f"Cleared {cleared} old stop-loss tracking records")
        return cleared
