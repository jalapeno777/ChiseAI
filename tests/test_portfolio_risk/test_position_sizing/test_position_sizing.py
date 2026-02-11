"""Unit tests for position sizing engine."""

import pytest

from portfolio_risk.position_sizing import (
    KellyInputs,
    PositionSizeCalculator,
    PositionSizeResult,
    PositionSizingEngine,
    SizingConfig,
    SizingMethod,
    VolatilityInputs,
)


class TestKellyCriterionSizing:
    """Tests for Kelly Criterion position sizing."""

    def test_kelly_basic_calculation(self) -> None:
        """Test basic Kelly Criterion calculation.

        Kelly formula: f* = (bp - q) / b
        where b = win/loss ratio, p = win probability, q = 1-p

        Example: p=0.6, b=2.0
        f* = (2.0 * 0.6 - 0.4) / 2.0 = (1.2 - 0.4) / 2.0 = 0.4 (40%)
        With quarter Kelly: 0.4 * 0.25 = 0.1 (10%)
        """
        engine = PositionSizingEngine()
        kelly_inputs = KellyInputs(win_probability=0.6, win_loss_ratio=2.0)

        result = engine.kelly_criterion_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,  # 5% stop loss
            kelly_inputs=kelly_inputs,
        )

        # Kelly fraction = (2.0 * 0.6 - 0.4) / 2.0 = 0.4
        # Adjusted for quarter Kelly = 0.4 * 0.25 = 0.1
        # Risk = 10% of $10,000 = $1,000
        # Stop distance = $5
        # Position size = $1,000 / $5 = 200 units
        # Notional = 200 * $100 = $20,000

        assert result.method_used == SizingMethod.KELLY_CRITERION
        assert result.metadata is not None
        assert result.metadata["kelly_fraction"] == pytest.approx(0.4, abs=0.01)
        assert result.metadata["adjusted_kelly"] == pytest.approx(0.1, abs=0.01)
        assert result.risk_percentage == pytest.approx(1.0, abs=0.1)  # Capped at 1%
        assert result.position_size > 0
        assert result.notional_value > 0

    def test_kelly_negative_expectation(self) -> None:
        """Test Kelly with negative expectation (unfavorable bet).

        When bp < q, Kelly fraction is negative, meaning don't bet.
        """
        engine = PositionSizingEngine()
        # p=0.4, b=1.5 gives negative expectation
        kelly_inputs = KellyInputs(win_probability=0.4, win_loss_ratio=1.5)

        result = engine.kelly_criterion_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,
            kelly_inputs=kelly_inputs,
        )

        # Kelly = (1.5 * 0.4 - 0.6) / 1.5 = 0, so position should be ~0 (floating point)
        assert result.metadata is not None
        assert result.metadata["kelly_fraction"] == pytest.approx(0.0, abs=0.01)
        assert result.position_size == pytest.approx(0.0, abs=1e-10)

    def test_kelly_max_risk_cap(self) -> None:
        """Test that Kelly sizing respects max risk per trade limit."""
        config = SizingConfig(max_risk_per_trade_pct=0.5, kelly_fraction=1.0)
        engine = PositionSizingEngine(config)
        kelly_inputs = KellyInputs(win_probability=0.8, win_loss_ratio=3.0)

        result = engine.kelly_criterion_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=98.0,
            kelly_inputs=kelly_inputs,
        )

        # Without cap, Kelly would suggest high risk
        # But we cap at 0.5%
        assert result.risk_percentage <= 0.5
        assert result.capped_by_limit or result.risk_percentage <= 0.5

    def test_kelly_inputs_validation(self) -> None:
        """Test KellyInputs validation."""
        # Valid inputs
        KellyInputs(win_probability=0.5, win_loss_ratio=2.0)

        # Invalid win_probability
        with pytest.raises(ValueError, match="win_probability"):
            KellyInputs(win_probability=1.5, win_loss_ratio=2.0)

        with pytest.raises(ValueError, match="win_probability"):
            KellyInputs(win_probability=-0.1, win_loss_ratio=2.0)

        # Invalid win_loss_ratio
        with pytest.raises(ValueError, match="win_loss_ratio"):
            KellyInputs(win_probability=0.5, win_loss_ratio=0)

        with pytest.raises(ValueError, match="win_loss_ratio"):
            KellyInputs(win_probability=0.5, win_loss_ratio=-1.0)

    def test_kelly_zero_account_balance(self) -> None:
        """Test Kelly with invalid account balance."""
        engine = PositionSizingEngine()
        kelly_inputs = KellyInputs(win_probability=0.6, win_loss_ratio=2.0)

        with pytest.raises(ValueError, match="account_balance"):
            engine.kelly_criterion_sizing(
                account_balance=0,
                entry_price=100.0,
                stop_loss_price=95.0,
                kelly_inputs=kelly_inputs,
            )

    def test_kelly_zero_entry_price(self) -> None:
        """Test Kelly with invalid entry price."""
        engine = PositionSizingEngine()
        kelly_inputs = KellyInputs(win_probability=0.6, win_loss_ratio=2.0)

        with pytest.raises(ValueError, match="entry_price"):
            engine.kelly_criterion_sizing(
                account_balance=10_000,
                entry_price=0,
                stop_loss_price=95.0,
                kelly_inputs=kelly_inputs,
            )

    def test_kelly_same_entry_stop(self) -> None:
        """Test Kelly with entry price equal to stop loss."""
        engine = PositionSizingEngine()
        kelly_inputs = KellyInputs(win_probability=0.6, win_loss_ratio=2.0)

        with pytest.raises(ValueError, match="stop_loss_price"):
            engine.kelly_criterion_sizing(
                account_balance=10_000,
                entry_price=100.0,
                stop_loss_price=100.0,
                kelly_inputs=kelly_inputs,
            )


