"""Tests for Discord LLM decision details in notifications.

Tests that LLM decision details are properly included in trade open/close
notifications when available, and that notifications remain backward compatible
when LLM details are not available.
"""

import pytest
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from discord_alerts.trade_notifier import TradeNotifier
from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus


@pytest.fixture
def trade_notifier():
    """Create TradeNotifier instance for testing."""
    return TradeNotifier(
        webhook_url="https://discord.com/api/webhooks/test",
        trading_channel_id="1234567890",
        max_retries=0,  # Disable retries in tests
    )


@pytest.fixture
def sample_outcome_open():
    """Create sample SignalOutcome for open trade."""
    return SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id="order-123",
        symbol="BTCUSDT",
        side="Buy",
        direction="LONG",
        fill_price=Decimal("50000.00"),
        fill_quantity=Decimal("0.0"),
        entry_price=Decimal("50000.00"),
        position_size=Decimal("1.1"),
        status=SignalOutcomeStatus.FILLED,
        entry_time=datetime.now(UTC),
    )


@pytest.fixture
def sample_outcome_closed():
    """Create sample SignalOutcome for closed trade."""
    return SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id="order-456",
        symbol="ETHUSDT",
        side="Sell",
        direction="SHORT",
        fill_price=Decimal("3000.00"),
        fill_quantity=Decimal("5.0"),
        entry_price=Decimal("3100.00"),
        exit_price=Decimal("3000.00"),
        position_size=Decimal("5.0"),
        status=SignalOutcomeStatus.CLOSED,
        pnl=Decimal("500.00"),
        entry_time=datetime.now(UTC),
        exit_time=datetime.now(UTC),
    )


@pytest.fixture
def sample_llm_decision_open():
    """Create sample LLM decision for open trade."""
    return {
        "decision": "GO",
        "confidence": 85,
        "provider": "claude-3-5-sonnet",
        "rationale": "Strong bullish momentum with high volume confirmation. RSI shows oversold conditions.",
        "position_size": "1.5 BTC",
        "stop_loss": 48000.00,
        "take_profit": 55000.00,
    }


@pytest.fixture
def sample_llm_decision_close():
    """Create sample LLM decision for closed trade."""
    return {
        "decision": "GO",
        "confidence": 85,
        "provider": "claude-3-5-sonnet",
        "rationale": "Target profit reached as predicted.",
        "exit_reason": "Take profit hit",
        "realized_pnl": 500.00,
    }


class TestTradeOpenNotificationWithLLM:
    """Test trade open notifications with LLM decision details."""

    @pytest.mark.asyncio
    async def test_open_notification_with_llm_details(
        self, trade_notifier, sample_outcome_open, sample_llm_decision_open
    ):
        """Test that open notification includes all LLM fields."""
        with patch.object(trade_notifier, "_send_webhook", autospec=True) as mock_send:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message_id = "msg-123"
            mock_send.return_value = mock_result
            trade_notifier._send_webhook = mock_send

            result = await trade_notifier.send_trade_open_notification(
                sample_outcome_open, sample_llm_decision_open
            )

            # Verify webhook was called
            assert mock_send.called

            # Get the embed from the call
            call_args = mock_send.call_args
            payload = call_args[0][0]
            embed = payload["embeds"][0]

            # Verify LLM fields are in embed
            fields = {f["name"]: f["value"] for f in embed["fields"]}

            # Check separator
            assert "━━━ LLM Decision Details ━━━" in fields

            # Check LLM decision and confidence
            assert "🤖 LLM Decision" in fields
            assert "GO" in fields["🤖 LLM Decision"]
            assert "85%" in fields["🤖 LLM Decision"]

            # Check provider
            assert "🔧 Provider" in fields
            assert "claude-3-5-sonnet" in fields["🔧 Provider"]

            # Check rationale
            assert "💭 Rationale" in fields

            # Check position size
            assert "📏 Recommended Size" in fields
            assert "1.5 BTC" in fields["📏 Recommended Size"]

            # Check stop loss
            assert "🛑 Stop Loss" in fields
            assert "$48,000.00" in fields["🛑 Stop Loss"]

            # Check take profit
            assert "🎯 Take Profit" in fields
            assert "$55,000.00" in fields["🎯 Take Profit"]

            # Verify result success
            assert result.success

    @pytest.mark.asyncio
    async def test_open_notification_without_llm_details(
        self, trade_notifier, sample_outcome_open
    ):
        """Test that open notification works without LLM details (backward compatible)."""
        with patch.object(trade_notifier, "_send_webhook", autospec=True) as mock_send:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message_id = "msg-456"
            mock_send.return_value = mock_result
            trade_notifier._send_webhook = mock_send

            result = await trade_notifier.send_trade_open_notification(
                sample_outcome_open, None
            )

            # Verify webhook was called
            assert mock_send.called

            # Get the embed from the call
            call_args = mock_send.call_args
            payload = call_args[0][0]
            embed = payload["embeds"][0]

            # Verify LLM fields are NOT in embed
            fields = {f["name"]: f["value"] for f in embed["fields"]}

            # Check separator is NOT present
            assert "━━━ LLM Decision Details ━━━" not in fields

            # Check LLM decision fields are NOT present
            assert "🤖 LLM Decision" not in fields
            assert "🔧 Provider" not in fields

            # Verify result success
            assert result.success


