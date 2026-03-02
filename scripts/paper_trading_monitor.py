#!/usr/bin/env python3
"""Paper Trading Monitor - Auto-restart service for paper trading emitter.

This script monitors the paper trading emitter and automatically restarts
it if it stops or fails to emit data to InfluxDB.

Usage:
    python3 paper_trading_monitor.py [--check-interval SECONDS]

Can be run via cron every 2 minutes:
    */2 * * * * cd /path/to/project && python3 scripts/paper_trading_monitor.py

For PAPER-DIAG-001: Auto-restart capability for paper trading loop
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "paper_trading_monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_DIR = Path(__file__).parent.parent
PID_FILE = Path(tempfile.gettempdir()) / "continuous_paper_emitter.pid"
STATUS_FILE = Path(tempfile.gettempdir()) / "continuous_paper_emitter.status"
EMITTER_SCRIPT = PROJECT_DIR / "scripts" / "continuous_paper_emitter.py"
MANAGER_SCRIPT = PROJECT_DIR / "scripts" / "paper_trading_manager.sh"

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087")
INFLUXDB_TOKEN = os.getenv(
    "INFLUXDB_TOKEN",
    "REDACTED_INFLUXDB_TOKEN",
)
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "chiseai")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "chiseai")

# Data freshness threshold (seconds)
DATA_FRESHNESS_THRESHOLD = 120  # 2 minutes


def get_redis_client() -> Any | None:
    """Get Redis client with error handling."""
    try:
        import redis

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        return client
    except Exception as e:
        logger.debug(f"Redis connection failed: {e}")
        return None


def is_process_running(pid: int | None = None) -> tuple[bool, int | None]:
    """Check if the emitter process is running.

    Returns:
        Tuple of (is_running, pid)
    """
    # First check PID file
    if pid is None and PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except (OSError, ValueError) as e:
            logger.debug(f"Failed to read PID file: {e}")
            pid = None

    # Check if process exists
    if pid:
        try:
            os.kill(pid, 0)  # Signal 0 checks if process exists
            return True, pid
        except (OSError, ProcessLookupError):
            logger.debug(f"Process {pid} not found")
            return False, pid

    # Fallback: check by process name
    try:
        result = subprocess.run(  # nosec B607
            ["pgrep", "-f", "continuous_paper_emitter.py"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            found_pid = int(result.stdout.strip().split("\n")[0])
            return True, found_pid
    except Exception as e:
        logger.debug(f"pgrep failed: {e}")

    return False, None


def check_recent_influxdb_data() -> tuple[bool, datetime | None]:
    """Check if recent data exists in InfluxDB.

    Returns:
        Tuple of (has_recent_data, last_timestamp)
    """
    # Query for most recent paper_portfolio data
    query = f"""
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "paper_portfolio")
  |> last()
