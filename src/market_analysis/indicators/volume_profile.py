"""Volume Profile indicator implementation.

Volume Profile displays trading activity over a specified time period
at specific price levels, identifying POC (Point of Control),
VAH (Value Area High), and VAL (Value Area Low).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.base import BaseIndicator, Signal, SignalDirection
from market_analysis.indicators.feature_store import FeatureStore


@dataclass
class VolumeProfileResult:
    """Result of Volume Profile calculation.

    Attributes:
        poc: Point of Control (price level with highest volume)
        vah: Value Area High (upper boundary of value area percentage)
        val: Value Area Low (lower boundary of value area percentage)
        volume_by_price: Dictionary mapping price levels to volume
        bins: Price bin edges used for the histogram
        bin_volumes: Volume aggregated per price bin
    """

    poc: float
    vah: float
    val: float
    volume_by_price: dict[float, float] = field(default_factory=dict)
    bins: np.ndarray = field(default_factory=lambda: np.array([]))
    bin_volumes: np.ndarray = field(default_factory=lambda: np.array([]))


class VolumeProfile(BaseIndicator[VolumeProfileResult]):
    """Volume Profile indicator with POC/VAH/VAL calculations.

    Analyzes volume distribution across price levels to identify
    key support/resistance zones.  Extends :class:`BaseIndicator`
    so it participates in the plugin system.
    """

    def __init__(
        self,
        lookback_periods: int = 24,
        volume_buckets: int = 12,
        value_area_pct: float = 0.7,
        use_feature_store: bool = True,
        name: str = "VolumeProfile",
    ) -> None:
        """Initialize Volume Profile calculator.

        Args:
            lookback_periods: Number of periods to analyze.
            volume_buckets: Number of price buckets for the histogram.
            value_area_pct: Fraction of total volume inside the value area
                (default 0.70 → 70 %).
            use_feature_store: Whether to cache results in FeatureStore.
            name: Indicator name exposed via the plugin system.

        Raises:
            ValueError: If *lookback_periods* < 2, *volume_buckets* < 2,
                or *value_area_pct* is not in (0, 1].
        """
        super().__init__(name)
        if lookback_periods < 2:
            raise ValueError("lookback_periods must be >= 2")
        if volume_buckets < 2:
            raise ValueError("volume_buckets must be >= 2")
        if not (0 < value_area_pct <= 1.0):
            raise ValueError("value_area_pct must be in (0, 1]")
        self.lookback_periods = lookback_periods
        self.volume_buckets = volume_buckets
        self.value_area_pct = value_area_pct
        self.use_feature_store = use_feature_store
        self._feature_store = FeatureStore(prefix="vp") if use_feature_store else None

    # ------------------------------------------------------------------
    # BaseIndicator interface
    # ------------------------------------------------------------------

    @property
    def description(self) -> str:
        return "Volume Profile with POC/VAH/VAL calculations"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "lookback_periods": self.lookback_periods,
            "volume_buckets": self.volume_buckets,
            "value_area_pct": self.value_area_pct,
        }

    def validate(self, data: list[OHLCVData]) -> bool:
        """Return *True* when *data* has at least *lookback_periods* rows."""
        return len(data) >= self.lookback_periods

    def compute(self, data: list[OHLCVData]) -> VolumeProfileResult:
        """Calculate Volume Profile from OHLCV data.

        Args:
            data: List of OHLCV data points.

        Returns:
            :class:`VolumeProfileResult` with POC, VAH, VAL, and histogram.

        Raises:
            ValueError: If insufficient data is provided.
        """
        if not self.validate(data):
            raise ValueError(
                f"Need {self.lookback_periods} data points, got {len(data)}"
            )

        # Check cache
        if self._feature_store is not None:
            cache_key = self._make_cache_key(data)
            cached = self._feature_store.get(cache_key)
            if cached is not None:
                return VolumeProfileResult(
                    poc=cached["poc"],
                    vah=cached["vah"],
                    val=cached["val"],
                    volume_by_price=cached.get("volume_by_price", {}),
                    bins=np.asarray(cached.get("bins", [])),
                    bin_volumes=np.asarray(cached.get("bin_volumes", [])),
                )

        result = self._calculate_profile(data)

        # Cache result
        if self._feature_store is not None:
            self._feature_store.set(
                self._make_cache_key(data),
                {
                    "poc": result.poc,
                    "vah": result.vah,
                    "val": result.val,
                    "volume_by_price": result.volume_by_price,
                    "bins": result.bins.tolist(),
                    "bin_volumes": result.bin_volumes.tolist(),
                },
            )

        return result

    def get_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_signal(self, result: VolumeProfileResult) -> Signal:
        """Convert a profile result into a :class:`Signal`.

        The current implementation always emits HOLD with 50 % confidence.
        Subclasses or callers may override to incorporate current price.
        """
        return Signal(
            direction=SignalDirection.HOLD,
            confidence=0.5,
            timestamp=__import__("datetime").datetime.utcnow(),
            metadata={"poc": result.poc, "vah": result.vah, "val": result.val},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_cache_key(self, data: list[OHLCVData]) -> str:
        """Generate a deterministic cache key from *data*."""
        if not data:
            return "vp_empty"
        last_ts = data[-1].timestamp
        return f"vp_{last_ts}_{self.lookback_periods}"

    def _calculate_profile(self, data: list[OHLCVData]) -> VolumeProfileResult:
        """Core profile calculation.

        Steps:
        1. Extract high/low/volume arrays for the lookback window.
        2. Create evenly-spaced price bins between min-low and max-high.
        3. Map each candle's typical price ((H+L)/2) to a bin and accumulate volume.
        4. POC = bin midpoint with the largest accumulated volume.
        5. Value area = smallest set of bins (sorted by volume descending)
           whose cumulative volume ≥ ``value_area_pct * total_volume``.
        6. VAH = upper edge of highest value-area bin.
           VAL = lower edge of lowest value-area bin.
        """
        window = data[-self.lookback_periods :]
        highs = np.array([d.high_price for d in window])
        lows = np.array([d.low_price for d in window])
        volumes = np.array([d.volume for d in window])

        # Create price bins
        min_price = float(np.min(lows))
        max_price = float(np.max(highs))
        bins = np.linspace(min_price, max_price, self.volume_buckets + 1)

        # Assign typical prices to bins
        typical_prices = (highs + lows) / 2.0
        bin_indices = np.digitize(typical_prices, bins) - 1
        bin_indices = np.clip(bin_indices, 0, self.volume_buckets - 1)

        # Aggregate volume by bin
        bin_volumes = np.zeros(self.volume_buckets, dtype=np.float64)
        for idx, vol in zip(bin_indices, volumes, strict=True):
            bin_volumes[int(idx)] += float(vol)

        # POC — bin with highest volume
        poc_bin = int(np.argmax(bin_volumes))
        poc = float((bins[poc_bin] + bins[poc_bin + 1]) / 2.0)

        # Value area
        total_volume = float(np.sum(bin_volumes))
        target_volume = total_volume * self.value_area_pct

        sorted_indices = np.argsort(bin_volumes)[::-1]
        cumulative = 0.0
        value_area_bins: list[int] = []
        for idx in sorted_indices:
            cumulative += float(bin_volumes[int(idx)])
            value_area_bins.append(int(idx))
            if cumulative >= target_volume:
                break

        if value_area_bins:
            vah = float(bins[max(value_area_bins) + 1])
            val = float(bins[min(value_area_bins)])
        else:
            vah = max_price
            val = min_price

        # Volume-by-price mapping (midpoint → volume)
        volume_by_price: dict[float, float] = {}
        for i in range(self.volume_buckets):
            midpoint = float((bins[i] + bins[i + 1]) / 2.0)
            volume_by_price[midpoint] = float(bin_volumes[i])

        return VolumeProfileResult(
            poc=poc,
            vah=vah,
            val=val,
            volume_by_price=volume_by_price,
            bins=bins,
            bin_volumes=bin_volumes,
        )
