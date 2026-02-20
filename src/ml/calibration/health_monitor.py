"""Calibration Health Monitor for ChiseAI.

This module provides the CalibrationHealthMonitor class for monitoring
calibration system health, tracking ECE trends, and triggering alerts
when calibration quality degrades.

Features:
- ECE trend monitoring
- Threshold adjustment frequency tracking
- Calibration stability scoring
- InfluxDB health metric export
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ml.calibration.controller import ThresholdController
    from ml.calibration.dynamic import DynamicThresholdAdjuster
    from ml.calibration.telemetry_exporter import CalibrationTelemetryExporter

# Import at runtime for type hints that need the actual class
from ml.calibration.telemetry_exporter import CalibrationHealthMetrics

logger = logging.getLogger(__name__)


# Health status thresholds
ECE_ALERT_THRESHOLD: float = 0.15  # ECE > 15% triggers alert
ECE_CRITICAL_THRESHOLD: float = 0.25  # ECE > 25% is critical
STABILITY_WINDOW_HOURS: int = 24  # Window for stability calculation
MAX_ACCEPTABLE_STABILITY_SCORE: float = 50.0  # Lower is better


class CalibrationStatus:
    """Calibration health status values."""

    WELL_CALIBRATED = "well_calibrated"
    ACCEPTABLE = "acceptable"
    POORLY_CALIBRATED = "poorly_calibrated"
    CRITICAL = "critical"


@dataclass
class CalibrationAlert:
    """Calibration health alert.

    Attributes:
        timestamp: When the alert was triggered
        signal_type: Type of signal (LONG, SHORT, SCALP) or 'all'
        alert_type: Type of alert ('ece_high', 'adjustment_spike', etc.)
        severity: Alert severity ('warning', 'critical')
        message: Human-readable alert message
        ece_value: Current ECE value that triggered alert
        threshold: Current threshold value
    """

    timestamp: datetime
    signal_type: str
    alert_type: str
    severity: str
    message: str
    ece_value: float | None = None
    threshold: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "ece_value": self.ece_value,
            "threshold": self.threshold,
        }


@dataclass
class AdjustmentFrequencyMetrics:
    """Metrics for threshold adjustment frequency.

    Attributes:
        signal_type: Type of signal
        adjustments_1h: Adjustments in last hour
        adjustments_6h: Adjustments in last 6 hours
        adjustments_24h: Adjustments in last 24 hours
        avg_adjustment_size: Average adjustment magnitude
        max_adjustment_size: Maximum adjustment magnitude
    """

    signal_type: str
    adjustments_1h: int = 0
    adjustments_6h: int = 0
    adjustments_24h: int = 0
    avg_adjustment_size: float = 0.0
    max_adjustment_size: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type,
            "adjustments_1h": self.adjustments_1h,
            "adjustments_6h": self.adjustments_6h,
            "adjustments_24h": self.adjustments_24h,
            "avg_adjustment_size": round(self.avg_adjustment_size, 4),
            "max_adjustment_size": round(self.max_adjustment_size, 4),
        }


class CalibrationHealthMonitor:
    """Monitor calibration system health and trigger alerts.

    The health monitor tracks ECE trends, threshold adjustment patterns,
    and overall calibration stability. It can export metrics to InfluxDB
    and trigger alerts when calibration quality degrades.

    Usage:
        >>> monitor = CalibrationHealthMonitor(controller, adjuster)
        >>> # Check health periodically
        >>> health_metrics = monitor.check_health("LONG")
        >>> alerts = monitor.get_active_alerts()
        >>> # Export to InfluxDB
        >>> await monitor.export_health_metrics(exporter)
    """

    def __init__(
        self,
        controller: ThresholdController,
        adjuster: DynamicThresholdAdjuster | None = None,
        ece_alert_threshold: float = ECE_ALERT_THRESHOLD,
        ece_critical_threshold: float = ECE_CRITICAL_THRESHOLD,
        enable_alerts: bool = True,
    ):
        """Initialize the calibration health monitor.

        Args:
            controller: ThresholdController with calibration data
            adjuster: DynamicThresholdAdjuster with adjustment history
            ece_alert_threshold: ECE threshold for warning alerts
            ece_critical_threshold: ECE threshold for critical alerts
            enable_alerts: Whether to enable alert generation
        """
        self.controller = controller
        self.adjuster = adjuster
        self.ece_alert_threshold = ece_alert_threshold
        self.ece_critical_threshold = ece_critical_threshold
        self.enable_alerts = enable_alerts

        # Alert tracking
        self._active_alerts: list[CalibrationAlert] = []
        self._alert_history: list[CalibrationAlert] = []

        # ECE history for trend analysis
        self._ece_history: dict[str, list[tuple[datetime, float]]] = {
            "LONG": [],
            "SHORT": [],
            "SCALP": [],
        }

        logger.info(
            f"CalibrationHealthMonitor initialized: "
            f"alert_threshold={ece_alert_threshold:.2f}, "
            f"critical_threshold={ece_critical_threshold:.2f}"
        )

    def check_health(self, signal_type: str) -> CalibrationHealthMetrics:
        """Check calibration health for a signal type.

        Args:
            signal_type: Type of signal to check (LONG, SHORT, SCALP)

        Returns:
            CalibrationHealthMetrics with current health status
        """
        timestamp = datetime.now(UTC)

        # Get current ECE
        ece = self._get_current_ece(signal_type)

        # Get current threshold
        threshold = self.controller.get_current_threshold(signal_type)

        # Determine health status
        health_status = self._determine_health_status(ece)

        # Calculate adjustment frequencies
        adj_counts = self._calculate_adjustment_counts(signal_type)

        # Calculate stability score
        stability_score = self._calculate_stability_score(signal_type, ece)

        # Create health metrics
        metrics = CalibrationHealthMetrics(
            timestamp=timestamp,
            signal_type=signal_type,
            ece=ece if ece is not None else 1.0,
            threshold=threshold,
            health_status=health_status,
            adjustment_count_1h=adj_counts["1h"],
            adjustment_count_24h=adj_counts["24h"],
            stability_score=stability_score,
        )

        # Update ECE history
        if ece is not None:
            self._ece_history[signal_type].append((timestamp, ece))
            # Trim history to last 24 hours
            cutoff = timestamp - timedelta(hours=STABILITY_WINDOW_HOURS)
            self._ece_history[signal_type] = [
                (t, v) for t, v in self._ece_history[signal_type] if t >= cutoff
            ]

        # Check for alerts if enabled
        if self.enable_alerts:
            self._check_alerts(signal_type, ece, threshold)

        return metrics

    def check_health_all(self) -> dict[str, CalibrationHealthMetrics]:
        """Check calibration health for all signal types.

        Returns:
            Dictionary mapping signal type to health metrics
        """
        return {
            "LONG": self.check_health("LONG"),
            "SHORT": self.check_health("SHORT"),
            "SCALP": self.check_health("SCALP"),
        }

    def _get_current_ece(self, signal_type: str) -> float | None:
        """Get current ECE for a signal type.

        Args:
            signal_type: Type of signal

        Returns:
            Current ECE value or None if not available
        """
        return self.controller._last_ece.get(signal_type)

    def _determine_health_status(self, ece: float | None) -> str:
        """Determine health status based on ECE.

        Args:
            ece: Current ECE value

        Returns:
            Health status string
        """
        if ece is None:
            return CalibrationStatus.POORLY_CALIBRATED

        if ece >= self.ece_critical_threshold:
            return CalibrationStatus.CRITICAL
        elif ece >= self.ece_alert_threshold:
            return CalibrationStatus.POORLY_CALIBRATED
        elif ece >= ECE_ALERT_THRESHOLD * 0.5:  # Halfway to alert threshold
            return CalibrationStatus.ACCEPTABLE
        else:
            return CalibrationStatus.WELL_CALIBRATED

    def _calculate_adjustment_counts(self, signal_type: str) -> dict[str, int]:
        """Calculate adjustment counts for various time windows.

        Args:
            signal_type: Type of signal

        Returns:
            Dictionary with adjustment counts for different windows
        """
        if self.adjuster is None:
            return {"1h": 0, "6h": 0, "24h": 0}

        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)
        six_hours_ago = now - timedelta(hours=6)
        day_ago = now - timedelta(hours=24)

        adjustments_1h = 0
        adjustments_6h = 0
        adjustments_24h = 0

        for adj in self.adjuster.adjustment_history:
            if adj.signal_type != signal_type:
                continue

            if adj.timestamp >= hour_ago:
                adjustments_1h += 1
            if adj.timestamp >= six_hours_ago:
                adjustments_6h += 1
            if adj.timestamp >= day_ago:
                adjustments_24h += 1

        return {
            "1h": adjustments_1h,
            "6h": adjustments_6h,
            "24h": adjustments_24h,
        }

    def _calculate_stability_score(
        self,
        signal_type: str,
        current_ece: float | None,
    ) -> float:
        """Calculate calibration stability score (lower is better).

        The stability score considers:
        - ECE variance over time
        - Adjustment frequency
        - Current ECE level

        Args:
            signal_type: Type of signal
            current_ece: Current ECE value

        Returns:
            Stability score (0-100 scale, lower is better)
        """
        if current_ece is None:
            return 100.0  # Worst score if no data

        score = 0.0

        # Factor 1: Current ECE level (0-40 points)
        # ECE of 0.25 = 40 points, ECE of 0 = 0 points
        ece_component = min(40.0, current_ece * 160)
        score += ece_component

        # Factor 2: ECE variance over last 24h (0-30 points)
        history = self._ece_history.get(signal_type, [])
        if len(history) >= 5:
            ece_values = [v for _, v in history]
            ece_std = np.std(ece_values)
            # Std of 0.1 = 30 points, 0 = 0 points
            variance_component = min(30.0, ece_std * 300)
            score += variance_component

        # Factor 3: Adjustment frequency (0-30 points)
        adj_counts = self._calculate_adjustment_counts(signal_type)
        # More than 10 adjustments in 24h = 30 points
        adj_component = min(30.0, adj_counts["24h"] * 3)
        score += adj_component

        return float(min(100.0, score))

    def _check_alerts(
        self,
        signal_type: str,
        ece: float | None,
        threshold: float,
    ) -> None:
        """Check for and create alerts if needed.

        Args:
            signal_type: Type of signal
            ece: Current ECE value
            threshold: Current threshold value
        """
        if ece is None:
            return

        timestamp = datetime.now(UTC)

        # Check for critical ECE
        if ece >= self.ece_critical_threshold:
            alert = CalibrationAlert(
                timestamp=timestamp,
                signal_type=signal_type,
                alert_type="ece_critical",
                severity="critical",
                message=f"ECE is critically high: {ece:.4f} "
                f"(threshold: {self.ece_critical_threshold:.2f})",
                ece_value=ece,
                threshold=threshold,
            )
            self._add_alert(alert)

        # Check for high ECE (warning)
        elif ece >= self.ece_alert_threshold:
            alert = CalibrationAlert(
                timestamp=timestamp,
                signal_type=signal_type,
                alert_type="ece_high",
                severity="warning",
                message=f"ECE is above acceptable threshold: {ece:.4f} "
                f"(threshold: {self.ece_alert_threshold:.2f})",
                ece_value=ece,
                threshold=threshold,
            )
            self._add_alert(alert)

        # Check for adjustment spike
        adj_counts = self._calculate_adjustment_counts(signal_type)
        if adj_counts["1h"] >= 3:
            alert = CalibrationAlert(
                timestamp=timestamp,
                signal_type=signal_type,
                alert_type="adjustment_spike",
                severity="warning",
                message=f"High adjustment frequency: {adj_counts['1h']} "
                f"adjustments in last hour",
                ece_value=ece,
                threshold=threshold,
            )
            self._add_alert(alert)

    def _add_alert(self, alert: CalibrationAlert) -> None:
        """Add an alert if not already active.

        Args:
            alert: Alert to add
        """
        # Check for duplicate recent alert
        recent_cutoff = datetime.now(UTC) - timedelta(minutes=5)
        for existing in self._active_alerts:
            if (
                existing.signal_type == alert.signal_type
                and existing.alert_type == alert.alert_type
                and existing.timestamp >= recent_cutoff
            ):
                return  # Duplicate, don't add

        self._active_alerts.append(alert)
        self._alert_history.append(alert)

        logger.warning(
            f"Calibration alert: [{alert.severity.upper()}] "
            f"{alert.signal_type}: {alert.message}"
        )

    def get_active_alerts(
        self,
        signal_type: str | None = None,
        severity: str | None = None,
    ) -> list[CalibrationAlert]:
        """Get active (unresolved) alerts.

        Args:
            signal_type: Filter by signal type
            severity: Filter by severity

        Returns:
            List of active alerts
        """
        alerts = self._active_alerts.copy()

        if signal_type:
            alerts = [a for a in alerts if a.signal_type == signal_type]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return alerts

    def clear_alerts(self, signal_type: str | None = None) -> int:
        """Clear active alerts.

        Args:
            signal_type: Only clear alerts for this signal type, or None for all

        Returns:
            Number of alerts cleared
        """
        if signal_type is None:
            count = len(self._active_alerts)
            self._active_alerts.clear()
            return count

        original_count = len(self._active_alerts)
        self._active_alerts = [
            a for a in self._active_alerts if a.signal_type != signal_type
        ]
        return original_count - len(self._active_alerts)

    def get_adjustment_frequency_metrics(
        self,
        signal_type: str,
    ) -> AdjustmentFrequencyMetrics:
        """Get adjustment frequency metrics for a signal type.

        Args:
            signal_type: Type of signal

        Returns:
            AdjustmentFrequencyMetrics
        """
        if self.adjuster is None:
            return AdjustmentFrequencyMetrics(signal_type=signal_type)

        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)
        six_hours_ago = now - timedelta(hours=6)
        day_ago = now - timedelta(hours=24)

        adjustments_1h = 0
        adjustments_6h = 0
        adjustments_24h = 0
        adjustment_sizes = []

        for adj in self.adjuster.adjustment_history:
            if adj.signal_type != signal_type:
                continue

            adjustment_sizes.append(abs(adj.change_amount))

            if adj.timestamp >= hour_ago:
                adjustments_1h += 1
            if adj.timestamp >= six_hours_ago:
                adjustments_6h += 1
            if adj.timestamp >= day_ago:
                adjustments_24h += 1

        return AdjustmentFrequencyMetrics(
            signal_type=signal_type,
            adjustments_1h=adjustments_1h,
            adjustments_6h=adjustments_6h,
            adjustments_24h=adjustments_24h,
            avg_adjustment_size=(
                float(np.mean(adjustment_sizes)) if adjustment_sizes else 0.0
            ),
            max_adjustment_size=max(adjustment_sizes) if adjustment_sizes else 0.0,
        )

    async def export_health_metrics(
        self,
        exporter: CalibrationTelemetryExporter,
        signal_type: str | None = None,
    ) -> bool:
        """Export health metrics to InfluxDB.

        Args:
            exporter: TelemetryExporter instance
            signal_type: Specific signal type, or None for all

        Returns:
            True if export successful
        """
        signal_types = [signal_type] if signal_type else ["LONG", "SHORT", "SCALP"]

        try:
            for st in signal_types:
                metrics = self.check_health(st)
                await exporter.export_health_status(metrics)

            return True

        except Exception as e:
            logger.warning(f"Failed to export health metrics: {e}")
            return False

    def get_health_summary(self) -> dict[str, Any]:
        """Get overall health summary.

        Returns:
            Dictionary with health summary
        """
        all_metrics = self.check_health_all()

        worst_status = CalibrationStatus.WELL_CALIBRATED
        status_priority = {
            CalibrationStatus.WELL_CALIBRATED: 0,
            CalibrationStatus.ACCEPTABLE: 1,
            CalibrationStatus.POORLY_CALIBRATED: 2,
            CalibrationStatus.CRITICAL: 3,
        }

        for metrics in all_metrics.values():
            if status_priority.get(metrics.health_status, 0) > status_priority.get(
                worst_status, 0
            ):
                worst_status = metrics.health_status

        active_alerts = len(self.get_active_alerts())

        return {
            "overall_status": worst_status,
            "active_alerts": active_alerts,
            "signal_health": {
                st: {
                    "status": m.health_status,
                    "ece": round(m.ece, 4),
                    "threshold": round(m.threshold, 4),
                    "stability_score": round(m.stability_score, 2),
                }
                for st, m in all_metrics.items()
            },
        }


__all__ = [
    "CalibrationHealthMonitor",
    "CalibrationAlert",
    "AdjustmentFrequencyMetrics",
    "CalibrationStatus",
    "CalibrationHealthMetrics",
    "ECE_ALERT_THRESHOLD",
    "ECE_CRITICAL_THRESHOLD",
]
