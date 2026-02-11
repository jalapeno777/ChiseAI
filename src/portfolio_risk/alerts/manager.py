"""Risk alert manager - main orchestrator for risk threshold alerts.

Coordinates detection, suppression, formatting, and sending of risk alerts.
Provides a high-level API for monitoring risk metrics and sending alerts.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portfolio.state_management.risk_calculator import RiskMetrics

    from .sender import RiskAlertSendResult
    from .types import (
        AlertThresholds,
        RiskAlert,
    )

logger = logging.getLogger(__name__)


class RiskAlertManager:
    """Manages risk threshold alerts end-to-end.

    Coordinates:
    - RiskAlertDetector for detecting threshold breaches
    - RiskAlertSender for sending alerts via Discord
    - Alert suppression to prevent spam

    Usage:
        manager = RiskAlertManager()
        await manager.initialize()

        # Process risk metrics and send alerts
        results = await manager.process_risk_metrics(risk_metrics)

        # Check for kill-switch condition
        kill_switch = manager.check_kill_switch(risk_metrics)
        if kill_switch:
            await manager.send_kill_switch_alert(kill_switch)

        await manager.close()
    """

    def __init__(
        self,
        thresholds: AlertThresholds | None = None,
        webhook_url: str | None = None,
    ):
        """Initialize risk alert manager.

        Args:
            thresholds: Alert thresholds (uses defaults if None)
            webhook_url: Discord webhook URL (reads from env if None)
        """
        from .detector import RiskAlertDetector
        from .sender import RiskAlertSender
        from .types import AlertThresholds

        self.thresholds = thresholds or AlertThresholds()
        self.detector = RiskAlertDetector(self.thresholds)
        self.sender = RiskAlertSender(webhook_url=webhook_url)

        logger.debug("RiskAlertManager initialized")

    async def initialize(self) -> bool:
        """Initialize the alert manager and verify Discord connection.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            health = await self.sender.health_check()
            if health["healthy"]:
                logger.info("RiskAlertManager initialized successfully")
                return True
            else:
                logger.warning(
                    f"RiskAlertManager initialized with issues: {health.get('error')}"
                )
                return False
        except Exception as e:
            logger.error(f"RiskAlertManager initialization failed: {e}")
            return False

    async def process_risk_metrics(
        self,
        risk_metrics: RiskMetrics,
        force: bool = False,
    ) -> list[RiskAlertSendResult]:
        """Process risk metrics and send alerts for threshold breaches.

        Args:
            risk_metrics: Calculated risk metrics
            force: Force send even if suppressed

        Returns:
            List of send results for each alert
        """
        # Detect alerts
        alerts = self.detector.detect_alerts(risk_metrics)

        if not alerts:
            logger.debug("No risk alerts detected")
            return []

        logger.info(f"Detected {len(alerts)} risk alerts, sending...")

        # Send alerts
        results = await self.sender.send_alerts(alerts, force=force)

        # Log summary
        sent = sum(1 for r in results if r.success)
        suppressed = sum(1 for r in results if r.suppressed)
        failed = len(results) - sent - suppressed

        logger.info(
            f"Alert processing complete: {sent} sent, "
            f"{suppressed} suppressed, {failed} failed"
        )

        return results

    def check_kill_switch(self, risk_metrics: RiskMetrics) -> RiskAlert | None:
        """Check if kill-switch condition is met.

        Args:
            risk_metrics: Risk metrics to check

        Returns:
            Kill-switch alert if condition met, None otherwise
        """
        return self.detector.detect_kill_switch(risk_metrics)

    async def send_kill_switch_alert(
        self,
        alert: RiskAlert,
    ) -> RiskAlertSendResult:
        """Send kill-switch alert immediately (no suppression).

        Args:
            alert: Kill-switch alert to send

        Returns:
            Send result
        """
        logger.critical(f"KILL SWITCH ALERT: {alert.message}")
        return await self.sender.send_kill_switch_alert(alert)

    def update_thresholds(self, thresholds: AlertThresholds) -> None:
        """Update alert thresholds.

        Args:
            thresholds: New alert thresholds
        """
        self.thresholds = thresholds
        self.detector.update_thresholds(thresholds)
        logger.debug(
            f"Updated thresholds: exposure={thresholds.exposure_threshold_pct}%, "
            f"margin={thresholds.margin_utilization_threshold_pct}%, "
            f"concentration={thresholds.concentration_threshold_pct}%"
        )

    def get_stats(self) -> dict[str, Any]:
        """Get alert manager statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "thresholds": self.thresholds.to_dict(),
            "sender": self.sender.get_suppressor_stats(),
        }

    async def health_check(self) -> dict[str, Any]:
        """Check alert manager health.

        Returns:
            Dictionary with health status
        """
        sender_health = await self.sender.health_check()

        return {
            "healthy": sender_health.get("healthy", False),
            "sender": sender_health,
            "thresholds": self.thresholds.to_dict(),
        }

    async def close(self) -> None:
        """Close alert manager and cleanup resources."""
        await self.sender.close()
        logger.info("RiskAlertManager closed")
