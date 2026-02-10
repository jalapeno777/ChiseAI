"""Tests for stop-loss engine.

Validates stop-loss calculations across all methods and market conditions.
"""

from __future__ import annotations

import numpy as np
import pytest

from portfolio_risk.stop_loss.engine import (
    StopLossComparison,
    StopLossEngine,
    StopLossMethod,
    StopLossResult,
    TradeDirection,
)


class MockKeyLevel:
    """Mock KeyLevel for testing."""

    def __init__(
        self,
        price: float,
        level_type: str,
        strength: float = 50.0,
        confluence_score: float = 0.0,
        description: str = "",
    ):
        self.price = price
        self.level_type = level_type
        self.strength = strength
        self.confluence_score = confluence_score
        self.description = description


class MockKeyLevelsResult:
    """Mock KeyLevelsResult for testing."""

    def __init__(
        self,
        nearest_support: MockKeyLevel | None = None,
        nearest_resistance: MockKeyLevel | None = None,
    ):
        self.nearest_support = nearest_support
        self.nearest_resistance = nearest_resistance


class TestStopLossResult:
    """Tests for StopLossResult dataclass."""

    def test_stop_loss_result_creation(self):
        """Test StopLossResult creation."""
        result = StopLossResult(
            stop_price=49000.0,
            method=StopLossMethod.ATR,
            distance_pct=0.02,
            risk_reward_ratio=1.5,
            is_valid=True,
            rationale="Test rationale",
        )

        assert result.stop_price == 49000.0
        assert result.method == StopLossMethod.ATR
        assert result.distance_pct == 0.02
        assert result.risk_reward_ratio == 1.5
        assert result.is_valid is True
        assert result.rationale == "Test rationale"

    def test_stop_loss_result_to_dict(self):
        """Test StopLossResult serialization."""
        result = StopLossResult(
            stop_price=49000.0,
            method=StopLossMethod.ATR,
            distance_pct=0.02,
            risk_reward_ratio=1.5,
            is_valid=True,
            rationale="Test",
            metadata={"key": "value"},
        )

        d = result.to_dict()

        assert d["stop_price"] == 49000.0
        assert d["method"] == "atr"
        assert d["distance_pct"] == 0.02
        assert d["risk_reward_ratio"] == 1.5
        assert d["is_valid"] is True
        assert d["rationale"] == "Test"
        assert d["metadata"] == {"key": "value"}


class TestStopLossEngineInitialization:
    """Tests for StopLossEngine initialization."""

    def test_default_initialization(self):
        """Test engine with default parameters."""
        engine = StopLossEngine()

        assert engine.atr_period == 14
        assert engine.atr_multiplier == 2.0
        assert engine.min_risk_reward == 1.5
        assert engine.default_percentage == 0.03
        assert engine.min_percentage == 0.02
        assert engine.max_percentage == 0.05
        assert engine.max_drawdown_pct == 0.15

    def test_custom_initialization(self):
        """Test engine with custom parameters."""
        engine = StopLossEngine(
            atr_period=10,
            atr_multiplier=3.0,
            min_risk_reward=2.0,
            default_percentage=0.04,
            min_percentage=0.01,
            max_percentage=0.10,
            max_drawdown_pct=0.20,
        )

        assert engine.atr_period == 10
        assert engine.atr_multiplier == 3.0
        assert engine.min_risk_reward == 2.0
        assert engine.default_percentage == 0.04
        assert engine.min_percentage == 0.01
        assert engine.max_percentage == 0.10
        assert engine.max_drawdown_pct == 0.20


