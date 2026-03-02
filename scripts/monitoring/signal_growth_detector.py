#!/usr/bin/env python3
"""Detects lack of signal growth and warns after 2 hours.

Should be run every 30-60 minutes.
"""

import asyncio
import logging
import os
import sys
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
REDIS_HOST = os.getenv(
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))

WARNING_THRESHOLD_HOURS = 2
ALERT_KEY = "bmad:chiseai:monitoring:signal_growth:last_count"
ALERT_TIME_KEY = "bmad:chiseai:monitoring:signal_growth:last_alert"


def get_redis() -> Any | None:
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def check_signal_growth(r: Any) -> str | None:
    """Check if signals have grown in last 2 hours."""
    try:
        current_count = len(r.keys("bmad:chiseai:signals:*"))
        last_count = r.get(ALERT_KEY)
        last_alert = r.get(ALERT_TIME_KEY)

        now = datetime.now(UTC)

        if last_count:
            last_count = int(last_count)

            if current_count == last_count:
                # No growth - check how long
                if last_alert:
                    last_alert_dt = datetime.fromisoformat(last_alert)
                    elapsed = now - last_alert_dt

                    if elapsed > timedelta(hours=WARNING_THRESHOLD_HOURS):
                        # Update alert time and warn
                        r.set(ALERT_TIME_KEY, now.isoformat())
                        return f"⚠️ **WARNING: No signal growth for {WARNING_THRESHOLD_HOURS}+ hours**\nSignal count stuck at {current_count}. Check signal generation pipeline."
                else:
                    # First time seeing no growth
                    r.set(ALERT_TIME_KEY, now.isoformat())
            else:
                # Growth detected - reset
                r.set(ALERT_KEY, current_count)
                r.delete(ALERT_TIME_KEY)
                logger.info(f"Signal growth detected: {last_count} -> {current_count}")
        else:
            # First run - store count
            r.set(ALERT_KEY, current_count)

    except Exception as e:
        logger.error(f"Signal growth check error: {e}")

    return None


async def send_warning(message: str):
    """Send warning to Discord or log locally."""
    import aiohttp

    # Try webhook first (more reliable)
    if DISCORD_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json={"content": message}
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info("Warning sent to Discord via webhook")
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
                    url, headers=headers, json={"content": message}
                ) as resp:
                    if resp.status == 200:
                        logger.info("Warning sent to Discord via bot")
                        return
        except Exception as e:
            logger.error(f"Discord bot error: {e}")

    # Fallback
    os.makedirs("logs/monitoring", exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    with open(f"logs/monitoring/WARNING-{timestamp}.log", "w") as f:
        f.write(message)
    logger.info("Warning logged locally")


async def main():
    r = get_redis()
    if not r:
        logger.error("Cannot connect to Redis")
        return 1

    warning = check_signal_growth(r)
    if warning:
        await send_warning(warning)
        # Write cron evidence with error status
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from cron_evidence import write_cron_evidence

            write_cron_evidence("signal-growth", status="error", error_message=warning)
        except Exception as e:
            logger.warning(f"Failed to write cron evidence: {e}")
        return 1  # Return non-zero to indicate warning condition

    # Write cron evidence with success status
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from cron_evidence import write_cron_evidence

        write_cron_evidence("signal-growth", status="success")
    except Exception as e:
        logger.warning(f"Failed to write cron evidence: {e}")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
