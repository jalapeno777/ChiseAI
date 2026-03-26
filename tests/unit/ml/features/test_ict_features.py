"""Tests for ICT Feature Engineering Pipeline.

ST-ICT-028-A: ICT Feature Engineering Pipeline Tests
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.ml.features.ict_features import (
    FEATURE_COMBINED_ICT_SCORE,
    FEATURE_CVD_BEARISH_DIVERGENCE,
    FEATURE_CVD_BULLISH_DIVERGENCE,
    FEATURE_CVD_MOMENTUM,
    FEATURE_CVD_SLOPE,
    FEATURE_FVG_50_CE_HIT_RATIO,
    FEATURE_FVG_BEARISH_COUNT,
    FEATURE_FVG_BULLISH_COUNT,
    FEATURE_FVG_MITIGATED_RATIO,
    FEATURE_OB_BEARISH_COUNT,
    FEATURE_OB_BULLISH_COUNT,
    FEATURE_OB_MITIGATED_RATIO,
    FEATURE_REGIME,
    ICTFeatureExtractor,
    ICTFeatureExtractorConfig,
    ICTFeatures,
    MarketRegime,
    normalize_ict_features,
)


class MockCVDResult:
    """Mock CVD result for testing."""

    def __init__(
        self,
        timestamps: list[datetime] | None = None,
        cvd_values: list[float] | None = None,
        trade_count: int = 0,
        buy_volume: float = 0.0,
        sell_volume: float = 0.0,
        net_volume: float = 0.0,
    ):
        self.timestamps = timestamps or []
        self.cvd_values = cvd_values or []
        self.trade_count = trade_count
        self.buy_volume = buy_volume
        self.sell_volume = sell_volume
        self.net_volume = net_volume


class MockFVG:
    """Mock FVG for testing."""

    def __init__(
        self,
        direction: str = "bullish",
        timestamp: int = 0,
        high: float = 100.0,
        low: float = 99.0,
        mitigation: str = "none",
        ce50_reached: bool = False,
    ):
        self.direction = MagicMock()
        self.direction.value = direction
        self.timestamp = timestamp
        self.high = high
        self.low = low
        self.mitigation = MagicMock()
        self.mitigation.value = mitigation
        self.ce50_reached = ce50_reached


class MockOrderBlock:
    """Mock Order Block for testing."""

    def __init__(
        self,
        direction: str = "bullish",
        mitigated: bool = False,
    ):
        self.direction = direction
        self.is_mitigated = mitigated


class TestICTFeatures:
    """Tests for ICTFeatures dataclass."""

    def test_ict_features_creation(self):
        """Test ICTFeatures creation with all fields."""
        timestamp = datetime.now(UTC)
        features = ICTFeatures(
            timestamp=timestamp,
            token="BTC/USDT",
            timeframe="1h",
            cvd_slope=0.5,
            cvd_momentum=0.3,
            cvd_bullish_divergence=0.8,
            cvd_bearish_divergence=0.1,
            fvg_bullish_count=2,
            fvg_bearish_count=1,
            fvg_mitigated_ratio=0.33,
            fvg_50ce_hit_ratio=0.5,
            ob_bullish_count=3,
            ob_bearish_count=1,
            ob_mitigated_ratio=0.25,
            combined_ict_score=0.65,
            regime=MarketRegime.BULLISH,
        )

        assert features.token == "BTC/USDT"
        assert features.timeframe == "1h"
        assert features.cvd_slope == 0.5
        assert features.fvg_bullish_count == 2
        assert features.regime == MarketRegime.BULLISH
        assert features.combined_ict_score == 0.65

    def test_features_dict_creation(self):
        """Test that features_dict is correctly built."""
        features = ICTFeatures(
            timestamp=datetime.now(UTC),
            token="ETH/USDT",
            timeframe="4h",
            cvd_slope=0.1,
            cvd_momentum=-0.2,
            cvd_bullish_divergence=0.0,
            cvd_bearish_divergence=0.7,
            fvg_bullish_count=0,
            fvg_bearish_count=3,
            fvg_mitigated_ratio=1.0,
            fvg_50ce_hit_ratio=1.0,
            ob_bullish_count=1,
            ob_bearish_count=2,
            ob_mitigated_ratio=0.5,
            combined_ict_score=-0.4,
            regime=MarketRegime.BEARISH,
        )

        assert FEATURE_CVD_SLOPE in features.features_dict
        assert FEATURE_CVD_MOMENTUM in features.features_dict
        assert FEATURE_FVG_BULLISH_COUNT in features.features_dict
        assert FEATURE_REGIME in features.features_dict
        assert features.features_dict[FEATURE_REGIME] == "bearish"

    def test_to_training_sample(self):
        """Test conversion to ML training sample format."""
        timestamp = datetime.now(UTC)
        features = ICTFeatures(
            timestamp=timestamp,
            token="BTC/USDT",
            timeframe="1h",
            cvd_slope=0.5,
            regime=MarketRegime.NEUTRAL,
        )

        sample = features.to_training_sample(label=1)

        assert sample["token"] == "BTC/USDT"
        assert sample["timeframe"] == "1h"
        assert sample["outcome"] == 1
        assert sample[FEATURE_CVD_SLOPE] == 0.5

    def test_to_training_sample_without_label(self):
        """Test conversion without label."""
        features = ICTFeatures(
            timestamp=datetime.now(UTC),
            token="BTC/USDT",
            timeframe="1h",
            cvd_slope=0.5,
        )

        sample = features.to_training_sample()

        assert "outcome" not in sample
        assert sample["token"] == "BTC/USDT"

    def test_feature_names(self):
        """Test feature_names property."""
        features = ICTFeatures(
            timestamp=datetime.now(UTC),
            token="BTC/USDT",
            timeframe="1h",
        )

        names = features.feature_names
        assert len(names) > 0
        assert FEATURE_CVD_SLOPE in names

    def test_feature_values(self):
        """Test feature_values property."""
        features = ICTFeatures(
            timestamp=datetime.now(UTC),
            token="BTC/USDT",
            timeframe="1h",
            cvd_slope=0.5,
            cvd_momentum=0.3,
        )

        values = features.feature_values
        assert len(values) == len(features.feature_names)
        assert 0.5 in values


class TestICTFeatureExtractorConfig:
    """Tests for ICTFeatureExtractorConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = ICTFeatureExtractorConfig()

        assert config.cvd_window_size == 20
        assert config.cvd_momentum_window == 10
        assert config.fvg_lookback_count == 5
        assert config.ob_lookback_count == 5
        assert "cvd" in config.score_weights
        assert "fvg" in config.score_weights
        assert "ob" in config.score_weights

    def test_custom_config(self):
        """Test custom configuration."""
        config = ICTFeatureExtractorConfig(
            cvd_window_size=50,
            divergence_threshold=0.1,
            score_weights={"cvd": 0.5, "fvg": 0.25, "ob": 0.25},
        )

        assert config.cvd_window_size == 50
        assert config.divergence_threshold == 0.1
        assert config.score_weights["cvd"] == 0.5


