#!/usr/bin/env python3
"""6-hour checkpoint gate audit (G1-G8) for ACTIVATION-001.

Posts detailed audit to Discord #development or logs locally.
Designed for cron execution with proper error handling and exit codes.
"""

import os
import sys
import subprocess
import socket
import ssl
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
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


def check_g1_scheduler(r: redis.Redis) -> Dict[str, Any]:
    """G1: Scheduler Continuity

    Validates scheduler is running AND reporting heartbeats.
    Shows UNKNOWN if no heartbeat data (scheduler not configured).
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

        # Check for state file in multiple possible locations
        state_paths = [
            "data/optimization_schedule.json",
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "data",
                "optimization_schedule.json",
            ),
        ]
        state_exists = any(os.path.exists(p) for p in state_paths)

        # Check for heartbeat data in Redis
        heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat") if r else {}
        last_seen = r.get("bmad:chiseai:scheduler:last_seen") if r else None
        has_heartbeat = bool(heartbeat or last_seen)

        # Truthful status reporting
        if not has_heartbeat:
            return {
                "gate": "G1",
                "status": "❓ UNKNOWN",
                "detail": "No heartbeat data - scheduler not configured",
                "recommendation": "Configure scheduler heartbeat reporting",
            }
        elif running and state_exists:
            return {
                "gate": "G1",
                "status": "✅ PASS",
                "detail": f"Process running, state exists, heartbeat: {last_seen or 'present'}",
            }
        elif state_exists:
            return {
                "gate": "G1",
                "status": "⚠️ CHECK",
                "detail": "State exists, process not running",
                "recommendation": "Verify scheduler process status",
            }
        else:
            return {
                "gate": "G1",
                "status": "❌ FAIL",
                "detail": "No process or state but heartbeat exists (inconsistent)",
                "recommendation": "Check for zombie processes or stale heartbeat",
            }
    except subprocess.TimeoutExpired:
        logger.error("G1 check timed out")
        return {"gate": "G1", "status": "❌ FAIL", "detail": "Process check timed out"}
    except FileNotFoundError:
        logger.error("ps command not found for G1 check")
        return {"gate": "G1", "status": "❌ FAIL", "detail": "ps command not available"}
    except Exception as e:
        logger.error(f"G1 check error: {e}")
        return {"gate": "G1", "status": "❌ FAIL", "detail": str(e)[:50]}


def check_g2_signal_cadence(r: redis.Redis) -> Dict[str, Any]:
    """G2: Signal Cadence

    Validates signals exist in Redis.
    Shows UNKNOWN if Redis is empty (not configured), not CHECK.
    """
    try:
        count = len(r.keys("bmad:chiseai:signals:*"))

        if count > 0:
            # Check for recent signals (within last hour)
            recent_signals = 0
            current_time = datetime.now(timezone.utc).timestamp()
            signal_keys = r.keys("bmad:chiseai:signals:*")

            for key in signal_keys[:10]:  # Sample first 10
                try:
                    signal_data = r.hgetall(key)
                    if signal_data:
                        timestamp = signal_data.get("timestamp") or signal_data.get(
                            "created_at"
                        )
                        if timestamp:
                            try:
                                signal_time = float(timestamp)
                                if current_time - signal_time < 3600:  # Within 1 hour
                                    recent_signals += 1
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    pass

            if recent_signals == 0:
                return {
                    "gate": "G2",
                    "status": "⏰ STALE",
                    "detail": f"{count} signals but none recent (may be stale)",
                    "recommendation": "Check signal generation frequency",
                }
            else:
                return {
                    "gate": "G2",
                    "status": "✅ PASS",
                    "detail": f"{count} signals, {recent_signals} recent",
                }
        else:
            # No signals - show UNKNOWN (not CHECK) as this indicates not configured
            return {
                "gate": "G2",
                "status": "❓ UNKNOWN",
                "detail": "No signals in Redis - signal pipeline not configured",
                "recommendation": "Configure signal sources or verify pipeline",
            }
    except redis.RedisError as e:
        logger.error(f"Redis error in G2: {e}")
        return {"gate": "G2", "status": "❌ FAIL", "detail": "Redis error"}
    except Exception as e:
        logger.error(f"G2 check error: {e}")
        return {"gate": "G2", "status": "❌ FAIL", "detail": str(e)[:50]}


def check_g3_data_flow(r: redis.Redis) -> Dict[str, Any]:
    """G3: Data Flow Movement

    Validates outcomes exist in Redis.
    Shows UNKNOWN if no outcomes (not configured), not CHECK.
    """
    try:
        count = r.scard("bmad:chiseai:outcomes:index")

        if count and count > 0:
            # Check for recent outcomes (within last 24 hours)
            recent_outcomes = 0
            current_time = datetime.now(timezone.utc).timestamp()
            outcome_ids = r.smembers("bmad:chiseai:outcomes:index")

            for outcome_id in list(outcome_ids)[:10]:  # Sample first 10
                try:
                    outcome = r.hgetall(f"bmad:chiseai:outcomes:{outcome_id}")
                    if outcome:
                        timestamp = outcome.get("timestamp") or outcome.get(
                            "created_at"
                        )
                        if timestamp:
                            try:
                                outcome_time = float(timestamp)
                                if (
                                    current_time - outcome_time < 86400
                                ):  # Within 24 hours
                                    recent_outcomes += 1
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    pass

            if recent_outcomes == 0:
                return {
                    "gate": "G3",
                    "status": "⏰ STALE",
                    "detail": f"{count} outcomes but none recent (may be stale)",
                    "recommendation": "Check if trading is still active",
                }
            else:
                return {
                    "gate": "G3",
                    "status": "✅ PASS",
                    "detail": f"{count} outcomes, {recent_outcomes} recent",
                }
        else:
            # No outcomes - show UNKNOWN (not CHECK) as this indicates not configured
            return {
                "gate": "G3",
                "status": "❓ UNKNOWN",
                "detail": "No outcomes in Redis - outcome pipeline not configured",
                "recommendation": "Configure outcome tracking or verify trading activity",
            }
    except redis.RedisError as e:
        logger.error(f"Redis error in G3: {e}")
        return {"gate": "G3", "status": "❌ FAIL", "detail": "Redis error"}
    except Exception as e:
        logger.error(f"G3 check error: {e}")
        return {"gate": "G3", "status": "❌ FAIL", "detail": str(e)[:50]}


def check_g4_kill_switch(r: redis.Redis) -> Dict[str, Any]:
    """G4: Kill Switch Active

    Validates kill switch is configured and armed.
    Shows NOT_CONFIGURED when not set, not CHECK.
    """
    try:
        enabled = r.hget("bmad:chiseai:kill_switch", "enabled")
        triggered = r.hget("bmad:chiseai:kill_switch", "triggered")

        # Check if kill switch is actually configured
        is_configured = enabled is not None

        if not is_configured:
            return {
                "gate": "G4",
                "status": "⚙️ NOT_CONFIGURED",
                "detail": "Kill switch not configured in Redis",
                "recommendation": "Configure kill switch before trading - set bmad:chiseai:kill_switch:enabled",
            }
        elif triggered == "1":
            return {
                "gate": "G4",
                "status": "🚨 ALERT",
                "detail": "TRIGGERED - Trading halted",
            }
        elif enabled == "1":
            return {"gate": "G4", "status": "✅ PASS", "detail": "Armed and ready"}
        else:
            return {
                "gate": "G4",
                "status": "⚠️ CHECK",
                "detail": "Kill switch configured but disabled",
                "recommendation": "Enable kill switch for safety",
            }
    except redis.RedisError as e:
        logger.error(f"Redis error in G4: {e}")
        return {"gate": "G4", "status": "❌ FAIL", "detail": "Redis error"}
    except Exception as e:
        logger.error(f"G4 check error: {e}")
        return {"gate": "G4", "status": "❌ FAIL", "detail": str(e)[:50]}


def check_g5_daily_loss(r: redis.Redis) -> Dict[str, Any]:
    """G5: Daily Loss Guard

    Validates daily loss limit is configured.
    Shows NOT_CONFIGURED when not set, not CHECK.
    """
    try:
        max_loss = r.hget("bmad:chiseai:daily_loss_limit", "max_loss_percent")
        current_loss = r.hget("bmad:chiseai:daily_loss_limit", "current_loss")

        if max_loss is None:
            return {
                "gate": "G5",
                "status": "⚙️ NOT_CONFIGURED",
                "detail": "Daily loss limit not configured in Redis",
                "recommendation": "Configure loss limit before trading - set bmad:chiseai:daily_loss_limit:max_loss_percent",
            }

        # Check if current loss is being tracked
        if current_loss is None:
            return {
                "gate": "G5",
                "status": "⚠️ CHECK",
                "detail": f"Limit: {max_loss}% but no current loss data",
                "recommendation": "Verify loss tracking is active",
            }

        # Check if limit is reached
        try:
            current = float(current_loss)
            max_val = float(max_loss)
            if current >= max_val:
                return {
                    "gate": "G5",
                    "status": "🚨 ALERT",
                    "detail": f"Daily loss limit reached: ${current:.2f} / {max_val}%",
                    "recommendation": "URGENT: Consider halting trading",
                }
        except (ValueError, TypeError):
            pass

        return {
            "gate": "G5",
            "status": "✅ PASS",
            "detail": f"Limit: {max_loss}%, Current: ${current_loss}",
        }
    except redis.RedisError as e:
        logger.error(f"Redis error in G5: {e}")
        return {"gate": "G5", "status": "❌ FAIL", "detail": "Redis error"}
    except Exception as e:
        logger.error(f"G5 check error: {e}")
        return {"gate": "G5", "status": "❌ FAIL", "detail": str(e)[:50]}


def check_g6_bybit_connectivity() -> Dict[str, Any]:
    """G6: Bybit Connectivity"""
    try:
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
    except socket.timeout:
        logger.error("G6 check timed out")
        return {"gate": "G6", "status": "❌ FAIL", "detail": "Connection timeout"}
    except socket.gaierror as e:
        logger.error(f"G6 DNS error: {e}")
        return {"gate": "G6", "status": "❌ FAIL", "detail": "DNS resolution failed"}
    except Exception as e:
        logger.error(f"G6 check error: {e}")
        return {"gate": "G6", "status": "❌ FAIL", "detail": str(e)[:50]}


def check_g7_observability(r: redis.Redis) -> Dict[str, Any]:
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
    except redis.RedisError as e:
        logger.error(f"Redis error in G7: {e}")
        return {"gate": "G7", "status": "❌ FAIL", "detail": "Redis error"}
    except Exception as e:
        logger.error(f"G7 check error: {e}")
        return {"gate": "G7", "status": "❌ FAIL", "detail": str(e)[:50]}


def check_g8_pipeline(r: redis.Redis) -> Dict[str, Any]:
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
    except redis.RedisError as e:
        logger.error(f"Redis error in G8: {e}")
        return {"gate": "G8", "status": "❌ FAIL", "detail": "Redis error"}
    except Exception as e:
        logger.error(f"G8 check error: {e}")
        return {"gate": "G8", "status": "❌ FAIL", "detail": str(e)[:50]}


def run_all_checks() -> List[Dict[str, Any]]:
    """Run all G1-G8 checks."""
    r = get_redis()
    if not r:
        return [{"gate": "ALL", "status": "❌ FAIL", "detail": "Redis unavailable"}]

    checks = []

    # Run each check with individual error handling
    check_functions = [
        lambda: check_g1_scheduler(r),
        lambda: check_g2_signal_cadence(r),
        lambda: check_g3_data_flow(r),
        lambda: check_g4_kill_switch(r),
        lambda: check_g5_daily_loss(r),
        check_g6_bybit_connectivity,
        lambda: check_g7_observability(r),
        lambda: check_g8_pipeline(r),
    ]

    for check_fn in check_functions:
        try:
            checks.append(check_fn())
        except Exception as e:
            logger.error(f"Unexpected error in check: {e}")
            checks.append({"gate": "ERR", "status": "❌ FAIL", "detail": str(e)[:50]})

    return checks


def format_checkpoint_message(checks: List[Dict]) -> str:
    """Format checkpoint message."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Count all status types including new ones
    pass_count = sum(1 for c in checks if "PASS" in c["status"])
    fail_count = sum(1 for c in checks if "FAIL" in c["status"])
    check_count = sum(1 for c in checks if "CHECK" in c["status"])
    unknown_count = sum(1 for c in checks if "UNKNOWN" in c["status"])
    not_configured_count = sum(1 for c in checks if "NOT_CONFIGURED" in c["status"])
    stale_count = sum(1 for c in checks if "STALE" in c["status"])
    alert_count = sum(1 for c in checks if "ALERT" in c["status"])

    # Build status line with all relevant statuses
    status_parts = [f"{pass_count} ✅"]
    if check_count:
        status_parts.append(f"{check_count} ⚠️")
    if unknown_count:
        status_parts.append(f"{unknown_count} ❓")
    if not_configured_count:
        status_parts.append(f"{not_configured_count} ⚙️")
    if stale_count:
        status_parts.append(f"{stale_count} ⏰")
    if alert_count:
        status_parts.append(f"{alert_count} 🚨")
    if fail_count:
        status_parts.append(f"{fail_count} ❌")

    lines = [
        f"**📊 Burn-in Checkpoint (6h)** | {timestamp}",
        f"",
        f"**Gate Status:** {' | '.join(status_parts)}",
        f"",
    ]

    for check in checks:
        lines.append(f"**{check['gate']}:** {check['status']} - {check['detail']}")
        # Include recommendation if present
        if "recommendation" in check:
            lines.append(f"   💡 {check['recommendation']}")

    lines.extend([f"", f"_Next checkpoint in 6 hours_"])

    return "\n".join(lines)


