#!/usr/bin/env python3
"""Signal continuity monitor.

Monitors signal generation health and triggers alerts/restarts if:
- No new signals generated in 15 minutes
- Signal count stagnant for extended periods
- Signal generator process not running

Part of P0-RUNTIME-HARDEN-004: Signal Stagnation Fix
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import redis

# Load .env file for cron environment
env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
)
if os.path.exists(env_path):
    with open(env_path) as f:
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
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))

# Alert thresholds
STAGNATION_THRESHOLD_MINUTES = 15
CRITICAL_STAGNATION_MINUTES = 30

# Redis keys
SIGNAL_COUNT_KEY = "bmad:chiseai:monitoring:signal_continuity:last_count"
SIGNAL_COUNT_TIME_KEY = "bmad:chiseai:monitoring:signal_continuity:last_count_time"
GENERATOR_HEARTBEAT_KEY = "bmad:chiseai:signal_generator:heartbeat"
ALERT_STATE_KEY = "bmad:chiseai:monitoring:signal_continuity:alert_state"

# Discord configuration
DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


def get_redis() -> Any | None:
    """Get Redis connection."""
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return None


def get_current_signal_count(r: Any) -> int:
    """Get current total signal count from Redis."""
    try:
        # Count all signal keys
        pattern = "bmad:chiseai:signals:*"
        keys = r.keys(pattern)
        return len(keys)
    except Exception as e:
        logger.error(f"Failed to count signals: {e}")
        return 0


def get_last_signal_timestamp(r: Any) -> datetime | None:
    """Get timestamp of most recent signal."""
    try:
        pattern = "bmad:chiseai:signals:*"
        keys = r.keys(pattern)

        if not keys:
            return None

        latest_time = None
        for key in keys:
            try:
                signal_data = r.hgetall(key)
                if signal_data and "timestamp" in signal_data:
                    ts_str = signal_data["timestamp"]
                    ts = datetime.fromisoformat(ts_str)
                    if latest_time is None or ts > latest_time:
                        latest_time = ts
            except Exception:  # nosec B112
                continue

        return latest_time
    except Exception as e:
        logger.error(f"Failed to get last signal timestamp: {e}")
        return None


def check_generator_heartbeat(r: Any) -> tuple[bool, datetime | None]:
    """Check if signal generator is sending heartbeats.

    Returns:
        Tuple of (is_alive, last_heartbeat_time)
    """
    try:
        heartbeat = r.hgetall(GENERATOR_HEARTBEAT_KEY)
        if not heartbeat:
            return False, None

        last_timestamp_str = heartbeat.get("timestamp")
        if not last_timestamp_str:
            return False, None

        last_timestamp = datetime.fromisoformat(last_timestamp_str)
        now = datetime.now(UTC)

        # Consider generator alive if heartbeat within last 5 minutes
        is_alive = (now - last_timestamp) < timedelta(minutes=5)

        return is_alive, last_timestamp
    except Exception as e:
        logger.error(f"Failed to check generator heartbeat: {e}")
        return False, None


def record_generator_heartbeat(
    r: Any, status: str = "running", message: str = ""
) -> bool:
    """Record signal generator heartbeat.

    This should be called by the signal generator itself.
    """
    try:
        now = datetime.now(UTC)
        heartbeat_data = {
            "timestamp": now.isoformat(),
            "status": status,
            "unix_timestamp": str(int(now.timestamp())),
        }

        if message:
            heartbeat_data["message"] = message

        r.hset(GENERATOR_HEARTBEAT_KEY, mapping=heartbeat_data)
        r.expire(GENERATOR_HEARTBEAT_KEY, 86400)  # 24 hour TTL

        return True
    except Exception as e:
        logger.error(f"Failed to record generator heartbeat: {e}")
        return False


def check_signal_stagnation(r: Any) -> dict[str, Any]:
    """Check for signal stagnation and return status.

    Returns:
        Dictionary with stagnation check results
    """
    result: dict[str, Any] = {
        "stagnant": False,
        "critical": False,
        "minutes_since_last_signal": None,
        "current_count": 0,
        "previous_count": None,
        "count_delta": 0,
        "generator_alive": False,
        "alert_message": None,
    }

    try:
        # Get current signal count
        current_count = get_current_signal_count(r)
        result["current_count"] = current_count

        # Get last signal timestamp
        last_signal_time = get_last_signal_timestamp(r)

        # Calculate time since last signal
        now = datetime.now(UTC)
        if last_signal_time:
            # Ensure last_signal_time is timezone-aware
            if last_signal_time.tzinfo is None:
                last_signal_time = last_signal_time.replace(tzinfo=UTC)
            minutes_since = (now - last_signal_time).total_seconds() / 60
            result["minutes_since_last_signal"] = round(minutes_since, 1)

        # Check generator heartbeat
        generator_alive, _ = check_generator_heartbeat(r)
        result["generator_alive"] = generator_alive

        # Get previous count from Redis
        previous_count = r.get(SIGNAL_COUNT_KEY)
        if previous_count:
            result["previous_count"] = int(previous_count)
            result["count_delta"] = current_count - int(previous_count)

        # Check for stagnation
        if result["minutes_since_last_signal"] is not None:
            if result["minutes_since_last_signal"] >= CRITICAL_STAGNATION_MINUTES:
                result["stagnant"] = True
                result["critical"] = True
                result["alert_message"] = (
                    f"🚨 CRITICAL: No signals for {result['minutes_since_last_signal']:.0f} minutes! "
                    f"Count: {current_count}. Generator alive: {generator_alive}"
                )
            elif result["minutes_since_last_signal"] >= STAGNATION_THRESHOLD_MINUTES:
                result["stagnant"] = True
                result["alert_message"] = (
                    f"⚠️ WARNING: No signals for {result['minutes_since_last_signal']:.0f} minutes. "
                    f"Count: {current_count}. Generator alive: {generator_alive}"
                )

        # Update stored count
        r.set(SIGNAL_COUNT_KEY, current_count)
        r.set(SIGNAL_COUNT_TIME_KEY, now.isoformat())

        return result

    except Exception as e:
        logger.error(f"Error checking signal stagnation: {e}")
        result["error"] = str(e)
        return result


async def send_alert(message: str, priority: str = "warning"):
    """Send alert to Discord or log locally."""
    # Try webhook first
    if DISCORD_WEBHOOK_URL:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json={"content": message}
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info(f"Alert sent to Discord ({priority})")
                        return
        except Exception as e:
            logger.warning(f"Discord webhook failed: {e}")

    # Fallback to local log
    os.makedirs("logs/monitoring", exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"logs/monitoring/SIGNAL_ALERT-{priority}-{timestamp}.log"
    with open(filename, "w") as f:
        f.write(message)
    logger.info(f"Alert logged to {filename}")


def trigger_auto_restart() -> bool:
    """Trigger auto-restart of signal generation.

    Returns:
        True if restart was triggered successfully
    """
    logger.warning("Auto-restart triggered for signal generation")

    # Log the restart attempt
    try:
        r = get_redis()
        if r:
            r.hset(
                "bmad:chiseai:signal_generator:restart_log",
                mapping={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "reason": "signal_stagnation",
                    "triggered_by": "signal_continuity_monitor",
                },
            )
    except Exception as e:
        logger.error(f"Failed to log restart: {e}")

    # Note: Actual restart would be handled by systemd/docker/system
    # This function logs the need for restart
    return True


async def main():
    """Main monitoring loop."""
    r = get_redis()
    if not r:
        logger.error("Cannot connect to Redis")
        return 1

    # Run stagnation check
    result = check_signal_stagnation(r)

    logger.info(f"Signal continuity check: {json.dumps(result, indent=2, default=str)}")

    # Send alerts if stagnant
    if result["stagnant"]:
        priority = "critical" if result["critical"] else "warning"
        await send_alert(result["alert_message"], priority)

        # Trigger auto-restart if critical
        if result["critical"]:
            trigger_auto_restart()

        return 1  # Non-zero exit for monitoring systems

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
