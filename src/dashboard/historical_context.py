"""Historical context panel for signal analysis.

Provides the HistoricalContext dataclass and HistoricalContextBuilder class
for retrieving and analyzing similar past signals to give context for
current signal evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_history.tracker import SignalTracker
    from market_analysis.signal_storage.models import SignalDirection


@dataclass
class SimilarSignalSummary:
    """Summary of a single similar signal for display.

    Attributes:
        signal_id: Unique signal identifier
        token: Trading pair token
        direction: Signal direction (LONG/SHORT/NEUTRAL)
        confidence: Confidence level (0.0-1.0)
        entry_price: Entry price at signal time
        exit_price: Exit price (if resolved)
        pnl: Profit/loss amount (if resolved)
        is_win: Whether the signal was profitable
        outcome_type: Type of outcome (tp_hit, sl_hit, etc.)
        duration_hours: Trade duration in hours
        timestamp: Signal generation timestamp
    """

    signal_id: str
    token: str
    direction: str
    confidence: float
    entry_price: float
    timestamp: int
    exit_price: float | None = None
    pnl: float | None = None
    is_win: bool | None = None
    outcome_type: str | None = None
    duration_hours: float | None = None

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.entry_price = max(0.0, self.entry_price)
        if self.exit_price is not None:
            self.exit_price = max(0.0, self.exit_price)

    @property
    def is_resolved(self) -> bool:
        """Check if the signal has been resolved with an outcome."""
        return self.is_win is not None

    @property
    def pnl_pct(self) -> float | None:
        """Calculate PnL percentage relative to entry price."""
        if self.pnl is None or self.entry_price == 0:
            return None
        return (self.pnl / self.entry_price) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "entry_price": round(self.entry_price, 2),
            "timestamp": self.timestamp,
            "exit_price": round(self.exit_price, 2) if self.exit_price else None,
            "pnl": round(self.pnl, 8) if self.pnl else None,
            "pnl_pct": round(self.pnl_pct, 4) if self.pnl_pct else None,
            "is_win": self.is_win,
            "is_resolved": self.is_resolved,
            "outcome_type": self.outcome_type,
            "duration_hours": (
                round(self.duration_hours, 2) if self.duration_hours else None
            ),
        }


@dataclass
class HistoricalContext:
    """Historical context for a signal based on similar past signals.

    Attributes:
        token: Trading pair token
        direction: Signal direction being analyzed
        confidence_range: Confidence range used for similarity matching
        sample_size: Total number of similar signals found
        resolved_count: Number of similar signals with outcomes
        win_rate: Win rate for similar signals (0.0-1.0)
        avg_pnl: Average PnL for similar signals
        max_drawdown: Maximum drawdown experienced in similar setups
        total_pnl: Total PnL across all similar signals
        avg_duration_hours: Average trade duration in hours
        similar_signals: List of individual similar signal summaries
        confidence_bucket: Confidence bucket for grouping
    """

    token: str
    direction: str
    confidence_range: tuple[float, float]
    sample_size: int = 0
    resolved_count: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    max_drawdown: float = 0.0
    total_pnl: float = 0.0
    avg_duration_hours: float = 0.0
    similar_signals: list[SimilarSignalSummary] = field(default_factory=list)
    confidence_bucket: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.win_rate = max(0.0, min(1.0, self.win_rate))
        self.max_drawdown = max(0.0, self.max_drawdown)

    @property
    def win_count(self) -> int:
        """Calculate number of winning signals."""
        if self.resolved_count == 0:
            return 0
        return int(self.win_rate * self.resolved_count)

    @property
    def loss_count(self) -> int:
        """Calculate number of losing signals."""
        return self.resolved_count - self.win_count

    @property
    def has_sufficient_data(self) -> bool:
        """Check if there's sufficient data for reliable context (>= 10 samples)."""
        return self.sample_size >= 10

    @property
    def has_sufficient_resolved(self) -> bool:
        """Check if there's sufficient resolved data (>= 5 resolved)."""
        return self.resolved_count >= 5

    @property
    def reliability_score(self) -> float:
        """Calculate reliability score based on sample size (0.0-1.0).

        Returns a score indicating how reliable the historical context is:
        - 0.0-0.3: Insufficient data (< 10 samples)
        - 0.3-0.6: Limited data (10-20 samples)
        - 0.6-0.8: Moderate data (20-50 samples)
        - 0.8-1.0: Good data (50+ samples)
        """
        if self.sample_size < 10:
            return self.sample_size / 30.0  # 0.0-0.33 for 0-10 samples
        elif self.sample_size < 20:
            return 0.3 + (self.sample_size - 10) / 30.0  # 0.33-0.63 for 10-20
        elif self.sample_size < 50:
            return 0.6 + (self.sample_size - 20) / 100.0  # 0.63-0.9 for 20-50
        else:
            return min(1.0, 0.9 + (self.sample_size - 50) / 500.0)  # 0.9-1.0 for 50+

    @property
    def win_rate_text(self) -> str:
        """Get win rate as formatted text."""
        return f"{self.win_rate:.1%}"

    @property
    def avg_pnl_text(self) -> str:
        """Get average PnL as formatted text."""
        if self.avg_pnl >= 0:
            return f"+{self.avg_pnl:.4f}"
        return f"{self.avg_pnl:.4f}"

    @property
    def max_drawdown_text(self) -> str:
        """Get max drawdown as formatted text."""
        return f"{self.max_drawdown:.2%}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "token": self.token,
            "direction": self.direction,
            "confidence_range": {
                "min": round(self.confidence_range[0], 4),
                "max": round(self.confidence_range[1], 4),
            },
            "confidence_bucket": self.confidence_bucket,
            "sample_size": self.sample_size,
            "resolved_count": self.resolved_count,
            "win_rate": round(self.win_rate, 4),
            "win_rate_text": self.win_rate_text,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "avg_pnl": round(self.avg_pnl, 8),
            "avg_pnl_text": self.avg_pnl_text,
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_text": self.max_drawdown_text,
            "total_pnl": round(self.total_pnl, 8),
            "avg_duration_hours": round(self.avg_duration_hours, 2),
            "has_sufficient_data": self.has_sufficient_data,
            "has_sufficient_resolved": self.has_sufficient_resolved,
            "reliability_score": round(self.reliability_score, 2),
            "similar_signals": [s.to_dict() for s in self.similar_signals],
        }

    def to_discord_message(self) -> str:
        """Format historical context as Discord message."""
        reliability_emoji = (
            "🟢"
            if self.reliability_score >= 0.8
            else "🟡" if self.reliability_score >= 0.5 else "🔴"
        )
        win_emoji = (
            "🟢" if self.win_rate >= 0.6 else "🟡" if self.win_rate >= 0.4 else "🔴"
        )
        pnl_emoji = "🟢" if self.avg_pnl > 0 else "🔴" if self.avg_pnl < 0 else "⚪"

        lines = [
            f"**📊 Historical Context: {self.token} {self.direction}**",
            "",
            f"**Similar Signals:** {self.sample_size} found",
            f"**Confidence Range:** "
            f"{self.confidence_range[0]:.0%} - {self.confidence_range[1]:.0%}",
            f"**Data Reliability:** {reliability_emoji} {self.reliability_score:.0%}",
            "",
            "**Performance Metrics:**",
            f"  {win_emoji} Win Rate: **{self.win_rate_text}** "
            f"({self.win_count}W / {self.loss_count}L)",
            f"  {pnl_emoji} Avg PnL: **{self.avg_pnl_text}**",
            f"  📉 Max Drawdown: {self.max_drawdown_text}",
        ]

        if self.avg_duration_hours > 0:
            lines.append(f"  ⏱️ Avg Duration: {self.avg_duration_hours:.1f}h")

        if not self.has_sufficient_data:
            lines.append("")
            lines.append("⚠️ *Limited historical data - context may be unreliable*")

        return "\n".join(lines)


