"""Tests for Premium/Discount Zone Classifier.

Covers:
- VWAP fair value calculation
- Volume Profile POC fair value calculation
- Zone classification (premium/discount/equilibrium)
- Cache and refresh interval behavior
- Edge cases and error handling
"""

import time

import pytest
from src.ict.zones.classifier import (
    FairValueMethod,
    FairValueResult,
    PremiumDiscountClassifier,
    ZoneType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_candles():
    """Create sample OHLCV candles for testing."""
    return [
        {"high": 50100.0, "low": 49900.0, "close": 50000.0, "volume": 100.0},
        {"high": 50200.0, "low": 50000.0, "close": 50100.0, "volume": 150.0},
        {"high": 50300.0, "low": 50100.0, "close": 50200.0, "volume": 200.0},
        {"high": 50200.0, "low": 49900.0, "close": 49950.0, "volume": 120.0},
        {"high": 50100.0, "low": 49800.0, "close": 49850.0, "volume": 180.0},
        {"high": 50400.0, "low": 50200.0, "close": 50300.0, "volume": 250.0},
        {"high": 50500.0, "low": 50300.0, "close": 50400.0, "volume": 300.0},
        {"high": 50300.0, "low": 50000.0, "close": 50100.0, "volume": 160.0},
        {"high": 50200.0, "low": 49900.0, "close": 50000.0, "volume": 140.0},
        {"high": 50100.0, "low": 49800.0, "close": 49900.0, "volume": 110.0},
    ]


@pytest.fixture
def single_price_candles():
    """Candles all at the same price (edge case)."""
    return [
        {"high": 50000.0, "low": 50000.0, "close": 50000.0, "volume": 100.0}
        for _ in range(5)
    ]


@pytest.fixture
def classifier():
    """Create a classifier with default settings."""
    return PremiumDiscountClassifier()


@pytest.fixture
def wide_equilibrium_classifier():
    """Create a classifier with a wider equilibrium zone."""
    return PremiumDiscountClassifier(equilibrium_width_pct=1.0)


# ---------------------------------------------------------------------------
# VWAP Tests
# ---------------------------------------------------------------------------


class TestVWAPCalculation:
    """Tests for VWAP fair value calculation."""

    def test_basic_vwap(self, classifier, sample_candles):
        """Test basic VWAP calculation with sample data."""
        result = classifier.calculate_vwap(sample_candles)

        assert isinstance(result, FairValueResult)
        assert result.value > 0
        assert result.method == FairValueMethod.VWAP
        assert result.data_points == len(sample_candles)
        assert 0 < result.confidence <= 1.0

    def test_vwap_with_single_candle(self, classifier):
        """Test VWAP with a single candle."""
        candle = [{"high": 510.0, "low": 490.0, "close": 500.0, "volume": 1000.0}]
        result = classifier.calculate_vwap(candle)

        expected_tp = (510.0 + 490.0 + 500.0) / 3.0
        assert result.value == pytest.approx(expected_tp)

    def test_vwap_with_uniform_prices(self, classifier):
        """Test VWAP when all prices are the same."""
        candles = [
            {"high": 500.0, "low": 500.0, "close": 500.0, "volume": 100.0}
            for _ in range(10)
        ]
        result = classifier.calculate_vwap(candles)

        assert result.value == pytest.approx(500.0)

    def test_vwap_weighted_by_volume(self, classifier):
        """Test that VWAP is properly weighted by volume."""
        # One candle at 100 with huge volume, one at 200 with tiny volume
        candles = [
            {"high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000.0},
            {"high": 200.0, "low": 200.0, "close": 200.0, "volume": 1.0},
        ]
        result = classifier.calculate_vwap(candles)

        # VWAP should be very close to 100 due to volume weighting
        assert result.value < 105.0

    def test_vwap_raises_on_empty_candles(self, classifier):
        """Test that VWAP raises ValueError on empty candles."""
        with pytest.raises(ValueError, match="empty"):
            classifier.calculate_vwap([])

    def test_vwap_raises_on_zero_volume(self, classifier):
        """Test that VWAP raises ValueError when all volumes are zero."""
        candles = [
            {"high": 100.0, "low": 100.0, "close": 100.0, "volume": 0.0}
            for _ in range(5)
        ]
        with pytest.raises(ValueError, match="Total volume is zero"):
            classifier.calculate_vwap(candles)

    def test_vwap_raises_on_negative_volume(self, classifier):
        """Test that VWAP raises ValueError on negative volume."""
        candles = [{"high": 100.0, "low": 100.0, "close": 100.0, "volume": -10.0}]
        with pytest.raises(ValueError, match="negative volume"):
            classifier.calculate_vwap(candles)

    def test_vwap_raises_on_missing_keys(self, classifier):
        """Test that VWAP raises ValueError on missing candle keys."""
        candles = [{"high": 100.0, "low": 100.0}]  # missing close, volume
        with pytest.raises(ValueError, match="missing required keys"):
            classifier.calculate_vwap(candles)

    def test_vwap_confidence_increases_with_data(self, classifier):
        """Test that VWAP confidence increases with more data points."""
        few_candles = [
            {"high": 500.0, "low": 490.0, "close": 495.0, "volume": 100.0}
            for _ in range(10)
        ]
        many_candles = few_candles * 10

        result_few = classifier.calculate_vwap(few_candles)
        result_many = classifier.calculate_vwap(many_candles)

        assert result_many.confidence > result_few.confidence


# ---------------------------------------------------------------------------
# Volume Profile POC Tests
# ---------------------------------------------------------------------------


class TestVolumeProfilePOC:
    """Tests for Volume Profile POC fair value calculation."""

    def test_basic_poc(self, classifier, sample_candles):
        """Test basic POC calculation."""
        result = classifier.calculate_volume_profile_poc(sample_candles)

        assert isinstance(result, FairValueResult)
        assert result.value > 0
        assert result.method == FairValueMethod.VOLUME_PROFILE_POC
        assert result.data_points == len(sample_candles)
        assert 0 < result.confidence <= 1.0

    def test_poc_is_within_range(self, classifier, sample_candles):
        """Test that POC falls within the global price range."""
        result = classifier.calculate_volume_profile_poc(sample_candles)

        all_highs = [c["high"] for c in sample_candles]
        all_lows = [c["low"] for c in sample_candles]

        assert result.value >= min(all_lows)
        assert result.value <= max(all_highs)

    def test_poc_with_single_price(self, classifier, single_price_candles):
        """Test POC when all candles have the same price."""
        result = classifier.calculate_volume_profile_poc(single_price_candles)

        assert result.value == 50000.0
        assert result.confidence == 1.0

    def test_poc_custom_bins(self, classifier, sample_candles):
        """Test POC with custom number of bins."""
        result_50 = classifier.calculate_volume_profile_poc(sample_candles, num_bins=50)
        result_200 = classifier.calculate_volume_profile_poc(
            sample_candles, num_bins=200
        )

        # Both should be in valid range
        all_highs = [c["high"] for c in sample_candles]
        all_lows = [c["low"] for c in sample_candles]
        for result in (result_50, result_200):
            assert result.value >= min(all_lows)
            assert result.value <= max(all_highs)

    def test_poc_raises_on_empty_candles(self, classifier):
        """Test that POC raises ValueError on empty candles."""
        with pytest.raises(ValueError, match="empty"):
            classifier.calculate_volume_profile_poc([])

    def test_poc_raises_on_invalid_bins(self, classifier, sample_candles):
        """Test that POC raises ValueError on invalid bin count."""
        with pytest.raises(ValueError, match="num_bins must be at least 1"):
            classifier.calculate_volume_profile_poc(sample_candles, num_bins=0)

    def test_poc_raises_on_negative_volume(self, classifier):
        """Test that POC raises ValueError on negative volume."""
        candles = [{"high": 100.0, "low": 90.0, "close": 95.0, "volume": -10.0}]
        with pytest.raises(ValueError, match="negative volume"):
            classifier.calculate_volume_profile_poc(candles)

    def test_poc_raises_on_high_less_than_low(self, classifier):
        """Test that POC raises ValueError when high < low."""
        candles = [{"high": 90.0, "low": 100.0, "close": 95.0, "volume": 100.0}]
        with pytest.raises(ValueError, match="high < low"):
            classifier.calculate_volume_profile_poc(candles)


# ---------------------------------------------------------------------------
# Zone Classification Tests
# ---------------------------------------------------------------------------


class TestZoneClassification:
    """Tests for premium/discount/equilibrium zone classification."""

    def test_premium_zone(self, classifier, sample_candles):
        """Test classification when price is above fair value."""
        result = classifier.classify(
            current_price=60000.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        assert result.zone == ZoneType.PREMIUM
        assert result.current_price == 60000.0
        assert result.deviation_pct > 0

    def test_discount_zone(self, classifier, sample_candles):
        """Test classification when price is below fair value."""
        result = classifier.classify(
            current_price=10000.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        assert result.zone == ZoneType.DISCOUNT
        assert result.current_price == 10000.0
        assert result.deviation_pct < 0

    def test_equilibrium_zone(self, classifier, sample_candles):
        """Test classification when price is near fair value."""
        # First get the fair value, then classify at fair value
        fv_result = classifier.calculate_vwap(sample_candles)
        result = classifier.classify_with_manual_fv(
            current_price=fv_result.value,
            fair_value=fv_result.value,
            method=FairValueMethod.VWAP,
        )

        assert result.zone == ZoneType.EQUILIBRIUM
        assert result.deviation_pct == 0.0

    def test_premium_boundary(self, classifier, sample_candles):
        """Test that price just above premium boundary is premium."""
        fv_result = classifier.calculate_vwap(sample_candles)
        # Classify at fair value first to get boundaries
        base = classifier.classify_with_manual_fv(
            current_price=fv_result.value,
            fair_value=fv_result.value,
            method=FairValueMethod.VWAP,
        )
        # Price just above premium boundary
        just_above = base.premium_boundary + 0.01
        result = classifier.classify_with_manual_fv(
            current_price=just_above,
            fair_value=fv_result.value,
            method=FairValueMethod.VWAP,
        )

        assert result.zone == ZoneType.PREMIUM

    def test_discount_boundary(self, classifier, sample_candles):
        """Test that price just below discount boundary is discount."""
        fv_result = classifier.calculate_vwap(sample_candles)
        base = classifier.classify_with_manual_fv(
            current_price=fv_result.value,
            fair_value=fv_result.value,
            method=FairValueMethod.VWAP,
        )
        just_below = base.discount_boundary - 0.01
        result = classifier.classify_with_manual_fv(
            current_price=just_below,
            fair_value=fv_result.value,
            method=FairValueMethod.VWAP,
        )

        assert result.zone == ZoneType.DISCOUNT

    def test_wide_equilibrium(self, wide_equilibrium_classifier, sample_candles):
        """Test that wider equilibrium zone captures more prices."""
        fv_result = wide_equilibrium_classifier.calculate_vwap(sample_candles)

        # A price 0.5% away should still be equilibrium with 1.0% width
        offset_price = fv_result.value * 1.005
        result = wide_equilibrium_classifier.classify_with_manual_fv(
            current_price=offset_price,
            fair_value=fv_result.value,
            method=FairValueMethod.VWAP,
        )

        assert result.zone == ZoneType.EQUILIBRIUM

    def test_classify_with_poc_method(self, classifier, sample_candles):
        """Test classification using Volume Profile POC method."""
        result = classifier.classify(
            current_price=60000.0,
            candles=sample_candles,
            method=FairValueMethod.VOLUME_PROFILE_POC,
            force_recalculate=True,
        )

        assert result.method == FairValueMethod.VOLUME_PROFILE_POC
        assert result.zone == ZoneType.PREMIUM

    def test_deviation_pct_calculation(self, classifier):
        """Test deviation percentage is calculated correctly."""
        # 2% above fair value of 100
        result = classifier.classify_with_manual_fv(
            current_price=102.0,
            fair_value=100.0,
            method=FairValueMethod.VWAP,
        )

        assert result.deviation_pct == pytest.approx(2.0)

    def test_distance_from_fv(self, classifier):
        """Test distance from fair value is calculated correctly."""
        result = classifier.classify_with_manual_fv(
            current_price=105.0,
            fair_value=100.0,
            method=FairValueMethod.VWAP,
        )

        assert result.distance_from_fv == pytest.approx(5.0)

    def test_to_dict(self, classifier, sample_candles):
        """Test serialization to dictionary."""
        result = classifier.classify(
            current_price=50500.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        d = result.to_dict()
        assert isinstance(d, dict)
        assert "zone" in d
        assert "fair_value" in d
        assert "current_price" in d
        assert "deviation_pct" in d
        assert "premium_boundary" in d
        assert "discount_boundary" in d
        assert d["zone"] in ("premium", "discount", "equilibrium")


# ---------------------------------------------------------------------------
# Cache and Refresh Interval Tests
# ---------------------------------------------------------------------------


class TestCacheAndRefresh:
    """Tests for caching and refresh interval behavior."""

    def test_cache_prevents_recalculation(self, classifier, sample_candles):
        """Test that classify uses cached fair value within refresh interval."""
        # First classification - calculates fair value
        result1 = classifier.classify(
            current_price=50500.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        # Second classification with different candles - should use cache
        different_candles = [
            {"high": 60000.0, "low": 58000.0, "close": 59000.0, "volume": 999.0}
        ]
        result2 = classifier.classify(
            current_price=50500.0,
            candles=different_candles,
            method=FairValueMethod.VWAP,
        )

        # Fair value should be the same (cached)
        assert result1.fair_value == result2.fair_value

    def test_force_recalculate_bypasses_cache(self, classifier, sample_candles):
        """Test that force_recalculate bypasses the cache."""
        result1 = classifier.classify(
            current_price=50500.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        # Force recalculate with very different candles
        different_candles = [
            {"high": 100.0, "low": 90.0, "close": 95.0, "volume": 1000.0}
            for _ in range(100)
        ]
        result2 = classifier.classify(
            current_price=50500.0,
            candles=different_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        # Fair values should differ
        assert result1.fair_value != result2.fair_value

    def test_refresh_interval_expired(self, classifier, sample_candles):
        """Test that cache expires after refresh interval."""
        # Create classifier with very short refresh interval
        fast_classifier = PremiumDiscountClassifier(refresh_interval_seconds=0.01)

        result1 = fast_classifier.classify(
            current_price=50500.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        # Wait for cache to expire
        time.sleep(0.02)

        # Different candles should now produce different fair value
        different_candles = [
            {"high": 100.0, "low": 90.0, "close": 95.0, "volume": 1000.0}
            for _ in range(100)
        ]
        result2 = fast_classifier.classify(
            current_price=50500.0,
            candles=different_candles,
            method=FairValueMethod.VWAP,
        )

        assert result1.fair_value != result2.fair_value

    def test_reset_cache(self, classifier, sample_candles):
        """Test that reset_cache forces recalculation."""
        result1 = classifier.classify(
            current_price=50500.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        classifier.reset_cache()

        # Verify cache is cleared
        assert classifier._cached_fair_value is None
        assert classifier._last_calculation_time == 0.0

    def test_default_refresh_is_300_seconds(self, classifier):
        """Test that default refresh interval is 300 seconds (5 minutes)."""
        assert classifier.refresh_interval_seconds == 300


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for validation and error handling."""

    def test_raises_on_negative_current_price(self, classifier, sample_candles):
        """Test that negative current price raises ValueError."""
        with pytest.raises(ValueError, match="current_price must be positive"):
            classifier.classify(
                current_price=-100.0,
                candles=sample_candles,
                method=FairValueMethod.VWAP,
            )

    def test_raises_on_zero_current_price(self, classifier, sample_candles):
        """Test that zero current price raises ValueError."""
        with pytest.raises(ValueError, match="current_price must be positive"):
            classifier.classify(
                current_price=0.0,
                candles=sample_candles,
                method=FairValueMethod.VWAP,
            )

    def test_raises_on_negative_equilibrium_width(self):
        """Test that negative equilibrium width raises ValueError."""
        with pytest.raises(
            ValueError, match="equilibrium_width_pct must be non-negative"
        ):
            PremiumDiscountClassifier(equilibrium_width_pct=-0.1)

    def test_raises_on_zero_refresh_interval(self):
        """Test that zero refresh interval raises ValueError."""
        with pytest.raises(
            ValueError, match="refresh_interval_seconds must be positive"
        ):
            PremiumDiscountClassifier(refresh_interval_seconds=0)

    def test_raises_on_negative_fair_value_manual(self, classifier):
        """Test that negative fair value raises in manual classify."""
        with pytest.raises(ValueError, match="fair_value must be positive"):
            classifier.classify_with_manual_fv(
                current_price=100.0,
                fair_value=-50.0,
                method=FairValueMethod.VWAP,
            )

    def test_raises_on_zero_fair_value_manual(self, classifier):
        """Test that zero fair value raises in manual classify."""
        with pytest.raises(ValueError, match="fair_value must be positive"):
            classifier.classify_with_manual_fv(
                current_price=100.0,
                fair_value=0.0,
                method=FairValueMethod.VWAP,
            )

    def test_zero_equilibrium_width_allowed(self):
        """Test that zero equilibrium width is allowed (narrow zones)."""
        classifier = PremiumDiscountClassifier(equilibrium_width_pct=0.0)
        result = classifier.classify_with_manual_fv(
            current_price=100.01,
            fair_value=100.0,
            method=FairValueMethod.VWAP,
        )
        assert result.zone == ZoneType.PREMIUM


# ---------------------------------------------------------------------------
# FairValueResult Tests
# ---------------------------------------------------------------------------


class TestFairValueResult:
    """Tests for FairValueResult dataclass."""

    def test_frozen_dataclass(self):
        """Test that FairValueResult is immutable."""
        result = FairValueResult(
            value=50000.0,
            method=FairValueMethod.VWAP,
            confidence=0.8,
            data_points=100,
            timestamp=1000.0,
        )
        with pytest.raises(AttributeError):
            result.value = 60000.0

    def test_all_fields_present(self):
        """Test that all expected fields are present."""
        result = FairValueResult(
            value=50000.0,
            method=FairValueMethod.VOLUME_PROFILE_POC,
            confidence=0.9,
            data_points=50,
            timestamp=2000.0,
        )
        assert result.value == 50000.0
        assert result.method == FairValueMethod.VOLUME_PROFILE_POC
        assert result.confidence == 0.9
        assert result.data_points == 50
        assert result.timestamp == 2000.0


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestPremiumDiscountIntegration:
    """Integration tests combining multiple components."""

    def test_full_workflow_vwap(self, classifier, sample_candles):
        """Test full classify workflow with VWAP."""
        result = classifier.classify(
            current_price=50500.0,
            candles=sample_candles,
            method=FairValueMethod.VWAP,
            force_recalculate=True,
        )

        assert result.zone in (
            ZoneType.PREMIUM,
            ZoneType.DISCOUNT,
            ZoneType.EQUILIBRIUM,
        )
        assert result.fair_value > 0
        assert result.premium_boundary > result.discount_boundary
        assert result.premium_boundary > result.fair_value
        assert result.discount_boundary < result.fair_value

    def test_full_workflow_poc(self, classifier, sample_candles):
        """Test full classify workflow with Volume Profile POC."""
        result = classifier.classify(
            current_price=49500.0,
            candles=sample_candles,
            method=FairValueMethod.VOLUME_PROFILE_POC,
            force_recalculate=True,
        )

        assert result.zone in (
            ZoneType.PREMIUM,
            ZoneType.DISCOUNT,
            ZoneType.EQUILIBRIUM,
        )
        assert result.method == FairValueMethod.VOLUME_PROFILE_POC
        assert result.premium_boundary > result.discount_boundary

    def test_boundary_symmetry(self, classifier):
        """Test that premium and discount boundaries are symmetric around FV."""
        fv = 50000.0
        result = classifier.classify_with_manual_fv(
            current_price=fv,
            fair_value=fv,
            method=FairValueMethod.VWAP,
        )

        upper_delta = result.premium_boundary - fv
        lower_delta = fv - result.discount_boundary
        assert upper_delta == pytest.approx(lower_delta)

    @pytest.mark.parametrize(
        "price_offset_pct,expected_zone",
        [
            (2.0, ZoneType.PREMIUM),
            (1.0, ZoneType.PREMIUM),
            (-2.0, ZoneType.DISCOUNT),
            (-1.0, ZoneType.DISCOUNT),
            (0.0, ZoneType.EQUILIBRIUM),
            (0.05, ZoneType.EQUILIBRIUM),
            (-0.05, ZoneType.EQUILIBRIUM),
        ],
    )
    def test_zone_classification_parametric(
        self, price_offset_pct, expected_zone, classifier
    ):
        """Parametric test for zone classification at various offsets."""
        fv = 50000.0
        price = fv * (1.0 + price_offset_pct / 100.0)

        result = classifier.classify_with_manual_fv(
            current_price=price,
            fair_value=fv,
            method=FairValueMethod.VWAP,
        )

        assert result.zone == expected_zone, (
            f"Price {price} (offset {price_offset_pct}%) should be "
            f"{expected_zone.value}, got {result.zone.value}"
        )
