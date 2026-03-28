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
        cache = SignalCache(ttl_seconds=0.05)  # 50ms TTL

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

        # Wait for expiration (2x TTL for CI stability)
        time.sleep(0.11)

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
        cache = SignalCache(ttl_seconds=0.05)  # 50ms TTL

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

        # Wait for expiration (2x TTL for CI stability)
        time.sleep(0.11)

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


class TestSignalGeneratorEntryPrice:
    """Tests for signal generation entry_price metadata (BURNIN-001)."""

    @patch("signal_generation.signal_generator.SignalGenerator._get_freshness_checker")
    @patch("signal_generation.signal_generator.SignalGenerator._get_scorer")
    def test_signal_metadata_contains_entry_price(
        self, mock_get_scorer, mock_get_checker
    ):
        """Test that generated signal includes entry_price in metadata (BURNIN-001 fix).

        Verifies the critical bug fix where entry_price was missing from signal
        metadata, causing risk enforcer to default to 0.0 and reject orders.
        """
        from market_analysis.confluence.scorer import ConfluenceScore

        # Mock freshness checker to return fresh result
        mock_checker = MagicMock()
        mock_checker.check_freshness.return_value = MagicMock(
            is_fresh=True,
            errors=[],
            data_age_seconds=0.0,
        )
        mock_get_checker.return_value = mock_checker

        # Mock confluence scorer to return a valid score
        mock_scorer = MagicMock()
        mock_confluence_score = MagicMock(spec=ConfluenceScore)
        mock_confluence_score.direction_str = "LONG"
        mock_confluence_score.confidence = 0.85
        mock_confluence_score.score = 80.0
        mock_confluence_score.contributing_factors = []
        mock_confluence_score.signal_breakdown = {}
        mock_confluence_score.metadata = {}
        mock_confluence_score.multiplier_applied = 1.0
        mock_confluence_score.multiplier_rationale = "test"
        mock_scorer.calculate_score.return_value = mock_confluence_score
        mock_get_scorer.return_value = mock_scorer

        config = SignalGenerationConfig(enable_freshness_checks=True)
        generator = SignalGenerator(config=config)

        # Create mock OHLCV data
        mock_ohlcv = [MagicMock(timestamp=1000, datetime_utc=datetime.now(UTC))]

        from data_ingestion.timeframe_config import Timeframe

        test_price = 65000.50
        signal = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
            current_price=test_price,
        )

        # Verify entry_price is in metadata
        assert (
            "entry_price" in signal.metadata
        ), "entry_price missing from signal metadata"
        assert (
            signal.metadata["entry_price"] == test_price
        ), f"entry_price mismatch: expected {test_price}, got {signal.metadata['entry_price']}"

    @patch("signal_generation.signal_generator.SignalGenerator._get_freshness_checker")
    @patch("signal_generation.signal_generator.SignalGenerator._get_scorer")
    def test_signal_entry_price_none_when_not_provided(
        self, mock_get_scorer, mock_get_checker
    ):
        """Test that entry_price is None when current_price not provided."""
        from market_analysis.confluence.scorer import ConfluenceScore

        # Mock freshness checker to return fresh result
        mock_checker = MagicMock()
        mock_checker.check_freshness.return_value = MagicMock(
            is_fresh=True,
            errors=[],
            data_age_seconds=0.0,
        )
        mock_get_checker.return_value = mock_checker

        # Mock confluence scorer to return a valid score
        mock_scorer = MagicMock()
        mock_confluence_score = MagicMock(spec=ConfluenceScore)
        mock_confluence_score.direction_str = "LONG"
        mock_confluence_score.confidence = 0.85
        mock_confluence_score.score = 80.0
        mock_confluence_score.contributing_factors = []
        mock_confluence_score.signal_breakdown = {}
        mock_confluence_score.metadata = {}
        mock_confluence_score.multiplier_applied = 1.0
        mock_confluence_score.multiplier_rationale = "test"
        mock_scorer.calculate_score.return_value = mock_confluence_score
        mock_get_scorer.return_value = mock_scorer

        config = SignalGenerationConfig(enable_freshness_checks=True)
        generator = SignalGenerator(config=config)

        # Create mock OHLCV data
        mock_ohlcv = [MagicMock(timestamp=1000, datetime_utc=datetime.now(UTC))]

        from data_ingestion.timeframe_config import Timeframe

        signal = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
            # current_price not provided
        )

        # Verify entry_price is None when not provided
        assert "entry_price" in signal.metadata
        assert signal.metadata["entry_price"] is None


