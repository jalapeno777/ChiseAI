"""Tests for the signal generator supervisor.

Covers:
- Supervisor tracks exactly one child process at any time
- No orphan children after supervisor restart
- PID file is always accurate and up-to-date
- Signal handling (SIGTERM, SIGKILL scenarios)
- File handle management (no leaks)
- Backoff circuit breaker
- Process group management
"""

import os
import signal
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from src.supervisor.supervisor import SignalGeneratorSupervisor


@pytest.fixture
def tmp_dirs(tmp_path: Path):
    """Create temporary log and PID file directories."""
    log_dir = tmp_path / "logs"
    pid_file = tmp_path / "run" / "supervisor.pid"
    log_dir.mkdir()
    pid_file.parent.mkdir(parents=True)
    return log_dir, pid_file


@pytest.fixture
def supervisor(tmp_dirs):
    """Return a supervisor with temp directories and no Redis."""
    log_dir, pid_file = tmp_dirs
    with patch(
        "src.supervisor.supervisor.SignalGeneratorSupervisor._init_redis",
        return_value=None,
    ):
        sup = SignalGeneratorSupervisor(
            signal_generator_script="true",  # no-op command
            log_dir=str(log_dir),
            pid_file=str(pid_file),
            restart_delay_seconds=0,
        )
    return sup


def _start_dummy_process(supervisor: SignalGeneratorSupervisor) -> None:
    """Start a short-lived dummy child process on the supervisor."""
    # Patch the script path to use a simple command
    supervisor.script_path = "true"
    supervisor._start_process()


# ======================================================================
# AC-1: Supervisor tracks exactly one child process at any time
# ======================================================================


