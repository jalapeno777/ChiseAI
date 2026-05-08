"""Signal Tracker for ICT Experiment Data Collection.

Tracks individual trading signals for the ICT hypothesis experiment.
Distinguishes between:
- Control group: Signals WITHOUT ICT confluence scoring (baseline)
- Treatment group: Signals WITH ICT confluence scoring (ICT-enhanced)

Supports signal types: CVD, FVG, Order Block, BOS, CHoCH

Redis Schema:
- signal:{signal_id} - Hash with signal data
- experiment:signals:{group} - List of signal IDs for each group
- experiment:outcomes:{signal_id} - Hash with outcome data
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import redis

# Redis key prefixes
SIGNAL_KEY_PREFIX = "experiment:signal:"
CONTROL_SIGNALS_KEY = "experiment:signals:control"
TREATMENT_SIGNALS_KEY = "experiment:signals:treatment"
OUTCOME_KEY_PREFIX = "experiment:outcome:"
EXPERIMENT_META_KEY = "experiment:meta"


class SignalGroup(Enum):
    """Signal group classification."""

    CONTROL = "control"
    TREATMENT = "treatment"


class SignalType(Enum):
    """Supported ICT signal types."""

    CVD = "cvd"
    FVG = "fvg"
    ORDER_BLOCK = "order_block"
    BOS_CHOCH = "bos_choch"
    BOS = "bos"
    CHOCH = "choch"

    @classmethod
    def is_valid(cls, signal_type: str) -> bool:
        """Check if signal type is valid."""
        try:
            cls(signal_type.lower())
            return True
        except ValueError:
            return False

    @classmethod
    def excluded_types(cls) -> list[str]:
        """Return list of excluded signal types (currently none)."""
        return []


@dataclass
class TrackedSignal:
    """A tracked trading signal with metadata.

    Attributes:
        signal_id: Unique identifier for the signal
        timestamp: Unix timestamp when signal was generated
        signal_type: Type of signal (cvd, fvg, order_block)
        group: Control or treatment group
        direction: Trading direction (bullish/bearish)
        entry_price: Entry price for the trade
        confluence_score: ICT confluence score (0.0-1.0), None for control
        stop_loss: Stop loss price
        take_profit: Take profit price
        metadata: Additional signal metadata
    """

    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: int = field(default_factory=lambda: int(time.time()))
    signal_type: str = ""
    group: SignalGroup = SignalGroup.CONTROL
    direction: str = "bullish"
    entry_price: float = 0.0
    confluence_score: float | None = None
    stop_loss: float = 0.0
    take_profit: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_redis_hash(self) -> dict[str, str]:
        """Convert to Redis hash-compatible dict."""
        return {
            "signal_id": self.signal_id,
            "timestamp": str(self.timestamp),
            "signal_type": self.signal_type,
            "group": self.group.value,
            "direction": self.direction,
            "entry_price": str(self.entry_price),
            "confluence_score": (
                str(self.confluence_score) if self.confluence_score is not None else ""
            ),
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "metadata": str(self.metadata),
        }

    @classmethod
    def from_redis_hash(cls, data: dict[str, str]) -> TrackedSignal:
        """Create instance from Redis hash data."""
        return cls(
            signal_id=data["signal_id"],
            timestamp=int(data["timestamp"]),
            signal_type=data["signal_type"],
            group=SignalGroup(data["group"]),
            direction=data["direction"],
            entry_price=float(data["entry_price"]),
            confluence_score=(
                float(data["confluence_score"])
                if data.get("confluence_score")
                else None
            ),
            stop_loss=float(data["stop_loss"]),
            take_profit=float(data["take_profit"]),
            metadata=eval(data["metadata"]) if data.get("metadata") else {},
        )


@dataclass
class SignalOutcome:
    """Outcome data for a tracked signal.

    Attributes:
        signal_id: Reference to the signal
        timestamp: When outcome was recorded
        pnl: Profit/loss as a ratio (e.g., 0.05 = 5% gain)
        outcome: Trade outcome (win/loss/breakeven)
        exit_price: Price at which trade was closed
        holding_period: Time in seconds the position was held
        metadata: Additional outcome metadata
    """

    signal_id: str
    timestamp: int = field(default_factory=lambda: int(time.time()))
    pnl: float = 0.0
    outcome: str = "pending"
    exit_price: float = 0.0
    holding_period: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_redis_hash(self) -> dict[str, str]:
        """Convert to Redis hash-compatible dict."""
        return {
            "signal_id": self.signal_id,
            "timestamp": str(self.timestamp),
            "pnl": str(self.pnl),
            "outcome": self.outcome,
            "exit_price": str(self.exit_price),
            "holding_period": str(self.holding_period),
            "metadata": str(self.metadata),
        }

    @classmethod
    def from_redis_hash(cls, data: dict[str, str]) -> SignalOutcome:
        """Create instance from Redis hash data."""
        return cls(
            signal_id=data["signal_id"],
            timestamp=int(data["timestamp"]),
            pnl=float(data["pnl"]),
            outcome=data["outcome"],
            exit_price=float(data["exit_price"]),
            holding_period=int(data["holding_period"]),
            metadata=eval(data["metadata"]) if data.get("metadata") else {},
        )


class SignalTracker:
    """Tracks signals and outcomes for ICT hypothesis experiment.

    Uses Redis for real-time storage with the following schema:
    - experiment:signal:{id} - Signal data as hash
    - experiment:signals:control - List of control signal IDs
    - experiment:signals:treatment - List of treatment signal IDs
    - experiment:outcome:{id} - Outcome data as hash
    - experiment:meta - Experiment metadata

    Usage:
        tracker = SignalTracker(redis_client)

        # Track a new signal
        signal = tracker.track_signal(
            signal_type="cvd",
            group=SignalGroup.TREATMENT,
            confluence_score=0.75,
            entry_price=1.1000,
            direction="bullish"
        )

        # Record outcome
        tracker.record_outcome(
            signal_id=signal.signal_id,
            pnl=0.023,
            outcome="win",
            exit_price=1.1230
        )

        # Get experiment statistics
        stats = tracker.get_experiment_stats()
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        """Initialize signal tracker.

        Args:
            redis_client: Redis client instance for storage
        """
        self._redis = redis_client

    def track_signal(
        self,
        signal_type: str,
        group: SignalGroup,
        entry_price: float,
        direction: str = "bullish",
        confluence_score: float | None = None,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        metadata: dict[str, Any] | None = None,
        signal_id: str | None = None,
        timestamp: int | None = None,
    ) -> TrackedSignal:
        """Track a new signal.

        Args:
            signal_type: Type of signal (cvd, fvg, order_block)
            group: Control or treatment group
            entry_price: Entry price for the trade
            direction: Trading direction (bullish/bearish)
            confluence_score: ICT confluence score (None for control)
            stop_loss: Stop loss price
            take_profit: Take profit price
            metadata: Additional metadata
            signal_id: Optional custom signal ID
            timestamp: Optional custom timestamp

        Returns:
            TrackedSignal instance

        Raises:
            ValueError: If signal type is invalid
        """
        # Validate signal type
        if not SignalType.is_valid(signal_type):
            raise ValueError(f"Invalid signal type: {signal_type}")

        # Create signal
        signal = TrackedSignal(
            signal_id=signal_id or str(uuid.uuid4()),
            timestamp=timestamp or int(time.time()),
            signal_type=signal_type.lower(),
            group=group,
            direction=direction.lower(),
            entry_price=entry_price,
            confluence_score=(
                confluence_score if group == SignalGroup.TREATMENT else None
            ),
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata or {},
        )

        # Store in Redis
        signal_key = f"{SIGNAL_KEY_PREFIX}{signal.signal_id}"
        self._redis.hset(signal_key, mapping=signal.to_redis_hash())

        # Add to group list
        group_key = (
            CONTROL_SIGNALS_KEY
            if group == SignalGroup.CONTROL
            else TREATMENT_SIGNALS_KEY
        )
        self._redis.rpush(group_key, signal.signal_id)

        return signal

    def record_outcome(
        self,
        signal_id: str,
        pnl: float,
        outcome: str,
        exit_price: float,
        holding_period: int = 0,
        metadata: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> SignalOutcome:
        """Record outcome for a tracked signal.

        Args:
            signal_id: ID of the signal
            pnl: Profit/loss as ratio
            outcome: Trade outcome (win/loss/breakeven/pending)
            exit_price: Price at which trade was closed
            holding_period: Time in seconds position was held
            metadata: Additional metadata
            timestamp: Optional custom timestamp

        Returns:
            SignalOutcome instance
        """
        outcome_obj = SignalOutcome(
            signal_id=signal_id,
            timestamp=timestamp or int(time.time()),
            pnl=pnl,
            outcome=outcome,
            exit_price=exit_price,
            holding_period=holding_period,
            metadata=metadata or {},
        )

        outcome_key = f"{OUTCOME_KEY_PREFIX}{signal_id}"
        self._redis.hset(outcome_key, mapping=outcome_obj.to_redis_hash())

        return outcome_obj

    def get_signal(self, signal_id: str) -> TrackedSignal | None:
        """Retrieve a tracked signal.

        Args:
            signal_id: ID of the signal

        Returns:
            TrackedSignal or None if not found
        """
        signal_key = f"{SIGNAL_KEY_PREFIX}{signal_id}"
        data = self._redis.hgetall(signal_key)
        if not data:
            return None
        return TrackedSignal.from_redis_hash(data)

    def get_outcome(self, signal_id: str) -> SignalOutcome | None:
        """Retrieve outcome for a signal.

        Args:
            signal_id: ID of the signal

        Returns:
            SignalOutcome or None if not found
        """
        outcome_key = f"{OUTCOME_KEY_PREFIX}{signal_id}"
        data = self._redis.hgetall(outcome_key)
        if not data:
            return None
        return SignalOutcome.from_redis_hash(data)

    def get_signals_by_group(
        self, group: SignalGroup, limit: int = 100, offset: int = 0
    ) -> list[TrackedSignal]:
        """Get signals for a specific group.

        Args:
            group: Control or treatment
            limit: Maximum number of signals to return
            offset: Number of signals to skip

        Returns:
            List of TrackedSignal instances
        """
        group_key = (
            CONTROL_SIGNALS_KEY
            if group == SignalGroup.CONTROL
            else TREATMENT_SIGNALS_KEY
        )
        signal_ids = self._redis.lrange(group_key, offset, offset + limit - 1)

        signals = []
        for sid in signal_ids:
            signal = self.get_signal(sid.decode() if isinstance(sid, bytes) else sid)
            if signal:
                signals.append(signal)
        return signals

    def get_signal_count(self, group: SignalGroup) -> int:
        """Get count of signals in a group.

        Args:
            group: Control or treatment

        Returns:
            Number of signals in the group
        """
        group_key = (
            CONTROL_SIGNALS_KEY
            if group == SignalGroup.CONTROL
            else TREATMENT_SIGNALS_KEY
        )
        return self._redis.llen(group_key)

    def get_experiment_stats(self) -> dict[str, Any]:
        """Get overall experiment statistics.

        Returns:
            Dictionary with experiment stats
        """
        control_count = self.get_signal_count(SignalGroup.CONTROL)
        treatment_count = self.get_signal_count(SignalGroup.TREATMENT)

        # Calculate outcome stats for each group
        control_outcomes = self._get_group_outcomes(SignalGroup.CONTROL)
        treatment_outcomes = self._get_group_outcomes(SignalGroup.TREATMENT)

        return {
            "control_signals": control_count,
            "treatment_signals": treatment_count,
            "total_signals": control_count + treatment_count,
            "control_win_rate": self._calculate_win_rate(control_outcomes),
            "treatment_win_rate": self._calculate_win_rate(treatment_outcomes),
            "control_avg_pnl": self._calculate_avg_pnl(control_outcomes),
            "treatment_avg_pnl": self._calculate_avg_pnl(treatment_outcomes),
        }

    def _get_group_outcomes(self, group: SignalGroup) -> list[SignalOutcome]:
        """Get all outcomes for a group."""
        signals = self.get_signals_by_group(group, limit=10000)
        outcomes = []
        for signal in signals:
            outcome = self.get_outcome(signal.signal_id)
            if outcome:
                outcomes.append(outcome)
        return outcomes

    def _calculate_win_rate(self, outcomes: list[SignalOutcome]) -> float:
        """Calculate win rate from outcomes."""
        if not outcomes:
            return 0.0
        wins = sum(1 for o in outcomes if o.outcome == "win")
        return wins / len(outcomes)

    def _calculate_avg_pnl(self, outcomes: list[SignalOutcome]) -> float:
        """Calculate average PnL from outcomes."""
        if not outcomes:
            return 0.0
        return sum(o.pnl for o in outcomes) / len(outcomes)

    def clear_experiment_data(self) -> None:
        """Clear all experiment data from Redis.

        WARNING: This deletes all signal and outcome data.
        Use with caution.
        """
        # Clear control signals
        control_ids = self._redis.lrange(CONTROL_SIGNALS_KEY, 0, -1)
        for sid in control_ids:
            sid_str = sid.decode() if isinstance(sid, bytes) else sid
            self._redis.delete(f"{SIGNAL_KEY_PREFIX}{sid_str}")
            self._redis.delete(f"{OUTCOME_KEY_PREFIX}{sid_str}")
        self._redis.delete(CONTROL_SIGNALS_KEY)

        # Clear treatment signals
        treatment_ids = self._redis.lrange(TREATMENT_SIGNALS_KEY, 0, -1)
        for sid in treatment_ids:
            sid_str = sid.decode() if isinstance(sid, bytes) else sid
            self._redis.delete(f"{SIGNAL_KEY_PREFIX}{sid_str}")
            self._redis.delete(f"{OUTCOME_KEY_PREFIX}{sid_str}")
        self._redis.delete(TREATMENT_SIGNALS_KEY)

        # Clear metadata
        self._redis.delete(EXPERIMENT_META_KEY)