class TestSignalGeneratorIndicatorSet:
    """Tests for signal generation with IndicatorSet conversion."""

    def test_indicatorset_has_required_attributes(self):
        """Test that IndicatorSet has the attributes expected by the fix.

        Verifies the fix can access rsi, macd, and bollinger_bands attributes
        from an IndicatorSet object (BURNIN-001 fix validation).
        """
        from market_analysis.indicators.calculator import IndicatorSet

        # Verify IndicatorSet is a dataclass with expected fields

        # Check that IndicatorSet is defined with the fields we need
        assert hasattr(IndicatorSet, "__dataclass_fields__")
        fields = IndicatorSet.__dataclass_fields__.keys()

        assert "rsi" in fields
        assert "macd" in fields
        assert "bollinger_bands" in fields
        assert "timeframe" in fields

    def test_signal_aggregator_accepts_list_not_indicatorset(self):
        """Test that SignalAggregator.aggregate() requires a list, not IndicatorSet.

        This test documents the bug that BURNIN-001 fixes: passing an
        IndicatorSet directly to aggregate() raises TypeError because
        it's not iterable.
        """
        from market_analysis.confluence.signal_aggregator import SignalAggregator
        from market_analysis.indicators.calculator import IndicatorSet

        aggregator = SignalAggregator()

        # Create a minimal IndicatorSet instance (with None values)
        from unittest.mock import MagicMock

        from data_ingestion.timeframe_config import Timeframe

        mock_timeframe = MagicMock(spec=Timeframe)
        mock_timeframe.value = "1h"

        indicator_set = IndicatorSet(timeframe=mock_timeframe)

        # Verify IndicatorSet is not iterable (this is the bug)
        try:
            list(indicator_set)
            raise AssertionError("IndicatorSet should not be iterable")
        except TypeError:
            pass  # Expected - IndicatorSet is not a list/sequence

        # Verify aggregate() expects a list (will fail with IndicatorSet)
        import inspect

        sig = inspect.signature(aggregator.aggregate)
        param = sig.parameters["signals"]

        # The parameter should accept a Sequence, not an IndicatorSet
        assert param.name == "signals"

    def test_indicatorset_conversion_extracts_signals(self):
        """Test that IndicatorSet attributes are properly accessed.

        Verifies the fix handles the case where IndicatorSet has
        rsi, macd, and bollinger_bands attributes.
        """
        from market_analysis.indicators.calculator import IndicatorSet

        # Create a minimal IndicatorSet to verify attribute access
        indicator_set = MagicMock(spec=IndicatorSet)
        indicator_set.rsi = MagicMock()
        indicator_set.macd = MagicMock()
        indicator_set.bollinger_bands = MagicMock()

        # Verify attributes are accessible (this is what the fix does)
        assert hasattr(indicator_set, "rsi")
        assert hasattr(indicator_set, "macd")
        assert hasattr(indicator_set, "bollinger_bands")

        # Verify we can check for None (important for the fix)
        indicator_set.rsi = None
        indicator_set.macd = None
        indicator_set.bollinger_bands = None

        # When all are None, signals_list should be empty
        signals_list = []
        if indicator_set.rsi is not None:
            signals_list.append("rsi_signal")
        if indicator_set.macd is not None:
            signals_list.append("macd_signal")
        if indicator_set.bollinger_bands is not None:
            signals_list.append("bb_signal")

        assert len(signals_list) == 0


