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
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import models
from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
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
    # Mock market_data provider with default price
    order_sim.market_data = MagicMock()
    order_sim.market_data.get_price = MagicMock(return_value=50000.0)

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
    async def test_throttle_allows_different_timeframes_same_symbol(
        self, orchestrator, mock_components
    ):
        """Test that G1_THROTTLE allows signals for same symbol with different timeframes.

        Before fix: Only first signal per symbol passed, subsequent timeframes
        for same symbol were incorrectly throttled (98% signal rejection).
        After fix: Signals with different timeframes are independently throttled.
        """
        import os
        import uuid

        from execution.paper.models import RiskAssessment

        # Set throttle interval to 60 seconds via env var (orchestrator reads it at init)
        original_val = os.environ.get("SYMBOL_EVAL_INTERVAL_SECONDS")
        os.environ["SYMBOL_EVAL_INTERVAL_SECONDS"] = "60"

        try:
            # Create fresh orchestrator with 60s throttle
            throttle_orch = PaperTradingOrchestrator(
                signal_generator=mock_components["signal_gen"],
                order_simulator=mock_components["order_sim"],
                position_tracker=mock_components["position_tracker"],
                risk_enforcer=mock_components["risk_enforcer"],
                telemetry_collector=mock_components["telemetry"],
                kill_switch=mock_components["kill_switch"],
                portfolio_value=10000.0,
            )

            # Setup mocks
            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=RiskAssessment(approved=True, position_size=0.1)
            )

            filled_order = PaperOrder(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-throttle",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=50000.0,
            )
            mock_components["order_sim"].place_order = AsyncMock(
                return_value=filled_order
            )

            mock_position = MagicMock()
            mock_position.position_id = "test-pos-throttle"
            mock_components["position_tracker"].open_position = AsyncMock(
                return_value=mock_position
            )

            # Signal 1: BTC/USDT on 15m timeframe
            signal_15m = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="15m",
                signal_id=str(uuid.uuid4()),
            )

            # Signal 2: BTC/USDT on 1h timeframe (same symbol, different timeframe)
            signal_1h = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                signal_id=str(uuid.uuid4()),
            )

            # Signal 3: BTC/USDT on 4h timeframe (same symbol, different timeframe)
            signal_4h = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="4h",
                signal_id=str(uuid.uuid4()),
            )

            # Setup mocks
            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=RiskAssessment(approved=True, position_size=0.1)
            )

            filled_order = PaperOrder(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-throttle",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=50000.0,
            )
            mock_components["order_sim"].place_order = AsyncMock(
                return_value=filled_order
            )

            mock_position = MagicMock()
            mock_position.position_id = "test-pos-throttle"
            mock_components["position_tracker"].open_position = AsyncMock(
                return_value=mock_position
            )

            # Signal 1: BTC/USDT on 15m timeframe
            signal_15m = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="15m",
                signal_id=str(uuid.uuid4()),
            )

            # Signal 2: BTC/USDT on 1h timeframe (same symbol, different timeframe)
            signal_1h = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                signal_id=str(uuid.uuid4()),
            )

            # Signal 3: BTC/USDT on 4h timeframe (same symbol, different timeframe)
            signal_4h = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="4h",
                signal_id=str(uuid.uuid4()),
            )

            # Process 15m signal - should succeed
            result_15m = await throttle_orch.process_signal(signal_15m)
            assert (
                result_15m.status == TradeStatus.EXECUTED
            ), f"15m signal should pass, got: {result_15m.status} {result_15m.reject_reason}"

            # Process 1h signal - should ALSO succeed (different timeframe)
            result_1h = await throttle_orch.process_signal(signal_1h)
            assert result_1h.status == TradeStatus.EXECUTED, (
                f"1h signal should pass (different timeframe), got: {result_1h.status} "
                f"{result_1h.reject_reason}"
            )

            # Process 4h signal - should ALSO succeed (different timeframe)
            result_4h = await throttle_orch.process_signal(signal_4h)
            assert result_4h.status == TradeStatus.EXECUTED, (
                f"4h signal should pass (different timeframe), got: {result_4h.status} "
                f"{result_4h.reject_reason}"
            )

            # Verify metrics show 3 signals processed (not rejected by throttle)
            assert (
                throttle_orch._metrics["signals_processed"] == 3
            ), f"Expected 3 signals processed, got {throttle_orch._metrics['signals_processed']}"
            assert (
                throttle_orch._metrics["gate_g1_throttle_count"] == 0
            ), f"Expected 0 throttle rejections, got {throttle_orch._metrics['gate_g1_throttle_count']}"

        finally:
            # Restore original env
            if original_val is None:
                os.environ.pop("SYMBOL_EVAL_INTERVAL_SECONDS", None)
            else:
                os.environ["SYMBOL_EVAL_INTERVAL_SECONDS"] = original_val

    @pytest.mark.asyncio
    async def test_throttle_still_works_for_same_symbol_same_timeframe(
        self, orchestrator, mock_components
    ):
        """Test that G1_THROTTLE still correctly throttles same symbol+timeframe within window."""
        import os
        import uuid

        from execution.paper.models import RiskAssessment

        # Set throttle interval to 60 seconds
        original_val = os.environ.get("SYMBOL_EVAL_INTERVAL_SECONDS")
        os.environ["SYMBOL_EVAL_INTERVAL_SECONDS"] = "60"

        try:
            throttle_orch = PaperTradingOrchestrator(
                signal_generator=mock_components["signal_gen"],
                order_simulator=mock_components["order_sim"],
                position_tracker=mock_components["position_tracker"],
                risk_enforcer=mock_components["risk_enforcer"],
                telemetry_collector=mock_components["telemetry"],
                kill_switch=mock_components["kill_switch"],
                portfolio_value=10000.0,
            )

            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=RiskAssessment(approved=True, position_size=0.1)
            )

            filled_order = PaperOrder(
                symbol="ETH/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-eth",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=3000.0,
            )
            mock_components["order_sim"].place_order = AsyncMock(
                return_value=filled_order
            )

            mock_position = MagicMock()
            mock_position.position_id = "test-pos-eth"
            mock_components["position_tracker"].open_position = AsyncMock(
                return_value=mock_position
            )

            # Two signals: same symbol AND same timeframe
            signal_1 = Signal(
                token="ETH/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                signal_id=str(uuid.uuid4()),
            )

            signal_2 = Signal(
                token="ETH/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",  # Same timeframe
                signal_id=str(uuid.uuid4()),
            )

            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=RiskAssessment(approved=True, position_size=0.1)
            )

            filled_order = PaperOrder(
                symbol="ETH/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-eth",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=3000.0,
            )
            mock_components["order_sim"].place_order = AsyncMock(
                return_value=filled_order
            )

            mock_position = MagicMock()
            mock_position.position_id = "test-pos-eth"
            mock_components["position_tracker"].open_position = AsyncMock(
                return_value=mock_position
            )

            # Two signals: same symbol AND same timeframe
            signal_1 = Signal(
                token="ETH/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                signal_id=str(uuid.uuid4()),
            )

            signal_2 = Signal(
                token="ETH/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",  # Same timeframe
                signal_id=str(uuid.uuid4()),
            )

            # First signal should pass
            result_1 = await throttle_orch.process_signal(signal_1)
            assert result_1.status == TradeStatus.EXECUTED

            # Second signal should be throttled (same symbol+timeframe)
            result_2 = await throttle_orch.process_signal(signal_2)
            assert result_2.status == TradeStatus.REJECTED
            assert any(
                "throttled" in r.lower() for r in result_2.reject_reason
            ), f"Expected throttle rejection, got: {result_2.reject_reason}"

            # Verify throttle metric was incremented
            assert throttle_orch._metrics["gate_g1_throttle_count"] == 1

        finally:
            if original_val is None:
                os.environ.pop("SYMBOL_EVAL_INTERVAL_SECONDS", None)
            else:
                os.environ["SYMBOL_EVAL_INTERVAL_SECONDS"] = original_val

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
        assert (
            elapsed_ms < 500
        ), f"Signal-to-order latency {elapsed_ms:.1f}ms exceeds 500ms"


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

    @pytest.mark.asyncio
    async def test_signals_processed_not_double_counted(
        self, orchestrator, mock_components, mock_signal
    ):
        """Regression test: signals_processed should increment once per signal.

        This test ensures that the signals_processed metric is incremented
        exactly once per signal, not double-counted in both the processing
        loop and process_signal method.

        Bug history: Previously incremented in both _processing_loop (line 211)
        and process_signal (line 265), causing incorrect metrics.
        """
        from execution.paper.models import RiskAssessment

        # Setup for successful processing
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )
        mock_components["order_sim"].place_order = AsyncMock(
            return_value=PaperOrder(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                order_id="test-order-regression",
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=50000.0,
            )
        )
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        # Get initial count
        initial_count = orchestrator._metrics["signals_processed"]

        # Process one signal directly (process_signal is the authoritative counter)
        await orchestrator.process_signal(mock_signal)

        # Verify count incremented by exactly 1
        final_count = orchestrator._metrics["signals_processed"]
        assert (
            final_count == initial_count + 1
        ), f"Expected {initial_count + 1}, got {final_count}. signals_processed should increment exactly once per signal."


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

    @pytest.mark.asyncio
    async def test_close_position_calls_outcome_capture(
        self, orchestrator, mock_components
    ):
        """Test that close_position calls outcome_capture.on_position_close()."""
        from datetime import UTC, datetime

        from execution.outcome_capture.integration import OutcomeCaptureResult

        # Create a mock position with all required attributes
        mock_position = MagicMock()
        mock_position.position_id = "test-pos-close-001"
        mock_position.symbol = "BTC/USDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.opened_at = datetime.now(UTC)
        mock_position.metadata = {
            "signal_id": "test-signal-close-001",
            "order_id": "test-order-close-001",
            "correlation_id": "test-corr-close-001",
            "leverage": 2.0,
        }

        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 150.0)  # $150 profit
        )

        # Create mock outcome_capture
        mock_outcome_capture = AsyncMock()
        mock_outcome_capture.on_position_close = AsyncMock(
            return_value=OutcomeCaptureResult(
                success=True,
                outcome_id="test-outcome-001",
                correlation_id="test-corr-close-001",
                discord_message_id="123456789",
                persisted_to="postgres",
            )
        )
        orchestrator.outcome_capture = mock_outcome_capture

        # Close the position
        result = await orchestrator.close_position(
            "test-pos-close-001", 51000.0, reason="test_close"
        )

        # Verify outcome_capture was called
        assert result is not None
        mock_outcome_capture.on_position_close.assert_called_once()

        # Verify call arguments
        call_args = mock_outcome_capture.on_position_close.call_args
        assert call_args.kwargs["exit_price"] == 51000.0
        assert call_args.kwargs["realized_pnl"] == 150.0
        assert call_args.kwargs["reason"] == "test_close"
        assert call_args.kwargs["correlation_id"] == "test-corr-close-001"

    @pytest.mark.asyncio
    async def test_close_position_outcome_capture_error_does_not_block(
        self, orchestrator, mock_components
    ):
        """Test that errors in outcome capture don't block position close."""
        mock_position = MagicMock()
        mock_position.position_id = "test-pos-close-002"
        mock_position.symbol = "BTC/USDT"
        mock_position.side = "short"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.opened_at = datetime.now(UTC)
        mock_position.metadata = {}

        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, -50.0)  # $50 loss
        )

        # Create mock outcome_capture that raises exception
        mock_outcome_capture = AsyncMock()
        mock_outcome_capture.on_position_close = AsyncMock(
            side_effect=Exception("Discord notification failed")
        )
        orchestrator.outcome_capture = mock_outcome_capture

        initial_value = orchestrator.portfolio_value

        # Close the position - should not raise despite outcome_capture error
        result = await orchestrator.close_position("test-pos-close-002", 49000.0)

        # Verify position was still closed
        assert result is not None
        assert result[1] == -50.0
        assert orchestrator.portfolio_value == initial_value - 50.0

        # Verify outcome_capture was called
        mock_outcome_capture.on_position_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_position_without_outcome_capture(
        self, orchestrator, mock_components
    ):
        """Test that close_position works when outcome_capture is None."""
        mock_position = MagicMock()
        mock_position.position_id = "test-pos-close-003"
        mock_position.symbol = "BTC/USDT"

        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 100.0)
        )

        # Ensure outcome_capture is None
        orchestrator.outcome_capture = None

        initial_value = orchestrator.portfolio_value

        # Close the position - should work without outcome_capture
        result = await orchestrator.close_position("test-pos-close-003", 50500.0)

        # Verify position was closed
        assert result is not None
        assert result[1] == 100.0
        assert orchestrator.portfolio_value == initial_value + 100.0

    @pytest.mark.asyncio
    async def test_opposite_signal_closes_existing_position(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that opposite signal closes existing position (BURNIN-001 fix)."""
        # Setup: Create an existing SHORT position
        from datetime import UTC, datetime

        from execution.paper.models import RiskAssessment

        existing_position = MagicMock()
        existing_position.position_id = "existing-pos-001"
        existing_position.symbol = "BTC/USDT"
        existing_position.side = "short"
        existing_position.opened_at = datetime.now(
            UTC
        )  # Fresh position, not time-expired

        # Mock get_open_positions to return the existing position
        mock_components["position_tracker"].get_open_positions = AsyncMock(
            return_value=[existing_position]
        )
        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(existing_position, 100.0)
        )

        # Setup risk enforcer and order simulator for new position
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            order_id="test-order-opp-001",
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
        )
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "new-pos-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Process a LONG signal (opposite of existing SHORT)
        result = await orchestrator.process_signal(mock_signal)

        # Verify existing position was closed
        mock_components["position_tracker"].close_position.assert_called_once()
        call_args = mock_components["position_tracker"].close_position.call_args
        assert call_args.kwargs["position_id"] == existing_position.position_id
        assert call_args.kwargs["exit_price"] == 50000.0

        # Verify new position was opened
        mock_components["position_tracker"].open_position.assert_called_once()

        # Verify trade was executed
        assert result.status == TradeStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_same_direction_signal_skipped(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that same direction signal is skipped (BURNIN-001 fix)."""
        # Setup: Create an existing LONG position
        from datetime import UTC, datetime

        existing_position = MagicMock()
        existing_position.position_id = "existing-pos-002"
        existing_position.symbol = "BTC/USDT"
        existing_position.side = "long"
        existing_position.opened_at = datetime.now(
            UTC
        )  # Fresh position, not time-expired

        # Mock get_open_positions to return the existing position
        mock_components["position_tracker"].get_open_positions = AsyncMock(
            return_value=[existing_position]
        )

        # Process a LONG signal (same as existing position)
        result = await orchestrator.process_signal(mock_signal)

        # Verify signal was skipped
        assert result.status == TradeStatus.SKIPPED
        assert result.correlation_id is not None

        # Verify no position was closed or opened
        mock_components["position_tracker"].close_position.assert_not_called()
        mock_components["position_tracker"].open_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_time_based_position_close(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that positions older than 60 seconds are closed when POC_MODE=true (BURNIN-001 fix).

        This test verifies the burn-in bypass only works when POC_MODE is explicitly enabled.
        The bypass allows time-based closing of old positions for testing purposes.
        """
        import os
        from datetime import UTC, datetime, timedelta

        # Enable POC_MODE for burn-in testing
        os.environ["POC_MODE"] = "true"

        try:
            # Setup: Create an existing LONG position that is OLD (older than 60 seconds)
            old_position = MagicMock()
            old_position.position_id = "old-pos-001"
            old_position.symbol = "BTC/USDT"
            old_position.side = "long"
            old_position.opened_at = datetime.now(UTC) - timedelta(
                seconds=61
            )  # Expired

            # Mock get_open_positions to return the old position
            mock_components["position_tracker"].get_open_positions = AsyncMock(
                return_value=[old_position]
            )
            mock_components["position_tracker"].close_position = AsyncMock(
                return_value=(old_position, 50.0)
            )

            # Process a LONG signal (same direction, but position is old)
            result = await orchestrator.process_signal(mock_signal)

            # Verify old position was closed due to time limit (burn-in bypass)
            mock_components["position_tracker"].close_position.assert_called_once()
            call_args = mock_components["position_tracker"].close_position.call_args
            assert call_args.kwargs["position_id"] == old_position.position_id
        finally:
            # Clean up: reset POC_MODE
            os.environ.pop("POC_MODE", None)

    @pytest.mark.asyncio
    async def test_time_based_position_close_blocked_when_poc_mode_disabled(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that positions older than 60 seconds are NOT closed when POC_MODE=false.

        This test verifies the burn-in bypass is blocked in production (non-POC) mode.
        ST-PAPER-GUARD-001: POC_MODE is the ONLY way to bypass burn-in.
        """
        import os
        from datetime import UTC, datetime, timedelta

        from execution.paper.models import RiskAssessment

        # Ensure POC_MODE is disabled (default for production)
        os.environ["POC_MODE"] = "false"

        try:
            # Setup: Create an existing LONG position that is OLD (older than 60 seconds)
            old_position = MagicMock()
            old_position.position_id = "old-pos-001"
            old_position.symbol = "BTC/USDT"
            old_position.side = "long"
            old_position.opened_at = datetime.now(UTC) - timedelta(
                seconds=61
            )  # Expired

            # Mock get_open_positions to return the old position
            mock_components["position_tracker"].get_open_positions = AsyncMock(
                return_value=[old_position]
            )
            mock_components["position_tracker"].close_position = AsyncMock(
                return_value=(old_position, 50.0)
            )

            # Setup for same-direction signal (should be skipped without burn-in bypass)
            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=RiskAssessment(approved=True, position_size=0.1)
            )

            # Process a LONG signal (same direction as existing position)
            result = await orchestrator.process_signal(mock_signal)

            # Verify old position was NOT closed due to time limit
            # When POC_MODE=false, the burn-in bypass is disabled
            mock_components["position_tracker"].close_position.assert_not_called()

            # Verify new position was NOT opened (same direction signal was skipped)
            mock_components["position_tracker"].open_position.assert_not_called()

            # Verify signal was handled but position unchanged
            assert result.status in (TradeStatus.SKIPPED, TradeStatus.EXECUTED)
        finally:
            # Clean up: reset POC_MODE
            os.environ.pop("POC_MODE", None)

    @pytest.mark.asyncio
    async def test_burn_in_bypass_unreachable_when_poc_mode_unset(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that burn-in bypass is unreachable when POC_MODE is not set.

        This test verifies the default production behavior where burn-in bypass
        is NOT active without explicit POC_MODE=true.
        ST-PAPER-GUARD-001: POC_MODE is the ONLY way to bypass burn-in.
        """
        import os
        from datetime import UTC, datetime, timedelta

        # Ensure POC_MODE is not set
        os.environ.pop("POC_MODE", None)

        # Setup: Create an existing LONG position that is OLD (older than 60 seconds)
        old_position = MagicMock()
        old_position.position_id = "old-pos-001"
        old_position.symbol = "BTC/USDT"
        old_position.side = "long"
        old_position.opened_at = datetime.now(UTC) - timedelta(seconds=61)  # Expired

        # Mock get_open_positions to return the old position
        mock_components["position_tracker"].get_open_positions = AsyncMock(
            return_value=[old_position]
        )
        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(old_position, 50.0)
        )

        # Process a LONG signal (same direction as existing position)
        result = await orchestrator.process_signal(mock_signal)

        # Verify old position was NOT closed due to time limit
        # When POC_MODE is not set (default false), the burn-in bypass is disabled
        mock_components["position_tracker"].close_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_existing_position_opens_new(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that new position is opened when no existing position."""
        from execution.paper.models import RiskAssessment

        # Mock no existing positions
        mock_components["position_tracker"].get_open_positions = AsyncMock(
            return_value=[]
        )

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            order_id="test-order-new-001",
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
        )
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "new-pos-002"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Process signal with no existing position
        result = await orchestrator.process_signal(mock_signal)

        # Verify position was opened
        mock_components["position_tracker"].open_position.assert_called_once()

        # Verify trade was executed
        assert result.status == TradeStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_open_notification_includes_llm_decision(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that open notification includes LLM decision when available."""
        from unittest.mock import patch

        from execution.llm.trade_decision_enhancer import TradeDecision
        from execution.paper.models import RiskAssessment

        # Setup mocks
        orchestrator.trade_notifier = AsyncMock()

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            order_id="test-order-llm-001",
            state=OrderState.FILLED,
            filled_quantity=0.1,
            avg_fill_price=50000.0,
        )
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-llm-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Mock LLM decision
        mock_decision = TradeDecision(
            go_no_go=True,
            confidence=85.0,
            provider="kimi",
            rationale="Test rationale",
            position_size=0.1,
            stop_loss=48000.0,
            take_profit=55000.0,
            risk_recommendation="Test recommendation",
            fallback_used=False,
            latency_ms=100.0,
        )

        # Enable decision enhancer and mock it
        orchestrator.decision_enhancer.enabled = True
        with patch.object(
            orchestrator.decision_enhancer,
            "enhance_decision",
            AsyncMock(return_value=mock_decision),
        ):
            result = await orchestrator.process_signal(mock_signal)

        # Verify trade was executed
        assert result.status == TradeStatus.EXECUTED

        # Verify trade_notifier was called with llm_decision
        orchestrator.trade_notifier.send_trade_open_notification.assert_called_once()
        call_args = orchestrator.trade_notifier.send_trade_open_notification.call_args
        _, kwargs = call_args

        assert "llm_decision" in kwargs
        assert kwargs["llm_decision"]["decision"] == "GO"
        assert kwargs["llm_decision"]["confidence"] == 85.0
        assert kwargs["llm_decision"]["provider"] == "kimi"

    @pytest.mark.asyncio
    async def test_close_notification_includes_llm_decision(
        self, orchestrator, mock_components
    ):
        """Test that close notification includes LLM decision from position metadata."""
        # Setup mocks
        orchestrator.trade_notifier = AsyncMock()

        # Create position with LLM metadata
        mock_position = MagicMock()
        mock_position.position_id = "test-pos-llm-close-001"
        mock_position.symbol = "BTC/USDT"
        mock_position.metadata = {
            "signal_id": "test-signal-llm-001",
            "llm_decision": {
                "decision": "GO",
                "confidence": 90.0,
                "provider": "kimi",
                "rationale": "Test close rationale",
            },
        }

        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 150.0)
        )

        # Call close_position
        result = await orchestrator.close_position("test-pos-llm-close-001", 50000.0)

        # Verify position was closed
        assert result is not None

        # Verify trade_notifier was called with llm_decision
        orchestrator.trade_notifier.send_trade_close_notification.assert_called_once()
        call_args = orchestrator.trade_notifier.send_trade_close_notification.call_args
        _, kwargs = call_args

        assert "llm_decision" in kwargs
        assert kwargs["llm_decision"]["decision"] == "GO"
        assert kwargs["llm_decision"]["confidence"] == 90.0


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


class TestNoneTelemetry:
    """Test orchestrator behavior when telemetry is None (BURNIN-001 fix)."""

    @pytest.fixture
    def orchestrator_none_telemetry(self, mock_components):
        """Create an orchestrator with None telemetry collector."""
        return PaperTradingOrchestrator(
            signal_generator=mock_components["signal_gen"],
            order_simulator=mock_components["order_sim"],
            position_tracker=mock_components["position_tracker"],
            risk_enforcer=mock_components["risk_enforcer"],
            telemetry_collector=None,
            kill_switch=mock_components["kill_switch"],
            portfolio_value=10000.0,
        )

    @pytest.mark.asyncio
    async def test_start_stop_with_none_telemetry(self, orchestrator_none_telemetry):
        """Test orchestrator start/stop does not crash when telemetry is None."""
        # Should not raise AttributeError
        await orchestrator_none_telemetry.start()
        assert orchestrator_none_telemetry._running is True
        assert orchestrator_none_telemetry._processing_task is not None

        await orchestrator_none_telemetry.stop()
        assert orchestrator_none_telemetry._running is False

    @pytest.mark.asyncio
    async def test_process_signal_with_none_telemetry(
        self, orchestrator_none_telemetry, mock_components, mock_signal
    ):
        """Test signal processing works when telemetry is None."""
        from execution.paper.risk_models import RiskAssessment

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=0.1,
            order_id="test-order-none-001",
            state=OrderState.FILLED,
            filled_quantity=0.1,
        )
        # Add a fill to set the avg_fill_price
        from execution.paper.models import PaperFill

        fill = PaperFill(
            fill_id="fill-001",
            order_id="test-order-none-001",
            symbol="BTC/USDT",
            side="buy",
            quantity=0.1,
            price=50000.0,
        )
        filled_order.add_fill(fill)
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-none-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Process signal - should not crash with None telemetry
        result = await orchestrator_none_telemetry.process_signal(mock_signal)

        assert result.status == TradeStatus.EXECUTED
        assert result.order is not None
        assert result.position is not None

    @pytest.mark.asyncio
    async def test_close_position_with_none_telemetry(
        self, orchestrator_none_telemetry, mock_components
    ):
        """Test position closing works when telemetry is None."""
        mock_position = MagicMock()
        mock_position.position_id = "test-pos-none-002"
        mock_position.symbol = "BTC/USDT"

        mock_components["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 150.0)
        )

        initial_value = orchestrator_none_telemetry.portfolio_value
        result = await orchestrator_none_telemetry.close_position(
            "test-pos-none-002", 51000.0
        )

        assert result is not None
        assert result[1] == 150.0
        assert orchestrator_none_telemetry.portfolio_value == initial_value + 150.0


class TestOrderSimulatorInterface:
    """Test that orchestrator calls order_simulator with correct interface (BURNIN-001 fix).

    This test verifies the fix for the interface mismatch where orchestrator
    was passing a PaperOrder object instead of individual parameters.
    """

    @pytest.mark.asyncio
    async def test_process_signal_calls_place_order_with_individual_params(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that place_order is called with individual parameters, not PaperOrder object."""
        from execution.paper.models import RiskAssessment

        # Setup risk enforcer to approve
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        # Create a properly filled order to return
        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=0.1,
            order_id="test-order-interface-001",
            state=OrderState.FILLED,
            filled_quantity=0.1,
        )
        # Add a fill to set avg_fill_price
        from execution.paper.models import PaperFill

        fill = PaperFill(
            fill_id="fill-interface-001",
            order_id="test-order-interface-001",
            symbol="BTC/USDT",
            side="buy",
            quantity=0.1,
            price=50000.0,
        )
        filled_order.add_fill(fill)

        # Track the call arguments
        call_kwargs = {}

        async def capture_call(*args, **kwargs):
            call_kwargs.update(kwargs)
            return filled_order

        mock_components["order_sim"].place_order = AsyncMock(side_effect=capture_call)

        mock_position = MagicMock()
        mock_position.position_id = "test-position-interface-001"
        mock_position.symbol = "BTC/USDT"
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Process signal
        result = await orchestrator.process_signal(mock_signal)

        # Verify the result
        assert result.status == TradeStatus.EXECUTED

        # Verify place_order was called with individual parameters, not PaperOrder
        assert mock_components["order_sim"].place_order.called

        # Verify all required parameters were passed
        assert "symbol" in call_kwargs, "place_order should receive 'symbol' parameter"
        assert "side" in call_kwargs, "place_order should receive 'side' parameter"
        assert (
            "order_type" in call_kwargs
        ), "place_order should receive 'order_type' parameter"
        assert (
            "quantity" in call_kwargs
        ), "place_order should receive 'quantity' parameter"
        assert "price" in call_kwargs, "place_order should receive 'price' parameter"

        # Verify parameter values
        assert call_kwargs["symbol"] == "BTC/USDT"
        assert call_kwargs["side"] == "buy"  # LONG -> buy
        assert call_kwargs["order_type"] == "market"
        assert call_kwargs["quantity"] == 0.1
        # Price should now be set from market data (BURNIN-001 fix)
        assert (
            call_kwargs["price"] == 50000.0
        ), f"Price should be set from market data, got {call_kwargs['price']}"

    @pytest.mark.asyncio
    async def test_process_signal_short_calls_place_order_with_sell_side(
        self, orchestrator, mock_components
    ):
        """Test that SHORT signals result in 'sell' side parameter."""
        from execution.paper.models import RiskAssessment

        # Create a SHORT signal
        short_signal = Signal(
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.85,
            base_score=85.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=3500.0,
            signal_id="test-signal-short-001",
        )

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.5)
        )

        filled_order = PaperOrder(
            symbol="ETH/USDT",
            side="sell",
            order_type="market",
            quantity=0.5,
            order_id="test-order-short-001",
            state=OrderState.FILLED,
            filled_quantity=0.5,
        )
        from execution.paper.models import PaperFill

        fill = PaperFill(
            fill_id="fill-short-001",
            order_id="test-order-short-001",
            symbol="ETH/USDT",
            side="sell",
            quantity=0.5,
            price=3000.0,
        )
        filled_order.add_fill(fill)

        call_kwargs = {}

        async def capture_call(*args, **kwargs):
            call_kwargs.update(kwargs)
            return filled_order

        mock_components["order_sim"].place_order = AsyncMock(side_effect=capture_call)
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        result = await orchestrator.process_signal(short_signal)

        assert result.status == TradeStatus.EXECUTED
        assert (
            call_kwargs["side"] == "sell"
        ), "SHORT signals should result in 'sell' side"
        assert call_kwargs["symbol"] == "ETH/USDT"
        assert call_kwargs["quantity"] == 0.5


