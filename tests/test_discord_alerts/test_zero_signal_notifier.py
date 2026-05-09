"""Tests for zero-signal Discord notifier module.

Tests cover:
- Alert message formatting
- Recovery notification formatting
- Rate limiting behavior (15-min cooldown per datasource)
- Active alert tracking for recovery detection
- Discord client interaction patterns

Story: ST-MVP-006
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from discord_alerts.zero_signal_notifier import (
    COLOR_CRITICAL,
    COLOR_RECOVERY,
    SEVERITY_COLORS,
    SEVERITY_EMOJIS,
    ZeroSignalDiscordFormatter,
    ZeroSignalNotifier,
)


class TestZeroSignalDiscordFormatter:
    """Tests for ZeroSignalDiscordFormatter."""

    def test_format_zero_signal_alert_basic(self):
        """Should format a basic zero-signal alert."""
        result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
            datasource="binance",
            duration_minutes=45,
            window_count=3,
            severity="critical",
            event_count=5,
        )

        assert "content" in result
        assert "embeds" in result
        assert len(result["embeds"]) == 1

        embed = result["embeds"][0]
        assert "binance" in embed["title"]
        assert embed["color"] == COLOR_CRITICAL
        assert len(embed["fields"]) == 6

        # Check all required fields
        field_names = [f["name"] for f in embed["fields"]]
        assert "Datasource" in field_names
        assert "Duration" in field_names
        assert "Severity" in field_names
        assert "Event Count" in field_names

    def test_format_zero_signal_alert_severity_colors(self):
        """Should use correct color per severity."""
        for severity, expected_color in SEVERITY_COLORS.items():
            result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
                datasource="test",
                duration_minutes=20,
                window_count=1,
                severity=severity,
                event_count=1,
            )
            assert result["embeds"][0]["color"] == expected_color

    def test_format_zero_signal_alert_emojis(self):
        """Should use correct emoji per severity."""
        for severity, expected_emoji in SEVERITY_EMOJIS.items():
            if severity == "recovery":
                continue
            result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
                datasource="test",
                duration_minutes=20,
                window_count=1,
                severity=severity,
                event_count=1,
            )
            assert expected_emoji in result["content"]

    def test_format_zero_signal_alert_duration_formatting(self):
        """Should format short and long durations."""
        # Short duration
        result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
            datasource="test",
            duration_minutes=15,
            window_count=1,
            severity="warning",
            event_count=1,
        )
        assert "15m" in result["embeds"][0]["description"]

        # Long duration (hours)
        result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
            datasource="test",
            duration_minutes=90,
            window_count=6,
            severity="critical",
            event_count=3,
        )
        assert "1h 30m" in result["embeds"][0]["description"]

    def test_format_zero_signal_alert_last_signal_time(self):
        """Should format last signal timestamp."""
        # With timestamp
        ts = time.time() - 1800  # 30 min ago
        result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
            datasource="test",
            duration_minutes=30,
            window_count=2,
            severity="warning",
            event_count=1,
            last_signal_time=ts,
        )
        # Should contain a formatted date
        last_signal_field = [
            f for f in result["embeds"][0]["fields"] if f["name"] == "Last Signal"
        ]
        assert len(last_signal_field) == 1
        assert "UTC" in last_signal_field[0]["value"]

    def test_format_zero_signal_alert_no_last_signal(self):
        """Should handle missing last signal time."""
        result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
            datasource="test",
            duration_minutes=30,
            window_count=2,
            severity="warning",
            event_count=1,
            last_signal_time=None,
        )
        last_signal_field = [
            f for f in result["embeds"][0]["fields"] if f["name"] == "Last Signal"
        ]
        assert last_signal_field[0]["value"] == "Unknown"

    def test_format_zero_signal_alert_footer(self):
        """Should include footer."""
        result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
            datasource="test",
            duration_minutes=30,
            window_count=2,
            severity="warning",
            event_count=1,
        )
        assert result["embeds"][0]["footer"]["text"] == "ChiseAI Zero-Signal Monitor"

    def test_format_zero_signal_alert_timestamp(self):
        """Should include ISO timestamp."""
        result = ZeroSignalDiscordFormatter.format_zero_signal_alert(
            datasource="test",
            duration_minutes=30,
            window_count=2,
            severity="warning",
            event_count=1,
        )
        ts = result["embeds"][0]["timestamp"]
        assert ts.endswith("Z")
        assert "T" in ts


class TestZeroSignalDiscordFormatterRecovery:
    """Tests for recovery notification formatting."""

    def test_format_recovery_notification_basic(self):
        """Should format a basic recovery notification."""
        result = ZeroSignalDiscordFormatter.format_recovery_notification(
            datasource="binance",
            outage_duration_minutes=45,
            event_count=3,
        )

        assert "content" in result
        assert "embeds" in result
        assert len(result["embeds"]) == 1

        embed = result["embeds"][0]
        assert "binance" in embed["title"]
        assert "Resumed" in embed["title"]
        assert embed["color"] == COLOR_RECOVERY
        assert "✅" in result["content"]

    def test_format_recovery_notification_duration(self):
        """Should format outage duration correctly."""
        result = ZeroSignalDiscordFormatter.format_recovery_notification(
            datasource="test",
            outage_duration_minutes=120,
            event_count=5,
        )
        assert "2h 0m" in result["embeds"][0]["description"]

    def test_format_recovery_notification_fields(self):
        """Should include required fields."""
        result = ZeroSignalDiscordFormatter.format_recovery_notification(
            datasource="test",
            outage_duration_minutes=45,
            event_count=3,
        )

        field_names = [f["name"] for f in result["embeds"][0]["fields"]]
        assert "Datasource" in field_names
        assert "Outage Duration" in field_names
        assert "Total Events" in field_names


class TestZeroSignalNotifierRateLimiting:
    """Tests for rate limiting behavior."""

    def test_first_alert_not_rate_limited(self):
        """First alert should not be rate limited."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            cooldown_seconds=900,
        )

        assert not notifier._is_rate_limited("binance")

    def test_second_alert_rate_limited(self):
        """Second alert within cooldown should be rate limited."""
        notifier = ZeroSignalNotifier(cooldown_seconds=900)

        # Simulate first alert was sent
        notifier._last_alert_time["binance"] = time.time()

        assert notifier._is_rate_limited("binance")

    def test_alert_after_cooldown_not_rate_limited(self):
        """Alert after cooldown should not be rate limited."""
        notifier = ZeroSignalNotifier(cooldown_seconds=1)

        # Simulate alert sent 2 seconds ago (past 1s cooldown)
        notifier._last_alert_time["binance"] = time.time() - 2

        assert not notifier._is_rate_limited("binance")

    def test_time_until_available(self):
        """Should calculate remaining cooldown time."""
        notifier = ZeroSignalNotifier(cooldown_seconds=900)

        notifier._last_alert_time["binance"] = time.time() - 300  # 5 min ago

        remaining = notifier._time_until_available("binance")
        assert 590 < remaining < 610  # ~10 min remaining

    def test_time_until_available_no_alert(self):
        """Should return 0 for datasources with no prior alert."""
        notifier = ZeroSignalNotifier(cooldown_seconds=900)
        assert notifier._time_until_available("binance") == 0.0

    def test_different_datasources_independent(self):
        """Rate limits should be independent per datasource."""
        notifier = ZeroSignalNotifier(cooldown_seconds=900)

        notifier._last_alert_time["binance"] = time.time()

        assert notifier._is_rate_limited("binance")
        assert not notifier._is_rate_limited("kraken")

    def test_clear_rate_limit(self):
        """Should clear rate limit for a datasource."""
        notifier = ZeroSignalNotifier(cooldown_seconds=900)
        notifier._last_alert_time["binance"] = time.time()

        notifier.clear_rate_limit("binance")

        assert not notifier._is_rate_limited("binance")


