"""Unit tests for feature extraction module.

Tests FeatureExtractor and related components.
"""

from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from market_analysis.signal_storage.models import (
    SignalDirection,
    SignalRecord,
)
from ml.training.extractor import (
    ExtractedFeatures,
    FeatureExtractor,
    MarketContext,
    TechnicalIndicators,
)


class TestTechnicalIndicators:
    """Tests for TechnicalIndicators dataclass."""

    def test_default_creation(self):
        """Test creating indicators with defaults."""
        indicators = TechnicalIndicators()
        assert indicators.rsi is None
        assert indicators.macd is None
        assert indicators.macd_signal is None

    def test_creation_with_values(self):
        """Test creating indicators with values."""
        indicators = TechnicalIndicators(
            rsi=65.5,
            macd=0.5,
            macd_signal=0.3,
            macd_histogram=0.2,
            bb_upper=45000.0,
            bb_lower=44000.0,
        )
        assert indicators.rsi == 65.5
        assert indicators.macd == 0.5
        assert indicators.macd_signal == 0.3
        assert indicators.macd_histogram == 0.2
        assert indicators.bb_upper == 45000.0
        assert indicators.bb_lower == 44000.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        indicators = TechnicalIndicators(rsi=65.5, macd=0.5)
        result = indicators.to_dict()
        assert result["rsi"] == 65.5
        assert result["macd"] == 0.5
        assert result["macd_signal"] is None


class TestMarketContext:
    """Tests for MarketContext dataclass."""

    def test_default_creation(self):
        """Test creating context with defaults."""
        context = MarketContext()
        assert context.trend_state is None
        assert context.trend_confidence is None
        assert context.confluence_score is None

    def test_creation_with_values(self):
        """Test creating context with values."""
        context = MarketContext(
            trend_state="bullish",
            trend_confidence=0.85,
            confluence_score=75.0,
            price_change_24h=2.5,
            volatility=0.15,
        )
        assert context.trend_state == "bullish"
        assert context.trend_confidence == 0.85
        assert context.confluence_score == 75.0
        assert context.price_change_24h == 2.5
        assert context.volatility == 0.15

    def test_to_dict(self):
        """Test conversion to dictionary."""
        context = MarketContext(trend_state="bullish", confluence_score=75.0)
        result = context.to_dict()
        assert result["trend_state"] == "bullish"
        assert result["confluence_score"] == 75.0
        assert result["trend_confidence"] is None


class TestExtractedFeatures:
    """Tests for ExtractedFeatures dataclass."""

    def test_creation(self):
        """Test creating extracted features."""
        timestamp = datetime.now()
        features = ExtractedFeatures(
            signal_id="test-sig-001",
            timestamp=timestamp,
            token="BTC",
            timeframe="1h",
            direction="long",
            confidence=0.85,
            entry_price=45000.0,
        )
        assert features.signal_id == "test-sig-001"
        assert features.token == "BTC"
        assert features.timeframe == "1h"
        assert features.direction == "long"

    def test_post_init(self):
        """Test post-init initialization of nested objects."""
        features = ExtractedFeatures(
            signal_id="test-sig-001",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
        )
        assert features.technical is not None
        assert features.market is not None
        assert isinstance(features.technical, TechnicalIndicators)
        assert isinstance(features.market, MarketContext)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        timestamp = datetime.now()
        features = ExtractedFeatures(
            signal_id="test-sig-001",
            timestamp=timestamp,
            token="BTC",
            timeframe="1h",
            direction="long",
            confidence=0.85,
            technical=TechnicalIndicators(rsi=65.5),
            market=MarketContext(trend_state="bullish"),
        )
        result = features.to_dict()
        assert result["signal_id"] == "test-sig-001"
        assert result["token"] == "BTC"
        assert result["rsi"] == 65.5
        assert result["trend_state"] == "bullish"


