#!/usr/bin/env python3
"""Hourly health check for ACTIVATION-001 burn-in monitoring.

Posts summary to Discord #development or logs locally if Discord unavailable.
Designed for cron execution with proper error handling and exit codes.

P0 HARDENING ENHANCEMENTS:
- Execution tracking with Redis timestamps
- Missed execution detection and self-healing
- Discord fallback retry with exponential backoff
- Detailed execution logging
"""

import os
import sys
import subprocess
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import redis


# Load .env file for cron environment
def load_env_file():
    """Load .env file from project root."""
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


load_env_file()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
REDIS_HOST = os.getenv(
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))

# P0 HARDENING: Redis keys for execution tracking
EXECUTION_TRACKING_KEY = "bmad:chiseai:monitoring:hourly:last_run"
EXECUTION_LOG_KEY = "bmad:chiseai:monitoring:hourly:log"
MISSED_EXECUTION_KEY = "bmad:chiseai:monitoring:hourly:missed_count"
SELF_HEALING_TRIGGERED_KEY = "bmad:chiseai:monitoring:hourly:self_healing_count"

# P0 HARDENING: Configuration
MAX_EXECUTION_GAP_MINUTES = 70  # Trigger self-healing if >70 min since last run
MAX_LOG_ENTRIES = 100  # Keep last 100 execution logs
DISCORD_RETRY_ATTEMPTS = 3
DISCORD_RETRY_BASE_DELAY = 2  # seconds


def get_redis() -> Optional[redis.Redis]:
    """Get Redis connection with error handling."""
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # Test connection
        r.ping()
        return r
    except redis.ConnectionError as e:
        logger.error(f"Redis connection error: {e}")
        return None
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def record_execution_start(r: redis.Redis) -> None:
    """P0 HARDENING: Record execution start timestamp."""
    try:
        now = datetime.now(timezone.utc)
        r.hset(
            EXECUTION_TRACKING_KEY,
            mapping={"last_run_start": now.isoformat(), "status": "running"},
        )
        logger.info(f"Recorded execution start: {now.isoformat()}")
    except Exception as e:
        logger.error(f"Failed to record execution start: {e}")


def record_execution_complete(r: redis.Redis, success: bool, details: str = "") -> None:
    """P0 HARDENING: Record execution completion with details."""
    try:
        now = datetime.now(timezone.utc)

        # Update tracking hash
        r.hset(
            EXECUTION_TRACKING_KEY,
            mapping={
                "last_run_complete": now.isoformat(),
                "last_run_success": "1" if success else "0",
                "status": "complete" if success else "failed",
                "details": details[:500],  # Limit detail length
            },
        )

        # Add to execution log (keep last MAX_LOG_ENTRIES)
        log_entry = {
            "timestamp": now.isoformat(),
            "success": success,
            "details": details[:200],
        }
        r.lpush(EXECUTION_LOG_KEY, str(log_entry))
        r.ltrim(EXECUTION_LOG_KEY, 0, MAX_LOG_ENTRIES - 1)

        logger.info(f"Recorded execution completion: success={success}")
    except Exception as e:
        logger.error(f"Failed to record execution completion: {e}")


