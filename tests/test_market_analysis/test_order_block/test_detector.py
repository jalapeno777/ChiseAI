"""Tests for Order Block Detector.

Tests bullish and bearish order block detection, regime gating,
volume confirmation, and integration with Zone types.
"""

from dataclasses import dataclass
from datetime import datetime

import pytest
from src.market_analysis.order_block import (
    OBPolaridade,
    OrderBlockConfig,
    OrderBlockDetector,
)
from src.market_analysis.regime import (
    RegimeClassification,
    UnifiedRegime,
    VolatilityRegime,
)


@dataclass
class MockOHLCV:
    """Mock OHLCV candle for testing."""

    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float = 0.0
    token: str = "BTC/USDT"
    timeframe: str = "1H"


class TestBullishOBDetection:
    """Tests for bullish order block detection."""

    def test_detects_bullish_ob_basic(self):
        """Test basic bullish OB detection with clear pattern."""
        # Create candles: bearish consolidation then strong bullish momentum
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),  # Bullish - ignore
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),  # Bearish anchor
            MockOHLCV(
                datetime(2024, 1, 3), 101, 115, 100, 114
            ),  # Strong bullish momentum
            MockOHLCV(datetime(2024, 1, 4), 114, 118, 113, 116),
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles)

        assert len(results) >= 1
        bullish_obs = [r for r in results if r.polarity == OBPolaridade.BULLISH]
        assert len(bullish_obs) >= 1

        ob = bullish_obs[0]
        assert ob.zone.zone_type.value == "OB"
        assert ob.strength_score > 0.0

    def test_bullish_ob_with_configurable_threshold(self):
        """Test that momentum threshold affects detection."""
        # Create candles with moderate bullish momentum
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 102, 103),  # Small bearish anchor
            MockOHLCV(
                datetime(2024, 1, 3), 103, 110, 102, 108
            ),  # Moderate bullish momentum
        ]

        # With high threshold, should not detect
        config = OrderBlockConfig(momentum_threshold=0.9)
        detector = OrderBlockDetector(config)
        results = detector.detect(candles)
        bullish_obs = [r for r in results if r.polarity == OBPolaridade.BULLISH]
        assert len(bullish_obs) == 0

        # With low threshold, should detect
        config = OrderBlockConfig(momentum_threshold=0.3)
        detector = OrderBlockDetector(config)
        results = detector.detect(candles)
        bullish_obs = [r for r in results if r.polarity == OBPolaridade.BULLISH]
        assert len(bullish_obs) >= 1

    def test_bullish_ob_volume_confirmation(self):
        """Test volume confirmation requirement."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),  # Bearish anchor
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),  # Strong bullish
        ]
        volume_data = [1000, 1000, 2000]  # High volume on momentum

        # Without volume requirement, should detect
        config = OrderBlockConfig(require_volume_confirmation=False)
        detector = OrderBlockDetector(config)
        results = detector.detect(candles, volume_data=volume_data)
        bullish_obs = [r for r in results if r.polarity == OBPolaridade.BULLISH]
        assert len(bullish_obs) >= 1

        # With volume confirmation, should still detect with high volume
        config = OrderBlockConfig(
            require_volume_confirmation=True, volume_threshold_multiplier=1.2
        )
        detector = OrderBlockDetector(config)
        results = detector.detect(candles, volume_data=volume_data)
        bullish_obs = [r for r in results if r.polarity == OBPolaridade.BULLISH]
        assert len(bullish_obs) >= 1
        assert bullish_obs[0].volume_confirmed is True


class TestBearishOBDetection:
    """Tests for bearish order block detection."""

    def test_detects_bearish_ob_basic(self):
        """Test basic bearish OB detection with clear pattern."""
        # Create candles: bullish consolidation then strong bearish momentum
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),  # Bullish
            MockOHLCV(datetime(2024, 1, 2), 102, 110, 100, 108),  # Bullish anchor
            MockOHLCV(
                datetime(2024, 1, 3), 108, 110, 85, 86
            ),  # Strong bearish momentum
            MockOHLCV(datetime(2024, 1, 4), 86, 88, 80, 82),
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles)

        assert len(results) >= 1
        bearish_obs = [r for r in results if r.polarity == OBPolaridade.BEARISH]
        assert len(bearish_obs) >= 1

        ob = bearish_obs[0]
        assert ob.zone.zone_type.value == "OB"
        assert ob.strength_score > 0.0

    def test_bearish_ob_requires_bullish_anchor(self):
        """Test that bearish OB requires bullish anchor candle."""
        # Create candles: bearish consolidation (wrong pattern)
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(
                datetime(2024, 1, 2), 105, 108, 100, 101
            ),  # Bearish - not valid anchor
            MockOHLCV(
                datetime(2024, 1, 3), 101, 110, 85, 86
            ),  # Strong bearish momentum
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles)
        bearish_obs = [r for r in results if r.polarity == OBPolaridade.BEARISH]
        # Should not detect bearish OB because anchor is bearish
        assert len(bearish_obs) == 0


class TestRegimeGating:
    """Tests for regime-gated activation."""

    def test_ob_detected_in_trending_regime(self):
        """Test OB is detected when regime is trending."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),
        ]

        regime = RegimeClassification(
            regime=UnifiedRegime.TRENDING,
            confidence=0.8,
            adx_value=30.0,
        )

        detector = OrderBlockDetector()
        results = detector.detect(candles, regime=regime)
        assert len(results) >= 1

    def test_ob_not_detected_in_ranging_regime(self):
        """Test OB is not detected when regime is ranging."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),
        ]

        regime = RegimeClassification(
            regime=UnifiedRegime.RANGING,
            confidence=0.7,
            adx_value=15.0,
        )

        config = OrderBlockConfig(regime_filter=[UnifiedRegime.TRENDING])
        detector = OrderBlockDetector(config)
        results = detector.detect(candles, regime=regime)
        assert len(results) == 0

    def test_ob_not_detected_in_volatile_regime(self):
        """Test OB is not detected when regime is volatile."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),
        ]

        regime = RegimeClassification(
            regime=UnifiedRegime.VOLATILE,
            confidence=0.6,
            adx_value=35.0,
            volatility_regime=VolatilityRegime.HIGH,
        )

        config = OrderBlockConfig(regime_filter=[UnifiedRegime.TRENDING])
        detector = OrderBlockDetector(config)
        results = detector.detect(candles, regime=regime)
        assert len(results) == 0

    def test_ob_without_regime_still_detects(self):
        """Test OB detection works without regime classification."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles, regime=None)
        assert len(results) >= 1


class TestOrderBlockZone:
    """Tests for OB zone creation and properties."""

    def test_ob_zone_has_correct_type(self):
        """Test that detected OB has ZoneType.OB."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles)

        for result in results:
            assert result.zone.zone_type.value == "OB"

    def test_ob_zone_has_valid_price_range(self):
        """Test that OB zone has valid high > low price range."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles)

        for result in results:
            assert result.zone.price_range.high > result.zone.price_range.low

    def test_ob_zone_contains_anchor_candle(self):
        """Test that OB zone contains the anchor candle range."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),  # Bearish anchor
            MockOHLCV(datetime(2024, 1, 3), 101, 115, 100, 114),  # Strong bullish
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles)
        bullish_obs = [r for r in results if r.polarity == OBPolaridade.BULLISH]

        if len(bullish_obs) > 0:
            ob = bullish_obs[0]
            anchor_idx = ob.anchor_candle_index
            anchor = candles[anchor_idx]
            # OB zone should extend beyond anchor candle
            assert ob.zone.price_range.high >= anchor.high_price
            assert ob.zone.price_range.low <= anchor.low_price


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_insufficient_candles(self):
        """Test that detection fails gracefully with insufficient candles."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),
        ]

        detector = OrderBlockDetector()
        results = detector.detect(candles)
        assert len(results) == 0

    def test_empty_candles(self):
        """Test that empty candle list returns empty results."""
        candles = []

        detector = OrderBlockDetector()
        results = detector.detect(candles)
        assert len(results) == 0

    def test_multiple_consolidation_bars(self):
        """Test OB detection with multiple consolidation bars."""
        candles = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 107, 101, 102),  # Consolidation
            MockOHLCV(datetime(2024, 1, 3), 102, 108, 100, 103),  # Consolidation
            MockOHLCV(datetime(2024, 1, 4), 103, 120, 100, 118),  # Strong bullish
        ]

        config = OrderBlockConfig(min_consolidation_bars=1, max_consolidation_bars=5)
        detector = OrderBlockDetector(config)
        results = detector.detect(candles)

        # Should detect OB with multi-bar consolidation
        assert len(results) >= 1


class TestOrderBlockStrength:
    """Tests for order block strength scoring."""

    def test_stronger_momentum_higher_score(self):
        """Test that stronger momentum candles produce higher strength scores."""
        # Weak momentum
        candles_weak = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 103),  # Weak bearish
            MockOHLCV(datetime(2024, 1, 3), 103, 108, 102, 107),  # Weak bullish
        ]

        # Strong momentum
        candles_strong = [
            MockOHLCV(datetime(2024, 1, 1), 100, 105, 98, 102),
            MockOHLCV(datetime(2024, 1, 2), 105, 108, 100, 101),  # Strong bearish
            MockOHLCV(datetime(2024, 1, 3), 101, 120, 100, 118),  # Strong bullish
        ]

        detector = OrderBlockDetector()
        results_weak = detector.detect(candles_weak)
        results_strong = detector.detect(candles_strong)

        if len(results_weak) > 0 and len(results_strong) > 0:
            weak_score = max(
                r.strength_score
                for r in results_weak
                if r.polarity == OBPolaridade.BULLISH
            )
            strong_score = max(
                r.strength_score
                for r in results_strong
                if r.polarity == OBPolaridade.BULLISH
            )
            assert strong_score > weak_score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
