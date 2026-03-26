"""Premium/Discount Zone Classifier.

Determines whether the current price is in a premium or discount zone
relative to fair value, calculated using Volume Profile POC or VWAP.

ICT Concepts:
    - Fair Value: The equilibrium price where the most volume traded (POC)
      or the volume-weighted average price (VWAP).
    - Premium Zone: Price is above fair value. Smart money looks to sell
      or take profits. Favor short setups or wait for retracement.
    - Discount Zone: Price is below fair value. Smart money looks to buy.
      Favor long setups.
    - Equilibrium Zone: Price is near fair value. Neutral bias.

Usage:
    classifier = PremiumDiscountClassifier()

    result = classifier.classify(
        current_price=50100.0,
        candles=candles_1h,
        method=FairValueMethod.VWAP,
    )

    if result.zone == ZoneType.DISCOUNT:
        print("Price in discount zone - look for longs")
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class FairValueMethod(str, Enum):
    """Method for calculating fair value."""

    VWAP = "vwap"
    VOLUME_PROFILE_POC = "volume_profile_poc"


class ZoneType(str, Enum):
    """Classification of the current price zone."""

    PREMIUM = "premium"
    DISCOUNT = "discount"
    EQUILIBRIUM = "equilibrium"


@dataclass(frozen=True)
class FairValueResult:
    """Result of a fair value calculation.

    Attributes:
        value: The calculated fair value price
        method: The method used to calculate fair value
        confidence: Confidence in the fair value (0.0-1.0)
        data_points: Number of candles used in calculation
        timestamp: Unix timestamp when calculated
    """

    value: float
    method: FairValueMethod
    confidence: float
    data_points: int
    timestamp: float


@dataclass(frozen=True)
class ZoneClassification:
    """Classification result for premium/discount zones.

    Attributes:
        zone: The current zone type (premium, discount, equilibrium)
        fair_value: The fair value reference price
        current_price: The current market price
        deviation_pct: Percentage deviation from fair value
        distance_from_fv: Absolute price distance from fair value
        premium_boundary: Price above which is premium zone
        discount_boundary: Price below which is discount zone
        equilibrium_width_pct: Width of equilibrium zone as percentage
        method: Fair value method used
        timestamp: Unix timestamp when classified
    """

    zone: ZoneType
    fair_value: float
    current_price: float
    deviation_pct: float
    distance_from_fv: float
    premium_boundary: float
    discount_boundary: float
    equilibrium_width_pct: float
    method: FairValueMethod
    timestamp: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "zone": self.zone.value,
            "fair_value": round(self.fair_value, 6),
            "current_price": round(self.current_price, 6),
            "deviation_pct": round(self.deviation_pct, 4),
            "distance_from_fv": round(self.distance_from_fv, 6),
            "premium_boundary": round(self.premium_boundary, 6),
            "discount_boundary": round(self.discount_boundary, 6),
            "equilibrium_width_pct": round(self.equilibrium_width_pct, 4),
            "method": self.method.value,
            "timestamp": self.timestamp,
        }


class PremiumDiscountClassifier:
    """Classifies price into premium, discount, or equilibrium zones.

    Uses either VWAP or Volume Profile POC as the fair value reference.
    The equilibrium zone width is configurable and defaults to 0.1% of
    fair value on each side.

    Classification refresh interval defaults to 5 minutes (300 seconds).

    Args:
        equilibrium_width_pct: Half-width of equilibrium zone as percentage
            of fair value. Default 0.1 (0.1% on each side of FV).
        refresh_interval_seconds: Minimum seconds between recalculations.
            Default 300 (5 minutes).

    Usage:
        classifier = PremiumDiscountClassifier(
            equilibrium_width_pct=0.15,
            refresh_interval_seconds=300,
        )

        result = classifier.classify(
            current_price=50100.0,
            candles=candles,
            method=FairValueMethod.VWAP,
        )
    """

    DEFAULT_EQUILIBRIUM_WIDTH_PCT = 0.1
    DEFAULT_REFRESH_INTERVAL = 300  # 5 minutes

    def __init__(
        self,
        equilibrium_width_pct: float = DEFAULT_EQUILIBRIUM_WIDTH_PCT,
        refresh_interval_seconds: float = DEFAULT_REFRESH_INTERVAL,
    ) -> None:
        if equilibrium_width_pct < 0:
            raise ValueError("equilibrium_width_pct must be non-negative")
        if refresh_interval_seconds <= 0:
            raise ValueError("refresh_interval_seconds must be positive")

        self.equilibrium_width_pct = equilibrium_width_pct
        self.refresh_interval_seconds = refresh_interval_seconds
        self._last_calculation_time: float = 0.0
        self._cached_fair_value: FairValueResult | None = None

    def calculate_vwap(
        self,
        candles: Sequence[dict],
    ) -> FairValueResult:
        """Calculate VWAP from candle data.

        VWAP = sum(typical_price * volume) / sum(volume)
        where typical_price = (high + low + close) / 3

        Args:
            candles: Sequence of candle dicts with keys:
                - 'high': float
                - 'low': float
                - 'close': float
                - 'volume': float

        Returns:
            FairValueResult with VWAP value

        Raises:
            ValueError: If candles are empty or missing required keys
        """
        if not candles:
            raise ValueError("Cannot calculate VWAP from empty candles")

        cumulative_tp_volume = 0.0
        cumulative_volume = 0.0

        for i, candle in enumerate(candles):
            try:
                high = float(candle["high"])
                low = float(candle["low"])
                close = float(candle["close"])
                volume = float(candle["volume"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Candle at index {i} missing required keys "
                    f"(high, low, close, volume): {exc}"
                ) from exc

            if volume < 0:
                raise ValueError(f"Candle at index {i} has negative volume: {volume}")

            typical_price = (high + low + close) / 3.0
            cumulative_tp_volume += typical_price * volume
            cumulative_volume += volume

        if cumulative_volume == 0:
            raise ValueError("Total volume is zero - cannot calculate VWAP")

        vwap = cumulative_tp_volume / cumulative_volume

        # Confidence based on data volume and count
        confidence = min(1.0, len(candles) / 100.0)

        return FairValueResult(
            value=vwap,
            method=FairValueMethod.VWAP,
            confidence=confidence,
            data_points=len(candles),
            timestamp=time.time(),
        )

    def calculate_volume_profile_poc(
        self,
        candles: Sequence[dict],
        num_bins: int = 100,
    ) -> FairValueResult:
        """Calculate Volume Profile Point of Control (POC).

        The POC is the price level with the highest traded volume.
        Volume is distributed across price bins based on each candle's
        high-low range.

        Args:
            candles: Sequence of candle dicts with keys:
                - 'high': float
                - 'low': float
                - 'close': float
                - 'volume': float
            num_bins: Number of price bins for the volume profile.
                Default 100.

        Returns:
            FairValueResult with POC value

        Raises:
            ValueError: If candles are empty or missing required keys
        """
        if not candles:
            raise ValueError("Cannot calculate POC from empty candles")

        if num_bins < 1:
            raise ValueError("num_bins must be at least 1")

        # Find global price range
        all_highs = []
        all_lows = []
        volumes = []

        for i, candle in enumerate(candles):
            try:
                high = float(candle["high"])
                low = float(candle["low"])
                volume = float(candle["volume"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Candle at index {i} missing required keys "
                    f"(high, low, volume): {exc}"
                ) from exc

            if volume < 0:
                raise ValueError(f"Candle at index {i} has negative volume: {volume}")
            if high < low:
                raise ValueError(f"Candle at index {i} has high < low ({high} < {low})")

            all_highs.append(high)
            all_lows.append(low)
            volumes.append(volume)

        global_high = max(all_highs)
        global_low = min(all_lows)

        if global_high == global_low:
            # All candles at the same price - return that price
            return FairValueResult(
                value=global_high,
                method=FairValueMethod.VOLUME_PROFILE_POC,
                confidence=1.0,
                data_points=len(candles),
                timestamp=time.time(),
            )

        # Build volume profile bins
        bin_size = (global_high - global_low) / num_bins
        bin_volumes = [0.0] * num_bins

        for candle_high, candle_low, volume in zip(
            all_highs, all_lows, volumes, strict=True
        ):
            if volume == 0:
                continue
            # Distribute volume across bins this candle spans
            start_bin = int((candle_low - global_low) / bin_size)
            end_bin = int((candle_high - global_low) / bin_size)
            # Clamp to valid range
            start_bin = max(0, min(start_bin, num_bins - 1))
            end_bin = max(0, min(end_bin, num_bins - 1))
            num_bins_hit = end_bin - start_bin + 1
            volume_per_bin = volume / num_bins_hit
            for b in range(start_bin, end_bin + 1):
                bin_volumes[b] += volume_per_bin

        # Find the bin with maximum volume
        max_volume_bin = max(range(num_bins), key=lambda b: bin_volumes[b])

        # POC is the midpoint of the bin with highest volume
        poc = global_low + (max_volume_bin + 0.5) * bin_size

        # Confidence based on concentration of volume at POC
        total_volume = sum(bin_volumes)
        if total_volume > 0:
            concentration = bin_volumes[max_volume_bin] / total_volume
            # Higher concentration = higher confidence
            confidence = min(1.0, concentration * 10.0 + len(candles) / 200.0)
        else:
            confidence = 0.0

        return FairValueResult(
            value=poc,
            method=FairValueMethod.VOLUME_PROFILE_POC,
            confidence=confidence,
            data_points=len(candles),
            timestamp=time.time(),
        )

    def calculate_fair_value(
        self,
        candles: Sequence[dict],
        method: FairValueMethod = FairValueMethod.VWAP,
    ) -> FairValueResult:
        """Calculate fair value using the specified method.

        Args:
            candles: Sequence of candle dicts
            method: Fair value calculation method

        Returns:
            FairValueResult with calculated fair value
        """
        if method == FairValueMethod.VWAP:
            return self.calculate_vwap(candles)
        elif method == FairValueMethod.VOLUME_PROFILE_POC:
            return self.calculate_volume_profile_poc(candles)
        else:
            raise ValueError(f"Unknown fair value method: {method}")

    def classify(
        self,
        current_price: float,
        candles: Sequence[dict],
        method: FairValueMethod = FairValueMethod.VWAP,
        force_recalculate: bool = False,
    ) -> ZoneClassification:
        """Classify current price into premium/discount/equilibrium zone.

        Args:
            current_price: Current market price
            candles: Sequence of candle dicts for fair value calculation
            method: Fair value method to use
            force_recalculate: Force recalculation even if within
                refresh interval

        Returns:
            ZoneClassification with zone type and boundaries

        Raises:
            ValueError: If current_price is not positive
        """
        if current_price <= 0:
            raise ValueError(f"current_price must be positive, got {current_price}")

        now = time.time()
        should_recalculate = (
            force_recalculate
            or self._cached_fair_value is None
            or (now - self._last_calculation_time) >= self.refresh_interval_seconds
        )

        if should_recalculate:
            self._cached_fair_value = self.calculate_fair_value(candles, method)
            self._last_calculation_time = now
            logger.debug(
                "Recalculated fair value: %.2f (method=%s)",
                self._cached_fair_value.value,
                method.value,
            )

        fv = self._cached_fair_value
        assert fv is not None  # guaranteed by should_recalculate logic

        # Calculate boundaries
        equilibrium_half_width = fv.value * (self.equilibrium_width_pct / 100.0)
        premium_boundary = fv.value + equilibrium_half_width
        discount_boundary = fv.value - equilibrium_half_width

        # Classify zone
        if current_price > premium_boundary:
            zone = ZoneType.PREMIUM
        elif current_price < discount_boundary:
            zone = ZoneType.DISCOUNT
        else:
            zone = ZoneType.EQUILIBRIUM

        # Calculate deviation
        if fv.value != 0:
            deviation_pct = ((current_price - fv.value) / fv.value) * 100.0
        else:
            deviation_pct = 0.0

        distance_from_fv = abs(current_price - fv.value)

        return ZoneClassification(
            zone=zone,
            fair_value=fv.value,
            current_price=current_price,
            deviation_pct=deviation_pct,
            distance_from_fv=distance_from_fv,
            premium_boundary=premium_boundary,
            discount_boundary=discount_boundary,
            equilibrium_width_pct=self.equilibrium_width_pct,
            method=method,
            timestamp=now,
        )

    def classify_with_manual_fv(
        self,
        current_price: float,
        fair_value: float,
        method: FairValueMethod = FairValueMethod.VWAP,
    ) -> ZoneClassification:
        """Classify zone using a manually provided fair value.

        This bypasses the cache and refresh interval, useful for
        external fair value sources.

        Args:
            current_price: Current market price
            fair_value: Pre-calculated fair value
            method: The method used to produce the fair value

        Returns:
            ZoneClassification with zone type and boundaries
        """
        if current_price <= 0:
            raise ValueError(f"current_price must be positive, got {current_price}")
        if fair_value <= 0:
            raise ValueError(f"fair_value must be positive, got {fair_value}")

        equilibrium_half_width = fair_value * (self.equilibrium_width_pct / 100.0)
        premium_boundary = fair_value + equilibrium_half_width
        discount_boundary = fair_value - equilibrium_half_width

        if current_price > premium_boundary:
            zone = ZoneType.PREMIUM
        elif current_price < discount_boundary:
            zone = ZoneType.DISCOUNT
        else:
            zone = ZoneType.EQUILIBRIUM

        if fair_value != 0:
            deviation_pct = ((current_price - fair_value) / fair_value) * 100.0
        else:
            deviation_pct = 0.0

        distance_from_fv = abs(current_price - fair_value)

        return ZoneClassification(
            zone=zone,
            fair_value=fair_value,
            current_price=current_price,
            deviation_pct=deviation_pct,
            distance_from_fv=distance_from_fv,
            premium_boundary=premium_boundary,
            discount_boundary=discount_boundary,
            equilibrium_width_pct=self.equilibrium_width_pct,
            method=method,
            timestamp=time.time(),
        )

    def reset_cache(self) -> None:
        """Reset the cached fair value and calculation time.

        Forces recalculation on the next classify() call.
        """
        self._cached_fair_value = None
        self._last_calculation_time = 0.0