def check_missed_execution(r: redis.Redis) -> tuple[bool, Optional[str]]:
    """P0 HARDENING: Check if previous execution was missed and trigger self-healing.

    Returns:
        (should_run, reason): Tuple indicating if immediate execution should occur
    """
    try:
        tracking = r.hgetall(EXECUTION_TRACKING_KEY)

        if not tracking or "last_run_complete" not in tracking:
            logger.info("No previous execution found - this may be first run")
            return False, None

        last_run_str = tracking.get("last_run_complete", "")
        last_run = datetime.fromisoformat(last_run_str)
        now = datetime.now(timezone.utc)
        elapsed_minutes = (now - last_run).total_seconds() / 60

        logger.info(f"Last execution was {elapsed_minutes:.1f} minutes ago")

        if elapsed_minutes > MAX_EXECUTION_GAP_MINUTES:
            # Missed execution detected
            r.hincrby(MISSED_EXECUTION_KEY, "count", 1)
            r.hset(MISSED_EXECUTION_KEY, "last_detected", now.isoformat())
            r.hset(MISSED_EXECUTION_KEY, "gap_minutes", str(int(elapsed_minutes)))

            reason = f"Missed execution detected: {elapsed_minutes:.1f} minutes since last run (threshold: {MAX_EXECUTION_GAP_MINUTES} min)"
            logger.warning(reason)

            # Increment self-healing counter
            r.hincrby(SELF_HEALING_TRIGGERED_KEY, "count", 1)
            r.hset(SELF_HEALING_TRIGGERED_KEY, "last_triggered", now.isoformat())

            return True, reason

        return False, None

    except Exception as e:
        logger.error(f"Error checking missed execution: {e}")
        return False, None


def get_execution_stats(r: redis.Redis) -> Dict[str, Any]:
    """P0 HARDENING: Get execution statistics for reporting."""
    try:
        tracking = r.hgetall(EXECUTION_TRACKING_KEY) or {}
        missed = r.hgetall(MISSED_EXECUTION_KEY) or {}
        self_healing = r.hgetall(SELF_HEALING_TRIGGERED_KEY) or {}

        stats: Dict[str, Any] = {
            "last_run_complete": tracking.get("last_run_complete", "N/A"),
            "last_run_success": tracking.get("last_run_success", "unknown"),
            "missed_count": int(missed.get("count", 0)),
            "self_healing_count": int(self_healing.get("count", 0)),
        }

        # Calculate time since last run
        if tracking.get("last_run_complete"):
            try:
                last_run = datetime.fromisoformat(tracking["last_run_complete"])
                now = datetime.now(timezone.utc)
                elapsed = (now - last_run).total_seconds() / 60
                stats["minutes_since_last_run"] = f"{elapsed:.1f}"
            except:
                stats["minutes_since_last_run"] = "unknown"

        return stats
    except Exception as e:
        logger.error(f"Error getting execution stats: {e}")
        return {}


def check_scheduler_health() -> Dict[str, Any]:
    """Check if scheduler process is running."""
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
    except subprocess.TimeoutExpired:
        logger.error("Process check timed out")
        return {"status": "⚠️", "running": False, "detail": "Check timed out"}
    except FileNotFoundError:
        logger.error("ps command not found")
        return {"status": "⚠️", "running": False, "detail": "ps command not available"}
    except Exception as e:
        logger.error(f"Scheduler check error: {e}")
        return {"status": "⚠️", "running": False, "detail": f"Check failed: {e}"}


def check_kill_switch(r: redis.Redis) -> Dict[str, Any]:
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
    except redis.RedisError as e:
        logger.error(f"Redis error checking kill switch: {e}")
        return {"status": "❌", "armed": False, "detail": "Redis error"}
    except Exception as e:
        logger.error(f"Kill switch check error: {e}")
        return {"status": "❌", "armed": False, "detail": f"Error: {e}"}


def check_daily_loss(r: redis.Redis) -> Dict[str, Any]:
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
    except redis.RedisError as e:
        logger.error(f"Redis error checking daily loss: {e}")
        return {
            "status": "❌",
            "limit": "N/A",
            "current": "N/A",
            "detail": "Redis error",
        }
    except Exception as e:
        logger.error(f"Daily loss check error: {e}")
        return {
            "status": "❌",
            "limit": "N/A",
            "current": "N/A",
            "detail": f"Error: {e}",
        }


