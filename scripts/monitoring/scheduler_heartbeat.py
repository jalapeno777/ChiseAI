#!/usr/bin/env python3
"""Scheduler Heartbeat Recorder for ChiseAI with P0 Hardening.

Records heartbeat data to Redis for the trading scheduler.
This script can be run as a one-shot command or in daemon mode.

P0 Hardening Features:
- Uptime tracking and process self-healing
- Stale heartbeat detection with auto-recovery trigger
- Watchdog that checks if heartbeat is >2m old and triggers recovery
- Exponential backoff for failed heartbeat writes
- Circuit breaker pattern for Redis failures

Usage:
    # One-shot mode (for cron)
    python3 scripts/monitoring/scheduler_heartbeat.py

    # Daemon mode
    python3 scripts/monitoring/scheduler_heartbeat.py --daemon --interval 30

    # Custom Redis connection
    python3 scripts/monitoring/scheduler_heartbeat.py --redis-host localhost --redis-port 6380

Cron Setup:
    * * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/scheduler_heartbeat.py >> /var/log/chiseai/scheduler_heartbeat.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import time
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, cast

# Add project root to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

try:
    import redis
except ImportError:
    redis = None  # type: ignore

logger = logging.getLogger(__name__)

# Redis configuration defaults
DEFAULT_REDIS_HOST = "host.docker.internal"
DEFAULT_REDIS_PORT = 6380
DEFAULT_REDIS_DB = 0

# Key patterns
HEARTBEAT_HASH_KEY = "bmad:chiseai:scheduler:heartbeat"
LAST_SEEN_KEY = "bmad:chiseai:scheduler:last_seen"
WATCHDOG_KEY = "bmad:chiseai:scheduler:watchdog"
RECOVERY_KEY = "bmad:chiseai:scheduler:recovery"
CIRCUIT_KEY = "bmad:chiseai:scheduler:circuit_breaker"

# TTL settings (5 minutes)
HEARTBEAT_TTL_SECONDS = 300

# P0 Hardening Constants
WATCHDOG_STALE_THRESHOLD_SECONDS = 120  # 2 minutes
MAX_RECOVERY_ATTEMPTS = 3
RECOVERY_COOLDOWN_SECONDS = 300  # 5 minutes
MIN_HEARTBEAT_INTERVAL = 30
MAX_HEARTBEAT_AGE_ALERT = 90
CIRCUIT_BREAKER_THRESHOLD = 5  # Failures before opening
CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60  # 1 minute before trying again
EXPONENTIAL_BACKOFF_BASE = 2
EXPONENTIAL_BACKOFF_MAX = 30  # Max 30 seconds between retries


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreaker:
    """Circuit breaker for Redis operations."""

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        timeout: int = CIRCUIT_BREAKER_TIMEOUT_SECONDS,
    ):
        self.threshold = threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = CircuitState.CLOSED

    def record_success(self) -> None:
        """Record a successful operation."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> bool:
        """Record a failed operation. Returns True if circuit opened."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.threshold:
            self.state = CircuitState.OPEN
            logger.error(f"Circuit breaker OPENED after {self.failure_count} failures")
            return True
        return False

    def can_execute(self) -> bool:
        """Check if operation can proceed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if self.last_failure_time and (
                time.time() - self.last_failure_time > self.timeout
            ):
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker entering HALF_OPEN state")
                return True
            return False

        return True  # HALF_OPEN allows one attempt

    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value


class ExponentialBackoff:
    """Exponential backoff for retries."""

    def __init__(
        self,
        base: int = EXPONENTIAL_BACKOFF_BASE,
        max_delay: int = EXPONENTIAL_BACKOFF_MAX,
    ):
        self.base = base
        self.max_delay = max_delay
        self.attempt = 0

    def next_delay(self) -> float:
        """Get next delay in seconds."""
        delay = min(self.base**self.attempt, self.max_delay)
        self.attempt += 1
        return delay

    def reset(self) -> None:
        """Reset backoff."""
        self.attempt = 0


