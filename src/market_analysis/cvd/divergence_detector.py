"""Divergence detector for CVD vs price analysis.

Detects when price action diverges from volume flow, signaling potential
reversals or exhaustion points.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DivergenceType(Enum):
    """Type of divergence detected."""

    BULLISH = "bullish"  # Price down, CVD up (potential bottom)
    BEARISH = "bearish"  # Price up, CVD down (potential top)
    HIDDEN_BULLISH = "hidden_bullish"  # Price higher high, CVD lower high
    HIDDEN_BEARISH = "hidden_bearish"  # Price lower low, CVD higher low


@dataclass
class Divergence:
    """Detected divergence between CVD and price.

    Attributes:
        divergence_type: Type of divergence
        price_index: Index in price series where divergence occurs
        cvd_index: Index in CVD series where divergence occurs
        price_value: Price at divergence point
        cvd_value: CVD value at divergence point
        timestamp: Timestamp of divergence
        strength: Confidence score 0-1
    """

    divergence_type: DivergenceType
    price_index: int
    cvd_index: int
    price_value: float
    cvd_value: float
    timestamp: datetime
    strength: float

    def __post_init__(self) -> None:
        """Validate divergence values."""
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"Strength must be in [0, 1], got {self.strength}")


class DivergenceDetector:
    """Detects divergences between CVD and price action.

    Divergence detection methodology:
    1. Identify swing highs/lows in both price and CVD
    2. Compare directional changes between the two
    3. Classify as regular or hidden divergence
    """

    def __init__(self, min_swing_size: float = 0.002, lookback: int = 5):
        """Initialize divergence detector.

        Args:
            min_swing_size: Minimum price change to qualify as swing (default 0.2%)
            lookback: Number of bars to look back for swing detection
        """
        self.min_swing_size = min_swing_size
        self.lookback = lookback

    @property
    def name(self) -> str:
        """Get detector name."""
        return "DivergenceDetector"

    @property
    def description(self) -> str:
        """Get human-readable description."""
        return (
            "Detects divergences between CVD and price action to identify "
            "potential reversal or exhaustion points."
        )

    def detect_swing_points(
        self, values: list[float], timestamps: list[datetime]
    ) -> list[tuple[int, str]]:
        """Detect swing highs and lows in a series.

        Args:
            values: Series of values
            timestamps: Corresponding timestamps

        Returns:
            List of (index, direction) tuples for swing points
        """
        if len(values) < self.lookback * 2 + 1:
            return []

        swing_points = []
        half_lookback = self.lookback

        for i in range(half_lookback, len(values) - half_lookback):
            window = values[i - half_lookback : i + half_lookback + 1]
            current = values[i]

            # Check for swing high
            if all(current > v for v in window[:half_lookback]) and all(
                current > v for v in window[half_lookback + 1 :]
            ):
                swing_points.append((i, "high"))

            # Check for swing low
            elif all(current < v for v in window[:half_lookback]) and all(
                current < v for v in window[half_lookback + 1 :]
            ):
                swing_points.append((i, "low"))

        return swing_points

    def calculate_strength(
        self, price_delta: float, cvd_delta: float, price_trend: float, cvd_trend: float
    ) -> float:
        """Calculate divergence strength score.

        Args:
            price_delta: Price change
            cvd_delta: CVD change
            price_trend: Overall price trend
            cvd_trend: Overall CVD trend

        Returns:
            Strength score 0-1
        """
        # Normalize by magnitude
        price_magnitude = abs(price_delta) / (abs(price_trend) + 1e-10)
        cvd_magnitude = abs(cvd_delta) / (abs(cvd_trend) + 1e-10)

        # Higher score if both show significant change
        score = (price_magnitude + cvd_magnitude) / 2

        return min(1.0, max(0.0, score))

    def detect(
        self,
        cvd_values: list[float],
        prices: list[float],
        timestamps: list[datetime],
    ) -> list[Divergence]:
        """Detect all divergences in CVD vs price.

        Args:
            cvd_values: CVD calculation values
            prices: Price values
            timestamps: Timestamps for both series

        Returns:
            List of detected Divergence objects
        """
        if len(cvd_values) != len(prices) or len(cvd_values) < self.lookback * 2:
            return []

        divergences: list[Divergence] = []

        # Find swing points
        cvd_swings = self.detect_swing_points(cvd_values, timestamps)
        price_swings = self.detect_swing_points(prices, timestamps)

        # Match swings and detect divergences
        for _i, (price_idx, price_dir) in enumerate(price_swings):
            # Find corresponding CVD swing
            for _j, (cvd_idx, cvd_dir) in enumerate(cvd_swings):
                if abs(price_idx - cvd_idx) <= self.lookback:
                    # Potential divergence - check types
                    div_type = self._classify_divergence(
                        price_dir, price_idx, prices, cvd_dir, cvd_idx, cvd_values
                    )

                    if div_type:
                        strength = self._calculate_divergence_strength(
                            prices, price_idx, cvd_values, cvd_idx
                        )

                        divergences.append(
                            Divergence(
                                divergence_type=div_type,
                                price_index=price_idx,
                                cvd_index=cvd_idx,
                                price_value=prices[price_idx],
                                cvd_value=cvd_values[cvd_idx],
                                timestamp=timestamps[price_idx],
                                strength=strength,
                            )
                        )
                    break

        return divergences

    def _classify_divergence(
        self,
        price_dir: str,
        price_idx: int,
        prices: list[float],
        cvd_dir: str,
        cvd_idx: int,
        cvd_values: list[float],
    ) -> DivergenceType | None:
        """Classify divergence between price and CVD swings.

        Args:
            price_dir: 'high' or 'low' for price
            price_idx: Index in price series
            prices: Price values
            cvd_dir: 'high' or 'low' for CVD
            cvd_idx: Index in CVD series
            cvd_values: CVD values

        Returns:
            DivergenceType if divergence detected, None otherwise
        """
        # Regular divergence
        if price_dir == "high" and cvd_dir == "low":
            return DivergenceType.BEARISH
        if price_dir == "low" and cvd_dir == "high":
            return DivergenceType.BULLISH

        # Check for hidden divergence
        if price_idx >= 2 and cvd_idx >= 2:
            prev_price_idx = price_idx - 1
            prev_cvd_idx = cvd_idx - 1

            if price_dir == "high" and cvd_dir == "high":
                # Price makes higher high, CVD makes lower high
                if (
                    prices[price_idx] > prices[prev_price_idx]
                    and cvd_values[cvd_idx] < cvd_values[prev_cvd_idx]
                ):
                    return DivergenceType.HIDDEN_BEARISH

            if price_dir == "low" and cvd_dir == "low":
                # Price makes lower low, CVD makes higher low
                if (
                    prices[price_idx] < prices[prev_price_idx]
                    and cvd_values[cvd_idx] > cvd_values[prev_cvd_idx]
                ):
                    return DivergenceType.HIDDEN_BULLISH

        return None

    def _calculate_divergence_strength(
        self, prices: list[float], price_idx: int, cvd_values: list[float], cvd_idx: int
    ) -> float:
        """Calculate strength of divergence.

        Args:
            prices: Price values
            price_idx: Price swing index
            cvd_values: CVD values
            cvd_idx: CVD swing index

        Returns:
            Strength score 0-1
        """
        # Look back over lookback period
        lookback = min(self.lookback, price_idx, cvd_idx)

        if lookback == 0:
            return 0.5

        price_delta = prices[price_idx] - prices[price_idx - lookback]
        cvd_delta = cvd_values[cvd_idx] - cvd_values[cvd_idx - lookback]

        price_trend = sum(prices[price_idx - lookback : price_idx + 1]) / (lookback + 1)
        cvd_trend = sum(cvd_values[cvd_idx - lookback : cvd_idx + 1]) / (lookback + 1)

        return self.calculate_strength(price_delta, cvd_delta, price_trend, cvd_trend)

    def get_latest_divergence(
        self,
        cvd_values: list[float],
        prices: list[float],
        timestamps: list[datetime],
    ) -> Divergence | None:
        """Get the most recent divergence.

        Args:
            cvd_values: CVD values
            prices: Price values
            timestamps: Timestamps

        Returns:
            Most recent Divergence or None
        """
        divergences = self.detect(cvd_values, prices, timestamps)
        if not divergences:
            return None

        return max(divergences, key=lambda d: d.price_index)
