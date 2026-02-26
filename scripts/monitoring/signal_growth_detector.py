#!/usr/bin/env python3
"""Detects lack of signal growth and warns after 2 hours.

Should be run every 30-60 minutes.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
REDIS_HOST = os.getenv("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))

WARNING_THRESHOLD_HOURS = 2
ALERT_KEY = "bmad:chiseai:monitoring:signal_growth:last_count"
ALERT_TIME_KEY = "bmad:chiseai:monitoring:signal_growth:last_alert"


def get_redis():
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def check_signal_growth(r: redis.Redis) -> Optional[str]:
    """Check if signals have grown in last 2 hours."""
    try:
        current_count = len(r.keys("bmad:chiseai:signals:*"))
        last_count = r.get(ALERT_KEY)
        last_alert = r.get(ALERT_TIME_KEY)

        now = datetime.now(timezone.utc)

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
                    url, headers=headers, json={"content": message}
                ) as resp:
                    if resp.status == 200:
                        logger.info("Warning sent to Discord")
                        return
        except Exception as e:
            logger.error(f"Discord error: {e}")

    # Fallback
    os.makedirs("logs/monitoring", exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
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
        return 1  # Return non-zero to indicate warning condition

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
