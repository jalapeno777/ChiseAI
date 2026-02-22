"""Tests for live gating risk enforcer.

Tests risk control validation and enforcement.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from execution.live_gating.risk_enforcer import RiskEnforcer, ValidationResult


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_valid_result(self):
        """Test valid validation result."""
        result = ValidationResult(valid=True, violations=[])
        assert result.valid is True
        assert len(result.violations) == 0

    def test_invalid_result_with_violations(self):
        """Test invalid validation result with violations."""
        result = ValidationResult(
            valid=True,  # Should be auto-corrected to False
            violations=["Risk too high"],
        )
        assert result.valid is False

    def test_to_dict(self):
        """Test serialization."""
        result = ValidationResult(
            valid=False,
            violations=["Leverage too high"],
            trade_params={"leverage": 5.0},
        )
        d = result.to_dict()
        assert d["valid"] is False
        assert d["violations"] == ["Leverage too high"]
        assert d["trade_params"]["leverage"] == 5.0


class TestRiskEnforcerInitialization:
    """Test RiskEnforcer initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        enforcer = RiskEnforcer()
        assert enforcer.portfolio_value == 10000.0

    def test_custom_portfolio_value(self):
        """Test custom portfolio value."""
        enforcer = RiskEnforcer(portfolio_value=50000.0)
        assert enforcer.portfolio_value == 50000.0

    def test_invalid_portfolio_value(self):
        """Test invalid portfolio value raises error."""
        with pytest.raises(ValueError, match="Portfolio value must be positive"):
            RiskEnforcer(portfolio_value=0)

    def test_negative_portfolio_value(self):
        """Test negative portfolio value raises error."""
        with pytest.raises(ValueError, match="Portfolio value must be positive"):
            RiskEnforcer(portfolio_value=-1000.0)


class TestLeverageCap:
    """Test leverage cap enforcement."""

    def test_enforce_leverage_within_cap(self):
        """Test leverage within cap passes."""
        enforcer = RiskEnforcer()
        assert enforcer.enforce_leverage_cap(1.0) is True
        assert enforcer.enforce_leverage_cap(2.0) is True
        assert enforcer.enforce_leverage_cap(3.0) is True

    def test_enforce_leverage_exceeds_cap(self):
        """Test leverage exceeding cap fails."""
        enforcer = RiskEnforcer()
        assert enforcer.enforce_leverage_cap(3.1) is False
        assert enforcer.enforce_leverage_cap(5.0) is False

    def test_enforce_leverage_zero(self):
        """Test zero leverage fails."""
        enforcer = RiskEnforcer()
        assert enforcer.enforce_leverage_cap(0.0) is False

    def test_enforce_leverage_negative(self):
        """Test negative leverage fails."""
        enforcer = RiskEnforcer()
        assert enforcer.enforce_leverage_cap(-1.0) is False

    def test_max_leverage_constant(self):
        """Test max leverage constant is 3.0."""
        assert RiskEnforcer.MAX_LEVERAGE == 3.0


class TestPositionLimit:
    """Test position limit enforcement."""

    def test_enforce_position_within_limit(self):
        """Test position within limit passes."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        # Small position should pass
        assert enforcer.enforce_position_limit(0.01, "BTCUSDT") is True

    def test_enforce_position_with_symbol(self):
        """Test position limit with symbol."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        result = enforcer.enforce_position_limit(0.1, "ETHUSDT")
        # Result depends on calculation, but should not error
        assert isinstance(result, bool)


class TestDailyLossCap:
    """Test daily loss cap checking."""

    def test_check_daily_loss_within_cap(self):
        """Test daily loss within cap passes."""
        enforcer = RiskEnforcer()
        enforcer._daily_loss = -500.0
        assert enforcer.check_daily_loss_cap(1000.0) is True

    def test_check_daily_loss_exceeds_cap(self):
        """Test daily loss exceeding cap fails."""
        enforcer = RiskEnforcer()
        enforcer._daily_loss = -1500.0
        assert enforcer.check_daily_loss_cap(1000.0) is False

    def test_check_daily_loss_exactly_at_cap(self):
        """Test daily loss exactly at cap passes."""
        enforcer = RiskEnforcer()
        enforcer._daily_loss = -1000.0
        assert enforcer.check_daily_loss_cap(1000.0) is True


