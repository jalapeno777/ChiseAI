"""Tests for Discord trade notifier.

Tests trade open/close notifications, retry logic, and failure handling.

For RECON-001: Trade Schema Reconciliation
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.discord_alerts.trade_notifier import TradeNotificationResult, TradeNotifier
from src.ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus


@pytest.fixture
def mock_signal_outcome() -> SignalOutcome:
    """Create a mock SignalOutcome for testing."""
    return SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id="test-order-123",
        symbol="BTCUSDT",
        token="BTC",
        side="Buy",
        direction="LONG",
        fill_price=Decimal("50000.00"),
        fill_quantity=Decimal("0.1"),
        fill_timestamp=datetime.now(UTC),
        outcome_type="manual_close",
        pnl=Decimal("100.00"),
        fee=Decimal("5.00"),
        status=SignalOutcomeStatus.CLOSED,
        entry_price=Decimal("49000.00"),
        exit_price=Decimal("50000.00"),
        entry_time=datetime.now(UTC),
        exit_time=datetime.now(UTC),
        leverage=Decimal("2.0"),
        entry_reason="signal_trigger",
        position_size=Decimal("0.1"),
    )


@pytest.fixture
def mock_open_outcome() -> SignalOutcome:
    """Create a mock SignalOutcome for open trade testing."""
    return SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id="test-order-456",
        symbol="ETHUSDT",
        token="ETH",
        side="Buy",
        direction="LONG",
        fill_price=Decimal("3000.00"),
        fill_quantity=Decimal("1.0"),
        fill_timestamp=datetime.now(UTC),
        outcome_type="tp_hit",
        pnl=None,
        fee=Decimal("3.00"),
        status=SignalOutcomeStatus.FILLED,
        entry_price=Decimal("3000.00"),
        exit_price=None,
        entry_time=datetime.now(UTC),
        exit_time=None,
        leverage=Decimal("1.0"),
        entry_reason="signal_trigger",
        position_size=Decimal("1.0"),
    )


@pytest.fixture
def mock_short_outcome() -> SignalOutcome:
    """Create a mock SignalOutcome for short trade testing."""
    return SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id="test-order-789",
        symbol="SOLUSDT",
        token="SOL",
        side="Sell",
        direction="SHORT",
        fill_price=Decimal("100.00"),
        fill_quantity=Decimal("10.0"),
        fill_timestamp=datetime.now(UTC),
        outcome_type="sl_hit",
        pnl=Decimal("-50.00"),
        fee=Decimal("2.00"),
        status=SignalOutcomeStatus.CLOSED,
        entry_price=Decimal("95.00"),
        exit_price=Decimal("100.00"),
        entry_time=datetime.now(UTC),
        exit_time=datetime.now(UTC),
        leverage=Decimal("3.0"),
        entry_reason="signal_trigger",
        position_size=Decimal("10.0"),
    )


class TestTradeNotifier:
    """Test suite for TradeNotifier."""

    @pytest.fixture
    def notifier(self) -> TradeNotifier:
        """Create a TradeNotifier instance for testing."""
        return TradeNotifier(
            webhook_url="https://discord.com/api/webhooks/test",
            trading_channel_id="1444447985378398459",
            max_retries=3,
            retry_base_delay=0.1,  # Fast for tests
            retry_max_delay=1.0,
        )

    @pytest.mark.asyncio
    async def test_trade_open_notification_success(
        self,
        notifier: TradeNotifier,
        mock_open_outcome: SignalOutcome,
    ) -> None:
        """Test successful trade open notification."""
        with patch.object(
            notifier,
            "_send_webhook_with_retry",
            return_value=TradeNotificationResult(success=True),
        ) as mock_send:
            result = await notifier.send_trade_open_notification(mock_open_outcome)

            assert result.success is True
            mock_send.assert_called_once()

            # Verify the payload was built correctly
            call_args = mock_send.call_args
            assert call_args is not None
            payload = call_args[0][0]
            assert "embeds" in payload
            assert len(payload["embeds"]) == 1

            embed = payload["embeds"][0]
            assert "Trade Opened: ETH" in embed["title"]
            assert "🟢" in embed["description"]  # LONG emoji
            assert embed["color"] == 0x00FF00  # Green for LONG

    @pytest.mark.asyncio
    async def test_trade_close_notification_success(
        self,
        notifier: TradeNotifier,
        mock_signal_outcome: SignalOutcome,
    ) -> None:
        """Test successful trade close notification with profit."""
        with patch.object(
            notifier,
            "_send_webhook_with_retry",
            return_value=TradeNotificationResult(success=True),
        ) as mock_send:
            result = await notifier.send_trade_close_notification(mock_signal_outcome)

            assert result.success is True
            mock_send.assert_called_once()

            # Verify the payload was built correctly
            call_args = mock_send.call_args
            assert call_args is not None
            payload = call_args[0][0]
            assert "embeds" in payload
            assert len(payload["embeds"]) == 1

            embed = payload["embeds"][0]
            assert "Trade Closed: BTC" in embed["title"]
            assert "🟢" in embed["fields"][0]["name"]  # Profit emoji
            assert "+$100.00" in embed["fields"][0]["value"]
            assert embed["color"] == 0x00FF00  # Green for profit

    @pytest.mark.asyncio
    async def test_trade_close_notification_loss(
        self,
        notifier: TradeNotifier,
        mock_short_outcome: SignalOutcome,
    ) -> None:
        """Test trade close notification with loss."""
        with patch.object(
            notifier,
            "_send_webhook_with_retry",
            return_value=TradeNotificationResult(success=True),
        ) as mock_send:
            result = await notifier.send_trade_close_notification(mock_short_outcome)

            assert result.success is True
            mock_send.assert_called_once()

            # Verify the payload was built correctly
            call_args = mock_send.call_args
            assert call_args is not None
            payload = call_args[0][0]
            embed = payload["embeds"][0]
            assert "🔴" in embed["fields"][0]["name"]  # Loss emoji
            assert (
                "$-50.00" in embed["fields"][0]["value"]
            )  # Format is $-50.00 not -$50.00
            assert embed["color"] == 0xFF0000  # Red for loss

    @pytest.mark.asyncio
    async def test_notification_without_webhook(self) -> None:
        """Test notification fails gracefully without webhook URL."""
        # Create notifier with explicit None webhook
        notifier = TradeNotifier(webhook_url=None, trading_channel_id=None)
        # Manually clear webhook to simulate no config
        notifier.webhook_url = None

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
        )

        result = await notifier.send_trade_open_notification(outcome)

        assert result.success is False
        assert result.error is not None
        assert "No webhook URL configured" in result.error

    @pytest.mark.asyncio
    async def test_retry_logic_success_after_failure(
        self,
        notifier: TradeNotifier,
        mock_signal_outcome: SignalOutcome,
    ) -> None:
        """Test retry logic succeeds after initial failures."""
        call_count = 0

        async def mock_send_webhook(payload: dict) -> TradeNotificationResult:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return TradeNotificationResult(
                    success=False,
                    error="Temporary error",
                )
            return TradeNotificationResult(success=True)

        with patch.object(notifier, "_send_webhook", side_effect=mock_send_webhook):
            with patch("asyncio.sleep", return_value=None):  # Skip actual delays
                result = await notifier._send_webhook_with_retry(
                    {"test": "payload"},
                    mock_signal_outcome,
                )

        assert result.success is True
        assert result.retry_count == 2
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_logic_exhausted(
        self,
        notifier: TradeNotifier,
        mock_signal_outcome: SignalOutcome,
    ) -> None:
        """Test retry logic fails after max retries exhausted."""
        with patch.object(
            notifier,
            "_send_webhook",
            return_value=TradeNotificationResult(
                success=False,
                error="Persistent error",
            ),
        ):
            with patch("asyncio.sleep", return_value=None):  # Skip actual delays
                with patch.object(
                    notifier,
                    "_queue_to_dead_letter",
                    return_value=True,
                ) as mock_queue:
                    result = await notifier._send_webhook_with_retry(
                        {"test": "payload"},
                        mock_signal_outcome,
                    )

        assert result.success is False
        assert result.retry_count == 4  # max_retries + 1 (initial attempt + 3 retries)
        assert result.error == "Persistent error"
        assert result.dead_letter_queued is True
        mock_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_logic_rate_limit(
        self,
        notifier: TradeNotifier,
        mock_signal_outcome: SignalOutcome,
    ) -> None:
        """Test retry logic handles rate limiting correctly."""
        call_count = 0

        async def mock_send_webhook(payload: dict) -> TradeNotificationResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return TradeNotificationResult(
                    success=False,
                    error="Rate limited by Discord. Retry after 2s",
                )
            return TradeNotificationResult(success=True)

        with patch.object(notifier, "_send_webhook", side_effect=mock_send_webhook):
            with patch("asyncio.sleep", return_value=None):  # Skip actual delays
                result = await notifier._send_webhook_with_retry(
                    {"test": "payload"},
                    mock_signal_outcome,
                )

        assert result.success is True
        assert result.retry_count == 1

    @pytest.mark.asyncio
    async def test_failure_logging(
        self,
        notifier: TradeNotifier,
        mock_signal_outcome: SignalOutcome,
    ) -> None:
        """Test that failures are logged with structured data."""
        with patch("src.discord_alerts.trade_notifier.logger") as mock_logger:
            with patch.object(
                notifier,
                "_send_webhook",
                return_value=TradeNotificationResult(
                    success=False,
                    error="Test error",
                ),
            ):
                with patch("asyncio.sleep", return_value=None):
                    with patch.object(
                        notifier,
                        "_queue_to_dead_letter",
                        return_value=True,
                    ):
                        await notifier._send_webhook_with_retry(
                            {"test": "payload"},
                            mock_signal_outcome,
                        )

            # Check that error was logged
            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "discord_notification_failed" in str(call)
            ]
            assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_dead_letter_queue(
        self,
        notifier: TradeNotifier,
        mock_signal_outcome: SignalOutcome,
    ) -> None:
        """Test dead-letter queue functionality."""
        mock_redis = MagicMock()
        mock_redis.lpush = MagicMock(return_value=1)
        mock_redis.expire = MagicMock(return_value=1)

        with patch.object(notifier, "_get_redis", return_value=mock_redis):
            result = await notifier._queue_to_dead_letter(
                {"test": "payload"},
                mock_signal_outcome,
                "Test error",
            )

        assert result is True
        mock_redis.lpush.assert_called_once()
        mock_redis.expire.assert_called_once()

        # Verify the queued item structure
        call_args = mock_redis.lpush.call_args
        queue_key = call_args[0][0]
        item_json = call_args[0][1]
        item = json.loads(item_json)

        assert queue_key == "chiseai:discord:dead_letter:trade_notifications"
        assert "timestamp" in item
        assert item["outcome_id"] == str(mock_signal_outcome.outcome_id)
        assert item["symbol"] == mock_signal_outcome.symbol
        assert item["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_process_dead_letter_queue(
        self,
        notifier: TradeNotifier,
    ) -> None:
        """Test processing items from dead-letter queue."""
        mock_redis = MagicMock()
        # Return one item, then None
        mock_redis.rpop = MagicMock(
            side_effect=[
                json.dumps(
                    {
                        "outcome_id": str(uuid4()),
                        "payload": {"embeds": [{"title": "Test"}]},
                        "retry_count": 0,
                    }
                ),
                None,
            ]
        )

        with patch.object(notifier, "_get_redis", return_value=mock_redis):
            with patch.object(
                notifier,
                "_send_webhook",
                return_value=TradeNotificationResult(success=True),
            ) as mock_send:
                results = await notifier.process_dead_letter_queue(max_items=5)

        assert len(results) == 1
        assert results[0].success is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check(self, notifier: TradeNotifier) -> None:
        """Test health check functionality."""
        with patch.object(
            notifier,
            "_get_session",
            return_value=AsyncMock(),
        ):
            health = await notifier.health_check()

        assert "healthy" in health
        assert "webhook_configured" in health
        assert "trading_channel_id" in health
        assert "retry_config" in health
        assert "dead_letter_queue" in health

        assert health["webhook_configured"] is True
        assert health["trading_channel_id"] == "1444447985378398459"
        assert health["retry_config"]["max_retries"] == 3

    def test_format_duration(self, notifier: TradeNotifier) -> None:
        """Test duration formatting."""
        from datetime import timedelta

        # Test with timedelta
        assert notifier._format_duration(timedelta(seconds=30)) == "30s"
        assert notifier._format_duration(timedelta(minutes=5)) == "5m 0s"
        assert notifier._format_duration(timedelta(hours=2)) == "2h 0m"
        assert notifier._format_duration(timedelta(days=1)) == "1d 0h"

        # Test with milliseconds
        assert notifier._format_duration(30000) == "30s"
        assert notifier._format_duration(300000) == "5m 0s"

    def test_build_open_embed_structure(
        self,
        notifier: TradeNotifier,
        mock_open_outcome: SignalOutcome,
    ) -> None:
        """Test that open embed has all required fields."""
        embed = notifier._build_open_embed(mock_open_outcome)

        # Required fields
        assert "title" in embed
        assert "description" in embed
        assert "color" in embed
        assert "fields" in embed
        assert "timestamp" in embed
        assert "footer" in embed

        # Check content
        assert mock_open_outcome.token in embed["title"]
        assert str(mock_open_outcome.direction) in embed["description"]
        assert f"${float(mock_open_outcome.entry_price):,.2f}" in embed["description"]

        # Check fields contain required info
        field_names = [f["name"] for f in embed["fields"]]
        assert any("Notional Value" in name for name in field_names)
        assert any("Signal ID" in name for name in field_names)

    def test_build_close_embed_structure(
        self,
        notifier: TradeNotifier,
        mock_signal_outcome: SignalOutcome,
    ) -> None:
        """Test that close embed has all required fields."""
        embed = notifier._build_close_embed(mock_signal_outcome)

        # Required fields
        assert "title" in embed
        assert "description" in embed
        assert "color" in embed
        assert "fields" in embed
        assert "timestamp" in embed
        assert "footer" in embed

        # Check content
        assert mock_signal_outcome.token in embed["title"]
        assert str(mock_signal_outcome.direction) in embed["description"]
        assert f"${float(mock_signal_outcome.entry_price):,.2f}" in embed["description"]
        assert f"${float(mock_signal_outcome.exit_price):,.2f}" in embed["description"]

        # Check fields contain required info
        field_names = [f["name"] for f in embed["fields"]]
        assert any("PnL" in name for name in field_names)
        assert any("Return" in name for name in field_names)
        assert any("Duration" in name for name in field_names)


class TestTradeNotificationResult:
    """Test suite for TradeNotificationResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a TradeNotificationResult."""
        result = TradeNotificationResult(
            success=True,
            message_id="12345",
            timestamp=datetime.now(UTC),
            retry_count=2,
        )

        assert result.success is True
        assert result.message_id == "12345"
        assert result.retry_count == 2
        assert result.dead_letter_queued is False

    def test_result_failure(self) -> None:
        """Test creating a failed TradeNotificationResult."""
        result = TradeNotificationResult(
            success=False,
            error="Connection timeout",
            retry_count=3,
            dead_letter_queued=True,
        )

        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.retry_count == 3
        assert result.dead_letter_queued is True


class TestSignalOutcomeIntegration:
    """Test integration with SignalOutcome model."""

    def test_signal_outcome_to_notification_dict(self) -> None:
        """Test SignalOutcome conversion to notification dict."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            symbol="BTCUSDT",
            token="BTC",
            direction="LONG",
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000"),
            entry_time=datetime.now(UTC),
            exit_time=datetime.now(UTC),
            pnl=Decimal("100"),
            leverage=Decimal("2.0"),
            position_size=Decimal("0.1"),
            entry_reason="signal_trigger",
            status=SignalOutcomeStatus.CLOSED,
        )

        notification_dict = outcome.to_notification_dict()

        assert notification_dict["symbol"] == "BTCUSDT"
        assert notification_dict["token"] == "BTC"
        assert notification_dict["direction"] == "LONG"
        assert notification_dict["entry_price"] == 50000.0
        assert notification_dict["exit_price"] == 51000.0
        assert notification_dict["pnl"] == 100.0
        assert notification_dict["leverage"] == 2.0
        assert notification_dict["position_size"] == 0.1
        assert notification_dict["entry_reason"] == "signal_trigger"
        assert notification_dict["is_closed"] is True

    def test_signal_outcome_properties(self) -> None:
        """Test SignalOutcome properties."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
            exit_price=Decimal("51000"),
            pnl=Decimal("100"),
            status=SignalOutcomeStatus.CLOSED,
        )

        assert outcome.is_closed is True
        assert outcome.position_value == Decimal("5000")
        assert outcome.realized_pnl == Decimal("100")

    def test_signal_outcome_token_derivation(self) -> None:
        """Test that token is derived from symbol if not set."""
        outcome = SignalOutcome(
            symbol="ETHUSDT",
            entry_price=Decimal("3000"),
            position_size=Decimal("1.0"),
        )

        # Token should be derived from symbol
        assert outcome.token == "ETH"

    def test_signal_outcome_direction_derivation(self) -> None:
        """Test that direction is derived from side if not set."""
        outcome_buy = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
        )

        outcome_sell = SignalOutcome(
            symbol="BTCUSDT",
            side="Sell",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
        )

        assert outcome_buy.direction == "LONG"
        assert outcome_sell.direction == "SHORT"


class TestWebhookURLRouting:
    """Test suite for webhook URL routing (DISCORD-TRADING-001)."""

    @pytest.fixture
    def notifier(self) -> TradeNotifier:
        """Create a TradeNotifier instance for testing."""
        return TradeNotifier(
            webhook_url="https://discord.com/api/webhooks/test",
            trading_channel_id="1444447985378398459",
            max_retries=3,
            retry_base_delay=0.1,
            retry_max_delay=1.0,
        )

    def test_trading_webhook_url_priority(self) -> None:
        """Test that DISCORD_TRADING_WEBHOOK_URL takes priority over DISCORD_WEBHOOK_URL."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_TRADING_WEBHOOK_URL": "https://discord.com/api/webhooks/trading",
                "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/general",
            },
            clear=True,
        ):
            notifier = TradeNotifier()
            assert notifier.webhook_url == "https://discord.com/api/webhooks/trading"

    def test_fallback_to_discord_webhook_url(self) -> None:
        """Test fallback to DISCORD_WEBHOOK_URL when DISCORD_TRADING_WEBHOOK_URL is not set."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/general",
            },
            clear=True,
        ):
            notifier = TradeNotifier()
            assert notifier.webhook_url == "https://discord.com/api/webhooks/general"

    def test_explicit_webhook_url_overrides_env(self) -> None:
        """Test that explicit webhook_url parameter overrides environment variables."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_TRADING_WEBHOOK_URL": "https://discord.com/api/webhooks/trading",
                "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/general",
            },
            clear=True,
        ):
            notifier = TradeNotifier(
                webhook_url="https://discord.com/api/webhooks/explicit"
            )
            assert notifier.webhook_url == "https://discord.com/api/webhooks/explicit"


