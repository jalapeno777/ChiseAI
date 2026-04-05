"""Unit tests for signal deduplication module.

Tests cover:
- Duplicate signal detection based on signal_id
- Configurable dedup window
- Thread-safety for concurrent access
- Redis fallback when Redis unavailable
- filter_duplicates helper function
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

from signal_generation.dedup import (
    DedupResult,
    SignalDeduper,
    filter_duplicates,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus


def _make_signal(
    signal_id: str = "test-signal-001",
    token: str = "BTC/USDT",
    confidence: float = 0.8,
) -> Signal:
    """Helper to create a test Signal."""
    return Signal(
        token=token,
        direction=SignalDirection.LONG,
        confidence=confidence,
        base_score=70.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1H",
        signal_id=signal_id,
    )


class TestSignalDeduperBasic:
    """Basic deduplication tests."""

    def test_is_duplicate_returns_false_for_new_signal(self):
        """New signal should not be marked as duplicate."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("new-signal-001")

        result = deduper.is_duplicate(signal)

        assert result.is_duplicate is False
        assert result.signal_id == "new-signal-001"

    def test_is_duplicate_returns_true_for_same_signal_id(self):
        """Same signal_id should be marked as duplicate on second call."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("duplicate-signal-001")

        # First call - not a duplicate
        result1 = deduper.is_duplicate(signal)
        assert result1.is_duplicate is False

        # Second call with same signal_id - should be duplicate
        result2 = deduper.is_duplicate(signal)
        assert result2.is_duplicate is True
        assert result2.signal_id == "duplicate-signal-001"

    def test_is_duplicate_with_missing_signal_id_allows_through(self):
        """Signal without signal_id should be allowed through (not marked duplicate)."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("")
        signal.signal_id = ""  # Ensure empty

        result = deduper.is_duplicate(signal)

        assert result.is_duplicate is False
        assert result.signal_id == ""

    def test_different_signal_ids_are_not_duplicates(self):
        """Different signal_ids should not be marked as duplicates."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal1 = _make_signal("signal-001")
        signal2 = _make_signal("signal-002")

        result1 = deduper.is_duplicate(signal1)
        result2 = deduper.is_duplicate(signal2)

        assert result1.is_duplicate is False
        assert result2.is_duplicate is False


class TestDedupWindow:
    """Tests for configurable deduplication window."""

    def test_dedup_window_defaults_to_60_seconds(self):
        """Default dedup window should be 60 seconds."""
        deduper = SignalDeduper()
        assert deduper.dedup_window_seconds == 60.0

    def test_dedup_window_is_configurable(self):
        """Dedup window should be configurable."""
        deduper = SignalDeduper(dedup_window_seconds=120.0)
        assert deduper.dedup_window_seconds == 120.0

    def test_same_signal_after_window_expires_is_not_duplicate(self):
        """Signal after window expires should not be marked duplicate."""
        deduper = SignalDeduper(dedup_window_seconds=1.0)  # 1 second window
        signal = _make_signal("expiring-signal")

        result1 = deduper.is_duplicate(signal)
        assert result1.is_duplicate is False

        # Wait for window to expire
        time.sleep(1.1)

        result2 = deduper.is_duplicate(signal)
        assert result2.is_duplicate is False


class TestDedupResult:
    """Tests for DedupResult dataclass."""

    def test_dedup_result_contains_signal_id(self):
        """DedupResult should contain signal_id."""
        result = DedupResult(is_duplicate=False, signal_id="test-123")
        assert result.signal_id == "test-123"

    def test_dedup_result_has_window_info_for_duplicates(self):
        """Duplicate result should have window timing info."""
        now = time.time()
        result = DedupResult(
            is_duplicate=True,
            signal_id="dup-123",
            window_start=now - 60,
            window_end=now,
        )
        assert result.is_duplicate is True
        assert result.window_start is not None
        assert result.window_end is not None


class TestMarkSeen:
    """Tests for explicit mark_seen functionality."""

    def test_mark_seen_marks_signal_as_seen(self):
        """Marking a signal as seen should prevent duplicate detection."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("mark-seen-signal")

        # Explicitly mark as seen
        result = deduper.mark_seen(signal)
        assert result is True

        # Now check - should be duplicate
        dedup_result = deduper.is_duplicate(signal)
        assert dedup_result.is_duplicate is True

    def test_mark_seen_returns_false_for_empty_signal_id(self):
        """mark_seen should return False for empty signal_id."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("")
        signal.signal_id = ""

        result = deduper.mark_seen(signal)
        assert result is False


class TestClear:
    """Tests for clear functionality."""

    def test_clear_removes_specific_signal(self):
        """Clear should remove specific signal from dedup state."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("clear-me")

        # Mark as seen
        deduper.mark_seen(signal)
        assert deduper.is_duplicate(signal).is_duplicate is True

        # Clear it
        count = deduper.clear("clear-me")
        assert count == 1

        # Should no longer be duplicate
        assert deduper.is_duplicate(signal).is_duplicate is False

    def test_clear_none_removes_all_local(self):
        """Clear with None should clear local cache."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)

        # Add some signals
        deduper.mark_seen(_make_signal("clear-1"))
        deduper.mark_seen(_make_signal("clear-2"))

        # Clear all
        count = deduper.clear(None)
        assert count == 2

        # Stats should show empty
        stats = deduper.get_stats()
        assert stats["local_cache_entries"] == 0


class TestGetStats:
    """Tests for get_stats functionality."""

    def test_get_stats_returns_window_config(self):
        """Stats should include configured window."""
        deduper = SignalDeduper(dedup_window_seconds=45.0)
        stats = deduper.get_stats()

        assert stats["dedup_window_seconds"] == 45.0
        assert "local_cache_entries" in stats
        assert "redis_available" in stats

    def test_get_stats_shows_local_cache_count(self):
        """Stats should show local cache entry count."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)

        # Add signals
        deduper.mark_seen(_make_signal("stats-1"))
        deduper.mark_seen(_make_signal("stats-2"))

        stats = deduper.get_stats()
        assert stats["local_cache_entries"] == 2


