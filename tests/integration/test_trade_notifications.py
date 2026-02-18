"""Integration tests for Discord trade notifications.

Tests the TradeNotifier with actual Discord webhook delivery.
Uses the #test channel for verification.

For PAPER-LIVE-001: Discord Trade Notification Integration
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass

# Skip all tests if no webhook URL is configured
pytestmark = pytest.mark.skipif(
    not os.getenv("DISCORD_WEBHOOK_URL"),
    reason="DISCORD_WEBHOOK_URL not set",
)


@pytest.fixture
def webhook_url():
    """Get Discord webhook URL from environment."""
    return os.getenv("DISCORD_WEBHOOK_URL")


@pytest.fixture
def test_channel_id():
    """Get test channel ID."""
    return "1465797462035009708"  # #test channel


@pytest.fixture
def mock_signal():
    """Create a mock signal for testing."""
    from signal_generation.models import Signal, SignalDirection, SignalStatus

    return Signal(
        token="BTC/USDT",
        direction=SignalDirection.LONG,
        confidence=0.85,
        base_score=78.5,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        signal_id=str(uuid.uuid4()),
        generation_latency_ms=45.2,
        metadata={"test": True},
    )


@pytest.fixture
def mock_position_long():
    """Create a mock long position for testing."""
    from portfolio.state_management.models import (
        Position,
        PositionDirection,
        PositionStatus,
    )

    return Position(
        position_id=str(uuid.uuid4()),
        token="BTC/USDT",
        direction=PositionDirection.LONG,
        entry_price=45000.0,
        quantity=0.5,
        current_price=45000.0,
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        status=PositionStatus.OPEN,
        leverage=2.0,
        margin_used=11250.0,
        metadata={"test": True},
    )


@pytest.fixture
def mock_position_short():
    """Create a mock short position for testing."""
    from portfolio.state_management.models import (
        Position,
        PositionDirection,
        PositionStatus,
    )

    return Position(
        position_id=str(uuid.uuid4()),
        token="ETH/USDT",
        direction=PositionDirection.SHORT,
        entry_price=3200.0,
        quantity=2.0,
        current_price=3200.0,
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        status=PositionStatus.OPEN,
        leverage=1.5,
        margin_used=4266.67,
        metadata={"test": True},
    )


@pytest.fixture
def mock_position_closed():
    """Create a mock closed position for testing."""
    from portfolio.state_management.models import (
        Position,
        PositionDirection,
        PositionStatus,
    )

    now = int(datetime.now(UTC).timestamp() * 1000)
    return Position(
        position_id=str(uuid.uuid4()),
        token="BTC/USDT",
        direction=PositionDirection.LONG,
        entry_price=45000.0,
        quantity=0.5,
        current_price=46500.0,
        realized_pnl=750.0,
        timestamp=now - 3600000,  # Opened 1 hour ago
        last_update=now,
        status=PositionStatus.CLOSED,
        leverage=2.0,
        margin_used=11250.0,
        metadata={"test": True},
    )


class TestTradeNotifierIntegration:
    """Integration tests for TradeNotifier with Discord."""

    @pytest.mark.asyncio
    async def test_send_trade_open_notification_long(
        self,
        webhook_url,
        mock_signal,
        mock_position_long,
    ):
        """Test sending trade open notification for long position."""
        from discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            result = await notifier.send_trade_open_notification(
                signal=mock_signal,
                position=mock_position_long,
            )

            assert result.success, f"Notification failed: {result.error}"
            assert result.timestamp is not None
            print("✅ Trade open notification sent successfully")
            print(f"   Timestamp: {result.timestamp}")
            print(f"   Position: {mock_position_long.token} LONG")

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    async def test_send_trade_open_notification_short(
        self,
        webhook_url,
        mock_signal,
        mock_position_short,
    ):
        """Test sending trade open notification for short position."""
        from discord_alerts.trade_notifier import TradeNotifier

        # Modify signal for short
        from signal_generation.models import SignalDirection

        mock_signal.direction = SignalDirection.SHORT
        mock_signal.token = "ETH/USDT"

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            result = await notifier.send_trade_open_notification(
                signal=mock_signal,
                position=mock_position_short,
            )

            assert result.success, f"Notification failed: {result.error}"
            assert result.timestamp is not None
            print("✅ Trade open notification sent successfully")
            print(f"   Timestamp: {result.timestamp}")
            print(f"   Position: {mock_position_short.token} SHORT")

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    async def test_send_trade_close_notification_profit(
        self,
        webhook_url,
        mock_position_closed,
    ):
        """Test sending trade close notification with profit."""
        from discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            result = await notifier.send_trade_close_notification(
                position=mock_position_closed,
                pnl=mock_position_closed.realized_pnl,
                exit_price=46500.0,
            )

            assert result.success, f"Notification failed: {result.error}"
            assert result.timestamp is not None
            print("✅ Trade close notification sent successfully")
            print(f"   Timestamp: {result.timestamp}")
            print(f"   PnL: ${mock_position_closed.realized_pnl:,.2f} (profit)")

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    async def test_send_trade_close_notification_loss(
        self,
        webhook_url,
    ):
        """Test sending trade close notification with loss."""
        from discord_alerts.trade_notifier import TradeNotifier
        from portfolio.state_management.models import (
            Position,
            PositionDirection,
            PositionStatus,
        )

        now = int(datetime.now(UTC).timestamp() * 1000)
        position = Position(
            position_id=str(uuid.uuid4()),
            token="SOL/USDT",
            direction=PositionDirection.LONG,
            entry_price=150.0,
            quantity=10.0,
            current_price=140.0,
            realized_pnl=-100.0,
            timestamp=now - 7200000,  # Opened 2 hours ago
            last_update=now,
            status=PositionStatus.CLOSED,
            leverage=1.0,
            margin_used=1500.0,
            metadata={"test": True},
        )

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            result = await notifier.send_trade_close_notification(
                position=position,
                pnl=-100.0,
                exit_price=140.0,
            )

            assert result.success, f"Notification failed: {result.error}"
            assert result.timestamp is not None
            print("✅ Trade close notification sent successfully")
            print(f"   Timestamp: {result.timestamp}")
            print("   PnL: -$100.00 (loss)")

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    async def test_notification_format_verification(
        self,
        webhook_url,
        mock_signal,
        mock_position_long,
    ):
        """Test that notification format includes all required fields."""
        from discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            # Build embed directly to verify format
            embed = notifier._build_open_embed(mock_signal, mock_position_long)

            # Verify required fields
            assert "title" in embed, "Missing title"
            assert "description" in embed, "Missing description"
            assert "color" in embed, "Missing color"
            assert "fields" in embed, "Missing fields"
            assert "timestamp" in embed, "Missing timestamp"
            assert "footer" in embed, "Missing footer"

            # Verify content
            assert mock_position_long.token in embed["title"], "Token not in title"
            assert "LONG" in embed["description"], "Direction not in description"
            assert "$45,000.00" in embed["description"], "Entry price not formatted"

            # Verify fields
            field_names = [f["name"] for f in embed["fields"]]
            assert any("Notional" in name for name in field_names), (
                "Missing notional value field"
            )
            assert any("Margin" in name for name in field_names), "Missing margin field"

            print("✅ Notification format verification passed")
            print(f"   Title: {embed['title']}")
            print(f"   Fields: {len(embed['fields'])} fields included")

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    async def test_close_notification_format(self, webhook_url, mock_position_closed):
        """Test that close notification format includes PnL correctly."""
        from discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            embed = notifier._build_close_embed(
                mock_position_closed,
                pnl=mock_position_closed.realized_pnl,
                exit_price=46500.0,
            )

            # Verify required fields
            assert "title" in embed, "Missing title"
            assert "description" in embed, "Missing description"
            assert "color" in embed, "Missing color"

            # Verify PnL is highlighted
            field_names = [f["name"] for f in embed["fields"]]
            assert any("PnL" in name for name in field_names), "Missing PnL field"

            # Color should be green for profit
            assert embed["color"] == 0x00FF00, "Color should be green for profit"

            print("✅ Close notification format verification passed")
            print(f"   Title: {embed['title']}")
            print(f"   Color: {embed['color']} (green=profit)")

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    async def test_notifier_without_webhook(self, monkeypatch):
        """Test that notifier handles missing webhook gracefully."""
        from discord_alerts.trade_notifier import TradeNotifier
        from portfolio.state_management.models import (
            Position,
            PositionDirection,
            PositionStatus,
        )
        from signal_generation.models import Signal, SignalDirection, SignalStatus

        # Ensure no webhook URL is available
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

        # Create notifier without webhook
        notifier = TradeNotifier(webhook_url=None)

        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=78.5,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id=str(uuid.uuid4()),
        )

        mock_position = Position(
            position_id=str(uuid.uuid4()),
            token="BTC/USDT",
            direction=PositionDirection.LONG,
            entry_price=45000.0,
            quantity=0.5,
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
            status=PositionStatus.OPEN,
        )

        result = await notifier.send_trade_open_notification(
            signal=mock_signal,
            position=mock_position,
        )

        assert not result.success, "Should fail without webhook"
        assert "No webhook URL" in result.error, "Should report missing webhook"

        print("✅ Missing webhook handling verified")

    @pytest.mark.asyncio
    async def test_health_check(self, webhook_url, monkeypatch):
        """Test health check functionality."""
        from discord_alerts.trade_notifier import TradeNotifier

        # With webhook
        notifier = TradeNotifier(webhook_url=webhook_url)
        health = await notifier.health_check()

        assert health["healthy"] is True, "Should be healthy with webhook"
        assert health["webhook_configured"] is True, "Should report webhook configured"

        # Without webhook - ensure env var is also cleared
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        notifier_no_url = TradeNotifier(webhook_url=None)
        health_no_url = await notifier_no_url.health_check()

        assert health_no_url["healthy"] is False, (
            "Should not be healthy without webhook"
        )
        assert health_no_url["webhook_configured"] is False, (
            "Should report webhook not configured"
        )

        print("✅ Health check verified")
        print(f"   With webhook: {health}")
        print(f"   Without webhook: {health_no_url}")


class TestTradeNotifierE2E:
    """End-to-end tests that actually send messages to Discord."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_actual_discord_delivery_open(
        self,
        webhook_url,
        test_channel_id,
    ):
        """Actually send a trade open notification to Discord #test channel.

        This test sends a real message to Discord and captures the message ID.
        """
        from discord_alerts.trade_notifier import TradeNotifier
        from portfolio.state_management.models import (
            Position,
            PositionDirection,
            PositionStatus,
        )
        from signal_generation.models import Signal, SignalDirection, SignalStatus

        # Create test data
        signal = Signal(
            token="TEST/BTC",
            direction=SignalDirection.LONG,
            confidence=0.82,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id=str(uuid.uuid4()),
            generation_latency_ms=32.5,
        )

        position = Position(
            position_id=str(uuid.uuid4()),
            token="TEST/BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
            status=PositionStatus.OPEN,
            leverage=2.0,
            margin_used=25000.0,
            metadata={"test_run": True, "channel": test_channel_id},
        )

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            result = await notifier.send_trade_open_notification(
                signal=signal,
                position=position,
            )

            assert result.success, f"Discord delivery failed: {result.error}"

            print("\n" + "=" * 60)
            print("🧪 E2E TEST: Trade Open Notification")
            print("=" * 60)
            print("✅ Message sent to Discord #test channel")
            print(f"   Channel ID: {test_channel_id}")
            print(f"   Timestamp: {result.timestamp}")
            print(f"   Token: {position.token}")
            print(f"   Direction: {position.direction.value}")
            print(f"   Entry: ${position.entry_price:,.2f}")
            print("=" * 60)

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_actual_discord_delivery_close(
        self,
        webhook_url,
        test_channel_id,
    ):
        """Actually send a trade close notification to Discord #test channel."""
        from discord_alerts.trade_notifier import TradeNotifier
        from portfolio.state_management.models import (
            Position,
            PositionDirection,
            PositionStatus,
        )

        now = int(datetime.now(UTC).timestamp() * 1000)

        # Create a profitable position
        position = Position(
            position_id=str(uuid.uuid4()),
            token="TEST/ETH",
            direction=PositionDirection.LONG,
            entry_price=3000.0,
            quantity=5.0,
            current_price=3150.0,
            realized_pnl=750.0,
            timestamp=now - 7200000,  # 2 hours ago
            last_update=now,
            status=PositionStatus.CLOSED,
            leverage=1.0,
            margin_used=15000.0,
            metadata={"test_run": True, "channel": test_channel_id},
        )

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            result = await notifier.send_trade_close_notification(
                position=position,
                pnl=position.realized_pnl,
                exit_price=3150.0,
            )

            assert result.success, f"Discord delivery failed: {result.error}"

            print("\n" + "=" * 60)
            print("🧪 E2E TEST: Trade Close Notification")
            print("=" * 60)
            print("✅ Message sent to Discord #test channel")
            print(f"   Channel ID: {test_channel_id}")
            print(f"   Timestamp: {result.timestamp}")
            print(f"   Token: {position.token}")
            print(f"   PnL: ${position.realized_pnl:,.2f} 🟢 PROFIT")
            print("=" * 60)

        finally:
            await notifier.close()

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_actual_discord_delivery_close_loss(
        self,
        webhook_url,
        test_channel_id,
    ):
        """Actually send a trade close notification with loss to Discord."""
        from discord_alerts.trade_notifier import TradeNotifier
        from portfolio.state_management.models import (
            Position,
            PositionDirection,
            PositionStatus,
        )

        now = int(datetime.now(UTC).timestamp() * 1000)

        # Create a losing short position
        position = Position(
            position_id=str(uuid.uuid4()),
            token="TEST/SOL",
            direction=PositionDirection.SHORT,
            entry_price=200.0,
            quantity=20.0,
            current_price=210.0,
            realized_pnl=-200.0,
            timestamp=now - 3600000,  # 1 hour ago
            last_update=now,
            status=PositionStatus.CLOSED,
            leverage=1.0,
            margin_used=4000.0,
            metadata={"test_run": True, "channel": test_channel_id},
        )

        notifier = TradeNotifier(webhook_url=webhook_url)

        try:
            result = await notifier.send_trade_close_notification(
                position=position,
                pnl=-200.0,
                exit_price=210.0,
            )

            assert result.success, f"Discord delivery failed: {result.error}"

            print("\n" + "=" * 60)
            print("🧪 E2E TEST: Trade Close Notification (Loss)")
            print("=" * 60)
            print("✅ Message sent to Discord #test channel")
            print(f"   Channel ID: {test_channel_id}")
            print(f"   Timestamp: {result.timestamp}")
            print(f"   Token: {position.token}")
            print("   PnL: -$200.00 🔴 LOSS")
            print("=" * 60)

        finally:
            await notifier.close()