"""

    curl_cmd = [
        "curl",
        "-s",
        "-X",
        "POST",
        f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
        "-H",
        f"Authorization: Token {INFLUXDB_TOKEN}",
        "-H",
        "Content-Type: application/vnd.flux",
        "-H",
        "Accept: application/csv",
        "--data-raw",
        query,
    ]

    try:
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logger.warning(f"InfluxDB query failed: {result.stderr}")
            return False, None

        # Parse CSV response
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            logger.info("No data found in InfluxDB (empty response)")
            return False, None

        # Check if we have actual data rows (not just headers)
        for line in lines[1:]:  # Skip header
            if line.strip() and "paper_portfolio" in line:
                # Data exists, check timestamp
                parts = line.split(",")
                if len(parts) > 5:
                    # Try to extract timestamp
                    try:
                        timestamp_str = parts[5]  # _time column
                        last_time = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00")
                        )
                        age_seconds = (datetime.now(UTC) - last_time).total_seconds()
                        is_fresh = age_seconds < DATA_FRESHNESS_THRESHOLD

                        logger.debug(
                            f"Last data: {last_time.isoformat()}, "
                            f"age: {age_seconds}s, fresh: {is_fresh}"
                        )
                        return is_fresh, last_time
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Failed to parse timestamp: {e}")
                        continue

        logger.info("No recent paper_portfolio data found in InfluxDB")
        return False, None

    except subprocess.TimeoutExpired:
        logger.warning("InfluxDB query timed out")
        return False, None
    except Exception as e:
        logger.error(f"Error querying InfluxDB: {e}")
        return False, None


def check_redis_status() -> dict[str, Any]:
    """Check Redis for emitter status."""
    status: dict[str, Any] = {
        "redis_available": False,
        "emitter_status": None,
        "last_heartbeat": None,
        "heartbeat_age_seconds": None,
    }

    redis_client = get_redis_client()
    if not redis_client:
        return status

    status["redis_available"] = True

    try:
        heartbeat = redis_client.hgetall("paper_trading:heartbeat")
        if heartbeat:
            status["emitter_status"] = heartbeat.get("status")
            status["last_heartbeat"] = heartbeat.get("last_heartbeat")

            if isinstance(status["last_heartbeat"], str):
                try:
                    last_time = datetime.fromisoformat(status["last_heartbeat"])
                    status["heartbeat_age_seconds"] = (
                        datetime.now(UTC) - last_time
                    ).total_seconds()
                except ValueError:
                    pass
    except Exception as e:
        logger.debug(f"Failed to get Redis heartbeat: {e}")

    return status


def check_status_file() -> dict[str, Any]:
    """Check the emitter's status file."""
    status: dict[str, Any] = {
        "file_exists": False,
        "status": None,
        "last_heartbeat": None,
        "heartbeat_age_seconds": None,
    }

    if not STATUS_FILE.exists():
        return status

    status["file_exists"] = True

    try:
        data = json.loads(STATUS_FILE.read_text())
        status["status"] = data.get("status")
        status["last_heartbeat"] = data.get("last_heartbeat")

        if isinstance(status["last_heartbeat"], str):
            try:
                last_time = datetime.fromisoformat(status["last_heartbeat"])
                status["heartbeat_age_seconds"] = (
                    datetime.now(UTC) - last_time
                ).total_seconds()
            except ValueError:
                pass
    except (OSError, json.JSONDecodeError) as e:
        logger.debug(f"Failed to read status file: {e}")

    return status