class TestATRBasedStop:
    """Tests for ATR-based stop-loss calculation."""

    def create_ohlcv_data(
        self,
        n: int = 20,
        base_price: float = 50000.0,
        volatility: float = 500.0,
    ):
        """Create mock OHLCV data."""
        from dataclasses import dataclass

        @dataclass
        class MockOHLCV:
            open_price: float
            high_price: float
            low_price: float
            close_price: float
            volume: float = 1000.0
            timestamp: int = 0

        np.random.seed(42)
        data = []
        for i in range(n):
            close = base_price + np.random.randn() * volatility
            high = close + abs(np.random.randn()) * volatility * 0.5
            low = close - abs(np.random.randn()) * volatility * 0.5
            open_p = close + np.random.randn() * volatility * 0.3
            data.append(MockOHLCV(open_p, high, low, close, timestamp=i))
        return data

    def test_atr_stop_long(self):
        """Test ATR-based stop for long position."""
        engine = StopLossEngine()
        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        result = engine.atr_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.ATR
        assert result.stop_price < entry_price  # Stop below entry for long
        assert result.distance_pct > 0

    def test_atr_stop_short(self):
        """Test ATR-based stop for short position."""
        engine = StopLossEngine()
        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        result = engine.atr_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.SHORT,
            ohlcv_data=data,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.ATR
        assert result.stop_price > entry_price  # Stop above entry for short
        assert result.distance_pct > 0

    def test_atr_stop_with_target(self):
        """Test ATR-based stop with target price."""
        engine = StopLossEngine()
        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0
        target_price = 52000.0

        result = engine.atr_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            target_price=target_price,
        )

        assert result.risk_reward_ratio > 0
        # R:R = reward / risk = (target - entry) / (entry - stop)
        expected_reward = target_price - entry_price
        expected_risk = entry_price - result.stop_price
        expected_rr = expected_reward / expected_risk if expected_risk > 0 else 0
        assert abs(result.risk_reward_ratio - expected_rr) < 0.01

    def test_atr_stop_insufficient_data(self):
        """Test ATR stop with insufficient data."""
        engine = StopLossEngine()
        data = self.create_ohlcv_data(n=5)  # Need at least 15
        entry_price = 50000.0

        result = engine.atr_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
        )

        assert result.is_valid is False
        assert "ATR calculation failed" in result.rationale

    def test_atr_stop_validation(self):
        """Test ATR stop validation against R:R constraint."""
        engine = StopLossEngine(min_risk_reward=3.0)  # High R:R requirement
        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0
        target_price = 50500.0  # Small target, won't meet 3:1 R:R

        result = engine.atr_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            target_price=target_price,
        )

        # Should be invalid due to R:R constraint
        assert result.is_valid is False
        assert result.risk_reward_ratio < 3.0


class TestTechnicalLevelStop:
    """Tests for technical level-based stop-loss calculation."""

    def test_technical_stop_long_with_support(self):
        """Test technical stop for long with support level."""
        engine = StopLossEngine()
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        result = engine.technical_level_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            key_levels=key_levels,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.TECHNICAL_LEVEL
        assert result.stop_price < support.price  # Stop below support with buffer
        assert "support" in result.rationale.lower()

    def test_technical_stop_short_with_resistance(self):
        """Test technical stop for short with resistance level."""
        engine = StopLossEngine()
        entry_price = 50000.0

        resistance = MockKeyLevel(
            price=51000.0,
            level_type="resistance",
            strength=80.0,
            description="Swing high",
        )
        key_levels = MockKeyLevelsResult(nearest_resistance=resistance)

        result = engine.technical_level_stop(
            entry_price=entry_price,
            direction=TradeDirection.SHORT,
            key_levels=key_levels,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.TECHNICAL_LEVEL
        assert result.stop_price > resistance.price  # Stop above resistance with buffer
        assert "resistance" in result.rationale.lower()

    def test_technical_stop_no_support(self):
        """Test technical stop when no support level exists."""
        engine = StopLossEngine()
        entry_price = 50000.0

        key_levels = MockKeyLevelsResult(nearest_support=None)

        result = engine.technical_level_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            key_levels=key_levels,
        )

        assert result.is_valid is False
        assert "No support level found" in result.rationale

    def test_technical_stop_level_weights(self):
        """Test that level weights are correctly identified."""
        engine = StopLossEngine()
        entry_price = 50000.0

        # Test swing level (weight 1.0)
        swing_support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            description="Swing low on 1h",
        )
        key_levels = MockKeyLevelsResult(nearest_support=swing_support)

        result = engine.technical_level_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            key_levels=key_levels,
        )

        assert result.metadata["level_weight"] == 1.0

        # Test pivot level (weight 0.8)
        pivot_support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            description="Previous 1h low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=pivot_support)

        result = engine.technical_level_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            key_levels=key_levels,
        )

        assert result.metadata["level_weight"] == 0.8