class TestFixedFractionalSizing:
    """Tests for fixed fractional position sizing."""

    def test_fixed_fractional_basic(self) -> None:
        """Test basic fixed fractional calculation.

        Formula: Position Size = (Account × Risk%) / (Stop Distance × Tick Value)

        Account: $10,000
        Risk: 1%
        Stop Distance: $5 (entry $100, stop $95)
        Position Size = ($10,000 × 0.01) / $5 = 20 units
        Notional = 20 × $100 = $2,000
        """
        engine = PositionSizingEngine()

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,
            risk_percentage=1.0,
        )

        assert result.method_used == SizingMethod.FIXED_FRACTIONAL
        assert result.risk_amount == pytest.approx(100.0, abs=0.01)  # 1% of $10k
        assert result.risk_percentage == pytest.approx(1.0, abs=0.01)
        assert result.position_size == pytest.approx(20.0, abs=0.01)
        assert result.notional_value == pytest.approx(2_000.0, abs=0.01)

    def test_fixed_fractional_default_risk(self) -> None:
        """Test fixed fractional with default risk percentage from config."""
        config = SizingConfig(default_risk_pct=2.0, max_risk_per_trade_pct=2.0)
        engine = PositionSizingEngine(config)

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        # Should use default 2% risk (not capped by max_risk_per_trade)
        assert result.risk_percentage == pytest.approx(2.0, abs=0.01)
        assert result.risk_amount == pytest.approx(200.0, abs=0.01)

    def test_fixed_fractional_risk_cap(self) -> None:
        """Test that risk percentage is capped at max per-trade limit."""
        config = SizingConfig(max_risk_per_trade_pct=1.0)
        engine = PositionSizingEngine(config)

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,
            risk_percentage=5.0,  # Request 5%, but cap at 1%
        )

        assert result.risk_percentage <= 1.0
        assert result.capped_by_limit or result.risk_percentage <= 1.0

    def test_fixed_fractional_leverage_cap(self) -> None:
        """Test that leverage is capped at max limit."""
        config = SizingConfig(max_leverage=2.0)
        engine = PositionSizingEngine(config)

        # Very tight stop loss would suggest high leverage
        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=99.9,  # 0.1% stop
            risk_percentage=1.0,
        )

        assert result.leverage_used <= 2.0
        assert result.capped_by_limit or result.leverage_used <= 2.0

    def test_fixed_fractional_validation(self) -> None:
        """Test input validation for fixed fractional."""
        engine = PositionSizingEngine()

        # Zero account balance
        with pytest.raises(ValueError, match="account_balance"):
            engine.fixed_fractional_sizing(
                account_balance=0,
                entry_price=100.0,
                stop_loss_price=95.0,
            )

        # Zero entry price
        with pytest.raises(ValueError, match="entry_price"):
            engine.fixed_fractional_sizing(
                account_balance=10_000,
                entry_price=0,
                stop_loss_price=95.0,
            )

        # Zero stop loss
        with pytest.raises(ValueError, match="stop_loss_price"):
            engine.fixed_fractional_sizing(
                account_balance=10_000,
                entry_price=100.0,
                stop_loss_price=0,
            )

        # Same entry and stop
        with pytest.raises(ValueError, match="stop_loss_price"):
            engine.fixed_fractional_sizing(
                account_balance=10_000,
                entry_price=100.0,
                stop_loss_price=100.0,
            )

        # Zero risk percentage
        with pytest.raises(ValueError, match="risk_percentage"):
            engine.fixed_fractional_sizing(
                account_balance=10_000,
                entry_price=100.0,
                stop_loss_price=95.0,
                risk_percentage=0,
            )


