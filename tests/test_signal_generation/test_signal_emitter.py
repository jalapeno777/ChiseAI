"""Tests for signal emitter module."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.signal_emitter import (
    CompositeEmitter,
    DashboardEmitter,
    DiscordEmitter,
    EmissionResult,
)


class TestEmissionResult:
    """Tests for EmissionResult dataclass."""

    def test_successful_result(self):
        """Test successful emission result."""
        result = EmissionResult(
            success=True, channel="discord", error=None, latency_ms=50.0
        )

        assert result.success is True
        assert result.channel == "discord"
        assert result.error is None
        assert result.latency_ms == 50.0

    def test_failed_result(self):
        """Test failed emission result."""
        result = EmissionResult(
            success=False, channel="discord", error="Connection timeout", latency_ms=0.0
        )

        assert result.success is False
        assert result.error == "Connection timeout"


class TestDiscordEmitter:
    """Tests for DiscordEmitter."""

    def test_initialization(self):
        """Test Discord emitter initialization."""
        emitter = DiscordEmitter(
            webhook_url="https://discord.com/api/webhooks/test",
            threshold=0.40,
            max_signals_per_hour=10,
        )

        assert emitter.name == "discord"
        assert emitter.webhook_url == "https://discord.com/api/webhooks/test"
        assert emitter.threshold == 0.40
        assert emitter.max_signals_per_hour == 10

    def test_default_threshold(self):
        """Test default Discord threshold is 40%."""
        emitter = DiscordEmitter()
        assert emitter.threshold == 0.40

    def test_webhook_from_env(self):
        """Test webhook URL from environment variable."""
        with patch.dict(
            "os.environ",
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/env"},
        ):
            emitter = DiscordEmitter()
            assert emitter.webhook_url == "https://discord.com/api/webhooks/env"

    @pytest.mark.asyncio
    async def test_emit_disabled_emitter(self):
        """Test emission when emitter is disabled."""
        emitter = DiscordEmitter()
        emitter.disable()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = await emitter.emit(signal)

        assert result.success is False
        assert result.error == "Emitter is disabled"

    @pytest.mark.asyncio
    async def test_emit_no_webhook(self):
        """Test emission without webhook URL."""
        with patch.dict("os.environ", {}, clear=True):
            emitter = DiscordEmitter(webhook_url=None)

            signal = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            )

            result = await emitter.emit(signal)

            assert result.success is False
            assert "No Discord webhook URL" in result.error

    @pytest.mark.asyncio
    async def test_emit_below_threshold(self):
        """Test emission of signal below Discord threshold."""
        emitter = DiscordEmitter(
            webhook_url="https://discord.com/api/webhooks/test", threshold=0.40
        )

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.30,  # Below 40% threshold
            base_score=40.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )

        result = await emitter.emit(signal)

        assert result.success is False
        assert "below Discord threshold" in result.error

    @pytest.mark.asyncio
    async def test_emit_rate_limit(self):
        """Test rate limiting."""
        emitter = DiscordEmitter(
            webhook_url="https://discord.com/api/webhooks/test",
            threshold=0.40,
            max_signals_per_hour=2,
        )

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        # First two should succeed (result unused but call required for rate limit)
        await emitter.emit(signal)
        await emitter.emit(signal)
        # Note: In actual implementation, these would succeed
        # Here we're testing the rate limit logic

        # Record signals manually to test rate limit
        emitter._record_signal("BTC/USDT")
        emitter._record_signal("BTC/USDT")

        # Third should fail due to rate limit
        result3 = await emitter.emit(signal)
        assert result3.success is False
        assert "Rate limit exceeded" in result3.error

    def test_rate_limit_check(self):
        """Test rate limit checking logic."""
        emitter = DiscordEmitter(max_signals_per_hour=3)

        # Should allow first 3
        assert emitter._check_rate_limit("BTC/USDT") is True
        emitter._record_signal("BTC/USDT")

        assert emitter._check_rate_limit("BTC/USDT") is True
        emitter._record_signal("BTC/USDT")

        assert emitter._check_rate_limit("BTC/USDT") is True
        emitter._record_signal("BTC/USDT")

        # Should block 4th
        assert emitter._check_rate_limit("BTC/USDT") is False

    @pytest.mark.asyncio
    async def test_emit_batch(self):
        """Test batch emission."""
        emitter = DiscordEmitter(webhook_url="https://discord.com/api/webhooks/test")

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.75,
                base_score=70.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
        ]

        results = await emitter.emit_batch(signals)

        assert len(results) == 2
        # Results may vary based on rate limiting


class TestDashboardEmitter:
    """Tests for DashboardEmitter."""

    def test_initialization(self):
        """Test dashboard emitter initialization."""
        emitter = DashboardEmitter(dashboard_url="http://localhost:8502")

        assert emitter.name == "dashboard"
        assert emitter.dashboard_url == "http://localhost:8502"

    @pytest.mark.asyncio
    async def test_emit_disabled(self):
        """Test emission when disabled."""
        emitter = DashboardEmitter()
        emitter.disable()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = await emitter.emit(signal)

        assert result.success is False
        assert result.error == "Emitter is disabled"

    @pytest.mark.asyncio
    async def test_emit_enabled(self):
        """Test emission when enabled."""
        emitter = DashboardEmitter()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = await emitter.emit(signal)

        # Should succeed (placeholder implementation)
        assert result.success is True
        assert result.channel == "dashboard"


class TestCompositeEmitter:
    """Tests for CompositeEmitter."""

    def test_initialization(self):
        """Test composite emitter initialization."""
        emitter = CompositeEmitter()

        assert emitter.name == "composite"
        assert emitter.emitters == []

    def test_add_emitter(self):
        """Test adding emitters."""
        composite = CompositeEmitter()
        discord = DiscordEmitter()
        dashboard = DashboardEmitter()

        composite.add_emitter(discord)
        composite.add_emitter(dashboard)

        assert len(composite.emitters) == 2

    @pytest.mark.asyncio
    async def test_emit_no_emitters(self):
        """Test emission with no emitters configured."""
        composite = CompositeEmitter()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = await composite.emit(signal)

        assert result.success is False
        assert result.error == "No emitters configured"

    @pytest.mark.asyncio
    async def test_emit_with_emitters(self):
        """Test emission with configured emitters."""
        composite = CompositeEmitter()

        # Add mock emitters
        mock_emitter1 = MagicMock()
        mock_emitter1.name = "mock1"
        mock_emitter1.emit = MagicMock(return_value=asyncio.Future())
        mock_emitter1.emit.return_value.set_result(
            EmissionResult(success=True, channel="mock1", latency_ms=10.0)
        )

        mock_emitter2 = MagicMock()
        mock_emitter2.name = "mock2"
        mock_emitter2.emit = MagicMock(return_value=asyncio.Future())
        mock_emitter2.emit.return_value.set_result(
            EmissionResult(success=True, channel="mock2", latency_ms=20.0)
        )

        composite.add_emitter(mock_emitter1)
        composite.add_emitter(mock_emitter2)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = await composite.emit(signal)

        assert result.success is True
        assert result.channel == "composite"
        assert result.latency_ms == 30.0  # Sum of both latencies

    @pytest.mark.asyncio
    async def test_emit_with_failure(self):
        """Test emission with one failing emitter."""
        composite = CompositeEmitter()

        # Add mock emitters - one succeeds, one fails
        mock_emitter1 = MagicMock()
        mock_emitter1.name = "mock1"
        mock_emitter1.emit = MagicMock(return_value=asyncio.Future())
        mock_emitter1.emit.return_value.set_result(
            EmissionResult(success=True, channel="mock1", latency_ms=10.0)
        )

        mock_emitter2 = MagicMock()
        mock_emitter2.name = "mock2"
        mock_emitter2.emit = MagicMock(return_value=asyncio.Future())
        mock_emitter2.emit.return_value.set_result(
            EmissionResult(
                success=False,
                channel="mock2",
                error="Connection failed",
                latency_ms=0.0,
            )
        )

        composite.add_emitter(mock_emitter1)
        composite.add_emitter(mock_emitter2)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = await composite.emit(signal)

        # Should succeed because one emitter succeeded
        assert result.success is True
        assert "Connection failed" in result.error

    @pytest.mark.asyncio
    async def test_emit_batch(self):
        """Test batch emission."""
        composite = CompositeEmitter()

        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_emitter.emit = MagicMock(return_value=asyncio.Future())
        mock_emitter.emit.return_value.set_result(
            EmissionResult(success=True, channel="mock", latency_ms=10.0)
        )

        composite.add_emitter(mock_emitter)

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.75,
                base_score=70.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
        ]

        results = await composite.emit_batch(signals)

        assert len(results) == 2
        assert all(r.success for r in results)