def post_discord(message: str) -> bool:
    """Post to Discord via webhook or bot API."""
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
                    "User-Agent": "ChiseAI-Checkpoint/1.0",
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
                    "User-Agent": "ChiseAI-Checkpoint/1.0",
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
            logger.error(f"Discord bot error: {e}")
    else:
        logger.warning("Discord not configured")

    return False


def log_local(message: str) -> str:
    """Log locally."""
    try:
        log_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "logs", "monitoring"
        )
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = os.path.join(log_dir, f"checkpoint-{timestamp}.log")

        with open(path, "w") as f:
            f.write(message)

        return path
    except Exception as e:
        logger.error(f"Failed to log locally: {e}")
        print(message)  # Last resort
        return "stdout"


def main() -> int:
    """Main checkpoint audit with proper exit codes."""
    logger.info("Starting 6-hour checkpoint audit")

    try:
        checks = run_all_checks()
        message = format_checkpoint_message(checks)

        # Try Discord, fallback to local
        if not post_discord(message):
            path = log_local(message)
            logger.info(f"Discord unavailable - logged to {path}")
        else:
            logger.info("Discord post successful")

        # Return non-zero if any FAIL
        if any("FAIL" in c["status"] for c in checks):
            logger.warning("Checkpoint audit completed with failures")
            return 1

        logger.info("Checkpoint audit completed successfully")
        return 0

    except Exception as e:
        logger.exception(f"Unexpected error in checkpoint audit: {e}")
        error_message = f"❌ **Checkpoint Audit Failed**\nUnexpected error: {str(e)}"
        log_local(error_message)
        return 1


if __name__ == "__main__":
    sys.exit(main())
