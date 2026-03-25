"""
Mitigation Tracker for Fair Value Gaps.

Tracks wick and close mitigation events for FVGs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class MitigationType(str, Enum):
    """Type of mitigation event."""

    WICK = "wick"  # Wick-only mitigation
    CLOSE = "close"  # Close mitigation (price closed within FVG)
    FULL = "full"  # FVG fully filled
    CE50 = "ce50"  # 50% Consequent Encroachment reached


@dataclass
class MitigationEvent:
    """
    Record of a mitigation event on an FVG.

    Attributes:
        timestamp: When the mitigation occurred
        price: Price at which mitigation occurred
        mitigation_type: Type of mitigation
        fvg_high: FVG upper boundary at time of mitigation
        fvg_low: FVG lower boundary at time of mitigation
        notes: Optional notes
    """

    timestamp: int  # Unix timestamp in milliseconds
    price: float
    mitigation_type: MitigationType
    fvg_high: float
    fvg_low: float
    notes: str | None = None


@dataclass
class MitigationStatus:
    """
    Current mitigation status of an FVG.

    Attributes:
        fvg: The FVG being tracked
        mitigation_type: Current mitigation status
        ce50_reached: Whether 50% CE has been reached
        events: History of mitigation events
        is_mitigated: Whether FVG is fully mitigated
    """

    fvg_high: float
    fvg_low: float
    current_mitigation: MitigationType = MitigationType.WICK
    ce50_reached: bool = False
    ce50_price: float | None = None
    events: list[MitigationEvent] = field(default_factory=list)

    @property
    def is_mitigated(self) -> bool:
        """Check if FVG is fully mitigated."""
        return self.current_mitigation == MitigationType.FULL

    @property
    def zone_size(self) -> float:
        """Calculate the size of the FVG zone."""
        return self.fvg_high - self.fvg_low

    @property
    def midpoint(self) -> float:
        """Calculate midpoint of the FVG zone."""
        return (self.fvg_high + self.fvg_low) / 2


class MitigationTracker:
    """
    Tracks mitigation events for Fair Value Gaps.

    Monitors price action to detect:
    - Wick mitigations (price enters via wick only)
    - Close mitigations (price closes within FVG)
    - 50% CE (Consequent Encroachment)

    Usage:
        tracker = MitigationTracker()
        status = tracker.check_mitigation(fvg, current_candle)
    """

    def __init__(self):
        """Initialize mitigation tracker."""
        self._tracked_fvgs: dict[str, MitigationStatus] = {}

    def track_fvg(self, fvg) -> MitigationStatus:
        """
        Start tracking an FVG.

        Args:
            fvg: The FVG to track

        Returns:
            MitigationStatus for the tracked FVG
        """
        fvg_id = self._get_fvg_id(fvg)
        status = MitigationStatus(
            fvg_high=fvg.high,
            fvg_low=fvg.low,
            current_mitigation=MitigationType.WICK,  # Default
        )
        # Calculate 50% CE price
        status.ce50_price = fvg.low + (fvg.zone_size * 0.5)
        self._tracked_fvgs[fvg_id] = status
        return status

    def check_mitigation(
        self,
        fvg,
        current_candle,
    ) -> MitigationStatus:
        """
        Check if an FVG has been mitigated by the current candle.

        Args:
            fvg: The FVG to check
            current_candle: Current OHLCV candle

        Returns:
            Updated MitigationStatus
        """
        fvg_id = self._get_fvg_id(fvg)

        if fvg_id not in self._tracked_fvgs:
            # Start tracking this FVG
            status = self.track_fvg(fvg)
        else:
            status = self._tracked_fvgs[fvg_id]

        # Skip if already fully mitigated
        if status.is_mitigated:
            return status

        # Determine direction
        direction = (
            fvg.direction.value if hasattr(fvg.direction, "value") else fvg.direction
        )

        if direction == "bullish":
            status = self._check_bullish_mitigation(status, current_candle)
        else:
            status = self._check_bearish_mitigation(status, current_candle)

        # Check 50% CE
        if not status.ce50_reached and status.ce50_price is not None:
            if status.fvg_low < current_candle.close_price <= status.fvg_high:
                # Check if close price is at or above 50% CE
                if current_candle.close_price >= status.ce50_price:
                    status.ce50_reached = True
                    status.events.append(
                        MitigationEvent(
                            timestamp=current_candle.timestamp,
                            price=current_candle.close_price,
                            mitigation_type=MitigationType.CE50,
                            fvg_high=status.fvg_high,
                            fvg_low=status.fvg_low,
                            notes="50% CE reached",
                        )
                    )

        self._tracked_fvgs[fvg_id] = status
        return status

    def _check_bullish_mitigation(
        self,
        status: MitigationStatus,
        current_candle,
    ) -> MitigationStatus:
        """Check bullish FVG mitigation."""
        candle_low = current_candle.low_price
        candle_high = current_candle.high_price
        candle_close = current_candle.close_price
        candle_high_price = candle_high

        # Check for full mitigation (FVG fully filled)
        if candle_low <= status.fvg_low and candle_high_price >= status.fvg_high:
            status.current_mitigation = MitigationType.FULL
            status.events.append(
                MitigationEvent(
                    timestamp=current_candle.timestamp,
                    price=candle_close,
                    mitigation_type=MitigationType.FULL,
                    fvg_high=status.fvg_high,
                    fvg_low=status.fvg_low,
                    notes="FVG fully filled",
                )
            )
            return status

        # Check for close mitigation (candle closes within FVG)
        if status.fvg_low < candle_close < status.fvg_high:
            status.current_mitigation = MitigationType.CLOSE
            status.events.append(
                MitigationEvent(
                    timestamp=current_candle.timestamp,
                    price=candle_close,
                    mitigation_type=MitigationType.CLOSE,
                    fvg_high=status.fvg_high,
                    fvg_low=status.fvg_low,
                    notes="Candle closed within FVG",
                )
            )
            return status

        # Check for wick mitigation (wick entered FVG)
        # For bullish FVG: low of candle enters FVG zone
        if candle_low < status.fvg_low <= candle_high_price:
            if status.current_mitigation == MitigationType.WICK:
                # Already marked as wick, update if better price
                pass
            else:
                status.current_mitigation = MitigationType.WICK
                status.events.append(
                    MitigationEvent(
                        timestamp=current_candle.timestamp,
                        price=status.fvg_low,
                        mitigation_type=MitigationType.WICK,
                        fvg_high=status.fvg_high,
                        fvg_low=status.fvg_low,
                        notes="Wick entered FVG",
                    )
                )
            return status

        # Upper wick enters FVG
        if candle_low <= status.fvg_high < candle_high_price:
            if status.current_mitigation == MitigationType.WICK:
                pass
            else:
                status.current_mitigation = MitigationType.WICK
                status.events.append(
                    MitigationEvent(
                        timestamp=current_candle.timestamp,
                        price=status.fvg_high,
                        mitigation_type=MitigationType.WICK,
                        fvg_high=status.fvg_high,
                        fvg_low=status.fvg_low,
                        notes="Upper wick entered FVG",
                    )
                )

        return status

    def _check_bearish_mitigation(
        self,
        status: MitigationStatus,
        current_candle,
    ) -> MitigationStatus:
        """Check bearish FVG mitigation."""
        candle_low = current_candle.low_price
        candle_high = current_candle.high_price
        candle_close = current_candle.close_price

        # Check for full mitigation (FVG fully filled)
        if candle_low <= status.fvg_low and candle_high >= status.fvg_high:
            status.current_mitigation = MitigationType.FULL
            status.events.append(
                MitigationEvent(
                    timestamp=current_candle.timestamp,
                    price=candle_close,
                    mitigation_type=MitigationType.FULL,
                    fvg_high=status.fvg_high,
                    fvg_low=status.fvg_low,
                    notes="FVG fully filled",
                )
            )
            return status

        # Check for close mitigation (candle closes within FVG)
        if status.fvg_low < candle_close < status.fvg_high:
            status.current_mitigation = MitigationType.CLOSE
            status.events.append(
                MitigationEvent(
                    timestamp=current_candle.timestamp,
                    price=candle_close,
                    mitigation_type=MitigationType.CLOSE,
                    fvg_high=status.fvg_high,
                    fvg_low=status.fvg_low,
                    notes="Candle closed within FVG",
                )
            )
            return status

        # Check for wick mitigation (wick entered FVG)
        # For bearish FVG: high of candle enters FVG zone
        if candle_low <= status.fvg_low < candle_high:
            if status.current_mitigation == MitigationType.WICK:
                pass
            else:
                status.current_mitigation = MitigationType.WICK
                status.events.append(
                    MitigationEvent(
                        timestamp=current_candle.timestamp,
                        price=status.fvg_low,
                        mitigation_type=MitigationType.WICK,
                        fvg_high=status.fvg_high,
                        fvg_low=status.fvg_low,
                        notes="Wick entered FVG",
                    )
                )
            return status

        # Lower wick enters FVG
        if candle_low <= status.fvg_high < candle_high:
            if status.current_mitigation == MitigationType.WICK:
                pass
            else:
                status.current_mitigation = MitigationType.WICK
                status.events.append(
                    MitigationEvent(
                        timestamp=current_candle.timestamp,
                        price=status.fvg_high,
                        mitigation_type=MitigationType.WICK,
                        fvg_high=status.fvg_high,
                        fvg_low=status.fvg_low,
                        notes="Lower wick entered FVG",
                    )
                )

        return status

    def _get_fvg_id(self, fvg) -> str:
        """Generate unique ID for an FVG."""
        timestamp = fvg.timestamp if hasattr(fvg, "timestamp") else fvg.get("timestamp")
        direction = (
            fvg.direction.value if hasattr(fvg.direction, "value") else fvg.direction
        )
        return f"{direction}_{timestamp}"

    def get_status(self, fvg) -> MitigationStatus | None:
        """
        Get mitigation status for an FVG.

        Args:
            fvg: The FVG to get status for

        Returns:
            MitigationStatus if tracked, None otherwise
        """
        fvg_id = self._get_fvg_id(fvg)
        return self._tracked_fvgs.get(fvg_id)

    def stop_tracking(self, fvg) -> bool:
        """
        Stop tracking an FVG.

        Args:
            fvg: The FVG to stop tracking

        Returns:
            True if FVG was being tracked, False otherwise
        """
        fvg_id = self._get_fvg_id(fvg)
        if fvg_id in self._tracked_fvgs:
            del self._tracked_fvgs[fvg_id]
            return True
        return False

    def get_all_tracked(self) -> dict[str, MitigationStatus]:
        """Get all tracked FVGs."""
        return self._tracked_fvgs.copy()

    def clear(self) -> None:
        """Clear all tracked FVGs."""
        self._tracked_fvgs.clear()
