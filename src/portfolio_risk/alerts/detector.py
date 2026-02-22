"""Risk alert detector for portfolio management.

Detects risk threshold breaches from RiskMetrics and generates
RiskAlert objects for each breach.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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

    # Paper Trading Alert Methods (ST-PAPER-008)

    def detect_redis_failure(
        self,
        error_rate: float,
        affected_operations: list[str],
        circuit_breaker_open: bool = False,
    ) -> RiskAlert | None:
        """Detect Redis failure condition and generate alert.

        Triggers when Redis circuit breaker opens or error rate is critical.

        Args:
            error_rate: Percentage of Redis operations failing (0-100)
            affected_operations: List of operation types affected by the failure
            circuit_breaker_open: Whether the circuit breaker is currently open

        Returns:
            RiskAlert if Redis failure detected, None otherwise
        """
        from .types import AlertSeverity, AlertType, RiskAlert

        # Trigger if circuit breaker is open or error rate is critical (>50%)
        if circuit_breaker_open or error_rate > 50.0:
            return RiskAlert(
                alert_type=AlertType.REDIS_FAILURE,
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"REDIS FAILURE: Circuit breaker {'OPEN' if circuit_breaker_open else 'CLOSED'}, "
                    f"error rate {error_rate:.1f}%. "
                    f"Affected operations: {', '.join(affected_operations)}"
                ),
                threshold=50.0,
                current_value=error_rate,
                portfolio_id="paper_trading",
                metadata={
                    "circuit_breaker_open": circuit_breaker_open,
                    "error_rate_pct": error_rate,
                    "affected_operations": affected_operations,
                    "recovery_steps_link": "docs/runbooks/redis-failure-response.md",
                    "estimated_recovery_time_minutes": 10,
                },
            )

        return None

    def detect_paper_sync_divergence(
        self,
        redis_state: dict[str, Any],
        memory_state: dict[str, Any],
        divergence_threshold_pct: float = 5.0,
    ) -> RiskAlert | None:
        """Detect divergence between Redis and in-memory state.

        Triggers when Redis and in-memory state differ by more than threshold.

        Args:
            redis_state: Current state from Redis (symbol -> position dict)
            memory_state: Current in-memory state (symbol -> position dict)
            divergence_threshold_pct: Percentage threshold for divergence (default 5%)

        Returns:
            RiskAlert if divergence detected, None otherwise
        """
        from .types import AlertSeverity, AlertType, RiskAlert

        # Calculate divergence for each position
        divergences = []
        affected_positions = []

        all_keys = set(redis_state.keys()) | set(memory_state.keys())

        for key in all_keys:
            redis_pos = redis_state.get(key, {})
            memory_pos = memory_state.get(key, {})

            # Extract notional values for comparison
            redis_value = (
                redis_pos.get("notional_value", 0.0)
                if isinstance(redis_pos, dict)
                else redis_pos
            )
            memory_value = (
                memory_pos.get("notional_value", 0.0)
                if isinstance(memory_pos, dict)
                else memory_pos
            )

            if isinstance(redis_value, (int, float)) and isinstance(
                memory_value, (int, float)
            ):
                # Calculate percentage difference relative to Redis value
                if redis_value != 0:
                    diff_pct = abs(redis_value - memory_value) / abs(redis_value) * 100
                else:
                    diff_pct = (
                        abs(memory_value) * 100
                    )  # If Redis is 0, any memory value is 100% diff

                if diff_pct > divergence_threshold_pct:
                    divergences.append(
                        {
                            "key": key,
                            "redis_value": redis_value,
                            "memory_value": memory_value,
                            "divergence_pct": diff_pct,
                        }
                    )
                    affected_positions.append(key)

        if divergences:
            max_divergence: float = max(d["divergence_pct"] for d in divergences)

            return RiskAlert(
                alert_type=AlertType.PAPER_SYNC_DIVERGENCE,
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"PAPER SYNC DIVERGENCE: {len(divergences)} positions diverged "
                    f"by >{divergence_threshold_pct}%. Max divergence: {max_divergence:.1f}%"
                ),
                threshold=divergence_threshold_pct,
                current_value=max_divergence,
                portfolio_id="paper_trading",
                metadata={
                    "divergence_count": len(divergences),
                    "max_divergence_pct": max_divergence,
                    "affected_positions": affected_positions,
                    "divergence_details": divergences,
                    "recovery_steps_link": "docs/runbooks/paper-trading-operations.md",
                },
            )

        return None

    def detect_validation_failure_rate(
        self,
        total_orders: int,
        failed_orders: int,
        failure_reasons: dict[str, int],
        window_minutes: int = 5,
        threshold_pct: float = 10.0,
    ) -> RiskAlert | None:
        """Detect high order validation failure rate.

        Triggers when >10% of orders fail validation in a 5-minute window.

        Args:
            total_orders: Total number of orders in the window
            failed_orders: Number of orders that failed validation
            failure_reasons: Dict mapping failure reason to count
            window_minutes: Time window for the calculation (default 5)
            threshold_pct: Failure rate threshold percentage (default 10%)

        Returns:
            RiskAlert if failure rate exceeds threshold, None otherwise
        """
        from .types import AlertSeverity, AlertType, RiskAlert

        if total_orders == 0:
            return None

        failure_rate = (failed_orders / total_orders) * 100

        if failure_rate > threshold_pct:
            return RiskAlert(
                alert_type=AlertType.VALIDATION_FAILURE_RATE,
                severity=AlertSeverity.WARNING,
                message=(
                    f"VALIDATION FAILURE RATE: {failure_rate:.1f}% of orders failed "
                    f"validation in the last {window_minutes} minutes "
                    f"({failed_orders}/{total_orders})"
                ),
                threshold=threshold_pct,
                current_value=failure_rate,
                portfolio_id="paper_trading",
                metadata={
                    "window_minutes": window_minutes,
                    "total_orders": total_orders,
                    "failed_orders": failed_orders,
                    "failure_rate_pct": failure_rate,
                    "failure_breakdown": failure_reasons,
                    "most_common_reason": (
                        max(failure_reasons.items(), key=lambda x: x[1])[0]
                        if failure_reasons
                        else None
                    ),
                },
            )

        return None
