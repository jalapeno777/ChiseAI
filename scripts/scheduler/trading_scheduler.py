#!/usr/bin/env python3
"""Trading scheduler daemon.

A simple scheduler that runs continuously and writes heartbeats to Redis.
Can be started/stopped gracefully and monitored via Redis heartbeats.
"""

import os
import sys
import time
import signal
import logging
import threading
from datetime import datetime, timezone
from typing import Optional
import redis

# Load .env file for cron environment
env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
)
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST = os.getenv(
    "SCHEDULER_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("SCHEDULER_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))
HEARTBEAT_KEY = "bmad:chiseai:scheduler:heartbeat"
HEARTBEAT_INTERVAL = int(os.getenv("SCHEDULER_HEARTBEAT_INTERVAL", "30"))  # seconds
PID_FILE = os.getenv("SCHEDULER_PID_FILE", "/tmp/trading_scheduler.pid")


class TradingScheduler:
    """Trading scheduler daemon that maintains Redis heartbeats."""

    def __init__(self):
        self.running = False
        self.redis_client: Optional[redis.Redis] = None
        self.start_time: Optional[datetime] = None
        self.last_run_time: Optional[datetime] = None
        self._shutdown_event = threading.Event()

    def _get_redis(self) -> Optional[redis.Redis]:
        """Get or create Redis connection."""
        if self.redis_client is None:
            try:
                self.redis_client = redis.Redis(
                    host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
                )
                # Test connection
                self.redis_client.ping()
            except Exception as e:
                logger.error(f"Redis connection error: {e}")
                self.redis_client = None
        return self.redis_client

    def _record_heartbeat(self, status: str = "running", message: str = "") -> bool:
        """Record heartbeat to Redis."""
        r = self._get_redis()
        if not r:
            logger.error("Cannot connect to Redis for heartbeat")
            return False

        try:
            now = datetime.now(timezone.utc)

            heartbeat_data = {
                "timestamp": now.isoformat(),
                "status": status,
                "unix_timestamp": str(int(now.timestamp())),
            }

            if self.start_time:
                heartbeat_data["start_time"] = self.start_time.isoformat()
                uptime_seconds = (now - self.start_time).total_seconds()
                heartbeat_data["uptime_seconds"] = str(int(uptime_seconds))

            if self.last_run_time:
                heartbeat_data["last_run_time"] = self.last_run_time.isoformat()

            if message:
                heartbeat_data["message"] = message

            # Store in Redis hash
            r.hset(HEARTBEAT_KEY, mapping=heartbeat_data)

            # Set TTL (7 days)
            r.expire(HEARTBEAT_KEY, 604800)

            return True

        except Exception as e:
            logger.error(f"Failed to record heartbeat: {e}")
            return False

    def _write_pid_file(self):
        """Write PID file."""
        try:
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
            logger.info(f"PID file written: {PID_FILE}")
        except Exception as e:
            logger.warning(f"Could not write PID file: {e}")

    def _remove_pid_file(self):
        """Remove PID file."""
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
                logger.info(f"PID file removed: {PID_FILE}")
        except Exception as e:
            logger.warning(f"Could not remove PID file: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._shutdown_event.set()

    def _do_work(self):
        """Perform scheduled work (placeholder for actual trading tasks)."""
        self.last_run_time = datetime.now(timezone.utc)
        logger.debug(f"Work cycle completed at {self.last_run_time.isoformat()}")

        # TODO: Add actual trading tasks here
        # - Check for signals
        # - Update positions
        # - Run optimization
        # - etc.

    def start(self):
        """Start the scheduler daemon."""
        logger.info("Starting Trading Scheduler...")

        # Check if already running
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                # Check if process exists
                os.kill(old_pid, 0)
                logger.error(f"Scheduler already running (PID: {old_pid})")
                return False
            except (ValueError, OSError, ProcessLookupError):
                # PID file stale, remove it
                self._remove_pid_file()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Initialize
        self.start_time = datetime.now(timezone.utc)
        self.running = True

        # Write PID file
        self._write_pid_file()

        # Record initial heartbeat
        self._record_heartbeat("running", "Scheduler started")

        logger.info(f"Scheduler started at {self.start_time.isoformat()}")
        logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")

        # Main loop
        last_heartbeat = time.time()

        try:
            while not self._shutdown_event.is_set():
                current_time = time.time()

                # Record heartbeat at interval
                if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                    self._record_heartbeat("running")
                    last_heartbeat = current_time

                # Do work
                try:
                    self._do_work()
                except Exception as e:
                    logger.error(f"Error in work cycle: {e}")
                    self._record_heartbeat("error", str(e))

                # Small sleep to prevent CPU spinning
                time.sleep(1)

        except Exception as e:
            logger.error(f"Fatal error in scheduler loop: {e}")
            self._record_heartbeat("error", f"Fatal: {e}")

        finally:
            self.stop()

        return True

    def stop(self):
        """Stop the scheduler gracefully."""
        logger.info("Stopping scheduler...")
        self.running = False

        # Record final heartbeat
        self._record_heartbeat("stopped", "Scheduler stopped gracefully")

        # Clean up
        self._remove_pid_file()

        if self.redis_client:
            try:
                self.redis_client.close()
            except:
                pass

        logger.info("Scheduler stopped")

    def status(self) -> dict:
        """Get current scheduler status."""
        status_info = {
            "running": self.running,
            "pid": os.getpid(),
            "pid_file": PID_FILE,
            "pid_file_exists": os.path.exists(PID_FILE),
        }

        if self.start_time:
            status_info["start_time"] = self.start_time.isoformat()
            uptime = datetime.now(timezone.utc) - self.start_time
            status_info["uptime_seconds"] = int(uptime.total_seconds())

        # Check Redis heartbeat
        try:
            r = self._get_redis()
            if r:
                heartbeat = r.hgetall(HEARTBEAT_KEY)
                if heartbeat:
                    status_info["redis_heartbeat"] = heartbeat
        except Exception as e:
            status_info["redis_error"] = str(e)

        return status_info


def start_daemon():
    """Start the scheduler daemon."""
    scheduler = TradingScheduler()
    success = scheduler.start()
    return 0 if success else 1


def stop_daemon():
    """Stop the scheduler daemon."""
    if not os.path.exists(PID_FILE):
        print("Scheduler not running (no PID file)")
        return 1

    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())

        # Send SIGTERM
        os.kill(pid, signal.SIGTERM)
        print(f"Sent stop signal to scheduler (PID: {pid})")
        return 0

    except ValueError:
        print("Invalid PID file")
        return 1
    except ProcessLookupError:
        print("Scheduler not running (stale PID file)")
        os.remove(PID_FILE)
        return 1
    except Exception as e:
        print(f"Error stopping scheduler: {e}")
        return 1


def show_status():
    """Show scheduler status."""
    scheduler = TradingScheduler()
    status = scheduler.status()

    print("Trading Scheduler Status")
    print("=" * 40)

    for key, value in status.items():
        if key == "redis_heartbeat":
            print(f"\nRedis Heartbeat:")
            for hk, hv in value.items():
                print(f"  {hk}: {hv}")
        else:
            print(f"{key}: {value}")

    return 0


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Trading Scheduler Daemon")
    parser.add_argument(
        "command",
        choices=["start", "stop", "status", "restart"],
        help="Command to execute",
    )
    parser.add_argument(
        "--foreground", action="store_true", help="Run in foreground (don't daemonize)"
    )

    args = parser.parse_args()

    if args.command == "start":
        return start_daemon()
    elif args.command == "stop":
        return stop_daemon()
    elif args.command == "restart":
        stop_daemon()
        time.sleep(1)
        return start_daemon()
    elif args.command == "status":
        return show_status()

    return 1


if __name__ == "__main__":
    exit(main())
