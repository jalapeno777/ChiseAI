"""Alert message formatter.

Formats trading signal alerts for Discord with proper markdown,
including token, direction, confidence, key levels, and timestamp.

For ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Type of Discord alert."""

    ACTIONABLE = "actionable"  # >= 75% confidence
    WATCHLIST = "watchlist"  # 40-74% confidence
    INFO = "info"  # General information


class AlertFormatter:
    """Formats trading signals as Discord messages.

    Supports different alert types (actionable, watchlist) with
    appropriate formatting and emojis.
    """

    # Emoji mappings
    DIRECTION_EMOJIS = {
        "LONG": "🟢",
        "SHORT": "🔴",
        "NEUTRAL": "⚪",
    }

    ALERT_TYPE_EMOJIS = {
        AlertType.ACTIONABLE: "🎯",
        AlertType.WATCHLIST: "👀",
        AlertType.INFO: "ℹ️",
    }

    CONFIDENCE_EMOJIS = {
        "high": "🔥",  # >= 75%
        "medium": "⚡",  # 40-74%
        "low": "💤",  # < 40%
    }

    def __init__(self) -> None:
        """Initialize alert formatter."""
        pass

    def format_signal(
        self,
        signal: Signal,
        alert_type: AlertType | None = None,
        include_key_levels: bool = True,
        include_factors: bool = True,
    ) -> dict[str, Any]:
        """Format a signal as a Discord message.

        Args:
            signal: The trading signal to format
            alert_type: Override alert type (auto-detected if None)
            include_key_levels: Whether to include key levels section
            include_factors: Whether to include contributing factors

        Returns:
            Dictionary with 'content' and 'embeds' for Discord API
        """
        # Auto-detect alert type if not specified
        if alert_type is None:
            alert_type = self._detect_alert_type(signal)

        # Build embed
        embed = self._build_embed(
            signal, alert_type, include_key_levels, include_factors
        )

        # Build content (notification text)
        content = self._build_content(signal, alert_type)

        return {
            "content": content,
            "embeds": [embed],
        }

    def _detect_alert_type(self, signal: Signal) -> AlertType:
        """Detect alert type from signal confidence.

        Args:
            signal: Trading signal

        Returns:
            Appropriate AlertType
        """
        confidence = signal.confidence

        if confidence >= 0.75:
            return AlertType.ACTIONABLE
        elif confidence >= 0.40:
            return AlertType.WATCHLIST
        else:
            return AlertType.INFO

    def _build_content(self, signal: Signal, alert_type: AlertType) -> str:
        """Build notification content.

        Args:
            signal: Trading signal
            alert_type: Type of alert

        Returns:
            Content string for Discord message
        """
        alert_emoji = self.ALERT_TYPE_EMOJIS.get(alert_type, "📊")
        direction_emoji = self.DIRECTION_EMOJIS.get(signal.direction_str, "📊")

        if alert_type == AlertType.ACTIONABLE:
            return (
                f"{alert_emoji} **ACTIONABLE SIGNAL** {direction_emoji} "
                f"**{signal.token}** - Confidence: {signal.confidence_percent:.1f}%"
            )
        elif alert_type == AlertType.WATCHLIST:
            return (
                f"{alert_emoji} **Watchlist Alert** {direction_emoji} "
                f"**{signal.token}** - Confidence: {signal.confidence_percent:.1f}%"
            )
        else:
            return (
                f"{alert_emoji} Signal Update: **{signal.token}** "
                f"[{signal.direction_str}] - {signal.confidence_percent:.1f}%"
            )

    def _build_embed(
        self,
        signal: Signal,
        alert_type: AlertType,
        include_key_levels: bool,
        include_factors: bool,
    ) -> dict[str, Any]:
        """Build Discord embed for signal.

        Args:
            signal: Trading signal
            alert_type: Type of alert
            include_key_levels: Whether to include key levels
            include_factors: Whether to include contributing factors

        Returns:
            Discord embed dictionary
        """
        # Determine color based on direction and confidence
        color = self._get_embed_color(signal)

        # Build title
        direction_emoji = self.DIRECTION_EMOJIS.get(signal.direction_str, "📊")
        title = f"{direction_emoji} {signal.direction_str} Signal: {signal.token}"

        # Build description
        confidence_emoji = self._get_confidence_emoji(signal.confidence)
        description = (
            f"{confidence_emoji} **Confidence:** {signal.confidence_percent:.1f}%\n"
            f"📊 **Base Score:** {signal.base_score:.1f}/100\n"
            f"⏱️ **Timeframe:** {signal.timeframe}\n"
            f"⚡ **Latency:** {signal.generation_latency_ms:.1f}ms"
        )

        # Build fields
        fields = []

        if include_key_levels:
            key_levels = self._extract_key_levels(signal)
            if key_levels:
                fields.append(
                    {
                        "name": "🔑 Key Levels",
                        "value": key_levels,
                        "inline": True,
                    }
                )

        if include_factors and signal.contributing_factors:
            factors_text = self._format_contributing_factors(
                signal.contributing_factors
            )
            if factors_text:
                fields.append(
                    {
                        "name": "📈 Contributing Factors",
                        "value": factors_text,
                        "inline": False,
                    }
                )

        # Add signal breakdown if available
        if signal.signal_breakdown:
            breakdown_text = self._format_signal_breakdown(signal.signal_breakdown)
            if breakdown_text:
                fields.append(
                    {
                        "name": "🔍 Signal Breakdown",
                        "value": breakdown_text,
                        "inline": False,
                    }
                )

        # Build footer
        timestamp_str = signal.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        footer_text = f"Signal ID: {signal.signal_id[:8]}... | {timestamp_str}"

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {"text": footer_text},
            "timestamp": signal.timestamp.isoformat(),
        }

        return embed

    def _get_embed_color(self, signal: Signal) -> int:
        """Get embed color based on signal direction and confidence.

        Args:
            signal: Trading signal

        Returns:
            Integer color code for Discord
        """
        # Color codes (Discord uses integer colors)
        colors = {
            "LONG_HIGH": 0x00FF00,  # Bright green
            "LONG_MED": 0x90EE90,  # Light green
            "SHORT_HIGH": 0xFF0000,  # Bright red
            "SHORT_MED": 0xFF6B6B,  # Light red
            "NEUTRAL": 0x808080,  # Gray
            "WATCHLIST": 0xFFA500,  # Orange
        }

        if signal.direction_str == "LONG":
            if signal.confidence >= 0.75:
                return colors["LONG_HIGH"]
            else:
                return colors["LONG_MED"]
        elif signal.direction_str == "SHORT":
            if signal.confidence >= 0.75:
                return colors["SHORT_HIGH"]
            else:
                return colors["SHORT_MED"]
        else:
            if signal.confidence >= 0.40:
                return colors["WATCHLIST"]
            return colors["NEUTRAL"]

    def _get_confidence_emoji(self, confidence: float) -> str:
        """Get emoji for confidence level.

        Args:
            confidence: Confidence value (0.0-1.0)

        Returns:
            Emoji string
        """
        if confidence >= 0.75:
            return self.CONFIDENCE_EMOJIS["high"]
        elif confidence >= 0.40:
            return self.CONFIDENCE_EMOJIS["medium"]
        else:
            return self.CONFIDENCE_EMOJIS["low"]

    def _extract_key_levels(self, signal: Signal) -> str:
        """Extract key levels from signal metadata.

        Args:
            signal: Trading signal

        Returns:
            Formatted key levels string
        """
        levels = []

        # Try to extract from metadata
        metadata = signal.metadata or {}

        # Look for entry price
        if "entry_price" in metadata:
            levels.append(f"Entry: ${metadata['entry_price']:,.2f}")

        # Look for support/resistance from signal breakdown
        breakdown = signal.signal_breakdown or {}

        # Check for price levels in various formats
        if "price_levels" in breakdown:
            price_levels = breakdown["price_levels"]
            if isinstance(price_levels, dict):
                if "support" in price_levels:
                    levels.append(f"Support: ${price_levels['support']:,.2f}")
                if "resistance" in price_levels:
                    levels.append(f"Resistance: ${price_levels['resistance']:,.2f}")

        # Check for Bollinger Bands
        if "bollinger" in breakdown:
            bb = breakdown["bollinger"]
            if isinstance(bb, dict):
                if "upper" in bb:
                    levels.append(f"BB Upper: ${bb['upper']:,.2f}")
                if "lower" in bb:
                    levels.append(f"BB Lower: ${bb['lower']:,.2f}")

        return "\n".join(levels) if levels else "N/A"

    def _format_contributing_factors(self, factors: list[dict[str, Any]]) -> str:
        """Format contributing factors as readable text.

        Args:
            factors: List of contributing factor dictionaries

        Returns:
            Formatted factors string
        """
        if not factors:
            return ""

        formatted = []
        for i, factor in enumerate(factors[:5], 1):  # Limit to top 5
            name = factor.get("name", "Unknown")
            value = factor.get("value", "")
            weight = factor.get("weight", 0)

            if weight:
                formatted.append(f"{i}. **{name}**: {value} (weight: {weight:.2f})")
            else:
                formatted.append(f"{i}. **{name}**: {value}")

        return "\n".join(formatted)

    def _format_signal_breakdown(self, breakdown: dict[str, Any]) -> str:
        """Format signal breakdown as readable text.

        Args:
            breakdown: Signal breakdown dictionary

        Returns:
            Formatted breakdown string
        """
        if not breakdown:
            return ""

        formatted = []

        # Format by timeframe
        for timeframe, data in breakdown.items():
            if isinstance(data, dict):
                score = data.get("score", 0)
                direction = data.get("direction", "neutral")
                formatted.append(f"• **{timeframe}**: {direction} ({score:.1f})")
            else:
                formatted.append(f"• **{timeframe}**: {data}")

        return "\n".join(formatted[:10])  # Limit to 10 items

    def format_simple_message(
        self,
        token: str,
        direction: str,
        confidence: float,
        timestamp: datetime | None = None,
    ) -> str:
        """Format a simple text-only message.

        Args:
            token: Trading pair token
            direction: Signal direction (LONG, SHORT, NEUTRAL)
            confidence: Confidence value (0.0-1.0)
            timestamp: Optional timestamp

        Returns:
            Simple formatted message string
        """
        direction_emoji = self.DIRECTION_EMOJIS.get(direction, "📊")
        confidence_pct = confidence * 100

        ts_str = ""
        if timestamp:
            ts_str = f" | {timestamp.strftime('%H:%M:%S')}"

        return (
            f"{direction_emoji} **{direction} Signal: {token}**\n"
            f"Confidence: **{confidence_pct:.1f}%**{ts_str}"
        )
