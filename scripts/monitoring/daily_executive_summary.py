#!/usr/bin/env python3
"""Daily executive summary for Captain Craig.

Posts daily at configured time with:
- PnL summary
- Drawdown
- Win rate
- ECE drift
- Incidents

Designed for cron execution with proper error handling and exit codes.
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any
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


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def validate_outcome_data(r: redis.Redis) -> Dict[str, Any]:
    """Validate that outcome data exists and is recent.

    Returns validation status and warnings about data quality.
    """
    try:
        outcomes = r.smembers("bmad:chiseai:outcomes:index")

        if not outcomes:
            return {
                "valid": False,
                "status": "NO_DATA",
                "warning": "No outcome data found - trading may not be active",
                "recommendation": "Verify trading system is running and recording outcomes",
                "outcome_count": 0,
                "recent_count": 0,
            }

        # Check for recent outcomes (within 24 hours)
        recent_count = 0
        current_time = datetime.now(timezone.utc).timestamp()

        for outcome_id in list(outcomes)[:20]:  # Sample first 20
            try:
                outcome = r.hgetall(f"bmad:chiseai:outcomes:{outcome_id}")
                if outcome:
                    timestamp = outcome.get("timestamp") or outcome.get("created_at")
                    if timestamp:
                        try:
                            outcome_time = float(timestamp)
                            if current_time - outcome_time < 86400:  # Within 24h
                                recent_count += 1
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass

        outcome_count = len(outcomes)

        if recent_count == 0 and outcome_count > 0:
            return {
                "valid": True,
                "status": "STALE_DATA",
                "warning": f"{outcome_count} outcomes but none recent - data may be stale",
                "recommendation": "Check if trading is still active",
                "outcome_count": outcome_count,
                "recent_count": 0,
            }

        return {
            "valid": True,
            "status": "HEALTHY",
            "warning": None,
            "recommendation": None,
            "outcome_count": outcome_count,
            "recent_count": recent_count,
        }
    except Exception as e:
        logger.error(f"Outcome validation error: {e}")
        return {
            "valid": False,
            "status": "ERROR",
            "warning": f"Could not validate outcome data: {e}",
            "recommendation": "Check Redis connectivity",
            "outcome_count": 0,
            "recent_count": 0,
        }


def calculate_pnl(r: redis.Redis) -> Dict[str, Any]:
    """Calculate daily PnL from outcomes with robust error handling and validation.

    Self-validation: Checks that outcome data exists and is recent.
    Reports warnings when data may be stale or incomplete.
    """
    # First validate the data
    validation = validate_outcome_data(r)

    try:
        # Get outcomes from last 24h
        outcomes = r.smembers("bmad:chiseai:outcomes:index")

        if not outcomes:
            logger.info("No outcomes found in Redis")
            return {
                "pnl": 0.0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_trades": 0,
                "data_status": validation["status"],
                "data_warning": validation.get("warning"),
                "data_recommendation": validation.get("recommendation"),
            }

        total_pnl = 0.0
        wins = 0
        losses = 0

        for outcome_id in outcomes:
            try:
                outcome = r.hgetall(f"bmad:chiseai:outcomes:{outcome_id}")
                if not outcome:
                    continue

                # Safely extract values with defaults
                entry = safe_float(outcome.get("entry_price"), 0.0)
                fill = safe_float(outcome.get("fill_price"), 0.0)
                direction = outcome.get("direction", "").upper()

                # Skip invalid data
                if entry == 0 and fill == 0:
                    continue

                # Calculate PnL
                if direction == "LONG":
                    pnl = fill - entry
                elif direction == "SHORT":
                    pnl = entry - fill
                else:
                    # Unknown direction, skip
                    logger.warning(
                        f"Unknown direction for outcome {outcome_id}: {direction}"
                    )
                    continue

                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1
            except Exception as e:
                logger.warning(f"Error processing outcome {outcome_id}: {e}")
                continue

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

        return {
            "pnl": round(total_pnl, 2),
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "data_status": validation["status"],
            "data_warning": validation.get("warning"),
            "data_recommendation": validation.get("recommendation"),
        }
    except redis.RedisError as e:
        logger.error(f"Redis error during PnL calculation: {e}")
        return {
            "pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_trades": 0,
            "data_status": "ERROR",
            "data_warning": f"Redis error: {e}",
            "data_recommendation": "Check Redis connectivity",
        }
    except Exception as e:
        logger.error(f"PnL calc error: {e}")
        return {
            "pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_trades": 0,
            "data_status": "ERROR",
            "data_warning": f"Calculation error: {e}",
            "data_recommendation": "Check outcome data format",
        }


def get_drawdown(r: redis.Redis) -> float:
    """Get current drawdown from daily loss tracking."""
    try:
        current = r.hget("bmad:chiseai:daily_loss_limit", "current_loss")
        return safe_float(current, 0.0)
    except redis.RedisError as e:
        logger.error(f"Redis error getting drawdown: {e}")
        return 0.0
    except Exception as e:
        logger.error(f"Drawdown error: {e}")
        return 0.0


def get_ece_drift(r: redis.Redis) -> str:
    """Get ECE (Expected Calibration Error) drift status."""
    try:
        # Check if ECE tracking key exists
        ece_data = r.hgetall("bmad:chiseai:ece_drift")
        if ece_data:
            status = ece_data.get("status", "unknown")
            if status == "drift":
                return "Drift detected"
            elif status == "ok":
                return "Within bounds"
        return "No ECE data"
    except Exception as e:
        logger.warning(f"ECE drift check failed: {e}")
        return "Unknown"


def get_incidents_24h(r: redis.Redis) -> int:
    """Count incidents in last 24h."""
    try:
        # Check incident log for any story
        incident_keys = r.keys("bmad:chiseai:iterlog:story:*:incidents")
        total_incidents = 0

        for key in incident_keys:
            try:
                incidents = r.lrange(key, 0, -1)
                if incidents:
                    total_incidents += len(incidents)
            except Exception as e:
                logger.warning(f"Error reading incidents from {key}: {e}")
                continue

        return total_incidents
    except redis.RedisError as e:
        logger.error(f"Redis error getting incidents: {e}")
        return 0
    except Exception as e:
        logger.error(f"Incidents error: {e}")
        return 0


def format_executive_summary(
    pnl: Dict, drawdown: float, ece: str, incidents: int
) -> str:
    """Format executive summary message with data validation warnings."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Determine PnL emoji
    pnl_emoji = "🟢" if pnl["pnl"] >= 0 else "🔴"

    # Get data validation info
    data_status = pnl.get("data_status", "UNKNOWN")
    data_warning = pnl.get("data_warning")
    data_recommendation = pnl.get("data_recommendation")

    # Status emoji for data
    status_emoji = {
        "HEALTHY": "✅",
        "STALE_DATA": "⏰",
        "NO_DATA": "❓",
        "ERROR": "❌",
    }.get(data_status, "❓")

    lines = [
        f"**📈 Daily Executive Summary** | {timestamp}",
        f"",
        f"**Performance:**",
        f"• PnL: {pnl_emoji} ${pnl['pnl']:.2f}",
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
        f"**Data Quality:** {status_emoji} {data_status}",
    ]

    # Add warnings if present
    if data_warning:
        lines.append(f"⚠️ {data_warning}")
    if data_recommendation:
        lines.append(f"💡 {data_recommendation}")

    lines.extend(
        [
            f"",
            f"_Next summary tomorrow_",
        ]
    )

    return "\n".join(lines)


