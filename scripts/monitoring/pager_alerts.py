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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
# Monitoring scripts use container-safe defaults per AGENTS.md
# Precedence: MONITORING_REDIS_* > REDIS_* > defaults
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
    """Check if scheduler has been down for >5 minutes."""
    try:
        # Check if process is running
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        running = any(
            "trading_activity" in line or "scheduler" in line
            for line in result.stdout.split("\n")
            if "grep" not in line
        )

        if not running:
            # Check when we last saw it running
            last_seen = r.hget(ALERT_STATE_KEY, "scheduler_last_seen")
            now = datetime.now(timezone.utc).isoformat()

            if last_seen:
                last_dt = datetime.fromisoformat(last_seen)
                elapsed = datetime.now(timezone.utc) - last_dt

                if elapsed > timedelta(minutes=5):
                    return f"⚠️ **ALERT: Scheduler down for {elapsed.seconds // 60} minutes**\nProcess not found. Check logs immediately."
            else:
                # First time seeing it down
                r.hset(ALERT_STATE_KEY, "scheduler_last_seen", now)
        else:
            # Scheduler is running, update last seen
            r.hset(
                ALERT_STATE_KEY,
                "scheduler_last_seen",
                datetime.now(timezone.utc).isoformat(),
            )

    except Exception as e:
        logger.error(f"Scheduler check error: {e}")

    return None


async def send_alert(message: str):
    """Send alert to Discord or log locally."""
    # Add @here mention for critical alerts
    full_message = f"@here {message}"

    if DISCORD_CHANNEL_ID and DISCORD_BOT_TOKEN:
        try:
            import aiohttp

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
                        logger.info("Alert sent to Discord")
                        return
        except Exception as e:
            logger.error(f"Discord error: {e}")

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
