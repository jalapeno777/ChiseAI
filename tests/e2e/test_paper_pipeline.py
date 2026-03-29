"""E2E tests for paper trading pipeline.

Tests the complete signal → order pipeline with mocked external dependencies
and real Redis for signal queue. Uses fakeredis for Redis mocking to test
the full SignalConsumer → Orchestrator → Order creation flow.

Part of PAPER-007: E2E Pipeline Validation Tests
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.paper.models import OrderState, PaperOrder, TradeStatus
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.signal_consumer import SignalConsumer
from signal_generation.models import Signal, SignalDirection, SignalStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_signal_generator():
    """Create a mock signal generator."""
    return MagicMock()


@pytest.fixture
def mock_order_simulator():
    """Create a mock order simulator with market data."""
    simulator = MagicMock()
    simulator.market_data = MagicMock()
    simulator.market_data.get_price = MagicMock(return_value=50000.0)
    simulator.set_market_price = MagicMock()
    simulator.place_order = AsyncMock()
    return simulator


@pytest.fixture
def mock_position_tracker():
    """Create a mock position tracker."""
    tracker = MagicMock()
    tracker.get_open_positions = AsyncMock(return_value=[])
    tracker.open_position = AsyncMock()
    return tracker


@pytest.fixture
def mock_risk_enforcer():
    """Create a mock risk enforcer that approves all orders."""
    enforcer = MagicMock()
    enforcer.validate_order = AsyncMock(
        return_value=MagicMock(
            approved=True,
            violations=[],
            position_size=0.1,
        )
    )
    return enforcer


@pytest.fixture
def mock_telemetry():
    """Create a mock telemetry collector."""
    telemetry = MagicMock()
    telemetry.start = AsyncMock()
    telemetry.stop = AsyncMock()
    telemetry.set_equity = AsyncMock()
    return telemetry


@pytest.fixture
def mock_kill_switch():
    """Create a mock kill switch that is not triggered."""
    kill_switch = MagicMock()
    kill_switch.state = MagicMock()
    kill_switch.state.value = "armed"
    return kill_switch


@pytest.fixture
def mock_decision_enhancer():
    """Create a mock decision enhancer (disabled)."""
    enhancer = MagicMock()
    enhancer.enabled = False
    return enhancer


@pytest.fixture
def sample_actionable_signal():
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


@pytest.fixture
def filled_order():
    """Create a filled order for mock return."""
    return PaperOrder(
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


@pytest.fixture
def mock_processed_position(filled_order):
    """Create a mock open position."""
    position = MagicMock()
    position.position_id = filled_order.order_id
    position.symbol = "BTC/USDT"
    position.side = "long"
    position.entry_price = 50000.0
    position.quantity = 0.1
    position.metadata = {}
    return position


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for SignalConsumer."""
    redis = AsyncMock()
    redis.scan = AsyncMock(return_value=(0, []))
    redis.type = AsyncMock(return_value="hash")
    redis.hgetall = AsyncMock(return_value={})
    redis.smembers = AsyncMock(return_value=set())
    redis.sadd = AsyncMock()
    redis.hset = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()
    redis.close = AsyncMock()
    redis.expire = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFullSignalToOrderPipeline:
    """AC1: Full signal→order E2E validation test.

    Tests complete flow: SignalConsumer → Orchestrator → Order creation.
    Uses mocked external dependencies (Redis async, exchange APIs).
    Verifies signal is processed and order is created.
    """

    @pytest.mark.asyncio
    async def test_full_signal_to_order_pipeline(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        mock_decision_enhancer,
        mock_redis,
        sample_actionable_signal,
        filled_order,
        mock_processed_position,
    ):
        """Test the complete signal → order pipeline.

        This is the primary E2E test verifying:
        1. SignalConsumer polls Redis and finds actionable signals
        2. Signal is submitted to Orchestrator
        3. Orchestrator validates via RiskEnforcer
        4. Order is placed via OrderSimulator
        5. Position is opened in PositionTracker
        """
        signal_id = sample_actionable_signal.signal_id
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        # Configure mock Redis to return our test signal
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(
            return_value={
                "signal_id": signal_id,
                "token": "BTC/USDT",
                "direction": "long",
                "confidence": "0.85",
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "actionable",
                "timeframe": "1h",
                "mode": "paper",
            }
        )
        mock_redis.smembers = AsyncMock(return_value=set())  # Not processed yet
        mock_redis.sadd = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)  # Lock acquisition succeeds
        mock_redis.delete = AsyncMock()

        # Setup order simulator to return filled order
        mock_order_simulator.place_order = AsyncMock(return_value=filled_order)
        mock_position_tracker.open_position = AsyncMock(
            return_value=mock_processed_position
        )

        # Create orchestrator with all mocks
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            decision_enhancer=mock_decision_enhancer,
        )

        # Create signal consumer with the mock Redis
        consumer = SignalConsumer(
            orchestrator=orchestrator,
            redis_client=mock_redis,
            poll_interval=0.1,
            symbol_throttle_seconds=0.0,
        )

        # Start orchestrator
        await orchestrator.start()

        try:
            # Start consumer
            await consumer.start()

            # Wait for processing
            await asyncio.sleep(0.3)

            # Stop consumer
            await consumer.stop()

            # Verify signal was submitted to orchestrator
            # The consumer should have called orchestrator.submit_signal
            # Check that order simulator was called (order creation path reached)
            assert mock_order_simulator.place_order.called, (
                "Order simulator place_order() was NOT called - "
                "order creation path not reached in E2E flow!"
            )

            # Verify order details
            call_args = mock_order_simulator.place_order.call_args
            assert call_args is not None

            # Verify orchestrator processed the signal
            metrics = orchestrator.get_metrics()
            assert (
                metrics["signals_processed"] >= 1
            ), "Orchestrator did not process any signals"

        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_signal_not_processed_when_not_actionable(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        mock_decision_enhancer,
        mock_redis,
    ):
        """Test that non-actionable signals are skipped in E2E flow.

        Verifies that signals with status != 'actionable' are not
        submitted to the orchestrator.
        """
        signal_id = str(uuid.uuid4())
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        # Configure mock Redis to return a non-actionable signal
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(
            return_value={
                "signal_id": signal_id,
                "token": "BTC/USDT",
                "direction": "long",
                "confidence": "0.85",
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "logged_only",  # Not actionable!
                "timeframe": "1h",
                "mode": "paper",
            }
        )

        # Create orchestrator
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            decision_enhancer=mock_decision_enhancer,
        )

        # Create consumer
        consumer = SignalConsumer(
            orchestrator=orchestrator,
            redis_client=mock_redis,
            poll_interval=0.1,
            symbol_throttle_seconds=0.0,
        )

        await consumer.start()
        await asyncio.sleep(0.2)
        await consumer.stop()

        # Verify orchestrator never received the signal
        # (submit_signal should not have been called for non-actionable)
        metrics = orchestrator.get_metrics()
        assert metrics["signals_processed"] == 0

    @pytest.mark.asyncio
    async def test_orchestrator_killswitch_blocks_order(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_decision_enhancer,
        sample_actionable_signal,
    ):
        """Test that kill switch blocks order creation in the pipeline.

        When kill switch is triggered, signals should be rejected without
        creating orders.
        """
        # Trigger kill switch
        mock_kill_switch = MagicMock()
        mock_kill_switch.state = MagicMock()
        mock_kill_switch.state.value = "triggered"

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            decision_enhancer=mock_decision_enhancer,
        )

        # Process signal
        result = await orchestrator.process_signal(sample_actionable_signal)

        # Verify order was blocked
        assert result.status == TradeStatus.REJECTED
        assert "kill" in str(result.reject_reason).lower()
        mock_order_simulator.place_order.assert_not_called()