class TestPercentageBasedStop:
    """Tests for percentage-based stop-loss calculation."""

    def test_percentage_stop_long_default(self):
        """Test percentage stop for long with default percentage."""
        engine = StopLossEngine(default_percentage=0.03)
        entry_price = 50000.0

        result = engine.percentage_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.PERCENTAGE
        assert result.distance_pct == 0.03
        expected_stop = entry_price * (1 - 0.03)
        assert abs(result.stop_price - expected_stop) < 0.01

    def test_percentage_stop_short_default(self):
        """Test percentage stop for short with default percentage."""
        engine = StopLossEngine(default_percentage=0.03)
        entry_price = 50000.0

        result = engine.percentage_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.SHORT,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.PERCENTAGE
        assert result.distance_pct == 0.03
        expected_stop = entry_price * (1 + 0.03)
        assert abs(result.stop_price - expected_stop) < 0.01

    def test_percentage_stop_custom(self):
        """Test percentage stop with custom percentage."""
        engine = StopLossEngine()
        entry_price = 50000.0

        result = engine.percentage_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            percentage=0.05,
        )

        assert result.distance_pct == 0.05
        expected_stop = entry_price * (1 - 0.05)
        assert abs(result.stop_price - expected_stop) < 0.01

    def test_percentage_stop_clamped_min(self):
        """Test that percentage is clamped to minimum."""
        engine = StopLossEngine(min_percentage=0.02)
        entry_price = 50000.0

        result = engine.percentage_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            percentage=0.01,  # Below minimum
        )

        assert result.distance_pct == 0.02  # Clamped to minimum
        assert "clamped" in result.rationale.lower()

    def test_percentage_stop_clamped_max(self):
        """Test that percentage is clamped to maximum."""
        engine = StopLossEngine(max_percentage=0.05)
        entry_price = 50000.0

        result = engine.percentage_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            percentage=0.10,  # Above maximum
        )

        assert result.distance_pct == 0.05  # Clamped to maximum
        assert "clamped" in result.rationale.lower()


class TestStopValidation:
    """Tests for stop-loss validation logic."""

    def test_validation_passes_within_constraints(self):
        """Test validation passes for valid stop."""
        engine = StopLossEngine(
            min_risk_reward=1.5,
            max_drawdown_pct=0.15,
        )

        # Valid: R:R = 2.0 > 1.5, distance = 5% < 15%
        is_valid = engine._validate_stop(
            distance_pct=0.05,
            risk_reward=2.0,
        )

        assert is_valid is True

    def test_validation_fails_rr_too_low(self):
        """Test validation fails when R:R is too low."""
        engine = StopLossEngine(min_risk_reward=2.0)

        # Invalid: R:R = 1.0 < 2.0
        is_valid = engine._validate_stop(
            distance_pct=0.05,
            risk_reward=1.0,
        )

        assert is_valid is False

    def test_validation_fails_drawdown_too_high(self):
        """Test validation fails when drawdown exceeds limit."""
        engine = StopLossEngine(max_drawdown_pct=0.10)

        # Invalid: distance = 15% > 10%
        is_valid = engine._validate_stop(
            distance_pct=0.15,
            risk_reward=2.0,
        )

        assert is_valid is False

    def test_validation_no_target(self):
        """Test validation when no target provided (R:R = 0)."""
        engine = StopLossEngine(min_risk_reward=1.5)

        # R:R = 0 means no target, should pass drawdown check only
        is_valid = engine._validate_stop(
            distance_pct=0.05,
            risk_reward=0.0,
        )

        assert is_valid is True


