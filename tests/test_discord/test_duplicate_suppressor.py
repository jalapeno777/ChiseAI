"""Tests for duplicate suppressor.

Tests for ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import time

from discord_alerts.duplicate_suppressor import AlertRecord, DuplicateSuppressor


class TestAlertRecord:
    """Test cases for AlertRecord dataclass."""

    def test_alert_record_creation(self) -> None:
        """Test creating an alert record."""
        record = AlertRecord(
            signal_id="test-signal-123",
            token="BTC/USDT",
            direction="LONG",
            confidence=0.85,
        )

        assert record.signal_id == "test-signal-123"
        assert record.token == "BTC/USDT"
        assert record.direction == "LONG"
        assert record.confidence == 0.85
        assert record.timestamp <= time.time()


class TestDuplicateSuppressor:
    """Test cases for DuplicateSuppressor."""

    def test_default_window(self) -> None:
        """Test default suppression window is 15 minutes."""
        suppressor = DuplicateSuppressor()
        assert suppressor.window_seconds == 900  # 15 minutes
        assert suppressor.enable_suppression is True

    def test_custom_window(self) -> None:
        """Test custom suppression window."""
        suppressor = DuplicateSuppressor(window_seconds=300)
        assert suppressor.window_seconds == 300

    def test_suppression_disabled(self) -> None:
        """Test suppression can be disabled."""
        suppressor = DuplicateSuppressor(enable_suppression=False)
        assert suppressor.enable_suppression is False

    def test_is_duplicate_no_record(self) -> None:
        """Test no duplicate when no record exists."""
        suppressor = DuplicateSuppressor()

        is_dup = suppressor.is_duplicate("BTC/USDT", "LONG")

        assert is_dup is False

    def test_is_duplicate_with_record(self) -> None:
        """Test duplicate detection with existing record."""
        suppressor = DuplicateSuppressor()

        # Record an alert
        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)

        # Same token+direction should be duplicate
        is_dup = suppressor.is_duplicate("BTC/USDT", "LONG")

        assert is_dup is True

    def test_is_duplicate_different_token(self) -> None:
        """Test no duplicate for different token."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)

        is_dup = suppressor.is_duplicate("ETH/USDT", "LONG")

        assert is_dup is False

    def test_is_duplicate_different_direction(self) -> None:
        """Test no duplicate for different direction."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)

        is_dup = suppressor.is_duplicate("BTC/USDT", "SHORT")

        assert is_dup is False

    def test_is_duplicate_after_window(self) -> None:
        """Test no duplicate after suppression window expires."""
        suppressor = DuplicateSuppressor(window_seconds=0.1)

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)

        # Wait for window to expire
        time.sleep(0.15)

        is_dup = suppressor.is_duplicate("BTC/USDT", "LONG")

        assert is_dup is False

    def test_is_duplicate_with_signal_id(self) -> None:
        """Test duplicate detection with signal ID."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-123", 0.85)

        # Same signal ID should be duplicate
        is_dup = suppressor.is_duplicate("BTC/USDT", "LONG", "signal-123")

        assert is_dup is True

    def test_is_duplicate_different_signal_id(self) -> None:
        """Test duplicate detection with different signal ID."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-123", 0.85)

        # Different signal ID but same token+direction within window is duplicate
        is_dup = suppressor.is_duplicate("BTC/USDT", "LONG", "signal-456")

        assert is_dup is True

    def test_should_send_new_alert(self) -> None:
        """Test should_send returns True for new alert."""
        suppressor = DuplicateSuppressor()

        result = suppressor.should_send("BTC/USDT", "LONG", "signal-1", 0.85)

        assert result is True

    def test_should_send_duplicate(self) -> None:
        """Test should_send returns False for duplicate."""
        suppressor = DuplicateSuppressor()

        suppressor.should_send("BTC/USDT", "LONG", "signal-1", 0.85)
        result = suppressor.should_send("BTC/USDT", "LONG", "signal-2", 0.90)

        assert result is False

    def test_should_send_suppression_disabled(self) -> None:
        """Test should_send returns True when suppression disabled."""
        suppressor = DuplicateSuppressor(enable_suppression=False)

        suppressor.should_send("BTC/USDT", "LONG", "signal-1", 0.85)
        result = suppressor.should_send("BTC/USDT", "LONG", "signal-2", 0.90)

        assert result is True

    def test_cleanup_old_entries(self) -> None:
        """Test cleanup of old entries."""
        suppressor = DuplicateSuppressor(window_seconds=0.1)

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)
        suppressor.record_alert("ETH/USDT", "SHORT", "signal-2", 0.75)

        # Wait for window to expire
        time.sleep(0.15)

        removed = suppressor.cleanup()

        assert removed == 2
        assert len(suppressor._alerts) == 0

    def test_cleanup_partial(self) -> None:
        """Test cleanup only removes expired entries."""
        suppressor = DuplicateSuppressor(window_seconds=1.0)

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)

        # Wait a bit but not full window
        time.sleep(0.1)

        suppressor.record_alert("ETH/USDT", "SHORT", "signal-2", 0.75)

        # First entry should be expired, second should remain
        # But we need to wait for first to expire
        time.sleep(0.95)  # Total ~1.05s since first record

        removed = suppressor.cleanup()

        assert removed == 1
        assert len(suppressor._alerts) == 1

    def test_clear(self) -> None:
        """Test clearing all records."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)
        suppressor.record_alert("ETH/USDT", "SHORT", "signal-2", 0.75)

        suppressor.clear()

        assert len(suppressor._alerts) == 0

    def test_get_stats(self) -> None:
        """Test getting suppressor statistics."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)
        suppressor.record_alert("BTC/USDT", "SHORT", "signal-2", 0.75)
        suppressor.record_alert("ETH/USDT", "LONG", "signal-3", 0.80)

        stats = suppressor.get_stats()

        assert stats["enabled"] is True
        assert stats["window_seconds"] == 900
        assert stats["active_records"] == 3
        assert stats["unique_tokens"] == 2  # BTC/USDT and ETH/USDT

    def test_get_recent_alerts(self) -> None:
        """Test getting recent alerts."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)
        suppressor.record_alert("ETH/USDT", "SHORT", "signal-2", 0.75)

        alerts = suppressor.get_recent_alerts()

        assert len(alerts) == 2

    def test_get_recent_alerts_filtered(self) -> None:
        """Test getting recent alerts with filters."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)
        suppressor.record_alert("ETH/USDT", "SHORT", "signal-2", 0.75)

        alerts = suppressor.get_recent_alerts(token="BTC/USDT")

        assert len(alerts) == 1
        assert alerts[0].token == "BTC/USDT"

    def test_thread_safety(self) -> None:
        """Test thread-safe operations."""
        import threading

        suppressor = DuplicateSuppressor()
        errors = []

        def record_alerts():
            try:
                for i in range(10):
                    suppressor.record_alert(f"TOKEN{i}", "LONG", f"signal-{i}", 0.85)
            except Exception as e:
                errors.append(e)

        # Run multiple threads concurrently
        threads = [threading.Thread(target=record_alerts) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(suppressor._alerts) == 10  # 10 unique tokens

    def test_case_insensitive_direction(self) -> None:
        """Test direction is case insensitive."""
        suppressor = DuplicateSuppressor()

        suppressor.record_alert("BTC/USDT", "LONG", "signal-1", 0.85)

        # lowercase should be treated same as uppercase
        is_dup = suppressor.is_duplicate("BTC/USDT", "long")

        assert is_dup is True