class TestFeatureExtractor:
    """Tests for FeatureExtractor class."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock signal storage."""
        storage = MagicMock()
        storage.get_signal_by_id = AsyncMock()
        return storage

    @pytest.fixture
    def sample_signal(self):
        """Create sample signal record."""
        return SignalRecord(
            signal_id="test-sig-001",
            token="BTC",
            timestamp=int(datetime.now().timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.85,
            entry_price=45000.0,
            score=75.0,
            timeframes_used=["1h"],
            indicators_used=["rsi", "macd"],
        )

    @pytest.mark.asyncio
    async def test_extract_features_no_storage(self):
        """Test extraction fails without storage."""
        extractor = FeatureExtractor(signal_storage=None)
        result = await extractor.extract_features("test-sig-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_features_signal_not_found(self, mock_storage):
        """Test extraction when signal not found."""
        mock_storage.get_signal_by_id.return_value = None
        extractor = FeatureExtractor(signal_storage=mock_storage)
        result = await extractor.extract_features("test-sig-001")
        assert result is None
        mock_storage.get_signal_by_id.assert_called_once_with("test-sig-001")

    @pytest.mark.asyncio
    async def test_extract_features_success(self, mock_storage, sample_signal):
        """Test successful feature extraction."""
        mock_storage.get_signal_by_id.return_value = sample_signal
        extractor = FeatureExtractor(signal_storage=mock_storage)

        # Mock the async methods
        extractor.extract_technical_indicators = AsyncMock(
            return_value=TechnicalIndicators(rsi=65.5, macd=0.5)
        )
        extractor.extract_market_context = AsyncMock(
            return_value=MarketContext(trend_state="bullish", confluence_score=75.0)
        )

        result = await extractor.extract_features("test-sig-001")

        assert result is not None
        assert result.signal_id == "test-sig-001"
        assert result.token == "BTC"
        assert result.timeframe == "1h"
        assert result.direction == "long"
        assert result.confidence == 0.85
        assert result.entry_price == 45000.0

    def test_extract_from_signal(self, sample_signal):
        """Test extraction from signal record."""
        extractor = FeatureExtractor()
        features = extractor._extract_from_signal(sample_signal)

        assert features.signal_id == "test-sig-001"
        assert features.token == "BTC"
        assert features.timeframe == "1h"
        assert features.direction == "long"
        assert features.confidence == 0.85
        assert features.entry_price == 45000.0

    def test_extract_from_signal_short_direction(self, sample_signal):
        """Test extraction with short direction."""
        sample_signal.direction = SignalDirection.SHORT
        extractor = FeatureExtractor()
        features = extractor._extract_from_signal(sample_signal)
        assert features.direction == "short"

    def test_extract_from_signal_neutral_direction(self, sample_signal):
        """Test extraction with neutral direction."""
        sample_signal.direction = SignalDirection.NEUTRAL
        extractor = FeatureExtractor()
        features = extractor._extract_from_signal(sample_signal)
        assert features.direction == "neutral"

    @pytest.mark.asyncio
    async def test_extract_technical_indicators_cache(self):
        """Test caching of technical indicators."""
        extractor = FeatureExtractor(use_cache=True)
        timestamp = datetime.now()

        # First call should compute
        with patch.object(
            extractor,
            "_compute_indicators",
            new_callable=AsyncMock,
            return_value=TechnicalIndicators(rsi=65.5),
        ) as mock_compute:
            result1 = await extractor.extract_technical_indicators(
                "BTC", "1h", timestamp
            )
            assert result1.rsi == 65.5
            assert mock_compute.called

        # Second call should use cache
        with patch.object(
            extractor,
            "_compute_indicators",
            new_callable=AsyncMock,
            return_value=TechnicalIndicators(rsi=70.0),
        ) as mock_compute:
            result2 = await extractor.extract_technical_indicators(
                "BTC", "1h", timestamp
            )
            assert result2.rsi == 65.5  # Should be cached value
            assert not mock_compute.called

    @pytest.mark.asyncio
    async def test_extract_market_context(self, sample_signal):
        """Test market context extraction."""
        extractor = FeatureExtractor()
        timestamp = datetime.now()

        context = await extractor.extract_market_context(
            token="BTC",
            timestamp=timestamp,
            signal=sample_signal,
        )

        assert context is not None
        assert context.confluence_score == 75.0

    @pytest.mark.asyncio
    async def test_extract_confluence_score(self, mock_storage, sample_signal):
        """Test confluence score extraction."""
        mock_storage.get_signal_by_id.return_value = sample_signal
        extractor = FeatureExtractor(signal_storage=mock_storage)

        score = await extractor.extract_confluence_score("test-sig-001")
        assert score == 75.0

    @pytest.mark.asyncio
    async def test_extract_confluence_score_no_storage(self):
        """Test confluence score without storage."""
        extractor = FeatureExtractor(signal_storage=None)
        score = await extractor.extract_confluence_score("test-sig-001")
        assert score is None

    def test_clear_cache(self):
        """Test cache clearing."""
        extractor = FeatureExtractor(use_cache=True)
        extractor._cache = {"key": "value"}
        extractor.clear_cache()
        assert len(extractor._cache) == 0

    def test_get_cache_stats_enabled(self):
        """Test cache stats with cache enabled."""
        extractor = FeatureExtractor(use_cache=True)
        extractor._cache = {"key1": "value1", "key2": "value2"}
        stats = extractor.get_cache_stats()
        assert stats["size"] == 2
        assert stats["enabled"] == 1

    def test_get_cache_stats_disabled(self):
        """Test cache stats with cache disabled."""
        extractor = FeatureExtractor(use_cache=False)
        stats = extractor.get_cache_stats()
        assert stats["size"] == 0
        assert stats["enabled"] == 0

    @pytest.mark.asyncio
    async def test_extract_markov_state(self):
        """Test Markov state extraction."""
        extractor = FeatureExtractor()
        timestamp = datetime.now()

        # Currently returns None (requires OHLCV data)
        result = await extractor.extract_markov_state("BTC", timestamp)
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_features_error_handling(self, mock_storage, sample_signal):
        """Test error handling during extraction."""
        mock_storage.get_signal_by_id.return_value = sample_signal
        extractor = FeatureExtractor(signal_storage=mock_storage)

        # Mock technical extraction to raise exception
        extractor.extract_technical_indicators = AsyncMock(
            side_effect=Exception("Technical extraction failed")
        )
        extractor.extract_market_context = AsyncMock(return_value=MarketContext())

        # Should still return features with empty technical indicators
        result = await extractor.extract_features("test-sig-001")
        assert result is not None
        assert result.technical is not None