class TestTradeValidation:
    """Test comprehensive trade validation."""

    def test_validate_trade_valid(self):
        """Test valid trade passes validation."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        trade_params = {
            "size": 0.01,
            "leverage": 2.0,
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        assert result.valid is True
        assert len(result.violations) == 0

    def test_validate_trade_leverage_violation(self):
        """Test trade with excessive leverage fails."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        trade_params = {
            "size": 0.01,
            "leverage": 5.0,  # Exceeds 3x
            "entry_price": 50000.0,
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        assert result.valid is False
        assert any("leverage" in v.lower() for v in result.violations)

    def test_validate_trade_risk_calculation_long(self):
        """Test risk calculation for long position."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        trade_params = {
            "size": 1.0,
            "leverage": 1.0,
            "entry_price": 50000.0,
            "stop_loss": 40000.0,  # 20% stop
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        # Risk = 1.0 * (50000 - 40000) = 10000
        # Risk % = 10000 / 10000 * 100 = 100%
        assert result.valid is False
        assert any("risk" in v.lower() for v in result.violations)

    def test_validate_trade_risk_calculation_short(self):
        """Test risk calculation for short position."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        trade_params = {
            "size": 1.0,
            "leverage": 1.0,
            "entry_price": 50000.0,
            "stop_loss": 60000.0,  # 20% stop for short
            "symbol": "BTCUSDT",
            "side": "short",
        }
        result = enforcer.validate_trade(trade_params)
        # Risk = 1.0 * (60000 - 50000) = 10000
        assert result.valid is False
        assert any("risk" in v.lower() for v in result.violations)

    def test_validate_trade_notional_exceeded(self):
        """Test trade with excessive notional value."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        trade_params = {
            "size": 10.0,  # Large size
            "leverage": 3.0,
            "entry_price": 50000.0,
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        # Notional = 10.0 * 50000 * 3 = 1,500,000
        # Max = 10000 * 3 = 30,000
        assert result.valid is False
        assert any("notional" in v.lower() for v in result.violations)

    def test_validate_trade_multiple_violations(self):
        """Test trade with multiple violations."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        trade_params = {
            "size": 10.0,
            "leverage": 5.0,  # Violation 1
            "entry_price": 50000.0,
            "stop_loss": 40000.0,  # Violation 2
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        assert result.valid is False
        assert len(result.violations) >= 2

    def test_validate_trade_params_stored(self):
        """Test trade params are stored in result."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        trade_params = {
            "size": 0.01,
            "leverage": 2.0,
            "entry_price": 50000.0,
            "symbol": "BTCUSDT",
        }
        result = enforcer.validate_trade(trade_params)
        assert result.trade_params["size"] == 0.01
        assert result.trade_params["leverage"] == 2.0

    def test_max_per_trade_risk_constant(self):
        """Test max per-trade risk constant is 1%."""
        assert RiskEnforcer.MAX_PER_TRADE_RISK_PCT == 1.0


class TestPortfolioValueUpdate:
    """Test portfolio value updates."""

    def test_update_portfolio_value(self):
        """Test updating portfolio value."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        enforcer.portfolio_value = 15000.0
        assert enforcer.portfolio_value == 15000.0

    def test_update_portfolio_value_invalid(self):
        """Test invalid portfolio value update."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        with pytest.raises(ValueError, match="Portfolio value must be positive"):
            enforcer.portfolio_value = 0


class TestTradeResultRecording:
    """Test trade result recording."""

    def test_record_trade_profit(self):
        """Test recording profitable trade."""
        enforcer = RiskEnforcer()
        enforcer.record_trade_result(100.0)
        assert enforcer._trade_count_today == 1
        assert enforcer._daily_loss == 0.0  # Profits don't add to loss

    def test_record_trade_loss(self):
        """Test recording losing trade."""
        enforcer = RiskEnforcer()
        enforcer.record_trade_result(-100.0)
        assert enforcer._trade_count_today == 1
        assert enforcer._daily_loss == -100.0

    def test_record_multiple_trades(self):
        """Test recording multiple trades."""
        enforcer = RiskEnforcer()
        enforcer.record_trade_result(100.0)
        enforcer.record_trade_result(-50.0)
        enforcer.record_trade_result(-30.0)
        assert enforcer._trade_count_today == 3
        assert enforcer._daily_loss == -80.0


class TestRiskSummary:
    """Test risk summary generation."""

    def test_get_risk_summary(self):
        """Test getting risk summary."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)
        enforcer.record_trade_result(-100.0)
        enforcer.validate_trade({"size": 0.01, "leverage": 2.0})

        summary = enforcer.get_risk_summary()
        assert summary["portfolio_value"] == 10000.0
        assert summary["max_per_trade_risk_pct"] == 1.0
        assert summary["max_leverage"] == 3.0
        assert summary["daily_loss"] == -100.0
        assert summary["trade_count_today"] == 1
        assert summary["validation_count"] == 1


