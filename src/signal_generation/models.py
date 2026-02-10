"""Signal models and data structures.

Defines the core signal dataclasses and enums used throughout
the signal generation module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SignalStatus(Enum):
    """Status of a generated signal."""

    ACTIONABLE = "actionable"  # Meets 75% threshold - ready for trading
    LOGGED_ONLY = "logged_only"  # Below threshold - logged but not actionable
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

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.base_score = max(0.0, min(100.0, self.base_score))

        # Generate UUID if not provided
        if not self.signal_id:
            import uuid

            self.signal_id = str(uuid.uuid4())

    @property
    def is_actionable(self) -> bool:
        """Check if signal is actionable (meets 75% threshold)."""
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
        }

    def to_discord_message(self) -> str:
        """Format signal as Discord message."""
        emoji = "🟢" if self.direction == SignalDirection.LONG else "🔴"
        if self.direction == SignalDirection.NEUTRAL:
            emoji = "⚪"

        return (
            f"{emoji} **{self.direction_str} Signal: {self.token}**\n"
            f"Confidence: **{self.confidence_percent:.1f}%** | "
            f"Score: {self.base_score:.1f}/100\n"
            f"Timeframe: {self.timeframe} | "
            f"Latency: {self.generation_latency_ms:.1f}ms"
        )

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
        }
