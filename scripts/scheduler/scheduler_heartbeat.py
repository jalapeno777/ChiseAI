#!/usr/bin/env python3
"""Trading scheduler heartbeat recorder.

Lightweight script to record a scheduler heartbeat to Redis.
Can be run standalone or called from cron/other schedulers.
"""

import os
import sys
import logging
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv(
    "SCHEDULER_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("SCHEDULER_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))
HEARTBEAT_KEY = "bmad:chiseai:scheduler:heartbeat"


def get_redis():
    """Get Redis connection."""
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return None


def record_heartbeat(
    status: str = "running",
    message: Optional[str] = None,
    extra_fields: Optional[dict] = None,
) -> bool:
    """Record a scheduler heartbeat to Redis.

    Args:
        status: Current status (running, paused, error, stopped)
        message: Optional status message
        extra_fields: Additional fields to store

    Returns:
        True if successful, False otherwise
    """
    r = get_redis()
    if not r:
        logger.error("Cannot connect to Redis")
        return False

    try:
        now = datetime.now(timezone.utc)

        # Build heartbeat data
        heartbeat_data = {
            "timestamp": now.isoformat(),
            "status": status,
            "unix_timestamp": str(int(now.timestamp())),
        }

        if message:
            heartbeat_data["message"] = message

        # Add any extra fields
        if extra_fields:
            for key, value in extra_fields.items():
                heartbeat_data[key] = str(value)

        # Store in Redis hash
        r.hset(HEARTBEAT_KEY, mapping=heartbeat_data)

        # Set TTL on the key (7 days)
        r.expire(HEARTBEAT_KEY, 604800)

        logger.info(f"Heartbeat recorded: {status} at {now.isoformat()}")
        return True

    except Exception as e:
        logger.error(f"Failed to record heartbeat: {e}")
        return False


def get_heartbeat_info() -> Optional[dict]:
    """Get current heartbeat info from Redis.

    Returns:
        Dictionary with heartbeat data or None if not found
    """
    r = get_redis()
    if not r:
        return None

    try:
        data = r.hgetall(HEARTBEAT_KEY)
        if not data:
            return None
        return data
    except Exception as e:
        logger.error(f"Failed to get heartbeat: {e}")
        return None


def is_scheduler_healthy(max_age_seconds: int = 120) -> tuple[bool, str]:
    """Check if scheduler is healthy based on heartbeat age.

    Args:
        max_age_seconds: Maximum acceptable age of heartbeat

    Returns:
        Tuple of (is_healthy, status_message)
    """
    info = get_heartbeat_info()

    if not info:
        return False, "No heartbeat found"

    try:
        last_timestamp = info.get("timestamp", "")
        status = info.get("status", "unknown")

        if not last_timestamp:
            return False, "Invalid heartbeat data"

        last_dt = datetime.fromisoformat(last_timestamp)
        now = datetime.now(timezone.utc)
        age_seconds = (now - last_dt).total_seconds()

        if status != "running":
            return False, f"Scheduler status: {status}"

        if age_seconds > max_age_seconds:
            return False, f"Heartbeat stale: {age_seconds:.0f}s old"

        return True, f"Healthy, {age_seconds:.0f}s ago"

    except Exception as e:
        return False, f"Error checking health: {e}"


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Record or check scheduler heartbeat")
    parser.add_argument(
        "--status", default="running", help="Status to record (default: running)"
    )
    parser.add_argument("--message", help="Optional status message")
    parser.add_argument(
        "--check", action="store_true", help="Check heartbeat instead of recording"
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=120,
        help="Max acceptable heartbeat age in seconds (default: 120)",
    )

    args = parser.parse_args()

    if args.check:
        is_healthy, message = is_scheduler_healthy(args.max_age)
        if is_healthy:
            print(f"✅ Scheduler healthy: {message}")
            return 0
        else:
            print(f"❌ Scheduler unhealthy: {message}")
            return 1
    else:
        success = record_heartbeat(args.status, args.message)
        if success:
            print("Heartbeat recorded successfully")
            return 0
        else:
            print("Failed to record heartbeat")
            return 1


if __name__ == "__main__":
    exit(main())
