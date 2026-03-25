"""Layer 1: Individual Signal Scorer for ICT signals.

This module implements Layer 1 of the two-layer scoring system. Each ICT signal
(CVD, FVG, Order Block) is scored individually to produce:
- Signal strength (0.0 - 1.0)
- Direction (bullish/bearish/neutral)
- Confidence (0.0 - 1.0)
- Metadata (timeframe, mitigation status, etc.)

The scorer takes raw signal data from CVD calculator, FVG detector, and
Order Block detector and normalizes them into a common Layer1Score format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.cvd.cvd_calculator import CVDResult
    from market_analysis.fvg.fvg_detector import FVGDetectionResult
    from market_analysis.order_block.ob_detector import OBDetectionResult


class Layer1SignalDirection(str, Enum):
    """Direction of a Layer 1 signal."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

    def to_confluence_direction(self) -> SignalDirection:
        """Convert to SignalDirection enum for confluence scoring.

        Returns:
            Corresponding SignalDirection value
        """
        from market_analysis.confluence.signal_aggregator import SignalDirection

        mapping = {
            Layer1SignalDirection.BULLISH: SignalDirection.LONG,
            Layer1SignalDirection.BEARISH: SignalDirection.SHORT,
            Layer1SignalDirection.NEUTRAL: SignalDirection.NEUTRAL,
        }
        return mapping[self]


