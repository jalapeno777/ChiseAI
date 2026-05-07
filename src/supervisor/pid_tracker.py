"""PID file tracking for orphan process detection and cleanup.

Manages a PID file on disk so that a new supervisor instance can detect
and clean up orphaned child processes left behind by a crashed or killed
previous instance.

Key properties:
  - Atomic writes via os.replace to prevent torn reads.
  - Stale-PID detection: a recorded PID that no longer exists or belongs
    to a different process is treated as stale and cleaned up.
  - Process-group-aware killing: sends SIGTERM/SIGKILL to the entire
    process group so that grandchildren are also reaped.
"""

import contextlib
import logging
import os
import signal
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Seconds to wait between SIGTERM and SIGKILL when reaping orphans.
_GRACE_PERIOD_SECONDS = 5


class PIDTracker:
    """Manages a PID file on disk for orphan detection and cleanup.

    Parameters
    ----------
    pid_file:
        Absolute path to the PID file (e.g. ``/run/chiseai/supervisor.pid``).
    """

    def __init__(self, pid_file: str | Path) -> None:
        self.pid_file = Path(pid_file)
        # Ensure parent directory exists
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def write_pid(self, pid: int) -> None:
        """Atomically write *pid* to the PID file.

        Uses write-to-temp + ``os.replace`` so that concurrent readers
        never see a partially-written file.
        """
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.pid_file.parent),
            prefix=".supervisor-pid-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(str(pid))
            os.replace(tmp_path, str(self.pid_file))
            logger.debug("PID file written: %s (pid=%d)", self.pid_file, pid)
        except BaseException:
            # Clean up the temp file on any failure
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def remove_pid(self) -> None:
        """Remove the PID file (called during clean shutdown)."""
        try:
            self.pid_file.unlink()
            logger.debug("PID file removed: %s", self.pid_file)
        except FileNotFoundError:
            pass  # Already gone — that's fine

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def read_pid(self) -> int | None:
        """Return the PID stored in the file, or ``None`` if absent/invalid."""
        try:
            text = self.pid_file.read_text().strip()
            return int(text)
        except (FileNotFoundError, ValueError):
            return None

    def is_pid_running(self, pid: int) -> bool:
        """Return ``True`` if *pid* refers to a running (non-zombie) process."""
        try:
            os.kill(pid, 0)  # Signal 0 = existence check
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we can't signal it — treat as running.
            return True
        except OSError:
            return False

        # os.kill succeeded, but the process might be a zombie.
        # Try to reap it with waitpid (works for our own children).
        try:
            waited_pid, status = os.waitpid(pid, os.WNOHANG)
            if waited_pid != 0:
                # Successfully reaped — process is dead
                return False
        except ChildProcessError:
            # Not our child — can't use waitpid, assume still running
            pass
        except OSError:
            pass

        return True

    # ------------------------------------------------------------------
    # Orphan reaping
    # ------------------------------------------------------------------

    def reap_orphan(self) -> bool:
        """Check for a stale PID file and kill the orphaned process.

        Returns ``True`` if an orphan was found and killed, ``False`` otherwise.
        If the recorded PID is no longer alive the stale PID file is simply
        removed.
        """
        pid = self.read_pid()
        if pid is None:
            return False

        if not self.is_pid_running(pid):
            logger.info("Stale PID file found (pid=%d not running); removing", pid)
            self.remove_pid()
            return False

        logger.warning(
            "Orphan process detected (pid=%d); terminating process group", pid
        )
        self._kill_process_group(pid)
        self.remove_pid()
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _kill_process_group(self, pid: int) -> None:
        """Send SIGTERM (then SIGKILL) to the process *group* of *pid*.

        When the child was started with ``start_new_session=True`` its
        process-group ID equals its own PID, so ``os.killpg(pid, ...)`` will
        reach the child and any of its own subprocesses.
        """
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return  # Already gone
        except PermissionError:
            logger.warning("No permission to SIGTERM pgid %d", pid)
            return

        # Give the process group time to shut down gracefully
        deadline = time.monotonic() + _GRACE_PERIOD_SECONDS
        while time.monotonic() < deadline:
            if not self.is_pid_running(pid):
                return  # Exited cleanly after SIGTERM
            time.sleep(0.2)

        # Escalate to SIGKILL if still alive
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # Good — it exited after SIGTERM
        except PermissionError:
            logger.warning("No permission to SIGKILL pgid %d", pid)
