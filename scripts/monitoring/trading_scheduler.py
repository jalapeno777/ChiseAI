#!/usr/bin/env python3
"""Trading Scheduler Daemon Wrapper with P0 Hardening.

A simple daemon wrapper that runs the scheduler heartbeat recorder
at regular intervals. This provides a long-running process that
can be managed by systemd or run directly.

P0 Hardening Features:
- Automatic restart on heartbeat failure
- Health check endpoint that can be queried
- Signal to trigger recovery mode
- PID file validation (prevent stale PID issues)

Usage:
    # Start daemon
    python3 scripts/monitoring/trading_scheduler.py start

    # Stop daemon
    python3 scripts/monitoring/trading_scheduler.py stop

    # Run in foreground (for testing)
    python3 scripts/monitoring/trading_scheduler.py --foreground

    # Check status
    python3 scripts/monitoring/trading_scheduler.py status

    # Health check
    python3 scripts/monitoring/trading_scheduler.py health

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
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
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
    WatchdogMonitor,
    RECOVERY_KEY,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_INTERVAL = 30  # seconds
DEFAULT_PID_FILE = "/tmp/chiseai_scheduler.pid"
DEFAULT_HEALTH_FILE = "/tmp/chiseai_scheduler.health"

# P0 Hardening Constants
MAX_HEARTBEAT_FAILURES = 3  # Restart after this many consecutive failures
HEALTH_CHECK_TIMEOUT = 5  # seconds
RECOVERY_SIGNAL = signal.SIGUSR1


class TradingSchedulerDaemon:
    """Daemon that records scheduler heartbeats at regular intervals with P0 hardening."""

    def __init__(
        self,
        interval: int = DEFAULT_INTERVAL,
        redis_host: str = DEFAULT_REDIS_HOST,
        redis_port: int = DEFAULT_REDIS_PORT,
        pid_file: str = DEFAULT_PID_FILE,
        health_file: str = DEFAULT_HEALTH_FILE,
    ):
        self.interval = interval
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.pid_file = pid_file
        self.health_file = health_file
        self.running = False
        self.redis_client = None
        self.heartbeat_failures = 0
        self.start_time: float | None = None
        self.in_recovery_mode = False

    def _write_pid(self) -> bool:
        """Write PID to file with validation."""
        try:
            pid = os.getpid()
            pid_data = {
                "pid": pid,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "hostname": os.uname().nodename,
            }
            with open(self.pid_file, "w") as f:
                json.dump(pid_data, f)
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

    def _read_pid(self) -> dict[str, Any] | None:
        """Read PID data from file.

        Returns:
            Dict with pid, started_at, hostname or None if invalid
        """
        try:
            if os.path.exists(self.pid_file):
                with open(self.pid_file, "r") as f:
                    return json.load(f)
            return None
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to read PID file: {e}")
            return None

    def _is_running(self) -> bool:
        """Check if daemon is already running with PID validation.

        Returns:
            True if daemon is running, False otherwise
        """
        pid_data = self._read_pid()
        if pid_data is None:
            return False

        pid = pid_data.get("pid")
        if pid is None:
            # Invalid PID file, clean up
            self._remove_pid()
            return False

        try:
            # Check if process exists and is this script
            os.kill(pid, 0)
            # Process exists - verify it's actually our daemon
            # by checking /proc/PID/cmdline
            try:
                with open(f"/proc/{pid}/cmdline", "r") as f:
                    cmdline = f.read()
                    if "trading_scheduler" in cmdline:
                        return True
                    else:
                        # Stale PID file - different process
                        logger.warning(
                            f"Stale PID file found (PID {pid} is not trading_scheduler)"
                        )
                        self._remove_pid()
                        return False
            except (FileNotFoundError, PermissionError):
                # Can't verify, assume it's running to be safe
                return True
        except OSError:
            # Process doesn't exist, clean up stale PID file
            logger.warning(f"Stale PID file found (PID {pid} not running)")
            self._remove_pid()
            return False

    def _write_health(self, status: str, details: dict[str, Any] | None = None) -> bool:
        """Write health status to file.

        Args:
            status: Health status ("healthy", "degraded", "unhealthy")
            details: Additional health details

        Returns:
            True if successful, False otherwise
        """
        try:
            health_data = {
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pid": os.getpid(),
                "uptime_seconds": (
                    int(time.time() - self.start_time) if self.start_time else 0
                ),
            }
            if details:
                health_data["details"] = details
            if self.in_recovery_mode:
                health_data["recovery_mode"] = True

            with open(self.health_file, "w") as f:
                json.dump(health_data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to write health file: {e}")
            return False

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _recovery_signal_handler(self, signum: int, frame: Any) -> None:
        """Handle recovery signal (SIGUSR1)."""
        logger.warning(f"Received recovery signal {signum}, entering recovery mode...")
        self.in_recovery_mode = True
        self.heartbeat_failures = 0  # Reset failure count

    def _check_recovery_trigger(self) -> bool:
        """Check if recovery has been triggered via Redis.

        Returns:
            True if recovery should be performed, False otherwise
        """
        if not self.redis_client:
            return False

        try:
            recovery_data = self.redis_client.hgetall(RECOVERY_KEY)
            if recovery_data:
                # Recovery has been triggered
                logger.warning("Recovery trigger detected in Redis")
                return True
        except Exception as e:
            logger.error(f"Error checking recovery trigger: {e}")

        return False

    def _perform_recovery(self) -> bool:
        """Perform recovery actions.

        Returns:
            True if recovery successful, False otherwise
        """
        logger.info("Performing recovery actions...")
        self.in_recovery_mode = True

        try:
            # Reconnect to Redis
            if self.redis_client:
                try:
                    self.redis_client.close()
                except:
                    pass

            self.redis_client = get_redis_client(self.redis_host, self.redis_port)
            if self.redis_client is None:
                logger.error("Recovery failed: Cannot reconnect to Redis")
                return False

            # Reset heartbeat failures
            self.heartbeat_failures = 0

            # Record recovery heartbeat
            record_heartbeat(
                self.redis_client,
                status="running",
                metadata={
                    "recovery": "true",
                    "recovery_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            logger.info("Recovery completed successfully")
            self.in_recovery_mode = False
            return True

        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            return False

    def run(self) -> int:
        """Run the daemon main loop with P0 hardening.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        logger.info(f"Starting trading scheduler daemon (interval={self.interval}s)")
        self.start_time = time.time()

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
        signal.signal(RECOVERY_SIGNAL, self._recovery_signal_handler)

        self.running = True
        logger.info("Daemon started successfully")

        try:
            while self.running:
                # Check for recovery trigger
                if self._check_recovery_trigger():
                    if not self._perform_recovery():
                        logger.error("Recovery failed, continuing with degraded state")

                # Record heartbeat
                success = record_heartbeat(self.redis_client, status="running")

                if success:
                    self.heartbeat_failures = 0
                    self._write_health("healthy", {"heartbeat": "success"})
                else:
                    self.heartbeat_failures += 1
                    logger.warning(
                        f"Heartbeat failed ({self.heartbeat_failures}/{MAX_HEARTBEAT_FAILURES})"
                    )
                    self._write_health(
                        "degraded",
                        {
                            "heartbeat": "failed",
                            "consecutive_failures": self.heartbeat_failures,
                        },
                    )

                    # Trigger recovery if too many failures
                    if self.heartbeat_failures >= MAX_HEARTBEAT_FAILURES:
                        logger.error(
                            f"Too many heartbeat failures ({self.heartbeat_failures}), "
                            "triggering recovery..."
                        )
                        if self._perform_recovery():
                            logger.info("Auto-recovery successful")
                        else:
                            logger.error("Auto-recovery failed")
                            # Continue running but stay in degraded state

                # Sleep with interrupt handling
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)

        except Exception as e:
            logger.error(f"Daemon error: {e}")
            self._write_health("unhealthy", {"error": str(e)})
            return 1

        finally:
            # Cleanup
            logger.info("Recording stop heartbeat...")
            if self.redis_client:
                record_stop(self.redis_client)
            self._remove_pid()
            # Clean up health file
            try:
                if os.path.exists(self.health_file):
                    os.remove(self.health_file)
            except:
                pass
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
        pid_data = self._read_pid()
        if pid_data is None:
            logger.info("Daemon is not running")
            return 0

        pid = pid_data.get("pid")
        if pid is None:
            logger.info("Invalid PID file, daemon not running")
            self._remove_pid()
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
            pid_data = self._read_pid()
            pid = pid_data.get("pid") if pid_data else None
            logger.info(f"Daemon is running (PID {pid})")
            return 0
        else:
            logger.info("Daemon is not running")
            return 1

    def health(self) -> int:
        """Check daemon health from health file.

        Returns:
            Exit code (0 if healthy, 1 if degraded/unhealthy)
        """
        try:
            if not os.path.exists(self.health_file):
                # Check if daemon is running
                if self._is_running():
                    logger.info("Daemon is running but no health file yet")
                    return 0
                else:
                    logger.error("Daemon is not running")
                    return 1

            with open(self.health_file, "r") as f:
                health_data = json.load(f)

            status = health_data.get("status", "unknown")
            timestamp = health_data.get("timestamp")

            # Check if health data is stale (>2 minutes old)
            if timestamp:
                health_time = datetime.fromisoformat(timestamp)
                age = datetime.now(timezone.utc) - health_time
                if age.total_seconds() > 120:
                    logger.error(
                        f"Health data is stale ({age.total_seconds():.0f}s old)"
                    )
                    return 1

            if status == "healthy":
                logger.info(
                    f"Daemon is healthy (uptime: {health_data.get('uptime_seconds', 0)}s)"
                )
                return 0
            elif status == "degraded":
                logger.warning(f"Daemon is degraded: {health_data.get('details', {})}")
                return 1
            else:
                logger.error(f"Daemon is unhealthy: {health_data.get('details', {})}")
                return 1

        except Exception as e:
            logger.error(f"Failed to check health: {e}")
            return 1

    def trigger_recovery(self) -> int:
        """Trigger recovery mode via signal.

        Returns:
            Exit code (0 if signal sent, 1 if failed)
        """
        pid_data = self._read_pid()
        if pid_data is None:
            logger.error("Daemon is not running")
            return 1

        pid = pid_data.get("pid")
        if pid is None:
            logger.error("Invalid PID file")
            return 1

        try:
            os.kill(pid, RECOVERY_SIGNAL)
            logger.info(f"Sent recovery signal to daemon (PID {pid})")
            return 0
        except OSError as e:
            logger.error(f"Failed to send recovery signal: {e}")
            return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Trading Scheduler Daemon for ChiseAI (P0 Hardened)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start daemon in background
  python3 trading_scheduler.py start

  # Stop daemon
  python3 trading_scheduler.py stop

  # Check status
  python3 trading_scheduler.py status

  # Check health
  python3 trading_scheduler.py health

  # Trigger recovery
  python3 trading_scheduler.py recover

  # Run in foreground (for testing or systemd)
  python3 trading_scheduler.py --foreground

  # Custom interval (60 seconds)
  python3 trading_scheduler.py --foreground --interval 60
        """,
    )

    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "stop", "status", "health", "recover"],
        help="Daemon command (start/stop/status/health/recover)",
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
        "--health-file",
        default=DEFAULT_HEALTH_FILE,
        help=f"Health file location (default: {DEFAULT_HEALTH_FILE})",
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
        health_file=args.health_file,
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
    elif args.command == "health":
        return daemon.health()
    elif args.command == "recover":
        return daemon.trigger_recovery()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