class TestGridStrategyValidation:
    """Test grid strategy validation."""

    def test_validate_grid_strategy_valid(self):
        """Test valid grid strategy."""
        enforcer = RiskEnforcer()
        result = enforcer.validate_grid_strategy(
            grid_levels=3,
            total_allocation_pct=50.0,
            per_level_risk_pct=0.5,  # 3 * 0.5 = 1.5% total (< 2%)
        )
        assert result.valid is True

    def test_validate_grid_strategy_excessive_allocation(self):
        """Test grid strategy with excessive allocation."""
        enforcer = RiskEnforcer()
        result = enforcer.validate_grid_strategy(
            grid_levels=5,
            total_allocation_pct=150.0,  # Exceeds 100%
            per_level_risk_pct=0.5,
        )
        assert result.valid is False
        assert any("allocation" in v.lower() for v in result.violations)

    def test_validate_grid_strategy_excessive_grid_risk(self):
        """Test grid strategy with excessive total risk."""
        enforcer = RiskEnforcer()
        result = enforcer.validate_grid_strategy(
            grid_levels=10,
            total_allocation_pct=50.0,
            per_level_risk_pct=0.5,  # 10 * 0.5 = 5% total
        )
        # 5% exceeds MAX_PER_GRID_WORST_CASE_PCT (2%)
        assert result.valid is False
        assert any("grid risk" in v.lower() for v in result.violations)

    def test_validate_grid_strategy_excessive_per_level_risk(self):
        """Test grid strategy with excessive per-level risk."""
        enforcer = RiskEnforcer()
        result = enforcer.validate_grid_strategy(
            grid_levels=3,
            total_allocation_pct=50.0,
            per_level_risk_pct=2.0,  # Exceeds 1%
        )
        assert result.valid is False
        assert any(
            "per-level" in v.lower() or "risk" in v.lower() for v in result.violations
        )

    def test_max_per_grid_worst_case_constant(self):
        """Test max per-grid worst case constant is 2%."""
        assert RiskEnforcer.MAX_PER_GRID_WORST_CASE_PCT == 2.0


class TestDailyReset:
    """Test daily counter reset."""

    def test_reset_daily_if_needed(self):
        """Test daily reset when day changes."""
        enforcer = RiskEnforcer()
        enforcer._daily_loss = -500.0
        enforcer._trade_count_today = 10
        enforcer._daily_loss_reset_time = datetime.now(UTC) - timedelta(days=2)

        enforcer._reset_daily_if_needed()
        assert enforcer._daily_loss == 0.0
        assert enforcer._trade_count_today == 0

    def test_no_reset_same_day(self):
        """Test no reset on same day."""
        enforcer = RiskEnforcer()
        enforcer._daily_loss = -500.0
        enforcer._trade_count_today = 10
        # Reset time is already today from initialization

        enforcer._reset_daily_if_needed()
        assert enforcer._daily_loss == -500.0
        assert enforcer._trade_count_today == 10