class TestTestTradeLabeling:
    """Test suite for test trade labeling (DISCORD-TRADING-001)."""

    @pytest.fixture
    def notifier(self) -> TradeNotifier:
        """Create a TradeNotifier instance for testing."""
        return TradeNotifier(
            webhook_url="https://discord.com/api/webhooks/test",
            trading_channel_id="1444447985378398459",
            max_retries=3,
            retry_base_delay=0.1,
            retry_max_delay=1.0,
        )

    def test_open_embed_test_prefix(self, notifier: TradeNotifier) -> None:
        """Test that [TEST] prefix is added to open trade title when is_test=True."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
            is_test=True,
        )

        embed = notifier._build_open_embed(outcome)
        assert "[TEST]" in embed["title"]
        assert "Trade Opened: BTC" in embed["title"]

    def test_open_embed_no_test_prefix(self, notifier: TradeNotifier) -> None:
        """Test that [TEST] prefix is NOT added when is_test=False."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
            is_test=False,
        )

        embed = notifier._build_open_embed(outcome)
        assert "[TEST]" not in embed["title"]
        assert "Trade Opened: BTC" in embed["title"]

    def test_close_embed_test_prefix(self, notifier: TradeNotifier) -> None:
        """Test that [TEST] prefix is added to close trade title when is_test=True."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000"),
            position_size=Decimal("0.1"),
            pnl=Decimal("100"),
            status=SignalOutcomeStatus.CLOSED,
            is_test=True,
        )

        embed = notifier._build_close_embed(outcome)
        assert "[TEST]" in embed["title"]
        assert "Trade Closed: BTC" in embed["title"]

    def test_close_embed_no_test_prefix(self, notifier: TradeNotifier) -> None:
        """Test that [TEST] prefix is NOT added when is_test=False."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000"),
            position_size=Decimal("0.1"),
            pnl=Decimal("100"),
            status=SignalOutcomeStatus.CLOSED,
            is_test=False,
        )

        embed = notifier._build_close_embed(outcome)
        assert "[TEST]" not in embed["title"]
        assert "Trade Closed: BTC" in embed["title"]

    def test_open_embed_test_indicator_in_footer(self, notifier: TradeNotifier) -> None:
        """Test that test indicator emoji is in footer for test trades."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
            is_test=True,
        )

        embed = notifier._build_open_embed(outcome)
        assert "🧪" in embed["footer"]["text"]

    def test_close_embed_test_indicator_in_footer(
        self, notifier: TradeNotifier
    ) -> None:
        """Test that test indicator emoji is in footer for test trades."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000"),
            position_size=Decimal("0.1"),
            pnl=Decimal("100"),
            status=SignalOutcomeStatus.CLOSED,
            is_test=True,
        )

        embed = notifier._build_close_embed(outcome)
        assert "🧪" in embed["footer"]["text"]


