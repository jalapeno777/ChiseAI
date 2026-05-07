"""Process supervisor for continuous signal generation with auto-restart.

Ensures signal generator stays running continuously by:
- Monitoring process health
- Auto-restarting on failure or completion
- Implementing backoff to prevent restart loops
- Logging all restart events
- Tracking the child PID on disk for orphan detection
- Cleaning up orphaned children from previous instances

Key fixes over the legacy ``scripts/monitoring/supervisor.py``:

1. **PID file on disk** — atomic writes ensure the PID is always accurate,
   even across crashes, so a new supervisor instance can detect orphans.
2. **Orphan reaping on start** — before launching a new child the supervisor
   checks for and kills any leftover process from a previous run.
3. **Process-group management** — the child is started in its own session
   (``start_new_session=True``) so the entire tree can be reaped.
4. **File-handle safety** — stdout/stderr file handles are tracked and
   closed on process termination, preventing leaks.
5. **No silent overwrite** — ``_start_process`` always stops any existing
   child before starting a new one.
"""

import argparse
import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TextIO

from src.supervisor.pid_tracker import PIDTracker

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_RESTART_DELAY_SECONDS = 5
DEFAULT_MAX_RESTARTS_PER_HOUR = 10
DEFAULT_SIGNAL_GENERATOR_SCRIPT = "scripts/continuous_signal_generator.py"
DEFAULT_LOG_DIR = "/var/log/chiseai"
DEFAULT_PID_FILE = "/run/chiseai/supervisor.pid"

# Redis configuration defaults
DEFAULT_REDIS_HOST = "host.docker.internal"
DEFAULT_REDIS_PORT = 6380

# Key patterns for supervisor state
SUPERVISOR_STATE_KEY = "bmad:chiseai:supervisor:state"
SUPERVISOR_RESTART_LOG_KEY = "bmad:chiseai:supervisor:restart_log"
SUPERVISOR_TTL_SECONDS = 3600  # 1 hour


