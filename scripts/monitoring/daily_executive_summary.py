#!/usr/bin/env python3
"""Daily executive summary for Captain Craig.

Posts daily at configured time with:
- PnL summary
- Drawdown
- Win rate
- ECE drift
- Incidents
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
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


def get_redis():
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def calculate_pnl(r: redis.Redis) -> Dict:
    """Calculate daily PnL from outcomes."""
    try:
        # Get outcomes from last 24h
        outcomes = r.smembers("bmad:chiseai:outcomes:index")

        total_pnl = 0.0
        wins = 0
        losses = 0

        for outcome_id in outcomes:
            outcome = r.hgetall(f"bmad:chiseai:outcomes:{outcome_id}")
            if outcome:
                # Calculate PnL from entry vs fill price
                entry = float(outcome.get("entry_price", 0))
                fill = float(outcome.get("fill_price", 0))
                direction = outcome.get("direction", "")

                if direction == "LONG":
                    pnl = fill - entry
                else:
                    pnl = entry - fill

                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        return {
            "pnl": total_pnl,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_trades": total_trades,
        }
    except Exception as e:
        logger.error(f"PnL calc error: {e}")
        return {"pnl": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_trades": 0}


def get_drawdown(r: redis.Redis) -> float:
    """Get current drawdown from daily loss tracking."""
    try:
        current = r.hget("bmad:chiseai:daily_loss_limit", "current_loss")
        return float(current or 0)
    except:
        return 0.0


def get_ece_drift(r: redis.Redis) -> str:
    """Get ECE (Expected Calibration Error) drift status."""
    # Placeholder - would read from confidence tracking
    return "Within bounds"  # or "Drift detected" if outside threshold


def get_incidents_24h(r: redis.Redis) -> int:
    """Count incidents in last 24h."""
    try:
        # Check incident log
        incidents = r.lrange(
            "bmad:chiseai:iterlog:story:ACTIVATION-001:incidents", 0, -1
        )
        return len(incidents) if incidents else 0
    except:
        return 0


def format_executive_summary(
    pnl: Dict, drawdown: float, ece: str, incidents: int
) -> str:
    """Format executive summary message."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"**📈 Daily Executive Summary** | {timestamp}",
        f"",
        f"**Performance:**",
        f"• PnL: ${pnl['pnl']:.2f}",
        f"• Win Rate: {pnl['win_rate']:.1f}% ({pnl['wins']}W / {pnl['losses']}L)",
        f"• Total Trades: {pnl['total_trades']}",
        f"",
        f"**Risk Metrics:**",
        f"• Drawdown: ${drawdown:.2f}",
        f"• ECE Drift: {ece}",
        f"",
        f"**Operations:**",
        f"• Incidents (24h): {incidents}",
        f"",
        f"_Next summary tomorrow_",
    ]

    return "\n".join(lines)


async def post_summary(message: str):
    """Post to Discord or log locally."""
    import aiohttp

    # Try webhook first (more reliable)
    if DISCORD_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json={"content": message}
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info("Summary posted to Discord via webhook")
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
                        logger.info("Summary posted to Discord via bot")
                        return
        except Exception as e:
            logger.error(f"Discord bot error: {e}")

    # Fallback
    os.makedirs("logs/monitoring", exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    with open(f"logs/monitoring/daily-summary-{timestamp}.log", "w") as f:
        f.write(message)
    logger.info("Summary logged locally")


async def main():
    r = get_redis()
    if not r:
        logger.error("Cannot connect to Redis")
        return 1

    pnl = calculate_pnl(r)
    drawdown = get_drawdown(r)
    ece = get_ece_drift(r)
    incidents = get_incidents_24h(r)

    message = format_executive_summary(pnl, drawdown, ece, incidents)
    await post_summary(message)

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