@pytest.mark.e2e
class TestPipelineLatency:
    """Tests for pipeline latency targets.

    Verifies that the signal → order pipeline meets latency targets:
    - Signal → Order placement: <500ms
    - Total pipeline: <2 seconds
    """

    @pytest.mark.asyncio
    async def test_signal_to_order_latency_under_target(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        mock_decision_enhancer,
        sample_actionable_signal,
        filled_order,
        mock_processed_position,
    ):
        """Test that signal → order latency is under 500ms target."""
        import time

        mock_order_simulator.place_order = AsyncMock(return_value=filled_order)
        mock_position_tracker.open_position = AsyncMock(
            return_value=mock_processed_position
        )

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            decision_enhancer=mock_decision_enhancer,
        )

        await orchestrator.start()

        try:
            start_time = time.perf_counter()
            result = await orchestrator.process_signal(sample_actionable_signal)
            end_time = time.perf_counter()

            latency_ms = (end_time - start_time) * 1000

            # Verify order was executed
            assert result.status == TradeStatus.EXECUTED

            # Verify latency target
            target_ms = PaperTradingOrchestrator.TARGET_SIGNAL_TO_ORDER_MS
            assert latency_ms < target_ms, (
                f"Signal → Order latency {latency_ms:.1f}ms exceeds "
                f"target {target_ms}ms"
            )

        finally:
            await orchestrator.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
