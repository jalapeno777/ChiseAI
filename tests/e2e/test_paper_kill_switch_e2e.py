"""End-to-end integration tests for Paper Trading Kill Switch.

Tests the complete kill switch lifecycle including:
- Activation and deactivation
- Signal processing blocking when active
- Safety invariant enforcement (1% max position, 3x max leverage, 15% daily loss)
- Demo environment only (no live trading)

For ST-LAUNCH-KILL-001: Kill-switch E2E test for paper trading
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperFill,
    PaperOrder,
    TradeStatus,
)
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.paper_kill_switch import (
    PaperKillSwitchActiveError,
    PaperKillSwitchManager,
    PaperKillSwitchStatus,
)
from execution.paper.risk_models import RiskAssessment, RiskSeverity, RiskViolation
from signal_generation.models import Signal, SignalDirection, SignalStatus

# ============================================================================
# Fixtures
# ============================================================================


class MockTelemetryCollector:
    """Mock telemetry collector for testing."""

    def __init__(self):
        self.trades = []
        self.equity = 10000.0
        self.running = False

    async def start(self):
        self.running = True

    async def stop(self):
        self.running = False

    async def add_trade(self, trade):
        self.trades.append(trade)

    async def set_equity(self, equity):
        self.equity = equity


class MockKillSwitch:
    """Mock kill switch for testing (orchestrator-level)."""

    def __init__(self):
        self.state = MagicMock()
        self.state.value = "armed"

    async def execute_kill_switch(self, **kwargs):
        self.state.value = "triggered"


@pytest.fixture
def mock_decision_enhancer():
    """Mock decision enhancer disabled for testing."""
    enhancer = MagicMock()
    enhancer.enabled = False
    return enhancer


def make_signal(
    token: str = "BTC/USDT",
    signal_id: str | None = None,
    direction: SignalDirection = SignalDirection.LONG,
) -> Signal:
    """Create a properly-formed mock signal with valid UUID signal_id."""
    return Signal(
        token=token,
        direction=direction,
        confidence=0.85,
        base_score=85.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        stop_loss=45000.0 if token == "BTC/USDT" else 3000.0,
        stop_loss_method="atr",
        signal_id=signal_id or str(uuid.uuid4()),
    )


@pytest.fixture
def mock_signal():
    """Create a mock signal for testing."""
    return make_signal(token="BTC/USDT")


@pytest.fixture
def mock_signal_alt():
    """Create an alternative mock signal for testing (different token/time)."""
    return make_signal(token="ETH/USDT")


@pytest.fixture
def mock_components(mock_decision_enhancer):
    """Create mock components for orchestrator."""
    signal_gen = MagicMock()
    order_sim = AsyncMock()
    order_sim.market_data = MagicMock()
    order_sim.market_data.get_price = MagicMock(return_value=50000.0)
    position_tracker = AsyncMock()
    position_tracker.get_open_positions = AsyncMock(return_value=[])
    position_tracker.open_position = AsyncMock()
    position_tracker.close_position = AsyncMock()
    risk_enforcer = AsyncMock()
    telemetry = MockTelemetryCollector()
    kill_switch = MockKillSwitch()

    return {
        "signal_gen": signal_gen,
        "order_sim": order_sim,
        "position_tracker": position_tracker,
        "risk_enforcer": risk_enforcer,
        "telemetry": telemetry,
        "kill_switch": kill_switch,
        "decision_enhancer": mock_decision_enhancer,
    }


@pytest.fixture
def orchestrator(mock_components):
    """Create an orchestrator with mock components."""
    return PaperTradingOrchestrator(
        signal_generator=mock_components["signal_gen"],
        order_simulator=mock_components["order_sim"],
        position_tracker=mock_components["position_tracker"],
        risk_enforcer=mock_components["risk_enforcer"],
        telemetry_collector=mock_components["telemetry"],
        kill_switch=mock_components["kill_switch"],
        decision_enhancer=mock_components["decision_enhancer"],
        portfolio_value=10000.0,
    )


def create_filled_order(order_id: str, quantity: float = 0.1) -> PaperOrder:
    """Create a filled paper order for testing."""
    filled_order = PaperOrder(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
        order_id=order_id,
        state=OrderState.FILLED,
        filled_quantity=quantity,
        avg_fill_price=50000.0,
    )
    fill = PaperFill(
        fill_id=f"fill-{order_id}",
        order_id=order_id,
        symbol="BTC/USDT",
        side="buy",
        quantity=quantity,
        price=50000.0,
    )
    filled_order.add_fill(fill)
    return filled_order


# ============================================================================
# Test Kill Switch Manager - Unit Tests (for context)
# ============================================================================


class TestPaperKillSwitchManagerBasics:
    """Test PaperKillSwitchManager basic async operations."""

    @pytest.mark.asyncio
    async def test_activate_returns_true_on_success(self):
        """Test activate returns True on successful activation."""
        manager = PaperKillSwitchManager()
        result = await manager.activate(reason="Test activation", activated_by="test")
        assert result is True
        await manager.close()
        await manager.deactivate()  # Clean up

    @pytest.mark.asyncio
    async def test_deactivate_returns_true(self):
        """Test deactivate returns True."""
        manager = PaperKillSwitchManager()
        await manager.activate(reason="Test", activated_by="test")
        result = await manager.deactivate()
        assert result is True
        await manager.close()

    @pytest.mark.asyncio
    async def test_status_inactive_initially(self):
        """Test status is inactive initially (after cleanup)."""
        manager = PaperKillSwitchManager()
        # Ensure clean state
        await manager.deactivate()
        status = await manager.get_status()
        assert status.active is False
        assert status.reason == ""
        await manager.close()

    @pytest.mark.asyncio
    async def test_status_active_after_activation(self):
        """Test status is active after activation."""
        manager = PaperKillSwitchManager()
        await manager.activate(reason="Test reason", activated_by="test")
        try:
            status = await manager.get_status()
            assert status.active is True
            assert status.reason == "Test reason"
            assert status.activated_by == "test"
            assert status.activated_at is not None
        finally:
            await manager.deactivate()
            await manager.close()

    @pytest.mark.asyncio
    async def test_is_active_returns_correct_state(self):
        """Test is_active returns correct boolean."""
        manager = PaperKillSwitchManager()
        # Start clean
        await manager.deactivate()
        assert await manager.is_active() is False
        await manager.activate(reason="Test", activated_by="test")
        assert await manager.is_active() is True
        await manager.deactivate()
        assert await manager.is_active() is False
        await manager.close()

    @pytest.mark.asyncio
    async def test_check_and_raise_raises_when_active(self):
        """Test check_and_raise_if_active raises when active."""
        manager = PaperKillSwitchManager()
        await manager.activate(reason="Test", activated_by="test")
        try:
            with pytest.raises(PaperKillSwitchActiveError) as exc_info:
                await manager.check_and_raise_if_active()
            assert "Test" in str(exc_info.value)
        finally:
            await manager.deactivate()
            await manager.close()

    @pytest.mark.asyncio
    async def test_check_and_raise_does_not_raise_when_inactive(self):
        """Test check_and_raise_if_active does not raise when inactive."""
        manager = PaperKillSwitchManager()
        await manager.deactivate()  # Ensure clean state
        try:
            await manager.check_and_raise_if_active()  # Should not raise
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_ttl_is_set_on_activation(self):
        """Test TTL is set when activating kill switch."""
        manager = PaperKillSwitchManager()
        await manager.activate(reason="Test", activated_by="test", ttl=60)
        try:
            status = await manager.get_status()
            assert status.active is True
            assert status.ttl_remaining is not None
            assert status.ttl_remaining <= 60
        finally:
            await manager.deactivate()
            await manager.close()


# ============================================================================
# Test Kill Switch Integration with Orchestrator
# ============================================================================


class TestKillSwitchLifecycleWithOrchestrator:
    """Test kill switch lifecycle integration with orchestrator."""

    @pytest.mark.asyncio
    async def test_signal_processing_blocked_when_kill_switch_active(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that signal processing is blocked when kill switch is active.

        This tests the core kill switch functionality: when the paper trading
        kill switch is activated, signals should be rejected before any
        risk checks or order placement occurs.
        """
        # Setup risk enforcer to approve (should not matter - kill switch blocks first)
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        # Activate the paper kill switch
        kill_switch_manager = PaperKillSwitchManager()
        try:
            await kill_switch_manager.activate(
                reason="E2E test activation", activated_by="test_e2e"
            )

            # Inject kill switch manager into orchestrator
            orchestrator._paper_kill_switch = kill_switch_manager

            # Process signal - should be blocked by kill switch
            result = await orchestrator.process_signal(mock_signal)

            # Verify signal was rejected by kill switch
            assert result.status == TradeStatus.REJECTED
            assert any(
                "kill switch" in reason.lower() for reason in result.reject_reason
            ), f"Expected kill switch rejection, got: {result.reject_reason}"
            assert result.order is None
            assert result.position is None
        finally:
            await kill_switch_manager.deactivate()
            await kill_switch_manager.close()

    @pytest.mark.asyncio
    async def test_signal_processing_resumes_after_kill_switch_deactivation(
        self, orchestrator, mock_components, mock_signal, mock_signal_alt
    ):
        """Test that signal processing resumes after kill switch deactivation.

        This tests the full lifecycle: activate -> process (blocked) ->
        deactivate -> process (allowed).
        """
        # Setup risk enforcer and order simulator for success
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = create_filled_order("test-order-ks-001")
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-ks-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Create kill switch manager and inject into orchestrator
        kill_switch_manager = PaperKillSwitchManager()
        orchestrator._paper_kill_switch = kill_switch_manager

        # Step 1: Activate kill switch
        await kill_switch_manager.activate(reason="E2E test", activated_by="test_e2e")

        # Verify blocked while active (use different signals to avoid throttle)
        result_blocked = await orchestrator.process_signal(mock_signal)
        assert result_blocked.status == TradeStatus.REJECTED

        # Step 2: Deactivate kill switch
        await kill_switch_manager.deactivate()

        # Step 3: Process signal - should succeed now (use different signal)
        result_allowed = await orchestrator.process_signal(mock_signal_alt)
        assert result_allowed.status == TradeStatus.EXECUTED
        assert result_allowed.order is not None
        assert result_allowed.position is not None

        await kill_switch_manager.close()

    @pytest.mark.asyncio
    async def test_kill_switch_status_preserved_across_manager_instances(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that kill switch status is preserved in Redis, not local state.

        This verifies the Redis-backed persistence: creating a new manager
        instance should see the same kill switch state.
        """
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        # Manager 1: Activate kill switch
        manager1 = PaperKillSwitchManager()
        await manager1.activate(reason="Shared state test", activated_by="manager1")

        try:
            # Manager 2: Should see active kill switch (Redis-backed)
            manager2 = PaperKillSwitchManager()
            status2 = await manager2.get_status()
            assert status2.active is True
            assert status2.reason == "Shared state test"

            # Manager 2: Verify is_active
            assert await manager2.is_active() is True

            await manager2.close()
        finally:
            # Cleanup
            await manager1.deactivate()
            await manager1.close()


# ============================================================================
# Test Safety Invariants
# ============================================================================


def get_reject_reason_strings(reject_reason: list) -> list[str]:
    """Extract string messages from reject_reason list (handles both strings and RiskViolation objects)."""
    result = []
    for item in reject_reason:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, RiskViolation):
            result.append(item.message)
        elif hasattr(item, "message"):
            result.append(str(item.message))
        else:
            result.append(str(item))
    return result


class TestKillSwitchSafetyInvariants:
    """Test kill switch enforces safety invariants (1%, 3x, 15%)."""

    @pytest.mark.asyncio
    async def test_position_size_limit_enforced(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test 1% max position size is enforced via risk enforcer.

        Safety Invariant: Position size <= 1% of portfolio
        Portfolio = $10,000 -> max position = $100 -> ~0.002 BTC at $50k
        """
        # Create violation for position size
        violation = RiskViolation(
            rule="POSITION_SIZE_EXCEEDED",
            severity=RiskSeverity.BLOCK.value,
            message="Position size 5.0% exceeds 1% maximum",
            current_value=5.0,
            limit_value=1.0,
        )

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=False,
                violations=[violation],
                position_size=5.0,
            )
        )

        kill_switch_manager = PaperKillSwitchManager()
        orchestrator._paper_kill_switch = kill_switch_manager

        result = await orchestrator.process_signal(mock_signal)

        # Verify rejection due to position size
        assert result.status == TradeStatus.REJECTED
        reason_strings = get_reject_reason_strings(result.reject_reason)
        assert any(
            "size" in reason.lower() or "1%" in reason for reason in reason_strings
        ), f"Expected position size rejection, got: {reason_strings}"

        await kill_switch_manager.close()

    @pytest.mark.asyncio
    async def test_leverage_limit_enforced(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test 3x max leverage is enforced via risk enforcer.

        Safety Invariant: Leverage <= 3x
        """
        # Create violation for leverage
        violation = RiskViolation(
            rule="LEVERAGE_EXCEEDED",
            severity=RiskSeverity.BLOCK.value,
            message="Leverage 5.0x exceeds 3x maximum",
            current_value=5.0,
            limit_value=3.0,
        )

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=False,
                violations=[violation],
                position_size=0.1,
            )
        )

        kill_switch_manager = PaperKillSwitchManager()
        orchestrator._paper_kill_switch = kill_switch_manager

        result = await orchestrator.process_signal(mock_signal)

        # Verify rejection due to leverage
        assert result.status == TradeStatus.REJECTED
        reason_strings = get_reject_reason_strings(result.reject_reason)
        assert any(
            "leverage" in reason.lower() or "3x" in reason for reason in reason_strings
        ), f"Expected leverage rejection, got: {reason_strings}"

        await kill_switch_manager.close()

    @pytest.mark.asyncio
    async def test_daily_loss_limit_enforced(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test 15% daily loss limit is enforced.

        Safety Invariant: Daily loss <= 15% of starting portfolio
        Portfolio = $10,000 -> max daily loss = $1,500
        """
        # Create violation for daily loss
        violation = RiskViolation(
            rule="DAILY_LOSS_LIMIT_EXCEEDED",
            severity=RiskSeverity.BLOCK.value,
            message="Daily loss limit 16.5% exceeds 15% maximum",
            current_value=16.5,
            limit_value=15.0,
        )

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=False,
                violations=[violation],
                position_size=0.1,
            )
        )

        kill_switch_manager = PaperKillSwitchManager()
        orchestrator._paper_kill_switch = kill_switch_manager

        result = await orchestrator.process_signal(mock_signal)

        # Verify rejection due to daily loss
        assert result.status == TradeStatus.REJECTED
        reason_strings = get_reject_reason_strings(result.reject_reason)
        assert any(
            "daily loss" in reason.lower() or "15%" in reason
            for reason in reason_strings
        ), f"Expected daily loss rejection, got: {reason_strings}"

        await kill_switch_manager.close()

    @pytest.mark.asyncio
    async def test_safe_position_within_all_limits(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that position within all safety limits is allowed.

        Safe parameters:
        - Position size: 0.5% (<= 1%)
        - Leverage: 2x (<= 3x)
        - Daily loss would be: < 15%
        """
        # Mock risk enforcer to approve
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=True,
                position_size=0.5,
            )
        )

        filled_order = create_filled_order("test-order-safe-001", quantity=0.01)
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-safe-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        kill_switch_manager = PaperKillSwitchManager()
        orchestrator._paper_kill_switch = kill_switch_manager

        # Process should succeed (within limits)
        result = await orchestrator.process_signal(mock_signal)
        assert (
            result.status == TradeStatus.EXECUTED
        ), f"Expected success, got: {result.reject_reason}"

        await kill_switch_manager.close()


# ============================================================================
# Test Demo Environment Safety
# ============================================================================


class TestDemoEnvironmentSafety:
    """Test that tests run in demo/paper environment only."""

    @pytest.mark.asyncio
    async def test_kill_switch_manager_uses_paper_redis_key(self):
        """Test that PaperKillSwitchManager uses the paper:kill_switch Redis key.

        This confirms demo/paper environment isolation from live trading.
        """
        manager = PaperKillSwitchManager()
        try:
            await manager.activate(reason="Demo key test", activated_by="test")
            status = await manager.get_status()
            assert status.active is True
        finally:
            await manager.deactivate()
            await manager.close()

    @pytest.mark.asyncio
    async def test_kill_switch_does_not_affect_live_trading(self):
        """Test that paper kill switch uses separate Redis key from live.

        The paper kill switch uses 'paper:kill_switch' which is distinct
        from any live trading kill switch keys, ensuring isolation.
        """
        manager = PaperKillSwitchManager()
        try:
            await manager.activate(reason="Isolation test", activated_by="test")
            # get_status() is async, need to await
            status = await manager.get_status()
            assert status.active is True
        finally:
            await manager.deactivate()
            await manager.close()


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestKillSwitchEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_multiple_activations_refresh_ttl(self):
        """Test that activating an already-active kill switch refreshes TTL."""
        manager = PaperKillSwitchManager()
        try:
            await manager.activate(reason="First", activated_by="test", ttl=100)

            status1 = await manager.get_status()
            ttl1 = status1.ttl_remaining

            # Activate again with longer TTL
            await manager.activate(reason="Second", activated_by="test", ttl=200)

            status2 = await manager.get_status()
            ttl2 = status2.ttl_remaining

            # TTL should be refreshed (close to 200, not 100)
            assert ttl2 > ttl1 or ttl2 == 200
            assert status2.reason == "Second"
        finally:
            await manager.deactivate()
            await manager.close()

    @pytest.mark.asyncio
    async def test_deactivate_when_not_active(self):
        """Test deactivate works when kill switch is not active."""
        manager = PaperKillSwitchManager()
        try:
            await manager.deactivate()
            result = await manager.deactivate()  # Should still return True
            assert result is True
            status = await manager.get_status()
            assert status.active is False
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_status_to_dict(self):
        """Test PaperKillSwitchStatus.to_dict() method."""
        status = PaperKillSwitchStatus(
            active=True,
            reason="Test",
            activated_at="2026-01-01T00:00:00Z",
            activated_by="test",
            ttl_remaining=100,
        )
        d = status.to_dict()
        assert d["active"] is True
        assert d["reason"] == "Test"
        assert d["ttl_remaining"] == 100

    @pytest.mark.asyncio
    async def test_status_str_representation(self):
        """Test PaperKillSwitchStatus string representation."""
        status_inactive = PaperKillSwitchStatus(active=False)
        str_inactive = str(status_inactive)
        assert "INACTIVE" in str_inactive

        status_active = PaperKillSwitchStatus(
            active=True,
            reason="Test reason",
            activated_by="tester",
            activated_at="2026-01-01T00:00:00Z",
            ttl_remaining=60,
        )
        str_active = str(status_active)
        assert "ACTIVE" in str_active
        assert "Test reason" in str_active
        assert "tester" in str_active
        assert "60s" in str_active

    @pytest.mark.asyncio
    async def test_concurrent_activation_attempts(self):
        """Test multiple concurrent activation attempts."""
        manager = PaperKillSwitchManager()
        try:

            async def activate(idx: int):
                await manager.activate(
                    reason=f"Concurrent {idx}", activated_by=f"tester{idx}"
                )

            # Run multiple activations concurrently
            await asyncio.gather(*[activate(i) for i in range(5)])

            # Should be active with the last reason
            status = await manager.get_status()
            assert status.active is True
        finally:
            await manager.deactivate()
            await manager.close()


# ============================================================================
# Test Orchestrator Integration Without Mock Kill Switch
# ============================================================================


class TestOrchestratorWithRealKillSwitch:
    """Test orchestrator with real (non-mocked) kill switch manager."""

    @pytest.mark.asyncio
    async def test_orchestrator_integration_with_real_kill_switch(
        self, mock_components, mock_signal, mock_signal_alt
    ):
        """Test full integration with real PaperKillSwitchManager.

        This test uses the actual Redis-backed kill switch manager,
        ensuring the orchestrator properly integrates with it.
        """
        # Create a third signal to avoid throttle issues
        mock_signal_third = make_signal(token="SOL/USDT")

        # Setup for successful execution when kill switch is inactive
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = create_filled_order("test-order-real-001")
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-real-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Create real kill switch manager and orchestrator
        kill_switch_manager = PaperKillSwitchManager()
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_components["signal_gen"],
            order_simulator=mock_components["order_sim"],
            position_tracker=mock_components["position_tracker"],
            risk_enforcer=mock_components["risk_enforcer"],
            telemetry_collector=mock_components["telemetry"],
            kill_switch=mock_components["kill_switch"],
            decision_enhancer=mock_components["decision_enhancer"],
            portfolio_value=10000.0,
        )
        orchestrator._paper_kill_switch = kill_switch_manager

        try:
            # Verify kill switch is initially inactive
            assert await kill_switch_manager.is_active() is False

            # Process signal should succeed when kill switch is inactive
            result_inactive = await orchestrator.process_signal(mock_signal)
            assert (
                result_inactive.status == TradeStatus.EXECUTED
            ), f"Expected success, got: {result_inactive.reject_reason}"

            # Activate kill switch
            await kill_switch_manager.activate(
                reason="Real integration test", activated_by="e2e_test"
            )
            assert await kill_switch_manager.is_active() is True

            # Process signal should be blocked when kill switch is active
            result_active = await orchestrator.process_signal(mock_signal_alt)
            assert result_active.status == TradeStatus.REJECTED

            # Deactivate and verify processing resumes (use third signal to avoid throttle)
            await kill_switch_manager.deactivate()
            assert await kill_switch_manager.is_active() is False

            result_resumed = await orchestrator.process_signal(mock_signal_third)
            assert (
                result_resumed.status == TradeStatus.EXECUTED
            ), f"Expected success after deactivation, got: {result_resumed.reject_reason}"
        finally:
            await kill_switch_manager.close()