class TestTradeCloseNotificationWithLLM:
    """Test trade close notifications with LLM decision details."""

    @pytest.mark.asyncio
    async def test_close_notification_with_llm_details(
        self, trade_notifier, sample_outcome_closed, sample_llm_decision_close
    ):
        """Test that close notification includes all LLM fields and PnL."""
        with patch.object(trade_notifier, "_send_webhook", autospec=True) as mock_send:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message_id = "msg-789"
            mock_send.return_value = mock_result
            trade_notifier._send_webhook = mock_send

            result = await trade_notifier.send_trade_close_notification(
                sample_outcome_closed, sample_llm_decision_close
            )

            # Verify webhook was called
            assert mock_send.called

            # Get the embed from the call
            call_args = mock_send.call_args
            payload = call_args[0][0]
            embed = payload["embeds"][0]

            # Verify LLM fields are in embed
            fields = {f["name"]: f["value"] for f in embed["fields"]}

            # Check separator
            assert "━━━ LLM Decision Details ━━━" in fields

            # Check LLM decision and confidence (uses "Original Decision" for close notifications)
            assert "🤖 Original Decision" in fields
            assert "GO" in fields["🤖 Original Decision"]
            assert "85%" in fields["🤖 Original Decision"]

            # Check provider
            assert "🔧 Provider" in fields
            assert "claude-3-5-sonnet" in fields["🔧 Provider"]

            # Check exit reason (close notifications show exit reason, not rationale)
            assert "🚪 Exit Reason" in fields
            assert "Take profit hit" in fields["🚪 Exit Reason"]

            # Verify result success
            assert result.success

    @pytest.mark.asyncio
    async def test_close_notification_without_llm_details(
        self, trade_notifier, sample_outcome_closed
    ):
        """Test that close notification works without LLM details (backward compatible)."""
        with patch.object(trade_notifier, "_send_webhook", autospec=True) as mock_send:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message_id = "msg-999"
            mock_send.return_value = mock_result
            trade_notifier._send_webhook = mock_send

            result = await trade_notifier.send_trade_close_notification(
                sample_outcome_closed, None
            )

            # Verify webhook was called
            assert mock_send.called

            # Get the embed from the call
            call_args = mock_send.call_args
            payload = call_args[0][0]
            embed = payload["embeds"][0]

            # Verify LLM fields are NOT in embed
            fields = {f["name"]: f["value"] for f in embed["fields"]}

            # Check separator is NOT present
            assert "━━━ LLM Decision Details ━━━" not in fields

            # Check LLM decision fields are NOT present
            assert "🤖 LLM Decision" not in fields
            assert "🔧 Provider" not in fields
            assert "🚪 Exit Reason" not in fields

            # Verify result success
            assert result.success


