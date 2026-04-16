"""Verification test for signal → order creation path.

This test verifies that the order creation path is reachable from consumed signals.
Part of P0-REMEDIATION-001 Batch 2B.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.paper.models import OrderState, PaperOrder, TradeStatus
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.risk_models import RiskViolation
from signal_generation.models import Signal, SignalDirection, SignalStatus


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for orchestrator."""
    signal_generator = MagicMock()

    order_simulator = MagicMock()
    order_simulator.market_data = MagicMock()
    order_simulator.market_data.get_price = MagicMock(return_value=50000.0)
    order_simulator.set_market_price = MagicMock()
    order_simulator.place_order = AsyncMock()

    position_tracker = MagicMock()
    position_tracker.get_open_positions = AsyncMock(return_value=[])
    position_tracker.open_position = AsyncMock()

    risk_enforcer = MagicMock()

    telemetry = MagicMock()
    telemetry.start = AsyncMock()
    telemetry.stop = AsyncMock()
    telemetry.set_equity = AsyncMock()

    kill_switch = MagicMock()
    kill_switch.state = MagicMock()
    kill_switch.state.value = "armed"  # Not triggered

    decision_enhancer = MagicMock()
    decision_enhancer.enabled = False  # Disable LLM enhancement for tests

    return {
        "signal_generator": signal_generator,
        "order_simulator": order_simulator,
        "position_tracker": position_tracker,
        "risk_enforcer": risk_enforcer,
        "telemetry": telemetry,
        "kill_switch": kill_switch,
        "decision_enhancer": decision_enhancer,
    }


@pytest.fixture
def sample_signal():
    """Create a sample actionable signal."""
    return Signal(
        token="BTC/USDT",
        direction=SignalDirection.LONG,
        confidence=0.85,
        base_score=85.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        signal_id=str(uuid.uuid4()),
    )


