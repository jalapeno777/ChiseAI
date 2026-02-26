#!/usr/bin/env python3
"""Pager-style immediate alerts for critical conditions with P0 Hardening.

Monitors continuously (or via frequent cron) for:
- Kill switch triggered
- Scheduler down for >5 min

Posts immediately to Discord with @here mention.

P0 Hardening Features:
- Auto-recovery action when scheduler detected down (try to restart)
- Escalation after 3 failed recovery attempts
- Recovery success/failure logging

Usage:
    # Run check once
    python3 scripts/monitoring/pager_alerts.py

    # Run with verbose output
    python3 scripts/monitoring/pager_alerts.py --verbose
"""

import os
import sys
import asyncio
import logging
import subprocess
import json
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
RECOVERY_LOG_KEY = "bmad:chiseai:monitoring:recovery_log"
RECOVERY_ATTEMPTS_KEY = "bmad:chiseai:monitoring:recovery_attempts"

# P0 Hardening Constants
MAX_RECOVERY_ATTEMPTS = 3
RECOVERY_COOLDOWN_MINUTES = 5
SCHEDULER_DOWN_THRESHOLD_MINUTES = 5
ESCALATION_THRESHOLD = 3  # Escalate after this many failed recoveries


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

                if elapsed > timedelta(minutes=SCHEDULER_DOWN_THRESHOLD_MINUTES):
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
        if elapsed > timedelta(minutes=SCHEDULER_DOWN_THRESHOLD_MINUTES):
            return f"⚠️ **ALERT: Scheduler heartbeat stale for {elapsed.seconds // 60} minutes**\nLast heartbeat: {status}. Scheduler may be hung or stopped."

        # Check if status is not running
        if status != "running":
            return f"⚠️ **ALERT: Scheduler status is '{status}'**\nScheduler is not in running state. Check logs immediately."

        # Scheduler is healthy - clear any previous alert state
        r.hdel(ALERT_STATE_KEY, "scheduler_last_seen")

    except Exception as e:
        logger.error(f"Scheduler check error: {e}")

    return None


def log_recovery_attempt(
    r: redis.Redis,
    action: str,
    success: bool,
    details: dict = None,
) -> bool:
    """Log a recovery attempt to Redis.

    Args:
        r: Redis client
        action: Description of recovery action taken
        success: Whether the recovery was successful
        details: Additional details about the recovery

    Returns:
        True if logged successfully, False otherwise
    """
    try:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "success": str(success).lower(),
        }
        if details:
            log_entry["details"] = json.dumps(details)

        # Add to recovery log list
        r.lpush(RECOVERY_LOG_KEY, json.dumps(log_entry))
        r.ltrim(RECOVERY_LOG_KEY, 0, 99)  # Keep last 100 entries
        r.expire(RECOVERY_LOG_KEY, 604800)  # 7 day TTL

        # Update attempt counter
        if success:
            r.delete(RECOVERY_ATTEMPTS_KEY)
        else:
            r.incr(RECOVERY_ATTEMPTS_KEY)
            r.expire(RECOVERY_ATTEMPTS_KEY, 86400)  # 24 hour TTL

        return True
    except Exception as e:
        logger.error(f"Failed to log recovery attempt: {e}")
        return False


def get_recovery_attempts(r: redis.Redis) -> int:
    """Get the number of failed recovery attempts.

    Args:
        r: Redis client

    Returns:
        Number of failed recovery attempts
    """
    try:
        attempts = r.get(RECOVERY_ATTEMPTS_KEY)
        return int(attempts) if attempts else 0
    except Exception as e:
        logger.error(f"Failed to get recovery attempts: {e}")
        return 0


def check_recovery_cooldown(r: redis.Redis) -> bool:
    """Check if recovery is on cooldown.

    Args:
        r: Redis client

    Returns:
        True if recovery can proceed, False if on cooldown
    """
    try:
        last_recovery = r.hget(ALERT_STATE_KEY, "last_recovery_attempt")
        if last_recovery:
            last_dt = datetime.fromisoformat(last_recovery)
            elapsed = datetime.now(timezone.utc) - last_dt
            if elapsed < timedelta(minutes=RECOVERY_COOLDOWN_MINUTES):
                logger.info(f"Recovery on cooldown ({elapsed.seconds // 60}m ago)")
                return False
        return True
    except Exception as e:
        logger.error(f"Failed to check recovery cooldown: {e}")
        return True  # Proceed if we can't check