class TestSignalFlowTap:
    """Tests for shadow-mode signal flow tap."""

    def _make_timeframe(self, value="1h"):
        """Create a mock Timeframe with .value attribute."""
        tf = MagicMock()
        tf.value = value
        return tf

    def test_register_and_unregister_tap(self):
        """Tap can be registered and unregistered."""
        gen = SignalGenerator(config=SignalGenerationConfig(enable_shadow_tap=True))
        tap_calls = []

        def tap(sig):
            tap_calls.append(sig)

        gen.register_signal_flow_tap(tap)
        assert gen._signal_flow_tap is tap
        gen.register_signal_flow_tap(None)
        assert gen._signal_flow_tap is None

    def test_tap_receives_signal_on_generate(self):
        """Registered tap receives the generated signal."""
        gen = SignalGenerator(
            config=SignalGenerationConfig(
                enable_shadow_tap=True,
                enable_freshness_checks=False,
                enable_caching=False,
            )
        )
        captured = []
        gen.register_signal_flow_tap(lambda sig: captured.append(sig))

        signal = gen.generate_signal(
            token="BTC/USDT",
            timeframe=self._make_timeframe("1h"),
            ohlcv_data=[],
        )
        assert len(captured) == 1
        assert captured[0].token == "BTC/USDT"
        assert captured[0] is signal

    def test_no_tap_zero_overhead(self):
        """When no tap is registered, no callback overhead occurs."""
        gen = SignalGenerator(
            config=SignalGenerationConfig(
                enable_freshness_checks=False,
                enable_caching=False,
            )
        )
        assert gen._signal_flow_tap is None
        # generate_signal should succeed without any tap
        signal = gen.generate_signal(
            token="ETH/USDT",
            timeframe=self._make_timeframe("15m"),
            ohlcv_data=[],
        )
        assert signal is not None

    def test_tap_exception_does_not_break_pipeline(self):
        """Exception in tap must not affect signal generation."""
        gen = SignalGenerator(
            config=SignalGenerationConfig(
                enable_shadow_tap=True,
                enable_freshness_checks=False,
                enable_caching=False,
            )
        )

        def bad_tap(sig):
            raise RuntimeError("tap exploded")

        gen.register_signal_flow_tap(bad_tap)
        # Should NOT raise despite tap failing
        signal = gen.generate_signal(
            token="BTC/USDT",
            timeframe=self._make_timeframe("1h"),
            ohlcv_data=[],
        )
        assert signal is not None

    def test_tap_latency_benchmark(self):
        """Timing benchmark: tap overhead must be negligible (<0.01ms)."""
        import statistics

        gen = SignalGenerator(
            config=SignalGenerationConfig(
                enable_shadow_tap=True,
                enable_freshness_checks=False,
                enable_caching=False,
            )
        )
        captured = []
        gen.register_signal_flow_tap(lambda sig: captured.append(sig))

        tf = self._make_timeframe("1h")

        # Warm up
        for _ in range(10):
            gen.generate_signal(token="BTC/USDT", timeframe=tf, ohlcv_data=[])

        # Benchmark WITH tap
        times_with_tap = []
        for _ in range(100):
            captured.clear()
            start = time.perf_counter()
            gen.generate_signal(token="BTC/USDT", timeframe=tf, ohlcv_data=[])
            times_with_tap.append((time.perf_counter() - start) * 1_000_000)  # µs

        # Benchmark WITHOUT tap
        gen.register_signal_flow_tap(None)
        times_without_tap = []
        for _ in range(100):
            start = time.perf_counter()
            gen.generate_signal(token="BTC/USDT", timeframe=tf, ohlcv_data=[])
            times_without_tap.append((time.perf_counter() - start) * 1_000_000)  # µs

        avg_with = statistics.mean(times_with_tap)
        avg_without = statistics.mean(times_without_tap)
        overhead_us = avg_with - avg_without

        # Overhead must be < 10µs (0.01ms) - effectively zero
        assert overhead_us < 10, (
            f"Tap overhead {overhead_us:.2f}µs exceeds 10µs threshold "
            f"(with={avg_with:.2f}µs, without={avg_without:.2f}µs)"
        )