@dataclass
class Layer1Score:
    """Individual signal score from Layer 1 scoring.

    Attributes:
        signal_type: Type of ICT signal (cvd, fvg, order_block)
        direction: Signal direction (bullish/bearish/neutral)
        strength: Signal strength (0.0-1.0)
        confidence: Confidence in the signal (0.0-1.0)
        timeframe: Timeframe of the signal
        metadata: Additional signal-specific data
        raw_data: Reference to original signal data
    """

    signal_type: str
    direction: Layer1SignalDirection
    strength: float
    confidence: float
    timeframe: str
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_data: Any = field(default=None)

    def __post_init__(self) -> None:
        """Validate and clamp values."""
        self.strength = max(0.0, min(1.0, self.strength))
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def weighted_score(self) -> float:
        """Calculate weighted score combining strength and confidence.

        Returns:
            Combined weighted score (0.0-1.0)
        """
        direction_multiplier = (
            1.0 if self.direction != Layer1SignalDirection.NEUTRAL else 0.5
        )
        return self.strength * self.confidence * direction_multiplier

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the score
        """
        return {
            "signal_type": self.signal_type,
            "direction": self.direction.value,
            "strength": round(self.strength, 3),
            "confidence": round(self.confidence, 3),
            "timeframe": self.timeframe,
            "weighted_score": round(self.weighted_score, 3),
            "metadata": self.metadata,
        }


class Layer1SignalScorer:
    """Scorer for individual ICT signals (Layer 1).

    This scorer normalizes raw ICT signals (CVD, FVG, Order Block) into
    a common Layer1Score format suitable for Layer 2 confluence aggregation.
    """

    def __init__(self, min_confidence_threshold: float = 0.3):
        """Initialize Layer 1 scorer.

        Args:
            min_confidence_threshold: Minimum confidence to consider signal valid
        """
        self.min_confidence_threshold = min_confidence_threshold

    def score_cvd(
        self,
        cvd_result: CVDResult,
        timeframe: str,
        price_data: list[float] | None = None,
    ) -> Layer1Score | None:
        """Score a CVD signal.

        Args:
            cvd_result: CVD calculation result
            timeframe: Timeframe of the signal
            price_data: Optional price data for divergence detection

        Returns:
            Layer1Score or None if insufficient data
        """
        if not cvd_result.cvd_values or len(cvd_result.cvd_values) < 2:
            return None

        # Get current CVD and previous for direction
        current_cvd = cvd_result.cvd_values[-1]
        prev_cvd = cvd_result.cvd_values[-2] if len(cvd_result.cvd_values) >= 2 else 0

        # Determine direction based on CVD slope
        cvd_change = current_cvd - prev_cvd
        if cvd_change > 0:
            direction = Layer1SignalDirection.BULLISH
        elif cvd_change < 0:
            direction = Layer1SignalDirection.BEARISH
        else:
            direction = Layer1SignalDirection.NEUTRAL

        # Calculate strength based on:
        # 1. Magnitude of CVD change relative to net volume
        # 2. Whether there's divergence with price (if price_data provided)
        net_volume = cvd_result.net_volume if cvd_result.net_volume != 0 else 1e-10
        strength = min(1.0, abs(cvd_change) / abs(net_volume) * 10)

        # Calculate confidence
        # More trades = higher confidence
        trade_count_factor = min(1.0, cvd_result.trade_count / 100)
        # Net volume direction agreement
        net_direction = 1.0 if cvd_result.net_volume * cvd_change > 0 else 0.5
        confidence = trade_count_factor * 0.4 + net_direction * 0.6
        confidence = min(1.0, confidence)

        # Check for divergence if price data available
        divergence_bonus = 0.0
        if price_data and len(price_data) >= 2:
            price_change = price_data[-1] - price_data[-2]
            if cvd_change > 0 and price_change < 0:
                divergence_bonus = 0.2  # Bullish divergence
            elif cvd_change < 0 and price_change > 0:
                divergence_bonus = 0.2  # Bearish divergence
            confidence = min(1.0, confidence + divergence_bonus)

        if confidence < self.min_confidence_threshold:
            return None

        return Layer1Score(
            signal_type="cvd",
            direction=direction,
            strength=strength,
            confidence=confidence,
            timeframe=timeframe,
            metadata={
                "cvd_change": cvd_change,
                "net_volume": cvd_result.net_volume,
                "trade_count": cvd_result.trade_count,
                "buy_volume": cvd_result.buy_volume,
                "sell_volume": cvd_result.sell_volume,
                "divergence_detected": divergence_bonus > 0,
            },
            raw_data=cvd_result,
        )

    def score_fvg(
        self,
        fvg_result: FVGDetectionResult,
        current_price: float | None = None,
        timeframe: str = "1H",
    ) -> Layer1Score | None:
        """Score an FVG signal.

        Args:
            fvg_result: FVG detection result
            current_price: Optional current price for mitigation check
            timeframe: Timeframe of the signal

        Returns:
            Layer1Score or None if no FVG detected
        """
        if fvg_result.fvg is None:
            return None

        fvg = fvg_result.fvg

        # Map FVG direction to Layer1 direction
        from market_analysis.fvg.fvg_detector import FVGDirection

        if fvg.direction == FVGDirection.BULLISH:
            direction = Layer1SignalDirection.BULLISH
        else:
            direction = Layer1SignalDirection.BEARISH

        # Calculate strength based on:
        # 1. FVG zone size relative to price
        # 2. Mitigation status
        zone_size = fvg.high - fvg.low
        avg_price = (fvg.high + fvg.low) / 2
        size_ratio = zone_size / avg_price if avg_price > 0 else 0.0
        strength = min(1.0, size_ratio * 100)  # Scale appropriately

        # Adjust strength based on mitigation status
        from market_analysis.fvg.fvg_detector import FVGMitigation

        mitigation_multiplier = {
            FVGMitigation.NONE: 1.0,
            FVGMitigation.WICK: 0.8,
            FVGMitigation.CLOSE: 0.5,
            FVGMitigation.FULL: 0.2,
        }
        strength *= mitigation_multiplier.get(fvg.mitigation, 1.0)

        # Calculate confidence based on:
        # 1. CE50 reached (higher confidence if price has retraced 50%)
        # 2. Regime at formation
        ce50_bonus = 0.15 if fvg.ce50_reached else 0.0
        regime_bonus = 0.1 if fvg.regime_at_formation else 0.0
        confidence = 0.6 + ce50_bonus + regime_bonus
        confidence = min(1.0, confidence)

        if confidence < self.min_confidence_threshold:
            return None

        return Layer1Score(
            signal_type="fvg",
            direction=direction,
            strength=strength,
            confidence=confidence,
            timeframe=timeframe,
            metadata={
                "fvg_direction": fvg.direction.value,
                "mitigation": fvg.mitigation.value,
                "ce50_reached": fvg.ce50_reached,
                "zone_high": fvg.high,
                "zone_low": fvg.low,
                "zone_size": zone_size,
                "midpoint": fvg.midpoint,
                "regime_at_formation": (
                    str(fvg.regime_at_formation) if fvg.regime_at_formation else None
                ),
            },
            raw_data=fvg,
        )

    def score_order_block(
        self,
        ob_result: OBDetectionResult,
        timeframe: str = "1H",
    ) -> Layer1Score | None:
        """Score an Order Block signal.

        Args:
            ob_result: Order Block detection result
            timeframe: Timeframe of the signal

        Returns:
            Layer1Score or None if no OB detected
        """
        if ob_result is None:
            return None

        # Map OB polarity to Layer1 direction
        from market_analysis.order_block.ob_detector import OBPolaridade

        if ob_result.polarity == OBPolaridade.BULLISH:
            direction = Layer1SignalDirection.BULLISH
        else:
            direction = Layer1SignalDirection.BEARISH

        # Use OB's strength_score directly (already calculated by detector)
        strength = ob_result.strength_score

        # Calculate confidence based on:
        # 1. Volume confirmation
        # 2. Strength score
        volume_bonus = 0.15 if ob_result.volume_confirmed else 0.0
        confidence = 0.5 + strength * 0.5 + volume_bonus
        confidence = min(1.0, confidence)

        if confidence < self.min_confidence_threshold:
            return None

        return Layer1Score(
            signal_type="order_block",
            direction=direction,
            strength=strength,
            confidence=confidence,
            timeframe=timeframe,
            metadata={
                "ob_polarity": ob_result.polarity.value,
                "volume_confirmed": ob_result.volume_confirmed,
                "anchor_candle_index": ob_result.anchor_candle_index,
                "momentum_candle_index": ob_result.momentum_candle_index,
                "zone_high": ob_result.zone.price_range.high,
                "zone_low": ob_result.zone.price_range.low,
            },
            raw_data=ob_result,
        )

    def score_multiple_fvgs(
        self,
        fvg_results: list[FVGDetectionResult],
        timeframe: str = "1H",
    ) -> list[Layer1Score]:
        """Score multiple FVG signals.

        Args:
            fvg_results: List of FVG detection results
            timeframe: Timeframe of the signals

        Returns:
            List of Layer1Scores (excludes None results)
        """
        scores = []
        for fvg_result in fvg_results:
            score = self.score_fvg(fvg_result, timeframe=timeframe)
            if score is not None:
                scores.append(score)
        return scores

    def score_multiple_order_blocks(
        self,
        ob_results: list[OBDetectionResult],
        timeframe: str = "1H",
    ) -> list[Layer1Score]:
        """Score multiple Order Block signals.

        Args:
            ob_results: List of Order Block detection results
            timeframe: Timeframe of the signals

        Returns:
            List of Layer1Scores
        """
        scores = []
        for ob_result in ob_results:
            score = self.score_order_block(ob_result, timeframe=timeframe)
            if score is not None:
                scores.append(score)
        return scores


# Import SignalDirection for type conversion
from market_analysis.confluence.signal_aggregator import SignalDirection  # noqa: E402