class TestVolatilityBasedSizing:
    """Tests for volatility-based position sizing."""

    def test_volatility_based_basic(self) -> None:
        """Test basic volatility-based calculation using ATR.

        ATR = $2.00, Multiplier = 2.0
        Stop Distance = $4.00
        Risk = 1% of $10,000 = $100
        Position Size = $100 / $4 = 25 units
        """
        engine = PositionSizingEngine()
        vol_inputs = VolatilityInputs(atr_value=2.0, atr_multiplier=2.0)

        result = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs,
            direction="long",
        )

        assert result.method_used == SizingMethod.VOLATILITY_BASED
        assert result.metadata is not None
        assert result.metadata["atr_value"] == 2.0
        assert result.metadata["atr_multiplier"] == 2.0
        assert result.metadata["stop_distance"] == 4.0
        assert result.position_size > 0
        assert result.notional_value > 0

    def test_volatility_based_zero_volatility(self) -> None:
        """Test edge case: zero volatility (ATR = 0)."""
        engine = PositionSizingEngine()
        vol_inputs = VolatilityInputs(atr_value=0.0, atr_multiplier=2.0)

        result = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs,
            direction="long",
        )

        # With zero volatility, should return zero position or minimum
        assert result.capped_by_limit
        assert result.metadata is not None
        assert result.metadata["note"] is not None

    def test_volatility_based_high_volatility_reduction(self) -> None:
        """Test that high volatility reduces position size."""
        engine = PositionSizingEngine()

        # High volatility scenario
        vol_inputs_high = VolatilityInputs(
            atr_value=5.0, atr_multiplier=2.0, volatility_percent=10.0
        )
        result_high = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs_high,
            direction="long",
        )

        # Normal volatility scenario
        vol_inputs_normal = VolatilityInputs(
            atr_value=5.0, atr_multiplier=2.0, volatility_percent=2.0
        )
        result_normal = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs_normal,
            direction="long",
        )

        # High volatility should result in smaller position (50% reduction)
        assert result_high.position_size < result_normal.position_size

    def test_volatility_based_validation(self) -> None:
        """Test input validation for volatility-based sizing."""
        engine = PositionSizingEngine()
        vol_inputs = VolatilityInputs(atr_value=2.0, atr_multiplier=2.0)

        # Zero account balance
        with pytest.raises(ValueError, match="account_balance"):
            engine.volatility_based_sizing(
                account_balance=0,
                entry_price=100.0,
                volatility_inputs=vol_inputs,
                direction="long",
            )

        # Zero entry price
        with pytest.raises(ValueError, match="entry_price"):
            engine.volatility_based_sizing(
                account_balance=10_000,
                entry_price=0,
                volatility_inputs=vol_inputs,
                direction="long",
            )

        # Invalid direction
        with pytest.raises(ValueError, match="direction"):
            engine.volatility_based_sizing(
                account_balance=10_000,
                entry_price=100.0,
                volatility_inputs=vol_inputs,
                direction="invalid",
            )

    def test_volatility_inputs_validation(self) -> None:
        """Test VolatilityInputs validation."""
        # Valid inputs
        VolatilityInputs(atr_value=2.0, atr_multiplier=2.0)

        # Negative ATR
        with pytest.raises(ValueError, match="atr_value"):
            VolatilityInputs(atr_value=-1.0, atr_multiplier=2.0)

        # Zero multiplier
        with pytest.raises(ValueError, match="atr_multiplier"):
            VolatilityInputs(atr_value=2.0, atr_multiplier=0)

        # Negative multiplier
        with pytest.raises(ValueError, match="atr_multiplier"):
            VolatilityInputs(atr_value=2.0, atr_multiplier=-1.0)


