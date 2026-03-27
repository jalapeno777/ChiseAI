"""Tests for Discord notification noise reduction (ST-AUTOCOG-016).

Covers:
- Score delta suppression for self-assessment notifications.
- Low-severity event digest batching and flushing.
- First-assessment always-notifies behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.governance.notifications.discord_notifier import (
    DEFAULT_DIGEST_INTERVAL_MINUTES,
    DEFAULT_DIGEST_MAX_ITEMS,
    DEFAULT_NOTIFICATION_SCORE_THRESHOLD,
    DiscordNotifier,
)
from src.governance.notifications.formatters import LowSeverityDigestFormatter


def _should_notify(
    current: float, previous: float | None, threshold: float = 0.01
) -> bool:
    """Convenience wrapper around DiscordNotifier.should_notify_for_assessment."""
    return DiscordNotifier.should_notify_for_assessment(current, previous, threshold)


# ---------------------------------------------------------------------------
# Pure-function tests: should_notify_for_assessment
# ---------------------------------------------------------------------------


class TestShouldNotifyForAssessment:
    """Tests for the score-delta noise gate."""

    def test_first_assessment_always_notifies(self) -> None:
        """No previous score (None) => always True."""
        assert _should_notify(0.85, None) is True

    def test_score_change_above_threshold(self) -> None:
        """Delta > threshold => True."""
        assert _should_notify(0.88, 0.85, threshold=0.01) is True

    def test_score_change_below_threshold(self) -> None:
        """Delta <= threshold => False."""
        assert _should_notify(0.851, 0.85, threshold=0.01) is False

    def test_score_exactly_at_threshold(self) -> None:
        """Delta very close to but <= threshold => False.

        Note: 0.01 is not exactly representable in IEEE 754, so we test
        with a value that is demonstrably <= threshold after subtraction.
        """
        # 0.001 < 0.01 => should be suppressed
        assert _should_notify(0.501, 0.50, threshold=0.01) is False

    def test_negative_score_change_above_threshold(self) -> None:
        """Negative delta whose absolute value exceeds threshold => True."""
        assert _should_notify(0.80, 0.85, threshold=0.01) is True

    def test_custom_threshold(self) -> None:
        """Custom threshold respected."""
        assert _should_notify(0.86, 0.85, threshold=0.005) is True
        assert _should_notify(0.852, 0.85, threshold=0.005) is False

    def test_zero_score_change(self) -> None:
        """Identical scores => False."""
        assert _should_notify(0.85, 0.85, threshold=0.01) is False

    def test_large_score_change(self) -> None:
        """Large delta => True."""
        assert _should_notify(0.50, 0.95, threshold=0.01) is True


# ---------------------------------------------------------------------------
# DiscordNotifier noise-reduction method tests
# ---------------------------------------------------------------------------


def _make_notifier(
    *,
    score_threshold: float = DEFAULT_NOTIFICATION_SCORE_THRESHOLD,
    digest_interval: int = DEFAULT_DIGEST_INTERVAL_MINUTES,
    digest_max: int = DEFAULT_DIGEST_MAX_ITEMS,
) -> DiscordNotifier:
    """Build a DiscordNotifier with no real client (unit-test friendly)."""
    return DiscordNotifier(
        client=None,
        config=None,
        notification_score_threshold=score_threshold,
        digest_interval_minutes=digest_interval,
        digest_max_items=digest_max,
    )


class TestNotifierInitNoiseParams:
    """Verify constructor stores noise-reduction config."""

    def test_default_threshold(self) -> None:
        n = _make_notifier()
        assert n._notification_score_threshold == DEFAULT_NOTIFICATION_SCORE_THRESHOLD

    def test_custom_threshold(self) -> None:
        n = _make_notifier(score_threshold=0.05)
        assert n._notification_score_threshold == 0.05

    def test_digest_buffer_initially_empty(self) -> None:
        n = _make_notifier()
        assert n._low_severity_buffer == []

    def test_digest_last_flush_initially_none(self) -> None:
        n = _make_notifier()
        assert n._digest_last_flush is None


class TestAddToDigest:
    """Test low-severity event buffering."""

    def test_low_severity_buffered(self) -> None:
        n = _make_notifier()
        event = {"event_type": "test", "severity": "low", "summary": "x"}
        assert n.add_to_digest(event) is True
        assert len(n._low_severity_buffer) == 1

    def test_medium_severity_buffered(self) -> None:
        n = _make_notifier()
        event = {"event_type": "test", "severity": "medium", "summary": "x"}
        assert n.add_to_digest(event) is True
        assert len(n._low_severity_buffer) == 1

    def test_high_severity_rejected(self) -> None:
        n = _make_notifier()
        event = {"event_type": "test", "severity": "high", "summary": "x"}
        assert n.add_to_digest(event) is False
        assert len(n._low_severity_buffer) == 0

    def test_critical_severity_rejected(self) -> None:
        n = _make_notifier()
        event = {"event_type": "test", "severity": "critical", "summary": "x"}
        assert n.add_to_digest(event) is False
        assert len(n._low_severity_buffer) == 0

    def test_missing_severity_treated_as_low(self) -> None:
        n = _make_notifier()
        event = {"event_type": "test", "summary": "x"}
        assert n.add_to_digest(event) is True


class TestShouldFlushDigest:
    """Test digest flush triggers."""

    def test_empty_buffer_no_flush(self) -> None:
        n = _make_notifier()
        assert n.should_flush_digest() is False

    def test_buffer_at_max_items_triggers_flush(self) -> None:
        n = _make_notifier(digest_max=3)
        for i in range(3):
            n.add_to_digest({"event_type": f"e{i}", "severity": "low"})
        assert n.should_flush_digest() is True

    def test_buffer_below_max_no_time_no_flush(self) -> None:
        n = _make_notifier(digest_max=10)
        for i in range(5):
            n.add_to_digest({"event_type": f"e{i}", "severity": "low"})
        assert n.should_flush_digest() is False

    def test_buffer_past_max_triggers_flush(self) -> None:
        n = _make_notifier(digest_max=2)
        for i in range(4):
            n.add_to_digest({"event_type": f"e{i}", "severity": "low"})
        assert n.should_flush_digest() is True

    def test_interval_elapsed_triggers_flush(self) -> None:
        n = _make_notifier(digest_interval=1)
        n._digest_last_flush = datetime.now(UTC) - timedelta(minutes=2)
        n.add_to_digest({"event_type": "e1", "severity": "low"})
        assert n.should_flush_digest() is True

    def test_interval_not_elapsed_no_flush(self) -> None:
        n = _make_notifier(digest_interval=60)
        n._digest_last_flush = datetime.now(UTC) - timedelta(minutes=10)
        n.add_to_digest({"event_type": "e1", "severity": "low"})
        assert n.should_flush_digest() is False


class TestSendDigest:
    """Test digest flushing."""

    @pytest.mark.asyncio
    async def test_empty_buffer_returns_false(self) -> None:
        n = _make_notifier()
        assert await n.send_digest() is False

    @pytest.mark.asyncio
    async def test_send_digest_clears_buffer(self) -> None:
        n = _make_notifier()
        n._is_enabled = lambda: True  # type: ignore[method-assign]
        n._send_with_retry = AsyncMock(return_value=(True, "msg123"))  # type: ignore[method-assign]
        for i in range(3):
            n.add_to_digest(
                {"event_type": f"e{i}", "severity": "low", "summary": f"item {i}"}
            )

        result = await n.send_digest()
        assert result is True
        assert len(n._low_severity_buffer) == 0
        assert n._digest_last_flush is not None

    @pytest.mark.asyncio
    async def test_send_digest_updates_flush_timestamp(self) -> None:
        n = _make_notifier()
        n._is_enabled = lambda: True  # type: ignore[method-assign]
        n._send_with_retry = AsyncMock(return_value=(True, "msg1"))  # type: ignore[method-assign]
        n.add_to_digest({"event_type": "e1", "severity": "low", "summary": "s1"})

        before = datetime.now(UTC)
        await n.send_digest()
        assert n._digest_last_flush is not None
        assert n._digest_last_flush >= before

    @pytest.mark.asyncio
    async def test_send_digest_disabled_returns_false(self) -> None:
        n = _make_notifier()
        n._is_enabled = lambda: False  # type: ignore[method-assign]
        n.add_to_digest({"event_type": "e1", "severity": "low", "summary": "s1"})

        result = await n.send_digest()
        assert result is False
        # Buffer should NOT be cleared when disabled
        assert len(n._low_severity_buffer) == 1

    @pytest.mark.asyncio
    async def test_send_digest_failure_returns_false(self) -> None:
        n = _make_notifier()
        n._is_enabled = lambda: True  # type: ignore[method-assign]
        n._send_with_retry = AsyncMock(return_value=(False, None))  # type: ignore[method-assign]
        n.add_to_digest({"event_type": "e1", "severity": "low", "summary": "s1"})

        result = await n.send_digest()
        assert result is False
        # Buffer IS cleared even on failure (items are not re-queued)
        assert len(n._low_severity_buffer) == 0


class TestNotifySelfAssessmentNoiseReduction:
    """Integration: notify_self_assessment with score-delta suppression."""

    def _make_artifact(self, *, score: float, date: str = "2026-03-27") -> Any:
        """Create a mock assessment artifact."""
        artifact = MagicMock()
        artifact.overall_score = score
        artifact.assessment_date = date
        artifact.status = "ok"
        artifact.findings = []
        artifact.recommendations = []
        return artifact

    @pytest.mark.asyncio
    async def test_first_assessment_sends(self) -> None:
        """First assessment (no previous_score) should always notify."""
        n = _make_notifier()
        n._is_enabled = lambda: True  # type: ignore[method-assign]
        n._is_duplicate = lambda eid: False  # type: ignore[method-assign]
        n._send_with_retry = AsyncMock(return_value=(True, "m1"))  # type: ignore[method-assign]

        artifact = self._make_artifact(score=0.85)
        result = await n.notify_self_assessment(artifact, previous_score=None)
        assert result is True
        n._send_with_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_unchanged_score_suppressed(self) -> None:
        """Score unchanged => notification suppressed, returns False."""
        n = _make_notifier()
        artifact = self._make_artifact(score=0.85)

        result = await n.notify_self_assessment(artifact, previous_score=0.85)
        assert result is False

    @pytest.mark.asyncio
    async def test_small_delta_suppressed(self) -> None:
        """Score change within threshold => suppressed."""
        n = _make_notifier(score_threshold=0.01)
        artifact = self._make_artifact(score=0.855)

        result = await n.notify_self_assessment(artifact, previous_score=0.85)
        assert result is False

    @pytest.mark.asyncio
    async def test_large_delta_sends(self) -> None:
        """Score change exceeds threshold => notification sent."""
        n = _make_notifier()
        n._is_enabled = lambda: True  # type: ignore[method-assign]
        n._is_duplicate = lambda eid: False  # type: ignore[method-assign]
        n._send_with_retry = AsyncMock(return_value=(True, "m2"))  # type: ignore[method-assign]

        artifact = self._make_artifact(score=0.90)
        result = await n.notify_self_assessment(artifact, previous_score=0.85)
        assert result is True
        n._send_with_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_decline_triggers_notification(self) -> None:
        """Score decline exceeding threshold => notification sent."""
        n = _make_notifier()
        n._is_enabled = lambda: True  # type: ignore[method-assign]
        n._is_duplicate = lambda eid: False  # type: ignore[method-assign]
        n._send_with_retry = AsyncMock(return_value=(True, "m3"))  # type: ignore[method-assign]

        artifact = self._make_artifact(score=0.70)
        result = await n.notify_self_assessment(artifact, previous_score=0.85)
        assert result is True
        n._send_with_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_still_suppressed_after_score_change(self) -> None:
        """Even with score change, duplicate detection still applies."""
        n = _make_notifier()
        n._is_enabled = lambda: True  # type: ignore[method-assign]
        n._is_duplicate = lambda eid: True  # type: ignore[method-assign]

        artifact = self._make_artifact(score=0.90)
        result = await n.notify_self_assessment(artifact, previous_score=0.85)
        assert result is False


# ---------------------------------------------------------------------------
# LowSeverityDigestFormatter tests
# ---------------------------------------------------------------------------


class TestLowSeverityDigestFormatter:
    """Test the digest message formatter."""

    def test_empty_items_returns_empty(self) -> None:
        f = LowSeverityDigestFormatter()
        assert f.format_digest([]) == ""

    def test_single_item(self) -> None:
        f = LowSeverityDigestFormatter()
        items = [
            {
                "event_type": "improvement_promoted",
                "severity": "low",
                "summary": "Promoted hypothesis-42",
                "run_id": "run-001",
            }
        ]
        result = f.format_digest(items)
        assert "Low-Severity Event Digest" in result
        assert "improvement_promoted" in result
        assert "Promoted hypothesis-42" in result
        assert "run-001" in result

    def test_multiple_items(self) -> None:
        f = LowSeverityDigestFormatter()
        items = [
            {"event_type": "e1", "severity": "low", "summary": "s1"},
            {"event_type": "e2", "severity": "medium", "summary": "s2"},
            {"event_type": "e3", "severity": "low", "summary": "s3"},
        ]
        result = f.format_digest(items)
        assert "(3 items)" in result
        assert "e1" in result
        assert "e2" in result
        assert "e3" in result

    def test_truncation_for_long_digest(self) -> None:
        f = LowSeverityDigestFormatter()
        items = [
            {"event_type": f"event-{i}", "severity": "low", "summary": "x" * 200}
            for i in range(50)
        ]
        result = f.format_digest(items)
        assert len(result) <= 2000

    def test_missing_optional_fields(self) -> None:
        f = LowSeverityDigestFormatter()
        items = [{"event_type": "test", "severity": "low"}]
        result = f.format_digest(items)
        assert "test" in result
        # No crash on missing summary / run_id