def restart_emitter() -> bool:
    """Restart the paper trading emitter.

    Returns:
        True if restart was successful
    """
    logger.info("Attempting to restart paper trading emitter...")

    # First try using the manager script
    if MANAGER_SCRIPT.exists():
        try:
            # Stop any existing process
            subprocess.run(  # nosec B607
                ["bash", str(MANAGER_SCRIPT), "stop"],
                capture_output=True,
                timeout=10,
            )
            time.sleep(1)

            # Start new process
            result = subprocess.run(  # nosec B607
                ["bash", str(MANAGER_SCRIPT), "start"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info("Emitter restarted successfully via manager script")
                return True
            else:
                logger.warning(f"Manager script restart failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"Manager script restart failed: {e}")

    # Fallback: direct Python execution
    try:
        # Kill any existing processes
        subprocess.run(  # nosec B607
            ["pkill", "-f", "continuous_paper_emitter.py"],
            capture_output=True,
        )
        time.sleep(1)

        # Start new process
        log_file = LOG_DIR / "continuous_paper_emitter.log"
        with open(log_file, "a") as log:
            process = subprocess.Popen(
                [sys.executable, str(EMITTER_SCRIPT)],
                stdout=log,
                stderr=log,
                cwd=PROJECT_DIR,
            )

        # Write PID file
        PID_FILE.write_text(str(process.pid))

        # Wait a moment and verify
        time.sleep(2)
        is_running, pid = is_process_running(process.pid)

        if is_running:
            logger.info(f"Emitter restarted successfully (PID: {pid})")
            return True
        else:
            logger.error("Emitter process failed to stay running")
            return False

    except Exception as e:
        logger.error(f"Direct restart failed: {e}")
        return False


def perform_health_check() -> dict[str, Any]:
    """Perform comprehensive health check.

    Returns:
        Dictionary with health check results
    """
    logger.info("Performing health check...")

    results: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "process_running": False,
        "process_pid": None,
        "recent_data_in_influxdb": False,
        "last_data_time": None,
        "redis_status": {},
        "status_file": {},
        "needs_restart": False,
        "restart_reason": None,
    }

    # Check process
    is_running, pid = is_process_running()
    results["process_running"] = is_running
    results["process_pid"] = pid

    # Check InfluxDB data
    has_data, last_time = check_recent_influxdb_data()
    results["recent_data_in_influxdb"] = has_data
    results["last_data_time"] = last_time.isoformat() if last_time else None

    # Check Redis
    results["redis_status"] = check_redis_status()

    # Check status file
    results["status_file"] = check_status_file()

    # Determine if restart is needed
    restart_reasons = []

    if not is_running:
        restart_reasons.append("Process not running")

    if not has_data:
        restart_reasons.append("No recent data in InfluxDB")

    # Check heartbeat age from Redis
    redis_age = results["redis_status"].get("heartbeat_age_seconds")
    if redis_age and redis_age > DATA_FRESHNESS_THRESHOLD:
        restart_reasons.append(f"Redis heartbeat stale ({redis_age:.0f}s old)")

    # Check heartbeat age from status file
    file_age = results["status_file"].get("heartbeat_age_seconds")
    if file_age and file_age > DATA_FRESHNESS_THRESHOLD:
        restart_reasons.append(f"Status file heartbeat stale ({file_age:.0f}s old)")

    if restart_reasons:
        results["needs_restart"] = True
        results["restart_reason"] = "; ".join(restart_reasons)

    return results


def main():
    """Main monitoring loop."""
    parser = argparse.ArgumentParser(
        description="Monitor and auto-restart paper trading emitter"
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=0,
        help="Run continuously with specified check interval (seconds). "
        "If 0, run once and exit (for cron usage).",
    )
    parser.add_argument(
        "--auto-restart",
        action="store_true",
        default=True,
        help="Automatically restart emitter if unhealthy",
    )
    parser.add_argument(
        "--no-auto-restart",
        dest="auto_restart",
        action="store_false",
        help="Disable auto-restart (check only)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Paper Trading Monitor Starting")
    logger.info(f"Auto-restart: {args.auto_restart}")
    logger.info(f"Check interval: {args.check_interval or 'single run (cron mode)'}s")
    logger.info("=" * 60)

    while True:
        try:
            # Perform health check
            results = perform_health_check()

            # Log results
            logger.info("Health check results:")
            logger.info(
                f"  Process running: {results['process_running']} "
                f"(PID: {results['process_pid']})"
            )
            logger.info(f"  Recent InfluxDB data: {results['recent_data_in_influxdb']}")
            logger.info(f"  Last data time: {results['last_data_time'] or 'N/A'}")

            if results["redis_status"].get("redis_available"):
                logger.info(
                    f"  Redis status: {results['redis_status']['emitter_status']}"
                )
            else:
                logger.info("  Redis: unavailable")

            # Handle restart if needed
            if results["needs_restart"]:
                logger.warning(f"Restart needed: {results['restart_reason']}")

                if args.auto_restart:
                    success = restart_emitter()
                    if success:
                        logger.info("Auto-restart completed successfully")
                        # Wait for emitter to stabilize
                        time.sleep(5)
                        # Verify restart
                        is_running, pid = is_process_running()
                        if is_running:
                            logger.info(f"Emitter verified running (PID: {pid})")
                        else:
                            logger.error("Emitter restart verification failed")
                    else:
                        logger.error("Auto-restart failed")
                else:
                    logger.info("Auto-restart disabled, manual intervention required")
            else:
                logger.info("Health check PASSED - no action needed")

            # Exit if single run mode
            if args.check_interval <= 0:
                break

            # Wait for next check
            logger.info(f"Waiting {args.check_interval}s until next check...")
            time.sleep(args.check_interval)

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in monitor loop: {e}", exc_info=True)
            if args.check_interval <= 0:
                break
            time.sleep(args.check_interval)

    logger.info("Paper Trading Monitor exiting")


if __name__ == "__main__":
    main()