class TestICTFeatureExtractor:
    """Tests for ICTFeatureExtractor."""

    def test_extractor_initialization(self):
        """Test extractor initialization."""
        extractor = ICTFeatureExtractor()
        assert extractor.config.cvd_window_size == 20

        config = ICTFeatureExtractorConfig(cvd_window_size=30)
        extractor_with_config = ICTFeatureExtractor(config=config)
        assert extractor_with_config.config.cvd_window_size == 30

    def test_extract_with_no_data(self):
        """Test extraction with no signal data."""
        extractor = ICTFeatureExtractor()
        features = extractor.extract(
            token="BTC/USDT",
            timeframe="1h",
            regime=MarketRegime.NEUTRAL,
        )

        assert features.token == "BTC/USDT"
        assert features.timeframe == "1h"
        assert features.cvd_slope == 0.0
        assert features.fvg_bullish_count == 0
        assert features.ob_bullish_count == 0
        assert features.regime == MarketRegime.NEUTRAL

    def test_extract_with_cvd_data(self):
        """Test extraction with CVD data."""
        # Use smaller window to have enough data for momentum calculation
        # cvd_window_size=3 gives us 3 values, momentum_window=3 needs 6 values
        # so we need at least 6 cvd_values total
        extractor = ICTFeatureExtractor(
            config=ICTFeatureExtractorConfig(cvd_window_size=3, cvd_momentum_window=3)
        )

        # Create mock CVD result with increasing values (need at least 6 for momentum)
        timestamps = [datetime.now(UTC) for _ in range(10)]
        cvd_values = list(range(10))  # 0, 1, 2, ..., 9
        cvd_result = MockCVDResult(timestamps=timestamps, cvd_values=cvd_values)

        features = extractor.extract(
            token="BTC/USDT",
            timeframe="1h",
            cvd_result=cvd_result,
            regime=MarketRegime.BULLISH,
        )

        assert features.cvd_slope > 0  # Should have positive slope
        assert features.cvd_momentum > 0  # Should have positive momentum

    def test_extract_with_fvg_data(self):
        """Test extraction with FVG data."""
        extractor = ICTFeatureExtractor()

        fvgs = [
            MockFVG(direction="bullish", mitigation="none", ce50_reached=False),
            MockFVG(direction="bullish", mitigation="wick", ce50_reached=True),
            MockFVG(direction="bearish", mitigation="close", ce50_reached=True),
            MockFVG(direction="bullish", mitigation="full", ce50_reached=True),
        ]

        features = extractor.extract(
            token="BTC/USDT",
            timeframe="1h",
            fvgs=fvgs,
            regime=MarketRegime.BULLISH,
        )

        assert features.fvg_bullish_count == 3
        assert features.fvg_bearish_count == 1
        assert features.fvg_mitigated_ratio == 0.75  # 3/4 mitigated
        assert features.fvg_50ce_hit_ratio == 0.75  # 3/4 with CE50 hit

    def test_extract_with_order_block_data(self):
        """Test extraction with Order Block data."""
        extractor = ICTFeatureExtractor()

        order_blocks = [
            MockOrderBlock(direction="bullish", mitigated=False),
            MockOrderBlock(direction="bullish", mitigated=True),
            MockOrderBlock(direction="bearish", mitigated=True),
        ]

        features = extractor.extract(
            token="ETH/USDT",
            timeframe="4h",
            order_blocks=order_blocks,
            regime=MarketRegime.BEARISH,
        )

        assert features.ob_bullish_count == 2
        assert features.ob_bearish_count == 1
        assert features.ob_mitigated_ratio == pytest.approx(0.667, rel=0.1)

    def test_extract_combined_score_bullish(self):
        """Test combined ICT score calculation for bullish setup."""
        extractor = ICTFeatureExtractor()

        # Create bullish setup
        fvgs = [
            MockFVG(direction="bullish", mitigation="none"),
            MockFVG(direction="bullish", mitigation="none"),
            MockFVG(direction="bullish", mitigation="none"),
        ]
        order_blocks = [
            MockOrderBlock(direction="bullish", mitigated=False),
            MockOrderBlock(direction="bullish", mitigated=False),
        ]

        features = extractor.extract(
            token="BTC/USDT",
            timeframe="1h",
            fvgs=fvgs,
            order_blocks=order_blocks,
            regime=MarketRegime.BULLISH,
            current_price=50000.0,
        )

        assert features.combined_ict_score > 0  # Should be bullish

    def test_extract_combined_score_bearish(self):
        """Test combined ICT score calculation for bearish setup."""
        extractor = ICTFeatureExtractor()

        # Create bearish setup
        fvgs = [
            MockFVG(direction="bearish", mitigation="none"),
            MockFVG(direction="bearish", mitigation="none"),
        ]
        order_blocks = [
            MockOrderBlock(direction="bearish", mitigated=False),
            MockOrderBlock(direction="bearish", mitigated=False),
        ]

        features = extractor.extract(
            token="BTC/USDT",
            timeframe="1h",
            fvgs=fvgs,
            order_blocks=order_blocks,
            regime=MarketRegime.BEARISH,
            current_price=50000.0,
        )

        # With BEARISH regime and bearish signals, the score should be positive
        # because regime multiplier (-1.0) flips negative raw_score to positive
        # This indicates aligned/confirmed bearish setup
        assert features.combined_ict_score > 0  # Should be positive (aligned)

    def test_extract_batch(self):
        """Test batch extraction."""
        extractor = ICTFeatureExtractor()

        samples = [
            {
                "token": "BTC/USDT",
                "timeframe": "1h",
                "regime": MarketRegime.BULLISH,
                "fvgs": [MockFVG(direction="bullish")],
            },
            {
                "token": "ETH/USDT",
                "timeframe": "1h",
                "regime": MarketRegime.BEARISH,
                "fvgs": [MockFVG(direction="bearish")],
            },
        ]

        features_list = extractor.extract_batch(
            token="BTC/USDT",
            timeframe="1h",
            samples=samples,
        )

        assert len(features_list) == 2
        assert features_list[0].regime == MarketRegime.BULLISH
        assert features_list[1].regime == MarketRegime.BEARISH


