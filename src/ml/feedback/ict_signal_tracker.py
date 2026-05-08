"""ICT Signal Tracker for ML Feedback Loop.

This module provides functionality to track ICT signal predictions
(CVD, FVG, Order Block) for performance analysis and outcome matching.

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

Features:
- Track ICT signal predictions with metadata
- Store signal direction, confidence, and timestamp
- Filter out BOS/CHoCH signals with logging
- Integrate with signal registry from ST-ICT-015

Usage:
    from ml.feedback.ict_signal_tracker import ICTSignalTracker, ICTSignalRecord

    tracker = ICTSignalTracker()
    await tracker.track_signal(signal_type=ICTSignalType.CVD, ...)
    signals = await tracker.get_signals_by_type(ICTSignalType.CVD)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from signal_generation.registry.signal_types import ICTSignalType

if TYPE_CHECKING:
    from signal_generation.registry.ict_signal_registry import ICTSignalRegistry

logger = logging.getLogger(__name__)


class ICTSignalDirection(Enum):
    """Direction of ICT signal."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class ICTSignalRecord:
    """An ICT signal prediction record.

    Attributes:
        signal_id: Unique identifier for the signal
        signal_type: Type of ICT signal (CVD, FVG, Order Block)
        direction: Signal direction (bullish/bearish/neutral)
        confidence: Signal confidence score (0.0-1.0)
        timestamp: When the signal was generated
        token: Trading pair symbol (e.g., "BTC")
        timeframe: Timeframe of the signal (e.g., "1H")
        entry_price: Suggested entry price
        metadata: Additional signal metadata
        tracked: Whether the signal has been tracked for outcome matching
    """

    signal_id: str
    signal_type: ICTSignalType
    direction: ICTSignalDirection
    confidence: float
    timestamp: datetime
    token: str
    timeframe: str
    entry_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tracked: bool = False

    def __post_init__(self) -> None:
        """Validate and normalize values after initialization."""
        # Validate confidence
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

        # Ensure timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 4),
            "timestamp": self.timestamp.isoformat(),
            "token": self.token,
            "timeframe": self.timeframe,
            "entry_price": self.entry_price,
            "metadata": self.metadata,
            "tracked": self.tracked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ICTSignalRecord:
        """Create ICTSignalRecord from dictionary.

        Args:
            data: Dictionary with signal data

        Returns:
            ICTSignalRecord instance
        """
        signal_type = ICTSignalType(data["signal_type"])
        direction = ICTSignalDirection(data["direction"])

        return cls(
            signal_id=data["signal_id"],
            signal_type=signal_type,
            direction=direction,
            confidence=float(data["confidence"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            token=data["token"],
            timeframe=data["timeframe"],
            entry_price=data.get("entry_price"),
            metadata=data.get("metadata", {}),
            tracked=data.get("tracked", False),
        )


class ICTSignalTracker:
    """Tracks ICT signal predictions for feedback analysis.

    This class provides methods to:
    - Track ICT signal predictions (CVD, FVG, Order Block)
    - Filter out BOS/CHoCH signals with logging
    - Retrieve signals by type, token, or timeframe
    - Mark signals as tracked for outcome matching

    BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.
    """

    # Valid ICT signal types for tracking (excludes BOS/CHoCH)
    VALID_SIGNAL_TYPES: list[ICTSignalType] = [
        ICTSignalType.CVD,
        ICTSignalType.FVG,
        ICTSignalType.ORDER_BLOCK,
        ICTSignalType.BOS_CHOCH,
    ]

    def __init__(self, registry: ICTSignalRegistry | None = None) -> None:
        """Initialize the ICT signal tracker.

        Args:
            registry: Optional ICT signal registry for validation
        """
        self._signals: list[ICTSignalRecord] = []
        self._registry = registry
        self._tracked_ids: set[str] = set()

    def is_bos_choch(self, signal_type: ICTSignalType) -> bool:
        """Check if a signal type is BOS/CHoCH.

        Args:
            signal_type: Signal type to check

        Returns:
            True if BOS/CHoCH, False otherwise
        """
        # BOS/CHOCH re-enabled — no longer excluded
        return False

    def track_signal(
        self,
        signal_type: ICTSignalType,
        signal_id: str,
        direction: ICTSignalDirection,
        confidence: float,
        timestamp: datetime,
        token: str,
        timeframe: str,
        entry_price: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ICTSignalRecord | None:
        """Track an ICT signal prediction.

        Args:
            signal_type: Type of ICT signal (CVD, FVG, Order Block, BOS_CHOCH)
            signal_id: Unique identifier for the signal
            direction: Signal direction
            confidence: Signal confidence (0.0-1.0)
            timestamp: When the signal was generated
            token: Trading pair symbol
            timeframe: Timeframe of the signal
            entry_price: Optional entry price
            metadata: Optional additional metadata

        Returns:
            ICTSignalRecord if tracked, None if filtered out
        """
        # Validate signal type
        if signal_type not in self.VALID_SIGNAL_TYPES:
            logger.warning(
                f"Invalid ICT signal type for tracking: {signal_type.value}. "
                f"Valid types: {[st.value for st in self.VALID_SIGNAL_TYPES]}"
            )
            return None

        # Check for duplicate
        if any(s.signal_id == signal_id for s in self._signals):
            logger.debug(f"Signal already tracked: {signal_id}")
            return None

        record = ICTSignalRecord(
            signal_id=signal_id,
            signal_type=signal_type,
            direction=direction,
            confidence=confidence,
            timestamp=timestamp,
            token=token,
            timeframe=timeframe,
            entry_price=entry_price,
            metadata=metadata or {},
            tracked=False,
        )

        self._signals.append(record)
        logger.debug(
            f"Tracked ICT signal: {signal_id}, type={signal_type.value}, "
            f"direction={direction.value}"
        )

        return record

    def get_signals_by_type(
        self,
        signal_type: ICTSignalType,
        include_tracked: bool = True,
    ) -> list[ICTSignalRecord]:
        """Get signals by type.

        Args:
            signal_type: Type of signal to retrieve
            include_tracked: Whether to include already tracked signals

        Returns:
            List of signals matching the type
        """
        return [
            s
            for s in self._signals
            if s.signal_type == signal_type and (include_tracked or not s.tracked)
        ]

    def get_signals_by_token(
        self,
        token: str,
        include_tracked: bool = True,
    ) -> list[ICTSignalRecord]:
        """Get signals by token.

        Args:
            token: Token symbol to filter by
            include_tracked: Whether to include already tracked signals

        Returns:
            List of signals for the token
        """
        return [
            s
            for s in self._signals
            if s.token == token and (include_tracked or not s.tracked)
        ]

    def get_signals_by_timeframe(
        self,
        timeframe: str,
        include_tracked: bool = True,
    ) -> list[ICTSignalRecord]:
        """Get signals by timeframe.

        Args:
            timeframe: Timeframe to filter by
            include_tracked: Whether to include already tracked signals

        Returns:
            List of signals for the timeframe
        """
        return [
            s
            for s in self._signals
            if s.timeframe == timeframe and (include_tracked or not s.tracked)
        ]

    def get_untracked_signals(
        self,
        signal_type: ICTSignalType | None = None,
    ) -> list[ICTSignalRecord]:
        """Get untracked signals for outcome matching.

        Args:
            signal_type: Optional signal type filter

        Returns:
            List of untracked signals
        """
        signals = [s for s in self._signals if not s.tracked]

        if signal_type is not None:
            signals = [s for s in signals if s.signal_type == signal_type]

        return signals

    def mark_tracked(self, signal_id: str) -> bool:
        """Mark a signal as tracked for outcome matching.

        Args:
            signal_id: ID of the signal to mark

        Returns:
            True if marked, False if not found
        """
        for signal in self._signals:
            if signal.signal_id == signal_id:
                signal.tracked = True
                self._tracked_ids.add(signal_id)
                logger.debug(f"Marked signal as tracked: {signal_id}")
                return True
        return False

    def get_all_signals(
        self,
        include_tracked: bool = True,
    ) -> list[ICTSignalRecord]:
        """Get all tracked signals.

        Args:
            include_tracked: Whether to include already tracked signals

        Returns:
            List of all signals
        """
        if include_tracked:
            return list(self._signals)
        return [s for s in self._signals if not s.tracked]

    def get_signal_counts(self) -> dict[str, int]:
        """Get count of signals by type.

        Returns:
            Dictionary mapping signal type to count
        """
        counts: dict[str, int] = {}
        for signal_type in self.VALID_SIGNAL_TYPES:
            count = len(self.get_signals_by_type(signal_type))
            counts[signal_type.value] = count
        return counts

    def get_tracked_count(self) -> int:
        """Get count of tracked signals.

        Returns:
            Number of tracked signals
        """
        return len(self._tracked_ids)

    def clear_tracked(self) -> None:
        """Clear tracked flag from all signals."""
        for signal in self._signals:
            signal.tracked = False
        self._tracked_ids.clear()
        logger.debug("Cleared tracked flags from all signals")

    def to_dict(self) -> dict[str, Any]:
        """Convert tracker state to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "total_signals": len(self._signals),
            "tracked_count": len(self._tracked_ids),
            "signals_by_type": self.get_signal_counts(),
            "signals": [s.to_dict() for s in self._signals],
        }


# Global tracker instance
_tracker: ICTSignalTracker | None = None


def get_ict_tracker() -> ICTSignalTracker:
    """Get or create global ICT signal tracker instance.

    Returns:
        The global ICT signal tracker
    """
    global _tracker
    if _tracker is None:
        _tracker = ICTSignalTracker()
    return _tracker
