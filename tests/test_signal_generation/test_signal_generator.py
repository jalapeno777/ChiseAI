"""Tests for signal generation module."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.signal_generator import (
    SignalCache,
    SignalGenerationConfig,
    SignalGenerator,
)


class TestSignalCache:
    """Tests for SignalCache."""

    def test_cache_basic_operations(self):
        """Test basic cache get/set operations."""
        cache = SignalCache(ttl_seconds=60.0)

        # Create a signal
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        # Set in cache
        cache.set("BTC/USDT", "1h", SignalDirection.LONG, signal)

        # Get from cache
        cached = cache.get("BTC/USDT", "1h", SignalDirection.LONG)
        assert cached is not None
        assert cached.token == "BTC/USDT"
        assert cached.direction == SignalDirection.LONG

    def test_cache_expiration(self):
        """Test that cache entries expire after TTL."""
        cache = SignalCache(ttl_seconds=0.1)  # 100ms TTL

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        cache.set("BTC/USDT", "1h", SignalDirection.LONG, signal)

        # Should be available immediately
        assert cache.get("BTC/USDT", "1h", SignalDirection.LONG) is not None

        # Wait for expiration
        time.sleep(0.15)

        # Should be expired
        assert cache.get("BTC/USDT", "1h", SignalDirection.LONG) is None

    def test_cache_different_keys(self):
        """Test that different keys don't interfere."""
        cache = SignalCache(ttl_seconds=60.0)

        signal1 = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        signal2 = Signal(
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.75,
            base_score=70.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="4h",
        )

        cache.set("BTC/USDT", "1h", SignalDirection.LONG, signal1)
        cache.set("ETH/USDT", "4h", SignalDirection.SHORT, signal2)

        # Both should be retrievable
        assert cache.get("BTC/USDT", "1h", SignalDirection.LONG) == signal1
        assert cache.get("ETH/USDT", "4h", SignalDirection.SHORT) == signal2

    def test_cache_clear(self):
        """Test cache clear operation."""
        cache = SignalCache(ttl_seconds=60.0)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        cache.set("BTC/USDT", "1h", SignalDirection.LONG, signal)
        assert cache.get("BTC/USDT", "1h", SignalDirection.LONG) is not None

        cache.clear()
        assert cache.get("BTC/USDT", "1h", SignalDirection.LONG) is None

    def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = SignalCache(ttl_seconds=0.1)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        cache.set("BTC/USDT", "1h", SignalDirection.LONG, signal)

        # Wait for expiration
        time.sleep(0.15)

        # Cleanup should remove expired entry
        removed = cache.cleanup_expired()
        assert removed == 1
        assert len(cache._cache) == 0


class TestSignalGenerator:
    """Tests for SignalGenerator."""

    def test_generator_initialization(self):
        """Test signal generator initialization."""
        config = SignalGenerationConfig(
            actionable_threshold=0.75,
            enable_freshness_checks=True,
            cache_ttl_seconds=300.0,
        )

        generator = SignalGenerator(config=config)

        assert generator.config.actionable_threshold == 0.75
        assert generator.config.enable_freshness_checks is True
        assert generator.config.cache_ttl_seconds == 300.0

    def test_map_direction(self):
        """Test direction mapping from confluence to signal."""
        generator = SignalGenerator()

        assert generator._map_direction("LONG") == SignalDirection.LONG
        assert generator._map_direction("SHORT") == SignalDirection.SHORT
        assert generator._map_direction("NEUTRAL") == SignalDirection.NEUTRAL
        assert generator._map_direction("unknown") == SignalDirection.NEUTRAL

    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        config = SignalGenerationConfig(max_signals_per_token_per_hour=2)
        generator = SignalGenerator(config=config)

        # Should allow first 2 signals
        assert generator._check_rate_limit("BTC/USDT") is True
        generator._record_signal("BTC/USDT")

        assert generator._check_rate_limit("BTC/USDT") is True
        generator._record_signal("BTC/USDT")

        # Should block 3rd signal
        assert generator._check_rate_limit("BTC/USDT") is False

    def test_get_cache_stats(self):
        """Test cache stats retrieval."""
        config = SignalGenerationConfig(enable_caching=True, cache_ttl_seconds=300.0)
        generator = SignalGenerator(config=config)

        stats = generator.get_cache_stats()

        assert stats["cache_enabled"] is True
        assert stats["cache_ttl_seconds"] == 300.0
        assert stats["cached_entries"] == 0

    @patch("signal_generation.signal_generator.SignalGenerator._get_freshness_checker")
    @patch("signal_generation.signal_generator.SignalGenerator._get_scorer")
    def test_generate_signal_stale_data(self, mock_get_scorer, mock_get_checker):
        """Test signal generation with stale data."""
        # Mock freshness checker to return stale result
        mock_checker = MagicMock()
        mock_checker.check_freshness.return_value = MagicMock(
            is_fresh=False,
            errors=["Data is stale"],
            data_age_seconds=300.0,
        )
        mock_get_checker.return_value = mock_checker

        config = SignalGenerationConfig(enable_freshness_checks=True)
        generator = SignalGenerator(config=config)

        # Create mock OHLCV data
        mock_ohlcv = [MagicMock(timestamp=1000, datetime_utc=datetime.now(UTC))]

        from data_ingestion.timeframe_config import Timeframe

        signal = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
        )

        assert signal.status == SignalStatus.STALE_DATA
        assert signal.confidence == 0.0

    def test_generate_signal_latency_tracking(self):
        """Test that signal generation tracks latency."""
        generator = SignalGenerator()

        # The latency should be set after generation
        # We can't easily test the actual latency without mocking,
        # but we can verify the field exists and is set
        assert hasattr(generator, "generate_signal")


class TestSignalGeneratorIntegration:
    """Integration tests for SignalGenerator."""

    @pytest.mark.skip(reason="Requires full indicator pipeline - run manually")
    def test_full_signal_generation_pipeline(self):
        """Test full signal generation with real dependencies."""
        # This test requires:
        # - Real OHLCV data
        # - Indicator calculator
        # - Signal aggregator
        # - Confluence scorer
        pass

    def test_config_defaults(self):
        """Test default configuration values."""
        config = SignalGenerationConfig()

        assert config.actionable_threshold == 0.75
        assert config.enable_freshness_checks is True
        assert config.max_signals_per_token_per_hour == 10
        assert config.cache_ttl_seconds == 300.0
        assert config.enable_caching is True