class TestNormalizeICTFeatures:
    """Tests for normalize_ict_features function."""

    def test_normalize_with_no_stats(self):
        """Test normalization with no statistics (should return same)."""
        features = ICTFeatures(
            timestamp=datetime.now(UTC),
            token="BTC/USDT",
            timeframe="1h",
            cvd_slope=0.5,
        )

        normalized = normalize_ict_features(features, None)

        assert normalized.cvd_slope == features.cvd_slope

    def test_normalize_with_stats(self):
        """Test normalization with statistics."""
        features = ICTFeatures(
            timestamp=datetime.now(UTC),
            token="BTC/USDT",
            timeframe="1h",
            cvd_slope=0.5,
            cvd_momentum=0.3,
        )

        stats = {
            FEATURE_CVD_SLOPE: {"mean": 0.0, "std": 0.5},
            FEATURE_CVD_MOMENTUM: {"mean": 0.1, "std": 0.2},
        }

        normalized = normalize_ict_features(features, stats)

        # 0.5 normalized with mean=0, std=0.5 should be 1.0
        assert normalized.cvd_slope == pytest.approx(1.0, rel=0.01)
        # 0.3 normalized with mean=0.1, std=0.2 should be 1.0
        assert normalized.cvd_momentum == pytest.approx(1.0, rel=0.01)