class WatchdogMonitor:
    """Watchdog that monitors heartbeat age and triggers recovery."""

    def __init__(self, redis_client: Any | None = None):
        self.redis_client = redis_client
        self.stale_threshold = timedelta(seconds=WATCHDOG_STALE_THRESHOLD_SECONDS)

    def check_heartbeat_age(self) -> dict[str, Any]:
        """Check if heartbeat is stale and needs recovery.

        Returns:
            Dict with status, age_seconds, and recovery_needed
        """
        if not self.redis_client:
            return {
                "status": "unknown",
                "age_seconds": None,
                "recovery_needed": False,
                "error": "No Redis connection",
            }

        try:
            heartbeat = cast(
                dict[str, Any], self.redis_client.hgetall(HEARTBEAT_HASH_KEY)
            )

            if not heartbeat:
                return {
                    "status": "missing",
                    "age_seconds": None,
                    "recovery_needed": True,
                    "error": "No heartbeat found in Redis",
                }

            timestamp_str = heartbeat.get("timestamp", "")
            if not timestamp_str:
                return {
                    "status": "invalid",
                    "age_seconds": None,
                    "recovery_needed": True,
                    "error": "Heartbeat missing timestamp",
                }

            last_heartbeat = datetime.fromisoformat(timestamp_str)
            now = datetime.now(UTC)
            age = now - last_heartbeat
            age_seconds = age.total_seconds()

            recovery_needed = age > self.stale_threshold

            return {
                "status": heartbeat.get("status", "unknown"),
                "age_seconds": age_seconds,
                "recovery_needed": recovery_needed,
                "pid": heartbeat.get("pid"),
                "hostname": heartbeat.get("hostname"),
            }

        except Exception as e:
            logger.error(f"Watchdog check error: {e}")
            return {
                "status": "error",
                "age_seconds": None,
                "recovery_needed": True,
                "error": str(e),
            }

    def trigger_recovery(self, reason: str = "heartbeat_stale") -> dict[str, Any]:
        """Trigger recovery action.

        Args:
            reason: Why recovery is being triggered

        Returns:
            Dict with recovery status and details
        """
        if not self.redis_client:
            return {"success": False, "error": "No Redis connection"}

        try:
            # Get current recovery state
            recovery_data = cast(
                dict[str, Any], self.redis_client.hgetall(RECOVERY_KEY) or {}
            )
            attempt_count = int(recovery_data.get("attempt_count", 0))
            last_attempt = recovery_data.get("last_attempt")

            # Check cooldown
            if last_attempt:
                last_dt = datetime.fromisoformat(last_attempt)
                cooldown_remaining = (
                    RECOVERY_COOLDOWN_SECONDS
                    - (datetime.now(UTC) - last_dt).total_seconds()
                )
                if cooldown_remaining > 0:
                    return {
                        "success": False,
                        "error": f"Recovery on cooldown for {cooldown_remaining:.0f}s",
                        "cooldown_remaining": cooldown_remaining,
                    }

            # Increment attempt count
            attempt_count += 1

            # Store recovery trigger
            recovery_info = {
                "triggered_at": datetime.now(UTC).isoformat(),
                "reason": reason,
                "attempt_count": str(attempt_count),
                "last_attempt": datetime.now(UTC).isoformat(),
            }
            self.redis_client.hset(RECOVERY_KEY, mapping=recovery_info)
            self.redis_client.expire(RECOVERY_KEY, 86400)  # 24 hour TTL

            # Log recovery attempt
            logger.warning(
                f"Recovery triggered (attempt {attempt_count}/{MAX_RECOVERY_ATTEMPTS}): {reason}"
            )

            # Check if we should escalate
            escalate = attempt_count >= MAX_RECOVERY_ATTEMPTS

            return {
                "success": True,
                "attempt_count": attempt_count,
                "escalate": escalate,
                "reason": reason,
            }

        except Exception as e:
            logger.error(f"Recovery trigger error: {e}")
            return {"success": False, "error": str(e)}

    def clear_recovery(self) -> bool:
        """Clear recovery state after successful recovery."""
        if not self.redis_client:
            return False

        try:
            self.redis_client.delete(RECOVERY_KEY)
            logger.info("Recovery state cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear recovery state: {e}")
            return False


