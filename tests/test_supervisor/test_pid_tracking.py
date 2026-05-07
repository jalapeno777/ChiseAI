"""Tests for PID file tracking and orphan process detection/cleanup.

Covers:
- Atomic PID file writes
- PID file removal
- Reading valid and invalid PID files
- Detecting running vs. stale PIDs
- Reaping orphan processes (process group kill)
- Edge cases: missing file, empty file, non-numeric content
"""

import os
import signal
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from src.supervisor.pid_tracker import PIDTracker


@pytest.fixture
def tmp_pid_file(tmp_path: Path) -> Path:
    """Return a path to a temporary PID file."""
    return tmp_path / "test-supervisor.pid"


@pytest.fixture
def tracker(tmp_pid_file: Path) -> PIDTracker:
    """Return a PIDTracker pointed at the temp PID file."""
    return PIDTracker(str(tmp_pid_file))


# ======================================================================
# Write / Read / Remove
# ======================================================================


class TestPIDFileIO:
    """Tests for PID file write, read, and remove operations."""

    def test_write_and_read_pid(self, tracker: PIDTracker) -> None:
        """Writing a PID then reading it back returns the same value."""
        tracker.write_pid(12345)
        assert tracker.read_pid() == 12345

    def test_write_creates_parent_dir(self, tmp_path: Path) -> None:
        """write_pid creates intermediate directories if needed."""
        pid_file = tmp_path / "nested" / "dir" / "supervisor.pid"
        t = PIDTracker(str(pid_file))
        t.write_pid(999)
        assert pid_file.exists()
        assert t.read_pid() == 999

    def test_write_overwrites_existing(self, tracker: PIDTracker) -> None:
        """A second write replaces the previous PID."""
        tracker.write_pid(100)
        tracker.write_pid(200)
        assert tracker.read_pid() == 200

    def test_write_is_atomic(self, tracker: PIDTracker) -> None:
        """No partial files should be visible (os.replace is atomic)."""
        tracker.write_pid(42)
        # The PID file should exist and be valid
        assert tracker.pid_file.exists()
        content = tracker.pid_file.read_text().strip()
        assert content == "42"
        # No leftover temp files
        tmp_files = list(tracker.pid_file.parent.glob(".supervisor-pid-*.tmp"))
        assert tmp_files == []

    def test_remove_pid_deletes_file(self, tracker: PIDTracker) -> None:
        """remove_pid deletes the PID file."""
        tracker.write_pid(555)
        assert tracker.pid_file.exists()
        tracker.remove_pid()
        assert not tracker.pid_file.exists()

    def test_remove_pid_idempotent(self, tracker: PIDTracker) -> None:
        """remove_pid on a missing file does not raise."""
        tracker.remove_pid()  # Should not raise FileNotFoundError

    def test_read_missing_file_returns_none(self, tracker: PIDTracker) -> None:
        """Reading a nonexistent PID file returns None."""
        assert tracker.read_pid() is None

    def test_read_empty_file_returns_none(self, tracker: PIDTracker) -> None:
        """An empty PID file returns None."""
        tracker.pid_file.write_text("")
        assert tracker.read_pid() is None

    def test_read_non_numeric_returns_none(self, tracker: PIDTracker) -> None:
        """A PID file with non-numeric content returns None."""
        tracker.pid_file.write_text("not-a-number")
        assert tracker.read_pid() is None

    def test_read_with_whitespace(self, tracker: PIDTracker) -> None:
        """Leading/trailing whitespace is stripped."""
        tracker.pid_file.write_text("  12345 \n")
        assert tracker.read_pid() == 12345


# ======================================================================
# Process detection
# ======================================================================


class TestIsPIDRunning:
    """Tests for is_pid_running."""

    def test_current_process_is_running(self, tracker: PIDTracker) -> None:
        """The current process PID is detected as running."""
        assert tracker.is_pid_running(os.getpid()) is True

    def test_nonexistent_pid(self, tracker: PIDTracker) -> None:
        """A PID that definitely doesn't exist returns False."""
        # Use a very high PID that won't exist
        assert tracker.is_pid_running(4194303) is False

    def test_init_process_is_running(self, tracker: PIDTracker) -> None:
        """PID 1 (init) is typically running on Linux."""
        assert tracker.is_pid_running(1) is True


# ======================================================================
# Orphan reaping
# ======================================================================


class TestReapOrphan:
    """Tests for orphan process detection and cleanup."""

    def test_reap_no_pid_file(self, tracker: PIDTracker) -> None:
        """No PID file → reap_orphan returns False."""
        assert tracker.reap_orphan() is False

    def test_reap_stale_pid(self, tracker: PIDTracker) -> None:
        """Stale PID (process no longer running) → file removed, returns False."""
        tracker.write_pid(4194303)  # non-existent PID
        assert tracker.reap_orphan() is False
        assert not tracker.pid_file.exists()

    def test_reap_real_orphan(self, tracker: PIDTracker) -> None:
        """A real orphan process is killed and the PID file removed."""
        # Start a sleep process in a new session (mimics supervisor child)
        proc = subprocess.Popen(
            ["sleep", "300"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid = proc.pid
        tracker.write_pid(pid)

        # Confirm process is alive
        assert tracker.is_pid_running(pid)

        # Patch grace period to keep tests fast
        import src.supervisor.pid_tracker as pt_mod

        original_grace = pt_mod._GRACE_PERIOD_SECONDS
        pt_mod._GRACE_PERIOD_SECONDS = 1

        try:
            result = tracker.reap_orphan()
            assert result is True
        finally:
            pt_mod._GRACE_PERIOD_SECONDS = original_grace

        # Process should be gone
        time.sleep(0.5)
        assert not tracker.is_pid_running(pid)
        assert not tracker.pid_file.exists()

        # Clean up just in case
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def test_reap_orphan_removes_stale_file_for_dead_pid(self, tmp_path: Path) -> None:
        """When PID is dead, file is cleaned up even though no kill happened."""
        tracker = PIDTracker(str(tmp_path / "orphan-test.pid"))
        tracker.write_pid(4194303)  # Definitely not running
        assert tracker.reap_orphan() is False
        assert tracker.read_pid() is None  # File removed


# ======================================================================
# Edge cases
# ======================================================================


class TestEdgeCases:
    """Edge cases for PIDTracker."""

    def test_concurrent_writers(self, tracker: PIDTracker) -> None:
        """Rapid sequential writes all produce valid files."""
        for pid in range(1, 100):
            tracker.write_pid(pid)
            assert tracker.read_pid() == pid

    @patch("os.killpg", side_effect=PermissionError("denied"))
    def test_kill_process_group_permission_error(
        self, mock_killpg: object, tracker: PIDTracker
    ) -> None:
        """_kill_process_group handles PermissionError gracefully."""
        # Should not raise
        tracker._kill_process_group(9999)

    @patch("os.killpg", side_effect=ProcessLookupError)
    def test_kill_process_group_already_gone(
        self, mock_killpg: object, tracker: PIDTracker
    ) -> None:
        """_kill_process_group handles ProcessLookupError gracefully."""
        tracker._kill_process_group(9999)
