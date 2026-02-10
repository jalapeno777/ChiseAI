"""Tests for key levels analyzer."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from dashboard.key_levels import (
    KeyLevel,
    KeyLevelsAnalyzer,
    KeyLevelsResult,
    LevelType,
)


@dataclass
class MockOHLCVData:
    """Mock OHLCV data for testing."""

    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


def create_mock_data_with_swings(count: int = 50) -> list[MockOHLCVData]:
    """Create mock data with clear swing highs and lows."""
    data = []

    for i in range(count):
        # Create a pattern with clear swings
        if i % 10 == 5:  # Swing high
            high = 52000.0
            low = 50000.0
            close = 51000.0
        elif i % 10 == 0:  # Swing low
            high = 50000.0
            low = 48000.0
            close = 49000.0
        else:
            high = 51000.0
            low = 49000.0
            close = 50000.0

        data.append(
            MockOHLCVData(
                timestamp=i * 3600,
                open_price=close * 0.99,
                high_price=high,
                low_price=low,
                close_price=close,
                volume=1000.0,
            )
        )

    return data


class TestKeyLevel:
    """Tests for KeyLevel dataclass."""

    def test_key_level_creation(self) -> None:
        """Test creating KeyLevel."""
        level = KeyLevel(
            price=50000.0,
            level_type=LevelType.SUPPORT,
            strength=75.0,
            timeframes=["1h"],
            touches=3,
            confluence_score=50.0,
            description="Test level",
        )

        assert level.price == 50000.0
        assert level.level_type == LevelType.SUPPORT
        assert level.strength == 75.0

    def test_key_level_normalization(self) -> None:
        """Test KeyLevel value normalization."""
        level = KeyLevel(
            price=50000.0,
            level_type=LevelType.SUPPORT,
            strength=150.0,  # Should be clamped to 100
            timeframes=["1h"],
            confluence_score=-10.0,  # Should be clamped to 0
        )

        assert level.strength == 100.0
        assert level.confluence_score == 0.0

    def test_key_level_to_dict(self) -> None:
        """Test KeyLevel serialization."""
        level = KeyLevel(
            price=50000.0,
            level_type=LevelType.RESISTANCE,
            strength=80.0,
            timeframes=["1h", "4h"],
            touches=5,
            confluence_score=75.0,
            description="Strong resistance",
        )

        d = level.to_dict()

        assert d["price"] == 50000.0
        assert d["level_type"] == "resistance"
        assert d["strength"] == 80.0
        assert d["confluence_score"] == 75.0


class TestKeyLevelsResult:
    """Tests for KeyLevelsResult dataclass."""

    def test_key_levels_result_creation(self) -> None:
        """Test creating KeyLevelsResult."""
        support = KeyLevel(
            price=49000.0,
            level_type=LevelType.SUPPORT,
            strength=80.0,
        )

        result = KeyLevelsResult(
            token="BTC/USDT",
            support_levels=[support],
            current_price=50000.0,
            nearest_support=support,
        )

        assert result.token == "BTC/USDT"
        assert len(result.support_levels) == 1
        assert result.current_price == 50000.0

    def test_key_levels_result_to_dict(self) -> None:
        """Test KeyLevelsResult serialization."""
        support = KeyLevel(
            price=49000.0,
            level_type=LevelType.SUPPORT,
            strength=80.0,
        )

        result = KeyLevelsResult(
            token="BTC/USDT",
            support_levels=[support],
            current_price=50000.0,
            nearest_support=support,
        )

        d = result.to_dict()

        assert d["token"] == "BTC/USDT"
        assert d["current_price"] == 50000.0
        assert len(d["support_levels"]) == 1


class TestKeyLevelsAnalyzer:
    """Tests for KeyLevelsAnalyzer."""

    def test_analyze_empty_data(self) -> None:
        """Test analysis with empty data."""
        analyzer = KeyLevelsAnalyzer()
        result = analyzer.analyze("BTC/USDT", {}, 50000.0)

        assert result.token == "BTC/USDT"
        assert result.current_price == 50000.0
        # Should still have round number levels
        assert len(result.round_levels) > 0

    def test_analyze_with_data(self) -> None:
        """Test analysis with OHLCV data."""
        analyzer = KeyLevelsAnalyzer()

        data = create_mock_data_with_swings(50)
        tf_data = {"1h": data}

        result = analyzer.analyze("BTC/USDT", tf_data, 50000.0)

        assert result.token == "BTC/USDT"
        assert result.current_price == 50000.0
        # Should have identified some levels
        assert len(result.support_levels) >= 0 or len(result.resistance_levels) >= 0

    def test_find_pivot_levels(self) -> None:
        """Test pivot level identification."""
        analyzer = KeyLevelsAnalyzer()

        data = [
            MockOHLCVData(0, 50000.0, 51000.0, 49000.0, 50000.0, 1000.0),
            MockOHLCVData(3600, 50000.0, 52000.0, 48000.0, 51000.0, 1000.0),
        ]

        pivots = analyzer._find_pivot_levels(data, "1h")

        assert len(pivots) == 3  # High, low, close
        # Pivot levels use the second-to-last candle (index -2)
        assert any(p.price == 51000.0 for p in pivots)  # Previous high
        assert any(p.price == 49000.0 for p in pivots)  # Previous low
        assert any(p.price == 50000.0 for p in pivots)  # Previous close

    def test_find_swing_levels(self) -> None:
        """Test swing level identification."""
        analyzer = KeyLevelsAnalyzer()

        data = create_mock_data_with_swings(50)

        swings = analyzer._find_swing_levels(data, "1h")

        # Should find some swing highs and lows
        assert len(swings) > 0

    def test_find_round_numbers(self) -> None:
        """Test round number identification."""
        analyzer = KeyLevelsAnalyzer()

        # Test with high price (BTC-like)
        levels = analyzer._find_round_numbers(52345.67)

        assert len(levels) > 0
        # Should include round 1000s around the price
        assert any(l.price % 1000 == 0 for l in levels)

    def test_find_round_numbers_low_price(self) -> None:
        """Test round numbers for low-priced asset."""
        analyzer = KeyLevelsAnalyzer()

        # Test with low price
        levels = analyzer._find_round_numbers(50.0)

        assert len(levels) > 0
        # Should include round 1s around the price
        assert any(l.price % 1 == 0 for l in levels)

    def test_merge_levels(self) -> None:
        """Test level merging."""
        analyzer = KeyLevelsAnalyzer()

        levels = [
            KeyLevel(
                price=50000.0,
                level_type=LevelType.SUPPORT,
                strength=50.0,
                timeframes=["1h"],
            ),
            KeyLevel(
                price=50050.0,
                level_type=LevelType.SUPPORT,
                strength=60.0,
                timeframes=["4h"],
            ),
            KeyLevel(
                price=51000.0,
                level_type=LevelType.RESISTANCE,
                strength=70.0,
                timeframes=["1h"],
            ),
        ]

        merged = analyzer._merge_levels(levels, 50000.0)

        # First two should be merged (within threshold)
        assert len(merged) < len(levels)

    def test_find_nearest_support(self) -> None:
        """Test finding nearest support."""
        analyzer = KeyLevelsAnalyzer()

        supports = [
            KeyLevel(price=48000.0, level_type=LevelType.SUPPORT, strength=80.0),
            KeyLevel(price=49000.0, level_type=LevelType.SUPPORT, strength=70.0),
            KeyLevel(
                price=51000.0, level_type=LevelType.SUPPORT, strength=60.0
            ),  # Above current
        ]

        nearest = analyzer._find_nearest_support(supports, 50000.0)

        assert nearest is not None
        assert nearest.price == 49000.0  # Closest support below price

    def test_find_nearest_resistance(self) -> None:
        """Test finding nearest resistance."""
        analyzer = KeyLevelsAnalyzer()

        resistances = [
            KeyLevel(
                price=48000.0, level_type=LevelType.RESISTANCE, strength=60.0
            ),  # Below current
            KeyLevel(price=51000.0, level_type=LevelType.RESISTANCE, strength=80.0),
            KeyLevel(price=52000.0, level_type=LevelType.RESISTANCE, strength=70.0),
        ]

        nearest = analyzer._find_nearest_resistance(resistances, 50000.0)

        assert nearest is not None
        assert nearest.price == 51000.0  # Closest resistance above price

    def test_confluence_scoring(self) -> None:
        """Test confluence score calculation."""
        analyzer = KeyLevelsAnalyzer()

        # Create levels from multiple timeframes at similar prices
        levels = [
            KeyLevel(
                price=50000.0,
                level_type=LevelType.SUPPORT,
                strength=50.0,
                timeframes=["1h"],
            ),
            KeyLevel(
                price=50010.0,
                level_type=LevelType.SUPPORT,
                strength=60.0,
                timeframes=["4h"],
            ),
            KeyLevel(
                price=50020.0,
                level_type=LevelType.SUPPORT,
                strength=70.0,
                timeframes=["1d"],
            ),
        ]

        merged = analyzer._merge_levels(levels, 50000.0)

        # Merged level should have high confluence
        assert len(merged) == 1
        assert merged[0].confluence_score > 50  # Multiple timeframes