class TestFilterDuplicates:
    """Tests for filter_duplicates helper function."""

    def test_filter_duplicates_returns_only_unique(self):
        """filter_duplicates should return only unique signals."""
        signal1 = _make_signal("unique-1")
        signal2 = _make_signal("unique-2")
        signal3 = _make_signal("unique-1")  # Duplicate of signal1

        signals = [signal1, signal2, signal3]
        unique, results = filter_duplicates(signals)

        assert len(unique) == 2
        assert unique[0].signal_id == "unique-1"
        assert unique[1].signal_id == "unique-2"

    def test_filter_duplicates_returns_dedup_results(self):
        """filter_duplicates should return dedup results for each signal."""
        signal1 = _make_signal("filter-1")
        signal2 = _make_signal("filter-1")  # Duplicate

        signals = [signal1, signal2]
        unique, results = filter_duplicates(signals)

        assert len(results) == 2
        assert results[0].is_duplicate is False
        assert results[1].is_duplicate is True

    def test_filter_duplicates_with_custom_deduper(self):
        """filter_duplicates should use provided deduper."""
        deduper = SignalDeduper(dedup_window_seconds=30.0)
        signal = _make_signal("custom-deduper")

        deduper.mark_seen(signal)  # Pre-mark

        signals = [signal]
        unique, results = filter_duplicates(signals, deduper=deduper)

        assert len(unique) == 0  # Should be filtered as duplicate
        assert results[0].is_duplicate is True


class TestThreadSafety:
    """Tests for thread-safety of deduplication."""

    def test_concurrent_is_duplicate_calls(self):
        """Concurrent calls should not cause race conditions."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("concurrent-signal")

        results: list[DedupResult] = []
        lock = threading.Lock()

        def check_duplicate():
            result = deduper.is_duplicate(signal)
            with lock:
                results.append(result)

        # Run concurrent checks
        threads = [threading.Thread(target=check_duplicate) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same result
        assert len(results) == 10
        # First call should be non-duplicate, rest should be duplicate
        duplicate_count = sum(1 for r in results if r.is_duplicate)
        assert duplicate_count == 9  # 9 duplicates after first

    def test_concurrent_mark_seen_calls(self):
        """Concurrent mark_seen calls should not cause errors."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)

        def mark_signal():
            deduper.mark_seen(_make_signal("thread-signal"))

        threads = [threading.Thread(target=mark_signal) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without error and have one entry
        stats = deduper.get_stats()
        assert stats["local_cache_entries"] >= 1


class TestRedisFallback:
    """Tests for Redis unavailability fallback."""

    def test_fallback_to_local_cache_when_redis_unavailable(self):
        """Should fall back to local cache when Redis unavailable."""
        # Create deduper with invalid Redis to force fallback
        deduper = SignalDeduper(
            redis_host="invalid-host",
            redis_port=9999,
            dedup_window_seconds=60.0,
        )

        signal = _make_signal("fallback-signal")

        # First call - not duplicate
        result1 = deduper.is_duplicate(signal)
        assert result1.is_duplicate is False

        # Second call - should use local cache fallback
        result2 = deduper.is_duplicate(signal)
        assert result2.is_duplicate is True

    def test_local_cache_fallback_still_works(self):
        """Local cache fallback should still detect duplicates."""
        deduper = SignalDeduper(
            redis_host="invalid-host",
            redis_port=9999,
            dedup_window_seconds=60.0,
        )
        signal = _make_signal("local-only-signal")

        deduper.mark_seen(signal)
        result = deduper.is_duplicate(signal)

        assert result.is_duplicate is True


class TestSignalMetadataPreservation:
    """Tests that signal metadata is preserved during dedup."""

    def test_signal_metadata_preserved_in_results(self):
        """Dedup results should reference signal_id, not modify signal."""
        deduper = SignalDeduper(dedup_window_seconds=60.0)
        signal = _make_signal("metadata-test", confidence=0.95)

        result1 = deduper.is_duplicate(signal)
        result2 = deduper.is_duplicate(signal)

        # Original signal should be unchanged
        assert signal.confidence == 0.95
        assert signal.signal_id == "metadata-test"

        # Results should reference the same signal_id
        assert result1.signal_id == "metadata-test"
        assert result2.signal_id == "metadata-test"
