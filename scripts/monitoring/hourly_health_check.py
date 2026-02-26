#!/usr/bin/env python3
"""Hourly health check for ACTIVATION-001 burn-in monitoring.

Posts summary to Discord #development or logs locally if Discord unavailable.
Designed for cron execution with proper error handling and exit codes.
"""

import os
import sys
import subprocess
import logging
from datetime import datetime, timezone
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


def check_discord_continuity(r: redis.Redis) -> Dict[str, Any]:
    """Check Discord continuity status."""
    try:
        status = r.get("chise:discord:continuity:continuity_status")
        last_success_at = r.get("chise:discord:continuity:last_success_at")
        post_count = r.get("chise:discord:continuity:post_count_window")
        failure_count = r.get("chise:discord:continuity:failure_count_window")

        if status is None:
            return {
                "status": "⚠️",
                "continuity_status": "unknown",
                "last_success": "N/A",
                "detail": "Not configured",
            }

        # Format last success time
        last_success_display = "unknown"
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
                last_success_display = last_success_at[:19]

        # Determine status emoji
        if status == "healthy":
            emoji = "✅"
        elif status == "degraded":
            emoji = "⚠️"
        else:
            emoji = "❌"

        post_count_int = int(post_count or "0")
        failure_count_int = int(failure_count or "0")
        failure_rate = 0.0
        if post_count_int > 0:
            failure_rate = failure_count_int / post_count_int

        return {
            "status": emoji,
            "continuity_status": status,
            "last_success": last_success_display,
            "failure_rate": f"{failure_rate:.1%}",
            "detail": f"{status} | Last: {last_success_display} | Fail: {failure_rate:.1%}",
        }
    except redis.RedisError as e:
        logger.error(f"Redis error checking Discord continuity: {e}")
        return {
            "status": "❌",
            "continuity_status": "error",
            "last_success": "N/A",
            "detail": "Redis error",
        }
    except Exception as e:
        logger.error(f"Discord continuity check error: {e}")
        return {
            "status": "❌",
            "continuity_status": "error",
            "last_success": "N/A",
            "detail": f"Error: {e}",
        }


def format_hourly_message(
    scheduler: Dict,
    kill_switch: Dict,
    daily_loss: Dict,
    metrics: Dict,
    discord_continuity: Dict,
) -> str:
    """Format hourly health message."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"**🔥 Burn-in Hourly Check** | {timestamp}",
        f"",
        f"**Scheduler:** {scheduler['status']} {scheduler['detail']}",
        f"**Kill Switch:** {kill_switch['status']} {kill_switch['detail']}",
        f"**Daily Loss:** {daily_loss['status']} {daily_loss['detail']}",
        f"**Discord:** {discord_continuity['status']} {discord_continuity['detail']}",
        f"",
        f"**Metrics:** Signals: {metrics['signals']} | Outcomes: {metrics['outcomes']} | Keys: {metrics['keys']}",
        f"",
        f"_Next check in 1 hour_",
    ]

    return "\n".join(lines)


def post_to_discord(message: str) -> bool:
    """Post message to Discord via webhook or bot API, synchronous for cron."""
    import urllib.request
    import urllib.error
    import json

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
                    return True
                else:
                    logger.warning(f"Discord webhook failed: {resp.status}")
        except urllib.error.HTTPError as e:
            logger.warning(f"Discord webhook HTTP error: {e.code} - {e.reason}")
        except urllib.error.URLError as e:
            logger.warning(f"Discord webhook URL error: {e.reason}")
        except Exception as e:
            logger.warning(f"Discord webhook error: {e}")

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
                    return True
                else:
                    logger.warning(f"Discord bot post failed: {resp.status}")
        except urllib.error.HTTPError as e:
            logger.warning(f"Discord bot HTTP error: {e.code} - {e.reason}")
        except urllib.error.URLError as e:
            logger.warning(f"Discord bot URL error: {e.reason}")
        except Exception as e:
            logger.error(f"Discord bot post error: {e}")
    else:
        logger.warning("Discord not configured - no webhook URL or bot token")

    return False


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
    logger.info("Starting hourly health check")

    try:
        # Connect to Redis
        r = get_redis()
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

        try:
            discord_continuity = check_discord_continuity(r)
        except Exception as e:
            logger.error(f"Discord continuity check failed: {e}")
            discord_continuity = {
                "status": "❌",
                "continuity_status": "error",
                "last_success": "N/A",
                "detail": f"Error: {e}",
            }

        # Format message
        message = format_hourly_message(
            scheduler, kill_switch, daily_loss, metrics, discord_continuity
        )

        # Try Discord, fallback to local
        discord_ok = post_to_discord(message)
        if not discord_ok:
            log_path = log_locally(message)
            logger.info(f"Discord unavailable - logged to {log_path}")
        else:
            logger.info("Discord post successful")

        # Return non-zero if critical checks failed
        if scheduler.get("running") is False and kill_switch.get("armed") is False:
            logger.warning(
                "Critical checks failed - scheduler not running, kill switch not armed"
            )
            return 1

        return 0

    except Exception as e:
        logger.exception(f"Unexpected error in hourly check: {e}")
        error_message = f"❌ **Hourly Check Failed**\nUnexpected error: {str(e)}"
        log_locally(error_message)
        return 1


if __name__ == "__main__":
    sys.exit(main())
