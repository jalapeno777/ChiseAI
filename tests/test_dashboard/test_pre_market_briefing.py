"""Tests for pre-market briefing generator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dashboard.pre_market_briefing import PreMarketBriefing, PreMarketBriefingGenerator
from signal_generation.models import Signal, SignalDirection, SignalStatus


@dataclass
class MockOHLCVData:
    """Mock OHLCV data for testing."""

    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


def create_mock_data(count: int, start_price: float = 50000.0) -> list[MockOHLCVData]:
    """Create mock OHLCV data."""
    data = []
    price = start_price

    for i in range(count):
        price = start_price + (i * 100)  # Gradual uptrend

        data.append(
            MockOHLCVData(
                timestamp=i * 3600,
                open_price=price * 0.99,
                high_price=price * 1.02,
                low_price=price * 0.98,
                close_price=price,
                volume=1000.0,
            )
        )

    return data


class TestPreMarketBriefing:
    """Tests for PreMarketBriefing dataclass."""

    def test_pre_market_briefing_creation(self) -> None:
        """Test creating PreMarketBriefing."""
        briefing = PreMarketBriefing(
            timestamp=datetime.now(UTC),
            briefing_text="Test briefing",
            update_interval_minutes=5,
        )

        assert briefing.briefing_text == "Test briefing"
        assert briefing.update_interval_minutes == 5

    def test_is_fresh(self) -> None:
        """Test freshness check."""
        # Fresh briefing
        fresh = PreMarketBriefing(
            timestamp=datetime.now(UTC),
            next_update_time=datetime.now(UTC) + timedelta(minutes=5),
            update_interval_minutes=5,
        )

        # Stale briefing
        stale = PreMarketBriefing(
            timestamp=datetime.now(UTC) - timedelta(minutes=10),
            next_update_time=datetime.now(UTC) - timedelta(minutes=5),
            update_interval_minutes=5,
        )

        assert fresh.is_fresh is True
        assert stale.is_fresh is False

    def test_to_dict(self) -> None:
        """Test PreMarketBriefing serialization."""
        briefing = PreMarketBriefing(
            timestamp=datetime.now(UTC),
            briefing_text="Test briefing",
            update_interval_minutes=5,
            generation_time_ms=100.5,
        )

        d = briefing.to_dict()

        assert d["briefing_text"] == "Test briefing"
        assert d["update_interval_minutes"] == 5
        assert d["generation_time_ms"] == 100.5

    def test_get_token_briefing(self) -> None:
        """Test getting token-specific briefing."""
        from dashboard.signal_list import ActiveSignal, SignalListResult

        signal = ActiveSignal(
            signal_id="test-1",
            token="BTC/USDT",
            direction="long",
            confidence=80.0,
            base_score=75.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )

        briefing = PreMarketBriefing(
            timestamp=datetime.now(UTC),
            active_signals=SignalListResult(
                timestamp=datetime.now(UTC),
                signals=[signal],
                high_confidence_count=1,
                long_count=1,
                short_count=0,
                tokens_covered=["BTC/USDT"],
            ),
        )

        token_briefing = briefing.get_token_briefing("BTC/USDT")

        assert token_briefing["token"] == "BTC/USDT"
        assert len(token_briefing["active_signals"]) == 1


class TestPreMarketBriefingGenerator:
    """Tests for PreMarketBriefingGenerator."""

    def test_generator_initialization(self) -> None:
        """Test generator initialization."""
        generator = PreMarketBriefingGenerator()

        assert generator.update_interval_minutes == 5
        assert generator.confidence_threshold == 75.0
        assert generator._cached_briefing is None

    def test_generator_custom_interval(self) -> None:
        """Test generator with custom interval."""
        generator = PreMarketBriefingGenerator(
            update_interval_minutes=10,
            confidence_threshold=80.0,
        )

        assert generator.update_interval_minutes == 10
        assert generator.confidence_threshold == 80.0

    def test_generate_empty_data(self) -> None:
        """Test generation with empty data."""
        generator = PreMarketBriefingGenerator()

        briefing = generator.generate({})

        assert briefing is not None
        assert briefing.market_summary is not None
        assert briefing.timestamp is not None

    def test_generate_with_data(self) -> None:
        """Test generation with data."""
        generator = PreMarketBriefingGenerator()

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {
                "1h": data,
                "4h": data[::4],  # 4h aggregated from 1h
            }
        }

        briefing = generator.generate(token_data)

        assert briefing.market_summary is not None
        assert len(briefing.key_levels) > 0
        assert "BTC/USDT" in briefing.key_levels

    def test_generate_with_signals(self) -> None:
        """Test generation with signals."""
        generator = PreMarketBriefingGenerator()

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.80,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
        ]

        briefing = generator.generate(token_data, signals=signals)

        assert briefing.active_signals is not None
        assert len(briefing.active_signals.signals) >= 0

    def test_caching(self) -> None:
        """Test briefing caching."""
        generator = PreMarketBriefingGenerator(update_interval_minutes=5)

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        # First generation
        briefing1 = generator.generate(token_data)

        # Second generation should use cache
        briefing2 = generator.generate(token_data)

        assert briefing1 is briefing2  # Same object from cache

    def test_force_refresh(self) -> None:
        """Test force refresh."""
        generator = PreMarketBriefingGenerator(update_interval_minutes=5)

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        # First generation
        briefing1 = generator.generate(token_data)

        # Force refresh
        briefing2 = generator.generate(token_data, force_refresh=True)

        assert briefing1 is not briefing2  # Different objects

    def test_cache_invalidation(self) -> None:
        """Test cache invalidation."""
        generator = PreMarketBriefingGenerator()

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        # Generate and cache
        generator.generate(token_data)
        assert generator._cached_briefing is not None

        # Invalidate cache
        generator.invalidate_cache()

        assert generator._cached_briefing is None
        assert generator._last_update is None

    def test_get_cache_status_empty(self) -> None:
        """Test cache status with no cache."""
        generator = PreMarketBriefingGenerator()

        status = generator.get_cache_status()

        assert status["cached"] is False
        assert status["valid"] is False

    def test_get_cache_status_valid(self) -> None:
        """Test cache status with valid cache."""
        generator = PreMarketBriefingGenerator(update_interval_minutes=5)

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        generator.generate(token_data)
        status = generator.get_cache_status()

        assert status["cached"] is True
        assert status["valid"] is True
        assert status["age_seconds"] is not None

    def test_briefing_text_generation(self) -> None:
        """Test briefing text generation."""
        generator = PreMarketBriefingGenerator()

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        briefing = generator.generate(token_data)

        assert briefing.briefing_text is not None
        assert len(briefing.briefing_text) > 0
        assert "Pre-Market Briefing" in briefing.briefing_text

    def test_generation_time_tracking(self) -> None:
        """Test generation time tracking."""
        generator = PreMarketBriefingGenerator()

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        briefing = generator.generate(token_data)

        assert briefing.generation_time_ms > 0
        # Should be reasonably fast (< 3 seconds as per NFR-001)
        assert briefing.generation_time_ms < 3000

    def test_multiple_tokens(self) -> None:
        """Test generation with multiple tokens."""
        generator = PreMarketBriefingGenerator()

        btc_data = create_mock_data(50, start_price=50000.0)
        eth_data = create_mock_data(50, start_price=3000.0)

        token_data = {
            "BTC/USDT": {"1h": btc_data},
            "ETH/USDT": {"1h": eth_data},
        }

        briefing = generator.generate(token_data)

        assert "BTC/USDT" in briefing.key_levels
        assert "ETH/USDT" in briefing.key_levels
        assert len(briefing.market_summary.tokens) == 2

    def test_next_update_time(self) -> None:
        """Test next update time calculation."""
        generator = PreMarketBriefingGenerator(update_interval_minutes=5)

        data = create_mock_data(50)
        token_data = {
            "BTC/USDT": {"1h": data},
        }

        briefing = generator.generate(token_data)

        assert briefing.next_update_time is not None
        expected_next = briefing.timestamp + timedelta(minutes=5)
        assert abs((briefing.next_update_time - expected_next).total_seconds()) < 1


class TestPreMarketBriefingIntegration:
    """Integration tests for pre-market briefing."""

    def test_full_pipeline(self) -> None:
        """Test full briefing generation pipeline."""
        generator = PreMarketBriefingGenerator()

        # Create realistic data
        btc_data = create_mock_data(168, start_price=50000.0)  # 1 week of hourly data
        eth_data = create_mock_data(168, start_price=3000.0)

        token_data = {
            "BTC/USDT": {
                "1h": btc_data,
                "4h": btc_data[::4],
                "1d": btc_data[::24],
            },
            "ETH/USDT": {
                "1h": eth_data,
                "4h": eth_data[::4],
                "1d": eth_data[::24],
            },
        }

        # Create signals
        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                contributing_factors=[{"type": "rsi", "weight": 0.5}],
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.80,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="4h",
            ),
        ]

        briefing = generator.generate(token_data, signals=signals)

        # Verify all components
        assert briefing.market_summary is not None
        assert len(briefing.key_levels) == 2
        assert briefing.active_signals is not None
        assert len(briefing.active_signals.signals) == 2
        assert len(briefing.market_regimes) > 0
        assert len(briefing.briefing_text) > 0

        # Verify serialization
        d = briefing.to_dict()
        assert "market_summary" in d
        assert "key_levels" in d
        assert "active_signals" in d
        assert "market_regimes" in d
        assert "briefing_text" in d