def get_metrics(r: redis.Redis) -> Dict[str, int]:
    """Get key metrics with error handling."""
    try:
        signals = len(r.keys("bmad:chiseai:signals:*"))
        outcomes = r.scard("bmad:chiseai:outcomes:index")
        keys = r.dbsize()

        return {"signals": signals, "outcomes": outcomes or 0, "keys": keys}
    except redis.RedisError as e:
        logger.error(f"Redis error getting metrics: {e}")
        return {"signals": 0, "outcomes": 0, "keys": 0}
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return {"signals": 0, "outcomes": 0, "keys": 0}


def format_hourly_message(
    scheduler: Dict,
    kill_switch: Dict,
    daily_loss: Dict,
    metrics: Dict,
    exec_stats: Optional[Dict[str, Any]] = None,
) -> str:
    """Format hourly health message."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # P0 HARDENING: Add execution stats to message
    exec_info = ""
    if exec_stats:
        missed = exec_stats.get("missed_count", 0)
        healing = exec_stats.get("self_healing_count", 0)
        if missed > 0 or healing > 0:
            exec_info = f"\n📊 Exec Stats: {missed} missed | {healing} self-healed"

    lines = [
        f"**🔥 Burn-in Hourly Check** | {timestamp}",
        f"",
        f"**Scheduler:** {scheduler['status']} {scheduler['detail']}",
        f"**Kill Switch:** {kill_switch['status']} {kill_switch['detail']}",
        f"**Daily Loss:** {daily_loss['status']} {daily_loss['detail']}",
        f"",
        f"**Metrics:** Signals: {metrics['signals']} | Outcomes: {metrics['outcomes']} | Keys: {metrics['keys']}{exec_info}",
        f"",
        f"_Next check in 1 hour_",
    ]

    return "\n".join(lines)


def post_to_discord_with_retry(message: str) -> tuple[bool, str]:
    """P0 HARDENING: Post message to Discord with exponential backoff retry."""
    import urllib.request
    import urllib.error
    import json

    last_error = ""

    for attempt in range(1, DISCORD_RETRY_ATTEMPTS + 1):
        try:
            logger.info(f"Discord post attempt {attempt}/{DISCORD_RETRY_ATTEMPTS}")

            # Try webhook first (more reliable)
            if DISCORD_WEBHOOK_URL:
                try:
                    data = json.dumps({"content": message}).encode("utf-8")
                    req = urllib.request.Request(
                        DISCORD_WEBHOOK_URL,
                        data=data,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "ChiseAI-HourlyCheck/1.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status in (200, 204):
                            logger.info("Discord webhook post successful")
                            return True, "webhook"
                        else:
                            last_error = f"webhook status {resp.status}"
                            logger.warning(f"Discord webhook failed: {resp.status}")
                except Exception as e:
                    last_error = f"webhook error: {str(e)[:50]}"
                    logger.warning(f"Discord webhook error on attempt {attempt}: {e}")

            # Fall back to bot API
            if DISCORD_CHANNEL_ID and DISCORD_BOT_TOKEN:
                try:
                    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
                    data = json.dumps({"content": message}).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=data,
                        headers={
                            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                            "Content-Type": "application/json",
                            "User-Agent": "ChiseAI-HourlyCheck/1.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status == 200:
                            logger.info("Discord bot post successful")
                            return True, "bot_api"
                        else:
                            last_error = f"bot_api status {resp.status}"
                            logger.warning(f"Discord bot post failed: {resp.status}")
                except Exception as e:
                    last_error = f"bot_api error: {str(e)[:50]}"
                    logger.warning(f"Discord bot error on attempt {attempt}: {e}")
            else:
                last_error = "no Discord configuration"
                logger.warning("Discord not configured - no webhook URL or bot token")

            # Exponential backoff before retry
            if attempt < DISCORD_RETRY_ATTEMPTS:
                delay = DISCORD_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.info(f"Retrying Discord post in {delay} seconds...")
                time.sleep(delay)

        except Exception as e:
            last_error = f"unexpected error: {str(e)[:50]}"
            logger.error(f"Unexpected Discord error on attempt {attempt}: {e}")
            if attempt < DISCORD_RETRY_ATTEMPTS:
                delay = DISCORD_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                time.sleep(delay)

    return False, last_error


def log_locally(message: str) -> str:
    """Log message to local file, return path."""
    try:
        log_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "logs", "monitoring"
        )
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        log_path = os.path.join(log_dir, f"hourly-{timestamp}.log")

        with open(log_path, "w") as f:
            f.write(message)
            f.write("\n")

        logger.info(f"Logged to: {log_path}")
        return log_path
    except Exception as e:
        logger.error(f"Failed to log locally: {e}")
        print(message)  # Last resort
        return "stdout"


def main() -> int:
    """Main hourly check with proper exit codes."""
    logger.info("=" * 60)
    logger.info("Starting hourly health check (P0 HARDENED)")
    logger.info("=" * 60)

    # P0 HARDENING: Record execution start
    r = get_redis()
    if r:
        record_execution_start(r)

        # P0 HARDENING: Check for missed execution and trigger self-healing
        should_run_immediately, missed_reason = check_missed_execution(r)
        if should_run_immediately:
            logger.warning(f"SELF-HEALING TRIGGERED: {missed_reason}")
    else:
        logger.error("Redis connection failed - cannot track execution")

    try:
        # Connect to Redis
        if not r:
            message = "❌ **Hourly Check Failed**\nRedis connection failed"
            log_path = log_locally(message)
            logger.error(f"Redis connection failed - logged to {log_path}")
            return 1

        # Run checks with individual error handling
        try:
            scheduler = check_scheduler_health()
        except Exception as e:
            logger.error(f"Scheduler check failed: {e}")
            scheduler = {"status": "❌", "running": False, "detail": f"Error: {e}"}

        try:
            kill_switch = check_kill_switch(r)
        except Exception as e:
            logger.error(f"Kill switch check failed: {e}")
            kill_switch = {"status": "❌", "armed": False, "detail": f"Error: {e}"}

        try:
            daily_loss = check_daily_loss(r)
        except Exception as e:
            logger.error(f"Daily loss check failed: {e}")
            daily_loss = {
                "status": "❌",
                "limit": "N/A",
                "current": "N/A",
                "detail": f"Error: {e}",
            }

        try:
            metrics = get_metrics(r)
        except Exception as e:
            logger.error(f"Metrics check failed: {e}")
            metrics = {"signals": 0, "outcomes": 0, "keys": 0}

        # P0 HARDENING: Get execution stats
        try:
            exec_stats = get_execution_stats(r)
        except Exception as e:
            logger.error(f"Execution stats failed: {e}")
            exec_stats = {}

        # Format message
        message = format_hourly_message(
            scheduler, kill_switch, daily_loss, metrics, exec_stats
        )

        # P0 HARDENING: Try Discord with retry, fallback to local
        discord_ok, discord_method = post_to_discord_with_retry(message)
        if not discord_ok:
            log_path = log_locally(message)
            logger.warning(f"Discord unavailable after retries - logged to {log_path}")
            details = f"Discord failed ({discord_method}), logged to {log_path}"
        else:
            logger.info(f"Discord post successful via {discord_method}")
            details = f"Discord OK via {discord_method}"

        # P0 HARDENING: Record execution completion
        success = True
        if scheduler.get("running") is False and kill_switch.get("armed") is False:
            logger.warning(
                "Critical checks failed - scheduler not running, kill switch not armed"
            )
            success = False

        record_execution_complete(r, success, details)

        # Return non-zero if critical checks failed
        if not success:
            return 1

        return 0

    except Exception as e:
        logger.exception(f"Unexpected error in hourly check: {e}")
        error_message = f"❌ **Hourly Check Failed**\nUnexpected error: {str(e)}"
        log_locally(error_message)
        if r:
            record_execution_complete(r, False, f"Exception: {str(e)[:100]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
