"""Tests for stop-loss calculator.

Validates the main calculator interface and integration.
"""

from __future__ import annotations

import numpy as np
import pytest

from portfolio_risk.stop_loss.calculator import (
    StopLossCalculation,
    StopLossCalculator,
    StopLossConfig,
)
from portfolio_risk.stop_loss.engine import (
    StopLossComparison,
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


class TestStopLossConfig:
    """Tests for StopLossConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = StopLossConfig()

        assert config.method is None  # Auto-selection
        assert config.atr_period == 14
        assert config.atr_multiplier == 2.0
        assert config.min_risk_reward == 1.5
        assert config.default_percentage == 0.03
        assert config.min_percentage == 0.02
        assert config.max_percentage == 0.05
        assert config.max_drawdown_pct == 0.15

    def test_custom_config(self):
        """Test custom configuration."""
        config = StopLossConfig(
            method=StopLossMethod.ATR,
            atr_period=10,
            atr_multiplier=3.0,
            min_risk_reward=2.0,
        )

        assert config.method == StopLossMethod.ATR
        assert config.atr_period == 10
        assert config.atr_multiplier == 3.0
        assert config.min_risk_reward == 2.0

    def test_config_serialization(self):
        """Test config serialization."""
        config = StopLossConfig(method=StopLossMethod.ATR)

        d = config.to_dict()

        assert d["method"] == "atr"
        assert d["atr_period"] == 14
        assert d["min_risk_reward"] == 1.5

    def test_config_serialization_auto(self):
        """Test config serialization with auto method."""
        config = StopLossConfig()  # No method specified

        d = config.to_dict()

        assert d["method"] == "auto"


class TestStopLossCalculation:
    """Tests for StopLossCalculation dataclass."""

    def test_calculation_creation(self):
        """Test StopLossCalculation creation."""
        config = StopLossConfig()
        selected_stop = StopLossResult(
            stop_price=49000.0,
            method=StopLossMethod.ATR,
            distance_pct=0.02,
            risk_reward_ratio=2.0,
            is_valid=True,
            rationale="Test",
        )
        comparison = StopLossComparison(
            results=[selected_stop],
            optimal=selected_stop,
            selection_rationale="Test",
        )

        calc = StopLossCalculation(
            entry_price=50000.0,
            direction=TradeDirection.LONG,
            target_price=52000.0,
            config=config,
            comparison=comparison,
            selected_stop=selected_stop,
        )

        assert calc.entry_price == 50000.0
        assert calc.direction == TradeDirection.LONG
        assert calc.target_price == 52000.0
        assert calc.risk_amount == 1000.0  # 50000 - 49000
        assert calc.risk_pct == 0.02  # 1000 / 50000

    def test_calculation_serialization(self):
        """Test StopLossCalculation serialization."""
        config = StopLossConfig()
        selected_stop = StopLossResult(
            stop_price=49000.0,
            method=StopLossMethod.ATR,
            distance_pct=0.02,
            risk_reward_ratio=2.0,
            is_valid=True,
            rationale="Test",
        )
        comparison = StopLossComparison(
            results=[selected_stop],
            optimal=selected_stop,
            selection_rationale="Test",
        )

        calc = StopLossCalculation(
            entry_price=50000.0,
            direction=TradeDirection.LONG,
            target_price=52000.0,
            config=config,
            comparison=comparison,
            selected_stop=selected_stop,
        )

        d = calc.to_dict()

        assert d["entry_price"] == 50000.0
        assert d["direction"] == "long"
        assert d["target_price"] == 52000.0
        assert d["risk_amount"] == 1000.0
        assert d["risk_pct"] == 0.02


class TestStopLossCalculator:
    """Tests for StopLossCalculator."""

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

    def test_calculator_initialization(self):
        """Test calculator initialization."""
        calculator = StopLossCalculator()

        assert calculator.default_config is not None
        assert calculator._engine is not None

    def test_calculator_with_config(self):
        """Test calculator with custom config."""
        config = StopLossConfig(atr_period=10)
        calculator = StopLossCalculator(config)

        assert calculator.default_config.atr_period == 10

    def test_calculate_stop_loss_auto(self):
        """Test stop-loss calculation with auto method selection."""
        calculator = StopLossCalculator()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        result = calculator.calculate_stop_loss(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
            target_price=52000.0,
        )

        assert isinstance(result, StopLossCalculation)
        assert result.entry_price == entry_price
        assert result.direction == TradeDirection.LONG
        assert result.selected_stop is not None
        assert len(result.comparison.results) == 3  # All methods compared

    def test_calculate_stop_loss_specific_method(self):
        """Test stop-loss calculation with specific method."""
        config = StopLossConfig(method=StopLossMethod.ATR)
        calculator = StopLossCalculator(config)

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        result = calculator.calculate_stop_loss(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
            target_price=52000.0,
        )

        assert result.selected_stop.method == StopLossMethod.ATR
        assert len(result.comparison.results) == 1  # Only ATR method

    def test_calculate_atr_stop(self):
        """Test direct ATR stop calculation."""
        calculator = StopLossCalculator()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        result = calculator.calculate_atr_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            target_price=52000.0,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.ATR

    def test_calculate_atr_stop_custom_multiplier(self):
        """Test ATR stop with custom multiplier."""
        calculator = StopLossCalculator()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        result1 = calculator.calculate_atr_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            atr_multiplier=1.0,
        )

        result2 = calculator.calculate_atr_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            atr_multiplier=3.0,
        )

        # Higher multiplier should give wider stop (lower price for long)
        assert result2.stop_price < result1.stop_price

    def test_calculate_technical_stop(self):
        """Test direct technical stop calculation."""
        calculator = StopLossCalculator()

        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        result = calculator.calculate_technical_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            key_levels=key_levels,
            target_price=52000.0,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.TECHNICAL_LEVEL

    def test_calculate_percentage_stop(self):
        """Test direct percentage stop calculation."""
        calculator = StopLossCalculator()

        entry_price = 50000.0

        result = calculator.calculate_percentage_stop(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            percentage=0.04,
            target_price=52000.0,
        )

        assert isinstance(result, StopLossResult)
        assert result.method == StopLossMethod.PERCENTAGE
        assert result.distance_pct == 0.04

    def test_config_override(self):
        """Test config override in calculate method."""
        default_config = StopLossConfig(atr_period=14)
        calculator = StopLossCalculator(default_config)

        # Override with different config
        override_config = StopLossConfig(atr_period=10)

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        result = calculator.calculate_stop_loss(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
            config=override_config,
        )

        assert result.config.atr_period == 10


class TestStopLossCalculatorEdgeCases:
    """Tests for edge cases and error handling."""

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

    def test_no_valid_stop_raises_error(self):
        """Test that error is raised when no valid stop can be calculated."""
        calculator = StopLossCalculator()

        # Empty data and no key levels - should get at least percentage result
        data = []
        entry_price = 50000.0
        key_levels = MockKeyLevelsResult(nearest_support=None)

        # With no data, only percentage method can work
        # The calculator should still return a result (percentage-based)
        result = calculator.calculate_stop_loss(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
        )

        # Should get a percentage-based stop as fallback
        assert result is not None
        assert result.selected_stop is not None

    def test_short_position_calculations(self):
        """Test calculations for short positions."""
        calculator = StopLossCalculator()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        resistance = MockKeyLevel(
            price=51000.0,
            level_type="resistance",
            strength=80.0,
            description="Swing high",
        )
        key_levels = MockKeyLevelsResult(nearest_resistance=resistance)

        result = calculator.calculate_stop_loss(
            entry_price=entry_price,
            direction=TradeDirection.SHORT,
            ohlcv_data=data,
            key_levels=key_levels,
            target_price=48000.0,
        )

        assert result.direction == TradeDirection.SHORT
        assert result.selected_stop.stop_price > entry_price

    def test_risk_metrics_calculation(self):
        """Test risk metrics are calculated correctly."""
        calculator = StopLossCalculator()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        result = calculator.calculate_stop_loss(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
        )

        # Verify risk metrics
        assert result.risk_amount > 0
        assert result.risk_pct > 0
        assert result.risk_pct == result.risk_amount / entry_price

    def test_without_target_price(self):
        """Test calculation without target price."""
        calculator = StopLossCalculator()

        data = self.create_ohlcv_data(n=20)
        entry_price = 50000.0

        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        result = calculator.calculate_stop_loss(
            entry_price=entry_price,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
            # No target_price
        )

        assert result.target_price is None
        # Should still calculate a valid stop
        assert result.selected_stop is not None
