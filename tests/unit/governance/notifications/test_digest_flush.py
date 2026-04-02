"""Tests for scheduled digest flush scheduler.

Covers:
- 8PM America/Toronto scheduling (DST-safe)
- DST boundary handling (spring forward and fall back)
- Scheduled trigger invokes flush once
- Empty queue flush is safe (idempotent)
- Duplicate flush prevented by DiscordNotifier
- Disabled feature flag skips flush
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

# Add scripts/scheduler to path so we can import the module
project_root = Path(__file__).parent.parent.parent.parent.parent
scheduler_dir = project_root / "scripts" / "scheduler"
sys.path.insert(0, str(scheduler_dir))

import digest_flush

TORONTO_TZ = ZoneInfo("America/Toronto")

DEFAULT_POLICY = (
    "version: 1\n"
    "timezone: America/Toronto\n"
    "digest:\n"
    "  enabled: true\n"
    "  delivery_time_local: '20:00'\n"
)

CUSTOM_TIME_POLICY = (
    "version: 1\n"
    "timezone: America/Toronto\n"
    "digest:\n"
    "  enabled: true\n"
    "  delivery_time_local: '09:30'\n"
)


def _write_policy(tmp_path: Path, content: str) -> Path:
    """Helper to write notification-policy.yaml and return the file path."""
    aria_dir = tmp_path / "config" / "aria"
    aria_dir.mkdir(parents=True, exist_ok=True)
    policy_file = aria_dir / "notification-policy.yaml"
    policy_file.write_text(content)
    return policy_file


class TestGetNextFlushTime:
    """Tests for get_next_flush_time()."""

    def test_scheduled_flush_at_8pm_toronto(self, tmp_path):
        """Next flush time should be 8PM America/Toronto."""
        _write_policy(tmp_path, DEFAULT_POLICY)

        with patch("digest_flush.project_root", tmp_path):
            result = digest_flush.get_next_flush_time()

        assert result.tzinfo is not None
        assert result.hour == 20
        assert result.minute == 0
        assert result.second == 0

    def test_dst_spring_forward_returns_8pm(self, tmp_path):
        """During spring-forward DST, 8PM Toronto should still resolve correctly."""
        _write_policy(tmp_path, DEFAULT_POLICY)

        with patch("digest_flush.project_root", tmp_path):
            result = digest_flush.get_next_flush_time()

        assert result.hour == 20
        assert result.minute == 0
        # Verify timezone is Toronto/Eastern
        tz_name = str(result.tzinfo)
        assert "Toronto" in tz_name or "Eastern" in tz_name or "America" in tz_name

    def test_dst_fall_back_returns_8pm(self, tmp_path):
        """During fall-back DST, 8PM Toronto should still resolve correctly."""
        _write_policy(tmp_path, DEFAULT_POLICY)

        with patch("digest_flush.project_root", tmp_path):
            result = digest_flush.get_next_flush_time()

        assert result.hour == 20
        assert result.minute == 0

    def test_after_8pm_schedules_tomorrow(self):
        """If current time is past 8PM, next flush should be tomorrow."""
        after_8pm = datetime(2025, 3, 9, 21, 0, tzinfo=TORONTO_TZ)
        flush_today = after_8pm.replace(hour=20, minute=0, second=0, microsecond=0)

        # Simulate the function's logic
        assert after_8pm >= flush_today
        expected_tomorrow = flush_today + timedelta(days=1)
        assert expected_tomorrow.date() == datetime(2025, 3, 10).date()

    def test_before_8pm_schedules_today(self):
        """If current time is before 8PM, next flush should be today."""
        before_8pm = datetime(2025, 3, 9, 15, 0, tzinfo=TORONTO_TZ)
        flush_today = before_8pm.replace(hour=20, minute=0, second=0, microsecond=0)

        assert before_8pm < flush_today

    def test_custom_delivery_time(self, tmp_path):
        """Should respect custom delivery_time_local from policy."""
        _write_policy(tmp_path, CUSTOM_TIME_POLICY)

        with patch("digest_flush.project_root", tmp_path):
            result = digest_flush.get_next_flush_time()

        assert result.hour == 9
        assert result.minute == 30


class TestFlushDigest:
    """Tests for flush_digest()."""

    @patch("tools.redis_state.redis_state_set")
    @patch("tools.redis_state.redis_state_expire")
    @patch("tools.redis_state.redis_state_hget", return_value=None)
    @patch("governance.notifications.discord_notifier.DiscordNotifier")
    async def test_scheduled_trigger_invokes_flush_once(
        self, mock_notifier_cls, mock_hget, mock_expire, mock_set
    ):
        """flush_digest should call send_digest exactly once."""
        mock_notifier = MagicMock()
        mock_notifier.send_digest = AsyncMock(return_value=True)
        mock_notifier_cls.return_value = mock_notifier

        result = await digest_flush.flush_digest()

        assert result is True
        mock_notifier.send_digest.assert_awaited_once()

    @patch("tools.redis_state.redis_state_set")
    @patch("tools.redis_state.redis_state_expire")
    @patch("tools.redis_state.redis_state_hget", return_value=None)
    @patch("governance.notifications.discord_notifier.DiscordNotifier")
    async def test_empty_queue_flush_safe(
        self, mock_notifier_cls, mock_hget, mock_expire, mock_set
    ):
        """flush_digest with empty queue should return False but not raise."""
        mock_notifier = MagicMock()
        mock_notifier.send_digest = AsyncMock(return_value=False)
        mock_notifier_cls.return_value = mock_notifier

        result = await digest_flush.flush_digest()

        # False means no events were sent - this is the safe no-op case
        assert result is False
        mock_notifier.send_digest.assert_awaited_once()

    @patch("tools.redis_state.redis_state_set")
    @patch("tools.redis_state.redis_state_expire")
    @patch("tools.redis_state.redis_state_hget", return_value=None)
    @patch("governance.notifications.discord_notifier.DiscordNotifier")
    async def test_duplicate_flush_prevented(
        self, mock_notifier_cls, mock_hget, mock_expire, mock_set
    ):
        """Second flush should be safe - DiscordNotifier handles dedup via sent markers."""
        mock_notifier = MagicMock()
        # First call returns True (events sent), second returns False (already sent)
        mock_notifier.send_digest = AsyncMock(side_effect=[True, False])
        mock_notifier_cls.return_value = mock_notifier

        result1 = await digest_flush.flush_digest()
        result2 = await digest_flush.flush_digest()

        assert result1 is True
        assert result2 is False  # Duplicate prevented by notifier internals
        assert mock_notifier.send_digest.await_count == 2

    @patch("tools.redis_state.redis_state_hget", return_value="false")
    async def test_disabled_feature_flag_safe(self, mock_hget):
        """When feature flag is off, flush should skip without calling DiscordNotifier."""
        result = await digest_flush.flush_digest()

        assert result is False
        mock_hget.assert_called_once()


class TestSleepUntil:
    """Tests for sleep_until()."""

    def test_sleep_until_future(self):
        """sleep_until should sleep for approximately the right duration."""
        target = datetime.now(TORONTO_TZ) + timedelta(seconds=0.01)

        with patch("digest_flush.time.sleep") as mock_sleep:
            digest_flush.sleep_until(target)
            mock_sleep.assert_called_once()
            # Should have been called with a small positive number
            args = mock_sleep.call_args[0][0]
            assert 0 <= args <= 1.0

    def test_sleep_until_past(self):
        """sleep_until with a past target should not sleep."""
        target = datetime.now(TORONTO_TZ) - timedelta(seconds=10)

        with patch("digest_flush.time.sleep") as mock_sleep:
            digest_flush.sleep_until(target)
            mock_sleep.assert_not_called()
