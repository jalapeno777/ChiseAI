"""Risk alert detector for portfolio management.

Detects risk threshold breaches from RiskMetrics and generates
RiskAlert objects for each breach.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.state_management.risk_calculator import RiskMetrics

    from .types import (
        AlertThresholds,
        RiskAlert,
    )

logger = logging.getLogger(__name__)


class RiskAlertDetector:
    """Detects risk threshold breaches and generates alerts.

    Analyzes RiskMetrics and generates RiskAlert objects for:
    - Exposure threshold breaches
    - Margin utilization threshold breaches
    - Concentration risk threshold breaches
    - Kill-switch conditions
    """

    def __init__(self, thresholds: AlertThresholds | None = None):
        """Initialize risk alert detector.

        Args:
            thresholds: Alert thresholds (uses defaults if None)
        """
        from .types import AlertThresholds

        self.thresholds = thresholds or AlertThresholds()
        logger.debug(
            f"RiskAlertDetector initialized: "
            f"exposure={self.thresholds.exposure_threshold_pct}%, "
            f"margin={self.thresholds.margin_utilization_threshold_pct}%, "
            f"concentration={self.thresholds.concentration_threshold_pct}%"
        )

    def detect_alerts(self, risk_metrics: RiskMetrics) -> list[RiskAlert]:
        """Detect all risk threshold breaches from metrics.

        Args:
            risk_metrics: Calculated risk metrics

        Returns:
            List of RiskAlert objects for triggered thresholds
        """
        alerts: list[RiskAlert] = []

        # Check exposure threshold
        exposure_alert = self._check_exposure(risk_metrics)
        if exposure_alert:
            alerts.append(exposure_alert)

        # Check margin utilization threshold
        margin_alert = self._check_margin_utilization(risk_metrics)
        if margin_alert:
            alerts.append(margin_alert)

        # Check concentration risk threshold
        concentration_alert = self._check_concentration(risk_metrics)
        if concentration_alert:
            alerts.append(concentration_alert)

        logger.debug(f"Detected {len(alerts)} risk alerts from metrics")
        return alerts

    def _check_exposure(self, risk_metrics: RiskMetrics) -> RiskAlert | None:
        """Check if exposure threshold is breached.

        Args:
            risk_metrics: Risk metrics to check

        Returns:
            RiskAlert if threshold breached, None otherwise
        """
        from .types import AlertSeverity, AlertType, RiskAlert

        total_equity = risk_metrics.margin_utilization.total_equity
        if total_equity <= 0:
            return None

        # Calculate exposure as percentage of equity
        exposure_pct = (abs(risk_metrics.net_exposure) / total_equity) * 100

        if exposure_pct > self.thresholds.exposure_threshold_pct:
            # Determine severity based on how much over threshold
            over_threshold = exposure_pct - self.thresholds.exposure_threshold_pct
            if over_threshold >= 20:
                severity = AlertSeverity.CRITICAL
            elif over_threshold >= 10:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO

            return RiskAlert(
                alert_type=AlertType.EXPOSURE,
                severity=severity,
                message=(
                    f"Net exposure ({exposure_pct:.1f}%) exceeds "
                    f"threshold ({self.thresholds.exposure_threshold_pct}%)"
                ),
                threshold=self.thresholds.exposure_threshold_pct,
                current_value=exposure_pct,
                portfolio_id=risk_metrics.portfolio_id,
            )

        return None

    def _check_margin_utilization(self, risk_metrics: RiskMetrics) -> RiskAlert | None:
        """Check if margin utilization threshold is breached.

        Args:
            risk_metrics: Risk metrics to check

        Returns:
            RiskAlert if threshold breached, None otherwise
        """
        from .types import AlertSeverity, AlertType, RiskAlert

        utilization_pct = risk_metrics.margin_utilization.utilization_pct

        if utilization_pct > self.thresholds.margin_utilization_threshold_pct:
            # Determine severity based on utilization level
            if utilization_pct >= 90:
                severity = AlertSeverity.CRITICAL
            elif utilization_pct >= 85:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO

            return RiskAlert(
                alert_type=AlertType.MARGIN_UTILIZATION,
                severity=severity,
                message=(
                    f"Margin utilization ({utilization_pct:.1f}%) exceeds "
                    f"threshold ({self.thresholds.margin_utilization_threshold_pct}%)"
                ),
                threshold=self.thresholds.margin_utilization_threshold_pct,
                current_value=utilization_pct,
                portfolio_id=risk_metrics.portfolio_id,
            )

        return None

    def _check_concentration(self, risk_metrics: RiskMetrics) -> RiskAlert | None:
        """Check if concentration risk threshold is breached.

        Args:
            risk_metrics: Risk metrics to check

        Returns:
            RiskAlert if threshold breached, None otherwise
        """
        from .types import AlertSeverity, AlertType, RiskAlert

        concentration_risk = risk_metrics.concentration_risk

        if concentration_risk > self.thresholds.concentration_threshold_pct:
            # Determine severity based on concentration level
            if concentration_risk >= 70:
                severity = AlertSeverity.CRITICAL
            elif concentration_risk >= 60:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO

            return RiskAlert(
                alert_type=AlertType.CONCENTRATION,
                severity=severity,
                message=(
                    f"Concentration risk ({concentration_risk:.1f}%) exceeds "
                    f"threshold ({self.thresholds.concentration_threshold_pct}%)"
                ),
                threshold=self.thresholds.concentration_threshold_pct,
                current_value=concentration_risk,
                portfolio_id=risk_metrics.portfolio_id,
            )

        return None

    def detect_kill_switch(
        self,
        risk_metrics: RiskMetrics,
        max_drawdown_pct: float = 15.0,
    ) -> RiskAlert | None:
        """Detect kill-switch condition (emergency stop).

        Args:
            risk_metrics: Risk metrics to check
            max_drawdown_pct: Maximum allowed drawdown percentage

        Returns:
            RiskAlert if kill-switch should activate, None otherwise
        """
        from .types import AlertSeverity, AlertType, RiskAlert

        # Check for critical margin utilization (emergency level)
        utilization_pct = risk_metrics.margin_utilization.utilization_pct

        if utilization_pct >= 95:
            return RiskAlert(
                alert_type=AlertType.KILL_SWITCH,
                severity=AlertSeverity.EMERGENCY,
                message=(
                    f"KILL SWITCH ACTIVATED: Critical margin utilization "
                    f"({utilization_pct:.1f}%) - Emergency position closure required"
                ),
                threshold=95.0,
                current_value=utilization_pct,
                portfolio_id=risk_metrics.portfolio_id,
                metadata={
                    "reason": "critical_margin",
                    "utilization_pct": utilization_pct,
                },
            )

        # Check for extreme concentration (single token risk)
        if risk_metrics.concentration_risk >= 80:
            return RiskAlert(
                alert_type=AlertType.KILL_SWITCH,
                severity=AlertSeverity.EMERGENCY,
                message=(
                    f"KILL SWITCH ACTIVATED: Extreme concentration risk "
                    f"({risk_metrics.concentration_risk:.1f}%) - Portfolio over-exposed"
                ),
                threshold=80.0,
                current_value=risk_metrics.concentration_risk,
                portfolio_id=risk_metrics.portfolio_id,
                metadata={
                    "reason": "extreme_concentration",
                    "concentration_pct": risk_metrics.concentration_risk,
                },
            )

        return None

    def update_thresholds(self, thresholds: AlertThresholds) -> None:
        """Update alert thresholds.

        Args:
            thresholds: New alert thresholds
        """
        self.thresholds = thresholds
        logger.debug(
            f"Updated thresholds: exposure={thresholds.exposure_threshold_pct}%, "
            f"margin={thresholds.margin_utilization_threshold_pct}%, "
            f"concentration={thresholds.concentration_threshold_pct}%"
        )