class TestRiskRewardCalculation:
    """Tests for risk:reward ratio calculation."""

    def test_rr_calculation_long(self):
        """Test R:R calculation for long position."""
        engine = StopLossEngine()

        entry = 50000.0
        stop = 49000.0  # 1000 risk
        target = 52000.0  # 2000 reward

        rr = engine._calculate_risk_reward(entry, stop, target)

        assert rr == 2.0  # 2000 / 1000

    def test_rr_calculation_short(self):
        """Test R:R calculation for short position."""
        engine = StopLossEngine()

        entry = 50000.0
        stop = 51000.0  # 1000 risk
        target = 48000.0  # 2000 reward

        rr = engine._calculate_risk_reward(entry, stop, target)

        assert rr == 2.0  # 2000 / 1000

    def test_rr_no_target(self):
        """Test R:R calculation when no target provided."""
        engine = StopLossEngine()

        rr = engine._calculate_risk_reward(50000.0, 49000.0, None)

        assert rr == 0.0

    def test_rr_zero_risk(self):
        """Test R:R calculation when stop equals entry."""
        engine = StopLossEngine()

        rr = engine._calculate_risk_reward(50000.0, 50000.0, 52000.0)

        assert rr == 0.0


class TestOptimalSelection:
    """Tests for optimal stop selection."""

    def test_select_optimal_valid_stops(self):
        """Test optimal selection among valid stops."""
        engine = StopLossEngine()

        results = [
            StopLossResult(
                stop_price=49000.0,
                method=StopLossMethod.ATR,
                distance_pct=0.02,
                risk_reward_ratio=2.0,
                is_valid=True,
                rationale="ATR stop",
            ),
            StopLossResult(
                stop_price=48500.0,
                method=StopLossMethod.TECHNICAL_LEVEL,
                distance_pct=0.03,
                risk_reward_ratio=3.0,
                is_valid=True,
                rationale="Technical stop",
            ),
            StopLossResult(
                stop_price=49500.0,
                method=StopLossMethod.PERCENTAGE,
                distance_pct=0.01,
                risk_reward_ratio=1.5,
                is_valid=True,
                rationale="Percentage stop",
            ),
        ]

        optimal, rationale = engine._select_optimal(results)

        assert optimal is not None
        assert optimal.method == StopLossMethod.TECHNICAL_LEVEL  # Highest R:R
        assert optimal.risk_reward_ratio == 3.0

    def test_select_optimal_no_valid_stops(self):
        """Test optimal selection when no stops are valid."""
        engine = StopLossEngine()

        results = [
            StopLossResult(
                stop_price=49000.0,
                method=StopLossMethod.ATR,
                distance_pct=0.02,
                risk_reward_ratio=1.0,
                is_valid=False,
                rationale="Invalid ATR",
            ),
            StopLossResult(
                stop_price=48500.0,
                method=StopLossMethod.TECHNICAL_LEVEL,
                distance_pct=0.03,
                risk_reward_ratio=0.8,
                is_valid=False,
                rationale="Invalid technical",
            ),
        ]

        optimal, rationale = engine._select_optimal(results)

        assert optimal is None
        assert "No valid stops" in rationale

    def test_select_optimal_tiebreaker(self):
        """Test tiebreaker when R:R is equal."""
        engine = StopLossEngine()

        results = [
            StopLossResult(
                stop_price=49000.0,
                method=StopLossMethod.PERCENTAGE,
                distance_pct=0.02,
                risk_reward_ratio=2.0,
                is_valid=True,
                rationale="Percentage",
            ),
            StopLossResult(
                stop_price=49000.0,
                method=StopLossMethod.ATR,
                distance_pct=0.02,
                risk_reward_ratio=2.0,
                is_valid=True,
                rationale="ATR",
            ),
            StopLossResult(
                stop_price=49000.0,
                method=StopLossMethod.TECHNICAL_LEVEL,
                distance_pct=0.02,
                risk_reward_ratio=2.0,
                is_valid=True,
                rationale="Technical",
            ),
        ]

        optimal, _ = engine._select_optimal(results)

        # Should prefer technical level when R:R is equal
        assert optimal.method == StopLossMethod.TECHNICAL_LEVEL


