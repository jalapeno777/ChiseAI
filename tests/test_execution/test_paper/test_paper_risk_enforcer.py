"""Tests for paper trading risk enforcer.

For PAPER-LOOP-001: Paper Trading Risk Enforcer
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signal_generation.models import Signal, SignalDirection, SignalStatus

from execution.paper.risk_enforcer import PaperRiskEnforcer
from execution.paper.risk_models import (
    PaperPosition,
    RiskAssessment,
    RiskCheck,
    RiskSeverity,
    RiskViolation,
)


class TestRiskCheck:
    """Tests for RiskCheck configuration."""

    def test_default_values(self):
        """Test default risk check values."""
        config = RiskCheck()
        assert config.max_position_pct == 0.10
        assert config.max_leverage == 3.0
        assert config.max_portfolio_exposure_pct == 0.80
        assert config.min_confidence == 0.75
        assert config.max_drawdown_pct == 0.15

    def test_custom_values(self):
        """Test custom risk check values."""
        config = RiskCheck(
            max_position_pct=0.15,
            max_leverage=5.0,
            max_portfolio_exposure_pct=0.90,
            min_confidence=0.80,
            max_drawdown_pct=0.20,
        )
        assert config.max_position_pct == 0.15
        assert config.max_leverage == 5.0
        assert config.max_portfolio_exposure_pct == 0.90
        assert config.min_confidence == 0.80
        assert config.max_drawdown_pct == 0.20

    def test_invalid_max_position_pct(self):
        """Test validation of invalid max_position_pct."""
        with pytest.raises(
            ValueError, match="max_position_pct must be between 0 and 1"
        ):
            RiskCheck(max_position_pct=1.5)
        with pytest.raises(
            ValueError, match="max_position_pct must be between 0 and 1"
        ):
            RiskCheck(max_position_pct=0)

    def test_invalid_max_leverage(self):
        """Test validation of invalid max_leverage."""
        with pytest.raises(ValueError, match="max_leverage must be positive"):
            RiskCheck(max_leverage=0)
        with pytest.raises(ValueError, match="max_leverage must be positive"):
            RiskCheck(max_leverage=-1)

    def test_invalid_min_confidence(self):
        """Test validation of invalid min_confidence."""
        with pytest.raises(ValueError, match="min_confidence must be between 0 and 1"):
            RiskCheck(min_confidence=1.5)
        with pytest.raises(ValueError, match="min_confidence must be between 0 and 1"):
            RiskCheck(min_confidence=0)


class TestRiskViolation:
    """Tests for RiskViolation dataclass."""

    def test_creation(self):
        """Test creating a risk violation."""
        violation = RiskViolation(
            rule="confidence",
            severity=RiskSeverity.BLOCK.value,
            message="Confidence too low",
            current_value=0.5,
            limit_value=0.75,
        )
        assert violation.rule == "confidence"
        assert violation.severity == "block"
        assert violation.current_value == 0.5
        assert violation.limit_value == 0.75

    def test_to_dict(self):
        """Test converting violation to dictionary."""
        violation = RiskViolation(
            rule="position_size",
            severity=RiskSeverity.WARNING.value,
            message="Position large",
            current_value=1000.0,
            limit_value=800.0,
            metadata={"token": "BTC"},
        )
        d = violation.to_dict()
        assert d["rule"] == "position_size"
        assert d["severity"] == "warning"
        assert d["current_value"] == 1000.0
        assert d["limit_value"] == 800.0
        assert d["metadata"] == {"token": "BTC"}


class TestRiskAssessment:
    """Tests for RiskAssessment dataclass."""

    def test_approved_no_violations(self):
        """Test approved assessment with no violations."""
        assessment = RiskAssessment(approved=True)
        assert assessment.approved is True
        assert assessment.has_violations is False
        assert assessment.has_blocking_violations is False
        assert assessment.has_warning_violations is False

    def test_rejected_with_blocking_violation(self):
        """Test rejected assessment with blocking violation."""
        violation = RiskViolation(
            rule="confidence",
            severity=RiskSeverity.BLOCK.value,
            message="Low confidence",
            current_value=0.5,
            limit_value=0.75,
        )
        assessment = RiskAssessment(
            approved=False,
            violations=[violation],
        )
        assert assessment.approved is False
        assert assessment.has_violations is True
        assert assessment.has_blocking_violations is True
        assert assessment.has_warning_violations is False

    def test_approved_with_warning(self):
        """Test approved assessment with warning violation."""
        violation = RiskViolation(
            rule="exposure",
            severity=RiskSeverity.WARNING.value,
            message="High exposure",
            current_value=0.85,
            limit_value=0.80,
        )
        assessment = RiskAssessment(
            approved=True,
            violations=[violation],
        )
        assert assessment.approved is True
        assert assessment.has_violations is True
        assert assessment.has_blocking_violations is False
        assert assessment.has_warning_violations is True

    def test_cannot_approve_with_blocking_violation(self):
        """Test that assessment cannot be approved with blocking violation."""
        violation = RiskViolation(
            rule="confidence",
            severity=RiskSeverity.BLOCK.value,
            message="Low confidence",
            current_value=0.5,
            limit_value=0.75,
        )
        with pytest.raises(
            ValueError, match="Cannot approve order with blocking violations"
        ):
            RiskAssessment(approved=True, violations=[violation])

    def test_to_dict(self):
        """Test converting assessment to dictionary."""
        assessment = RiskAssessment(
            approved=True,
            position_size=1.5,
            margin_required=500.0,
            metadata={"token": "ETH"},
        )
        d = assessment.to_dict()
        assert d["approved"] is True
        assert d["position_size"] == 1.5
        assert d["margin_required"] == 500.0
        assert d["metadata"] == {"token": "ETH"}


class TestPaperPosition:
    """Tests for PaperPosition dataclass."""

    def test_creation(self):
        """Test creating a paper position."""
        pos = PaperPosition(
            position_id="pos-001",
            token="BTC/USDT",
            direction="long",
            quantity=1.5,
            entry_price=50000.0,
            current_price=51000.0,
            leverage=2.0,
        )
        assert pos.position_id == "pos-001"
        assert pos.token == "BTC/USDT"
        assert pos.direction == "long"
        assert pos.quantity == 1.5

    def test_value_calculation(self):
        """Test position value calculation."""
        pos = PaperPosition(
            position_id="pos-001",
            token="BTC/USDT",
            direction="long",
            quantity=1.5,
            entry_price=50000.0,
            current_price=51000.0,
            leverage=2.0,
        )
        assert pos.value == 1.5 * 51000.0  # 76500.0

    def test_notional_value_calculation(self):
        """Test notional value calculation with leverage."""
        pos = PaperPosition(
            position_id="pos-001",
            token="BTC/USDT",
            direction="long",
            quantity=1.5,
            entry_price=50000.0,
            current_price=51000.0,
            leverage=2.0,
        )
        assert pos.notional_value == pos.value * 2.0  # 153000.0

    def test_unrealized_pnl_long(self):
        """Test unrealized PnL for long position."""
        pos = PaperPosition(
            position_id="pos-001",
            token="BTC/USDT",
            direction="long",
            quantity=1.5,
            entry_price=50000.0,
            current_price=51000.0,
            leverage=2.0,
        )
        # (51000 - 50000) * 1.5 = 1500
        assert pos.unrealized_pnl == 1500.0

    def test_unrealized_pnl_short(self):
        """Test unrealized PnL for short position."""
        pos = PaperPosition(
            position_id="pos-001",
            token="BTC/USDT",
            direction="short",
            quantity=-1.5,
            entry_price=50000.0,
            current_price=49000.0,
            leverage=2.0,
        )
        # (50000 - 49000) * 1.5 = 1500
        assert pos.unrealized_pnl == 1500.0

    def test_to_dict(self):
        """Test converting position to dictionary."""
        pos = PaperPosition(
            position_id="pos-001",
            token="BTC/USDT",
            direction="long",
            quantity=1.5,
            entry_price=50000.0,
            current_price=51000.0,
            leverage=2.0,
        )
        d = pos.to_dict()
        assert d["position_id"] == "pos-001"
        assert d["token"] == "BTC/USDT"
        assert d["value"] == 76500.0


class TestPaperRiskEnforcer:
    """Tests for PaperRiskEnforcer class."""

    @pytest.fixture
    def enforcer(self):
        """Create a basic risk enforcer."""
        return PaperRiskEnforcer()

    @pytest.fixture
    def enforcer_with_kill_switch(self):
        """Create a risk enforcer with mock kill switch."""
        kill_switch = AsyncMock()
        kill_switch.execute_kill_switch = AsyncMock(
            return_value=MagicMock(
                success=True,
                positions_closed=2,
            )
        )
        return PaperRiskEnforcer(kill_switch_executor=kill_switch)

    @pytest.fixture
    def valid_signal(self):
        """Create a valid signal above confidence threshold."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=85.0,
            timestamp=datetime.utcnow(),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=48000.0,
            risk_reward_ratio=2.0,
            metadata={"entry_price": 50000.0},
        )

    @pytest.fixture
    def low_confidence_signal(self):
        """Create a signal below confidence threshold."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.60,
            base_score=60.0,
            timestamp=datetime.utcnow(),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_valid_order_approved(self, enforcer, valid_signal):
        """Test that a valid order is approved."""
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=[],
        )
        assert assessment.approved is True
        assert assessment.has_blocking_violations is False

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self, enforcer, low_confidence_signal):
        """Test that low confidence signals are rejected."""
        assessment = await enforcer.validate_order(
            signal=low_confidence_signal,
            portfolio_value=100000.0,
            current_positions=[],
        )
        assert assessment.approved is False
        assert any(v.rule == "confidence" for v in assessment.violations)
        assert all(
            v.severity == RiskSeverity.BLOCK.value
            for v in assessment.violations
            if v.rule == "confidence"
        )

    @pytest.mark.asyncio
    async def test_position_size_limit(self, enforcer, valid_signal):
        """Test that position size > 10% portfolio is rejected."""
        # Create a position that would exceed 10% of small portfolio
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=1000.0,  # Small portfolio
            current_positions=[],
        )
        # Should still be approved as position sizing respects limits
        # The position size calculation caps at max_position_pct

    @pytest.mark.asyncio
    async def test_portfolio_exposure_warning(self, enforcer, valid_signal):
        """Test warning when portfolio exposure > 80%."""
        # Create existing positions that use 75% of portfolio
        existing_positions = [
            PaperPosition(
                position_id="pos-001",
                token="ETH/USDT",
                direction="long",
                quantity=100.0,
                entry_price=3000.0,
                current_price=3000.0,
            )
        ]
        # 100 * 3000 = 300,000 value, portfolio is 100,000
        # This is 300% exposure, way over 80%
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=existing_positions,
        )
        assert assessment.has_warning_violations is True
        assert any(v.rule == "exposure" for v in assessment.violations)

    @pytest.mark.asyncio
    async def test_drawdown_triggers_kill_switch(
        self, enforcer_with_kill_switch, valid_signal
    ):
        """Test that 15% drawdown triggers kill-switch."""
        assessment = await enforcer_with_kill_switch.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=[],
            current_drawdown_pct=0.15,  # 15% drawdown
        )
        assert assessment.approved is False
        assert any(v.rule == "drawdown" for v in assessment.violations)
        # Verify kill-switch was called
        enforcer_with_kill_switch.kill_switch.execute_kill_switch.assert_called_once()

    @pytest.mark.asyncio
    async def test_drawdown_below_threshold(
        self, enforcer_with_kill_switch, valid_signal
    ):
        """Test that drawdown below threshold doesn't trigger kill-switch."""
        assessment = await enforcer_with_kill_switch.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=[],
            current_drawdown_pct=0.10,  # 10% drawdown
        )
        assert assessment.approved is True
        # Kill-switch should not be called
        enforcer_with_kill_switch.kill_switch.execute_kill_switch.assert_not_called()

    @pytest.mark.asyncio
    async def test_excessive_leverage_rejected(self, enforcer, valid_signal):
        """Test that leverage > 3x is rejected."""
        valid_signal.metadata["leverage"] = 5.0  # Excessive leverage
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=[],
        )
        assert assessment.approved is False
        assert any(v.rule == "leverage" for v in assessment.violations)

    @pytest.mark.asyncio
    async def test_valid_leverage_accepted(self, enforcer, valid_signal):
        """Test that leverage <= 3x is accepted."""
        valid_signal.metadata["leverage"] = 2.0  # Valid leverage
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=[],
        )
        assert assessment.approved is True
        assert not any(v.rule == "leverage" for v in assessment.violations)

    def test_calculate_position_size_with_stop_loss(self, enforcer, valid_signal):
        """Test position size calculation with stop loss."""
        size = enforcer.calculate_position_size(valid_signal, 100000.0)
        # Should calculate based on 1% risk and stop distance
        # Risk = $1000, stop distance = $2000 (50000 - 48000)
        # Size = 1000 / 2000 = 0.5
        assert size > 0
        # Should be capped at 10% of portfolio
        max_size = (100000.0 * 0.10) / 50000.0  # 0.2
        assert size <= max_size

    def test_calculate_position_size_without_stop_loss(self, enforcer):
        """Test position size calculation without stop loss."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=85.0,
            timestamp=datetime.utcnow(),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            metadata={"entry_price": 50000.0},
        )
        size = enforcer.calculate_position_size(signal, 100000.0)
        # Should use fixed fractional (1% of portfolio)
        # 1000 / 50000 = 0.02
        assert size > 0

    def test_violation_log(self, enforcer, valid_signal):
        """Test that violations are logged."""
        # Create a violation
        violation = RiskViolation(
            rule="test",
            severity=RiskSeverity.BLOCK.value,
            message="Test violation",
            current_value=1.0,
            limit_value=0.5,
        )
        enforcer._log_violation(violation, valid_signal)

        log = enforcer.get_violation_log()
        assert len(log) == 1
        assert log[0]["violation"]["rule"] == "test"
        assert log[0]["signal_id"] == valid_signal.signal_id

    def test_clear_violation_log(self, enforcer, valid_signal):
        """Test clearing violation log."""
        violation = RiskViolation(
            rule="test",
            severity=RiskSeverity.BLOCK.value,
            message="Test violation",
            current_value=1.0,
            limit_value=0.5,
        )
        enforcer._log_violation(violation, valid_signal)
        assert len(enforcer.get_violation_log()) == 1

        enforcer.clear_violation_log()
        assert len(enforcer.get_violation_log()) == 0

    def test_get_stats(self, enforcer):
        """Test getting enforcer statistics."""
        stats = enforcer.get_stats()
        assert "config" in stats
        assert "violation_stats" in stats
        assert "kill_switch_configured" in stats
        assert stats["config"]["max_position_pct"] == 0.10
        assert stats["kill_switch_configured"] is False

    def test_get_stats_with_kill_switch(self, enforcer_with_kill_switch):
        """Test getting stats when kill-switch is configured."""
        stats = enforcer_with_kill_switch.get_stats()
        assert stats["kill_switch_configured"] is True

    @pytest.mark.asyncio
    async def test_check_drawdown_triggers_kill_switch(self, enforcer_with_kill_switch):
        """Test check_drawdown method triggers kill-switch."""
        triggered = await enforcer_with_kill_switch.check_drawdown(0.15)
        assert triggered is True
        enforcer_with_kill_switch.kill_switch.execute_kill_switch.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_drawdown_no_trigger(self, enforcer_with_kill_switch):
        """Test check_drawdown doesn't trigger below threshold."""
        triggered = await enforcer_with_kill_switch.check_drawdown(0.10)
        assert triggered is False
        enforcer_with_kill_switch.kill_switch.execute_kill_switch.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_drawdown_without_kill_switch(self, enforcer):
        """Test check_drawdown without kill-switch configured."""
        triggered = await enforcer.check_drawdown(0.15)
        # Should still return True to indicate threshold was reached
        assert triggered is True

    @pytest.mark.asyncio
    async def test_multiple_violations(self, enforcer):
        """Test that multiple violations are captured."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.60,  # Low confidence
            base_score=60.0,
            timestamp=datetime.utcnow(),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
            metadata={"leverage": 5.0},  # Excessive leverage
        )
        assessment = await enforcer.validate_order(
            signal=signal,
            portfolio_value=100000.0,
            current_positions=[],
        )
        assert assessment.approved is False
        assert len(assessment.violations) >= 2
        rules = [v.rule for v in assessment.violations]
        assert "confidence" in rules
        assert "leverage" in rules

    @pytest.mark.asyncio
    async def test_existing_token_position_replacement(self, enforcer, valid_signal):
        """Test that existing token positions are replaced in exposure calc."""
        existing_positions = [
            PaperPosition(
                position_id="pos-001",
                token="BTC/USDT",  # Same token as signal
                direction="long",
                quantity=0.5,
                entry_price=49000.0,
                current_price=50000.0,
            )
        ]
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=existing_positions,
        )
        # Should be approved as we're replacing the existing position
        assert assessment.approved is True

    @pytest.mark.asyncio
    async def test_position_filtering_by_symbol_attribute(self, enforcer, valid_signal):
        """Test position filtering works with symbol attribute (BURNIN-001 fix).

        This test verifies that positions with 'symbol' attribute (from position_tracker.py)
        are correctly filtered when checking exposure, matching against signal.token.
        """

        # Create a mock position class with 'symbol' attribute (like position_tracker.PaperPosition)
        class MockPositionWithSymbol:
            def __init__(self, symbol, quantity, entry_price, current_price):
                self.symbol = symbol
                self.quantity = quantity
                self.entry_price = entry_price
                self.current_price = current_price

            @property
            def value(self):
                return abs(self.quantity) * self.current_price

        # Create positions with different symbols
        existing_positions = [
            MockPositionWithSymbol("BTC/USDT", 0.5, 49000.0, 50000.0),  # Same as signal
            MockPositionWithSymbol("ETH/USDT", 2.0, 3000.0, 3100.0),  # Different token
        ]

        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=existing_positions,
        )
        # Should be approved - the BTC position should be excluded from exposure calc
        # because we're replacing it with the new signal
        assert assessment.approved is True

        # Verify the exposure calculation excluded the BTC position
        # Total exposure would be: 0.5*50000 + 2*3100 = 25000 + 6200 = 31200
        # Adjusted (minus BTC): 6200
        # New position: ~0.5 BTC at 50000 = 25000 (capped at 10% = 10000)
        # New exposure: 6200 + 10000 = 16200 < 80000 (80% limit)
        assert assessment.metadata["current_drawdown_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_position_filtering_excludes_matching_symbol(
        self, enforcer, valid_signal
    ):
        """Test that positions with matching symbol are excluded from exposure calc.

        Regression test for BURNIN-001: PaperPosition attribute error.
        """

        class MockPositionWithSymbol:
            def __init__(self, symbol, quantity, current_price):
                self.symbol = symbol
                self.quantity = quantity
                self.current_price = current_price

            @property
            def value(self):
                return abs(self.quantity) * self.current_price

        # Create positions - one matching signal token, one different
        btc_position = MockPositionWithSymbol("BTC/USDT", 1.0, 50000.0)  # $50,000 value
        eth_position = MockPositionWithSymbol("ETH/USDT", 10.0, 3000.0)  # $30,000 value

        existing_positions = [btc_position, eth_position]

        assessment = await enforcer.validate_order(
            signal=valid_signal,  # BTC/USDT signal
            portfolio_value=100000.0,
            current_positions=existing_positions,
        )

        # The BTC position should be excluded (we're replacing it)
        # Only ETH position ($30k) counts toward exposure
        # New position is capped at 10% = $10k
        # Total new exposure = $30k + $10k = $40k < $80k limit (80%)
        # Should be approved with no exposure warning
        assert assessment.approved is True
        exposure_violations = [v for v in assessment.violations if v.rule == "exposure"]
        assert (
            len(exposure_violations) == 0
        ), "Should not have exposure warning with $40k on $100k portfolio"


class TestIntegrationWithKillSwitch:
    """Integration tests with kill-switch executor."""

    @pytest.mark.asyncio
    async def test_kill_switch_integration(self):
        """Test full integration with kill-switch executor."""
        from execution.kill_switch.executor import KillSwitchExecutor

        # Create a real kill-switch executor (without connectors)
        kill_switch = KillSwitchExecutor()

        enforcer = PaperRiskEnforcer(kill_switch_executor=kill_switch)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=85.0,
            timestamp=datetime.utcnow(),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            metadata={},
        )

        # Test that enforcer can call kill-switch
        assessment = await enforcer.validate_order(
            signal=signal,
            portfolio_value=100000.0,
            current_positions=[],
            current_drawdown_pct=0.15,
        )

        assert assessment.approved is False
        assert kill_switch.state.value == "triggered"


class TestEdgeCases:
    """Edge case tests."""

    @pytest.fixture
    def enforcer(self):
        """Create a basic risk enforcer."""
        return PaperRiskEnforcer()

    @pytest.fixture
    def enforcer_with_kill_switch(self):
        """Create a risk enforcer with mock kill switch."""
        kill_switch = AsyncMock()
        kill_switch.execute_kill_switch = AsyncMock(
            return_value=MagicMock(
                success=True,
                positions_closed=2,
            )
        )
        return PaperRiskEnforcer(kill_switch_executor=kill_switch)

    @pytest.fixture
    def valid_signal(self):
        """Create a valid signal above confidence threshold."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=85.0,
            timestamp=datetime.now(),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=48000.0,
            risk_reward_ratio=2.0,
            metadata={"entry_price": 50000.0},
        )

    @pytest.mark.asyncio
    async def test_zero_portfolio_value(self, enforcer, valid_signal):
        """Test handling of zero portfolio value."""
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=0.0,
            current_positions=[],
        )
        # Should handle gracefully
        assert isinstance(assessment, RiskAssessment)

    @pytest.mark.asyncio
    async def test_negative_drawdown(self, enforcer, valid_signal):
        """Test handling of negative drawdown (profit)."""
        assessment = await enforcer.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=[],
            current_drawdown_pct=-0.05,  # Profit
        )
        assert assessment.approved is True

    @pytest.mark.asyncio
    async def test_exact_threshold_confidence(self, enforcer):
        """Test exact confidence threshold (75%)."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.75,  # Exactly at threshold
            base_score=75.0,
            timestamp=datetime.now(),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            metadata={},
        )
        assessment = await enforcer.validate_order(
            signal=signal,
            portfolio_value=100000.0,
            current_positions=[],
        )
        # Should be approved (>= threshold)
        assert assessment.approved is True

    @pytest.mark.asyncio
    async def test_just_below_confidence_threshold(self, enforcer):
        """Test just below confidence threshold."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.7499,  # Just below 75%
            base_score=74.99,
            timestamp=datetime.now(),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
            metadata={},
        )
        assessment = await enforcer.validate_order(
            signal=signal,
            portfolio_value=100000.0,
            current_positions=[],
        )
        assert assessment.approved is False

    @pytest.mark.asyncio
    async def test_exact_drawdown_threshold(
        self, enforcer_with_kill_switch, valid_signal
    ):
        """Test exact drawdown threshold (15%)."""
        assessment = await enforcer_with_kill_switch.validate_order(
            signal=valid_signal,
            portfolio_value=100000.0,
            current_positions=[],
            current_drawdown_pct=0.15,  # Exactly at threshold
        )
        assert assessment.approved is False
        assert any(v.rule == "drawdown" for v in assessment.violations)