class TestPayloadFormatValidation:
    """Test payload format and structure validation."""

    @pytest.mark.asyncio
    async def test_open_payload_structure(
        self, trade_notifier, sample_outcome_open, sample_llm_decision_open
    ):
        """Test that open notification payload has correct structure."""
        with patch.object(trade_notifier, "_send_webhook", autospec=True) as mock_send:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message_id = "msg-111"
            mock_send.return_value = mock_result
            trade_notifier._send_webhook = mock_send

            await trade_notifier.send_trade_open_notification(
                sample_outcome_open, sample_llm_decision_open
            )

            # Get payload
            call_args = mock_send.call_args
            payload = call_args[0][0]

            # Validate payload structure
            assert "embeds" in payload
            assert len(payload["embeds"]) == 1

            embed = payload["embeds"][0]

            # Validate embed fields
            assert "title" in embed
            assert "description" in embed
            assert "color" in embed
            assert "fields" in embed
            assert "timestamp" in embed
            assert "footer" in embed

            # Validate field structure
            for field in embed["fields"]:
                assert "name" in field
                assert "value" in field
                assert "inline" in field
                assert isinstance(field["name"], str)
                assert isinstance(field["value"], str)
                assert isinstance(field["inline"], bool)

    @pytest.mark.asyncio
    async def test_close_payload_structure(
        self, trade_notifier, sample_outcome_closed, sample_llm_decision_close
    ):
        """Test that close notification payload has correct structure."""
        with patch.object(trade_notifier, "_send_webhook", autospec=True) as mock_send:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message_id = "msg-222"
            mock_send.return_value = mock_result
            trade_notifier._send_webhook = mock_send

            await trade_notifier.send_trade_close_notification(
                sample_outcome_closed, sample_llm_decision_close
            )

            # Get payload
            call_args = mock_send.call_args
            payload = call_args[0][0]

            # Validate payload structure
            assert "embeds" in payload
            assert len(payload["embeds"]) == 1

            embed = payload["embeds"][0]

            # Validate embed fields
            assert "title" in embed
            assert "description" in embed
            assert "color" in embed
            assert "fields" in embed
            assert "timestamp" in embed
            assert "footer" in embed

            # Validate PnL is highlighted
            fields = {f["name"]: f["value"] for f in embed["fields"]}
            assert any("Realized PnL" in name for name in fields.keys())

    @pytest.mark.asyncio
    async def test_rationale_truncation(self, trade_notifier, sample_outcome_open):
        """Test that long rationale is truncated properly."""
        # Create LLM decision with very long rationale
        long_rationale = "A" * 300  # 300 chars
        llm_decision = {
            "decision": "GO",
            "confidence": 75,
            "provider": "test-provider",
            "rationale": long_rationale,
        }

        with patch.object(trade_notifier, "_send_webhook", autospec=True) as mock_send:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message_id = "msg-333"
            mock_send.return_value = mock_result
            trade_notifier._send_webhook = mock_send

            await trade_notifier.send_trade_open_notification(
                sample_outcome_open, llm_decision
            )

            # Get embed
            call_args = mock_send.call_args
            payload = call_args[0][0]
            embed = payload["embeds"][0]

            # Find rationale field
            fields = embed["fields"]
            rationale_field = next(
                (f for f in fields if "💭 Rationale" in f["name"]), None
            )

            assert rationale_field is not None
            # Should be truncated to 200 chars + "..."
            assert len(rationale_field["value"]) <= 203  # 200 + "..."
            assert rationale_field["value"].endswith("...")


class TestIntegrationLLMExtraction:
    """Test LLM decision extraction in integration layer."""

    @pytest.mark.asyncio
    async def test_integration_extracts_llm_from_metadata(self):
        """Test that integration layer extracts LLM decision from outcome metadata."""
        from execution.alerts.integration import ExecutionAlertIntegration

        # Create mock outcome with LLM decision in metadata
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000.00"),
            position_size=Decimal("1.0"),
            status=SignalOutcomeStatus.FILLED,
            metadata={
                "llm_decision": {
                    "decision": "GO",
                    "confidence": 90,
                    "provider": "gpt-4",
                    "rationale": "Strong uptrend confirmed",
                    "position_size": "1.0 BTC",
                    "stop_loss": 48000.00,
                    "take_profit": 55000.00,
                }
            },
        )

        # Create integration instance
        mock_notifier = MagicMock()
        mock_notifier.send_trade_open_notification = AsyncMock(
            return_value=MagicMock(success=True, message_id="test-msg")
        )

        integration = ExecutionAlertIntegration(
            trade_notifier=mock_notifier, enabled=True
        )

        # Call on_trade_opened
        result = await integration.on_trade_opened(outcome)

        # Verify notifier was called with LLM decision
        assert mock_notifier.send_trade_open_notification.called
        call_args = mock_notifier.send_trade_open_notification.call_args

        # Check that llm_decision parameter was passed
        assert len(call_args[0]) == 2 or len(call_args[1]) > 0

        # Get the llm_decision argument
        if len(call_args[0]) == 2:
            llm_decision = call_args[0][1]
        else:
            llm_decision = call_args[1].get("llm_decision")

        assert llm_decision is not None
        assert llm_decision["decision"] == "GO"
        assert llm_decision["confidence"] == 90
        assert llm_decision["provider"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_integration_handles_missing_llm_metadata(self):
        """Test that integration handles outcomes without LLM metadata."""
        from execution.alerts.integration import ExecutionAlertIntegration

        # Create outcome without LLM decision in metadata
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            symbol="ETHUSDT",
            side="Sell",
            direction="SHORT",
            entry_price=Decimal("3000.00"),
            position_size=Decimal("5.0"),
            status=SignalOutcomeStatus.FILLED,
            metadata={
                "correlation_id": "test-123",
                "signal_confidence": 0.75,
            },
        )

        # Create integration instance
        mock_notifier = MagicMock()
        mock_notifier.send_trade_open_notification = AsyncMock(
            return_value=MagicMock(success=True, message_id="test-msg-2")
        )

        integration = ExecutionAlertIntegration(
            trade_notifier=mock_notifier, enabled=True
        )

        # Call on_trade_opened
        result = await integration.on_trade_opened(outcome)

        # Verify notifier was called
        assert mock_notifier.send_trade_open_notification.called
        call_args = mock_notifier.send_trade_open_notification.call_args

        # Get the llm_decision argument
        if len(call_args[0]) == 2:
            llm_decision = call_args[0][1]
        else:
            llm_decision = call_args[1].get("llm_decision")

        # Should be None when no LLM metadata
        assert llm_decision is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
