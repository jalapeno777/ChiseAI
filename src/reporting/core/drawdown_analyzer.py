"""Drawdown Analyzer for the core report generation engine.

Calculates:
- Maximum drawdown (absolute and percentage)
- Drawdown duration
- Recovery time analysis
- Current drawdown status

For ST-NS-023-T1: Core Report Generation Engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DrawdownResult:
    """Result of drawdown analysis.

    Attributes:
        max_drawdown: Maximum drawdown (absolute value)
        max_drawdown_pct: Maximum drawdown as percentage
        current_drawdown: Current drawdown
        current_drawdown_pct: Current drawdown as percentage
        drawdown_start: When the maximum drawdown started
        drawdown_bottom: When the maximum drawdown bottomed
        drawdown_end: When drawdown recovered (if applicable)
        recovery_time_days: Days to recover from max drawdown
        duration_days: Duration of the drawdown period
    """

    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: float = 0.0
    current_drawdown: Decimal = Decimal("0")
    current_drawdown_pct: float = 0.0
    drawdown_start: datetime | None = None
    drawdown_bottom: datetime | None = None
    drawdown_end: datetime | None = None
    recovery_time_days: float = 0.0
    duration_days: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_drawdown": float(self.max_drawdown),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "current_drawdown": float(self.current_drawdown),
            "current_drawdown_pct": round(self.current_drawdown_pct, 2),
            "drawdown_start": (
                self.drawdown_start.isoformat() if self.drawdown_start else None
            ),
            "drawdown_bottom": (
                self.drawdown_bottom.isoformat() if self.drawdown_bottom else None
            ),
            "drawdown_end": (
                self.drawdown_end.isoformat() if self.drawdown_end else None
            ),
            "recovery_time_days": round(self.recovery_time_days, 2),
            "duration_days": round(self.duration_days, 2),
        }


@dataclass
class DrawdownEvent:
    """A single drawdown event.

    Attributes:
        start_time: When the drawdown started
        bottom_time: When the drawdown bottomed
        end_time: When the drawdown recovered (or None if ongoing)
        peak_value: Portfolio value at the peak before drawdown
        trough_value: Portfolio value at the bottom
        recovery_value: Portfolio value when recovered
        drawdown_amount: Absolute drawdown
        drawdown_pct: Percentage drawdown
        is_recovered: Whether the drawdown has been recovered
    """

    start_time: datetime
    bottom_time: datetime
    end_time: datetime | None = None
    peak_value: Decimal = Decimal("0")
    trough_value: Decimal = Decimal("0")
    recovery_value: Decimal | None = None
    drawdown_amount: Decimal = Decimal("0")
    drawdown_pct: float = 0.0
    is_recovered: bool = False

    @property
    def duration(self) -> timedelta:
        """Calculate duration of drawdown event.

        Returns:
            Duration from start to bottom (or to now if ongoing)
        """
        if self.end_time:
            return self.end_time - self.start_time
        return datetime.now(self.start_time.tzinfo) - self.start_time

    @property
    def recovery_time(self) -> timedelta | None:
        """Calculate recovery time (if recovered).

        Returns:
            Time to recover, or None if not recovered
        """
        if not self.is_recovered or not self.end_time:
            return None
        return self.end_time - self.start_time


@dataclass
class EquityPoint:
    """A single equity data point.

    Attributes:
        timestamp: Time of the data point
        equity: Portfolio equity at this point
        peak_equity: Peak equity up to this point
    """

    timestamp: datetime
    equity: Decimal
    peak_equity: Decimal = Decimal("0")


class DrawdownAnalyzer:
    """Analyze drawdowns in portfolio performance.

    Supports:
    - Maximum drawdown calculation
    - Drawdown duration analysis
    - Recovery time analysis
    - Multiple drawdown events tracking

    Attributes:
        min_peak_threshold: Minimum peak before tracking drawdown
    """

    def __init__(
        self,
        min_peak_threshold: float = 100.0,
    ) -> None:
        """Initialize drawdown analyzer.

        Args:
            min_peak_threshold: Minimum peak value to track drawdowns
        """
        self._min_peak_threshold = Decimal(str(min_peak_threshold))
        self._equity_curve: list[EquityPoint] = []
        self._drawdown_events: list[DrawdownEvent] = []

        logger.info(f"DrawdownAnalyzer initialized: min_peak=${min_peak_threshold}")

    def add_equity_point(
        self,
        timestamp: datetime,
        equity: float | Decimal,
    ) -> None:
        """Add an equity data point.

        Args:
            timestamp: Time of the data point
            equity: Portfolio equity value
        """
        equity_dec = Decimal(str(equity))

        # Calculate new peak
        if not self._equity_curve:
            peak = equity_dec
        else:
            peak = max(self._equity_curve[-1].peak_equity, equity_dec)

        point = EquityPoint(
            timestamp=timestamp,
            equity=equity_dec,
            peak_equity=peak,
        )

        self._equity_curve.append(point)

    def add_equity_curve(
        self,
        data: list[tuple[datetime, float | Decimal]],
    ) -> None:
        """Add multiple equity data points.

        Args:
            data: List of (timestamp, equity) tuples
        """
        for timestamp, equity in data:
            self.add_equity_point(timestamp, equity)

    def clear(self) -> None:
        """Clear all equity data and drawdown events."""
        self._equity_curve.clear()
        self._drawdown_events.clear()

    def calculate_max_drawdown(self) -> DrawdownResult:
        """Calculate maximum drawdown from current equity curve.

        Returns:
            DrawdownResult with maximum drawdown metrics
        """
        if not self._equity_curve:
            return DrawdownResult()

        max_dd = Decimal("0")
        max_dd_pct = 0.0
        current_dd = Decimal("0")
        current_dd_pct = 0.0
        dd_start: datetime | None = None
        dd_bottom: datetime | None = None
        dd_end: datetime | None = None
        in_drawdown = False
        temp_dd_start: datetime | None = None

        peak = Decimal("0")

        for point in self._equity_curve:
            if point.peak_equity > peak:
                peak = point.peak_equity
                in_drawdown = False
                dd_start = None
            else:
                # We're in a drawdown
                if not in_drawdown and peak >= self._min_peak_threshold:
                    in_drawdown = True
                    temp_dd_start = point.timestamp

                if in_drawdown:
                    dd = peak - point.equity
                    dd_pct = (dd / peak) * 100 if peak > 0 else 0.0

                    if dd > max_dd:
                        max_dd = dd
                        max_dd_pct = float(dd_pct)
                        dd_start = temp_dd_start
                        dd_bottom = point.timestamp
                        dd_end = None

        # Calculate current drawdown
        if self._equity_curve:
            last_point = self._equity_curve[-1]
            current_dd = last_point.peak_equity - last_point.equity
            current_dd_pct = (
                float(current_dd / last_point.peak_equity * 100)
                if last_point.peak_equity > 0
                else 0.0
            )

        # Calculate recovery time for max drawdown
        recovery_days = 0.0
        duration_days = 0.0

        if dd_bottom and max_dd > 0:
            # Find recovery point
            for point in self._equity_curve:
                if point.timestamp > dd_bottom and point.equity >= peak:
                    if dd_start:
                        recovery_days = (
                            point.timestamp - dd_start
                        ).total_seconds() / 86400
                        dd_end = point.timestamp
                    break

            # Calculate duration
            if dd_start:
                duration_days = (dd_bottom - dd_start).total_seconds() / 86400

        result = DrawdownResult(
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            current_drawdown=current_dd,
            current_drawdown_pct=current_dd_pct,
            drawdown_start=dd_start,
            drawdown_bottom=dd_bottom,
            drawdown_end=dd_end,
            recovery_time_days=recovery_days,
            duration_days=duration_days,
        )

        logger.debug(
            f"Max drawdown: ${max_dd} ({max_dd_pct:.2f}%), "
            f"duration: {duration_days:.1f}d, recovery: {recovery_days:.1f}d"
        )

        return result

    def analyze_drawdown_events(
        self,
        min_drawdown_pct: float = 5.0,
    ) -> list[DrawdownEvent]:
        """Analyze all drawdown events from equity curve.

        Args:
            min_drawdown_pct: Minimum drawdown percentage to track

        Returns:
            List of DrawdownEvent objects
        """
        if not self._equity_curve:
            return []

        events: list[DrawdownEvent] = []
        peak = Decimal("0")
        peak_time: datetime | None = None
        in_drawdown = False
        dd_trough: datetime | None = None
        dd_trough_value = Decimal("0")
        current_dd_start: datetime | None = None

        for point in self._equity_curve:
            if point.peak_equity > peak:
                # New peak reached
                if in_drawdown and current_dd_start:
                    # We were in a drawdown and recovered
                    dd_pct = (
                        float((peak - dd_trough_value) / peak * 100)
                        if peak > 0
                        else 0.0
                    )
                    if dd_pct >= min_drawdown_pct:
                        event = DrawdownEvent(
                            start_time=current_dd_start,
                            bottom_time=dd_trough,
                            end_time=point.timestamp,
                            peak_value=peak,
                            trough_value=dd_trough_value,
                            recovery_value=point.equity,
                            drawdown_amount=peak - dd_trough_value,
                            drawdown_pct=dd_pct,
                            is_recovered=True,
                        )
                        events.append(event)

                peak = point.peak_equity
                peak_time = point.timestamp
                in_drawdown = False
                current_dd_start = None

            elif peak > 0 and point.equity < peak:
                # In drawdown
                if not in_drawdown:
                    in_drawdown = True
                    current_dd_start = peak_time
                    dd_trough = point.timestamp
                    dd_trough_value = point.equity
                else:
                    # Continue tracking drawdown
                    if point.equity < dd_trough_value:
                        dd_trough = point.timestamp
                        dd_trough_value = point.equity

        # Handle ongoing drawdown
        if in_drawdown and current_dd_start and dd_trough:
            dd_pct = float((peak - dd_trough_value) / peak * 100) if peak > 0 else 0.0
            if dd_pct >= min_drawdown_pct:
                event = DrawdownEvent(
                    start_time=current_dd_start,
                    bottom_time=dd_trough,
                    peak_value=peak,
                    trough_value=dd_trough_value,
                    drawdown_amount=peak - dd_trough_value,
                    drawdown_pct=dd_pct,
                    is_recovered=False,
                )
                events.append(event)

        self._drawdown_events = events
        logger.debug(f"Found {len(events)} drawdown events")

        return events

    def get_current_drawdown(self) -> DrawdownResult:
        """Get current drawdown status.

        Returns:
            DrawdownResult with current drawdown metrics
        """
        if not self._equity_curve:
            return DrawdownResult()

        last_point = self._equity_curve[-1]
        peak = last_point.peak_equity
        equity = last_point.equity

        dd_amount = peak - equity
        dd_pct = float(dd_amount / peak * 100) if peak > 0 else 0.0

        # Find when the current drawdown started
        dd_start: datetime | None = None
        for point in reversed(self._equity_curve):
            if point.peak_equity > equity:
                dd_start = point.timestamp
                break

        return DrawdownResult(
            current_drawdown=dd_amount,
            current_drawdown_pct=dd_pct,
            drawdown_start=dd_start,
            drawdown_bottom=last_point.timestamp if dd_amount > 0 else None,
        )

    def get_drawdown_statistics(self) -> dict[str, Any]:
        """Get statistics about all drawdown events.

        Returns:
            Dictionary with drawdown statistics
        """
        if not self._drawdown_events:
            # Re-analyze if no events stored
            self.analyze_drawdown_events()

        if not self._drawdown_events:
            return {
                "total_drawdowns": 0,
                "average_drawdown_pct": 0.0,
                "average_duration_days": 0.0,
                "average_recovery_days": 0.0,
                "longest_drawdown_days": 0.0,
                "slowest_recovery_days": 0.0,
                "recovery_rate": 0.0,
            }

        recovered = [e for e in self._drawdown_events if e.is_recovered]
        avg_dd_pct = sum(e.drawdown_pct for e in self._drawdown_events) / len(
            self._drawdown_events
        )
        avg_duration = (
            sum(e.duration.total_seconds() for e in self._drawdown_events)
            / len(self._drawdown_events)
            / 86400
        )

        avg_recovery = 0.0
        if recovered:
            recovery_times = [
                e.recovery_time.total_seconds() / 86400
                for e in recovered
                if e.recovery_time
            ]
            if recovery_times:
                avg_recovery = sum(recovery_times) / len(recovery_times)

        longest_dd = (
            max(e.duration.total_seconds() for e in self._drawdown_events) / 86400
        )

        slowest_recovery = 0.0
        if recovered:
            recovery_times = [
                e.recovery_time.total_seconds() / 86400
                for e in recovered
                if e.recovery_time
            ]
            if recovery_times:
                slowest_recovery = max(recovery_times)

        recovery_rate = len(recovered) / len(self._drawdown_events) * 100

        return {
            "total_drawdowns": len(self._drawdown_events),
            "average_drawdown_pct": round(avg_dd_pct, 2),
            "average_duration_days": round(avg_duration, 2),
            "average_recovery_days": round(avg_recovery, 2),
            "longest_drawdown_days": round(longest_dd, 2),
            "slowest_recovery_days": round(slowest_recovery, 2),
            "recovery_rate": round(recovery_rate, 2),
        }
