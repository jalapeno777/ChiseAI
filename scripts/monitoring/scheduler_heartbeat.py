#!/usr/bin/env python3
"""Scheduler Heartbeat Recorder for ChiseAI.

Records heartbeat data to Redis for the trading scheduler.
This script can be run as a one-shot command or in daemon mode.

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
import logging
import os
import socket
import sys
import time
from datetime import datetime, timezone
from typing import Any

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

# TTL settings (5 minutes)
HEARTBEAT_TTL_SECONDS = 300


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
) -> bool:
    """Record a scheduler heartbeat to Redis.

    Args:
        redis_client: Connected Redis client
        status: Scheduler status ("running", "stopped", "error")
        metadata: Additional metadata to store

    Returns:
        True if successful, False otherwise
    """
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        hostname = socket.gethostname()
        pid = os.getpid()

        # Build heartbeat data
        heartbeat_data = {
            "timestamp": timestamp,
            "status": status,
            "pid": str(pid),
            "hostname": hostname,
        }

        # Add any additional metadata
        if metadata:
            heartbeat_data.update({k: str(v) for k, v in metadata.items()})

        # Store in hash
        redis_client.hset(HEARTBEAT_HASH_KEY, mapping=heartbeat_data)
        redis_client.expire(HEARTBEAT_HASH_KEY, HEARTBEAT_TTL_SECONDS)

        # Also set a simple string key for quick checks
        redis_client.set(LAST_SEEN_KEY, timestamp, ex=HEARTBEAT_TTL_SECONDS)

        logger.debug(f"Heartbeat recorded: {timestamp} (status={status})")
        return True

    except Exception as e:
        logger.error(f"Failed to record heartbeat: {e}")
        return False


def record_stop(redis_client: redis.Redis) -> bool:
    """Record that the scheduler has stopped.

    Args:
        redis_client: Connected Redis client

    Returns:
        True if successful, False otherwise
    """
    return record_heartbeat(redis_client, status="stopped")


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
    """Run heartbeat recording in daemon mode.

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

    running = True

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
            if not record_heartbeat(client, status="running"):
                logger.warning("Failed to record heartbeat, will retry")

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
        description="Scheduler Heartbeat Recorder for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # One-shot mode (for cron)
  python3 scheduler_heartbeat.py

  # Daemon mode with 30-second intervals
  python3 scheduler_heartbeat.py --daemon --interval 30

  # Custom Redis connection
  python3 scheduler_heartbeat.py --redis-host localhost --redis-port 6380

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
    else:
        return run_one_shot(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            status=args.status,
        )


if __name__ == "__main__":
    sys.exit(main())
