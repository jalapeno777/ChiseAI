"""Tests for Volume Profile indicator module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.volume_profile import (
    VolumeProfile,
    VolumeProfileResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ohlcv(
    timestamp: int = 1609459200000,
    open_price: float = 100.0,
    high_price: float = 102.0,
    low_price: float = 98.0,
    close_price: float = 100.0,
    volume: float = 1000.0,
) -> OHLCVData:
    """Helper to build an :class:`OHLCVData` instance."""
    return OHLCVData(
        timestamp=timestamp,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
    )


@pytest.fixture
def flat_data() -> list[OHLCVData]:
    """24 candles all at the same price — minimal volatility."""
    return [
        _make_ohlcv(
            timestamp=1609459200000 + i * 60000,
            high_price=101.0,
            low_price=99.0,
            volume=1000.0,
        )
        for i in range(24)
    ]


@pytest.fixture
def trending_data() -> list[OHLCVData]:
    """50 candles with a steady upward trend."""
    data: list[OHLCVData] = []
    price = 100.0
    for i in range(50):
        price += 0.5
        data.append(
            _make_ohlcv(
                timestamp=1609459200000 + i * 60000,
                high_price=price + 1.0,
                low_price=price - 1.0,
                volume=1000.0 + i * 10,
            )
        )
    return data


@pytest.fixture
def volatile_data() -> list[OHLCVData]:
    """30 candles with high volatility (large H-L ranges)."""
    np.random.seed(99)
    data: list[OHLCVData] = []
    price = 100.0
    for i in range(30):
        price += np.random.normal(0, 3.0)
        price = max(price, 20.0)
        spread = abs(np.random.normal(0, 5.0)) + 1.0
        data.append(
            _make_ohlcv(
                timestamp=1609459200000 + i * 60000,
                high_price=price + spread,
                low_price=price - spread,
                volume=abs(np.random.normal(2000, 500)),
            )
        )
    return data


@pytest.fixture
def vp() -> VolumeProfile:
    """Default VolumeProfile instance (no FeatureStore)."""
    return VolumeProfile(
        lookback_periods=24,
        volume_buckets=12,
        value_area_pct=0.7,
        use_feature_store=False,
    )


# ---------------------------------------------------------------------------
# VolumeProfileResult
# ---------------------------------------------------------------------------


class TestVolumeProfileResult:
    """Tests for the VolumeProfileResult dataclass."""

    def test_creation_with_defaults(self) -> None:
        result = VolumeProfileResult(poc=100.0, vah=105.0, val=95.0)
        assert result.poc == 100.0
        assert result.vah == 105.0
        assert result.val == 95.0
        assert result.volume_by_price == {}
        assert len(result.bins) == 0
        assert len(result.bin_volumes) == 0

    def test_creation_full(self) -> None:
        vbp = {100.0: 500.0, 101.0: 800.0}
        bins = np.array([99.0, 100.0, 101.0, 102.0])
        bv = np.array([500.0, 800.0])
        result = VolumeProfileResult(
            poc=101.0,
            vah=102.0,
            val=99.0,
            volume_by_price=vbp,
            bins=bins,
            bin_volumes=bv,
        )
        assert result.poc == 101.0
        assert result.vah == 102.0
        assert result.val == 99.0
        assert result.volume_by_price == vbp
        np.testing.assert_array_equal(result.bins, bins)
        np.testing.assert_array_equal(result.bin_volumes, bv)


# ---------------------------------------------------------------------------
# VolumeProfile — initialization
# ---------------------------------------------------------------------------


class TestVolumeProfileInit:
    """Tests for VolumeProfile constructor validation."""

    def test_default_init(self) -> None:
        vp = VolumeProfile(use_feature_store=False)
        assert vp.lookback_periods == 24
        assert vp.volume_buckets == 12
        assert vp.value_area_pct == 0.7
        assert vp.name == "VolumeProfile"

    def test_custom_name(self) -> None:
        vp = VolumeProfile(name="MyVP", use_feature_store=False)
        assert vp.name == "MyVP"

    def test_lookback_too_small(self) -> None:
        with pytest.raises(ValueError, match="lookback_periods must be >= 2"):
            VolumeProfile(lookback_periods=1, use_feature_store=False)

    def test_volume_buckets_too_small(self) -> None:
        with pytest.raises(ValueError, match="volume_buckets must be >= 2"):
            VolumeProfile(volume_buckets=1, use_feature_store=False)

    def test_value_area_pct_zero(self) -> None:
        with pytest.raises(ValueError, match="value_area_pct must be in"):
            VolumeProfile(value_area_pct=0.0, use_feature_store=False)

    def test_value_area_pct_negative(self) -> None:
        with pytest.raises(ValueError, match="value_area_pct must be in"):
            VolumeProfile(value_area_pct=-0.1, use_feature_store=False)

    def test_value_area_pct_above_one(self) -> None:
        with pytest.raises(ValueError, match="value_area_pct must be in"):
            VolumeProfile(value_area_pct=1.5, use_feature_store=False)

    def test_value_area_pct_exactly_one(self) -> None:
        vp = VolumeProfile(value_area_pct=1.0, use_feature_store=False)
        assert vp.value_area_pct == 1.0

    def test_feature_store_created_by_default(self) -> None:
        vp = VolumeProfile(use_feature_store=True)
        assert vp._feature_store is not None

    def test_feature_store_disabled(self) -> None:
        vp = VolumeProfile(use_feature_store=False)
        assert vp._feature_store is None


# ---------------------------------------------------------------------------
# BaseIndicator interface
# ---------------------------------------------------------------------------


class TestBaseIndicatorInterface:
    """Verify BaseIndicator abstract methods are implemented correctly."""

    def test_description(self, vp: VolumeProfile) -> None:
        assert isinstance(vp.description, str)
        assert "POC" in vp.description

    def test_parameters(self, vp: VolumeProfile) -> None:
        params = vp.parameters
        assert params["lookback_periods"] == 24
        assert params["volume_buckets"] == 12
        assert params["value_area_pct"] == 0.7

    def test_validate_sufficient(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        assert vp.validate(flat_data) is True

    def test_validate_insufficient(self, vp: VolumeProfile) -> None:
        assert vp.validate([_make_ohlcv()]) is False

    def test_validate_exact_minimum(self, vp: VolumeProfile) -> None:
        vp2 = VolumeProfile(lookback_periods=5, use_feature_store=False)
        data = [_make_ohlcv(timestamp=1000 + i * 60) for i in range(5)]
        assert vp2.validate(data) is True

    def test_get_metadata(self, vp: VolumeProfile) -> None:
        meta = vp.get_metadata()
        assert meta["name"] == "VolumeProfile"
        assert "description" in meta
        assert "parameters" in meta

    def test_to_signal(self, vp: VolumeProfile) -> None:
        result = VolumeProfileResult(poc=100.0, vah=105.0, val=95.0)
        sig = vp.to_signal(result)
        assert sig.direction.value == "hold"
        assert sig.confidence == 0.5
        assert isinstance(sig.timestamp, datetime)
        assert sig.metadata["poc"] == 100.0
        assert sig.metadata["vah"] == 105.0
        assert sig.metadata["val"] == 95.0


# ---------------------------------------------------------------------------
# compute() — core calculation
# ---------------------------------------------------------------------------


class TestCompute:
    """Tests for the compute method and result correctness."""

    def test_compute_insufficient_data_raises(self, vp: VolumeProfile) -> None:
        with pytest.raises(ValueError, match="Need 24 data points, got 5"):
            vp.compute([_make_ohlcv(timestamp=i) for i in range(5)])

    def test_compute_returns_result(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        result = vp.compute(flat_data)
        assert isinstance(result, VolumeProfileResult)

    def test_poc_within_range(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        result = vp.compute(flat_data)
        min_low = min(d.low_price for d in flat_data)
        max_high = max(d.high_price for d in flat_data)
        assert min_low <= result.poc <= max_high

    def test_val_within_range(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        result = vp.compute(flat_data)
        min_low = min(d.low_price for d in flat_data)
        max_high = max(d.high_price for d in flat_data)
        assert min_low <= result.val <= max_high

    def test_vah_within_range(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        result = vp.compute(flat_data)
        min_low = min(d.low_price for d in flat_data)
        max_high = max(d.high_price for d in flat_data)
        assert min_low <= result.vah <= max_high

    def test_vah_ge_val(
        self, vp: VolumeProfile, volatile_data: list[OHLCVData]
    ) -> None:
        result = vp.compute(volatile_data)
        assert result.vah >= result.val

    def test_val_le_poc_le_vah(
        self, vp: VolumeProfile, trending_data: list[OHLCVData]
    ) -> None:
        """POC should sit between VAL and VAH (inclusive)."""
        result = vp.compute(trending_data)
        assert result.val <= result.poc <= result.vah

    def test_volume_by_price_keys_match_bins(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        result = vp.compute(flat_data)
        # Number of price levels should equal volume_buckets
        assert len(result.volume_by_price) == vp.volume_buckets

    def test_bin_volumes_sum(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        """Sum of bin volumes should equal total volume in the window."""
        result = vp.compute(flat_data)
        expected_total = sum(d.volume for d in flat_data[-vp.lookback_periods :])
        np.testing.assert_almost_equal(
            float(np.sum(result.bin_volumes)), expected_total, decimal=6
        )

    def test_different_lookback(self, trending_data: list[OHLCVData]) -> None:
        """Shorter lookback should produce a different POC than full lookback."""
        vp_short = VolumeProfile(lookback_periods=10, use_feature_store=False)
        vp_long = VolumeProfile(lookback_periods=40, use_feature_store=False)
        r_short = vp_short.compute(trending_data)
        r_long = vp_long.compute(trending_data)
        # They may coincide by chance, but generally should differ
        # We just verify both produce valid results
        assert r_short.poc != r_long.poc or r_short.vah != r_long.vah

    def test_different_bucket_count(self, volatile_data: list[OHLCVData]) -> None:
        """Different bucket counts should yield different granularity."""
        vp_coarse = VolumeProfile(volume_buckets=4, use_feature_store=False)
        vp_fine = VolumeProfile(volume_buckets=20, use_feature_store=False)
        r_coarse = vp_coarse.compute(volatile_data)
        r_fine = vp_fine.compute(volatile_data)
        assert len(r_coarse.volume_by_price) == 4
        assert len(r_fine.volume_by_price) == 20

    def test_value_area_pct_100(self, volatile_data: list[OHLCVData]) -> None:
        """With 100% value area, all bins with non-zero volume are included."""
        vp100 = VolumeProfile(
            lookback_periods=24, value_area_pct=1.0, use_feature_store=False
        )
        result = vp100.compute(volatile_data)
        total_volume = float(np.sum(result.bin_volumes))
        # With 100% target, all volume should fall within value area
        # VAH >= all bin upper edges that have volume, VAL <= all bin lower edges
        nonzero_bins = np.nonzero(result.bin_volumes)[0]
        if len(nonzero_bins) > 0:
            assert result.val <= result.bins[nonzero_bins[0] + 1]
            assert result.vah >= result.bins[nonzero_bins[-1]]

    def test_value_area_pct_small(self, volatile_data: list[OHLCVData]) -> None:
        """A small value area should produce narrow VAH-VAL range."""
        vp_small = VolumeProfile(value_area_pct=0.1, use_feature_store=False)
        result = vp_small.compute(volatile_data)
        assert result.vah >= result.val
        # Range should be much smaller than full price range
        full_range = max(d.high_price for d in volatile_data) - min(
            d.low_price for d in volatile_data
        )
        va_range = result.vah - result.val
        assert va_range <= full_range


# ---------------------------------------------------------------------------
# FeatureStore integration
# ---------------------------------------------------------------------------


class TestFeatureStoreIntegration:
    """Tests for FeatureStore caching behaviour."""

    def test_cache_key_format(self, vp: VolumeProfile) -> None:
        data = [_make_ohlcv(timestamp=5000 + i * 60) for i in range(24)]
        key = vp._make_cache_key(data)
        assert key.startswith("vp_")
        assert "24" in key
        assert str(5000 + 23 * 60) in key

    def test_cache_key_empty_data(self, vp: VolumeProfile) -> None:
        key = vp._make_cache_key([])
        assert key == "vp_empty"

    def test_cache_hit(self, vp: VolumeProfile, flat_data: list[OHLCVData]) -> None:
        """When FeatureStore returns cached data, compute should use it."""
        cached_payload: dict[str, Any] = {
            "poc": 42.0,
            "vah": 50.0,
            "val": 35.0,
            "volume_by_price": {40.0: 100.0},
            "bins": [35.0, 45.0, 50.0],
            "bin_volumes": [100.0],
        }
        mock_store = MagicMock()
        mock_store.get.return_value = cached_payload
        vp._feature_store = mock_store

        result = vp.compute(flat_data)

        assert result.poc == 42.0
        assert result.vah == 50.0
        assert result.val == 35.0
        mock_store.get.assert_called_once()

    def test_cache_miss_falls_through(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        """When cache returns None, compute should calculate normally."""
        mock_store = MagicMock()
        mock_store.get.return_value = None
        vp._feature_store = mock_store

        result = vp.compute(flat_data)

        assert isinstance(result, VolumeProfileResult)
        mock_store.set.assert_called_once()

    def test_cache_stores_serializable(
        self, vp: VolumeProfile, flat_data: list[OHLCVData]
    ) -> None:
        """Cached payload must contain JSON-serializable types."""
        mock_store = MagicMock()
        mock_store.get.return_value = None
        vp._feature_store = mock_store

        vp.compute(flat_data)

        call_args = mock_store.set.call_args
        payload = call_args[0][1]  # second positional arg
        # All values should be JSON-safe (no np.ndarray at top level)
        assert isinstance(payload["poc"], (int, float))
        assert isinstance(payload["vah"], (int, float))
        assert isinstance(payload["val"], (int, float))
        assert isinstance(payload["bins"], list)
        assert isinstance(payload["bin_volumes"], list)

    @patch("market_analysis.indicators.volume_profile.FeatureStore")
    def test_feature_store_not_created_when_disabled(self, MockFS: Any) -> None:
        vp = VolumeProfile(use_feature_store=False)
        MockFS.assert_not_called()
        assert vp._feature_store is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge-case scenarios for Volume Profile."""

    def test_single_volume_bucket(self) -> None:
        """Minimum viable config: 2 data points, 2 buckets."""
        vp = VolumeProfile(
            lookback_periods=2, volume_buckets=2, use_feature_store=False
        )
        data = [
            _make_ohlcv(
                timestamp=1000, high_price=110.0, low_price=100.0, volume=500.0
            ),
            _make_ohlcv(
                timestamp=2000, high_price=120.0, low_price=90.0, volume=1500.0
            ),
        ]
        result = vp.compute(data)
        assert isinstance(result, VolumeProfileResult)
        # With 2 bins, the second candle's volume should dominate
        assert result.vah >= result.val

    def test_all_volume_in_one_candle(self) -> None:
        """One candle has all the volume, others have zero."""
        vp = VolumeProfile(
            lookback_periods=5, volume_buckets=5, use_feature_store=False
        )
        data = [
            _make_ohlcv(
                timestamp=1000 + i * 60,
                high_price=100.0 + i,
                low_price=99.0 + i,
                volume=0.0 if i != 3 else 10000.0,
            )
            for i in range(5)
        ]
        result = vp.compute(data)
        # POC should be near the dominant candle's price range
        assert 101.5 <= result.poc <= 103.5

    def test_all_same_price(self) -> None:
        """All candles have identical H/L — bins collapse."""
        vp = VolumeProfile(
            lookback_periods=10, volume_buckets=5, use_feature_store=False
        )
        data = [
            _make_ohlcv(
                timestamp=1000 + i * 60,
                high_price=100.0,
                low_price=100.0,
                volume=100.0,
            )
            for i in range(10)
        ]
        result = vp.compute(data)
        # All volume in one bin → POC = that bin's midpoint
        assert np.isclose(result.poc, 100.0, atol=1e-6)
        assert np.isclose(result.vah, 100.0, atol=1e-6)
        assert np.isclose(result.val, 100.0, atol=1e-6)

    def test_very_large_dataset(self) -> None:
        """Ensure no performance blow-up with 500+ candles."""
        vp = VolumeProfile(
            lookback_periods=100, volume_buckets=24, use_feature_store=False
        )
        data = [
            _make_ohlcv(
                timestamp=1000 + i * 60,
                high_price=100.0 + (i % 20),
                low_price=95.0 + (i % 20),
                volume=500.0 + i,
            )
            for i in range(500)
        ]
        result = vp.compute(data)
        assert isinstance(result, VolumeProfileResult)
        assert result.val <= result.poc <= result.vah


# ---------------------------------------------------------------------------
# Determinism / reproducibility
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same input must always produce the same output."""

    def test_idempotent_compute(
        self, vp: VolumeProfile, volatile_data: list[OHLCVData]
    ) -> None:
        r1 = vp.compute(volatile_data)
        r2 = vp.compute(volatile_data)
        assert r1.poc == r2.poc
        assert r1.vah == r2.vah
        assert r1.val == r2.val
        np.testing.assert_array_equal(r1.bin_volumes, r2.bin_volumes)