class TestOrderPriceValidation:
    """Test order price validation and value calculation (BURNIN-001 fix).

    These tests verify that:
    1. Entry price is retrieved from market data before validation
    2. Price is passed to validate_order() and _create_order()
    3. Order value is calculated correctly (non-zero)
    4. Orders are rejected when no valid price is available
    """

    @pytest.mark.asyncio
    async def test_order_created_with_valid_price(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that PaperOrder is created with a valid price."""
        from execution.paper.models import RiskAssessment

        # Setup market price
        mock_components["order_sim"].market_data.get_price = MagicMock(
            return_value=50000.0
        )

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=0.1)
        )

        # Capture the order that is created
        created_order = None

        async def capture_place_order(*args, **kwargs):
            nonlocal created_order
            # Create the order that would be returned
            from execution.paper.models import PaperFill

            order = PaperOrder(
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs["order_type"],
                quantity=kwargs["quantity"],
                price=kwargs.get("price"),
                order_id="test-order-price-001",
                state=OrderState.FILLED,
                filled_quantity=kwargs["quantity"],
            )
            # Add a fill
            fill = PaperFill(
                fill_id="fill-price-001",
                order_id="test-order-price-001",
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                quantity=kwargs["quantity"],
                price=50000.0,
            )
            order.add_fill(fill)
            created_order = order
            return order

        mock_components["order_sim"].place_order = AsyncMock(
            side_effect=capture_place_order
        )
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        result = await orchestrator.process_signal(mock_signal)

        # Verify order was created with correct price
        assert result.status == TradeStatus.EXECUTED
        assert created_order is not None
        assert (
            created_order.price == 50000.0
        ), f"Expected price=50000.0, got {created_order.price}"

    @pytest.mark.asyncio
    async def test_validate_order_receives_entry_price(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that validate_order is called with entry_price parameter."""
        from execution.paper.models import RiskAssessment

        expected_price = 55000.0
        mock_components["order_sim"].market_data.get_price = MagicMock(
            return_value=expected_price
        )

        call_kwargs = {}

        async def capture_validate(*args, **kwargs):
            call_kwargs.update(kwargs)
            return RiskAssessment(approved=True, position_size=0.1)

        mock_components["risk_enforcer"].validate_order = AsyncMock(
            side_effect=capture_validate
        )

        filled_order = PaperOrder(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=0.1,
            price=expected_price,
            order_id="test-order-price-002",
            state=OrderState.FILLED,
            filled_quantity=0.1,
        )
        from execution.paper.models import PaperFill

        fill = PaperFill(
            fill_id="fill-price-002",
            order_id="test-order-price-002",
            symbol="BTC/USDT",
            side="buy",
            quantity=0.1,
            price=expected_price,
        )
        filled_order.add_fill(fill)
        mock_components["order_sim"].place_order = AsyncMock(return_value=filled_order)
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        result = await orchestrator.process_signal(mock_signal)

        assert result.status == TradeStatus.EXECUTED
        assert (
            "entry_price" in call_kwargs
        ), "validate_order should receive 'entry_price' parameter"
        assert (
            call_kwargs["entry_price"] == expected_price
        ), f"Expected entry_price={expected_price}, got {call_kwargs.get('entry_price')}"

    @pytest.mark.asyncio
    async def test_order_rejected_when_no_market_price(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that order is rejected when no market price is available."""
        # Mock no price available
        mock_components["order_sim"].market_data.get_price = MagicMock(
            return_value=None
        )

        result = await orchestrator.process_signal(mock_signal)

        # Should be rejected due to no price
        assert result.status == TradeStatus.REJECTED
        assert any("market price" in reason.lower() for reason in result.reject_reason)

        # Should not have called risk enforcer or placed order
        mock_components["risk_enforcer"].validate_order.assert_not_called()
        mock_components["order_sim"].place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_order_rejected_when_price_is_zero(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that order is rejected when market price is zero."""
        # Mock zero price
        mock_components["order_sim"].market_data.get_price = MagicMock(return_value=0.0)

        result = await orchestrator.process_signal(mock_signal)

        # Should be rejected due to invalid price
        assert result.status == TradeStatus.REJECTED
        assert any("market price" in reason.lower() for reason in result.reject_reason)

    @pytest.mark.asyncio
    async def test_order_rejected_when_price_is_negative(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that order is rejected when market price is negative."""
        # Mock negative price (edge case)
        mock_components["order_sim"].market_data.get_price = MagicMock(
            return_value=-100.0
        )

        result = await orchestrator.process_signal(mock_signal)

        # Should be rejected due to invalid price
        assert result.status == TradeStatus.REJECTED
        assert any("market price" in reason.lower() for reason in result.reject_reason)

    @pytest.mark.asyncio
    async def test_order_value_calculated_correctly(
        self, orchestrator, mock_components, mock_signal
    ):
        """Test that order notional value is calculated correctly (price * quantity)."""
        from execution.paper.models import RiskAssessment

        price = 50000.0
        quantity = 0.1
        expected_value = price * quantity  # $5,000

        mock_components["order_sim"].market_data.get_price = MagicMock(
            return_value=price
        )
        mock_components["risk_enforcer"].validate_order = AsyncMock(
            return_value=RiskAssessment(approved=True, position_size=quantity)
        )

        # Capture the placed order parameters
        call_kwargs = {}

        async def capture_call(*args, **kwargs):
            call_kwargs.update(kwargs)
            order = PaperOrder(
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs["order_type"],
                quantity=kwargs["quantity"],
                price=kwargs.get("price"),
                order_id="test-order-value-001",
                state=OrderState.FILLED,
                filled_quantity=kwargs["quantity"],
            )
            from execution.paper.models import PaperFill

            fill = PaperFill(
                fill_id="fill-value-001",
                order_id="test-order-value-001",
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                quantity=kwargs["quantity"],
                price=price,
            )
            order.add_fill(fill)
            return order

        mock_components["order_sim"].place_order = AsyncMock(side_effect=capture_call)
        mock_components["position_tracker"].open_position = AsyncMock(
            return_value=MagicMock()
        )

        result = await orchestrator.process_signal(mock_signal)

        assert result.status == TradeStatus.EXECUTED
        assert call_kwargs["price"] == price
        assert call_kwargs["quantity"] == quantity
        # Verify notional value would be correct
        notional_value = call_kwargs["price"] * call_kwargs["quantity"]
        assert (
            notional_value == expected_value
        ), f"Expected value=${expected_value}, got ${notional_value}"

    @pytest.mark.asyncio
    async def test_create_order_raises_on_invalid_price(
        self, orchestrator, mock_signal
    ):
        """Test that _create_order raises ValueError when price is invalid."""
        with pytest.raises(ValueError) as exc_info:
            orchestrator._create_order(
                signal=mock_signal,
                position_size=0.1,
                entry_price=0.0,  # Invalid price
                correlation_id="test-corr-invalid",
            )
        assert "Entry price must be positive" in str(exc_info.value)

    def test_create_order_succeeds_with_valid_price(self, orchestrator, mock_signal):
        """Test that _create_order succeeds with valid price and sets it on order."""
        valid_price = 50000.0

        order = orchestrator._create_order(
            signal=mock_signal,
            position_size=0.1,
            entry_price=valid_price,
            correlation_id="test-corr-valid",
        )

        assert (
            order.price == valid_price
        ), f"Expected price={valid_price}, got {order.price}"
        assert order.quantity == 0.1
        assert order.symbol == mock_signal.token


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