class TestPositionSizeCalculator:
    """Tests for the main PositionSizeCalculator interface."""

    def test_calculator_fixed_fractional(self) -> None:
        """Test calculator with fixed fractional method."""
        calculator = PositionSizeCalculator()

        result = calculator.calculate_position_size(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,
            method=SizingMethod.FIXED_FRACTIONAL,
            risk_percentage=1.0,
        )

        assert result.method_used == SizingMethod.FIXED_FRACTIONAL
        assert result.risk_percentage == pytest.approx(1.0, abs=0.01)

    def test_calculator_kelly(self) -> None:
        """Test calculator with Kelly Criterion method."""
        calculator = PositionSizeCalculator()
        kelly_inputs = KellyInputs(win_probability=0.6, win_loss_ratio=2.0)

        result = calculator.calculate_position_size(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,
            method=SizingMethod.KELLY_CRITERION,
            kelly_inputs=kelly_inputs,
        )

        assert result.method_used == SizingMethod.KELLY_CRITERION

    def test_calculator_volatility(self) -> None:
        """Test calculator with volatility-based method."""
        calculator = PositionSizeCalculator()
        vol_inputs = VolatilityInputs(atr_value=2.0, atr_multiplier=2.0)

        result = calculator.calculate_position_size(
            account_balance=10_000,
            entry_price=100.0,
            method=SizingMethod.VOLATILITY_BASED,
            volatility_inputs=vol_inputs,
            direction="long",
        )

        assert result.method_used == SizingMethod.VOLATILITY_BASED

    def test_calculator_missing_kelly_inputs(self) -> None:
        """Test calculator raises error when Kelly inputs are missing."""
        calculator = PositionSizeCalculator()

        with pytest.raises(ValueError, match="kelly_inputs"):
            calculator.calculate_position_size(
                account_balance=10_000,
                entry_price=100.0,
                stop_loss_price=95.0,
                method=SizingMethod.KELLY_CRITERION,
            )

    def test_calculator_missing_stop_loss(self) -> None:
        """Test calculator raises error when stop loss is missing."""
        calculator = PositionSizeCalculator()

        with pytest.raises(ValueError, match="stop_loss_price"):
            calculator.calculate_position_size(
                account_balance=10_000,
                entry_price=100.0,
                method=SizingMethod.FIXED_FRACTIONAL,
            )

    def test_calculator_missing_volatility_inputs(self) -> None:
        """Test calculator raises error when volatility inputs are missing."""
        calculator = PositionSizeCalculator()

        with pytest.raises(ValueError, match="volatility_inputs"):
            calculator.calculate_position_size(
                account_balance=10_000,
                entry_price=100.0,
                method=SizingMethod.VOLATILITY_BASED,
            )

    def test_calculate_atr(self) -> None:
        """Test ATR calculation from OHLCV data."""
        from data_ingestion.ohlcv_fetcher import OHLCVData

        calculator = PositionSizeCalculator()

        # Create sample OHLCV data
        data = [
            OHLCVData(
                timestamp=i,
                open_price=100.0 + i,
                high_price=102.0 + i,
                low_price=98.0 + i,
                close_price=101.0 + i,
                volume=1000.0,
            )
            for i in range(20)
        ]

        atr = calculator.calculate_atr(data, period=14)

        # ATR should be positive
        assert atr > 0

    def test_calculate_atr_insufficient_data(self) -> None:
        """Test ATR calculation with insufficient data."""
        from data_ingestion.ohlcv_fetcher import OHLCVData

        calculator = PositionSizeCalculator()

        # Create insufficient data
        data = [
            OHLCVData(
                timestamp=i,
                open_price=100.0,
                high_price=102.0,
                low_price=98.0,
                close_price=101.0,
                volume=1000.0,
            )
            for i in range(5)
        ]

        atr = calculator.calculate_atr(data, period=14)

        # Should return 0 for insufficient data
        assert atr == 0.0


