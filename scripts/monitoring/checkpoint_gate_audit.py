#!/usr/bin/env python3
"""6-hour checkpoint gate audit (G1-G8) for ACTIVATION-001.

Posts detailed audit to Discord #development or logs locally.
"""

import os
import sys
import asyncio
import subprocess
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List
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


def check_g1_scheduler(r: redis.Redis):
    """G1: Scheduler Continuity - Check Redis heartbeat"""
    from datetime import datetime, timezone, timedelta

    try:
        heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")

        if not heartbeat:
            return {
                "gate": "G1",
                "status": "❌ FAIL",
                "detail": "No scheduler heartbeat in Redis",
            }

        timestamp_str = heartbeat.get("timestamp", "")
        status = heartbeat.get("status", "unknown")
        uptime_seconds = heartbeat.get("uptime_seconds", "")

        if not timestamp_str:
            return {
                "gate": "G1",
                "status": "❌ FAIL",
                "detail": "Invalid heartbeat data",
            }

        # Parse timestamp and check age
        last_heartbeat = datetime.fromisoformat(timestamp_str)
        now = datetime.now(timezone.utc)
        age_seconds = (now - last_heartbeat).total_seconds()

        # Consider healthy if heartbeat within 2 minutes and status is running
        max_age = 120  # seconds

        if status != "running":
            return {
                "gate": "G1",
                "status": "❌ FAIL",
                "detail": f"Scheduler status: {status}",
            }

        if age_seconds > max_age:
            return {
                "gate": "G1",
                "status": "⚠️ CHECK",
                "detail": f"Heartbeat stale: {age_seconds:.0f}s old",
            }

        # Build detail message
        detail_parts = [f"Heartbeat {age_seconds:.0f}s ago"]
        if uptime_seconds:
            detail_parts.append(f"uptime: {int(uptime_seconds) // 60}m")

        return {
            "gate": "G1",
            "status": "✅ PASS",
            "detail": ", ".join(detail_parts),
        }

    except Exception as e:
        return {"gate": "G1", "status": "❌ FAIL", "detail": str(e)}


def check_g2_signal_cadence(r: redis.Redis):
    """G2: Signal Cadence"""
    try:
        count = len(r.keys("bmad:chiseai:signals:*"))
        if count > 0:
            return {
                "gate": "G2",
                "status": "✅ PASS",
                "detail": f"{count} signals in Redis",
            }
        else:
            return {"gate": "G2", "status": "⚠️ CHECK", "detail": "No signals found"}
    except Exception as e:
        return {"gate": "G2", "status": "❌ FAIL", "detail": str(e)}


def check_g3_data_flow(r: redis.Redis):
    """G3: Data Flow Movement"""
    try:
        count = r.scard("bmad:chiseai:outcomes:index")
        if count and count > 0:
            return {
                "gate": "G3",
                "status": "✅ PASS",
                "detail": f"{count} outcomes recorded",
            }
        else:
            return {"gate": "G3", "status": "⚠️ CHECK", "detail": "No outcomes found"}
    except Exception as e:
        return {"gate": "G3", "status": "❌ FAIL", "detail": str(e)}


def check_g4_kill_switch(r: redis.Redis):
    """G4: Kill Switch Active"""
    try:
        enabled = r.hget("bmad:chiseai:kill_switch", "enabled")
        triggered = r.hget("bmad:chiseai:kill_switch", "triggered")

        if enabled == "1" and triggered == "0":
            return {"gate": "G4", "status": "✅ PASS", "detail": "Armed and ready"}
        elif triggered == "1":
            return {
                "gate": "G4",
                "status": "🚨 ALERT",
                "detail": "TRIGGERED - Trading halted",
            }
        else:
            return {"gate": "G4", "status": "⚠️ CHECK", "detail": "Not configured"}
    except Exception as e:
        return {"gate": "G4", "status": "❌ FAIL", "detail": str(e)}


