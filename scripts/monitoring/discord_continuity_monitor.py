#!/usr/bin/env python3
"""Discord Continuity Monitor - Tracks Discord message delivery health.

Runs every 5 minutes (cron) to:
1. Post a test message to Discord (webhook or bot API)
2. Track success/failure in Redis
3. Calculate continuity status based on recent history

Redis Key Schema:
- chise:discord:continuity:last_post_at = ISO timestamp of last attempted post
- chise:discord:continuity:last_success_at = ISO timestamp of last successful post
- chise:discord:continuity:post_count_window = count of posts in last 1 hour
- chise:discord:continuity:failure_count_window = count of failures in last 1 hour
- chise:discord:continuity:continuity_status = "healthy" | "degraded" | "down"

Status Calculation:
- healthy: < 10% failure rate in last hour AND last success within 10 minutes
- degraded: 10-50% failure rate OR last success 10-30 minutes ago
- down: > 50% failure rate OR last success > 30 minutes ago
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import redis
import urllib.request
import urllib.error


# Load .env file for cron environment
def load_env_file():
    """Load .env file from project root."""
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


load_env_file()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
REDIS_HOST = os.getenv(
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))

# Redis key prefixes
REDIS_PREFIX = "chise:discord:continuity"
KEY_LAST_POST_AT = f"{REDIS_PREFIX}:last_post_at"
KEY_LAST_SUCCESS_AT = f"{REDIS_PREFIX}:last_success_at"
KEY_POST_COUNT_WINDOW = f"{REDIS_PREFIX}:post_count_window"
KEY_FAILURE_COUNT_WINDOW = f"{REDIS_PREFIX}:failure_count_window"
KEY_CONTINUITY_STATUS = f"{REDIS_PREFIX}:continuity_status"

# Status thresholds
HEALTHY_FAILURE_RATE = 0.10  # 10%
DEGRADED_FAILURE_RATE = 0.50  # 50%
HEALTHY_MAX_AGE_SECONDS = 600  # 10 minutes
DEGRADED_MAX_AGE_SECONDS = 1800  # 30 minutes
WINDOW_SECONDS = 3600  # 1 hour


def get_redis() -> Optional[redis.Redis]:
    """Get Redis connection with error handling."""
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        r.ping()
        return r
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return None


def post_test_message_to_discord() -> tuple[bool, str]:
    """Post a test message to Discord via webhook or bot API.

    Returns:
        tuple: (success: bool, error_message: str)
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = f"🔔 Discord Continuity Test | {timestamp}"

    # Try webhook first (more reliable)
    if DISCORD_WEBHOOK_URL:
        try:
            data = json.dumps({"content": message}).encode("utf-8")
            req = urllib.request.Request(
                DISCORD_WEBHOOK_URL,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ChiseAI-ContinuityMonitor/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 204):
                    logger.info("Discord webhook post successful")
                    return True, ""
                else:
                    error_msg = f"Discord webhook failed: {resp.status}"
                    logger.warning(error_msg)
                    return False, error_msg
        except urllib.error.HTTPError as e:
            error_msg = f"Discord webhook HTTP error: {e.code} - {e.reason}"
            logger.warning(error_msg)
            return False, error_msg
        except urllib.error.URLError as e:
            error_msg = f"Discord webhook URL error: {e.reason}"
            logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Discord webhook error: {e}"
            logger.warning(error_msg)
            return False, error_msg

    # Fall back to bot API
    if DISCORD_CHANNEL_ID and DISCORD_BOT_TOKEN:
        try:
            url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
            data = json.dumps({"content": message}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                    "Content-Type": "application/json",
                    "User-Agent": "ChiseAI-ContinuityMonitor/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info("Discord bot post successful")
                    return True, ""
                else:
                    error_msg = f"Discord bot post failed: {resp.status}"
                    logger.warning(error_msg)
                    return False, error_msg
        except urllib.error.HTTPError as e:
            error_msg = f"Discord bot HTTP error: {e.code} - {e.reason}"
            logger.warning(error_msg)
            return False, error_msg
        except urllib.error.URLError as e:
            error_msg = f"Discord bot URL error: {e.reason}"
            logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Discord bot post error: {e}"
            logger.warning(error_msg)
            return False, error_msg

    error_msg = "Discord not configured - no webhook URL or bot token"
    logger.error(error_msg)
    return False, error_msg


def calculate_status(
    failure_rate: float, seconds_since_last_success: Optional[float]
) -> str:
    """Calculate continuity status based on failure rate and last success time.

    Args:
        failure_rate: Fraction of failures in the last hour (0.0 to 1.0)
        seconds_since_last_success: Seconds since last successful post, or None

    Returns:
        str: "healthy", "degraded", or "down"
    """
    # Check for down conditions first (most severe)
    if failure_rate > DEGRADED_FAILURE_RATE:
        return "down"

    if seconds_since_last_success is not None:
        if seconds_since_last_success > DEGRADED_MAX_AGE_SECONDS:
            return "down"
    else:
        # No successful post ever recorded
        return "down"

    # Check for degraded conditions
    if failure_rate >= HEALTHY_FAILURE_RATE:
        return "degraded"

    if seconds_since_last_success is not None:
        if seconds_since_last_success > HEALTHY_MAX_AGE_SECONDS:
            return "degraded"

    return "healthy"


def update_continuity_metrics(
    r: redis.Redis, success: bool, error_message: str
) -> Dict[str, Any]:
    """Update Redis with continuity metrics and calculate status.

    Args:
        r: Redis connection
        success: Whether the Discord post was successful
        error_message: Error message if failed

    Returns:
        Dict with current metrics and status
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat().replace("+00:00", "Z")

    # Always update last_post_at
    r.set(KEY_LAST_POST_AT, now_iso)

    # Get current window metrics
    post_count_str = r.get(KEY_POST_COUNT_WINDOW) or "0"
    failure_count_str = r.get(KEY_FAILURE_COUNT_WINDOW) or "0"
    last_success_str = r.get(KEY_LAST_SUCCESS_AT)

    post_count = int(post_count_str)
    failure_count = int(failure_count_str)

    # Update metrics based on success/failure
    if success:
        r.set(KEY_LAST_SUCCESS_AT, now_iso)
        last_success_str = now_iso
        post_count += 1
    else:
        failure_count += 1
        post_count += 1

    # Calculate failure rate
    total_attempts = post_count
    failure_rate = failure_count / total_attempts if total_attempts > 0 else 0.0

    # Calculate seconds since last success
    seconds_since_last_success = None
    if last_success_str:
        try:
            last_success = datetime.fromisoformat(
                last_success_str.replace("Z", "+00:00")
            )
            seconds_since_last_success = (now - last_success).total_seconds()
        except Exception as e:
            logger.warning(f"Failed to parse last success timestamp: {e}")

    # Calculate status
    status = calculate_status(failure_rate, seconds_since_last_success)

    # Update Redis
    r.set(KEY_POST_COUNT_WINDOW, str(post_count))
    r.set(KEY_FAILURE_COUNT_WINDOW, str(failure_count))
    r.set(KEY_CONTINUITY_STATUS, status)

    # Set TTL on window counters (they reset after 1 hour of inactivity)
    r.expire(KEY_POST_COUNT_WINDOW, WINDOW_SECONDS)
    r.expire(KEY_FAILURE_COUNT_WINDOW, WINDOW_SECONDS)

    logger.info(
        f"Continuity updated: status={status}, "
        f"failure_rate={failure_rate:.1%}, "
        f"posts={post_count}, failures={failure_count}"
    )

    return {
        "status": status,
        "failure_rate": failure_rate,
        "post_count": post_count,
        "failure_count": failure_count,
        "seconds_since_last_success": seconds_since_last_success,
        "last_success_at": last_success_str,
        "last_post_at": now_iso,
        "error_message": error_message if not success else None,
    }


def get_continuity_status(r: redis.Redis) -> Dict[str, Any]:
    """Get current continuity status from Redis.

    Args:
        r: Redis connection

    Returns:
        Dict with current metrics and status
    """
    last_post_at = r.get(KEY_LAST_POST_AT)
    last_success_at = r.get(KEY_LAST_SUCCESS_AT)
    post_count = int(r.get(KEY_POST_COUNT_WINDOW) or "0")
    failure_count = int(r.get(KEY_FAILURE_COUNT_WINDOW) or "0")
    status = r.get(KEY_CONTINUITY_STATUS) or "unknown"

    now = datetime.now(timezone.utc)

    # Calculate failure rate
    total_attempts = post_count
    failure_rate = failure_count / total_attempts if total_attempts > 0 else 0.0

    # Calculate seconds since last success
    seconds_since_last_success = None
    if last_success_at:
        try:
            last_success = datetime.fromisoformat(
                last_success_at.replace("Z", "+00:00")
            )
            seconds_since_last_success = (now - last_success).total_seconds()
        except Exception as e:
            logger.warning(f"Failed to parse last success timestamp: {e}")

    return {
        "status": status,
        "failure_rate": failure_rate,
        "post_count": post_count,
        "failure_count": failure_count,
        "seconds_since_last_success": seconds_since_last_success,
        "last_success_at": last_success_at,
        "last_post_at": last_post_at,
    }


def main() -> int:
    """Main continuity monitor function.

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    logger.info("Starting Discord continuity monitor")

    # Connect to Redis
    r = get_redis()
    if not r:
        logger.error("Redis connection failed - cannot track continuity")
        return 1

    # Post test message to Discord
    success, error_message = post_test_message_to_discord()

    # Update continuity metrics
    try:
        metrics = update_continuity_metrics(r, success, error_message)

        # Log results
        if success:
            logger.info(f"Continuity check passed: {metrics['status']}")
        else:
            logger.warning(
                f"Continuity check failed: {metrics['status']} - {error_message}"
            )

        # Return non-zero if status is down
        if metrics["status"] == "down":
            logger.error("Discord continuity is DOWN")
            return 1

        return 0

    except Exception as e:
        logger.exception(f"Failed to update continuity metrics: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
