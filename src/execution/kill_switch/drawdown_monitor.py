"""Drawdown monitor for kill-switch triggering.

Tracks rolling 24-hour portfolio value and calculates drawdown
metrics for kill-switch activation decisions.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class PortfolioValuePoint:
    """A single portfolio value measurement.

    Attributes:
        timestamp: When the value was recorded
        value: Portfolio value in base currency
        source: Data source ("bybit", "bitget", "calculated")
    """

    timestamp: datetime
    value: float
    source: str = "calculated"


@dataclass
class DrawdownMetrics:
    """Calculated drawdown metrics.

    Attributes:
        current_drawdown_pct: Current drawdown from peak
        peak_value: Highest value in the rolling window
        trough_value: Lowest value in the rolling window
        peak_timestamp: When peak occurred
        trough_timestamp: When trough occurred
        window_start: Start of rolling window
        window_end: End of rolling window
        data_points: Number of data points in calculation
    """

    current_drawdown_pct: float = 0.0
    peak_value: float = 0.0
    trough_value: float = 0.0
    peak_timestamp: datetime | None = None
    trough_timestamp: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    data_points: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "current_drawdown_pct": self.current_drawdown_pct,
            "peak_value": self.peak_value,
            "trough_value": self.trough_value,
            "peak_timestamp": self.peak_timestamp.isoformat()
            if self.peak_timestamp
            else None,
            "trough_timestamp": self.trough_timestamp.isoformat()
            if self.trough_timestamp
            else None,
            "window_start": self.window_start.isoformat()
            if self.window_start
            else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "data_points": self.data_points,
        }


class DrawdownMonitor:
    """Monitors portfolio value and calculates rolling drawdown.

    Tracks portfolio value over a rolling window (default 24 hours)
    and calculates drawdown metrics for kill-switch decisions.

    Attributes:
        rolling_window_hours: Hours to keep in rolling window
        max_data_points: Maximum data points to retain
        influxdb_client: Optional InfluxDB client for metrics persistence
        measurement_name: InfluxDB measurement name
    """

    def __init__(
        self,
        rolling_window_hours: int = 24,
        max_data_points: int = 10000,
        influxdb_client: Any | None = None,
        measurement_name: str = "drawdown_metrics",
    ):
        """Initialize drawdown monitor.

        Args:
            rolling_window_hours: Rolling window duration in hours
            max_data_points: Maximum data points to retain
            influxdb_client: Optional InfluxDB client for persistence
            measurement_name: InfluxDB measurement name
        """
        self.rolling_window_hours = rolling_window_hours
        self.max_data_points = max_data_points
        self.influxdb_client = influxdb_client
        self.measurement_name = measurement_name

        self._value_history: list[PortfolioValuePoint] = []
        self._last_metrics: DrawdownMetrics | None = None

        logger.info(
            f"DrawdownMonitor initialized: window={rolling_window_hours}h, "
            f"max_points={max_data_points}"
        )

    def record_value(
        self,
        value: float,
        timestamp: datetime | None = None,
        source: str = "calculated",
    ) -> None:
        """Record a portfolio value measurement.

        Args:
            value: Portfolio value
            timestamp: Measurement timestamp (default: now)
            source: Data source identifier
        """
        ts = timestamp or datetime.now(UTC)
        point = PortfolioValuePoint(timestamp=ts, value=value, source=source)
        self._value_history.append(point)

        # Trim to max size
        if len(self._value_history) > self.max_data_points:
            self._value_history = self._value_history[-self.max_data_points :]

        # Trim to rolling window
        self._trim_to_window()

        logger.debug(f"Recorded portfolio value: {value:.2f} at {ts}")

    def _trim_to_window(self) -> None:
        """Remove data points outside the rolling window."""
        if not self._value_history:
            return

        cutoff = datetime.now(UTC) - timedelta(hours=self.rolling_window_hours)
        self._value_history = [p for p in self._value_history if p.timestamp >= cutoff]

    def calculate_rolling_drawdown(self) -> DrawdownMetrics:
        """Calculate drawdown over the rolling window.

        Returns:
            DrawdownMetrics with current drawdown percentage and related data
        """
        self._trim_to_window()

        if len(self._value_history) < 2:
            # Not enough data for meaningful calculation
            metrics = DrawdownMetrics(
                current_drawdown_pct=0.0,
                data_points=len(self._value_history),
            )
            self._last_metrics = metrics
            return metrics

        # Find peak and trough
        peak_point = max(self._value_history, key=lambda p: p.value)
        trough_point = min(self._value_history, key=lambda p: p.value)

        # Current value is the most recent
        current_value = self._value_history[-1].value

        # Calculate drawdown from peak
        if peak_point.value > 0:
            drawdown_pct = ((peak_point.value - current_value) / peak_point.value) * 100
            # Ensure non-negative (shouldn't happen but safety check)
            drawdown_pct = max(0.0, drawdown_pct)
        else:
            drawdown_pct = 0.0

        metrics = DrawdownMetrics(
            current_drawdown_pct=drawdown_pct,
            peak_value=peak_point.value,
            trough_value=trough_point.value,
            peak_timestamp=peak_point.timestamp,
            trough_timestamp=trough_point.timestamp,
            window_start=self._value_history[0].timestamp,
            window_end=self._value_history[-1].timestamp,
            data_points=len(self._value_history),
        )

        self._last_metrics = metrics

        logger.debug(
            f"Drawdown calculation: {drawdown_pct:.2f}% from peak {peak_point.value:.2f}"
        )

        return metrics

    def check_drawdown_threshold(self, threshold_pct: float = 15.0) -> bool:
        """Check if current drawdown exceeds threshold.

        Args:
            threshold_pct: Drawdown threshold percentage

        Returns:
            True if drawdown exceeds threshold, False otherwise
        """
        metrics = self.calculate_rolling_drawdown()

        exceeded = metrics.current_drawdown_pct >= threshold_pct

        if exceeded:
            logger.warning(
                f"Drawdown threshold exceeded: {metrics.current_drawdown_pct:.2f}% "
                f">= {threshold_pct}%"
            )

        return exceeded

    def get_current_value(self) -> float | None:
        """Get most recent portfolio value.

        Returns:
            Latest portfolio value or None if no data
        """
        if not self._value_history:
            return None
        return self._value_history[-1].value

    def get_peak_value(self) -> float | None:
        """Get peak value in rolling window.

        Returns:
            Peak portfolio value or None if no data
        """
        self._trim_to_window()
        if not self._value_history:
            return None
        return max(p.value for p in self._value_history)

    def get_value_history(self) -> list[PortfolioValuePoint]:
        """Get current value history (copy).

        Returns:
            List of portfolio value points in the rolling window
        """
        self._trim_to_window()
        return list(self._value_history)

    async def write_metrics_to_influxdb(
        self, metrics: DrawdownMetrics | None = None
    ) -> bool:
        """Write drawdown metrics to InfluxDB.

        Args:
            metrics: Metrics to write (default: recalculate current)

        Returns:
            True if write successful, False otherwise
        """
        if not self.influxdb_client:
            return False

        m = metrics or self.calculate_rolling_drawdown()

        try:
            # Build InfluxDB point
            point = {
                "measurement": self.measurement_name,
                "tags": {
                    "source": "drawdown_monitor",
                },
                "fields": {
                    "drawdown_pct": m.current_drawdown_pct,
                    "peak_value": m.peak_value,
                    "trough_value": m.trough_value,
                    "data_points": m.data_points,
                },
                "time": datetime.now(UTC).isoformat(),
            }

            # Write to InfluxDB
            await self.influxdb_client.write_point(point)

            logger.debug(
                f"Wrote drawdown metrics to InfluxDB: {m.current_drawdown_pct:.2f}%"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to write drawdown metrics to InfluxDB: {e}")
            return False

    def reset(self) -> None:
        """Reset the monitor, clearing all history."""
        self._value_history.clear()
        self._last_metrics = None
        logger.info("DrawdownMonitor reset")

    def get_summary(self) -> dict[str, Any]:
        """Get summary of current drawdown state.

        Returns:
            Dictionary with drawdown summary
        """
        metrics = self.calculate_rolling_drawdown()
        current_value = self.get_current_value()

        return {
            "current_drawdown_pct": metrics.current_drawdown_pct,
            "current_value": current_value,
            "peak_value": metrics.peak_value,
            "trough_value": metrics.trough_value,
            "window_hours": self.rolling_window_hours,
            "data_points": metrics.data_points,
            "window_start": metrics.window_start.isoformat()
            if metrics.window_start
            else None,
            "window_end": metrics.window_end.isoformat()
            if metrics.window_end
            else None,
        }
