#!/usr/bin/env python3
"""Trading Scheduler Daemon Wrapper.

A simple daemon wrapper that runs the scheduler heartbeat recorder
at regular intervals. This provides a long-running process that
can be managed by systemd or run directly.

Usage:
    # Start daemon
    python3 scripts/monitoring/trading_scheduler.py start

    # Stop daemon
    python3 scripts/monitoring/trading_scheduler.py stop

    # Run in foreground (for testing)
    python3 scripts/monitoring/trading_scheduler.py --foreground

    # Check status
    python3 scripts/monitoring/trading_scheduler.py status

Systemd Service Setup:
    # Create /etc/systemd/system/chiseai-scheduler.service:
    [Unit]
    Description=ChiseAI Trading Scheduler Heartbeat
    After=network.target

    [Service]
    Type=simple
    User=chiseai
    WorkingDirectory=/home/tacopants/projects/ChiseAI
    ExecStart=/usr/bin/python3 scripts/monitoring/trading_scheduler.py --foreground
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from scripts.monitoring.scheduler_heartbeat import (
    DEFAULT_REDIS_HOST,
    DEFAULT_REDIS_PORT,
    get_redis_client,
    record_heartbeat,
    record_stop,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_INTERVAL = 30  # seconds
DEFAULT_PID_FILE = "/tmp/chiseai_scheduler.pid"


class TradingSchedulerDaemon:
    """Daemon that records scheduler heartbeats at regular intervals."""

    def __init__(
        self,
        interval: int = DEFAULT_INTERVAL,
        redis_host: str = DEFAULT_REDIS_HOST,
        redis_port: int = DEFAULT_REDIS_PORT,
        pid_file: str = DEFAULT_PID_FILE,
    ):
        self.interval = interval
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.pid_file = pid_file
        self.running = False
        self.redis_client = None

    def _write_pid(self) -> bool:
        """Write PID to file."""
        try:
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))
            return True
        except Exception as e:
            logger.error(f"Failed to write PID file: {e}")
            return False

    def _remove_pid(self) -> bool:
        """Remove PID file."""
        try:
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
            return True
        except Exception as e:
            logger.error(f"Failed to remove PID file: {e}")
            return False

    def _read_pid(self) -> int | None:
        """Read PID from file."""
        try:
            if os.path.exists(self.pid_file):
                with open(self.pid_file, "r") as f:
                    return int(f.read().strip())
            return None
        except Exception as e:
            logger.error(f"Failed to read PID file: {e}")
            return None

    def _is_running(self) -> bool:
        """Check if daemon is already running."""
        pid = self._read_pid()
        if pid is None:
            return False

        try:
            # Check if process exists
            os.kill(pid, 0)
            return True
        except OSError:
            # Process doesn't exist, clean up stale PID file
            self._remove_pid()
            return False

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run(self) -> int:
        """Run the daemon main loop.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        logger.info(f"Starting trading scheduler daemon (interval={self.interval}s)")

        # Connect to Redis
        self.redis_client = get_redis_client(self.redis_host, self.redis_port)
        if self.redis_client is None:
            logger.error("Cannot start daemon: Redis connection failed")
            return 1

        # Write PID file
        if not self._write_pid():
            return 1

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self.running = True
        logger.info("Daemon started successfully")

        try:
            while self.running:
                # Record heartbeat
                if not record_heartbeat(self.redis_client, status="running"):
                    logger.warning("Failed to record heartbeat, will retry")

                # Sleep with interrupt handling
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)

        except Exception as e:
            logger.error(f"Daemon error: {e}")
            return 1

        finally:
            # Cleanup
            logger.info("Recording stop heartbeat...")
            if self.redis_client:
                record_stop(self.redis_client)
            self._remove_pid()
            logger.info("Daemon stopped")

        return 0

    def start(self) -> int:
        """Start the daemon.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        if self._is_running():
            logger.error("Daemon is already running")
            return 1

        # Fork to background
        try:
            pid = os.fork()
            if pid > 0:
                # Parent process
                logger.info(f"Daemon started with PID {pid}")
                return 0
        except OSError as e:
            logger.error(f"Fork failed: {e}")
            return 1

        # Child process - detach from terminal
        try:
            os.setsid()
        except OSError:
            pass

        # Second fork to prevent reacquiring terminal
        try:
            pid = os.fork()
            if pid > 0:
                os._exit(0)
        except OSError as e:
            logger.error(f"Second fork failed: {e}")
            os._exit(1)

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()

        with open("/dev/null", "r") as f:
            os.dup2(f.fileno(), sys.stdin.fileno())
        with open("/dev/null", "a+") as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
            os.dup2(f.fileno(), sys.stderr.fileno())

        # Run the daemon
        return self.run()

    def stop(self) -> int:
        """Stop the daemon.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        pid = self._read_pid()
        if pid is None:
            logger.info("Daemon is not running")
            return 0

        try:
            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent stop signal to daemon (PID {pid})")

            # Wait for process to terminate
            for _ in range(10):  # Wait up to 10 seconds
                try:
                    os.kill(pid, 0)
                    time.sleep(1)
                except OSError:
                    # Process terminated
                    logger.info("Daemon stopped")
                    return 0

            # Force kill if still running
            logger.warning("Daemon did not stop gracefully, forcing...")
            os.kill(pid, signal.SIGKILL)
            logger.info("Daemon killed")
            return 0

        except OSError as e:
            logger.error(f"Failed to stop daemon: {e}")
            return 1

    def status(self) -> int:
        """Check daemon status.

        Returns:
            Exit code (0 if running, 1 if not running)
        """
        if self._is_running():
            pid = self._read_pid()
            logger.info(f"Daemon is running (PID {pid})")
            return 0
        else:
            logger.info("Daemon is not running")
            return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Trading Scheduler Daemon for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start daemon in background
  python3 trading_scheduler.py start

  # Stop daemon
  python3 trading_scheduler.py stop

  # Check status
  python3 trading_scheduler.py status

  # Run in foreground (for testing or systemd)
  python3 trading_scheduler.py --foreground

  # Custom interval (60 seconds)
  python3 trading_scheduler.py --foreground --interval 60
        """,
    )

    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "stop", "status"],
        help="Daemon command (start/stop/status)",
    )

    parser.add_argument(
        "--foreground",
        "-f",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Heartbeat interval in seconds (default: {DEFAULT_INTERVAL})",
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
        "--pid-file",
        default=DEFAULT_PID_FILE,
        help=f"PID file location (default: {DEFAULT_PID_FILE})",
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
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Create daemon instance
    daemon = TradingSchedulerDaemon(
        interval=args.interval,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        pid_file=args.pid_file,
    )

    # Handle command
    if args.foreground:
        return daemon.run()
    elif args.command == "start":
        return daemon.start()
    elif args.command == "stop":
        return daemon.stop()
    elif args.command == "status":
        return daemon.status()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
