#!/usr/bin/env python3
"""Detects lack of signal growth and warns after 2 hours.

Should be run every 30-60 minutes.

P0 HARDENING ENHANCEMENTS:
- Suppression logic when growth resumes (clear alerts)
- Trend tracking (signals/hour)
- Early warning at 1.5h instead of 2h
- Recovery confirmation message when growth resumes
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
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

DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
REDIS_HOST = os.getenv(
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))

# P0 HARDENING: Thresholds
WARNING_THRESHOLD_HOURS = 2
EARLY_WARNING_THRESHOLD_HOURS = 1.5  # Early warning threshold

# P0 HARDENING: Redis keys
ALERT_KEY = "bmad:chiseai:monitoring:signal_growth:last_count"
ALERT_TIME_KEY = "bmad:chiseai:monitoring:signal_growth:last_alert"
TREND_KEY = "bmad:chiseai:monitoring:signal_growth:trend"
RECOVERY_KEY = "bmad:chiseai:monitoring:signal_growth:recovery_notified"
EXECUTION_LOG_KEY = "bmad:chiseai:monitoring:signal_growth:execution_log"


def get_redis():
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def record_execution(r: redis.Redis, action: str, details: str = "") -> None:
    """P0 HARDENING: Record execution details."""
    try:
        now = datetime.now(timezone.utc)
        entry = {
            "timestamp": now.isoformat(),
            "action": action,
            "details": details[:200],
        }
        r.lpush(EXECUTION_LOG_KEY, json.dumps(entry))
        r.ltrim(EXECUTION_LOG_KEY, 0, 99)  # Keep last 100 entries
    except Exception as e:
        logger.error(f"Failed to record execution: {e}")


def calculate_signal_trend(r: redis.Redis, current_count: int) -> Dict[str, Any]:
    """P0 HARDENING: Calculate signals/hour trend."""
    try:
        # Get trend history
        trend_data = r.hgetall(TREND_KEY)

        if not trend_data or "first_count" not in trend_data:
            # First run - initialize trend tracking
            now = datetime.now(timezone.utc)
            r.hset(
                TREND_KEY,
                mapping={
                    "first_count": str(current_count),
                    "first_time": now.isoformat(),
                    "last_count": str(current_count),
                    "last_time": now.isoformat(),
                },
            )
            return {"status": "initialized", "signals_per_hour": 0}

        first_count = int(trend_data.get("first_count", current_count))
        first_time_str = trend_data.get("first_time", "")

        if first_time_str:
            first_time = datetime.fromisoformat(first_time_str)
            now = datetime.now(timezone.utc)
            elapsed_hours = (now - first_time).total_seconds() / 3600

            if elapsed_hours > 0:
                signals_added = current_count - first_count
                signals_per_hour = signals_added / elapsed_hours

                # Update last values
                r.hset(
                    TREND_KEY,
                    mapping={
                        "last_count": str(current_count),
                        "last_time": now.isoformat(),
                        "signals_per_hour": str(round(signals_per_hour, 2)),
                    },
                )

                return {
                    "status": "calculated",
                    "signals_per_hour": round(signals_per_hour, 2),
                    "elapsed_hours": round(elapsed_hours, 2),
                    "signals_added": signals_added,
                }

        return {"status": "no_data", "signals_per_hour": 0}

    except Exception as e:
        logger.error(f"Error calculating trend: {e}")
        return {"status": "error", "signals_per_hour": 0}


def check_signal_growth(r: redis.Redis) -> tuple[Optional[str], Optional[str]]:
    """P0 HARDENING: Check if signals have grown with enhanced logic.

    Returns:
        (message, action): Tuple of (message to send, action type)
            action can be: "warning", "early_warning", "recovery", "ok", None
    """
    try:
        current_count = len(r.keys("bmad:chiseai:signals:*"))
        last_count = r.get(ALERT_KEY)
        last_alert = r.get(ALERT_TIME_KEY)

        now = datetime.now(timezone.utc)

        # P0 HARDENING: Calculate trend
        trend = calculate_signal_trend(r, current_count)
        logger.info(f"Signal trend: {trend}")

        if last_count:
            last_count = int(last_count)

            if current_count > last_count:
                # P0 HARDENING: Growth detected - check if we need to send recovery message
                growth = current_count - last_count
                logger.info(
                    f"Signal growth detected: {last_count} -> {current_count} (+{growth})"
                )

                # Check if we had previously alerted about no growth
                recovery_notified = r.get(RECOVERY_KEY)

                if last_alert and not recovery_notified:
                    # We had an alert and now growth resumed - send recovery message
                    last_alert_dt = datetime.fromisoformat(last_alert)
                    stalled_duration = now - last_alert_dt

                    recovery_msg = (
                        f"✅ **Signal Growth Recovered**\n"
                        f"Signals resumed growing after {stalled_duration.total_seconds() // 60:.0f} minutes.\n"
                        f"Count: {last_count} → {current_count} (+{growth})\n"
                        f"Rate: {trend.get('signals_per_hour', 0):.2f} signals/hour"
                    )

                    # Mark recovery as notified
                    r.set(RECOVERY_KEY, "1", ex=3600)  # Expire after 1 hour

                    # Reset alert tracking
                    r.set(ALERT_KEY, current_count)
                    r.delete(ALERT_TIME_KEY)

                    record_execution(r, "recovery", f"Growth resumed: +{growth}")
                    return recovery_msg, "recovery"

                # Normal growth - just update tracking
                r.set(ALERT_KEY, current_count)
                r.delete(ALERT_TIME_KEY)
                r.delete(RECOVERY_KEY)  # Clear recovery flag

                record_execution(r, "growth", f"+{growth} signals")
                return None, "ok"

            elif current_count == last_count:
                # No growth - check thresholds
                if last_alert:
                    last_alert_dt = datetime.fromisoformat(last_alert)
                    elapsed = now - last_alert_dt

                    # P0 HARDENING: Early warning at 1.5h
                    if elapsed > timedelta(hours=WARNING_THRESHOLD_HOURS):
                        # Full warning - update alert time and warn
                        r.set(ALERT_TIME_KEY, now.isoformat())

                        warning_msg = (
                            f"🚨 **CRITICAL: No signal growth for {WARNING_THRESHOLD_HOURS}+ hours**\n"
                            f"Signal count stuck at {current_count}. Check signal generation pipeline immediately.\n"
                            f"Trend: {trend.get('signals_per_hour', 0):.2f} signals/hour"
                        )

                        record_execution(
                            r, "critical_warning", f"Stuck at {current_count}"
                        )
                        return warning_msg, "warning"

                    elif elapsed > timedelta(hours=EARLY_WARNING_THRESHOLD_HOURS):
                        # P0 HARDENING: Early warning at 1.5h
                        early_warning_msg = (
                            f"⚠️ **Early Warning: No signal growth for {EARLY_WARNING_THRESHOLD_HOURS:.1f}+ hours**\n"
                            f"Signal count: {current_count}. Monitor signal generation pipeline.\n"
                            f"Trend: {trend.get('signals_per_hour', 0):.2f} signals/hour"
                        )

                        record_execution(
                            r, "early_warning", f"Stuck at {current_count}"
                        )
                        return early_warning_msg, "early_warning"

                else:
                    # First time seeing no growth - record it
                    r.set(ALERT_TIME_KEY, now.isoformat())
                    record_execution(
                        r, "stalled", f"First detection at {current_count}"
                    )

        else:
            # First run - store count
            r.set(ALERT_KEY, current_count)
            record_execution(r, "init", f"Starting count: {current_count}")

    except Exception as e:
        logger.error(f"Signal growth check error: {e}")
        record_execution(r, "error", str(e)[:100])

    return None, None


async def send_message(message: str, action: str):
    """P0 HARDENING: Send message to Discord or log locally."""
    import aiohttp

    # Add emoji prefix based on action
    prefix = ""
    if action == "recovery":
        prefix = "🟢 "
    elif action == "warning":
        prefix = "🔴 "
    elif action == "early_warning":
        prefix = "🟡 "

    full_message = f"{prefix}{message}"

    # Try webhook first (more reliable)
    if DISCORD_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json={"content": full_message}
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info(f"Message sent to Discord via webhook ({action})")
                        return True
                    else:
                        logger.warning(f"Discord webhook failed: {resp.status}")
        except Exception as e:
            logger.warning(f"Discord webhook error: {e}")

    # Fall back to bot API
    if DISCORD_CHANNEL_ID and DISCORD_BOT_TOKEN:
        try:
            url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
            headers = {
                "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json={"content": full_message}
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"Message sent to Discord via bot ({action})")
                        return True
        except Exception as e:
            logger.error(f"Discord bot error: {e}")

    # Fallback
    os.makedirs("logs/monitoring", exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = (
        f"logs/monitoring/{action.upper()}-{timestamp}.log"
        if action
        else f"logs/monitoring/MSG-{timestamp}.log"
    )
    with open(filename, "w") as f:
        f.write(full_message)
    logger.info(f"Message logged locally to {filename}")


async def main():
    """Main with P0 HARDENING."""
    logger.info("=" * 60)
    logger.info("Starting signal growth detector (P0 HARDENED)")
    logger.info("=" * 60)

    r = get_redis()
    if not r:
        logger.error("Cannot connect to Redis")
        return 1

    message, action = check_signal_growth(r)

    if message and action:
        await send_message(message, action)

        # Return non-zero for warning conditions
        if action in ["warning", "early_warning"]:
            return 1
        elif action == "recovery":
            return 0  # Recovery is good
    else:
        logger.info("No action needed - signals healthy")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