def post_summary(message: str) -> bool:
    """Post to Discord or log locally. Synchronous version for cron."""
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
                    "User-Agent": "ChiseAI-DailySummary/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 204):
                    logger.info("Summary posted to Discord via webhook")
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
                    "User-Agent": "ChiseAI-DailySummary/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info("Summary posted to Discord via bot")
                    return True
                else:
                    logger.warning(f"Discord bot API failed: {resp.status}")
        except urllib.error.HTTPError as e:
            logger.warning(f"Discord bot HTTP error: {e.code} - {e.reason}")
        except urllib.error.URLError as e:
            logger.warning(f"Discord bot URL error: {e.reason}")
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
    else:
        logger.warning("Discord not configured - no webhook URL or bot token")

    # Fallback to local logging
    try:
        log_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "logs", "monitoring"
        )
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        log_path = os.path.join(log_dir, f"daily-summary-{timestamp}.log")
        with open(log_path, "w") as f:
            f.write(message)
        logger.info(f"Summary logged locally to {log_path}")
    except Exception as e:
        logger.error(f"Failed to log locally: {e}")
        print(message)  # Last resort: print to stdout

    return False


def main() -> int:
    """Main function with proper exit codes."""
    logger.info("Starting daily executive summary")

    try:
        r = get_redis()
        if not r:
            logger.error("Cannot connect to Redis")
            error_message = "❌ **Daily Summary Failed**\nRedis connection failed"
            post_summary(error_message)
            return 1

        # Gather metrics with individual error handling
        try:
            pnl = calculate_pnl(r)
        except Exception as e:
            logger.error(f"Failed to calculate PnL: {e}")
            pnl = {
                "pnl": 0.0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_trades": 0,
            }

        try:
            drawdown = get_drawdown(r)
        except Exception as e:
            logger.error(f"Failed to get drawdown: {e}")
            drawdown = 0.0

        try:
            ece = get_ece_drift(r)
        except Exception as e:
            logger.error(f"Failed to get ECE drift: {e}")
            ece = "Unknown"

        try:
            incidents = get_incidents_24h(r)
        except Exception as e:
            logger.error(f"Failed to get incidents: {e}")
            incidents = 0

        message = format_executive_summary(pnl, drawdown, ece, incidents)
        post_summary(message)

        logger.info("Daily executive summary completed")
        return 0

    except Exception as e:
        logger.exception(f"Unexpected error in daily summary: {e}")
        error_message = f"❌ **Daily Summary Failed**\nError: {str(e)}"
        post_summary(error_message)
        return 1


if __name__ == "__main__":
    sys.exit(main())
