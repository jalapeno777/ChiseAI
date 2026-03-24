#!/usr/bin/env python3
"""Process supervisor for continuous signal generation with auto-restart.

Ensures signal generator stays running continuously by:
- Monitoring process health
- Auto-restarting on failure or completion
- Implementing backoff to prevent restart loops
- Logging all restart events
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_RESTART_DELAY_SECONDS = 5
DEFAULT_MAX_RESTARTS_PER_HOUR = 10
DEFAULT_SIGNAL_GENERATOR_SCRIPT = "scripts/continuous_signal_generator.py"
DEFAULT_LOG_DIR = "/var/log/chiseai"

# Redis configuration defaults
DEFAULT_REDIS_HOST = "host.docker.internal"
DEFAULT_REDIS_PORT = 6380

# Key patterns for supervisor state
SUPERVISOR_STATE_KEY = "bmad:chiseai:supervisor:state"
SUPERVOR_RESTART_LOG_KEY = "bmad:chiseai:supervisor:restart_log"
SUPERVISOR_TTL_SECONDS = 3600  # 1 hour


class SignalGeneratorSupervisor:
    """Supervises the continuous signal generator process."""

    def __init__(
        self,
        restart_delay_seconds: int = DEFAULT_RESTART_DELAY_SECONDS,
        max_restarts_per_hour: int = DEFAULT_MAX_RESTARTS_PER_HOUR,
        signal_generator_script: str = DEFAULT_SIGNAL_GENERATOR_SCRIPT,
        log_dir: str = DEFAULT_LOG_DIR,
        redis_host: str = DEFAULT_REDIS_HOST,
        redis_port: int = DEFAULT_REDIS_PORT,
        duration: int = 0,  # 0 = run forever
        interval: int = 30,
    ):
        self.restart_delay = restart_delay_seconds
        self.max_restarts_per_hour = max_restarts_per_hour
        self.script_path = signal_generator_script
        self.log_dir = log_dir
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.duration = duration
        self.interval = interval

        self.process: subprocess.Popen | None = None
        self.restart_history: list[datetime] = []
        self.running = False
        self.start_time: datetime | None = None
        self.total_restarts = 0

        # Ensure log directory exists
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

        # Try to import redis for state tracking
        self.redis_client = None
        try:
            import redis as redis_lib

            self.redis_client = redis_lib.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self.redis_client.ping()
            logger.info("Redis connection established for supervisor state tracking")
        except Exception as e:
            logger.warning(f"Redis not available for supervisor state tracking: {e}")
            self.redis_client = None

    def start(self) -> int:
        """Start supervision loop.

        Returns:
            Exit code (0 for clean shutdown, 1 for error)
        """
        self.running = True
        self.start_time = datetime.now(UTC)
        logger.info("=" * 60)
        logger.info("Signal generator supervisor starting...")
        logger.info(f"Script: {self.script_path}")
        logger.info(f"Max restarts/hour: {self.max_restarts_per_hour}")
        logger.info(f"Restart delay: {self.restart_delay}s")
        logger.info(
            f"Duration: {'forever' if self.duration == 0 else f'{self.duration} minutes'}"
        )
        logger.info(f"Signal interval: {self.interval}s")
        logger.info("=" * 60)

        # Handle shutdown gracefully
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        # Record supervisor start in Redis
        self._record_supervisor_state("starting")

        try:
            while self.running:
                try:
                    if self._should_restart():
                        self._start_process()
                    else:
                        logger.error(
                            f"Too many restarts ({len(self.restart_history)} in last hour), "
                            "backing off for 5 minutes"
                        )
                        self._record_supervisor_state("backoff")
                        time.sleep(300)  # 5 minute backoff
                        continue

                    # Monitor process
                    if self.process:
                        self._monitor_process()

                except Exception as e:
                    logger.exception(f"Supervisor error: {e}")
                    time.sleep(self.restart_delay)

        except Exception as e:
            logger.exception(f"Fatal supervisor error: {e}")
            return 1

        logger.info("Supervisor shutting down")
        self._record_supervisor_state("shutting_down")
        self._stop_process()
        self._record_supervisor_state("stopped")

        return 0

    def _should_restart(self) -> bool:
        """Check if we should restart based on restart history."""
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        # Clean old restarts (older than 1 hour)
        self.restart_history = [t for t in self.restart_history if t > one_hour_ago]

        return len(self.restart_history) < self.max_restarts_per_hour

    def _start_process(self) -> None:
        """Start the signal generator process."""
        logger.info("Starting signal generator...")

        try:
            # Build command arguments
            cmd = [
                sys.executable,
                self.script_path,
                "--duration",
                str(self.duration),  # 0 = run forever
                "--interval",
                str(self.interval),
            ]

            # Open log files for stdout/stderr
            stdout_path = Path(self.log_dir) / "signal_generator.stdout.log"
            stderr_path = Path(self.log_dir) / "signal_generator.stderr.log"

            stdout_file = open(stdout_path, "a")
            stderr_file = open(stderr_path, "a")

            # Write start marker to logs
            start_marker = f"\n{'=' * 60}\n[{datetime.now(UTC).isoformat()}] Process started by supervisor\n{'=' * 60}\n"
            stdout_file.write(start_marker)
            stderr_file.write(start_marker)
            stdout_file.flush()
            stderr_file.flush()

            self.process = subprocess.Popen(
                cmd,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                # Don't use PIPE - write directly to files to avoid buffer issues
            )

            restart_time = datetime.now(UTC)
            self.restart_history.append(restart_time)
            self.total_restarts += 1

            logger.info(f"Signal generator started with PID {self.process.pid}")
            logger.info(f"Total restarts this session: {self.total_restarts}")

            # Record restart in Redis
            self._record_restart_event(restart_time, self.process.pid)
            self._record_supervisor_state("running", pid=self.process.pid)

        except Exception as e:
            logger.error(f"Failed to start signal generator: {e}")
            self.process = None
            self._record_supervisor_state("start_failed", error=str(e))

    def _monitor_process(self) -> None:
        """Monitor running process and restart if needed."""
        if self.process is None:
            return

        # Check if process is still running
        retcode = self.process.poll()

        if retcode is not None:
            # Process exited
            if retcode == 0:
                logger.info(f"Signal generator exited normally (code {retcode})")
                self._record_supervisor_state("process_exited_clean", exit_code=retcode)
            else:
                logger.error(f"Signal generator crashed (code {retcode})")
                self._record_supervisor_state("process_crashed", exit_code=retcode)

            self.process = None
            time.sleep(self.restart_delay)
        else:
            # Process still running, sleep briefly
            time.sleep(1)

    def _stop_process(self) -> None:
        """Stop the signal generator process."""
        if self.process:
            logger.info(f"Stopping signal generator (PID {self.process.pid})...")
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                    logger.info("Signal generator stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Signal generator did not stop gracefully, killing..."
                    )
                    self.process.kill()
                    self.process.wait(timeout=2)
                    logger.info("Signal generator killed")
            except Exception as e:
                logger.error(f"Error stopping process: {e}")
            finally:
                self.process = None

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    def _record_restart_event(self, restart_time: datetime, pid: int) -> None:
        """Record restart event to Redis for monitoring."""
        if not self.redis_client:
            return

        try:
            event = {
                "timestamp": restart_time.isoformat(),
                "pid": str(pid),
                "restart_count_this_hour": str(len(self.restart_history)),
                "total_restarts": str(self.total_restarts),
            }

            # Add to restart log (keep last 100)
            self.redis_client.lpush(SUPERVOR_RESTART_LOG_KEY, json.dumps(event))
            self.redis_client.ltrim(SUPERVOR_RESTART_LOG_KEY, 0, 99)
            self.redis_client.expire(SUPERVOR_RESTART_LOG_KEY, SUPERVISOR_TTL_SECONDS)

        except Exception as e:
            logger.warning(f"Failed to record restart event: {e}")

    def _record_supervisor_state(
        self,
        status: str,
        pid: int | None = None,
        exit_code: int | None = None,
        error: str | None = None,
    ) -> None:
        """Record supervisor state to Redis."""
        if not self.redis_client:
            return

        try:
            state = {
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
                "supervisor_pid": str(os.getpid()),
                "total_restarts": str(self.total_restarts),
                "restarts_last_hour": str(len(self.restart_history)),
            }

            if pid:
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

        except Exception as e:
            logger.warning(f"Failed to record supervisor state: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get supervisor statistics."""
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


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Process supervisor for continuous signal generation with auto-restart",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults (restarts on crash, max 10/hour)
  python3 scripts/monitoring/supervisor.py

  # Run with custom restart limits
  python3 scripts/monitoring/supervisor.py --max-restarts 5 --restart-delay 10

  # Run signal generator for 60 minutes with 30s intervals
  python3 scripts/monitoring/supervisor.py --duration 60 --interval 30

  # Run forever (until manually stopped)
  python3 scripts/monitoring/supervisor.py --duration 0