class TestSignalToOrderPath:
    """Test signal → order creation path."""

    @pytest.mark.asyncio
    async def test_submit_signal_adds_to_queue(self, mock_dependencies, sample_signal):
        """Test that submit_signal() adds signal to queue."""
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        # Submit signal
        await orchestrator.submit_signal(sample_signal)

        # Verify signal is in queue
        assert orchestrator._signal_queue.qsize() == 1

        # Verify we can get it back
        queued_signal = orchestrator._signal_queue.get_nowait()
        assert queued_signal.signal_id == sample_signal.signal_id
        assert queued_signal.token == sample_signal.token

    @pytest.mark.asyncio
    async def test_process_signal_reaches_order_creation(
        self, mock_dependencies, sample_signal
    ):
        """Test that process_signal() reaches order creation when conditions are met."""
        # Setup risk enforcer to approve
        mock_dependencies["risk_enforcer"].validate_order = AsyncMock(
            return_value=MagicMock(
                approved=True,
                violations=[],
                position_size=0.1,
            )
        )

        # Setup order simulator to return filled order
        filled_order = PaperOrder(
            order_id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=0.1,
            price=50000.0,
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
        )
        mock_dependencies["order_simulator"].place_order = AsyncMock(
            return_value=filled_order
        )

        # Setup position tracker
        mock_position = MagicMock()
        mock_position.position_id = str(uuid.uuid4())
        mock_position.symbol = "BTC/USDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.metadata = {}
        mock_dependencies["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        # Process signal
        result = await orchestrator.process_signal(sample_signal)

        # Verify order simulator was called (order creation path reached)
        assert mock_dependencies["order_simulator"].place_order.called, (
            "Order simulator place_order() was NOT called - order creation path broken!"
        )

        # Verify result
        assert result.status == TradeStatus.EXECUTED
        assert result.order is not None
        assert result.position is not None

    @pytest.mark.asyncio
    async def test_process_signal_blocked_by_kill_switch(
        self, mock_dependencies, sample_signal
    ):
        """Test that kill switch blocks order creation."""
        mock_dependencies["kill_switch"].state.value = "triggered"

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        result = await orchestrator.process_signal(sample_signal)

        # Verify order simulator was NOT called
        assert not mock_dependencies["order_simulator"].place_order.called, (
            "Order simulator should NOT be called when kill switch is triggered"
        )

        # Verify rejection
        assert result.status == TradeStatus.REJECTED
        assert "kill-switch" in str(result.reject_reason).lower()

    @pytest.mark.asyncio
    async def test_process_signal_blocked_by_no_market_price(
        self, mock_dependencies, sample_signal
    ):
        """Test that missing market price blocks order creation for unknown symbols."""
        # Use an unknown symbol that has no default price
        sample_signal.token = "UNKNOWN/XYZ"
        mock_dependencies["order_simulator"].market_data.get_price = MagicMock(
            return_value=None
        )

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        result = await orchestrator.process_signal(sample_signal)

        # Verify order simulator was NOT called
        assert not mock_dependencies["order_simulator"].place_order.called, (
            "Order simulator should NOT be called when no market price"
        )

        # Verify rejection
        assert result.status == TradeStatus.REJECTED
        assert "market price" in str(result.reject_reason).lower()

    @pytest.mark.asyncio
    async def test_process_signal_blocked_by_risk_enforcer(
        self, mock_dependencies, sample_signal
    ):
        """Test that risk enforcer rejection blocks order creation."""
        # After ORM schema drift (ST-PAPER-RECON-008), violations are
        # RiskViolation objects, not plain strings.  The orchestrator's
        # _emit_gate_outcomes method accesses v.rule and v.message, so
        # the mock must provide proper RiskViolation instances.
        violation = RiskViolation(
            rule="position_limit",
            severity="block",
            message="Position limit exceeded",
            current_value=1.0,
            limit_value=1.0,
        )
        mock_dependencies["risk_enforcer"].validate_order = AsyncMock(
            return_value=MagicMock(
                approved=False,
                violations=[violation],
                position_size=0.0,
            )
        )

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        result = await orchestrator.process_signal(sample_signal)

        # Verify order simulator was NOT called
        assert not mock_dependencies["order_simulator"].place_order.called, (
            "Order simulator should NOT be called when risk enforcer rejects"
        )

        # Verify rejection
        assert result.status == TradeStatus.REJECTED
        # reject_reason is set to assessment.violations (list[RiskViolation])
        # so check that the violation message appears in the stringified reason
        reason_text = str(result.reject_reason)
        assert "Position limit exceeded" in reason_text

    @pytest.mark.asyncio
    async def test_full_signal_flow_simulation(self, mock_dependencies, sample_signal):
        """Test complete signal flow from submit to order creation."""
        # Setup mocks for successful flow
        mock_dependencies["risk_enforcer"].validate_order = AsyncMock(
            return_value=MagicMock(
                approved=True,
                violations=[],
                position_size=0.1,
            )
        )

        filled_order = PaperOrder(
            order_id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=0.1,
            price=50000.0,
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
        )
        mock_dependencies["order_simulator"].place_order = AsyncMock(
            return_value=filled_order
        )

        mock_position = MagicMock()
        mock_position.position_id = str(uuid.uuid4())
        mock_position.symbol = "BTC/USDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.metadata = {}
        mock_dependencies["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        # Start orchestrator
        await orchestrator.start()

        try:
            # Submit signal
            await orchestrator.submit_signal(sample_signal)

            # Wait for processing loop to process
            await asyncio.sleep(0.1)

            # Verify order was placed
            assert mock_dependencies["order_simulator"].place_order.called, (
                "Order simulator place_order() was NOT called in full flow!"
            )

            # Verify metrics updated
            metrics = orchestrator.get_metrics()
            assert metrics["signals_processed"] >= 1
            assert metrics["trades_executed"] >= 1

        finally:
            await orchestrator.stop()


class TestOrderCreationPathBlockers:
    """Test to identify specific blockers in the order creation path."""

    @pytest.mark.asyncio
    async def test_verify_all_path_components_exist(self, mock_dependencies):
        """Verify all components in the signal→order path exist and are callable."""
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        # Verify all required methods exist
        assert hasattr(orchestrator, "submit_signal"), "Missing submit_signal method"
        assert hasattr(orchestrator, "process_signal"), "Missing process_signal method"
        assert hasattr(orchestrator, "_create_order"), "Missing _create_order method"
        assert hasattr(orchestrator, "_processing_loop"), (
            "Missing _processing_loop method"
        )

        # Verify all dependencies are set
        assert orchestrator.order_simulator is not None, "order_simulator not set"
        assert orchestrator.risk_enforcer is not None, "risk_enforcer not set"
        assert orchestrator.position_tracker is not None, "position_tracker not set"
        assert orchestrator.kill_switch is not None, "kill_switch not set"

        # Verify signal queue exists
        assert orchestrator._signal_queue is not None, "Signal queue not initialized"

    @pytest.mark.asyncio
    async def test_create_order_produces_valid_order(
        self, mock_dependencies, sample_signal
    ):
        """Test that _create_order produces a valid PaperOrder."""
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        order = orchestrator._create_order(
            signal=sample_signal,
            position_size=0.1,
            entry_price=50000.0,
            correlation_id=str(uuid.uuid4()),
        )

        # Verify order is valid
        assert isinstance(order, PaperOrder), "_create_order did not return PaperOrder"
        assert order.symbol == sample_signal.token
        assert order.side == "buy"  # LONG -> buy
        assert order.quantity == 0.1
        assert order.price == 50000.0
        assert order.order_type == "market"
        assert order.state == OrderState.PENDING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