@dataclass
class HistoricalContextResult:
    """Result of building historical context with multiple confidence ranges.

    Attributes:
        primary_context: Context for the primary confidence range
        broader_context: Context for a broader confidence range (if applicable)
        all_contexts: List of all contexts queried
        timestamp: When the context was built
    """

    primary_context: HistoricalContext | None = None
    broader_context: HistoricalContext | None = None
    all_contexts: list[HistoricalContext] = field(default_factory=list)
    timestamp: int = 0

    @property
    def has_data(self) -> bool:
        """Check if any context has data."""
        return any(ctx.sample_size > 0 for ctx in self.all_contexts)

    @property
    def best_context(self) -> HistoricalContext | None:
        """Get the context with the most reliable data."""
        if not self.all_contexts:
            return None
        return max(self.all_contexts, key=lambda ctx: ctx.reliability_score)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary_context": (
                self.primary_context.to_dict() if self.primary_context else None
            ),
            "broader_context": (
                self.broader_context.to_dict() if self.broader_context else None
            ),
            "all_contexts": [ctx.to_dict() for ctx in self.all_contexts],
            "has_data": self.has_data,
            "timestamp": self.timestamp,
        }


class HistoricalContextBuilder:
    """Builder for creating historical context from similar past signals.

    Queries signal history to find similar signals based on:
    - Same token
    - Same direction (LONG/SHORT)
    - Comparable confidence level (within configurable range)

    Calculates metrics including:
    - Win rate for similar signals
    - Average PnL
    - Maximum drawdown
    - Sample size
    """

    # Default confidence range tolerance (±10%)
    DEFAULT_CONFIDENCE_TOLERANCE = 0.10

    # Minimum signals required for reliable context
    MIN_SIGNALS_FOR_RELIABLE_CONTEXT = 10

    # Default limit for similar signals to retrieve
    DEFAULT_SIGNAL_LIMIT = 500

    def __init__(
        self,
        signal_tracker: SignalTracker,
        confidence_tolerance: float = DEFAULT_CONFIDENCE_TOLERANCE,
    ):
        """Initialize builder.

        Args:
            signal_tracker: SignalTracker instance for querying signal history
            confidence_tolerance: Tolerance for confidence matching (default: 0.10)
        """
        self.signal_tracker = signal_tracker
        self.confidence_tolerance = confidence_tolerance

    async def build(
        self,
        token: str,
        direction: str | SignalDirection,
        confidence: float,
        lookback_days: int = 90,
        limit: int = DEFAULT_SIGNAL_LIMIT,
    ) -> HistoricalContext:
        """Build historical context for a signal.

        Args:
            token: Trading pair token (e.g., "BTC")
            direction: Signal direction ("LONG", "SHORT", or SignalDirection enum)
            confidence: Confidence level (0.0-1.0)
            lookback_days: Number of days to look back (default: 90)
            limit: Maximum number of signals to retrieve

        Returns:
            HistoricalContext with similar signal analysis
        """
        # Normalize direction to string
        if hasattr(direction, "value"):
            direction_str = direction.value
        else:
            direction_str = str(direction).upper()

        # Calculate confidence range
        confidence_range = self._calculate_confidence_range(confidence)

        # Calculate time range
        import time

        end_time = int(time.time() * 1000)
        start_time = end_time - (lookback_days * 24 * 3600 * 1000)

        # Query similar signals
        similar_signals = await self._find_similar_signals(
            token=token,
            direction=direction_str,
            min_confidence=confidence_range[0],
            max_confidence=confidence_range[1],
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        # Calculate metrics
        metrics = self._calculate_metrics(similar_signals)

        # Build context
        context = HistoricalContext(
            token=token,
            direction=direction_str,
            confidence_range=confidence_range,
            sample_size=len(similar_signals),
            resolved_count=metrics["resolved_count"],
            win_rate=metrics["win_rate"],
            avg_pnl=metrics["avg_pnl"],
            max_drawdown=metrics["max_drawdown"],
            total_pnl=metrics["total_pnl"],
            avg_duration_hours=metrics["avg_duration_hours"],
            similar_signals=similar_signals,
            confidence_bucket=self._get_confidence_bucket(confidence),
        )

        return context

    async def build_with_fallback(
        self,
        token: str,
        direction: str | SignalDirection,
        confidence: float,
        lookback_days: int = 90,
        limit: int = DEFAULT_SIGNAL_LIMIT,
    ) -> HistoricalContextResult:
        """Build historical context with fallback to broader ranges.

        If insufficient data is found with the primary confidence range,
        this method will try progressively broader ranges.

        Args:
            token: Trading pair token
            direction: Signal direction
            confidence: Confidence level
            lookback_days: Number of days to look back
            limit: Maximum number of signals to retrieve

        Returns:
            HistoricalContextResult with primary and fallback contexts
        """
        import time

        timestamp = int(time.time() * 1000)

        # Try primary range first
        primary_context = await self.build(
            token=token,
            direction=direction,
            confidence=confidence,
            lookback_days=lookback_days,
            limit=limit,
        )

        all_contexts = [primary_context]
        broader_context: HistoricalContext | None = None

        # If insufficient data, try broader range
        if not primary_context.has_sufficient_data:
            # Try with double the tolerance
            broader_tolerance = self.confidence_tolerance * 2
            broader_range = (
                max(0.0, confidence - broader_tolerance),
                min(1.0, confidence + broader_tolerance),
            )

            end_time = timestamp
            start_time = end_time - (lookback_days * 24 * 3600 * 1000)

            # Normalize direction
            if hasattr(direction, "value"):
                direction_str = direction.value
            else:
                direction_str = str(direction).upper()

            broader_signals = await self._find_similar_signals(
                token=token,
                direction=direction_str,
                min_confidence=broader_range[0],
                max_confidence=broader_range[1],
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )

            broader_metrics = self._calculate_metrics(broader_signals)

            broader_context = HistoricalContext(
                token=token,
                direction=direction_str,
                confidence_range=broader_range,
                sample_size=len(broader_signals),
                resolved_count=broader_metrics["resolved_count"],
                win_rate=broader_metrics["win_rate"],
                avg_pnl=broader_metrics["avg_pnl"],
                max_drawdown=broader_metrics["max_drawdown"],
                total_pnl=broader_metrics["total_pnl"],
                avg_duration_hours=broader_metrics["avg_duration_hours"],
                similar_signals=broader_signals,
                confidence_bucket=self._get_confidence_bucket(confidence),
            )

            all_contexts.append(broader_context)

        return HistoricalContextResult(
            primary_context=primary_context,
            broader_context=broader_context,
            all_contexts=all_contexts,
            timestamp=timestamp,
        )

    def _calculate_confidence_range(self, confidence: float) -> tuple[float, float]:
        """Calculate confidence range for similarity matching.

        Args:
            confidence: Target confidence level

        Returns:
            Tuple of (min_confidence, max_confidence)
        """
        min_conf = max(0.0, confidence - self.confidence_tolerance)
        max_conf = min(1.0, confidence + self.confidence_tolerance)
        return (min_conf, max_conf)

    def _get_confidence_bucket(self, confidence: float) -> str:
        """Get confidence bucket string for the given confidence.

        Args:
            confidence: Confidence level (0.0-1.0)

        Returns:
            Bucket string (e.g., "70-80")
        """
        confidence_pct = int(confidence * 100)
        lower = (confidence_pct // 10) * 10
        upper = lower + 10
        return f"{lower}-{upper}"

    async def _find_similar_signals(
        self,
        token: str,
        direction: str,
        min_confidence: float,
        max_confidence: float,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[SimilarSignalSummary]:
        """Find similar signals matching the criteria.

        Args:
            token: Trading pair token
            direction: Signal direction
            min_confidence: Minimum confidence level
            max_confidence: Maximum confidence level
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
            limit: Maximum number of results

        Returns:
            List of SimilarSignalSummary
        """
        signals_with_outcomes = await self.signal_tracker.get_signal_history(
            token=token,
            direction=direction,
            start_time=start_time,
            end_time=end_time,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            include_outcomes=True,
            limit=limit,
        )

        summaries = []
        for swo in signals_with_outcomes:
            signal = swo.signal
            outcome = swo.outcome

            summary = SimilarSignalSummary(
                signal_id=signal.signal_id,
                token=signal.token,
                direction=signal.direction.value,
                confidence=signal.confidence,
                entry_price=signal.entry_price,
                timestamp=signal.timestamp,
                exit_price=outcome.exit_price if outcome else None,
                pnl=outcome.pnl if outcome else None,
                is_win=outcome.is_win if outcome else None,
                outcome_type=outcome.outcome_type.value if outcome else None,
                duration_hours=outcome.duration_hours if outcome else None,
            )
            summaries.append(summary)

        return summaries

    def _calculate_metrics(self, signals: list[SimilarSignalSummary]) -> dict[str, Any]:
        """Calculate metrics from similar signals.

        Args:
            signals: List of similar signal summaries

        Returns:
            Dictionary with calculated metrics
        """
        resolved = [s for s in signals if s.is_resolved]

        if not resolved:
            return {
                "resolved_count": 0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "max_drawdown": 0.0,
                "total_pnl": 0.0,
                "avg_duration_hours": 0.0,
            }

        wins = [s for s in resolved if s.is_win]

        win_rate = len(wins) / len(resolved) if resolved else 0.0

        total_pnl = sum(s.pnl for s in resolved if s.pnl is not None)
        avg_pnl = total_pnl / len(resolved) if resolved else 0.0

        # Calculate max drawdown from cumulative PnL
        max_drawdown = self._calculate_max_drawdown(resolved)

        # Calculate average duration
        durations = [s.duration_hours for s in resolved if s.duration_hours is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "resolved_count": len(resolved),
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "max_drawdown": max_drawdown,
            "total_pnl": total_pnl,
            "avg_duration_hours": avg_duration,
        }

    def _calculate_max_drawdown(self, signals: list[SimilarSignalSummary]) -> float:
        """Calculate maximum drawdown from a series of trades.

        This calculates the worst peak-to-trough decline in the
        cumulative PnL curve.

        Args:
            signals: List of resolved signals

        Returns:
            Maximum drawdown as a decimal (0.0-1.0)
        """
        if not signals:
            return 0.0

        # Sort by timestamp
        sorted_signals = sorted(signals, key=lambda s: s.timestamp)

        # Calculate cumulative PnL
        cumulative_pnl = 0.0
        peak_pnl = 0.0
        max_dd = 0.0

        for signal in sorted_signals:
            if signal.pnl is not None:
                cumulative_pnl += signal.pnl

                if cumulative_pnl > peak_pnl:
                    peak_pnl = cumulative_pnl

                if peak_pnl > 0:
                    drawdown = (peak_pnl - cumulative_pnl) / peak_pnl
                    max_dd = max(max_dd, drawdown)

        return max_dd

    def with_tolerance(self, tolerance: float) -> HistoricalContextBuilder:
        """Create new builder with different confidence tolerance.

        Args:
            tolerance: New confidence tolerance

        Returns:
            New HistoricalContextBuilder with updated tolerance
        """
        return HistoricalContextBuilder(
            signal_tracker=self.signal_tracker,
            confidence_tolerance=tolerance,
        )