class SignalGeneratorSupervisor:
    """Supervises the continuous signal generator process.

    Parameters
    ----------
    restart_delay_seconds:
        Seconds to wait between restart attempts.
    max_restarts_per_hour:
        Circuit-breaker: max restarts allowed within one hour.
    signal_generator_script:
        Path to the signal-generator script to supervise.
    log_dir:
        Directory for log files.
    pid_file:
        Path to the PID file for orphan tracking.
    redis_host / redis_port:
        Redis connection parameters for state tracking.
    duration:
        Duration in minutes (0 = run forever).
    interval:
        Signal generation interval in seconds.
    """

    def __init__(
        self,
        restart_delay_seconds: int = DEFAULT_RESTART_DELAY_SECONDS,
        max_restarts_per_hour: int = DEFAULT_MAX_RESTARTS_PER_HOUR,
        signal_generator_script: str = DEFAULT_SIGNAL_GENERATOR_SCRIPT,
        log_dir: str = DEFAULT_LOG_DIR,
        pid_file: str = DEFAULT_PID_FILE,
        redis_host: str = DEFAULT_REDIS_HOST,
        redis_port: int = DEFAULT_REDIS_PORT,
        duration: int = 0,
        interval: int = 30,
    ):
        self.restart_delay = restart_delay_seconds
        self.max_restarts_per_hour = max_restarts_per_hour
        self.script_path = signal_generator_script
        self.log_dir = log_dir
        self.pid_tracker = PIDTracker(pid_file)
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.duration = duration
        self.interval = interval

        self.process: subprocess.Popen | None = None
        self._stdout_file: TextIO | None = None
        self._stderr_file: TextIO | None = None
        self.restart_history: list[datetime] = []
        self.running = False
        self.start_time: datetime | None = None
        self.total_restarts = 0

        # Ensure log directory exists
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

        # Redis client for state tracking
        self.redis_client = self._init_redis()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_redis(self) -> Any:
        """Return a Redis client, or ``None`` if Redis is unavailable."""
        try:
            import redis as redis_lib

            client = redis_lib.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            client.ping()
            logger.info("Redis connection established for supervisor state tracking")
            return client
        except Exception as exc:
            logger.warning("Redis not available for supervisor state tracking: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Main supervision loop
    # ------------------------------------------------------------------

    def start(self) -> int:
        """Start the supervision loop.

        Returns
        -------
        int
            Exit code (0 for clean shutdown, 1 for error).
        """
        self.running = True
        self.start_time = datetime.now(UTC)

        self._log_banner()

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        # --- Orphan reaping ------------------------------------------------
        # Before launching any child, check for and kill leftover processes
        # from a previous supervisor instance.
        self.pid_tracker.reap_orphan()
        self._record_supervisor_state("starting")

        try:
            while self.running:
                try:
                    if not self._should_restart():
                        logger.error(
                            "Too many restarts (%d in last hour), backing off for 5 minutes",
                            len(self.restart_history),
                        )
                        self._record_supervisor_state("backoff")
                        time.sleep(300)
                        continue

                    self._start_process()

                    if self.process:
                        self._monitor_process()

                except Exception as exc:
                    logger.exception("Supervisor error: %s", exc)
                    time.sleep(self.restart_delay)

        except Exception as exc:
            logger.exception("Fatal supervisor error: %s", exc)
            return 1

        logger.info("Supervisor shutting down")
        self._record_supervisor_state("shutting_down")
        self._stop_process()
        self.pid_tracker.remove_pid()
        self._record_supervisor_state("stopped")
        return 0

    # ------------------------------------------------------------------
    # Restart bookkeeping
    # ------------------------------------------------------------------

    def _should_restart(self) -> bool:
        """Return ``True`` unless the hourly restart cap has been reached."""
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)
        self.restart_history = [t for t in self.restart_history if t > one_hour_ago]
        return len(self.restart_history) < self.max_restarts_per_hour

    # ------------------------------------------------------------------
    # Child process lifecycle
    # ------------------------------------------------------------------

    def _start_process(self) -> None:
        """Start (or restart) the signal generator child process.

        Guarantees:
        * Any existing child is fully stopped before a new one is launched.
        * The child runs in its own session so the entire process group can
          be killed on shutdown or orphan reaping.
        * File handles for stdout/stderr are tracked and closed on cleanup.
        * The PID is written to disk *after* the process is confirmed alive.
        """
        # Always stop any existing child first — prevents silent overwrite.
        if self.process is not None:
            logger.warning(
                "Existing child process (pid=%d) still referenced; stopping before restart",
                self.process.pid,
            )
            self._stop_process()

        logger.info("Starting signal generator...")

        try:
            cmd = [
                sys.executable,
                self.script_path,
                "--duration",
                str(self.duration),
                "--interval",
                str(self.interval),
            ]

            stdout_path = Path(self.log_dir) / "signal_generator.stdout.log"
            stderr_path = Path(self.log_dir) / "signal_generator.stderr.log"

            self._stdout_file = open(stdout_path, "a")  # noqa: SIM115
            self._stderr_file = open(stderr_path, "a")  # noqa: SIM115

            start_marker = (
                f"\n{'=' * 60}\n"
                f"[{datetime.now(UTC).isoformat()}] Process started by supervisor\n"
                f"{'=' * 60}\n"
            )
            self._stdout_file.write(start_marker)
            self._stderr_file.write(start_marker)
            self._stdout_file.flush()
            self._stderr_file.flush()

            self.process = subprocess.Popen(
                cmd,
                stdout=self._stdout_file,
                stderr=self._stderr_file,
                text=True,
                start_new_session=True,  # new process group for clean kill
            )

            # Verify process is alive before recording PID
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Child exited immediately with code {self.process.returncode}"
                )

            restart_time = datetime.now(UTC)
            self.restart_history.append(restart_time)
            self.total_restarts += 1

            logger.info("Signal generator started with PID %d", self.process.pid)
            logger.info("Total restarts this session: %d", self.total_restarts)

            # Record PID to disk for orphan detection
            self.pid_tracker.write_pid(self.process.pid)

            # Record in Redis
            self._record_restart_event(restart_time, self.process.pid)
            self._record_supervisor_state("running", pid=self.process.pid)

        except Exception as exc:
            logger.error("Failed to start signal generator: %s", exc)
            self.process = None
            self._close_file_handles()
            self._record_supervisor_state("start_failed", error=str(exc))

    def _monitor_process(self) -> None:
        """Monitor the running child and flag it for restart on exit."""
        if self.process is None:
            return

        retcode = self.process.poll()

        if retcode is not None:
            # Child exited — clean up handles
            self._close_file_handles()

            if retcode == 0:
                logger.info("Signal generator exited normally (code %d)", retcode)
                self._record_supervisor_state("process_exited_clean", exit_code=retcode)
            else:
                logger.error("Signal generator crashed (code %d)", retcode)
                self._record_supervisor_state("process_crashed", exit_code=retcode)

            self.process = None
            self.pid_tracker.remove_pid()
            time.sleep(self.restart_delay)
        else:
            # Still running
            time.sleep(1)

    def _stop_process(self) -> None:
        """Terminate the child process and its entire process group."""
        if self.process is None:
            return

        pid = self.process.pid
        logger.info("Stopping signal generator (PID %d)...", pid)
        try:
            # SIGTERM to the process group
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                # Fallback: SIGTERM to just the process
                with contextlib.suppress(ProcessLookupError, OSError):
                    self.process.terminate()

            try:
                self.process.wait(timeout=5)
                logger.info("Signal generator stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("Signal generator did not stop gracefully, killing...")
                # SIGKILL the process group
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(pid, signal.SIGKILL)
                try:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except (ProcessLookupError, OSError):
                    pass
                logger.info("Signal generator killed")
        except Exception as exc:
            logger.error("Error stopping process: %s", exc)
        finally:
            self.process = None
            self.pid_tracker.remove_pid()
            self._close_file_handles()

    # ------------------------------------------------------------------
    # File-handle management
    # ------------------------------------------------------------------

    def _close_file_handles(self) -> None:
        """Close stdout/stderr log file handles if open."""
        for name in ("_stdout_file", "_stderr_file"):
            fh = getattr(self, name, None)
            if fh is not None:
                with contextlib.suppress(OSError):
                    fh.close()
                setattr(self, name, None)

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        """Handle SIGTERM / SIGINT by flagging the loop for clean exit."""
        logger.info("Received signal %d, initiating graceful shutdown...", signum)
        self.running = False

    # ------------------------------------------------------------------
    # Redis state tracking
    # ------------------------------------------------------------------

    def _record_restart_event(self, restart_time: datetime, pid: int) -> None:
        """Record a restart event to Redis."""
        if not self.redis_client:
            return
        try:
            event = {
                "timestamp": restart_time.isoformat(),
                "pid": str(pid),
                "restart_count_this_hour": str(len(self.restart_history)),
                "total_restarts": str(self.total_restarts),
            }
            self.redis_client.lpush(SUPERVISOR_RESTART_LOG_KEY, json.dumps(event))
            self.redis_client.ltrim(SUPERVISOR_RESTART_LOG_KEY, 0, 99)
            self.redis_client.expire(SUPERVISOR_RESTART_LOG_KEY, SUPERVISOR_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Failed to record restart event: %s", exc)

    def _record_supervisor_state(
        self,
        status: str,
        pid: int | None = None,
        exit_code: int | None = None,
        error: str | None = None,
    ) -> None:
        """Record the current supervisor state to Redis."""
        if not self.redis_client:
            return
        try:
            state: dict[str, str] = {
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
                "supervisor_pid": str(os.getpid()),
                "total_restarts": str(self.total_restarts),
                "restarts_last_hour": str(len(self.restart_history)),
            }
            if pid is not None:
                state["signal_generator_pid"] = str(pid)
            if exit_code is not None:
                state["last_exit_code"] = str(exit_code)
            if error:
                state["last_error"] = error
            if self.start_time:
                uptime = (datetime.now(UTC) - self.start_time).total_seconds()
                state["uptime_seconds"] = str(int(uptime))
            self.redis_client.hset(SUPERVISOR_STATE_KEY, mapping=state)
            self.redis_client.expire(SUPERVISOR_STATE_KEY, SUPERVISOR_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Failed to record supervisor state: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_banner(self) -> None:
        logger.info("=" * 60)
        logger.info("Signal generator supervisor starting...")
        logger.info("Script: %s", self.script_path)
        logger.info("Max restarts/hour: %d", self.max_restarts_per_hour)
        logger.info("Restart delay: %ds", self.restart_delay)
        logger.info(
            "Duration: %s",
            "forever" if self.duration == 0 else f"{self.duration} minutes",
        )
        logger.info("Signal interval: %ds", self.interval)
        logger.info("PID file: %s", self.pid_tracker.pid_file)
        logger.info("=" * 60)

    def get_stats(self) -> dict[str, Any]:
        """Return a snapshot of supervisor statistics."""
        return {
            "running": self.running,
            "total_restarts": self.total_restarts,
            "restarts_last_hour": len(self.restart_history),
            "max_restarts_per_hour": self.max_restarts_per_hour,
            "current_pid": self.process.pid if self.process else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": (
                (datetime.now(UTC) - self.start_time).total_seconds()
                if self.start_time
                else 0
            ),
        }


# ======================================================================
# CLI entry point
# ======================================================================


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Process supervisor for continuous signal generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 -m src.supervisor.supervisor
  python3 -m src.supervisor.supervisor --max-restarts 5 --restart-delay 10
  python3 -m src.supervisor.supervisor --duration 60 --interval 30
        """,
    )

    parser.add_argument(
        "--restart-delay",
        type=int,
        default=DEFAULT_RESTART_DELAY_SECONDS,
        help=f"Seconds to wait before restarting (default: {DEFAULT_RESTART_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=DEFAULT_MAX_RESTARTS_PER_HOUR,
        help=f"Max restarts per hour (default: {DEFAULT_MAX_RESTARTS_PER_HOUR})",
    )
    parser.add_argument(
        "--script",
        default=DEFAULT_SIGNAL_GENERATOR_SCRIPT,
        help=f"Path to signal generator script (default: {DEFAULT_SIGNAL_GENERATOR_SCRIPT})",
    )
    parser.add_argument(
        "--log-dir",
        default=DEFAULT_LOG_DIR,
        help=f"Directory for log files (default: {DEFAULT_LOG_DIR})",
    )
    parser.add_argument(
        "--pid-file",
        default=DEFAULT_PID_FILE,
        help=f"Path to PID file (default: {DEFAULT_PID_FILE})",
    )
    parser.add_argument(
        "--redis-host",
        default=os.getenv("REDIS_HOST", DEFAULT_REDIS_HOST),
        help=f"Redis host (default: {DEFAULT_REDIS_HOST})",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=int(os.getenv("REDIS_PORT", DEFAULT_REDIS_PORT)),
        help=f"Redis port (default: {DEFAULT_REDIS_PORT})",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Duration in minutes (0 = run forever, default: 0)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Signal generation interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    Path(args.log_dir).mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        file_handler = logging.FileHandler(Path(args.log_dir) / "supervisor.log")
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    except Exception as exc:
        print(f"Warning: Could not create file handler: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=log_level, format=log_format, handlers=handlers, force=True
    )

    supervisor = SignalGeneratorSupervisor(
        restart_delay_seconds=args.restart_delay,
        max_restarts_per_hour=args.max_restarts,
        signal_generator_script=args.script,
        log_dir=args.log_dir,
        pid_file=args.pid_file,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        duration=args.duration,
        interval=args.interval,
    )
    return supervisor.start()


if __name__ == "__main__":
    sys.exit(main())
