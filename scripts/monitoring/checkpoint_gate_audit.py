#!/usr/bin/env python3
"""6-hour checkpoint gate audit (G1-G8) for ACTIVATION-001.

Posts detailed audit to Discord #development or logs locally.
"""

import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Load .env for cron context (must be before other imports)
from scripts.monitoring import load_env  # noqa: F401, E402

import asyncio
import subprocess
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List
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


def check_g1_scheduler():
    """G1: Scheduler Continuity"""
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        running = any(
            "trading_activity" in line or "scheduler" in line
            for line in result.stdout.split("\n")
            if "grep" not in line
        )

        state_exists = os.path.exists("data/optimization_schedule.json")

        if running and state_exists:
            return {
                "gate": "G1",
                "status": "✅ PASS",
                "detail": "Process running, state file exists",
            }
        elif state_exists:
            return {
                "gate": "G1",
                "status": "⚠️ CHECK",
                "detail": "State exists, process not running",
            }
        else:
            return {"gate": "G1", "status": "❌ FAIL", "detail": "No process or state"}
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


def check_g6_bybit_connectivity():
    """G6: Bybit Connectivity"""
    try:
        import socket
        import ssl

        # Simple TCP connection test to Bybit API
        host = "api.bybit.com"
        port = 443
        timeout = 5

        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                # Send a simple HTTPS request
                request = f"GET /v5/market/time HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
                ssock.send(request.encode())
                response = ssock.recv(1024).decode()
                if "200 OK" in response or "HTTP/1.1" in response:
                    return {
                        "gate": "G6",
                        "status": "✅ PASS",
                        "detail": "API reachable",
                    }
                else:
                    return {
                        "gate": "G6",
                        "status": "⚠️ CHECK",
                        "detail": "API responded unexpectedly",
                    }
    except Exception as e:
        return {"gate": "G6", "status": "❌ FAIL", "detail": str(e)[:50]}


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
    """G8: End-to-End Pipeline"""
    try:
        signals = len(r.keys("bmad:chiseai:signals:*"))
        outcomes = r.scard("bmad:chiseai:outcomes:index")

        if signals > 0 and outcomes > 0:
            return {
                "gate": "G8",
                "status": "✅ PASS",
                "detail": f"Flow working: {signals} signals → {outcomes} outcomes",
            }
        else:
            return {
                "gate": "G8",
                "status": "⚠️ CHECK",
                "detail": f"Flow incomplete: {signals} signals, {outcomes} outcomes",
            }
    except Exception as e:
        return {"gate": "G8", "status": "❌ FAIL", "detail": str(e)}


def run_all_checks():
    """Run all G1-G8 checks."""
    r = get_redis()
    if not r:
        return [{"gate": "ALL", "status": "❌ FAIL", "detail": "Redis unavailable"}]

    checks = [
        check_g1_scheduler(),
        check_g2_signal_cadence(r),
        check_g3_data_flow(r),
        check_g4_kill_switch(r),
        check_g5_daily_loss(r),
        check_g6_bybit_connectivity(),
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