def get_redis_client(
    host: str = DEFAULT_REDIS_HOST,
    port: int = DEFAULT_REDIS_PORT,
    db: int = DEFAULT_REDIS_DB,
) -> redis.Redis | None:
    """Create a Redis client connection.

    Args:
        host: Redis host
        port: Redis port
        db: Redis database number

    Returns:
        Redis client or None if connection fails
    """
    if redis is None:
        logger.error("Redis package not installed. Install with: pip install redis")
        return None

    try:
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
        # Test connection
        client.ping()
        return client
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis at {host}:{port}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error connecting to Redis: {e}")
        return None


def record_heartbeat(
    redis_client: redis.Redis,
    status: str = "running",
    metadata: dict[str, Any] | None = None,
    uptime_seconds: int | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    force: bool = False,
) -> bool:
    """Record a scheduler heartbeat to Redis with P0 hardening.

    Args:
        redis_client: Connected Redis client
        status: Scheduler status ("running", "stopped", "error")
        metadata: Additional metadata to store
        uptime_seconds: Process uptime in seconds
        circuit_breaker: Circuit breaker for Redis failures

    Returns:
        True if successful, False otherwise
    """
    # Check circuit breaker
    if circuit_breaker and not circuit_breaker.can_execute():
        logger.warning(
            f"Circuit breaker is {circuit_breaker.get_state()}, skipping heartbeat"
        )
        return False

    try:
        timestamp = datetime.now(UTC).isoformat()
        hostname = socket.gethostname()
        pid = os.getpid()

        # Build heartbeat data
        heartbeat_data = {
            "timestamp": timestamp,
            "status": status,
            "pid": str(pid),
            "hostname": hostname,
        }

        # Add uptime if provided
        if uptime_seconds is not None:
            heartbeat_data["uptime_seconds"] = str(uptime_seconds)

        # Add any additional metadata
        if metadata:
            heartbeat_data.update({k: str(v) for k, v in metadata.items()})

        # Store in hash
        redis_client.hset(HEARTBEAT_HASH_KEY, mapping=heartbeat_data)
        redis_client.expire(HEARTBEAT_HASH_KEY, HEARTBEAT_TTL_SECONDS)

        # Also set a simple string key for quick checks
        redis_client.set(LAST_SEEN_KEY, timestamp, ex=HEARTBEAT_TTL_SECONDS)

        # Record success in circuit breaker
        if circuit_breaker:
            circuit_breaker.record_success()

        logger.debug(f"Heartbeat recorded: {timestamp} (status={status})")
        return True

    except Exception as e:
        logger.error(f"Failed to record heartbeat: {e}")
        # Record failure in circuit breaker
        if circuit_breaker:
            circuit_breaker.record_failure()
        return False


def record_stop(redis_client: redis.Redis) -> bool:
    """Record that the scheduler has stopped.

    Args:
        redis_client: Connected Redis client

    Returns:
        True if successful, False otherwise
    """
    return record_heartbeat(redis_client, status="stopped")


def check_heartbeat_health(redis_client: redis.Redis) -> dict[str, Any]:
    """Compatibility helper for tests and external callers."""
    watchdog = WatchdogMonitor(redis_client)
    return watchdog.check_heartbeat_age()


def run_watchdog_check(
    redis_host: str = DEFAULT_REDIS_HOST,
    redis_port: int = DEFAULT_REDIS_PORT,
) -> dict[str, Any]:
    """Run watchdog check and trigger recovery if needed.

    Args:
        redis_host: Redis host
        redis_port: Redis port

    Returns:
        Dict with check results and any recovery actions
    """
    client = get_redis_client(redis_host, redis_port)
    if client is None:
        return {"error": "Cannot connect to Redis", "recovery_triggered": False}

    watchdog = WatchdogMonitor(client)

    # Check heartbeat age
    check_result = watchdog.check_heartbeat_age()

    result = {
        "check": check_result,
        "recovery_triggered": False,
        "recovery_result": None,
    }

    # Trigger recovery if needed
    if check_result.get("recovery_needed"):
        reason = check_result.get("error", "heartbeat_stale")
        recovery_result = watchdog.trigger_recovery(reason)
        result["recovery_triggered"] = True
        result["recovery_result"] = recovery_result

        # Log recovery action
        if recovery_result.get("escalate"):
            logger.error(
                f"ESCALATION REQUIRED: Recovery failed {MAX_RECOVERY_ATTEMPTS} times"
            )

    return result