class TestCompareMethods:
    """Tests for method comparison."""

    def create_ohlcv_data(self, n: int = 20):
        """Create mock OHLCV data."""
        from dataclasses import dataclass

        @dataclass
        class MockOHLCV:
            open_price: float
            high_price: float
            low_price: float
            close_price: float
            volume: float = 1000.0
            timestamp: int = 0

        np.random.seed(42)
        data = []
        for i in range(n):
            close = 50000.0 + np.random.randn() * 500
            high = close + abs(np.random.randn()) * 250
            low = close - abs(np.random.randn()) * 250
            open_p = close + np.random.randn() * 150
            data.append(MockOHLCV(open_p, high, low, close, timestamp=i))
        return data

    def test_compare_all_methods(self):
        """Test comparison of all three methods."""
        engine = StopLossEngine()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        comparison = engine.compare_methods(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
            target_price=52000.0,
        )

        assert isinstance(comparison, StopLossComparison)
        assert len(comparison.results) == 3
        assert comparison.optimal is not None
        assert all(
            r.method
            in [
                StopLossMethod.ATR,
                StopLossMethod.TECHNICAL_LEVEL,
                StopLossMethod.PERCENTAGE,
            ]
            for r in comparison.results
        )

    def test_comparison_serialization(self):
        """Test StopLossComparison serialization."""
        engine = StopLossEngine()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        comparison = engine.compare_methods(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
        )

        d = comparison.to_dict()

        assert "results" in d
        assert "optimal" in d
        assert "selection_rationale" in d
        assert len(d["results"]) == 3


