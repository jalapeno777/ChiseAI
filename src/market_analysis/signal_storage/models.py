"""Data models for signal storage.

Defines dataclasses for SignalRecord and OutcomeRecord used in signal
history tracking and outcome correlation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class SignalDirection(Enum):
    """Signal direction enumeration."""

    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


class OutcomeType(Enum):
    """Outcome type enumeration for signal resolution."""

    TP_HIT = "tp_hit"  # Take profit hit
    SL_HIT = "sl_hit"  # Stop loss hit
    MANUAL_CLOSE = "manual_close"  # Manually closed
    TIMEOUT = "timeout"  # Expired without resolution
    UNKNOWN = "unknown"  # Unknown/untracked outcome

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass
class SignalRecord:
    """Stored signal for historical tracking.

    Attributes:
        signal_id: UUID v4 for unique identification
        token: Trading pair token (e.g., "BTC", "ETH")
        timestamp: Unix timestamp in milliseconds
        direction: Signal direction (LONG/SHORT/NEUTRAL)
        confidence: Confidence level (0.0-1.0)
        entry_price: Entry price at signal time
        score: Confluence score (0-100)
        multiplier_applied: Confidence multiplier that was applied (if any)
        indicators_used: List of indicator types used (e.g., ["rsi", "macd"])
        timeframes_used: List of timeframes used (e.g., ["1h", "4h"])
        metadata: Additional metadata for the signal
    """

    signal_id: str
    token: str
    timestamp: int
    direction: SignalDirection
    confidence: float
    entry_price: float
    score: float
    multiplier_applied: float | None = None
    indicators_used: list[str] = field(default_factory=list)
    timeframes_used: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        # Normalize confidence to 0-1 range
        self.confidence = max(0.0, min(1.0, self.confidence))
        # Normalize score to 0-100 range
        self.score = max(0.0, min(100.0, self.score))

    @property
    def confidence_bucket(self) -> str:
        """Get confidence bucket for grouping (0-10, 10-20, etc.).

        Returns:
            String bucket identifier (e.g., "70-80" for 70-80% confidence)
        """
        confidence_pct = int(self.confidence * 100)
        lower = (confidence_pct // 10) * 10
        upper = lower + 10
        return f"{lower}-{upper}"

    @property
    def signal_type(self) -> str:
        """Get signal type identifier (direction + indicator combination).

        Returns:
            String like "LONG_rsi_macd" or "SHORT_bb"
        """
        indicators_str = (
            "_".join(sorted(self.indicators_used)) if self.indicators_used else "none"
        )
        return f"{self.direction.value}_{indicators_str}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the signal record
        """
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "timestamp": self.timestamp,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 4),
            "entry_price": self.entry_price,
            "score": round(self.score, 2),
            "multiplier_applied": self.multiplier_applied,
            "indicators_used": self.indicators_used,
            "timeframes_used": self.timeframes_used,
            "confidence_bucket": self.confidence_bucket,
            "signal_type": self.signal_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignalRecord:
        """Create SignalRecord from dictionary.

        Args:
            data: Dictionary with signal data

        Returns:
            SignalRecord instance
        """
        direction = SignalDirection(data.get("direction", "NEUTRAL"))
        return cls(
            signal_id=data["signal_id"],
            token=data["token"],
            timestamp=data["timestamp"],
            direction=direction,
            confidence=data.get("confidence", 0.0),
            entry_price=data.get("entry_price", 0.0),
            score=data.get("score", 0.0),
            multiplier_applied=data.get("multiplier_applied"),
            indicators_used=data.get("indicators_used", []),
            timeframes_used=data.get("timeframes_used", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class OutcomeRecord:
    """Recorded outcome for a signal.

    Attributes:
        signal_id: Reference to the SignalRecord that generated this outcome
        exit_timestamp: Unix timestamp in milliseconds when position closed
        is_win: True if the outcome was profitable
        pnl: Profit/loss amount (positive for profit, negative for loss)
        exit_price: Exit price when position closed
        duration_hours: Duration of the trade in hours
        outcome_type: Type of outcome (tp_hit, sl_hit, manual_close, timeout)
        note: Optional notes about the outcome
    """

    signal_id: str
    exit_timestamp: int
    is_win: bool
    pnl: float
    exit_price: float
    duration_hours: float
    outcome_type: OutcomeType = OutcomeType.UNKNOWN
    note: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        # Ensure is_win matches pnl sign (with small tolerance for fees)
        if self.pnl > 0.001 and not self.is_win:
            self.is_win = True
        elif self.pnl < -0.001 and self.is_win:
            self.is_win = False

        # Ensure outcome_type is an enum
        if isinstance(self.outcome_type, str):
            try:
                self.outcome_type = OutcomeType(self.outcome_type)
            except ValueError:
                self.outcome_type = OutcomeType.UNKNOWN

    @property
    def pnl_pct(self) -> float:
        """Calculate PnL percentage relative to entry.

        Note: This requires the entry price which is stored in the
        corresponding SignalRecord. This property returns 0.0 as
        the entry price is not available in OutcomeRecord.

        Returns:
            0.0 (entry price not available in this record)
        """
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the outcome record
        """
        return {
            "signal_id": self.signal_id,
            "exit_timestamp": self.exit_timestamp,
            "is_win": self.is_win,
            "pnl": round(self.pnl, 8),
            "exit_price": self.exit_price,
            "duration_hours": round(self.duration_hours, 2),
            "outcome_type": self.outcome_type.value,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutcomeRecord:
        """Create OutcomeRecord from dictionary.

        Args:
            data: Dictionary with outcome data

        Returns:
            OutcomeRecord instance
        """
        outcome_type_str = data.get("outcome_type", "unknown")
        try:
            outcome_type = OutcomeType(outcome_type_str)
        except ValueError:
            outcome_type = OutcomeType.UNKNOWN

        return cls(
            signal_id=data["signal_id"],
            exit_timestamp=data["exit_timestamp"],
            is_win=data.get("is_win", False),
            pnl=data.get("pnl", 0.0),
            exit_price=data.get("exit_price", 0.0),
            duration_hours=data.get("duration_hours", 0.0),
            outcome_type=outcome_type,
            note=data.get("note"),
        )


@dataclass
class SignalWithOutcome:
    """Combined signal and its outcome for analysis.

    This dataclass pairs a SignalRecord with its corresponding
    OutcomeRecord for accuracy calculations and reporting.
    """

    signal: SignalRecord
    outcome: OutcomeRecord | None = None

    @property
    def is_resolved(self) -> bool:
        """Check if the signal has been resolved with an outcome."""
        return self.outcome is not None

    @property
    def is_win(self) -> bool | None:
        """Get win status if resolved, None otherwise."""
        if self.outcome is None:
            return None
        return self.outcome.is_win

    @property
    def pnl(self) -> float | None:
        """Get PnL if resolved, None otherwise."""
        if self.outcome is None:
            return None
        return self.outcome.pnl

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal": self.signal.to_dict(),
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "is_resolved": self.is_resolved,
            "is_win": self.is_win,
            "pnl": self.pnl,
        }