def run_one_shot(
    redis_host: str = DEFAULT_REDIS_HOST,
    redis_port: int = DEFAULT_REDIS_PORT,
    status: str = "running",
) -> int:
    """Run heartbeat recording once.

    Args:
        redis_host: Redis host
        redis_port: Redis port
        status: Status to record

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    client = get_redis_client(redis_host, redis_port)
    if client is None:
        return 1

    if record_heartbeat(client, status=status):
        logger.info("Heartbeat recorded successfully")
        return 0
    else:
        logger.error("Failed to record heartbeat")
        return 1


def run_daemon(
    interval: int = 30,
    redis_host: str = DEFAULT_REDIS_HOST,
    redis_port: int = DEFAULT_REDIS_PORT,
) -> int:
    """Run heartbeat recording in daemon mode with P0 hardening.

    Args:
        interval: Seconds between heartbeats
        redis_host: Redis host
        redis_port: Redis port

    Returns:
        Exit code (0 for clean shutdown, 1 for error)
    """
    logger.info(f"Starting scheduler heartbeat daemon (interval={interval}s)")

    client = get_redis_client(redis_host, redis_port)
    if client is None:
        logger.error("Cannot start daemon: Redis connection failed")
        return 1

    # Initialize P0 hardening components
    circuit_breaker = CircuitBreaker()
    backoff = ExponentialBackoff()
    start_time = time.time()
    running = True
    consecutive_failures = 0

    def signal_handler(signum, frame):
        nonlocal running
        logger.info(f"Received signal {signum}, shutting down...")
        running = False

    # Register signal handlers for graceful shutdown
    import signal

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        while running:
            # Calculate uptime
            uptime_seconds = int(time.time() - start_time)

            # Record heartbeat with circuit breaker
            success = record_heartbeat(
                client,
                status="running",
                uptime_seconds=uptime_seconds,
                circuit_breaker=circuit_breaker,
            )

            if success:
                consecutive_failures = 0
                backoff.reset()
            else:
                consecutive_failures += 1
                delay = backoff.next_delay()
                logger.warning(
                    f"Heartbeat failed ({consecutive_failures} consecutive), "
                    f"backing off for {delay}s"
                )
                time.sleep(delay)
                continue

            # Sleep with interrupt handling
            for _ in range(interval):
                if not running:
                    break
                time.sleep(1)

    except Exception as e:
        logger.error(f"Daemon error: {e}")
        return 1

    finally:
        # Record stop on shutdown
        logger.info("Recording stop heartbeat...")
        record_stop(client)
        logger.info("Daemon stopped")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scheduler Heartbeat Recorder for ChiseAI (P0 Hardened)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # One-shot mode (for cron)
  python3 scheduler_heartbeat.py

  # Daemon mode with 30-second intervals
  python3 scheduler_heartbeat.py --daemon --interval 30

  # Custom Redis connection
  python3 scheduler_heartbeat.py --redis-host localhost --redis-port 6380

  # Watchdog check (triggers recovery if heartbeat >2m old)
  python3 scheduler_heartbeat.py --watchdog-check

Cron Setup:
  * * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/scheduler_heartbeat.py >> /var/log/chiseai/scheduler_heartbeat.log 2>&1
        """,
    )

    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode (continuous heartbeat)",
    )

    parser.add_argument(
        "--watchdog-check",
        action="store_true",
        help="Run watchdog check and trigger recovery if needed",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Heartbeat interval in seconds (daemon mode only, default: 30)",
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
        "--status",
        default="running",
        choices=["running", "stopped", "error"],
        help="Status to record (default: running)",
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

    if args.daemon:
        return run_daemon(
            interval=args.interval,
            redis_host=args.redis_host,
            redis_port=args.redis_port,
        )
    elif args.watchdog_check:
        result = run_watchdog_check(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
        )
        print(json.dumps(result, indent=2))
        return 0 if not result.get("recovery_triggered") else 1
    else:
        return run_one_shot(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            status=args.status,
        )


if __name__ == "__main__":
    sys.exit(main())
