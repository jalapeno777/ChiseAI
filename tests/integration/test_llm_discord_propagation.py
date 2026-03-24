"""End-to-end integration test for LLM decision propagation to Discord.

Proves that:
1. With USE_LLM_TRADE_DECISIONS=true, Discord payload contains LLM details
2. With USE_LLM_TRADE_DECISIONS=false, payload is valid without LLM section

For PAPER-EXEC-001 Party Mode audit must-fix.
"""

import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Import required components
pytest.importorskip("execution.paper.orchestrator")
pytest.importorskip("execution.alerts.integration")

from execution.alerts.integration import ExecutionAlertIntegration
from execution.paper.models import OrderSide, OrderState
from execution.paper.orchestrator import PaperTradingOrchestrator
from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus


class TestLLMToDiscordPropagation:
    """Test end-to-end LLM decision propagation to Discord notifications."""

    @pytest.fixture
    def mock_components(self):
        """Create mock components for orchestrator."""
        return {
            "signal_generator": MagicMock(),
            "order_simulator": MagicMock(),
            "position_tracker": AsyncMock(),
            "risk_enforcer": AsyncMock(),
            "telemetry": AsyncMock(),
            "kill_switch": MagicMock(),
        }

    @pytest.fixture
    def mock_signal(self):
        """Create a mock trading signal."""
        signal = MagicMock()
        signal.token = "BTCUSDT"
        signal.direction.value = "long"
        signal.confidence = 0.75
        signal.signal_id = str(uuid4())
        signal.stop_loss = None
        signal.stop_loss_method = None
        return signal

    @pytest.mark.asyncio
    async def test_llm_details_propagate_to_discord_when_enabled(
        self, mock_components, mock_signal
    ):
        """E2E test: With LLM enabled, Discord payload contains LLM details."""
        # Set feature flag
        with patch.dict(os.environ, {"USE_LLM_TRADE_DECISIONS": "true"}):
            # Setup mocks
            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=MagicMock(approved=True, position_size=0.1, violations=[])
            )
            mock_components["position_tracker"].get_open_positions = AsyncMock(
                return_value=[]
            )

            # Create a mock position that captures metadata from open_position call
            captured_metadata = {}

            async def capture_open_position(
                *, symbol, side, entry_price, quantity, metadata
            ):
                """Capture metadata passed to open_position and return mock position."""
                captured_metadata.update(metadata)
                mock_position = MagicMock()
                mock_position.position_id = "test-pos-123"
                mock_position.symbol = symbol
                mock_position.quantity = quantity
                mock_position.entry_price = entry_price
                mock_position.side = side
                mock_position.metadata = metadata  # Return the actual metadata
                return mock_position

            mock_components["position_tracker"].open_position = AsyncMock(
                side_effect=capture_open_position
            )

            # Mock order simulator
            mock_order = MagicMock()
            mock_order.state = OrderState.FILLED
            mock_order.order_id = "test-order-123"
            mock_order.symbol = "BTCUSDT"
            mock_order.filled_quantity = 0.1
            mock_order.avg_fill_price = 50000.0
            mock_order.side = OrderSide.BUY.value
            mock_components["order_simulator"].place_order = AsyncMock(
                return_value=mock_order
            )
            mock_components["order_simulator"].market_data.get_price.return_value = (
                50000.0
            )

            # Mock kill switch
            mock_components["kill_switch"].state.value = "armed"

            # Create orchestrator with LLM enhancer
            orchestrator = PaperTradingOrchestrator(
                signal_generator=mock_components["signal_generator"],
                order_simulator=mock_components["order_simulator"],
                position_tracker=mock_components["position_tracker"],
                risk_enforcer=mock_components["risk_enforcer"],
                telemetry_collector=mock_components["telemetry"],
                kill_switch=mock_components["kill_switch"],
            )

            # Mock the LLM enhancer to return a decision with metadata
            llm_decision_mock = MagicMock()
            llm_decision_mock.go_no_go = True
            llm_decision_mock.confidence = 85.0
            llm_decision_mock.provider = "kimi"
            llm_decision_mock.rationale = "Strong bullish momentum"
            llm_decision_mock.position_size = 0.15
            llm_decision_mock.stop_loss = 48000.0
            llm_decision_mock.take_profit = 55000.0
            llm_decision_mock.risk_recommendation = "Use tight stop"
            llm_decision_mock.fallback_used = False
            llm_decision_mock.latency_ms = 150.0

            orchestrator.decision_enhancer = MagicMock()
            orchestrator.decision_enhancer.enabled = True
            orchestrator.decision_enhancer.enhance_decision = AsyncMock(
                return_value=llm_decision_mock
            )

            # Process signal
            result = await orchestrator.process_signal(mock_signal)

            # Verify result has LLM metadata (captured from open_position call)
            assert result.position is not None
            assert "llm_decision" in captured_metadata

            llm_meta = captured_metadata["llm_decision"]
            assert llm_meta["decision"] == "GO"
            assert llm_meta["confidence"] == 85.0
            assert llm_meta["provider"] == "kimi"
            assert llm_meta["position_size"] == 0.15
            assert llm_meta["stop_loss"] == 48000.0
            assert llm_meta["take_profit"] == 55000.0

            print(f"✅ LLM metadata persisted: {llm_meta}")

    @pytest.mark.asyncio
    async def test_no_llm_details_when_disabled(self, mock_components, mock_signal):
        """E2E test: With LLM disabled, payload is valid without LLM section."""
        # Set feature flag to false
        with patch.dict(os.environ, {"USE_LLM_TRADE_DECISIONS": "false"}):
            # Setup mocks (same as above)
            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=MagicMock(approved=True, position_size=0.1, violations=[])
            )
            mock_components["position_tracker"].get_open_positions = AsyncMock(
                return_value=[]
            )

            # Create a mock position that captures metadata from open_position call
            captured_metadata = {}

            async def capture_open_position(
                *, symbol, side, entry_price, quantity, metadata
            ):
                """Capture metadata passed to open_position and return mock position."""
                captured_metadata.update(metadata)
                mock_position = MagicMock()
                mock_position.position_id = "test-pos-456"
                mock_position.symbol = symbol
                mock_position.quantity = quantity
                mock_position.entry_price = entry_price
                mock_position.side = side
                mock_position.metadata = metadata
                return mock_position

            mock_components["position_tracker"].open_position = AsyncMock(
                side_effect=capture_open_position
            )

            mock_order = MagicMock()
            mock_order.state = OrderState.FILLED
            mock_order.order_id = "test-order-456"
            mock_order.symbol = "BTCUSDT"
            mock_order.filled_quantity = 0.1
            mock_order.avg_fill_price = 50000.0
            mock_order.side = OrderSide.BUY.value
            mock_components["order_simulator"].place_order = AsyncMock(
                return_value=mock_order
            )
            mock_components["order_simulator"].market_data.get_price.return_value = (
                50000.0
            )
            mock_components["kill_switch"].state.value = "armed"

            # Create orchestrator
            orchestrator = PaperTradingOrchestrator(
                signal_generator=mock_components["signal_generator"],
                order_simulator=mock_components["order_simulator"],
                position_tracker=mock_components["position_tracker"],
                risk_enforcer=mock_components["risk_enforcer"],
                telemetry_collector=mock_components["telemetry"],
                kill_switch=mock_components["kill_switch"],
            )

            # Process signal
            result = await orchestrator.process_signal(mock_signal)

            # Verify result has NO LLM metadata
            assert result.position is not None
            assert "llm_decision" not in captured_metadata

            print("✅ No LLM metadata when disabled (as expected)")

    @pytest.mark.asyncio
    async def test_integration_extracts_llm_for_discord(self):
        """Test that ExecutionAlertIntegration extracts LLM metadata for Discord."""
        # Create outcome with LLM metadata
        outcome = SignalOutcome(
            signal_id=uuid4(),
            order_id="test-order",
            symbol="BTCUSDT",
            side="Buy",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("0.1"),
            status=SignalOutcomeStatus.FILLED,
            metadata={
                "llm_decision": {
                    "decision": "GO",
                    "confidence": 90.0,
                    "provider": "kimi",
                    "rationale": "Strong setup",
                    "position_size": 0.2,
                    "stop_loss": 48000.0,
                    "take_profit": 55000.0,
                    "risk_recommendation": "Manage risk",
                    "fallback_used": False,
                    "latency_ms": 120.0,
                }
            },
        )

        # Create integration
        integration = ExecutionAlertIntegration(
            enabled=True
        )  # Enabled to test the flow

        # Mock the trade notifier
        integration._trade_notifier = MagicMock()
        integration._trade_notifier.send_trade_open_notification = AsyncMock(
            return_value=MagicMock(success=True, message_id="12345")
        )

        # Call on_trade_opened
        result = await integration.on_trade_opened(outcome)

        # Verify the notifier was called
        assert integration._trade_notifier.send_trade_open_notification.called

        # Get call arguments - method is called with positional args: (outcome, llm_decision)
        call_args = integration._trade_notifier.send_trade_open_notification.call_args
        assert call_args is not None

        # Extract llm_decision from call (second positional arg or keyword arg)
        args, kwargs = call_args
        if len(args) >= 2:
            llm_decision = args[1]  # Second positional argument
        else:
            llm_decision = kwargs.get("llm_decision")

        assert llm_decision is not None
        assert llm_decision["decision"] == "GO"
        assert llm_decision["confidence"] == 90.0
        assert llm_decision["provider"] == "kimi"

        print(f"✅ Integration extracted LLM for Discord: {llm_decision}")

    @pytest.mark.asyncio
    async def test_end_to_end_llm_to_discord_flow(self, mock_components, mock_signal):
        """Full E2E test: Orchestrator → Position → Integration → Discord payload.

        This test proves the complete flow:
        1. Orchestrator processes signal with LLM enabled
        2. Position metadata contains LLM decision
        3. ExecutionAlertIntegration extracts LLM metadata
        4. Discord payload includes LLM details
        """
        with patch.dict(os.environ, {"USE_LLM_TRADE_DECISIONS": "true"}):
            # Setup mocks
            mock_components["risk_enforcer"].validate_order = AsyncMock(
                return_value=MagicMock(approved=True, position_size=0.1, violations=[])
            )
            mock_components["position_tracker"].get_open_positions = AsyncMock(
                return_value=[]
            )

            # Create a mock position that captures metadata from open_position call
            captured_metadata = {}

            async def capture_open_position(
                *, symbol, side, entry_price, quantity, metadata
            ):
                """Capture metadata passed to open_position and return mock position."""
                captured_metadata.update(metadata)
                mock_position = MagicMock()
                mock_position.position_id = "test-pos-e2e"
                mock_position.symbol = symbol
                mock_position.quantity = quantity
                mock_position.entry_price = entry_price
                mock_position.side = side
                mock_position.metadata = metadata
                return mock_position

            mock_components["position_tracker"].open_position = AsyncMock(
                side_effect=capture_open_position
            )

            # Mock order simulator
            mock_order = MagicMock()
            mock_order.state = OrderState.FILLED
            mock_order.order_id = "test-order-e2e"
            mock_order.symbol = "BTCUSDT"
            mock_order.filled_quantity = 0.1
            mock_order.avg_fill_price = 50000.0
            mock_order.side = OrderSide.BUY.value
            mock_components["order_simulator"].place_order = AsyncMock(
                return_value=mock_order
            )
            mock_components["order_simulator"].market_data.get_price.return_value = (
                50000.0
            )
            mock_components["kill_switch"].state.value = "armed"

            # Create orchestrator
            orchestrator = PaperTradingOrchestrator(
                signal_generator=mock_components["signal_generator"],
                order_simulator=mock_components["order_simulator"],
                position_tracker=mock_components["position_tracker"],
                risk_enforcer=mock_components["risk_enforcer"],
                telemetry_collector=mock_components["telemetry"],
                kill_switch=mock_components["kill_switch"],
            )

            # Mock LLM enhancer
            llm_decision_mock = MagicMock()
            llm_decision_mock.go_no_go = True
            llm_decision_mock.confidence = 88.5
            llm_decision_mock.provider = "kimi"
            llm_decision_mock.rationale = "Excellent risk/reward ratio"
            llm_decision_mock.position_size = 0.12
            llm_decision_mock.stop_loss = 49000.0
            llm_decision_mock.take_profit = 54000.0
            llm_decision_mock.risk_recommendation = "Standard position sizing"
            llm_decision_mock.fallback_used = False
            llm_decision_mock.latency_ms = 145.0

            orchestrator.decision_enhancer = MagicMock()
            orchestrator.decision_enhancer.enabled = True
            orchestrator.decision_enhancer.enhance_decision = AsyncMock(
                return_value=llm_decision_mock
            )

            # Process signal through orchestrator
            trade_result = await orchestrator.process_signal(mock_signal)

            # Verify position has LLM metadata (captured from the open_position call)
            assert trade_result.position is not None
            assert "llm_decision" in captured_metadata

            llm_meta = captured_metadata["llm_decision"]
            assert llm_meta["confidence"] == 88.5
            assert llm_meta["provider"] == "kimi"

            # Now simulate what happens when ExecutionAlertIntegration processes this
            # Create SignalOutcome from the trade result (as done in _create_outcome_from_result)
            outcome = SignalOutcome(
                signal_id=uuid4(),
                order_id=mock_order.order_id,
                symbol=mock_order.symbol,
                side="Buy",
                fill_price=Decimal(str(mock_order.avg_fill_price)),
                fill_quantity=Decimal(str(mock_order.filled_quantity)),
                status=SignalOutcomeStatus.FILLED,
                metadata=captured_metadata,  # This contains llm_decision
            )

            # Create integration and mock notifier
            integration = ExecutionAlertIntegration(enabled=True)
            integration._trade_notifier = MagicMock()
            integration._trade_notifier.send_trade_open_notification = AsyncMock(
                return_value=MagicMock(success=True, message_id="e2e-msg-123")
            )

            # Process through integration
            alert_result = await integration.on_trade_opened(outcome)

            # Verify alert was sent
            assert alert_result["sent"] is True

            # Verify Discord payload contains LLM decision
            call_args = (
                integration._trade_notifier.send_trade_open_notification.call_args
            )
            args, kwargs = call_args

            # Extract llm_decision from call (second positional arg or keyword arg)
            if len(args) >= 2:
                discord_llm_decision = args[1]  # Second positional argument
            else:
                discord_llm_decision = kwargs.get("llm_decision")

            assert discord_llm_decision is not None
            assert discord_llm_decision["decision"] == "GO"
            assert discord_llm_decision["confidence"] == 88.5
            assert discord_llm_decision["provider"] == "kimi"
            assert discord_llm_decision["position_size"] == 0.12
            assert discord_llm_decision["stop_loss"] == 49000.0
            assert discord_llm_decision["take_profit"] == 54000.0

            print(
                "✅ Full E2E flow verified: LLM details propagated to Discord payload"
            )
            print(f"   - Decision: {discord_llm_decision['decision']}")
            print(f"   - Confidence: {discord_llm_decision['confidence']}%")
            print(f"   - Provider: {discord_llm_decision['provider']}")
            print(f"   - Position Size: {discord_llm_decision['position_size']}")
