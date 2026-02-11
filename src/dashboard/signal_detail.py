"""Signal detail breakdown for dashboard display.

Provides detailed breakdown of signal components including confluence scores,
confidence multipliers, stop-loss calculations, position sizing, and risk/reward
ratios for individual signal analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dashboard.key_levels import KeyLevel, KeyLevelsResult
    from portfolio.state_management.tracker import PortfolioTracker
    from portfolio_risk.position_sizing.integration import PositionSizingIntegration
    from signal_generation.models import Signal


@dataclass
class IndicatorContribution:
    """Contribution of a single indicator to the confluence score.

    Attributes:
        indicator_type: Type of indicator (e.g., "rsi", "macd", "bb")
        timeframe: Timeframe of the indicator signal
        direction: Signal direction from this indicator
        strength: Signal strength (0.0-1.0)
        confidence: Indicator confidence (0.0-1.0)
        weight: Applied weight for this indicator/timeframe
        weighted_score: Final weighted contribution score
        raw_value: Raw indicator value
    """

    indicator_type: str
    timeframe: str
    direction: str
    strength: float
    confidence: float
    weight: float
    weighted_score: float
    raw_value: float | None = None

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.strength = max(0.0, min(1.0, self.strength))
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.weight = max(0.0, self.weight)
        self.weighted_score = max(0.0, self.weighted_score)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "indicator_type": self.indicator_type,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strength": round(self.strength, 3),
            "confidence": round(self.confidence, 3),
            "weight": round(self.weight, 3),
            "weighted_score": round(self.weighted_score, 3),
            "raw_value": self.raw_value,
        }


@dataclass
class TimeframeAgreement:
    """Agreement analysis across timeframes.

    Attributes:
        timeframe: Timeframe identifier
        dominant_direction: Dominant direction for this timeframe
        long_weight: Weight of long signals
        short_weight: Weight of short signals
        neutral_weight: Weight of neutral signals
        signal_count: Number of signals in this timeframe
        agrees_with_overall: Whether this timeframe agrees with overall signal
    """

    timeframe: str
    dominant_direction: str
    long_weight: float
    short_weight: float
    neutral_weight: float
    signal_count: int
    agrees_with_overall: bool

    @property
    def total_weight(self) -> float:
        """Get total weight for this timeframe."""
        return self.long_weight + self.short_weight + self.neutral_weight

    @property
    def agreement_ratio(self) -> float:
        """Get agreement ratio (0-1) for dominant direction."""
        total = self.total_weight
        if total == 0:
            return 0.0
        if self.dominant_direction == "long":
            return self.long_weight / total
        elif self.dominant_direction == "short":
            return self.short_weight / total
        else:
            return self.neutral_weight / total

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timeframe": self.timeframe,
            "dominant_direction": self.dominant_direction,
            "long_weight": round(self.long_weight, 3),
            "short_weight": round(self.short_weight, 3),
            "neutral_weight": round(self.neutral_weight, 3),
            "total_weight": round(self.total_weight, 3),
            "signal_count": self.signal_count,
            "agreement_ratio": round(self.agreement_ratio, 3),
            "agrees_with_overall": self.agrees_with_overall,
        }


@dataclass
class ConfluenceBreakdown:
    """Detailed breakdown of confluence score components.

    Attributes:
        base_score: Base confluence score (0-100)
        agreement_ratio: Signal agreement ratio (0-1)
        avg_strength: Average signal strength (0-1)
        avg_confidence: Average signal confidence (0-1)
        diversity_bonus: Timeframe diversity bonus (0-0.1)
        type_bonus: Indicator type diversity bonus (0-0.1)
        indicator_contributions: List of individual indicator contributions
        timeframe_agreements: Agreement analysis per timeframe
    """

    base_score: float
    agreement_ratio: float
    avg_strength: float
    avg_confidence: float
    diversity_bonus: float
    type_bonus: float
    indicator_contributions: list[IndicatorContribution] = field(default_factory=list)
    timeframe_agreements: list[TimeframeAgreement] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.base_score = max(0.0, min(100.0, self.base_score))
        self.agreement_ratio = max(0.0, min(1.0, self.agreement_ratio))
        self.avg_strength = max(0.0, min(1.0, self.avg_strength))
        self.avg_confidence = max(0.0, min(1.0, self.avg_confidence))
        self.diversity_bonus = max(0.0, min(0.1, self.diversity_bonus))
        self.type_bonus = max(0.0, min(0.1, self.type_bonus))

    @property
    def total_contributing_indicators(self) -> int:
        """Get total number of contributing indicators."""
        return len(self.indicator_contributions)

    @property
    def unique_timeframes(self) -> list[str]:
        """Get list of unique timeframes."""
        return list(set(tf.timeframe for tf in self.timeframe_agreements))

    @property
    def unique_indicator_types(self) -> list[str]:
        """Get list of unique indicator types."""
        return list(set(ic.indicator_type for ic in self.indicator_contributions))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "base_score": round(self.base_score, 2),
            "agreement_ratio": round(self.agreement_ratio, 3),
            "avg_strength": round(self.avg_strength, 3),
            "avg_confidence": round(self.avg_confidence, 3),
            "diversity_bonus": round(self.diversity_bonus, 3),
            "type_bonus": round(self.type_bonus, 3),
            "total_contributing_indicators": self.total_contributing_indicators,
            "unique_timeframes": self.unique_timeframes,
            "unique_indicator_types": self.unique_indicator_types,
            "indicator_contributions": [
                ic.to_dict() for ic in self.indicator_contributions
            ],
            "timeframe_agreements": [ta.to_dict() for ta in self.timeframe_agreements],
        }


@dataclass
class ConfidenceMultiplierInfo:
    """Information about the confidence multiplier applied.

    Attributes:
        multiplier: The multiplier value applied (e.g., 1.0, 1.1, 1.2, 1.3, 1.5)
        rationale: Explanation of why multiplier was/wasn't applied
        base_confidence: Confidence before multiplier
        final_confidence: Confidence after multiplier
        agreeing_timeframes: Number of timeframes in agreement
        conflicting_timeframes: Number of conflicting timeframes
    """

    multiplier: float
    rationale: str
    base_confidence: float
    final_confidence: float
    agreeing_timeframes: int
    conflicting_timeframes: int

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.multiplier = max(1.0, min(1.5, self.multiplier))
        self.base_confidence = max(0.0, min(1.0, self.base_confidence))
        self.final_confidence = max(0.0, min(1.0, self.final_confidence))
        self.agreeing_timeframes = max(0, self.agreeing_timeframes)
        self.conflicting_timeframes = max(0, self.conflicting_timeframes)

    @property
    def was_applied(self) -> bool:
        """Check if multiplier was actually applied (> 1.0)."""
        return self.multiplier > 1.0

    @property
    def confidence_boost_percent(self) -> float:
        """Get confidence boost as percentage."""
        return (self.multiplier - 1.0) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "multiplier": round(self.multiplier, 2),
            "rationale": self.rationale,
            "base_confidence": round(self.base_confidence, 3),
            "final_confidence": round(self.final_confidence, 3),
            "was_applied": self.was_applied,
            "confidence_boost_percent": round(self.confidence_boost_percent, 1),
            "agreeing_timeframes": self.agreeing_timeframes,
            "conflicting_timeframes": self.conflicting_timeframes,
        }


@dataclass
class StopLossInfo:
    """Calculated stop-loss information.

    Attributes:
        stop_loss_price: Recommended stop-loss price level
        stop_loss_percent: Stop-loss distance as percentage from entry
        based_on: What the stop-loss is based on (key_level, volatility, hybrid)
        key_level_used: Key level used for calculation (if applicable)
        atr_value: ATR value used (if volatility-based)
        atr_multiplier: ATR multiplier used
    """

    stop_loss_price: float
    stop_loss_percent: float
    based_on: str
    key_level_used: KeyLevel | None = None
    atr_value: float | None = None
    atr_multiplier: float = 2.0

    def __post_init__(self) -> None:
        """Validate values."""
        self.stop_loss_percent = max(0.0, self.stop_loss_percent)
        if self.atr_value is not None:
            self.atr_value = max(0.0, self.atr_value)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "stop_loss_price": round(self.stop_loss_price, 2),
            "stop_loss_percent": round(self.stop_loss_percent, 2),
            "based_on": self.based_on,
            "key_level_used": (
                self.key_level_used.to_dict() if self.key_level_used else None
            ),
            "atr_value": round(self.atr_value, 2) if self.atr_value else None,
            "atr_multiplier": self.atr_multiplier,
        }


@dataclass
class PositionSizeInfo:
    """Calculated position size information.

    Attributes:
        position_size: Position size in base currency
        position_value_usd: Position value in USD
        risk_amount_usd: Risk amount in USD
        risk_percent: Risk as percentage of portfolio
        portfolio_value_usd: Portfolio value used for calculation
        leverage_used: Leverage multiplier (if any)
    """

    position_size: float
    position_value_usd: float
    risk_amount_usd: float
    risk_percent: float
    portfolio_value_usd: float
    leverage_used: float = 1.0

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.position_size = max(0.0, self.position_size)
        self.position_value_usd = max(0.0, self.position_value_usd)
        self.risk_amount_usd = max(0.0, self.risk_amount_usd)
        self.risk_percent = max(0.0, min(100.0, self.risk_percent))
        self.portfolio_value_usd = max(0.0, self.portfolio_value_usd)
        self.leverage_used = max(1.0, self.leverage_used)

    @property
    def margin_required_usd(self) -> float:
        """Calculate margin required with leverage."""
        return self.position_value_usd / self.leverage_used

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "position_size": round(self.position_size, 6),
            "position_value_usd": round(self.position_value_usd, 2),
            "risk_amount_usd": round(self.risk_amount_usd, 2),
            "risk_percent": round(self.risk_percent, 2),
            "portfolio_value_usd": round(self.portfolio_value_usd, 2),
            "leverage_used": self.leverage_used,
            "margin_required_usd": round(self.margin_required_usd, 2),
        }


@dataclass
class RiskRewardInfo:
    """Risk/Reward ratio calculation.

    Attributes:
        risk_reward_ratio: Risk/Reward ratio (e.g., 1:2 = 2.0)
        risk_amount: Risk amount in price terms
        reward_amount: Reward amount in price terms
        take_profit_price: Recommended take-profit price
        take_profit_percent: Take-profit distance as percentage
        risk_percent: Risk as percentage from entry
    """

    risk_reward_ratio: float
    risk_amount: float
    reward_amount: float
    take_profit_price: float
    take_profit_percent: float
    risk_percent: float

    def __post_init__(self) -> None:
        """Validate values."""
        self.risk_reward_ratio = max(0.0, self.risk_reward_ratio)
        self.risk_amount = max(0.0, self.risk_amount)
        self.reward_amount = max(0.0, self.reward_amount)
        self.take_profit_percent = max(0.0, self.take_profit_percent)
        self.risk_percent = max(0.0, self.risk_percent)

    @property
    def is_favorable(self) -> bool:
        """Check if R:R ratio is favorable (>= 1.5)."""
        return self.risk_reward_ratio >= 1.5

    @property
    def ratio_text(self) -> str:
        """Get ratio as text (e.g., '1:2.5')."""
        return f"1:{self.risk_reward_ratio:.1f}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "ratio_text": self.ratio_text,
            "risk_amount": round(self.risk_amount, 2),
            "reward_amount": round(self.reward_amount, 2),
            "take_profit_price": round(self.take_profit_price, 2),
            "take_profit_percent": round(self.take_profit_percent, 2),
            "risk_percent": round(self.risk_percent, 2),
            "is_favorable": self.is_favorable,
        }


@dataclass
class SignalDetail:
    """Complete signal detail breakdown for dashboard display.

    Attributes:
        signal_id: Unique signal identifier
        token: Trading pair
        direction: Signal direction (long/short/neutral)
        entry_price: Entry price for the signal
        confidence: Final confidence score (0-100)
        base_score: Base confluence score (0-100)
        timeframe: Primary timeframe
        timestamp: Signal generation timestamp
        confluence_breakdown: Detailed confluence score breakdown
        confidence_multiplier: Confidence multiplier information
        stop_loss: Calculated stop-loss information
        position_size: Calculated position size information
        risk_reward: Risk/reward ratio information
        metadata: Additional metadata
    """

    signal_id: str
    token: str
    direction: str
    entry_price: float
    confidence: float
    base_score: float
    timeframe: str
    timestamp: str
    confluence_breakdown: ConfluenceBreakdown
    confidence_multiplier: ConfidenceMultiplierInfo
    stop_loss: StopLossInfo
    position_size: PositionSizeInfo
    risk_reward: RiskRewardInfo
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.confidence = max(0.0, min(100.0, self.confidence))
        self.base_score = max(0.0, min(100.0, self.base_score))
        self.entry_price = max(0.0, self.entry_price)

    @property
    def is_long(self) -> bool:
        """Check if signal is long."""
        return self.direction.lower() == "long"

    @property
    def is_short(self) -> bool:
        """Check if signal is short."""
        return self.direction.lower() == "short"

    @property
    def emoji(self) -> str:
        """Get emoji for signal direction."""
        if self.is_long:
            return "🟢"
        elif self.is_short:
            return "🔴"
        else:
            return "⚪"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 2),
            "confidence": round(self.confidence, 1),
            "base_score": round(self.base_score, 1),
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "emoji": self.emoji,
            "confluence_breakdown": self.confluence_breakdown.to_dict(),
            "confidence_multiplier": self.confidence_multiplier.to_dict(),
            "stop_loss": self.stop_loss.to_dict(),
            "position_size": self.position_size.to_dict(),
            "risk_reward": self.risk_reward.to_dict(),
            "metadata": self.metadata,
        }

    def to_discord_message(self) -> str:
        """Format signal detail as Discord message."""
        lines = [
            f"{self.emoji} **{self.direction.upper()} Signal Detail: {self.token}**",
            f"Entry: ${self.entry_price:,.2f} | Confidence: **{self.confidence:.1f}%**",
            "",
            "**Confluence Breakdown:**",
            f"  Base Score: {self.confluence_breakdown.base_score:.1f}/100",
            f"  Contributing Indicators: "
            f"{self.confluence_breakdown.total_contributing_indicators}",
            f"  Timeframes: {', '.join(self.confluence_breakdown.unique_timeframes)}",
            "",
            "**Confidence Multiplier:**",
            f"  Multiplier: {self.confidence_multiplier.multiplier:.1f}x",
            f"  Rationale: {self.confidence_multiplier.rationale}",
            "",
            "**Risk Management:**",
            f"  Stop-Loss: ${self.stop_loss.stop_loss_price:,.2f} "
            f"({self.stop_loss.stop_loss_percent:.2f}%)",
            f"  Position Size: {self.position_size.position_size:.4f} "
            f"({self.position_size.risk_percent:.1f}% risk)",
            f"  Risk/Reward: {self.risk_reward.ratio_text}",
        ]
        return "\n".join(lines)


class SignalDetailBuilder:
    """Builder for creating detailed signal breakdowns.

    Constructs comprehensive signal detail views including:
    - Confluence score component breakdown
    - Confidence multiplier analysis
    - Stop-loss calculation using key levels and volatility
    - Position size calculation using risk management rules
    - Risk/reward ratio calculation
    """

    # Default risk parameters
    DEFAULT_RISK_PERCENT = 1.0  # 1% portfolio risk per trade
    DEFAULT_ATR_MULTIPLIER = 2.0
    DEFAULT_LEVERAGE = 1.0
    DEFAULT_RR_TARGET = 2.0  # Target 1:2 risk/reward

    def __init__(
        self,
        risk_percent: float = DEFAULT_RISK_PERCENT,
        atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
        leverage: float = DEFAULT_LEVERAGE,
        portfolio_tracker: PortfolioTracker | None = None,
        sizing_integration: PositionSizingIntegration | None = None,
    ):
        """Initialize builder.

        Args:
            risk_percent: Portfolio risk percentage per trade (default: 1.0)
            atr_multiplier: ATR multiplier for stop-loss (default: 2.0)
            leverage: Default leverage multiplier (default: 1.0)
            portfolio_tracker: Optional portfolio tracker for state integration
            sizing_integration: Optional position sizing integration instance
        """
        self.risk_percent = risk_percent
        self.atr_multiplier = atr_multiplier
        self.leverage = leverage
        self.portfolio_tracker = portfolio_tracker

        # Initialize or use provided sizing integration
        if sizing_integration:
            self.sizing_integration = sizing_integration
            if portfolio_tracker:
                self.sizing_integration.set_portfolio_tracker(portfolio_tracker)
        elif portfolio_tracker:
            from portfolio_risk.position_sizing.integration import (
                PositionSizingIntegration,
            )

            self.sizing_integration = PositionSizingIntegration(
                portfolio_tracker=portfolio_tracker,
            )
        else:
            self.sizing_integration = None

    def build(
        self,
        signal: Signal,
        entry_price: float,
        key_levels: KeyLevelsResult | None = None,
        atr_value: float | None = None,
        portfolio_value_usd: float = 10000.0,
    ) -> SignalDetail:
        """Build complete signal detail breakdown.

        Args:
            signal: The signal to analyze
            entry_price: Entry price for the trade
            key_levels: Key levels result for stop-loss calculation
            atr_value: ATR value for volatility-based stop-loss
            portfolio_value_usd: Portfolio value for position sizing

        Returns:
            SignalDetail with complete breakdown
        """
        # Build confluence breakdown
        confluence_breakdown = self._build_confluence_breakdown(signal)

        # Build confidence multiplier info
        confidence_multiplier = self._build_confidence_multiplier(signal)

        # Calculate stop-loss
        stop_loss = self._calculate_stop_loss(
            signal, entry_price, key_levels, atr_value
        )

        # Calculate position size using integration if available
        if self.sizing_integration:
            position_size = self._calculate_position_size_with_integration(
                signal, entry_price, stop_loss.stop_loss_price
            )
        else:
            # Fallback to basic calculation
            position_size = self._calculate_position_size(
                entry_price, stop_loss.stop_loss_price, portfolio_value_usd
            )

        # Calculate risk/reward
        risk_reward = self._calculate_risk_reward(
            signal, entry_price, stop_loss, key_levels
        )

        return SignalDetail(
            signal_id=signal.signal_id,
            token=signal.token,
            direction=signal.direction.value,
            entry_price=entry_price,
            confidence=signal.confidence * 100,  # Convert to percentage
            base_score=signal.base_score,
            timeframe=signal.timeframe,
            timestamp=signal.timestamp.isoformat(),
            confluence_breakdown=confluence_breakdown,
            confidence_multiplier=confidence_multiplier,
            stop_loss=stop_loss,
            position_size=position_size,
            risk_reward=risk_reward,
            metadata=signal.metadata,
        )

    def _build_confluence_breakdown(self, signal: Signal) -> ConfluenceBreakdown:
        """Build confluence score breakdown from signal.

        Args:
            signal: Signal with signal_breakdown data

        Returns:
            ConfluenceBreakdown with detailed components
        """
        signal_breakdown = signal.signal_breakdown or {}
        contributing_factors = signal.contributing_factors or []

        # Extract score components from metadata if available
        metadata = signal.metadata or {}
        score_components = metadata.get("score_components", {})

        # Build indicator contributions
        indicator_contributions: list[IndicatorContribution] = []
        for factor in contributing_factors:
            contribution = IndicatorContribution(
                indicator_type=factor.get("indicator", "unknown"),
                timeframe=factor.get("timeframe", "unknown"),
                direction=factor.get("direction", "neutral"),
                strength=factor.get("strength", 0.0),
                confidence=factor.get("confidence", 0.0),
                weight=factor.get("weight", 0.0),
                weighted_score=factor.get("weighted_score", 0.0),
                raw_value=factor.get("raw_value"),
            )
            indicator_contributions.append(contribution)

        # Sort by weighted score (descending)
        indicator_contributions.sort(key=lambda x: x.weighted_score, reverse=True)

        # Build timeframe agreements from signal_breakdown
        timeframe_agreements: list[TimeframeAgreement] = []
        by_timeframe = signal_breakdown.get("by_timeframe", {})

        for timeframe, data in by_timeframe.items():
            directions = data.get("directions", [])
            long_count = directions.count("SignalDirection.LONG")
            short_count = directions.count("SignalDirection.SHORT")
            neutral_count = directions.count("SignalDirection.NEUTRAL")

            # Determine dominant direction
            if long_count > short_count and long_count > neutral_count:
                dominant = "long"
            elif short_count > long_count and short_count > neutral_count:
                dominant = "short"
            else:
                dominant = "neutral"

            # Check agreement with overall signal direction
            agrees = dominant == signal.direction.value

            agreement = TimeframeAgreement(
                timeframe=timeframe,
                dominant_direction=dominant,
                long_weight=float(long_count),
                short_weight=float(short_count),
                neutral_weight=float(neutral_count),
                signal_count=data.get("count", 0),
                agrees_with_overall=agrees,
            )
            timeframe_agreements.append(agreement)

        # Sort by timeframe (shorter first)
        timeframe_order = {"1m": 0, "5m": 1, "15m": 2, "1h": 3, "4h": 4, "1d": 5}
        timeframe_agreements.sort(key=lambda x: timeframe_order.get(x.timeframe, 99))

        return ConfluenceBreakdown(
            base_score=signal.base_score,
            agreement_ratio=score_components.get("agreement_ratio", 0.5),
            avg_strength=score_components.get("avg_strength", 0.5),
            avg_confidence=score_components.get("avg_confidence", 0.5),
            diversity_bonus=score_components.get("diversity_bonus", 0.0),
            type_bonus=score_components.get("type_bonus", 0.0),
            indicator_contributions=indicator_contributions,
            timeframe_agreements=timeframe_agreements,
        )

    def _build_confidence_multiplier(self, signal: Signal) -> ConfidenceMultiplierInfo:
        """Build confidence multiplier information from signal.

        Args:
            signal: Signal with multiplier data

        Returns:
            ConfidenceMultiplierInfo with multiplier details
        """
        metadata = signal.metadata or {}

        # Get multiplier from metadata or signal
        multiplier = metadata.get("multiplier_applied", 1.0)
        if multiplier is None:
            multiplier = 1.0

        rationale = metadata.get("multiplier_rationale", "No multiplier applied")
        base_confidence = metadata.get(
            "base_confidence_before_multiplier", signal.confidence
        )

        # Calculate agreeing/conflicting timeframes from signal_breakdown
        signal_breakdown = signal.signal_breakdown or {}
        by_timeframe = signal_breakdown.get("by_timeframe", {})

        agreeing = 0
        conflicting = 0
        overall_direction = signal.direction.value

        for _timeframe, data in by_timeframe.items():
            directions = data.get("directions", [])
            long_count = directions.count("SignalDirection.LONG")
            short_count = directions.count("SignalDirection.SHORT")
            neutral_count = directions.count("SignalDirection.NEUTRAL")

            if long_count > short_count and long_count > neutral_count:
                tf_direction = "long"
            elif short_count > long_count and short_count > neutral_count:
                tf_direction = "short"
            else:
                tf_direction = "neutral"

            if tf_direction == overall_direction and tf_direction != "neutral":
                agreeing += 1
            elif tf_direction != overall_direction and tf_direction != "neutral":
                conflicting += 1

        return ConfidenceMultiplierInfo(
            multiplier=multiplier,
            rationale=rationale,
            base_confidence=base_confidence,
            final_confidence=signal.confidence,
            agreeing_timeframes=agreeing,
            conflicting_timeframes=conflicting,
        )

    def _calculate_stop_loss(
        self,
        signal: Signal,
        entry_price: float,
        key_levels: KeyLevelsResult | None,
        atr_value: float | None,
    ) -> StopLossInfo:
        """Calculate stop-loss level.

        Uses key levels if available, otherwise falls back to ATR-based calculation.

        Args:
            signal: Signal direction info
            entry_price: Entry price
            key_levels: Key levels for support/resistance
            atr_value: ATR value for volatility-based stop

        Returns:
            StopLossInfo with calculated stop-loss
        """
        is_long = signal.direction.value == "long"

        # Try to use key levels first
        if key_levels:
            if is_long and key_levels.nearest_support:
                stop_price = (
                    key_levels.nearest_support.price * 0.995
                )  # 0.5% below support
                stop_percent = abs(entry_price - stop_price) / entry_price * 100
                return StopLossInfo(
                    stop_loss_price=stop_price,
                    stop_loss_percent=stop_percent,
                    based_on="key_level",
                    key_level_used=key_levels.nearest_support,
                )
            elif not is_long and key_levels.nearest_resistance:
                stop_price = (
                    key_levels.nearest_resistance.price * 1.005
                )  # 0.5% above resistance
                stop_percent = abs(entry_price - stop_price) / entry_price * 100
                return StopLossInfo(
                    stop_loss_price=stop_price,
                    stop_loss_percent=stop_percent,
                    based_on="key_level",
                    key_level_used=key_levels.nearest_resistance,
                )

        # Fall back to ATR-based calculation
        if atr_value and atr_value > 0:
            atr_distance = atr_value * self.atr_multiplier
            if is_long:
                stop_price = entry_price - atr_distance
            else:
                stop_price = entry_price + atr_distance
            stop_percent = atr_distance / entry_price * 100
            return StopLossInfo(
                stop_loss_price=stop_price,
                stop_loss_percent=stop_percent,
                based_on="volatility",
                atr_value=atr_value,
                atr_multiplier=self.atr_multiplier,
            )

        # Final fallback: fixed percentage (2%)
        fallback_percent = 2.0
        if is_long:
            stop_price = entry_price * (1 - fallback_percent / 100)
        else:
            stop_price = entry_price * (1 + fallback_percent / 100)

        return StopLossInfo(
            stop_loss_price=stop_price,
            stop_loss_percent=fallback_percent,
            based_on="fixed_percentage",
        )

    def _calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        portfolio_value_usd: float,
    ) -> PositionSizeInfo:
        """Calculate position size using risk management rules.

        Uses the 1% portfolio risk rule: position size is calculated so that
        if stop-loss is hit, the loss equals the risk percentage of portfolio.

        Args:
            entry_price: Entry price
            stop_loss_price: Stop-loss price
            portfolio_value_usd: Total portfolio value

        Returns:
            PositionSizeInfo with calculated position size
        """
        # Calculate risk amount in USD
        risk_amount_usd = portfolio_value_usd * (self.risk_percent / 100)

        # Calculate price risk (distance to stop-loss)
        price_risk = abs(entry_price - stop_loss_price)

        if price_risk == 0:
            # Avoid division by zero - use minimal position
            position_size = 0.0
            position_value = 0.0
        else:
            # Position size = Risk Amount / Price Risk
            position_size = risk_amount_usd / price_risk
            position_value = position_size * entry_price

        return PositionSizeInfo(
            position_size=position_size,
            position_value_usd=position_value,
            risk_amount_usd=risk_amount_usd,
            risk_percent=self.risk_percent,
            portfolio_value_usd=portfolio_value_usd,
            leverage_used=self.leverage,
        )

    def _calculate_position_size_with_integration(
        self,
        signal: Signal,
        entry_price: float,
        stop_loss_price: float,
    ) -> PositionSizeInfo:
        """Calculate position size using PositionSizingIntegration.

        Uses the integrated position sizing engine that factors in
        current portfolio exposure and risk limits.

        Args:
            signal: Trading signal
            entry_price: Entry price
            stop_loss_price: Stop-loss price

        Returns:
            PositionSizeInfo with calculated position size
        """
        if not self.sizing_integration:
            raise ValueError("Sizing integration not available")

        # Calculate sizing using integration
        sizing = self.sizing_integration.calculate_sizing_for_signal(
            signal=signal,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            method=None,  # Use default method
            risk_percentage=self.risk_percent,
            use_portfolio_state=True,
        )

        return PositionSizeInfo(
            position_size=sizing.position_size,
            position_value_usd=sizing.notional_value,
            risk_amount_usd=sizing.risk_amount_usd,
            risk_percent=sizing.risk_percent,
            portfolio_value_usd=sizing.total_equity,
            leverage_used=sizing.leverage_used,
        )

    def _calculate_risk_reward(
        self,
        signal: Signal,
        entry_price: float,
        stop_loss: StopLossInfo,
        key_levels: KeyLevelsResult | None,
    ) -> RiskRewardInfo:
        """Calculate risk/reward ratio.

        Args:
            signal: Signal direction info
            entry_price: Entry price
            stop_loss: Stop-loss information
            key_levels: Key levels for take-profit targets

        Returns:
            RiskRewardInfo with R:R ratio
        """
        is_long = signal.direction.value == "long"
        risk_amount = abs(entry_price - stop_loss.stop_loss_price)
        risk_percent = risk_amount / entry_price * 100

        # Determine take-profit target
        if key_levels:
            if is_long and key_levels.nearest_resistance:
                take_profit = key_levels.nearest_resistance.price
            elif not is_long and key_levels.nearest_support:
                take_profit = key_levels.nearest_support.price
            else:
                # Default to 2:1 R:R
                take_profit = (
                    entry_price + (risk_amount * 2)
                    if is_long
                    else entry_price - (risk_amount * 2)
                )
        else:
            # Default to 2:1 R:R
            take_profit = (
                entry_price + (risk_amount * 2)
                if is_long
                else entry_price - (risk_amount * 2)
            )

        reward_amount = abs(take_profit - entry_price)
        take_profit_percent = reward_amount / entry_price * 100

        # Calculate R:R ratio
        rr_ratio = 0.0 if risk_amount == 0 else reward_amount / risk_amount

        return RiskRewardInfo(
            risk_reward_ratio=rr_ratio,
            risk_amount=risk_amount,
            reward_amount=reward_amount,
            take_profit_price=take_profit,
            take_profit_percent=take_profit_percent,
            risk_percent=risk_percent,
        )

    def with_risk_params(
        self,
        risk_percent: float | None = None,
        atr_multiplier: float | None = None,
        leverage: float | None = None,
    ) -> SignalDetailBuilder:
        """Create new builder with modified risk parameters.

        Args:
            risk_percent: New risk percentage
            atr_multiplier: New ATR multiplier
            leverage: New leverage multiplier

        Returns:
            New SignalDetailBuilder with updated parameters
        """
        return SignalDetailBuilder(
            risk_percent=(
                risk_percent if risk_percent is not None else self.risk_percent
            ),
            atr_multiplier=(
                atr_multiplier if atr_multiplier is not None else self.atr_multiplier
            ),
            leverage=leverage if leverage is not None else self.leverage,
            portfolio_tracker=self.portfolio_tracker,
            sizing_integration=self.sizing_integration,
        )
