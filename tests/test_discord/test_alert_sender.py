"""Tests for alert sender.

Tests for ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest import mock

import pytest

from discord_alerts.alert_formatter import AlertType
from discord_alerts.alert_sender import AlertSender, SendResult
from discord_alerts.config import DiscordConfig
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestSendResult:
    """Test cases for SendResult dataclass."""

    def test_send_result_creation(self) -> None:
        """Test creating send result."""
        result = SendResult(
            success=True,
            message_id="12345",
            channel="trading-signals",
            latency_ms=150.5,
            retries=0,
        )

        assert result.success is True
        assert result.message_id == "12345"
        assert result.channel == "trading-signals"
        assert result.latency_ms == 150.5
        assert result.retries == 0
        assert result.suppressed is False

    def test_send_result_failure(self) -> None:
        """Test creating failed send result."""
        result = SendResult(
            success=False,
            error="Rate limited",
            retries=2,
            suppressed=True,
        )

        assert result.success is False
        assert result.error == "Rate limited"
        assert result.retries == 2
        assert result.suppressed is True


class TestAlertSender:
    """Test cases for AlertSender."""

    @pytest.fixture
    def config(self) -> DiscordConfig:
        """Create Discord config fixture."""
        return DiscordConfig(
            webhook_url="https://discord.com/api/webhooks/123456/test",
            default_channel="trading-signals",
            watchlist_channel="watchlist",
            rate_limit_per_minute=10,
            enable_duplicate_suppression=True,
            max_retries=3,
        )

    @pytest.fixture
    def actionable_signal(self) -> Signal:
        """Create actionable signal fixture (75%+ confidence)."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=82.5,
            timestamp=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="test-signal-123",
            generation_latency_ms=150.5,
        )

    @pytest.fixture
    def watchlist_signal(self) -> Signal:
        """Create watchlist signal fixture (40-74% confidence)."""
        return Signal(
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.55,
            base_score=52.0,
            timestamp=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="4h",
            signal_id="test-signal-456",
            generation_latency_ms=200.0,
        )

    @pytest.fixture
    def low_confidence_signal(self) -> Signal:
        """Create low confidence signal fixture (<40% confidence)."""
        return Signal(
            token="SOL/USDT",
            direction=SignalDirection.NEUTRAL,
            confidence=0.25,
            base_score=30.0,
            timestamp=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="15m",
            signal_id="test-signal-789",
            generation_latency_ms=100.0,
        )

    def test_sender_creation(self, config) -> None:
        """Test creating alert sender."""
        sender = AlertSender(config)

        assert sender.config == config
        assert sender._client is None
        assert sender._formatter is None
        assert sender._suppressor is None
        assert sender._rate_limiter is None

    @pytest.mark.asyncio
    async def test_determine_alert_type_actionable(
        self, config, actionable_signal
    ) -> None:
        """Test determining alert type for actionable signal."""
        sender = AlertSender(config)

        alert_type, channel = sender._determine_alert_type_and_channel(
            actionable_signal
        )

        assert alert_type == AlertType.ACTIONABLE
        assert channel == "trading-signals"

    @pytest.mark.asyncio
    async def test_determine_alert_type_watchlist(
        self, config, watchlist_signal
    ) -> None:
        """Test determining alert type for watchlist signal."""
        sender = AlertSender(config)

        alert_type, channel = sender._determine_alert_type_and_channel(watchlist_signal)

        assert alert_type == AlertType.WATCHLIST
        assert channel == "watchlist"

    @pytest.mark.asyncio
    async def test_determine_alert_type_low_confidence(
        self, config, low_confidence_signal
    ) -> None:
        """Test determining alert type for low confidence signal."""
        sender = AlertSender(config)

        alert_type, channel = sender._determine_alert_type_and_channel(
            low_confidence_signal
        )

        assert alert_type == AlertType.INFO
        assert channel == "trading-signals"

    @pytest.mark.asyncio
    async def test_determine_alert_type_watchlist_no_channel(
        self, watchlist_signal
    ) -> None:
        """Test watchlist falls back to default when no watchlist channel."""
        config = DiscordConfig(
            webhook_url="https://test.webhook",
            default_channel="trading-signals",
            watchlist_channel=None,  # No watchlist channel
        )
        sender = AlertSender(config)

        alert_type, channel = sender._determine_alert_type_and_channel(watchlist_signal)

        assert alert_type == AlertType.WATCHLIST
        assert channel == "trading-signals"  # Falls back to default

    @pytest.mark.asyncio
    async def test_send_signal_duplicate_suppressed(
        self, config, actionable_signal
    ) -> None:
        """Test duplicate signal is suppressed."""
        sender = AlertSender(config)

        # First send should succeed (mocked)
        with mock.patch.object(
            sender, "_send_with_retry", return_value=SendResult(success=True)
        ):
            await sender.send_signal(actionable_signal)

        # Second send should be suppressed
        result2 = await sender.send_signal(actionable_signal)

        assert result2.success is False
        assert result2.suppressed is True
        assert "Duplicate" in result2.error

    @pytest.mark.asyncio
    async def test_send_signal_force_send(self, config, actionable_signal) -> None:
        """Test force sending bypasses suppression."""
        sender = AlertSender(config)

        # Send twice with force=True
        with mock.patch.object(
            sender, "_send_with_retry", return_value=SendResult(success=True)
        ):
            await sender.send_signal(actionable_signal)
            result2 = await sender.send_signal(actionable_signal, force=True)

        # Second send should not be suppressed when forced
        assert result2.suppressed is False

    @pytest.mark.asyncio
    async def test_send_signal_suppression_disabled(self, actionable_signal) -> None:
        """Test sending when suppression is disabled."""
        config = DiscordConfig(
            webhook_url="https://test.webhook",
            enable_duplicate_suppression=False,
        )
        sender = AlertSender(config)

        # Send twice
        with mock.patch.object(
            sender, "_send_with_retry", return_value=SendResult(success=True)
        ):
            await sender.send_signal(actionable_signal)
            result2 = await sender.send_signal(actionable_signal)

        # Second should not be suppressed
        assert result2.suppressed is False

    @pytest.mark.asyncio
    async def test_send_signal_rate_limited(self, config) -> None:
        """Test rate limiting."""
        config = DiscordConfig(
            webhook_url="https://test.webhook",
            default_channel="test",
            rate_limit_per_minute=1,  # Very low limit
            enable_duplicate_suppression=False,  # Disable to test rate limit
        )
        sender = AlertSender(config)

        # Create two different signals to avoid duplicate detection
        signal1 = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="signal-1",
        )
        signal2 = Signal(
            token="ETH/USDT",  # Different token
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="signal-2",
        )

        # First send
        with mock.patch.object(
            sender, "_send_with_retry", return_value=SendResult(success=True)
        ):
            await sender.send_signal(signal1)

        # Second send should be rate limited
        result2 = await sender.send_signal(signal2)

        assert result2.success is False
        assert result2.suppressed is True
        assert "Rate limited" in result2.error

    @pytest.mark.asyncio
    async def test_send_batch(self, config) -> None:
        """Test sending batch of signals."""
        sender = AlertSender(config)

        signals = [
            Signal(
                token=f"TOKEN{i}",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                signal_id=f"signal-{i}",
            )
            for i in range(3)
        ]

        with mock.patch.object(
            sender, "_send_with_retry", return_value=SendResult(success=True)
        ):
            results = await sender.send_batch(signals)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_send_with_retry_success(self, config) -> None:
        """Test successful send with retry logic."""
        sender = AlertSender(config)

        with mock.patch.object(
            sender._get_client(),
            "send_message",
            return_value={
                "success": True,
                "message_id": "12345",
            },
        ):
            result = await sender._send_with_retry("Test message", "test-channel")

        assert result.success is True
        assert result.retries == 0

    @pytest.mark.asyncio
    async def test_send_with_retry_rate_limit(self, config) -> None:
        """Test retry on rate limit."""
        sender = AlertSender(config)

        # First call rate limited, second succeeds
        responses = [
            {"success": False, "error": "Rate limited", "retry_after": 0.01},
            {"success": True, "message_id": "12345"},
        ]

        with mock.patch.object(
            sender._get_client(), "send_message", side_effect=responses
        ):
            result = await sender._send_with_retry("Test message", "test-channel")

        assert result.success is True
        assert result.retries == 1

    @pytest.mark.asyncio
    async def test_send_with_retry_max_retries_exceeded(self, config) -> None:
        """Test failure after max retries."""
        config = DiscordConfig(
            webhook_url="https://test.webhook",
            max_retries=2,
            retry_base_delay=0.001,  # Fast for testing
        )
        sender = AlertSender(config)

        # Always fail
        with mock.patch.object(
            sender._get_client(),
            "send_message",
            return_value={"success": False, "error": "Network error"},
        ):
            result = await sender._send_with_retry("Test message", "test-channel")

        assert result.success is False
        assert result.retries == 2
        assert "Max retries exceeded" in result.error or "Network error" in result.error

    @pytest.mark.asyncio
    async def test_health_check(self, config) -> None:
        """Test health check."""
        sender = AlertSender(config)

        # Mock client health check
        with mock.patch.object(
            sender._get_client(),
            "health_check",
            return_value={"healthy": True, "connected": True},
        ):
            health = await sender.health_check()

        assert "healthy" in health
        assert "client" in health
        assert "rate_limiter" in health
        assert "suppressor" in health
        assert "config" in health

    @pytest.mark.asyncio
    async def test_close(self, config) -> None:
        """Test closing sender."""
        sender = AlertSender(config)

        # Initialize client
        client = sender._get_client()

        with mock.patch.object(client, "disconnect") as mock_disconnect:
            await sender.close()

        mock_disconnect.assert_called_once()

    def test_get_client_lazy_init(self, config) -> None:
        """Test lazy initialization of client."""
        sender = AlertSender(config)

        assert sender._client is None

        client = sender._get_client()

        assert client is not None
        assert sender._client is not None

    def test_get_formatter_lazy_init(self, config) -> None:
        """Test lazy initialization of formatter."""
        sender = AlertSender(config)

        assert sender._formatter is None

        formatter = sender._get_formatter()

        assert formatter is not None
        assert sender._formatter is not None

    def test_get_suppressor_lazy_init(self, config) -> None:
        """Test lazy initialization of suppressor."""
        sender = AlertSender(config)

        assert sender._suppressor is None

        suppressor = sender._get_suppressor()

        assert suppressor is not None
        assert sender._suppressor is not None

    def test_get_rate_limiter_lazy_init(self, config) -> None:
        """Test lazy initialization of rate limiter."""
        sender = AlertSender(config)

        assert sender._rate_limiter is None

        rate_limiter = sender._get_rate_limiter()

        assert rate_limiter is not None
        assert sender._rate_limiter is not None