def attempt_scheduler_recovery(r: redis.Redis) -> dict:
    """Attempt to recover the scheduler by restarting it.

    Args:
        r: Redis client

    Returns:
        Dict with recovery result details
    """
    result = {
        "attempted": False,
        "success": False,
        "method": None,
        "error": None,
        "escalate": False,
    }

    # Check cooldown
    if not check_recovery_cooldown(r):
        result["error"] = "Recovery on cooldown"
        return result

    # Get current failure count
    failure_count = get_recovery_attempts(r)

    if failure_count >= MAX_RECOVERY_ATTEMPTS:
        result["escalate"] = True
        result["error"] = f"Max recovery attempts ({MAX_RECOVERY_ATTEMPTS}) reached"
        logger.error(result["error"])
        return result

    result["attempted"] = True
    logger.warning(
        f"Attempting scheduler recovery (attempt {failure_count + 1}/{MAX_RECOVERY_ATTEMPTS})"
    )

    # Record recovery attempt time
    try:
        r.hset(
            ALERT_STATE_KEY,
            "last_recovery_attempt",
            datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to record recovery attempt time: {e}")

    # Try to restart using trading_scheduler.py
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    scheduler_script = os.path.join(
        project_root, "scripts", "monitoring", "trading_scheduler.py"
    )

    # First, try to stop any existing scheduler
    try:
        logger.info("Stopping existing scheduler...")
        stop_result = subprocess.run(
            [sys.executable, scheduler_script, "stop"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        logger.info(f"Stop result: {stop_result.returncode}")
        if stop_result.stdout:
            logger.info(f"Stop stdout: {stop_result.stdout}")
        if stop_result.stderr:
            logger.warning(f"Stop stderr: {stop_result.stderr}")
    except Exception as e:
        logger.warning(f"Failed to stop existing scheduler: {e}")
        # Continue anyway - might not be running

    # Wait a moment for cleanup
    import time

    time.sleep(2)

    # Start the scheduler
    try:
        logger.info("Starting scheduler...")
        start_result = subprocess.run(
            [sys.executable, scheduler_script, "start"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if start_result.returncode == 0:
            logger.info("Scheduler started successfully")
            result["success"] = True
            result["method"] = "trading_scheduler_start"

            # Wait a moment and verify
            time.sleep(3)
            try:
                status_result = subprocess.run(
                    [sys.executable, scheduler_script, "status"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if status_result.returncode == 0:
                    logger.info("Scheduler status verified")
                else:
                    logger.warning("Scheduler status check failed after start")
            except Exception as e:
                logger.warning(f"Failed to verify scheduler status: {e}")
        else:
            result["error"] = f"Start failed with code {start_result.returncode}"
            if start_result.stderr:
                result["error"] += f": {start_result.stderr}"
            logger.error(result["error"])

    except subprocess.TimeoutExpired:
        result["error"] = "Scheduler start timed out"
        logger.error(result["error"])
    except Exception as e:
        result["error"] = f"Failed to start scheduler: {e}"
        logger.error(result["error"])

    # Log the recovery attempt
    log_recovery_attempt(
        r,
        f"scheduler_restart_{result['method'] or 'failed'}",
        result["success"],
        {"error": result["error"], "escalate": result["escalate"]},
    )

    # Check if we need to escalate
    if not result["success"]:
        new_failure_count = get_recovery_attempts(r)
        if new_failure_count >= ESCALATION_THRESHOLD:
            result["escalate"] = True
            logger.error(
                f"ESCALATION REQUIRED: {new_failure_count} failed recovery attempts"
            )

    return result


async def send_alert(message: str, is_escalation: bool = False):
    """Send alert to Discord or log locally."""
    # Add @here mention for critical alerts
    prefix = "@here " if is_escalation else ""
    full_message = f"{prefix}{message}"
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
    recovery_performed = False
    recovery_result = None

    # Check critical conditions
    kill_alert = check_kill_switch_triggered(r)
    if kill_alert:
        alerts.append((kill_alert, True))  # (message, is_escalation)

    sched_alert = check_scheduler_down(r)
    if sched_alert:
        # Try auto-recovery first
        recovery_result = attempt_scheduler_recovery(r)
        recovery_performed = recovery_result["attempted"]

        if recovery_result["success"]:
            # Recovery successful - send info alert
            recovery_msg = f"✅ **RECOVERY SUCCESSFUL**: Scheduler was restarted automatically after being down."
            alerts.append((recovery_msg, False))
        else:
            # Recovery failed - add to alerts
            alerts.append((sched_alert, recovery_result.get("escalate", False)))

            if recovery_result.get("escalate"):
                escalation_msg = (
                    f"🚨 **ESCALATION REQUIRED**: Scheduler recovery failed {ESCALATION_THRESHOLD}+ times. "
                    f"Manual intervention required!"
                )
                alerts.append((escalation_msg, True))

    # Send alerts
    for alert_msg, is_escalation in alerts:
        await send_alert(alert_msg, is_escalation)

    # Log summary
    if recovery_performed:
        logger.info(
            f"Recovery attempt: success={recovery_result.get('success', False)}, "
            f"escalate={recovery_result.get('escalate', False)}"
        )

    return (
        0
        if not alerts or (recovery_performed and recovery_result.get("success"))
        else 1
    )


if __name__ == "__main__":
    exit(asyncio.run(main()))
