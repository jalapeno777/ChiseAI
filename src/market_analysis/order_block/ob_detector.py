"""Order Block Detector Module.

Detects bullish and bearish order blocks based on ICT methodology.
Order blocks are zones where institutional orders were executed,
appearing as a consolidation candle before a strong directional move.

Bullish OB: Bearish candle(s) before strong bullish momentum
Bearish OB: Bullish candle(s) before strong bearish momentum

Usage:
    from src.market_analysis.order_block import OrderBlockDetector

    detector = OrderBlockDetector()
    order_blocks = detector.detect(candles, regime_classification)
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np

from src.market_analysis.regime import RegimeClassification, UnifiedRegime
from src.market_analysis.safety.lookahead_guard import lookahead_guard
from src.market_analysis.zones import Zone, ZoneType
from src.market_analysis.zones.zone_models import PriceRange


class OBPolaridade(str, Enum):
    """Order block polarity (direction)."""

    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass
class OBDetectionResult:
    """Result of order block detection.

    Attributes:
        polarity: Bullish or bearish order block
        zone: The zone representing the order block
        anchor_candle_index: Index of the anchor candle (pre-move consolidation)
        momentum_candle_index: Index of the momentum candle (strong move after OB)
        strength_score: Strength of the order block (0.0-1.0)
        volume_confirmed: Whether volume confirmed the order block
    """

    polarity: OBPolaridade
    zone: Zone
    anchor_candle_index: int
    momentum_candle_index: int
    strength_score: float
    volume_confirmed: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "polarity": self.polarity.value,
            "zone": self.zone.to_dict(),
            "anchor_candle_index": self.anchor_candle_index,
            "momentum_candle_index": self.momentum_candle_index,
            "strength_score": self.strength_score,
            "volume_confirmed": self.volume_confirmed,
        }


class OrderBlockConfig:
    """Configuration for order block detection.

    Attributes:
        momentum_threshold: Minimum candle body percentage for momentum (default: 0.6)
        min_consolidation_bars: Minimum bars in consolidation (default: 1)
        max_consolidation_bars: Maximum bars in consolidation (default: 5)
        ob_zone_extension_pips: Pips to extend OB zone beyond candle range (default: 5)
        require_volume_confirmation: Whether volume must confirm OB (default: False)
        volume_threshold_multiplier: Volume multiplier vs average for confirmation (default: 1.2)
        regime_filter: Only detect OB in these regimes (default: [TRENDING])
    """

    def __init__(
        self,
        momentum_threshold: float = 0.6,
        min_consolidation_bars: int = 1,
        max_consolidation_bars: int = 5,
        ob_zone_extension_pips: float = 5.0,
        require_volume_confirmation: bool = False,
        volume_threshold_multiplier: float = 1.2,
        regime_filter: list[UnifiedRegime] | None = None,
    ):
        self.momentum_threshold = momentum_threshold
        self.min_consolidation_bars = min_consolidation_bars
        self.max_consolidation_bars = max_consolidation_bars
        self.ob_zone_extension_pips = ob_zone_extension_pips
        self.require_volume_confirmation = require_volume_confirmation
        self.volume_threshold_multiplier = volume_threshold_multiplier
        self.regime_filter = regime_filter or [UnifiedRegime.TRENDING]


class OrderBlockDetector:
    """Detects order blocks using ICT methodology.

    An order block is a consolidation zone where institutional traders
    positioned themselves before a strong directional move.

    Bullish Order Block:
    - Bearish candle(s) in a consolidation
    - Followed by strong bullish momentum candle(s)
    - The consolidation zone becomes a potential support

    Bearish Order Block:
    - Bullish candle(s) in a consolidation
    - Followed by strong bearish momentum candle(s)
    - The consolidation zone becomes a potential resistance

    The detector is regime-gated and can use volume confirmation.
    """

    def __init__(self, config: OrderBlockConfig | None = None):
        """Initialize order block detector.

        Args:
            config: Optional configuration for detection parameters
        """
        self.config = config or OrderBlockConfig()

    @lookahead_guard
    def detect(
        self,
        candles: list,
        regime: RegimeClassification | None = None,
        volume_data: list[float] | None = None,
    ) -> list[OBDetectionResult]:
        """Detect order blocks in the given candles.

        Args:
            candles: List of OHLCV candle data
            regime: Optional regime classification for regime-gating
            volume_data: Optional volume data for volume confirmation

        Returns:
            List of detected order blocks
        """
        results: list[OBDetectionResult] = []

        # Regime gate check
        if regime is not None and regime.regime not in self.config.regime_filter:
            return results

        if len(candles) < 3:
            return results

        # Calculate average volume if needed
        avg_volume: float | None = None
        if self.config.require_volume_confirmation and volume_data:
            avg_volume = float(
                np.mean(volume_data[-20:])
                if len(volume_data) >= 20
                else np.mean(volume_data)
            )

        # Detect bullish OB: bearish candle(s) before bullish momentum
        bullish_obs = self._detect_bullish_ob(candles, volume_data, avg_volume)
        results.extend(bullish_obs)

        # Detect bearish OB: bullish candle(s) before bearish momentum
        bearish_obs = self._detect_bearish_ob(candles, volume_data, avg_volume)
        results.extend(bearish_obs)

        return results

    def _detect_bullish_ob(
        self,
        candles: list,
        volume_data: list[float] | None,
        avg_volume: float | None,
    ) -> list[OBDetectionResult]:
        """Detect bullish order blocks.

        A bullish OB forms when:
        1. There's a bearish candle (or candles in consolidation)
        2. Followed by a strong bullish momentum candle

        Args:
            candles: Candle data
            volume_data: Volume data
            avg_volume: Average volume for confirmation

        Returns:
            List of detected bullish OBs
        """
        results: list[OBDetectionResult] = []
        n = len(candles)

        for i in range(self.config.min_consolidation_bars, n - 1):
            # Check if candles[i] is bearish (anchor candle)
            anchor = candles[i]
            anchor_body_pct = self._get_bearish_body_pct(anchor)

            # Anchor should be bearish
            if anchor_body_pct <= 0:
                continue

            # Look for momentum candle after anchor
            for j in range(i + 1, min(i + self.config.max_consolidation_bars + 1, n)):
                momentum = candles[j]
                momentum_body_pct = self._get_bullish_body_pct(momentum)

                # Momentum should be strongly bullish
                if momentum_body_pct < self.config.momentum_threshold:
                    continue

                # Calculate OB zone (from anchor candle)
                ob_high = max(
                    anchor.high_price,
                    candles[i - 1].high_price if i > 0 else anchor.high_price,
                )
                ob_low = min(
                    anchor.low_price,
                    candles[i - 1].low_price if i > 0 else anchor.low_price,
                )

                # Add extension
                price_range = ob_high - ob_low
                extension = price_range * 0.1  # 10% extension
                ob_high += extension
                ob_low -= extension

                # Volume confirmation
                volume_confirmed = False
                if (
                    self.config.require_volume_confirmation
                    and avg_volume
                    and volume_data
                ):
                    momentum_volume = volume_data[j] if j < len(volume_data) else 0
                    volume_confirmed = (
                        momentum_volume
                        >= avg_volume * self.config.volume_threshold_multiplier
                    )

                # Calculate strength score
                strength = self._calculate_ob_strength(
                    candles, i, j, OBPolaridade.BULLISH, volume_confirmed
                )

                # Create Zone object
                zone = Zone(
                    zone_type=ZoneType.OB,
                    timeframe=getattr(candles[0], "timeframe", "UNKNOWN"),
                    token=getattr(candles[0], "token", "UNKNOWN"),
                    price_range=PriceRange(high=ob_high, low=ob_low),
                    notes=f"Bullish OB detected at candle {i}, momentum at {j}",
                )

                results.append(
                    OBDetectionResult(
                        polarity=OBPolaridade.BULLISH,
                        zone=zone,
                        anchor_candle_index=i,
                        momentum_candle_index=j,
                        strength_score=strength,
                        volume_confirmed=volume_confirmed,
                    )
                )
                break  # Found valid OB, no need to check further

        return results

    def _detect_bearish_ob(
        self,
        candles: list,
        volume_data: list[float] | None,
        avg_volume: float | None,
    ) -> list[OBDetectionResult]:
        """Detect bearish order blocks.

        A bearish OB forms when:
        1. There's a bullish candle (or candles in consolidation)
        2. Followed by a strong bearish momentum candle

        Args:
            candles: Candle data
            volume_data: Volume data
            avg_volume: Average volume for confirmation

        Returns:
            List of detected bearish OBs
        """
        results: list[OBDetectionResult] = []
        n = len(candles)

        for i in range(self.config.min_consolidation_bars, n - 1):
            # Check if candles[i] is bullish (anchor candle)
            anchor = candles[i]
            anchor_body_pct = self._get_bullish_body_pct(anchor)

            # Anchor should be bullish
            if anchor_body_pct <= 0:
                continue

            # Look for momentum candle after anchor
            for j in range(i + 1, min(i + self.config.max_consolidation_bars + 1, n)):
                momentum = candles[j]
                momentum_body_pct = self._get_bearish_body_pct(momentum)

                # Momentum should be strongly bearish
                if momentum_body_pct < self.config.momentum_threshold:
                    continue

                # Calculate OB zone (from anchor candle)
                ob_high = max(
                    anchor.high_price,
                    candles[i - 1].high_price if i > 0 else anchor.high_price,
                )
                ob_low = min(
                    anchor.low_price,
                    candles[i - 1].low_price if i > 0 else anchor.low_price,
                )

                # Add extension
                price_range = ob_high - ob_low
                extension = price_range * 0.1  # 10% extension
                ob_high += extension
                ob_low -= extension

                # Volume confirmation
                volume_confirmed = False
                if (
                    self.config.require_volume_confirmation
                    and avg_volume
                    and volume_data
                ):
                    momentum_volume = volume_data[j] if j < len(volume_data) else 0
                    volume_confirmed = (
                        momentum_volume
                        >= avg_volume * self.config.volume_threshold_multiplier
                    )

                # Calculate strength score
                strength = self._calculate_ob_strength(
                    candles, i, j, OBPolaridade.BEARISH, volume_confirmed
                )

                # Create Zone object
                zone = Zone(
                    zone_type=ZoneType.OB,
                    timeframe=getattr(candles[0], "timeframe", "UNKNOWN"),
                    token=getattr(candles[0], "token", "UNKNOWN"),
                    price_range=PriceRange(high=ob_high, low=ob_low),
                    notes=f"Bearish OB detected at candle {i}, momentum at {j}",
                )

                results.append(
                    OBDetectionResult(
                        polarity=OBPolaridade.BEARISH,
                        zone=zone,
                        anchor_candle_index=i,
                        momentum_candle_index=j,
                        strength_score=strength,
                        volume_confirmed=volume_confirmed,
                    )
                )
                break  # Found valid OB, no need to check further

        return results

    def _get_bearish_body_pct(self, candle) -> float:
        """Get bearish body percentage (0-1).

        Returns 1.0 for a full bearish candle (open > close),
        scaled down for smaller bearish bodies.
        """
        if hasattr(candle, "open_price") and hasattr(candle, "close_price"):
            body = candle.open_price - candle.close_price
            total_range = candle.high_price - candle.low_price
            if total_range > 0:
                return max(0, body / total_range)
        return 0.0

    def _get_bullish_body_pct(self, candle) -> float:
        """Get bullish body percentage (0-1).

        Returns 1.0 for a full bullish candle (close > open),
        scaled down for smaller bullish bodies.
        """
        if hasattr(candle, "open_price") and hasattr(candle, "close_price"):
            body = candle.close_price - candle.open_price
            total_range = candle.high_price - candle.low_price
            if total_range > 0:
                return max(0, body / total_range)
        return 0.0

    def _calculate_ob_strength(
        self,
        candles: list,
        anchor_idx: int,
        momentum_idx: int,
        polarity: OBPolaridade,
        volume_confirmed: bool,
    ) -> float:
        """Calculate order block strength score (0.0-1.0).

        Factors:
        - Momentum candle strength
        - Anchor candle quality
        - Volume confirmation (if enabled)

        Args:
            candles: Candle data
            anchor_idx: Index of anchor candle
            momentum_idx: Index of momentum candle
            polarity: OB polarity
            volume_confirmed: Whether volume confirmed the OB

        Returns:
            Strength score between 0.0 and 1.0
        """
        anchor = candles[anchor_idx]
        momentum = candles[momentum_idx]

        # Calculate anchor quality
        if polarity == OBPolaridade.BULLISH:
            anchor_body = self._get_bearish_body_pct(anchor)
        else:
            anchor_body = self._get_bullish_body_pct(anchor)

        # Calculate momentum strength
        if polarity == OBPolaridade.BULLISH:
            momentum_body = self._get_bullish_body_pct(momentum)
        else:
            momentum_body = self._get_bearish_body_pct(momentum)

        # Base strength from momentum
        strength = momentum_body * 0.6

        # Add anchor contribution
        strength += anchor_body * 0.25

        # Volume bonus
        if self.config.require_volume_confirmation:
            if volume_confirmed:
                strength += 0.15
        else:
            # Without volume requirement, give small bonus
            strength += 0.1

        return min(1.0, max(0.0, strength))


# TODO: Register with indicator_weights.py in EP-ICT-005
# from src.market_analysis.confluence.indicator_weights import register_indicator
# register_indicator("order_block", OrderBlockDetector)