class TestDurationField:
    """Test suite for duration field in close notifications."""

    @pytest.fixture
    def notifier(self) -> TradeNotifier:
        """Create a TradeNotifier instance for testing."""
        return TradeNotifier(
            webhook_url="https://discord.com/api/webhooks/test",
            trading_channel_id="1444447985378398459",
            max_retries=3,
            retry_base_delay=0.1,
            retry_max_delay=1.0,
        )

    def test_duration_field_present_in_close_embed(
        self,
        notifier: TradeNotifier,
    ) -> None:
        """Test that duration field is present in close embed."""
        from datetime import timedelta

        entry_time = datetime.now(UTC)
        exit_time = entry_time + timedelta(hours=2, minutes=30)

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000"),
            position_size=Decimal("0.1"),
            pnl=Decimal("100"),
            status=SignalOutcomeStatus.CLOSED,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        embed = notifier._build_close_embed(outcome)
        field_names = [f["name"] for f in embed["fields"]]
        assert any("Duration" in name for name in field_names)

    def test_duration_format_hours_minutes(
        self,
        notifier: TradeNotifier,
    ) -> None:
        """Test that duration is formatted correctly for hours and minutes."""
        from datetime import timedelta

        entry_time = datetime.now(UTC)
        exit_time = entry_time + timedelta(hours=2, minutes=30)

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000"),
            position_size=Decimal("0.1"),
            pnl=Decimal("100"),
            status=SignalOutcomeStatus.CLOSED,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        embed = notifier._build_close_embed(outcome)
        duration_field = next(f for f in embed["fields"] if "Duration" in f["name"])
        assert "2h 30m" in duration_field["value"]

    def test_duration_not_present_when_exit_time_missing(
        self,
        notifier: TradeNotifier,
    ) -> None:
        """Test that duration field is not present when exit_time is missing."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            entry_price=Decimal("50000"),
            position_size=Decimal("0.1"),
            pnl=Decimal("100"),
            status=SignalOutcomeStatus.CLOSED,
            entry_time=datetime.now(UTC),
            exit_time=None,
        )

        embed = notifier._build_close_embed(outcome)
        field_names = [f["name"] for f in embed["fields"]]
        assert not any("Duration" in name for name in field_names)


class TestNotificationThrottle:
    """Tests for per-symbol notification throttle (FIX 3d).

    Notifications for the same symbol within NOTIFICATION_MIN_INTERVAL_SECONDS
    should be throttled. Different symbols should not interfere.
    """

    @pytest.fixture
    def notifier_with_throttle(self) -> TradeNotifier:
        """Create a notifier with a short throttle for testing."""
        notifier = TradeNotifier(webhook_url="https://discord.test/webhook")
        notifier._notification_min_interval = 10  # 10s for testing
        return notifier

    def test_should_throttle_returns_false_for_first_notification(
        self, notifier_with_throttle: TradeNotifier
    ):
        """Test that first notification for a symbol is never throttled."""
        assert notifier_with_throttle._should_throttle_notification("BTCUSDT") is False

    def test_should_throttle_returns_true_within_interval(
        self, notifier_with_throttle: TradeNotifier
    ):
        """Test that rapid notification for same symbol is throttled."""
        notifier_with_throttle._record_notification_sent("BTCUSDT")
        # Immediately try again — should be throttled
        assert notifier_with_throttle._should_throttle_notification("BTCUSDT") is True

    def test_different_symbols_not_throttled(
        self, notifier_with_throttle: TradeNotifier
    ):
        """Test that different symbols have independent throttle."""
        notifier_with_throttle._record_notification_sent("BTCUSDT")
        # ETH should not be throttled
        assert notifier_with_throttle._should_throttle_notification("ETHUSDT") is False

    def test_throttle_clears_after_interval(
        self, notifier_with_throttle: TradeNotifier
    ):
        """Test that throttle clears after minimum interval passes."""
        import time

        notifier_with_throttle._notification_min_interval = 0  # Instant expiry
        notifier_with_throttle._record_notification_sent("BTCUSDT")
        time.sleep(0.01)  # Tiny wait
        assert notifier_with_throttle._should_throttle_notification("BTCUSDT") is False

    def test_throttle_reads_env_var(self):
        """Test that NOTIFICATION_MIN_INTERVAL_SECONDS env var is respected."""
        with patch.dict(os.environ, {"NOTIFICATION_MIN_INTERVAL_SECONDS": "60"}):
            notifier = TradeNotifier(webhook_url="https://discord.test/webhook")
            assert notifier._notification_min_interval == 60

    def test_throttle_minimum_is_5_seconds(self):
        """Test that throttle minimum is 5 seconds (safety floor)."""
        with patch.dict(os.environ, {"NOTIFICATION_MIN_INTERVAL_SECONDS": "1"}):
            notifier = TradeNotifier(webhook_url="https://discord.test/webhook")
            assert notifier._notification_min_interval >= 5

    @pytest.mark.asyncio
    async def test_open_notification_skipped_when_throttled(self):
        """Test that open notification returns throttled result."""
        notifier = TradeNotifier(webhook_url="https://discord.test/webhook")
        notifier._notification_min_interval = 300  # 5 min throttle

        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000"),
            position_size=Decimal("0.1"),
            status=SignalOutcomeStatus.CLOSED,
        )

        # Send first notification
        with patch.object(
            notifier, "_send_webhook_with_retry", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = TradeNotificationResult(
                success=True, message_id="123"
            )
            result1 = await notifier.send_trade_open_notification(outcome)
            assert result1.success is True

        # Second notification should be throttled
        result2 = await notifier.send_trade_open_notification(outcome)
        assert result2.success is False
        assert "throttled" in result2.error.lower()

    @pytest.mark.asyncio
    async def test_close_notification_skipped_when_throttled(self):
        """Test that close notification returns throttled result."""
        notifier = TradeNotifier(webhook_url="https://discord.test/webhook")
        notifier._notification_min_interval = 300

        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            symbol="ETHUSDT",
            token="ETH",
            side="Sell",
            direction="SHORT",
            fill_price=Decimal("3000"),
            position_size=Decimal("1.0"),
            status=SignalOutcomeStatus.CLOSED,
        )

        with patch.object(
            notifier, "_send_webhook_with_retry", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = TradeNotificationResult(
                success=True, message_id="456"
            )
            result1 = await notifier.send_trade_close_notification(outcome)
            assert result1.success is True

        result2 = await notifier.send_trade_close_notification(outcome)
        assert result2.success is False
        assert "throttled" in result2.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