class TestSingleChildProcess:
    """Acceptance criterion: exactly one child at any time."""

    def test_process_is_none_before_start(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """Before start(), no child process exists."""
        assert supervisor.process is None

    def test_start_creates_single_process(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """_start_process creates exactly one subprocess.Popen."""
        supervisor.script_path = "sleep"
        supervisor._start_process()
        assert supervisor.process is not None
        assert supervisor.process.poll() is None  # still running
        supervisor._stop_process()

    def test_restart_stops_old_before_starting_new(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """Calling _start_process twice doesn't leave two children running."""
        supervisor.script_path = "sleep"
        supervisor._start_process()
        first_pid = supervisor.process.pid
        assert first_pid is not None

        # Start again — old process should be stopped first
        supervisor._start_process()
        second_pid = supervisor.process.pid

        # First child should be dead
        time.sleep(0.3)
        try:
            os.kill(first_pid, 0)
            pytest.fail("First child should have been terminated")
        except ProcessLookupError:
            pass  # Expected

        # Only the second child should be alive
        assert supervisor.process is not None
        assert supervisor.process.pid == second_pid

        supervisor._stop_process()


# ======================================================================
# AC-2: No orphan children after supervisor restart
# ======================================================================


class TestOrphanCleanup:
    """Acceptance criterion: no orphans after restart."""

    def test_orphan_killed_on_new_supervisor_start(self, tmp_dirs) -> None:
        """A new supervisor instance kills orphaned children from a previous instance."""
        log_dir, pid_file = tmp_dirs

        # Simulate a previous supervisor that left a child running
        orphan = subprocess.Popen(
            ["sleep", "300"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        orphan_pid = orphan.pid

        # Write the orphan's PID to the PID file
        from src.supervisor.pid_tracker import PIDTracker

        tracker = PIDTracker(str(pid_file))
        tracker.write_pid(orphan_pid)

        # Patch grace period for fast tests
        import src.supervisor.pid_tracker as pt_mod

        original_grace = pt_mod._GRACE_PERIOD_SECONDS
        pt_mod._GRACE_PERIOD_SECONDS = 1

        try:
            # New supervisor instance detects and kills the orphan
            with patch(
                "src.supervisor.supervisor.SignalGeneratorSupervisor._init_redis",
                return_value=None,
            ):
                sup = SignalGeneratorSupervisor(
                    signal_generator_script="true",
                    log_dir=str(log_dir),
                    pid_file=str(pid_file),
                    restart_delay_seconds=0,
                )
                result = sup.pid_tracker.reap_orphan()
                assert result is True
        finally:
            pt_mod._GRACE_PERIOD_SECONDS = original_grace

        # Orphan should be dead
        time.sleep(0.5)
        assert not tracker.is_pid_running(orphan_pid)

        # Clean up just in case
        try:
            os.killpg(orphan_pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def test_stale_pid_file_cleaned_on_start(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """A stale PID file (process gone) is removed on startup."""
        # Write a PID that doesn't exist
        supervisor.pid_tracker.write_pid(4194303)
        assert supervisor.pid_tracker.read_pid() == 4194303

        # reap_orphan should clean it up
        supervisor.pid_tracker.reap_orphan()
        assert supervisor.pid_tracker.read_pid() is None


# ======================================================================
# AC-3: PID file is always accurate and up-to-date
# ======================================================================


class TestPIDFileAccuracy:
    """Acceptance criterion: PID file always reflects reality."""

    def test_pid_file_matches_child_pid(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """After starting a child, the PID file matches the child's PID."""
        supervisor.script_path = "sleep"
        supervisor._start_process()

        child_pid = supervisor.process.pid
        pid_from_file = supervisor.pid_tracker.read_pid()

        assert pid_from_file == child_pid
        supervisor._stop_process()

    def test_pid_file_removed_after_stop(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """After stopping a child, the PID file is removed."""
        supervisor.script_path = "sleep"
        supervisor._start_process()
        assert supervisor.pid_tracker.read_pid() is not None

        supervisor._stop_process()
        assert supervisor.pid_tracker.read_pid() is None

    def test_pid_file_removed_after_crash_recovery(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """When a child exits (crash), _monitor_process cleans up the PID file."""
        supervisor.script_path = "true"  # exits immediately
        supervisor._start_process()
        assert supervisor.pid_tracker.read_pid() is not None

        # Wait for the process to exit
        time.sleep(0.3)

        # Simulate monitoring loop
        supervisor._monitor_process()

        # PID file should be cleaned up
        assert supervisor.pid_tracker.read_pid() is None


# ======================================================================
# AC-4: Signal handling
# ======================================================================


class TestSignalHandling:
    """Signal handling for clean shutdown."""

    def test_sigterm_sets_running_false(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """SIGTERM handler sets running to False."""
        supervisor.running = True
        supervisor._handle_shutdown(signal.SIGTERM, None)
        assert supervisor.running is False

    def test_sigint_sets_running_false(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """SIGINT handler sets running to False."""
        supervisor.running = True
        supervisor._handle_shutdown(signal.SIGINT, None)
        assert supervisor.running is False

    def test_stop_process_kills_child(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """_stop_process terminates the child process."""
        supervisor.script_path = "sleep"
        supervisor._start_process()
        child_pid = supervisor.process.pid

        supervisor._stop_process()

        # Process should be None
        assert supervisor.process is None

        # Child should be dead
        time.sleep(0.3)
        assert not supervisor.pid_tracker.is_pid_running(child_pid)


# ======================================================================
# AC-5: File handle management
# ======================================================================


class TestFileHandles:
    """File handles for stdout/stderr are properly managed."""

    def test_file_handles_opened_on_start(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """_start_process opens stdout and stderr file handles."""
        supervisor.script_path = "sleep"
        supervisor._start_process()

        assert supervisor._stdout_file is not None
        assert supervisor._stderr_file is not None
        assert not supervisor._stdout_file.closed
        assert not supervisor._stderr_file.closed

        supervisor._stop_process()

    def test_file_handles_closed_on_stop(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """_stop_process closes stdout and stderr file handles."""
        supervisor.script_path = "sleep"
        supervisor._start_process()

        stdout_fh = supervisor._stdout_file
        stderr_fh = supervisor._stderr_file

        supervisor._stop_process()

        assert stdout_fh.closed
        assert stderr_fh.closed

    def test_file_handles_closed_on_process_exit(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """File handles are closed when the process exits (via _monitor_process)."""
        supervisor.script_path = "true"  # exits immediately
        supervisor._start_process()

        stdout_fh = supervisor._stdout_file
        stderr_fh = supervisor._stderr_file

        # Wait for exit
        time.sleep(0.3)
        supervisor._monitor_process()

        assert stdout_fh.closed
        assert stderr_fh.closed


# ======================================================================
# Process group management
# ======================================================================


class TestProcessGroup:
    """Child runs in its own session/process group."""

    def test_child_has_own_session(self, supervisor: SignalGeneratorSupervisor) -> None:
        """Child process has its own session ID (different from parent)."""
        supervisor.script_path = "sleep"
        supervisor._start_process()

        child_pid = supervisor.process.pid
        child_sid = os.getsid(child_pid)
        parent_pid = os.getpid()

        # Child should be in its own session (SID == its own PID)
        assert child_sid == child_pid
        assert child_sid != os.getsid(parent_pid)

        supervisor._stop_process()


# ======================================================================
# Backoff circuit breaker
# ======================================================================


class TestBackoff:
    """Circuit breaker prevents restart loops."""

    def test_should_restart_under_limit(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """Under the restart limit, _should_restart returns True."""
        assert supervisor._should_restart() is True

    def test_should_not_restart_over_limit(
        self, supervisor: SignalGeneratorSupervisor
    ) -> None:
        """Over the restart limit, _should_restart returns False."""
        from datetime import UTC, datetime

        # Fill restart history to max
        supervisor.restart_history = [
            datetime.now(UTC) for _ in range(supervisor.max_restarts_per_hour)
        ]
        assert supervisor._should_restart() is False


# ======================================================================
# Statistics
# ======================================================================


class TestStats:
    """get_stats returns correct information."""

    def test_stats_initial(self, supervisor: SignalGeneratorSupervisor) -> None:
        """Initial stats show no restarts and no running process."""
        stats = supervisor.get_stats()
        assert stats["running"] is False
        assert stats["total_restarts"] == 0
        assert stats["current_pid"] is None

    def test_stats_after_start(self, supervisor: SignalGeneratorSupervisor) -> None:
        """Stats reflect a running child process."""
        supervisor.script_path = "sleep"
        supervisor._start_process()

        stats = supervisor.get_stats()
        assert stats["total_restarts"] == 1
        assert stats["current_pid"] == supervisor.process.pid

        supervisor._stop_process()
