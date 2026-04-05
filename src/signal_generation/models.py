"""Signal models and data structures.

Defines the core signal dataclasses and enums used throughout
the signal generation module.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


def _safe_float(value: float, default: float = 0.0) -> float:
    """Safely convert a value to float, handling NaN and None.

    Args:
        value: The value to convert
        default: Default value if conversion fails or value is NaN

    Returns:
        Safe float value in range [0.0, 1.0] or default
    """
    if value is None:
        return default
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            logger.warning(
                f"Invalid confidence value {value!r} detected, defaulting to {default}"
            )
            return default
        return result
    except (TypeError, ValueError):
        logger.warning(f"Could not convert {value!r} to float, defaulting to {default}")
        return default


class SignalStatus(Enum):
    """Status of a generated signal."""

    ACTIONABLE = "actionable"  # Meets 75% threshold - ready for trading
    LOGGED_ONLY = "logged_only"  # Below threshold - logged but not actionable
    RATE_LIMITED = "rate_limited"  # Actionable but rate-limited
    STALE_DATA = "stale_data"  # Data freshness check failed
    ERROR = "error"  # Error during generation


class SignalDirection(Enum):
    """Direction of a trading signal."""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    """A generated trading signal.

    Attributes:
        token: Trading pair/token (e.g., "BTC/USDT")
        direction: Signal direction (LONG, SHORT, NEUTRAL)
        confidence: Final confidence score (0.0-1.0)
        base_score: Base confluence score (0-100)
        timestamp: Signal generation timestamp (UTC)
        status: Signal status (actionable, logged_only, etc.)
        timeframe: Primary timeframe for the signal
        contributing_factors: List of factors that contributed
        signal_breakdown: Breakdown by indicator/timeframe
        metadata: Additional signal metadata
        signal_id: Unique signal identifier (UUID)
        generation_latency_ms: Time taken to generate signal (ms)
        stop_loss: Stop-loss price level (optional until calculated)
        stop_loss_method: Method used to calculate stop-loss
        stop_loss_rationale: Explanation of stop-loss selection
        trailing_stop: Trailing stop price level (if applicable)
        trailing_stop_enabled: Whether trailing stop is recommended
        risk_reward_ratio: Risk:reward ratio for the signal
        take_profit: Take-profit price level (optional, calculated from key levels or R:R)
    """

    token: str
    direction: SignalDirection
    confidence: float
    base_score: float
    timestamp: datetime
    status: SignalStatus
    timeframe: str
    contributing_factors: list[dict[str, Any]] = field(default_factory=list)
    signal_breakdown: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    signal_id: str = ""
    generation_latency_ms: float = 0.0
    stop_loss: float | None = None
    stop_loss_method: str | None = None
    stop_loss_rationale: str | None = None
    trailing_stop: float | None = None
    trailing_stop_enabled: bool = False
    risk_reward_ratio: float = 0.0
    take_profit: float | None = None

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        # Safely handle NaN/inf confidence values
        self.confidence = _safe_float(self.confidence, default=0.0)
        self.confidence = max(0.0, min(1.0, self.confidence))

        # Safely handle NaN/inf base_score values
        self.base_score = _safe_float(self.base_score, default=0.0)
        self.base_score = max(0.0, min(100.0, self.base_score))

        # Generate UUID if not provided
        if not self.signal_id:
            import uuid

            self.signal_id = str(uuid.uuid4())

    @property
    def is_actionable(self) -> bool:
        """Check if signal is actionable (meets 75% threshold).

        Guards against:
        - Zero confidence (should never be actionable)
        - NaN confidence (should never be actionable)
        - Missing or invalid confidence data
        """
        # Re-check confidence is valid (defense in depth after __post_init__)
        if not isinstance(self.confidence, float) or self.confidence <= 0.0:
            return False
        return self.status == SignalStatus.ACTIONABLE and self.confidence >= 0.75

    @property
    def confidence_percent(self) -> float:
        """Get confidence as percentage (0-100)."""
        return self.confidence * 100

    @property
    def direction_str(self) -> str:
        """Get direction as uppercase string."""
        return self.direction.value.upper()

    def to_dict(self) -> dict[str, Any]:
        """Convert signal to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 4),
            "confidence_percent": round(self.confidence_percent, 2),
            "base_score": round(self.base_score, 2),
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "timeframe": self.timeframe,
            "is_actionable": self.is_actionable,
            "contributing_factors": self.contributing_factors,
            "signal_breakdown": self.signal_breakdown,
            "metadata": self.metadata,
            "generation_latency_ms": round(self.generation_latency_ms, 3),
            "stop_loss": round(self.stop_loss, 2) if self.stop_loss else None,
            "stop_loss_method": self.stop_loss_method,
            "stop_loss_rationale": self.stop_loss_rationale,
            "trailing_stop": (
                round(self.trailing_stop, 2) if self.trailing_stop else None
            ),
            "trailing_stop_enabled": self.trailing_stop_enabled,
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "take_profit": round(self.take_profit, 2) if self.take_profit else None,
        }

    def to_discord_message(self) -> str:
        """Format signal as Discord message."""
        emoji = "🟢" if self.direction == SignalDirection.LONG else "🔴"
        if self.direction == SignalDirection.NEUTRAL:
            emoji = "⚪"

        # Base message
        message = (
            f"{emoji} **{self.direction_str} Signal: {self.token}**\n"
            f"Confidence: **{self.confidence_percent:.1f}%** | "
            f"Score: {self.base_score:.1f}/100\n"
            f"Timeframe: {self.timeframe} | "
            f"Latency: {self.generation_latency_ms:.1f}ms"
        )

        # Add stop-loss information if available
        if self.stop_loss is not None:
            message += f"\n🛑 Stop-Loss: **${self.stop_loss:,.2f}**"
            if self.stop_loss_method:
                message += f" ({self.stop_loss_method})"
            if self.risk_reward_ratio > 0:
                message += f" | R:R **{self.risk_reward_ratio:.2f}**"

        # Add trailing stop if enabled
        if self.trailing_stop_enabled and self.trailing_stop is not None:
            message += f"\n🔄 Trailing Stop: ${self.trailing_stop:,.2f}"

        # Add take-profit if available
        if self.take_profit is not None:
            message += f"\n🎯 Take-Profit: **${self.take_profit:,.2f}**"

        return message

    def to_dashboard_payload(self) -> dict[str, Any]:
        """Format signal for dashboard display."""
        return {
            "id": self.signal_id,
            "token": self.token,
            "direction": self.direction.value,
            "confidence": self.confidence,
            "score": self.base_score,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "timeframe": self.timeframe,
            "factors": self.contributing_factors[:5],  # Top 5 factors
            "latency_ms": self.generation_latency_ms,
            "stop_loss": self.stop_loss,
            "stop_loss_method": self.stop_loss_method,
            "stop_loss_rationale": self.stop_loss_rationale,
            "trailing_stop": self.trailing_stop,
            "trailing_stop_enabled": self.trailing_stop_enabled,
            "risk_reward_ratio": self.risk_reward_ratio,
            "take_profit": self.take_profit,
        }
