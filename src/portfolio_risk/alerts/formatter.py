"""Alert formatter for risk threshold alerts.

Formats risk alerts as Discord messages with proper markdown,
emojis, and embeds for different alert types and severities.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import RiskAlert

from .types import AlertSeverity, AlertType

logger = logging.getLogger(__name__)


class RiskAlertFormatter:
    """Formats risk alerts as Discord messages.

    Supports different alert types (exposure, margin, concentration, kill_switch)
    with appropriate formatting, emojis, and severity-based styling.
    """

    # Emoji mappings
    ALERT_TYPE_EMOJIS: dict[AlertType, str] = {
        AlertType.EXPOSURE: "📊",
        AlertType.MARGIN_UTILIZATION: "💰",
        AlertType.CONCENTRATION: "🎯",
        AlertType.KILL_SWITCH: "🚨",
        AlertType.POSITION_COUNT: "📋",
        # Paper trading specific alerts (ST-PAPER-008)
        AlertType.REDIS_FAILURE: "🔴",
        AlertType.PAPER_SYNC_DIVERGENCE: "⚠️",
        AlertType.VALIDATION_FAILURE_RATE: "📉",
    }

    SEVERITY_EMOJIS: dict[AlertSeverity, str] = {
        AlertSeverity.INFO: "ℹ️",
        AlertSeverity.WARNING: "⚠️",
        AlertSeverity.CRITICAL: "🔴",
        AlertSeverity.EMERGENCY: "🚨",
    }

    SEVERITY_COLORS: dict[AlertSeverity, int] = {
        AlertSeverity.INFO: 0x3498DB,  # Blue
        AlertSeverity.WARNING: 0xF39C12,  # Orange
        AlertSeverity.CRITICAL: 0xE74C3C,  # Red
        AlertSeverity.EMERGENCY: 0x8E44AD,  # Purple
    }

    def __init__(self) -> None:
        """Initialize risk alert formatter."""
        pass

    def format_alert(self, alert: RiskAlert) -> dict[str, Any]:
        """Format a risk alert as a Discord message.

        Args:
            alert: Risk alert to format

        Returns:
            Dictionary with 'content' and 'embeds' for Discord API
        """
        # Build notification content
        content = self._build_content(alert)

        # Build embed
        embed = self._build_embed(alert)

        return {
            "content": content,
            "embeds": [embed],
        }

    def _build_content(self, alert: RiskAlert) -> str:
        """Build notification content.

        Args:
            alert: Risk alert

        Returns:
            Content string for Discord message
        """
        type_emoji = self.ALERT_TYPE_EMOJIS.get(alert.alert_type, "📊")
        severity_emoji = self.SEVERITY_EMOJIS.get(alert.severity, "⚠️")

        if alert.alert_type.value == "kill_switch":
            return (
                f"{severity_emoji} **KILL SWITCH ACTIVATED** {type_emoji}\n"
                f"Portfolio: `{alert.portfolio_id}`"
            )
        elif alert.severity.value == "critical":
            return (
                f"{severity_emoji} **CRITICAL RISK ALERT** {type_emoji}\n"
                f"Portfolio: `{alert.portfolio_id}`"
            )
        elif alert.severity.value == "warning":
            return (
                f"{severity_emoji} **Risk Alert** {type_emoji}\n"
                f"Portfolio: `{alert.portfolio_id}`"
            )
        else:
            return (
                f"{severity_emoji} Risk Update {type_emoji}\n"
                f"Portfolio: `{alert.portfolio_id}`"
            )

    def _build_embed(self, alert: RiskAlert) -> dict[str, Any]:
        """Build Discord embed for risk alert.

        Args:
            alert: Risk alert

        Returns:
            Discord embed dictionary
        """
        # Get color based on severity
        color = self.SEVERITY_COLORS.get(alert.severity, 0x95A5A6)

        # Build title
        type_emoji = self.ALERT_TYPE_EMOJIS.get(alert.alert_type, "📊")
        title = f"{type_emoji} {self._format_alert_type(alert.alert_type)} Alert"

        # Build description
        description = f"**{alert.message}**"

        # Build fields
        fields = [
            {
                "name": "Threshold",
                "value": f"{alert.threshold:.2f}%",
                "inline": True,
            },
            {
                "name": "Current Value",
                "value": f"{alert.current_value:.2f}%",
                "inline": True,
            },
            {
                "name": "Severity",
                "value": alert.severity.value.upper(),
                "inline": True,
            },
        ]

        # Add breach percentage if applicable
        if alert.current_value > alert.threshold:
            breach_pct = (
                (alert.current_value - alert.threshold) / alert.threshold
            ) * 100
            fields.append(
                {
                    "name": "Breach Amount",
                    "value": f"+{breach_pct:.1f}% over threshold",
                    "inline": False,
                }
            )

        # Build footer
        timestamp_str = alert.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        footer_text = f"Alert Type: {alert.alert_type.value} | {timestamp_str}"

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {"text": footer_text},
            "timestamp": alert.timestamp.isoformat(),
        }

        return embed

    def _format_alert_type(self, alert_type: AlertType) -> str:
        """Format alert type for display.

        Args:
            alert_type: Alert type

        Returns:
            Formatted string
        """
        type_names: dict[AlertType, str] = {
            AlertType.EXPOSURE: "Exposure",
            AlertType.MARGIN_UTILIZATION: "Margin Utilization",
            AlertType.CONCENTRATION: "Concentration",
            AlertType.KILL_SWITCH: "Kill Switch",
            AlertType.POSITION_COUNT: "Position Count",
            # Paper trading specific alerts (ST-PAPER-008)
            AlertType.REDIS_FAILURE: "Redis Failure",
            AlertType.PAPER_SYNC_DIVERGENCE: "Paper Sync Divergence",
            AlertType.VALIDATION_FAILURE_RATE: "Validation Failure Rate",
        }
        return type_names.get(alert_type, "Risk")

    def format_simple_message(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        threshold: float,
        current_value: float,
    ) -> str:
        """Format a simple text-only message.

        Args:
            alert_type: Type of alert
            severity: Alert severity
            message: Alert message
            threshold: Threshold value
            current_value: Current value

        Returns:
            Simple formatted message string
        """
        type_emoji = self.ALERT_TYPE_EMOJIS.get(alert_type, "📊")
        severity_emoji = self.SEVERITY_EMOJIS.get(severity, "⚠️")

        return (
            f"{severity_emoji} {type_emoji} **{self._format_alert_type(alert_type)}**\n"
            f"{message}\n"
            f"Threshold: {threshold:.2f}% | Current: {current_value:.2f}%"
        )
