#!/usr/bin/env python3
"""Hourly health check for ACTIVATION-001 burn-in monitoring.

Posts summary to Discord #development or logs locally if Discord unavailable.
"""

import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Load .env for cron context (must be before other imports)
from scripts.monitoring import load_env  # noqa: F401, E402

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
REDIS_HOST = os.getenv(
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))


def get_redis():
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def check_scheduler_health():
    """Check if scheduler process is running."""
    import subprocess

    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        running = any(
            "trading_activity" in line or "scheduler" in line
            for line in result.stdout.split("\n")
            if "grep" not in line
        )
        return {
            "status": "✅" if running else "❌",
            "running": running,
            "detail": "Process active" if running else "Process not found",
        }
    except Exception as e:
        return {"status": "⚠️", "running": False, "detail": f"Check failed: {e}"}


def check_kill_switch(r: redis.Redis):
    """Check kill switch state."""
    try:
        enabled = r.hget("bmad:chiseai:kill_switch", "enabled")
        triggered = r.hget("bmad:chiseai:kill_switch", "triggered")

        if enabled == "1" and triggered == "0":
            return {"status": "✅", "armed": True, "detail": "Armed"}
        elif triggered == "1":
            return {"status": "🚨", "armed": False, "detail": "TRIGGERED"}
        else:
            return {"status": "⚠️", "armed": False, "detail": "Not configured"}
    except Exception as e:
        return {"status": "❌", "armed": False, "detail": f"Error: {e}"}


def check_daily_loss(r: redis.Redis):
    """Check daily loss limit."""
    try:
        max_loss = r.hget("bmad:chiseai:daily_loss_limit", "max_loss_percent")
        current = r.hget("bmad:chiseai:daily_loss_limit", "current_loss")

        if max_loss:
            return {
                "status": "✅",
                "limit": f"{max_loss}%",
                "current": f"${current or '0'}",
                "detail": f"Limit: {max_loss}%",
            }
        else:
            return {
                "status": "⚠️",
                "limit": "N/A",
                "current": "N/A",
                "detail": "Not configured",
            }
    except Exception as e:
        return {
            "status": "❌",
            "limit": "N/A",
            "current": "N/A",
            "detail": f"Error: {e}",
        }


def get_metrics(r: redis.Redis):
    """Get key metrics."""
    try:
        signals = len(r.keys("bmad:chiseai:signals:*"))
        outcomes = r.scard("bmad:chiseai:outcomes:index")
        keys = r.dbsize()

        return {"signals": signals, "outcomes": outcomes, "keys": keys}
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return {"signals": 0, "outcomes": 0, "keys": 0}


def format_hourly_message(scheduler, kill_switch, daily_loss, metrics):
    """Format hourly health message."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"**🔥 Burn-in Hourly Check** | {timestamp}",
        f"",
        f"**Scheduler:** {scheduler['status']} {scheduler['detail']}",
        f"**Kill Switch:** {kill_switch['status']} {kill_switch['detail']}",
        f"**Daily Loss:** {daily_loss['status']} {daily_loss['detail']}",
        f"",
        f"**Metrics:** Signals: {metrics['signals']} | Outcomes: {metrics['outcomes']} | Keys: {metrics['keys']}",
        f"",
        f"_Next check in 1 hour_",
    ]

    return "\n".join(lines)


async def post_to_discord(message: str) -> bool:
    """Post message to Discord via webhook or bot API, return True if successful."""
    import aiohttp

    # Try webhook first (more reliable)
    if DISCORD_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json={"content": message}
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info("Discord webhook post successful")
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
            payload = {"content": message}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        logger.info("Discord bot post successful")
                        return True
                    else:
                        logger.error(f"Discord bot post failed: {resp.status}")
        except Exception as e:
            logger.error(f"Discord bot post error: {e}")
    else:
        logger.warning("Discord not configured - no webhook URL or bot token")

    return False


def log_locally(message: str) -> str:
    """Log message to local file, return path."""
    log_dir = "logs/monitoring"
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = f"{log_dir}/hourly-{timestamp}.log"

    with open(log_path, "w") as f:
        f.write(message)
        f.write("\n")

    logger.info(f"Logged to: {log_path}")
    return log_path


async def main():
    """Main hourly check."""
    logger.info("Starting hourly health check")

    # Connect to Redis
    r = get_redis()
    if not r:
        message = "❌ **Hourly Check Failed**\nRedis connection failed"
        log_path = log_locally(message)
        print(f"Failed - logged to {log_path}")
        return 1

    # Run checks
    scheduler = check_scheduler_health()
    kill_switch = check_kill_switch(r)
    daily_loss = check_daily_loss(r)
    metrics = get_metrics(r)

    # Format message
    message = format_hourly_message(scheduler, kill_switch, daily_loss, metrics)

    # Try Discord, fallback to local
    discord_ok = await post_to_discord(message)
    if not discord_ok:
        log_path = log_locally(message)
        print(f"Discord unavailable - logged to {log_path}")
    else:
        print("Discord post successful")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