Systemd Service:
  systemctl start chiseai-signal-generator
  systemctl status chiseai-signal-generator
  journalctl -u chiseai-signal-generator -f
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
        help=f"Maximum restarts per hour (default: {DEFAULT_MAX_RESTARTS_PER_HOUR})",
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
        "--redis-host",
        default=os.getenv("REDIS_HOST", DEFAULT_REDIS_HOST),
        help=f"Redis host for state tracking (default: {DEFAULT_REDIS_HOST})",
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
        help="Duration in minutes for signal generator (0 = run forever, default: 0)",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Signal generation interval in seconds (default: 30)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Ensure log directory exists
    Path(args.log_dir).mkdir(parents=True, exist_ok=True)

    # Setup handlers
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    # Try to add file handler
    try:
        file_handler = logging.FileHandler(Path(args.log_dir) / "supervisor.log")
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    except Exception as e:
        print(f"Warning: Could not create file handler: {e}", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers,
        force=True,
    )

    # Create and run supervisor
    supervisor = SignalGeneratorSupervisor(
        restart_delay_seconds=args.restart_delay,
        max_restarts_per_hour=args.max_restarts,
        signal_generator_script=args.script,
        log_dir=args.log_dir,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        duration=args.duration,
        interval=args.interval,
    )

    return supervisor.start()


if __name__ == "__main__":
    sys.exit(main())