def check_g5_daily_loss(r: redis.Redis):
    """G5: Daily Loss Guard"""
    try:
        max_loss = r.hget("bmad:chiseai:daily_loss_limit", "max_loss_percent")
        if max_loss:
            return {"gate": "G5", "status": "✅ PASS", "detail": f"Limit: {max_loss}%"}
        else:
            return {"gate": "G5", "status": "⚠️ CHECK", "detail": "Not configured"}
    except Exception as e:
        return {"gate": "G5", "status": "❌ FAIL", "detail": str(e)}


def check_g6_discord_continuity(r: redis.Redis):
    """G6: Discord Continuity - Track Discord message delivery health.

    Reads continuity evidence keys from Redis:
    - chise:discord:continuity:continuity_status
    - chise:discord:continuity:last_success_at
    - chise:discord:continuity:post_count_window
    - chise:discord:continuity:failure_count_window

    Status:
    - PASS if status is "healthy"
    - CHECK if status is "degraded"
    - FAIL if status is "down" or keys don't exist
    """
    try:
        # Read continuity keys from Redis
        status = r.get("chise:discord:continuity:continuity_status")
        last_success_at = r.get("chise:discord:continuity:last_success_at")
        post_count = r.get("chise:discord:continuity:post_count_window")
        failure_count = r.get("chise:discord:continuity:failure_count_window")

        # Check if keys exist
        if status is None:
            return {
                "gate": "G6",
                "status": "❌ FAIL",
                "detail": "No continuity data in Redis - monitor not running?",
            }

        # Calculate failure rate
        post_count_int = int(post_count or "0")
        failure_count_int = int(failure_count or "0")
        failure_rate = 0.0
        if post_count_int > 0:
            failure_rate = failure_count_int / post_count_int

        # Format last success time
        last_success_display = "never"
        if last_success_at:
            try:
                from datetime import datetime, timezone

                last_dt = datetime.fromisoformat(last_success_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                seconds_ago = (now - last_dt).total_seconds()
                if seconds_ago < 60:
                    last_success_display = f"{int(seconds_ago)}s ago"
                elif seconds_ago < 3600:
                    last_success_display = f"{int(seconds_ago / 60)}m ago"
                else:
                    last_success_display = f"{int(seconds_ago / 3600)}h ago"
            except Exception:
                last_success_display = last_success_at

        # Build detail message
        detail = f"Status: {status} | Last success: {last_success_display} | Failure rate: {failure_rate:.1%} ({failure_count_int}/{post_count_int})"

        # Determine gate status
        if status == "healthy":
            return {
                "gate": "G6",
                "status": "✅ PASS",
                "detail": detail,
            }
        elif status == "degraded":
            return {
                "gate": "G6",
                "status": "⚠️ CHECK",
                "detail": detail,
            }
        else:  # down or unknown
            return {
                "gate": "G6",
                "status": "❌ FAIL",
                "detail": detail,
            }

    except Exception as e:
        return {"gate": "G6", "status": "❌ FAIL", "detail": f"Error: {str(e)[:50]}"}


def check_g7_observability(r: redis.Redis):
    """G7: Observability Health"""
    try:
        ping = r.ping()
        keys = r.dbsize()
        info = r.info("server")
        uptime = info.get("uptime_in_seconds", 0)

        if ping and uptime > 3600:
            return {
                "gate": "G7",
                "status": "✅ PASS",
                "detail": f"Redis OK, {keys} keys, {uptime // 3600}h uptime",
            }
        elif ping:
            return {
                "gate": "G7",
                "status": "⚠️ CHECK",
                "detail": f"Redis OK but uptime <1h",
            }
        else:
            return {"gate": "G7", "status": "❌ FAIL", "detail": "Redis ping failed"}
    except Exception as e:
        return {"gate": "G7", "status": "❌ FAIL", "detail": str(e)}


def check_g8_pipeline(r: redis.Redis):
    """G8: End-to-End Pipeline - Burn-in Verdict Integration

    Reads burn-in verdict from Redis string key bmad:chiseai:burnin:verdict.
    Verdict values: "GO" or "NO-GO".
    Verdict is authoritative for G8 status.
    """
    try:
        # Read burn-in verdict from Redis (stored as STRING, not hash)
        verdict = r.get("bmad:chiseai:burnin:verdict")

        # Get pipeline counts for context
        signals = len(r.keys("bmad:chiseai:signals:*"))
        outcomes = r.scard("bmad:chiseai:outcomes:index")

        if verdict is None:
            # No verdict found - burn-in not completed
            return {
                "gate": "G8",
                "status": "❓ UNKNOWN",
                "detail": "No burn-in verdict found - burn-in not completed",
            }
        elif verdict == "GO":
            # Burn-in passed - pipeline approved
            return {
                "gate": "G8",
                "status": "✅ PASS",
                "detail": f"Burn-in verdict: GO | Pipeline: {signals} signals → {outcomes} outcomes",
            }
        elif verdict == "NO-GO":
            # Burn-in failed - pipeline halted
            return {
                "gate": "G8",
                "status": "❌ FAIL",
                "detail": "Burn-in verdict: NO-GO | Pipeline halted",
            }
        else:
            # Unexpected verdict value
            return {
                "gate": "G8",
                "status": "⚠️ CHECK",
                "detail": f"Unexpected verdict: '{verdict}' | Pipeline: {signals} signals → {outcomes} outcomes",
            }
    except Exception as e:
        return {"gate": "G8", "status": "❌ FAIL", "detail": str(e)}


def run_all_checks():
    """Run all G1-G8 checks."""
    r = get_redis()
    if not r:
        return [{"gate": "ALL", "status": "❌ FAIL", "detail": "Redis unavailable"}]

    checks = [
        check_g1_scheduler(r),
        check_g2_signal_cadence(r),
        check_g3_data_flow(r),
        check_g4_kill_switch(r),
        check_g5_daily_loss(r),
        check_g6_discord_continuity(r),
        check_g7_observability(r),
        check_g8_pipeline(r),
    ]

    return checks


def format_checkpoint_message(checks: List[Dict]):
    """Format checkpoint message."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    pass_count = sum(1 for c in checks if "PASS" in c["status"])
    fail_count = sum(1 for c in checks if "FAIL" in c["status"])
    check_count = sum(1 for c in checks if "CHECK" in c["status"])

    lines = [
        f"**📊 Burn-in Checkpoint (6h)** | {timestamp}",
        f"",
        f"**Gate Status:** {pass_count} ✅ | {check_count} ⚠️ | {fail_count} ❌",
        f"",
    ]

    for check in checks:
        lines.append(f"**{check['gate']}:** {check['status']} - {check['detail']}")

    lines.extend([f"", f"_Next checkpoint in 6 hours_"])

    return "\n".join(lines)


async def post_discord(message: str):
    """Post to Discord via webhook or bot API."""
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

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json={"content": message}
                ) as resp:
                    if resp.status == 200:
                        logger.info("Discord bot post successful")
                        return True
                    else:
                        logger.error(f"Discord bot post failed: {resp.status}")
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
    else:
        logger.warning("Discord not configured")

    return False


def log_local(message: str):
    """Log locally."""
    os.makedirs("logs/monitoring", exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = f"logs/monitoring/checkpoint-{timestamp}.log"

    with open(path, "w") as f:
        f.write(message)

    return path


async def main():
    """Main checkpoint audit."""
    logger.info("Starting 6-hour checkpoint audit")

    checks = run_all_checks()
    message = format_checkpoint_message(checks)

    # Try Discord, fallback to local
    if not await post_discord(message):
        path = log_local(message)
        print(f"Discord unavailable - logged to {path}")
    else:
        print("Discord post successful")

    # Return non-zero if any FAIL
    if any("FAIL" in c["status"] for c in checks):
        return 1
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