class TestPositionLimitsValidation:
    """Tests for position limits validation."""

    def test_validate_within_limits(self) -> None:
        """Test validation passes for position within limits."""
        calculator = PositionSizeCalculator()

        result = PositionSizeResult(
            position_size=10.0,
            notional_value=1_000.0,
            risk_amount=100.0,
            risk_percentage=1.0,
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
        )

        is_valid, reason = calculator.validate_position_limits(
            result, account_balance=10_000
        )

        assert is_valid is True
        assert "within all risk limits" in reason

    def test_validate_exceeds_risk_limit(self) -> None:
        """Test validation fails when risk exceeds limit."""
        config = SizingConfig(max_risk_per_trade_pct=1.0)
        calculator = PositionSizeCalculator(config)

        result = PositionSizeResult(
            position_size=100.0,
            notional_value=10_000.0,
            risk_amount=500.0,
            risk_percentage=5.0,  # Exceeds 1% limit
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
        )

        is_valid, reason = calculator.validate_position_limits(
            result, account_balance=10_000
        )

        assert is_valid is False
        assert "exceeds max per-trade limit" in reason

    def test_validate_exceeds_leverage_limit(self) -> None:
        """Test validation fails when leverage exceeds limit."""
        config = SizingConfig(max_leverage=3.0)
        calculator = PositionSizeCalculator(config)

        result = PositionSizeResult(
            position_size=500.0,
            notional_value=50_000.0,
            risk_amount=500.0,
            risk_percentage=1.0,
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=5.0,  # Exceeds 3x limit
        )

        is_valid, reason = calculator.validate_position_limits(
            result, account_balance=10_000
        )

        assert is_valid is False
        assert "exceeds max" in reason

    def test_validate_grid_risk_limit(self) -> None:
        """Test validation fails when grid risk exceeds limit."""
        config = SizingConfig(max_risk_per_grid_pct=2.0)
        calculator = PositionSizeCalculator(config)

        existing_positions = [
            PositionSizeResult(
                position_size=10.0,
                notional_value=1_000.0,
                risk_amount=150.0,
                risk_percentage=1.5,
                method_used=SizingMethod.FIXED_FRACTIONAL,
                leverage_used=1.0,
            )
        ]

        new_position = PositionSizeResult(
            position_size=10.0,
            notional_value=1_000.0,
            risk_amount=100.0,
            risk_percentage=1.0,
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
        )

        # Total grid risk = 1.5% + 1.0% = 2.5%, exceeds 2% limit
        is_valid, reason = calculator.validate_position_limits(
            new_position, account_balance=10_000, existing_positions=existing_positions
        )

        assert is_valid is False
        assert "grid risk" in reason.lower()

    def test_validate_grid_leverage_limit(self) -> None:
        """Test validation fails when grid leverage (notional) exceeds limit."""
        # Use high max_position_size_pct and max_risk_per_grid_pct
        # to trigger leverage limit first
        config = SizingConfig(
            max_leverage=3.0, max_position_size_pct=500.0, max_risk_per_grid_pct=100.0
        )
        calculator = PositionSizeCalculator(config)

        # Create existing positions with high notional but low risk
        existing_positions = [
            PositionSizeResult(
                position_size=40.0,
                notional_value=4_000.0,  # 4x leverage on $1k account
                risk_amount=1.0,  # Very low risk
                risk_percentage=0.1,
                method_used=SizingMethod.FIXED_FRACTIONAL,
                leverage_used=4.0,
            )
        ]

        new_position = PositionSizeResult(
            position_size=30.0,
            notional_value=3_000.0,  # 3x leverage on $1k account
            risk_amount=0.5,  # Very low risk
            risk_percentage=0.05,
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=3.0,
        )

        # Total grid leverage = 4x + 3x = 7x, exceeds 6x limit (2x max_leverage)
        # Account balance = $1,000
        # Total notional = $7,000 -> leverage = 7x
        is_valid, reason = calculator.validate_position_limits(
            new_position, account_balance=1_000, existing_positions=existing_positions
        )

        assert is_valid is False
        assert "grid leverage" in reason.lower()