class TestCriticalBugFixes:
    """Tests for CRITICAL bug fixes in stop-loss validation.

    These tests validate that:
    - CRITICAL-001: Stop-loss is on correct side of entry for trade direction
    - CRITICAL-002: Technical levels are on correct side of entry
    - CRITICAL-003: Stop prices are positive and distances are non-negative
    """

    def create_ohlcv_data(self, n: int = 20):
        """Create mock OHLCV data."""
        from dataclasses import dataclass

        @dataclass
        class MockOHLCV:
            open_price: float
            high_price: float
            low_price: float
            close_price: float
            volume: float = 1000.0
            timestamp: int = 0

        np.random.seed(42)
        data = []
        for i in range(n):
            close = 50000.0 + np.random.randn() * 500
            high = close + abs(np.random.randn()) * 250
            low = close - abs(np.random.randn()) * 250
            open_p = close + np.random.randn() * 150
            data.append(MockOHLCV(open_p, high, low, close, timestamp=i))
        return data

    # CRITICAL-001: Stop-loss direction validation tests

    def test_atr_stop_long_validates_positive_price(self):
        """Test that ATR stop validates stop price is positive."""
        engine = StopLossEngine()
        data = self.create_ohlcv_data(n=20)
        entry_price = 100.0  # Very low entry price

        # With normal ATR (~600-700), stop would be negative
        # This tests CRITICAL-003: zero/negative price validation
        with pytest.raises(ValueError, match="Invalid stop-loss price"):
            engine.atr_based_stop(
                entry_price=entry_price,
                direction=TradeDirection.LONG,
                ohlcv_data=data,
            )

    def test_atr_stop_short_validates_direction(self):
        """Test that ATR stop for SHORT is above entry."""
        engine = StopLossEngine()
        data = self.create_ohlcv_data(n=20)
        entry_price = 100000.0  # Very high entry price

        result = engine.atr_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.SHORT,
            ohlcv_data=data,
        )
        # Should work normally - stop should be above entry
        assert result.stop_price > entry_price

    def test_validate_stop_direction_long_raises_when_stop_above(self):
        """Test _validate_stop_direction raises for LONG with stop above entry."""
        engine = StopLossEngine()

        with pytest.raises(ValueError, match="Invalid stop-loss for LONG position"):
            engine._validate_stop_direction(
                entry_price=50000.0,
                stop_price=51000.0,  # Above entry - WRONG for LONG
                direction=TradeDirection.LONG,
            )

    def test_validate_stop_direction_short_raises_when_stop_below(self):
        """Test _validate_stop_direction raises for SHORT with stop below entry."""
        engine = StopLossEngine()

        with pytest.raises(ValueError, match="Invalid stop-loss for SHORT position"):
            engine._validate_stop_direction(
                entry_price=50000.0,
                stop_price=49000.0,  # Below entry - WRONG for SHORT
                direction=TradeDirection.SHORT,
            )

    def test_validate_stop_direction_long_equal_raises(self):
        """Test _validate_stop_direction raises for LONG with stop equal to entry."""
        engine = StopLossEngine()

        with pytest.raises(ValueError, match="Invalid stop-loss for LONG position"):
            engine._validate_stop_direction(
                entry_price=50000.0,
                stop_price=50000.0,  # Equal to entry - WRONG for LONG
                direction=TradeDirection.LONG,
            )

    def test_validate_stop_direction_short_equal_raises(self):
        """Test _validate_stop_direction raises for SHORT with stop equal to entry."""
        engine = StopLossEngine()

        with pytest.raises(ValueError, match="Invalid stop-loss for SHORT position"):
            engine._validate_stop_direction(
                entry_price=50000.0,
                stop_price=50000.0,  # Equal to entry - WRONG for SHORT
                direction=TradeDirection.SHORT,
            )

    def test_validate_stop_direction_long_valid_passes(self):
        """Test _validate_stop_direction passes for valid LONG stop."""
        engine = StopLossEngine()

        # Should not raise
        engine._validate_stop_direction(
            entry_price=50000.0,
            stop_price=49000.0,  # Below entry - CORRECT for LONG
            direction=TradeDirection.LONG,
        )

    def test_validate_stop_direction_short_valid_passes(self):
        """Test _validate_stop_direction passes for valid SHORT stop."""
        engine = StopLossEngine()

        # Should not raise
        engine._validate_stop_direction(
            entry_price=50000.0,
            stop_price=51000.0,  # Above entry - CORRECT for SHORT
            direction=TradeDirection.SHORT,
        )

    # CRITICAL-002: Technical level wrong-side tests

    def test_technical_stop_long_with_resistance_above_raises(self):
        """Test technical stop for LONG with resistance above entry raises."""
        engine = StopLossEngine()
        entry_price = 50000.0

        # Wrong: Using a "support" that is actually above entry (like resistance)
        wrong_support = MockKeyLevel(
            price=51000.0,  # Above entry - WRONG for LONG support
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=wrong_support)

        with pytest.raises(ValueError, match="Invalid support level for LONG position"):
            engine.technical_level_stop(
                entry_price=entry_price,
                direction=TradeDirection.LONG,
                key_levels=key_levels,
            )

    def test_technical_stop_short_with_support_below_raises(self):
        """Test technical stop for SHORT with support below entry raises."""
        engine = StopLossEngine()
        entry_price = 50000.0

        # Wrong: Using a "resistance" that is actually below entry (like support)
        wrong_resistance = MockKeyLevel(
            price=49000.0,  # Below entry - WRONG for SHORT resistance
            level_type="resistance",
            strength=80.0,
            description="Swing high",
        )
        key_levels = MockKeyLevelsResult(nearest_resistance=wrong_resistance)

        with pytest.raises(
            ValueError, match="Invalid resistance level for SHORT position"
        ):
            engine.technical_level_stop(
                entry_price=entry_price,
                direction=TradeDirection.SHORT,
                key_levels=key_levels,
            )

    def test_technical_stop_long_level_equal_to_entry_raises(self):
        """Test technical stop for LONG with support equal to entry raises."""
        engine = StopLossEngine()
        entry_price = 50000.0

        support = MockKeyLevel(
            price=50000.0,  # Equal to entry - WRONG
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        with pytest.raises(ValueError, match="Invalid support level for LONG position"):
            engine.technical_level_stop(
                entry_price=entry_price,
                direction=TradeDirection.LONG,
                key_levels=key_levels,
            )

    def test_technical_stop_short_level_equal_to_entry_raises(self):
        """Test technical stop for SHORT with resistance equal to entry raises."""
        engine = StopLossEngine()
        entry_price = 50000.0

        resistance = MockKeyLevel(
            price=50000.0,  # Equal to entry - WRONG
            level_type="resistance",
            strength=80.0,
            description="Swing high",
        )
        key_levels = MockKeyLevelsResult(nearest_resistance=resistance)

        with pytest.raises(
            ValueError, match="Invalid resistance level for SHORT position"
        ):
            engine.technical_level_stop(
                entry_price=entry_price,
                direction=TradeDirection.SHORT,
                key_levels=key_levels,
            )

    # CRITICAL-003: Zero/negative price validation tests

    def test_validate_stop_price_positive_zero_raises(self):
        """Test _validate_stop_price_positive raises for zero stop price."""
        engine = StopLossEngine()

        with pytest.raises(ValueError, match="Invalid stop-loss price"):
            engine._validate_stop_price_positive(
                stop_price=0.0,
                stop_distance=1000.0,
            )

    def test_validate_stop_price_positive_negative_raises(self):
        """Test _validate_stop_price_positive raises for negative stop price."""
        engine = StopLossEngine()

        with pytest.raises(ValueError, match="Invalid stop-loss price"):
            engine._validate_stop_price_positive(
                stop_price=-100.0,
                stop_distance=1000.0,
            )

    def test_validate_stop_price_positive_negative_distance_raises(self):
        """Test _validate_stop_price_positive raises for negative stop distance."""
        engine = StopLossEngine()

        with pytest.raises(ValueError, match="Invalid stop distance"):
            engine._validate_stop_price_positive(
                stop_price=49000.0,
                stop_distance=-100.0,
            )

    def test_validate_stop_price_positive_valid_passes(self):
        """Test _validate_stop_price_positive passes for valid values."""
        engine = StopLossEngine()

        # Should not raise
        engine._validate_stop_price_positive(
            stop_price=49000.0,
            stop_distance=1000.0,
        )

    def test_validate_stop_price_positive_zero_distance_passes(self):
        """Test _validate_stop_price_positive passes for zero stop distance."""
        engine = StopLossEngine()

        # Should not raise - zero distance is edge case but technically valid
        engine._validate_stop_price_positive(
            stop_price=50000.0,
            stop_distance=0.0,
        )

    # Integration tests for percentage-based stops

    def test_percentage_stop_long_validates_direction(self):
        """Test percentage stop validates direction for LONG."""
        engine = StopLossEngine()
        entry_price = 50000.0

        result = engine.percentage_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            percentage=0.03,
        )

        # Stop should be below entry
        assert result.stop_price < entry_price
        assert result.stop_price == pytest.approx(48500.0, abs=0.01)

    def test_percentage_stop_short_validates_direction(self):
        """Test percentage stop validates direction for SHORT."""
        engine = StopLossEngine()
        entry_price = 50000.0

        result = engine.percentage_based_stop(
            entry_price=entry_price,
            direction=TradeDirection.SHORT,
            percentage=0.03,
        )

        # Stop should be above entry
        assert result.stop_price > entry_price
        assert result.stop_price == pytest.approx(51500.0, abs=0.01)
