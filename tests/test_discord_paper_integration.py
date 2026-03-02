"""Test Discord integration with paper trading orchestrator.

Tests that trade open/close alerts are sent to Discord when
positions are opened and closed in the paper trading flow.

For P0-REPAIR-001: Discord Integration Repair
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    pass


# Set test environment variables
os.environ.setdefault("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
os.environ.setdefault("DISCORD_TRADING_CHANNEL_ID", "1444447985378398459")


@pytest.fixture
def mock_signal():
    """Create a mock trading signal."""
    signal = MagicMock()
    signal.signal_id = str(uuid4())
    signal.token = "BTC"
    signal.direction.value = "long"
    signal.stop_loss = 40000.0
    signal.stop_loss_method = "atr"
    signal.confidence = 0.85
    return signal


@pytest.fixture
def mock_filled_order():
    """Create a mock filled order."""
    order = MagicMock()
    order.order_id = str(uuid4())
    order.symbol = "BTCUSDT"
    order.avg_fill_price = 45000.0
    order.filled_quantity = 0.1
    return order


@pytest.fixture
def mock_position():
    """Create a mock paper position."""
    position = MagicMock()
    position.position_id = str(uuid4())
    position.symbol = "BTCUSDT"
    position.side = "long"
    position.entry_price = 45000.0
    position.quantity = 0.1
    position.opened_at = datetime.now(UTC)
    position.closed_at = None
    position.metadata = {
        "signal_id": str(uuid4()),
        "order_id": str(uuid4()),
        "correlation_id": str(uuid4()),
    }
    return position


class TestDiscordIntegration:
    """Test Discord notification integration with paper trading."""

    @pytest.mark.asyncio
    async def test_trade_open_notification_sent(
        self, mock_signal, mock_filled_order, mock_position
    ):
        """Test that trade open notification is sent when position is opened."""
        from discord_alerts.trade_notifier import TradeNotificationResult, TradeNotifier
        from execution.paper.orchestrator import PaperTradingOrchestrator

        # Create mock notifier
        mock_notifier = MagicMock(spec=TradeNotifier)
        mock_notifier.create_outcome_from_paper_position = MagicMock()
        mock_notifier.send_trade_open_notification = AsyncMock()
        mock_notifier.send_trade_open_notification.return_value = (
            TradeNotificationResult(
                success=True,
                message_id="1234567890123456789",
                timestamp=datetime.now(UTC),
            )
        )

        # Create mock components
        mock_signal_gen = MagicMock()
        mock_order_sim = MagicMock()
        mock_position_tracker = MagicMock()
        mock_position_tracker.open_position = AsyncMock(return_value=mock_position)
        mock_risk_enforcer = MagicMock()
        mock_telemetry = MagicMock()
        mock_kill_switch = MagicMock()
        mock_kill_switch.state.value = "armed"

        # Create orchestrator with mock notifier
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_gen,
            order_simulator=mock_order_sim,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            portfolio_value=10000.0,
            trade_notifier=mock_notifier,
        )

        # Call _open_position
        correlation_id = str(uuid4())
        position = await orchestrator._open_position(
            filled_order=mock_filled_order,
            signal=mock_signal,
            correlation_id=correlation_id,
        )

        # Verify notification was sent
        mock_notifier.create_outcome_from_paper_position.assert_called_once()
        mock_notifier.send_trade_open_notification.assert_called_once()

        # Verify the outcome was created with correct parameters
        call_args = mock_notifier.create_outcome_from_paper_position.call_args
        assert call_args.kwargs["position"] == mock_position
        assert call_args.kwargs["order"] == mock_filled_order
        assert call_args.kwargs["signal_id"] == mock_signal.signal_id

        print("✓ Trade open notification sent successfully")
        print(
            f"  Message ID: {mock_notifier.send_trade_open_notification.return_value.message_id}"
        )

    @pytest.mark.asyncio
    async def test_trade_close_notification_sent(self, mock_position):
        """Test that trade close notification is sent when position is closed."""
        from discord_alerts.trade_notifier import TradeNotificationResult, TradeNotifier
        from execution.paper.orchestrator import PaperTradingOrchestrator

        # Create mock notifier
        mock_notifier = MagicMock(spec=TradeNotifier)
        mock_notifier.create_outcome_from_paper_position = MagicMock()
        mock_notifier.send_trade_close_notification = AsyncMock()
        mock_notifier.send_trade_close_notification.return_value = (
            TradeNotificationResult(
                success=True,
                message_id="9876543210987654321",
                timestamp=datetime.now(UTC),
            )
        )

        # Create closed position mock
        closed_position = MagicMock()
        closed_position.position_id = mock_position.position_id
        closed_position.symbol = "BTCUSDT"
        closed_position.side = "long"
        closed_position.entry_price = 45000.0
        closed_position.quantity = 0.1
        closed_position.metadata = mock_position.metadata
        closed_position.closed_at = datetime.now(UTC)

        # Create mock position tracker that returns async result
        from execution.paper.position_tracker import PaperPositionTracker

        mock_position_tracker = AsyncMock(spec=PaperPositionTracker)
        mock_position_tracker.close_position = AsyncMock(
            return_value=(closed_position, 150.0)
        )

        # Create mock components
        mock_signal_gen = MagicMock()
        mock_order_sim = MagicMock()
        mock_risk_enforcer = MagicMock()
        mock_telemetry = MagicMock()
        mock_kill_switch = MagicMock()

        # Create orchestrator with mock notifier
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_gen,
            order_simulator=mock_order_sim,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            portfolio_value=10000.0,
            trade_notifier=mock_notifier,
        )

        # Call close_position
        exit_price = 46500.0
        result = await orchestrator.close_position(
            position_id=mock_position.position_id,
            exit_price=exit_price,
            reason="test",
        )

        # Verify notification was sent
        assert result is not None
        mock_notifier.create_outcome_from_paper_position.assert_called_once()
        mock_notifier.send_trade_close_notification.assert_called_once()

        # Verify the outcome was created with correct parameters
        call_args = mock_notifier.create_outcome_from_paper_position.call_args
        assert call_args.kwargs["pnl"] == 150.0
        assert call_args.kwargs["exit_price"] == exit_price

        print("✓ Trade close notification sent successfully")
        print(
            f"  Message ID: {mock_notifier.send_trade_close_notification.return_value.message_id}"
        )
        print("  Realized PnL: $150.00")

    @pytest.mark.asyncio
    async def test_notification_graceful_failure(
        self, mock_signal, mock_filled_order, mock_position
    ):
        """Test that notification failures don't break the trading flow."""
        from discord_alerts.trade_notifier import TradeNotificationResult, TradeNotifier
        from execution.paper.orchestrator import PaperTradingOrchestrator

        # Create mock notifier that fails
        mock_notifier = MagicMock(spec=TradeNotifier)
        mock_notifier.create_outcome_from_paper_position = MagicMock()
        mock_notifier.send_trade_open_notification = AsyncMock()
        mock_notifier.send_trade_open_notification.return_value = (
            TradeNotificationResult(
                success=False,
                error="Discord webhook error: HTTP 500",
            )
        )

        # Create mock components
        mock_signal_gen = MagicMock()
        mock_order_sim = MagicMock()
        mock_position_tracker = MagicMock()
        mock_position_tracker.open_position = AsyncMock(return_value=mock_position)
        mock_risk_enforcer = MagicMock()
        mock_telemetry = MagicMock()
        mock_kill_switch = MagicMock()
        mock_kill_switch.state.value = "armed"

        # Create orchestrator with mock notifier
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_gen,
            order_simulator=mock_order_sim,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            portfolio_value=10000.0,
            trade_notifier=mock_notifier,
        )

        # Call _open_position - should not raise even if notification fails
        correlation_id = str(uuid4())
        position = await orchestrator._open_position(
            filled_order=mock_filled_order,
            signal=mock_signal,
            correlation_id=correlation_id,
        )

        # Position should still be returned even if notification failed
        assert position == mock_position
        mock_notifier.send_trade_open_notification.assert_called_once()

        print("✓ Notification failure handled gracefully")
        print("  Position still opened despite Discord error")


