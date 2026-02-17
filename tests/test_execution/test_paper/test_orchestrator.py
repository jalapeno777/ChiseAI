"""Integration tests for Paper Trading Orchestrator.

Tests end-to-end signal processing workflow including:
- Signal consumption and validation
- Risk enforcement
- Order placement and fills
- Position tracking
- Telemetry recording
- Kill-switch integration
- Latency requirements (<2 seconds total)
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import models
from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
    PaperTradeResult,
    TradeStatus,
)
from execution.paper.orchestrator import PaperTradingOrchestrator
from signal_generation.models import Signal, SignalDirection, SignalStatus


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
    """Mock kill switch for testing."""

    def __init__(self):
        self.state = MagicMock()
        self.state.value = "armed"

    async def execute_kill_switch(self, **kwargs):
        self.state.value = "triggered"


@pytest.fixture
def mock_signal():
    """Create a mock signal for testing."""
    return Signal(
        token="BTC/USDT",
        direction=SignalDirection.LONG,
        confidence=0.85,
        base_score=85.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        stop_loss=45000.0,
        stop_loss_method="atr",
        signal_id="test-signal-001",
    )


@pytest.fixture
def mock_signal_low_confidence():
    """Create a low-confidence signal for testing rejection."""
    return Signal(
        token="ETH/USDT",
        direction=SignalDirection.SHORT,
        confidence=0.60,  # Below 75% threshold
        base_score=60.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.LOGGED_ONLY,
        timeframe="1h",
        signal_id="test-signal-002",
    )


@pytest.fixture
def mock_components():
    """Create mock components for orchestrator."""
    # Signal generator
    signal_gen = MagicMock()

    # Order simulator (mocked but returns real PaperOrder)
    order_sim = AsyncMock()

    # Position tracker
    position_tracker = AsyncMock()
    position_tracker.get_open_positions = AsyncMock(return_value=[])
    position_tracker.open_position = AsyncMock()
    position_tracker.close_position = AsyncMock()

    # Risk enforcer
    risk_enforcer = AsyncMock()

    # Telemetry
    telemetry = MockTelemetryCollector()

    # Kill switch
    kill_switch = MockKillSwitch()

    return {
        "signal_gen": signal_gen,
        "order_sim": order_sim,
        "position_tracker": position_tracker,
        "risk_enforcer": risk_enforcer,
        "telemetry": telemetry,
        "kill_switch": kill_switch,
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
        portfolio_value=10000.0,
    )


class TestOrchestratorInit:
    """Test orchestrator initialization."""

    def test_initialization(self, mock_components):
        """Test orchestrator initializes correctly."""
        orch = PaperTradingOrchestrator(
            signal_generator=mock_components["signal_gen"],
            order_simulator=mock_components["order_sim"],
            position_tracker=mock_components["position_tracker"],
            risk_enforcer=mock_components["risk_enforcer"],
            telemetry_collector=mock_components["telemetry"],
            kill_switch=mock_components["kill_switch"],
            portfolio_value=50000.0,
        )

        assert orch.portfolio_value == 50000.0
        assert orch._running is False
        assert orch._metrics["signals_processed"] == 0

    def test_default_portfolio_value(self, mock_components):
        """Test default portfolio value is $10,000."""
        orch = PaperTradingOrchestrator(
            signal_generator=mock_components["signal_gen"],
            order_simulator=mock_components["order_sim"],
            position_tracker=mock_components["position_tracker"],
            risk_enforcer=mock_components["risk_enforcer"],
            telemetry_collector=mock_components["telemetry"],
            kill_switch=mock_components["kill_switch"],
        )

        assert orch.portfolio_value == 10000.0


class TestSignalProcessing:
    """Test signal processing workflow."""

    @pytest.mark.asyncio
    async def test_successful_trade_flow(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test successful signal-to-position flow."""
        # Setup mocks
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=True,
                position_size=0.1,
                correlation_id=mock_signal.signal_id,
            )
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            order_id="test-order-001",
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
            correlation_id="test-corr-001",
        )
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Process signal
        result = await orchestrator.process_signal(mock_signal)

        # Verify result
        assert result.status == TradeStatus.EXECUTED
        assert result.order is not None
        assert result.position is not None
        assert result.correlation_id is not None
        assert len(result.reject_reason) == 0

    @pytest.mark.asyncio
    async def test_signal_rejected_by_risk(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test signal rejected by risk enforcer."""
        from execution.paper.models import RiskAssessment

        # Setup rejection
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=False,
                violations=["Max position size exceeded", "Insufficient confidence"],
                correlation_id=mock_signal.signal_id,
            )
        )

        result = await orchestrator.process_signal(mock_signal)

        # Verify rejection
        assert result.status == TradeStatus.REJECTED
        assert len(result.reject_reason) == 2
        assert "Max position size exceeded" in result.reject_reason
        assert result.order is None
        assert result.position is None

    @pytest.mark.asyncio
    async def test_signal_rejected_by_kill_switch(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test signal rejected when kill-switch is triggered."""
        # Trigger kill-switch
        mock_components["kill_switch"].state.value = "triggered"

        result = await orchestrator.process_signal(mock_signal)

        # Verify rejection
        assert result.status == TradeStatus.REJECTED
        assert "Kill-switch triggered" in result.reject_reason
        assert result.order is None

    @pytest.mark.asyncio
    async def test_low_confidence_signal_rejected(
        self, orchestrator, mock_components, mock_signal_low_confidence
    ):
        """Test low confidence signal is rejected."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=False,
                violations=["Signal confidence 60.0% below minimum 75.0%"],
                correlation_id=mock_signal_low_confidence.signal_id,
            )
        )

        result = await orchestrator.process_signal(mock_signal_low_confidence)

        assert result.status == TradeStatus.REJECTED
        assert any("confidence" in reason.lower() for reason in result.reject_reason)

    @pytest.mark.asyncio
    async def test_order_fill_failure(self, orchestrator, mock_components, mock_signal):
        """Test handling when order fails to fill."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        # Order rejected by simulator
        rejected_order = PaperOrder(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            order_id="test-order-002",
            state=OrderState.REJECTED,
            correlation_id="test-corr-002",
        )
        mock_components["order_sim"].place_order = AsyncMock(
            return_value=rejected_order
        )

        result = await orchestrator.process_signal(mock_signal)

        assert result.status == TradeStatus.FAILED
        assert result.order is not None
        assert result.order.state == OrderState.REJECTED


class TestLatencyRequirements:
    """Test latency requirements (<2 seconds total)."""

    @pytest.mark.asyncio
    async def test_total_latency_under_2_seconds(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test total pipeline latency is under 2 seconds."""
        from execution.paper.models import RiskAssessment

        # Setup fast mocks
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            order_id="test-order-003",
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
        )
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-003"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Measure latency
        start = time.perf_counter()
        result = await orchestrator.process_signal(mock_signal)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify latency and result
        assert result.status == TradeStatus.EXECUTED
        assert elapsed_ms < 2000, f"Latency {elapsed_ms:.1f}ms exceeds 2000ms target"
        print(f"\nMeasured latency: {elapsed_ms:.1f}ms")

    @pytest.mark.asyncio
    async def test_signal_to_order_latency_under_500ms(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test signal-to-order latency is under 500ms."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            order_id="test-order-004",
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
        )
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        # Measure just the order placement phase
        start = time.perf_counter()
        await orchestrator.process_signal(mock_signal)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Should be well under 500ms since mocks are instant
        assert elapsed_ms < 500, (
            f"Signal-to-order latency {elapsed_ms:.1f}ms exceeds 500ms"
        )


class TestErrorHandling:
    """Test error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_component_error_does_not_crash_loop(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that component errors don't crash the processing loop."""
        # Make risk enforcer raise exception
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            side_effect=Exception("Risk service unavailable")
        )

        # Should return failed result, not raise
        result = await orchestrator.process_signal(mock_signal)

        assert result.status == TradeStatus.FAILED
        assert "Risk service unavailable" in result.reject_reason[0]

    @pytest.mark.asyncio
    async def test_order_simulator_error_handled(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test order simulator errors are handled gracefully."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        # Make order simulator raise exception
        mock_components["order_sim"].place_order = AsyncMock(
            side_effect=Exception("Exchange connection failed")
        )

        result = await orchestrator.process_signal(mock_signal)

        assert result.status == TradeStatus.FAILED
        assert "Exchange connection failed" in result.reject_reason[0]

    @pytest.mark.asyncio
    async def test_correlation_id_preserved_in_errors(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test correlation ID is preserved even in error cases."""
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            side_effect=Exception("Service error")
        )

        result = await orchestrator.process_signal(mock_signal)

        assert result.correlation_id is not None
        assert len(result.correlation_id) > 0


class TestMetricsAndReporting:
    """Test metrics collection and reporting."""

    @pytest.mark.asyncio
    async def test_metrics_updated_on_success(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test metrics are updated on successful trade."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )
        mock_components["order_sim"].place_order = AsyncMock(
            return_value=PaperOrder(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-005",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=50000.0,
            )
        )
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        # Process signal
        await orchestrator.process_signal(mock_signal)

        # Check metrics
        metrics = orchestrator.get_metrics()
        assert metrics["signals_processed"] == 1
        assert metrics["trades_executed"] == 1
        assert metrics["trades_rejected"] == 0
        assert metrics["avg_latency_ms"] > 0

    @pytest.mark.asyncio
    async def test_metrics_updated_on_rejection(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test metrics are updated on rejected signal."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(
                approved=False,
                violations=["Risk limit exceeded"],
            )
        )

        await orchestrator.process_signal(mock_signal)

        metrics = orchestrator.get_metrics()
        assert metrics["signals_processed"] == 1
        assert metrics["trades_executed"] == 0
        assert metrics["trades_rejected"] == 1

    @pytest.mark.asyncio
    async def test_portfolio_summary(self, orchestrator, mock_components, mock_signal):
        """Test portfolio summary generation."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )
        mock_components["order_sim"].place_order = AsyncMock(
            return_value=PaperOrder(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-006",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=50000.0,
            )
        )
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )
        mock_components["position_tracker"].get_open_positions = AsyncMock(
            return_value=[MagicMock(unrealized_pnl=100.0)]
        )
        mock_components["position_tracker"].get_closed_positions = AsyncMock(
            return_value=[MagicMock(realized_pnl=50.0)]
        )

        await orchestrator.process_signal(mock_signal)

        summary = await orchestrator.get_portfolio_summary()

        assert "portfolio_value" in summary
        assert "open_positions" in summary
        assert "metrics" in summary


class TestPositionManagement:
    """Test position opening and closing."""

    @pytest.mark.asyncio
    async def test_close_position_updates_portfolio(
        self, orchestrator, mock_components
    ):
        """Test closing a position updates portfolio value."""
        mock_position = MagicMock()
        mock_position.position_id = "test-pos-007"
        mock_position.symbol = "BTC/USDT"

        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 150.0)  # $150 profit
        )

        initial_value = orchestrator.portfolio_value
        result = await orchestrator.close_position("test-pos-007", 51000.0)

        assert result is not None
        assert result[1] == 150.0  # Realized PnL
        assert orchestrator.portfolio_value == initial_value + 150.0


class TestConcurrency:
    """Test concurrent signal processing."""

    @pytest.mark.asyncio
    async def test_multiple_signals_processed(self, orchestrator, mock_components):
        """Test multiple signals can be processed."""
        from execution.paper.models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )
        mock_components["order_sim"].place_order = AsyncMock(
            return_value=PaperOrder(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-008",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=50000.0,
            )
        )
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        # Create multiple signals
        signals = [
            Signal(
                token=f"TOKEN{i}/USDT",
                direction=SignalDirection.LONG,
                confidence=0.80,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                stop_loss=100.0,
            )
            for i in range(5)
        ]

        # Process all signals
        results = await asyncio.gather(
            *[orchestrator.process_signal(sig) for sig in signals]
        )

        # All should succeed
        assert all(r.status == TradeStatus.EXECUTED for r in results)
        assert len(results) == 5

        # Metrics should show 5 processed
        metrics = orchestrator.get_metrics()
        assert metrics["signals_processed"] == 5
        assert metrics["trades_executed"] == 5


class TestStartStop:
    """Test orchestrator lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, orchestrator, mock_components):
        """Test orchestrator start and stop."""
        await orchestrator.start()

        assert orchestrator._running is True
        assert orchestrator._processing_task is not None
        assert mock_components["telemetry"].running is True

        await orchestrator.stop()

        assert orchestrator._running is False
        assert mock_components["telemetry"].running is False

    @pytest.mark.asyncio
    async def test_submit_signal_to_queue(self, orchestrator, mock_components):
        """Test signal submission to queue."""
        await orchestrator.start()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=85.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=45000.0,
        )

        await orchestrator.submit_signal(signal)

        # Signal should be in queue
        assert orchestrator._signal_queue.qsize() == 1

        await orchestrator.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