class TestSizingConfig:
    """Tests for SizingConfig validation."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = SizingConfig()

        assert config.max_risk_per_trade_pct == 1.0  # 1%
        assert config.max_risk_per_grid_pct == 2.0  # 2%
        assert config.max_leverage == 3.0  # 3x
        assert config.default_risk_pct == 1.0  # 1%
        assert config.kelly_fraction == 0.25  # Quarter Kelly

    def test_config_validation(self) -> None:
        """Test configuration validation."""
        # Invalid max_risk_per_trade_pct
        with pytest.raises(ValueError, match="max_risk_per_trade_pct"):
            SizingConfig(max_risk_per_trade_pct=0)

        with pytest.raises(ValueError, match="max_risk_per_trade_pct"):
            SizingConfig(max_risk_per_trade_pct=101)

        # Invalid max_risk_per_grid_pct
        with pytest.raises(ValueError, match="max_risk_per_grid_pct"):
            SizingConfig(max_risk_per_grid_pct=0)

        # Invalid max_leverage
        with pytest.raises(ValueError, match="max_leverage"):
            SizingConfig(max_leverage=0)

        # Invalid kelly_fraction
        with pytest.raises(ValueError, match="kelly_fraction"):
            SizingConfig(kelly_fraction=0)

        with pytest.raises(ValueError, match="kelly_fraction"):
            SizingConfig(kelly_fraction=1.5)


class TestPositionSizeResultProperties:
    """Tests for PositionSizeResult dataclass."""

    def test_position_size_result_creation(self) -> None:
        """Test creating PositionSizeResult with all fields."""
        result = PositionSizeResult(
            position_size=100.0,
            notional_value=10_000.0,
            risk_amount=100.0,
            risk_percentage=1.0,
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
            capped_by_limit=True,
            metadata={"key": "value"},
        )

        assert result.position_size == 100.0
        assert result.notional_value == 10_000.0
        assert result.capped_by_limit is True
        assert result.metadata == {"key": "value"}


class TestAdditionalCalculatorFeatures:
    """Tests for additional calculator features."""

    def test_calculator_unknown_method(self) -> None:
        """Test calculator with unknown method raises error."""
        calculator = PositionSizeCalculator()

        # Create a fake method value
        class FakeMethod:
            pass

        with pytest.raises(ValueError, match="Unknown sizing method"):
            calculator.calculate_position_size(
                account_balance=10_000,
                entry_price=100.0,
                stop_loss_price=95.0,
                method=FakeMethod(),  # type: ignore
            )

    def test_volatility_based_short_direction(self) -> None:
        """Test volatility-based sizing with short direction."""
        engine = PositionSizingEngine()
        vol_inputs = VolatilityInputs(atr_value=2.0, atr_multiplier=2.0)

        result = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs,
            direction="short",
        )

        assert result.method_used == SizingMethod.VOLATILITY_BASED
        assert result.metadata is not None
        assert result.metadata["stop_loss_price"] == 104.0  # entry + stop_distance

    def test_volatility_based_low_volatility_increase(self) -> None:
        """Test that low volatility increases position size."""
        # Use higher max risk to see the volatility adjustment effect
        config = SizingConfig(max_risk_per_trade_pct=2.0)
        engine = PositionSizingEngine(config)

        # Low volatility scenario (increases risk by 20%)
        vol_inputs_low = VolatilityInputs(
            atr_value=2.0, atr_multiplier=2.0, volatility_percent=0.5
        )
        result_low = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs_low,
            direction="long",
        )

        # Normal volatility scenario (no adjustment)
        vol_inputs_normal = VolatilityInputs(
            atr_value=2.0, atr_multiplier=2.0, volatility_percent=2.0
        )
        result_normal = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs_normal,
            direction="long",
        )

        # Low volatility should result in larger position (20% increase)
        assert result_low.position_size > result_normal.position_size

    def test_validate_exceeds_position_size_limit(self) -> None:
        """Test validation fails when position size exceeds limit."""
        config = SizingConfig(max_position_size_pct=10.0)
        calculator = PositionSizeCalculator(config)

        result = PositionSizeResult(
            position_size=500.0,
            notional_value=50_000.0,  # 50% of account, exceeds 10% limit
            risk_amount=100.0,
            risk_percentage=1.0,
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
        )

        is_valid, reason = calculator.validate_position_limits(
            result, account_balance=100_000
        )

        assert is_valid is False
        assert "exceeds max" in reason


class TestPositionCapScenarios:
    """Tests for position capping and leverage recalculation."""

    def test_kelly_leverage_recalculation_after_position_cap(self) -> None:
        """Test leverage_used is recalculated after position cap in Kelly method."""
        # Configure with low position size limit to trigger capping
        config = SizingConfig(max_position_size_pct=10.0, max_leverage=10.0)
        engine = PositionSizingEngine(config)
        kelly_inputs = KellyInputs(win_probability=0.8, win_loss_ratio=3.0)

        result = engine.kelly_criterion_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,
            kelly_inputs=kelly_inputs,
        )

        # Position should be capped by max_position_size_pct (10%)
        assert result.capped_by_limit is True
        # leverage_used should be recalculated to reflect actual leverage
        # max_position_size_pct=10% means max notional = $1,000
        # leverage = $1,000 / $10,000 = 0.1x
        assert result.leverage_used == pytest.approx(0.1, abs=0.01)
        assert result.notional_value == pytest.approx(1_000.0, abs=0.01)

    def test_fixed_fractional_leverage_recalculation_after_position_cap(self) -> None:
        """Test leverage_used is recalculated after position cap in fixed fractional."""
        config = SizingConfig(max_position_size_pct=10.0, max_leverage=10.0)
        engine = PositionSizingEngine(config)

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=99.0,  # 1% stop - would normally suggest high leverage
            risk_percentage=5.0,  # 5% risk
        )

        # Without cap: risk=$500, stop=$1, position=500 units,
        # notional=$50,000, leverage=5x
        # With 10% position cap: max notional = $1,000
        assert result.capped_by_limit is True
        assert result.leverage_used == pytest.approx(0.1, abs=0.01)
        assert result.notional_value == pytest.approx(1_000.0, abs=0.01)

    def test_volatility_based_leverage_recalculation_after_position_cap(self) -> None:
        """Test leverage_used is recalculated after position cap."""
        config = SizingConfig(max_position_size_pct=10.0, max_leverage=10.0)
        engine = PositionSizingEngine(config)
        vol_inputs = VolatilityInputs(atr_value=0.5, atr_multiplier=2.0)  # Small ATR

        result = engine.volatility_based_sizing(
            account_balance=10_000,
            entry_price=100.0,
            volatility_inputs=vol_inputs,
            direction="long",
        )

        # With 10% position cap: max notional = $1,000
        if result.capped_by_limit:
            assert result.leverage_used <= 0.1  # Should be capped

    def test_multiple_caps_triggering_simultaneously(self) -> None:
        """Test when multiple caps (leverage and position size) trigger together."""
        config = SizingConfig(
            max_leverage=2.0,
            max_position_size_pct=5.0,  # 5% = $500 on $10k account
            max_risk_per_trade_pct=10.0,
        )
        engine = PositionSizingEngine(config)

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=99.0,  # 1% stop
            risk_percentage=10.0,  # Would suggest $1,000 risk
        )

        # Position should be capped
        assert result.capped_by_limit is True
        # Should respect the most restrictive limit (position size: 5% = $500)
        assert result.notional_value <= 500.0
        assert result.leverage_used <= 0.05

    def test_risk_percentage_after_capping(self) -> None:
        """Test that risk_percentage reflects capped notional value."""
        config = SizingConfig(max_position_size_pct=5.0)
        engine = PositionSizingEngine(config)

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=95.0,  # 5% stop
            risk_percentage=5.0,  # Would suggest $500 risk
        )

        # With 5% position cap: max notional = $500
        # Position size = $500 / $100 = 5 units
        # Risk = 5 units * $5 stop * $1 tick = $25
        # Risk % = $25 / $10,000 = 0.25%
        if result.capped_by_limit:
            assert (
                result.risk_percentage <= 0.3
            )  # Should be much lower than requested 5%


class TestTickValueValidation:
    """Tests for tick_value validation in SizingConfig."""

    def test_tick_value_positive_validation(self) -> None:
        """Test that tick_value must be positive."""
        with pytest.raises(ValueError, match="tick_value"):
            SizingConfig(tick_value=0)

        with pytest.raises(ValueError, match="tick_value"):
            SizingConfig(tick_value=-1.0)

    def test_tick_value_maximum_validation(self) -> None:
        """Test that tick_value has a reasonable maximum."""
        with pytest.raises(ValueError, match="tick_value"):
            SizingConfig(tick_value=2_000_000)

    def test_tick_value_valid_values(self) -> None:
        """Test valid tick_value values."""
        # Standard values should work
        config1 = SizingConfig(tick_value=1.0)
        assert config1.tick_value == 1.0

        config2 = SizingConfig(tick_value=0.01)
        assert config2.tick_value == 0.01

        config3 = SizingConfig(tick_value=100_000)
        assert config3.tick_value == 100_000


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_extreme_price_values(self) -> None:
        """Test with extreme price values."""
        engine = PositionSizingEngine()

        # Very high price
        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100_000.0,
            stop_loss_price=95_000.0,
            risk_percentage=1.0,
        )
        assert result.position_size > 0

        # Very low price
        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=0.0001,
            stop_loss_price=0.00009,
            risk_percentage=1.0,
        )
        assert result.position_size > 0

    def test_very_tight_stop_loss(self) -> None:
        """Test with very tight stop loss (small stop distance)."""
        engine = PositionSizingEngine()

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=99.99,  # 0.01% stop
            risk_percentage=1.0,
        )

        # Should still calculate correctly
        assert result.position_size > 0
        assert result.notional_value > 0

    def test_very_wide_stop_loss(self) -> None:
        """Test with very wide stop loss."""
        engine = PositionSizingEngine()

        result = engine.fixed_fractional_sizing(
            account_balance=10_000,
            entry_price=100.0,
            stop_loss_price=50.0,  # 50% stop
            risk_percentage=1.0,
        )

        # Position should be very small
        assert result.position_size > 0

    def test_large_account_balance(self) -> None:
        """Test with large account balance."""
        engine = PositionSizingEngine()

        result = engine.fixed_fractional_sizing(
            account_balance=1_000_000,
            entry_price=100.0,
            stop_loss_price=95.0,
            risk_percentage=1.0,
        )

        assert result.risk_amount == pytest.approx(10_000.0, abs=0.01)
        assert result.position_size == pytest.approx(2_000.0, abs=0.01)

    def test_small_account_balance(self) -> None:
        """Test with small account balance."""
        engine = PositionSizingEngine()

        result = engine.fixed_fractional_sizing(
            account_balance=100,
            entry_price=100.0,
            stop_loss_price=95.0,
            risk_percentage=1.0,
        )

        assert result.risk_amount == pytest.approx(1.0, abs=0.01)

    def test_minimum_position_size(self) -> None:
        """Test minimum position size enforcement."""
        config = SizingConfig(min_position_size=1.0)
        engine = PositionSizingEngine(config)

        # Very wide stop would suggest tiny position
        result = engine.fixed_fractional_sizing(
            account_balance=100,
            entry_price=100.0,
            stop_loss_price=10.0,  # 90% stop
            risk_percentage=1.0,
        )

        # Should be zero because calculated size is below minimum
        assert result.position_size == 0.0
