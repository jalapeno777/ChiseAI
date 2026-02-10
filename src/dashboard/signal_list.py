"""Active signal list builder for pre-market briefing.

Builds a list of active signals meeting the 75% confidence threshold
for dashboard display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal


@dataclass
class ActiveSignal:
    """An active signal for dashboard display.

    Attributes:
        signal_id: Unique signal identifier
        token: Trading pair
        direction: Signal direction (long/short)
        confidence: Confidence score (0-100)
        base_score: Base confluence score (0-100)
        timeframe: Primary timeframe
        timestamp: Signal generation timestamp
        contributing_factors: Top contributing factors
        status: Signal status
    """

    signal_id: str
    token: str
    direction: str
    confidence: float
    base_score: float
    timeframe: str
    timestamp: datetime
    contributing_factors: list[dict[str, Any]] = field(default_factory=list)
    status: str = "active"

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.confidence = max(0.0, min(100.0, self.confidence))
        self.base_score = max(0.0, min(100.0, self.base_score))

    @property
    def is_high_confidence(self) -> bool:
        """Check if signal meets 75% threshold."""
        return self.confidence >= 75.0

    @property
    def emoji(self) -> str:
        """Get emoji for signal direction."""
        return (
            "🟢"
            if self.direction.lower() == "long"
            else "🔴"
            if self.direction.lower() == "short"
            else "⚪"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction,
            "confidence": round(self.confidence, 1),
            "base_score": round(self.base_score, 1),
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "contributing_factors": self.contributing_factors[:3],  # Top 3
            "status": self.status,
            "is_high_confidence": self.is_high_confidence,
            "emoji": self.emoji,
        }


@dataclass
class SignalListResult:
    """Result of building active signal list.

    Attributes:
        timestamp: When the list was built
        signals: List of active signals
        high_confidence_count: Number of signals >= 75%
        long_count: Number of long signals
        short_count: Number of short signals
        tokens_covered: List of tokens with active signals
    """

    timestamp: datetime
    signals: list[ActiveSignal] = field(default_factory=list)
    high_confidence_count: int = 0
    long_count: int = 0
    short_count: int = 0
    tokens_covered: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "signals": [s.to_dict() for s in self.signals],
            "high_confidence_count": self.high_confidence_count,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "tokens_covered": self.tokens_covered,
            "total_signals": len(self.signals),
        }


class SignalListBuilder:
    """Builder for active signal lists.

    Filters and formats signals meeting the 75% confidence threshold
    for dashboard display. Sorts by confidence and provides summary
    statistics.
    """

    def __init__(self, confidence_threshold: float = 75.0):
        """Initialize builder.

        Args:
            confidence_threshold: Minimum confidence threshold (default: 75.0)
        """
        self.confidence_threshold = confidence_threshold

    def build(
        self,
        signals: list["Signal"],
        max_signals: int = 20,
    ) -> SignalListResult:
        """Build active signal list from generated signals.

        Args:
            signals: List of generated signals
            max_signals: Maximum number of signals to include

        Returns:
            SignalListResult with filtered and sorted signals
        """
        timestamp = datetime.now(UTC)

        # Filter to actionable signals meeting threshold
        actionable_signals = [
            s
            for s in signals
            if s.is_actionable and s.confidence * 100 >= self.confidence_threshold
        ]

        # Convert to ActiveSignal format
        active_signals = [self._convert_signal(s) for s in actionable_signals]

        # Sort by confidence (descending)
        active_signals.sort(key=lambda x: x.confidence, reverse=True)

        # Limit to max_signals
        active_signals = active_signals[:max_signals]

        # Calculate statistics
        high_confidence = sum(1 for s in active_signals if s.is_high_confidence)
        long_count = sum(1 for s in active_signals if s.direction.lower() == "long")
        short_count = sum(1 for s in active_signals if s.direction.lower() == "short")
        tokens = list(set(s.token for s in active_signals))

        return SignalListResult(
            timestamp=timestamp,
            signals=active_signals,
            high_confidence_count=high_confidence,
            long_count=long_count,
            short_count=short_count,
            tokens_covered=tokens,
        )

    def build_from_tokens(
        self,
        token_signals_map: dict[str, list["Signal"]],
        max_signals: int = 20,
    ) -> SignalListResult:
        """Build signal list from token-signal map.

        Args:
            token_signals_map: Map of token -> list of signals
            max_signals: Maximum number of signals to include

        Returns:
            SignalListResult with filtered and sorted signals
        """
        all_signals: list["Signal"] = []
        for signals in token_signals_map.values():
            all_signals.extend(signals)

        return self.build(all_signals, max_signals)

    def _convert_signal(self, signal: "Signal") -> ActiveSignal:
        """Convert Signal to ActiveSignal.

        Args:
            signal: Signal to convert

        Returns:
            ActiveSignal for dashboard
        """
        # Extract top contributing factors
        factors = signal.contributing_factors[:3] if signal.contributing_factors else []

        return ActiveSignal(
            signal_id=signal.signal_id,
            token=signal.token,
            direction=signal.direction.value,
            confidence=signal.confidence * 100,  # Convert to percentage
            base_score=signal.base_score,
            timeframe=signal.timeframe,
            timestamp=signal.timestamp,
            contributing_factors=factors,
            status=signal.status.value,
        )

    def filter_by_token(
        self,
        result: SignalListResult,
        token: str,
    ) -> SignalListResult:
        """Filter signal list to single token.

        Args:
            result: Original signal list result
            token: Token to filter by

        Returns:
            Filtered SignalListResult
        """
        filtered = [s for s in result.signals if s.token == token]

        return SignalListResult(
            timestamp=result.timestamp,
            signals=filtered,
            high_confidence_count=sum(1 for s in filtered if s.is_high_confidence),
            long_count=sum(1 for s in filtered if s.direction.lower() == "long"),
            short_count=sum(1 for s in filtered if s.direction.lower() == "short"),
            tokens_covered=[token] if filtered else [],
        )

    def get_summary_text(self, result: SignalListResult) -> str:
        """Generate human-readable summary text.

        Args:
            result: Signal list result

        Returns:
            Summary text
        """
        lines = [
            f"Active Signals: {len(result.signals)}",
            f"  High Confidence (≥75%): {result.high_confidence_count}",
            f"  Long: {result.long_count} | Short: {result.short_count}",
            f"  Tokens: {', '.join(result.tokens_covered[:5])}",
        ]

        if len(result.tokens_covered) > 5:
            lines[-1] += f" (+{len(result.tokens_covered) - 5} more)"

        return "\n".join(lines)
