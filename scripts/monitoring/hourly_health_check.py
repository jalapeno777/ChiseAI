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


def check_scheduler_health(r: redis.Redis) -> Dict[str, Any]:
    """Check if scheduler process is running with heartbeat validation.

    Self-validation: Verifies heartbeat data exists in Redis.
    Shows UNKNOWN if no heartbeat data.
    """
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        running = any(
            "trading_activity" in line or "scheduler" in line
            for line in result.stdout.split("\n")
            if "grep" not in line
        )

        # Check for heartbeat data (self-validation)
        heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat") if r else {}
        last_seen = r.get("bmad:chiseai:scheduler:last_seen") if r else None
        has_heartbeat = bool(heartbeat or last_seen)

        # Truthful status reporting
        if not has_heartbeat:
            return {
                "status": "❓",
                "running": running,
                "detail": "No heartbeat data - scheduler not configured",
                "self_validation": "WARNING: Cannot verify scheduler health without heartbeat",
                "recommendation": "Configure scheduler heartbeat reporting",
            }
        elif running:
            return {
                "status": "✅",
                "running": True,
                "detail": f"Process active, heartbeat: {last_seen or 'present'}",
                "self_validation": "OK",
            }
        else:
            return {
                "status": "❌",
                "running": False,
                "detail": "Process not found but heartbeat exists (may be stale)",
                "self_validation": "WARNING: Heartbeat exists but process not running",
                "recommendation": "Check for zombie processes or stale heartbeat",
            }
    except subprocess.TimeoutExpired:
        logger.error("Process check timed out")
        return {
            "status": "⚠️",
            "running": False,
            "detail": "Check timed out",
            "self_validation": "ERROR",
        }
    except FileNotFoundError:
        logger.error("ps command not found")
        return {
            "status": "⚠️",
            "running": False,
            "detail": "ps command not available",
            "self_validation": "ERROR",
        }
    except Exception as e:
        logger.error(f"Scheduler check error: {e}")
        return {
            "status": "⚠️",
            "running": False,
            "detail": f"Check failed: {e}",
            "self_validation": "ERROR",
        }


def check_kill_switch(r: redis.Redis) -> Dict[str, Any]:
    """Check kill switch state with self-validation.

    Self-validation: Distinguishes between not configured and disabled.
    Shows NOT_CONFIGURED when kill switch is not set up.
    """
    try:
        enabled = r.hget("bmad:chiseai:kill_switch", "enabled")
        triggered = r.hget("bmad:chiseai:kill_switch", "triggered")

        # Check if actually configured
        is_configured = enabled is not None

        if not is_configured:
            return {
                "status": "⚙️",
                "armed": False,
                "detail": "Not configured",
                "self_validation": "WARNING: Kill switch not configured - safety feature missing",
                "recommendation": "Configure kill switch before trading",
            }
        elif triggered == "1":
            return {
                "status": "🚨",
                "armed": False,
                "detail": "TRIGGERED",
                "self_validation": "ALERT: Kill switch has been triggered",
            }
        elif enabled == "1":
            return {
                "status": "✅",
                "armed": True,
                "detail": "Armed",
                "self_validation": "OK",
            }
        else:
            return {
                "status": "⚠️",
                "armed": False,
                "detail": "Configured but disabled",
                "self_validation": "WARNING: Kill switch configured but not enabled",
                "recommendation": "Enable kill switch for safety",
            }
    except redis.RedisError as e:
        logger.error(f"Redis error checking kill switch: {e}")
        return {
            "status": "❌",
            "armed": False,
            "detail": "Redis error",
            "self_validation": "ERROR",
        }
    except Exception as e:
        logger.error(f"Kill switch check error: {e}")
        return {
            "status": "❌",
            "armed": False,
            "detail": f"Error: {e}",
            "self_validation": "ERROR",
        }


def check_daily_loss(r: redis.Redis) -> Dict[str, Any]:
    """Check daily loss limit with self-validation.

    Self-validation: Distinguishes between not configured and missing current data.
    Shows NOT_CONFIGURED when loss limit is not set up.
    """
    try:
        max_loss = r.hget("bmad:chiseai:daily_loss_limit", "max_loss_percent")
        current = r.hget("bmad:chiseai:daily_loss_limit", "current_loss")

        if max_loss is None:
            return {
                "status": "⚙️",
                "limit": "N/A",
                "current": "N/A",
                "detail": "Not configured",
                "self_validation": "WARNING: Daily loss limit not configured - risk guard missing",
                "recommendation": "Configure daily loss limit before trading",
            }
        elif current is None:
            return {
                "status": "⚠️",
                "limit": f"{max_loss}%",
                "current": "N/A",
                "detail": f"Limit: {max_loss}% but no current data",
                "self_validation": "WARNING: Loss limit configured but no current loss tracking",
                "recommendation": "Verify loss tracking is active",
            }
        else:
            # Check if limit reached
            try:
                current_val = float(current)
                max_val = float(max_loss)
                if current_val >= max_val:
                    return {
                        "status": "🚨",
                        "limit": f"{max_loss}%",
                        "current": f"${current}",
                        "detail": f"LIMIT REACHED: ${current_val:.2f} / {max_val}%",
                        "self_validation": "ALERT: Daily loss limit has been reached",
                    }
            except (ValueError, TypeError):
                pass

            return {
                "status": "✅",
                "limit": f"{max_loss}%",
                "current": f"${current}",
                "detail": f"Limit: {max_loss}%, Current: ${current}",
                "self_validation": "OK",
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
    scheduler: Dict, kill_switch: Dict, daily_loss: Dict, metrics: Dict
) -> str:
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
            scheduler = check_scheduler_health(r)
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

        # Format message
        message = format_hourly_message(scheduler, kill_switch, daily_loss, metrics)

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
