#!/usr/bin/env python3
"""Pager-style immediate alerts for critical conditions.

Monitors continuously (or via frequent cron) for:
- Kill switch triggered
- Scheduler down for >5 min

Posts immediately to Discord with @here mention.
"""

import os
import sys
import asyncio
import logging
import subprocess
from datetime import datetime, timezone, timedelta
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

DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
REDIS_HOST = os.getenv(
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))

ALERT_STATE_KEY = "bmad:chiseai:monitoring:pager_alerts:last_check"


def get_redis():
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def check_kill_switch_triggered(r: redis.Redis) -> Optional[str]:
    """Check if kill switch is triggered. Returns alert message if triggered."""
    try:
        triggered = r.hget("bmad:chiseai:kill_switch", "triggered")
        if triggered == "1":
            return "🚨 **CRITICAL: KILL SWITCH TRIGGERED** 🚨\nTrading has been halted. Immediate investigation required."
    except Exception as e:
        logger.error(f"Kill switch check error: {e}")
    return None


def check_scheduler_down(r: redis.Redis) -> Optional[str]:
    """Check if scheduler has been down for >5 minutes based on Redis heartbeat."""
    try:
        # Get heartbeat from Redis
        heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")
        now = datetime.now(timezone.utc)

        if not heartbeat:
            # No heartbeat found - check how long it's been missing
            last_seen = r.hget(ALERT_STATE_KEY, "scheduler_last_seen")

            if last_seen:
                last_dt = datetime.fromisoformat(last_seen)
                elapsed = now - last_dt

                if elapsed > timedelta(minutes=5):
                    return f"⚠️ **ALERT: Scheduler heartbeat missing for {elapsed.seconds // 60} minutes**\nNo heartbeat in Redis. Check if scheduler is running."
            else:
                # First time seeing no heartbeat
                r.hset(ALERT_STATE_KEY, "scheduler_last_seen", now.isoformat())
                r.expire(ALERT_STATE_KEY, 86400)  # 24 hour TTL

            return None

        # We have a heartbeat - check its age
        timestamp_str = heartbeat.get("timestamp", "")
        status = heartbeat.get("status", "unknown")

        if not timestamp_str:
            return "⚠️ **ALERT: Scheduler heartbeat has invalid timestamp**"

        last_heartbeat = datetime.fromisoformat(timestamp_str)
        elapsed = now - last_heartbeat

        # Update last seen (we have a heartbeat, even if stale)
        r.hset(ALERT_STATE_KEY, "scheduler_last_seen", now.isoformat())

        # Check if heartbeat is stale (>5 minutes old)
        if elapsed > timedelta(minutes=5):
            return f"⚠️ **ALERT: Scheduler heartbeat stale for {elapsed.seconds // 60} minutes**\nLast heartbeat: {status}. Scheduler may be hung or stopped."

        # Check if status is not running
        if status != "running":
            return f"⚠️ **ALERT: Scheduler status is '{status}'**\nScheduler is not in running state. Check logs immediately."

        # Scheduler is healthy - clear any previous alert state
        r.hdel(ALERT_STATE_KEY, "scheduler_last_seen")

    except Exception as e:
        logger.error(f"Scheduler check error: {e}")

    return None


async def send_alert(message: str):
    """Send alert to Discord or log locally."""
    # Add @here mention for critical alerts
    full_message = f"@here {message}"
    import aiohttp

    # Try webhook first (more reliable)
    if DISCORD_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json={"content": full_message}
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info("Alert sent to Discord via webhook")
                        return
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
                        logger.info("Alert sent to Discord via bot")
                        return
        except Exception as e:
            logger.error(f"Discord bot error: {e}")

    # Fallback to local log
    os.makedirs("logs/monitoring", exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with open(f"logs/monitoring/ALERT-{timestamp}.log", "w") as f:
        f.write(full_message)
    logger.info(f"Alert logged locally")


async def main():
    r = get_redis()
    if not r:
        logger.error("Cannot connect to Redis")
        return 1

    alerts = []

    # Check critical conditions
    kill_alert = check_kill_switch_triggered(r)
    if kill_alert:
        alerts.append(kill_alert)

    sched_alert = check_scheduler_down(r)
    if sched_alert:
        alerts.append(sched_alert)

    # Send alerts
    for alert in alerts:
        await send_alert(alert)

    return 0 if not alerts else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