class TestMarketRegime:
    """Tests for MarketRegime enum."""

    def test_market_regime_values(self):
        """Test MarketRegime enum values."""
        assert MarketRegime.BULLISH.value == "bullish"
        assert MarketRegime.BEARISH.value == "bearish"
        assert MarketRegime.NEUTRAL.value == "neutral"
        assert MarketRegime.TRANSITIONAL.value == "transitional"


class TestFeatureNames:
    """Tests for feature name constants."""

    def test_all_feature_constants_defined(self):
        """Test all feature constants are properly defined."""
        assert FEATURE_CVD_SLOPE == "cvd_slope"
        assert FEATURE_CVD_MOMENTUM == "cvd_momentum"
        assert FEATURE_CVD_BULLISH_DIVERGENCE == "cvd_bullish_divergence"
        assert FEATURE_CVD_BEARISH_DIVERGENCE == "cvd_bearish_divergence"
        assert FEATURE_FVG_BULLISH_COUNT == "fvg_bullish_count"
        assert FEATURE_FVG_BEARISH_COUNT == "fvg_bearish_count"
        assert FEATURE_FVG_MITIGATED_RATIO == "fvg_mitigated_ratio"
        assert FEATURE_FVG_50_CE_HIT_RATIO == "fvg_50ce_hit_ratio"
        assert FEATURE_OB_BULLISH_COUNT == "ob_bullish_count"
        assert FEATURE_OB_BEARISH_COUNT == "ob_bearish_count"
        assert FEATURE_OB_MITIGATED_RATIO == "ob_mitigated_ratio"
        assert FEATURE_COMBINED_ICT_SCORE == "combined_ict_score"
        assert FEATURE_REGIME == "market_regime"