class TestSignalOutcomeFactory:
    """Test the SignalOutcome factory method."""

    def test_create_outcome_from_open_position(self, mock_position):
        """Test creating SignalOutcome from an open position."""
        from discord_alerts.trade_notifier import TradeNotifier
        from ml.models.signal_outcome import SignalOutcomeStatus

        outcome = TradeNotifier.create_outcome_from_paper_position(
            position=mock_position,
            signal_id=mock_position.metadata["signal_id"],
        )

        # Check outcome attributes (avoid isinstance check due to import path issues)
        assert hasattr(outcome, "symbol")
        assert outcome.symbol == "BTCUSDT"
        assert outcome.direction == "LONG"
        assert outcome.side == "Buy"
        assert outcome.entry_price == Decimal("45000.0")
        assert outcome.position_size == Decimal("0.1")
        assert outcome.status == SignalOutcomeStatus.FILLED
        assert outcome.pnl is None
        assert outcome.exit_price is None

        print("✓ SignalOutcome created from open position")
        print(f"  Symbol: {outcome.symbol}")
        print(f"  Direction: {outcome.direction}")
        print(f"  Entry Price: ${outcome.entry_price}")

    def test_create_outcome_from_closed_position(self, mock_position):
        """Test creating SignalOutcome from a closed position."""
        from discord_alerts.trade_notifier import TradeNotifier
        from ml.models.signal_outcome import SignalOutcomeStatus

        mock_position.closed_at = datetime.now(UTC)

        outcome = TradeNotifier.create_outcome_from_paper_position(
            position=mock_position,
            signal_id=mock_position.metadata["signal_id"],
            pnl=150.0,
            exit_price=46500.0,
        )

        # Check outcome attributes (avoid isinstance check due to import path issues)
        assert hasattr(outcome, "status")
        assert outcome.status == SignalOutcomeStatus.CLOSED
        assert outcome.pnl == Decimal("150.0")
        assert outcome.exit_price == Decimal("46500.0")

        print("✓ SignalOutcome created from closed position")
        print(f"  Status: {outcome.status.value}")
        print(f"  PnL: ${outcome.pnl}")
        print(f"  Exit Price: ${outcome.exit_price}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