class TestZeroSignalNotifierSending:
    """Tests for sending alerts."""

    @pytest.mark.asyncio
    async def test_send_zero_signal_alert_success(self):
        """Should send alert and return success result."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            channel_id="test-channel",
        )

        result = await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=45,
            window_count=3,
            severity="critical",
            event_count=5,
        )

        assert result.success is True
        assert result.datasource == "binance"
        assert result.notification_type == "alert"
        assert result.rate_limited is False
        assert result.error is None

        # Verify client was called with correct args
        mock_client.send_message.assert_called_once()
        call_kwargs = mock_client.send_message.call_args[1]
        assert call_kwargs["channel"] == "test-channel"
        assert len(call_kwargs["embeds"]) == 1
        assert "binance" in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_send_zero_signal_alert_rate_limited(self):
        """Should return rate-limited result when within cooldown."""
        mock_client = AsyncMock()
        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            cooldown_seconds=900,
        )

        # Simulate recent alert
        notifier._last_alert_time["binance"] = time.time()

        result = await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=45,
            window_count=3,
            severity="critical",
            event_count=5,
        )

        assert result.success is False
        assert result.rate_limited is True
        mock_client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_zero_signal_alert_client_error(self):
        """Should return error result when client fails."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(side_effect=Exception("Network error"))

        notifier = ZeroSignalNotifier(discord_client=mock_client)

        result = await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=45,
            window_count=3,
            severity="critical",
            event_count=5,
        )

        assert result.success is False
        assert result.error == "Network error"
        assert result.rate_limited is False

    @pytest.mark.asyncio
    async def test_send_zero_signal_alert_tracks_active(self):
        """Should track datasource as active after alert."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        notifier = ZeroSignalNotifier(discord_client=mock_client)

        await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=45,
            window_count=3,
            severity="critical",
            event_count=5,
        )

        assert notifier.has_active_alert("binance")
        assert "binance" in notifier.get_active_alerts()


class TestZeroSignalNotifierRecovery:
    """Tests for recovery notifications."""

    @pytest.mark.asyncio
    async def test_send_recovery_notification_success(self):
        """Should send recovery notification for active alert."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            enable_recovery_notices=True,
        )

        # Set up active alert
        notifier._active_alerts.add("binance")

        result = await notifier.send_recovery_notification(
            datasource="binance",
            outage_duration_minutes=45,
            event_count=3,
        )

        assert result.success is True
        assert result.notification_type == "recovery"
        assert not notifier.has_active_alert("binance")
        mock_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_recovery_no_active_alert(self):
        """Should skip recovery notification if no active alert."""
        mock_client = AsyncMock()
        notifier = ZeroSignalNotifier(discord_client=mock_client)

        result = await notifier.send_recovery_notification(
            datasource="binance",
            outage_duration_minutes=45,
            event_count=3,
        )

        assert result.success is False
        assert "No active alert" in result.error
        mock_client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_recovery_disabled(self):
        """Should skip recovery if recovery notices disabled."""
        mock_client = AsyncMock()
        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            enable_recovery_notices=False,
        )

        notifier._active_alerts.add("binance")

        result = await notifier.send_recovery_notification(
            datasource="binance",
            outage_duration_minutes=45,
            event_count=3,
        )

        assert result.success is False
        assert "disabled" in result.error

    @pytest.mark.asyncio
    async def test_recovery_clears_rate_limit(self):
        """Recovery should reset rate limit so next alert can fire."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            enable_recovery_notices=True,
        )

        # Set up active alert and rate limit
        notifier._active_alerts.add("binance")
        notifier._last_alert_time["binance"] = time.time()

        await notifier.send_recovery_notification(
            datasource="binance",
            outage_duration_minutes=45,
            event_count=3,
        )

        # Rate limit should be cleared
        assert not notifier._is_rate_limited("binance")


class TestZeroSignalNotifierReset:
    """Tests for notifier reset."""

    def test_reset_clears_all_state(self):
        """Should clear all tracking state."""
        notifier = ZeroSignalNotifier(cooldown_seconds=900)

        notifier._last_alert_time["binance"] = time.time()
        notifier._active_alerts.add("binance")
        notifier._active_alerts.add("kraken")

        notifier.reset()

        assert len(notifier._last_alert_time) == 0
        assert len(notifier._active_alerts) == 0
        assert not notifier.has_active_alert("binance")

    def test_get_active_alerts_returns_copy(self):
        """Should return a copy of active alerts."""
        notifier = ZeroSignalNotifier()
        notifier._active_alerts.add("binance")

        active = notifier.get_active_alerts()
        active.add("kraken")  # Modify the copy

        assert "kraken" not in notifier._active_alerts


class TestZeroSignalIntegration:
    """Integration tests for the full alert flow."""

    @pytest.mark.asyncio
    async def test_full_alert_lifecycle(self):
        """Should handle full alert → recovery lifecycle."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            cooldown_seconds=60,
            enable_recovery_notices=True,
        )

        # 1. Send initial alert
        result = await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=30,
            window_count=2,
            severity="warning",
            event_count=1,
        )
        assert result.success is True
        assert notifier.has_active_alert("binance")

        # 2. Try second alert (should be rate limited)
        result = await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=45,
            window_count=3,
            severity="critical",
            event_count=2,
        )
        assert result.success is False
        assert result.rate_limited is True

        # 3. Send recovery
        result = await notifier.send_recovery_notification(
            datasource="binance",
            outage_duration_minutes=45,
            event_count=2,
        )
        assert result.success is True
        assert not notifier.has_active_alert("binance")

        # 4. Can send new alert after recovery (rate limit cleared)
        assert not notifier._is_rate_limited("binance")

        # 5. Send new alert
        result = await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=15,
            window_count=1,
            severity="warning",
            event_count=3,
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_multiple_datasources_independent(self):
        """Should handle multiple datasources independently."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        notifier = ZeroSignalNotifier(
            discord_client=mock_client,
            cooldown_seconds=900,
        )

        # Alert for binance
        r1 = await notifier.send_zero_signal_alert(
            datasource="binance",
            duration_minutes=30,
            window_count=2,
            severity="warning",
            event_count=1,
        )
        assert r1.success is True

        # Alert for kraken (should not be rate limited)
        r2 = await notifier.send_zero_signal_alert(
            datasource="kraken",
            duration_minutes=20,
            window_count=1,
            severity="warning",
            event_count=1,
        )
        assert r2.success is True

        # Recovery for binance only
        r3 = await notifier.send_recovery_notification(
            datasource="binance",
            outage_duration_minutes=30,
            event_count=1,
        )
        assert r3.success is True

        # Kraken still active
        assert notifier.has_active_alert("kraken")
        assert not notifier.has_active_alert("binance")
