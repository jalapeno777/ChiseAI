#!/usr/bin/env python3
"""6-hour checkpoint gate audit (G1-G8) for ACTIVATION-001.

Posts detailed audit to Discord #development or logs locally.

P0 HARDENING ENHANCEMENTS:
- 6h execution tracking in Redis
- Missed checkpoint detection and auto-trigger
- G1-G8 gate tracking over time with trend analysis
- Gate improvement/degradation trend detection
"""

import os
import sys
import asyncio
import subprocess
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
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

# P0 HARDENING: Redis keys for checkpoint tracking
CHECKPOINT_TRACKING_KEY = "bmad:chiseai:monitoring:checkpoint:last_run"
CHECKPOINT_LOG_KEY = "bmad:chiseai:monitoring:checkpoint:log"
GATE_HISTORY_KEY = "bmad:chiseai:monitoring:checkpoint:gate_history"
MISSED_CHECKPOINT_KEY = "bmad:chiseai:monitoring:checkpoint:missed_count"
AUTO_TRIGGER_KEY = "bmad:chiseai:monitoring:checkpoint:auto_trigger_count"

# P0 HARDENING: Configuration
MAX_CHECKPOINT_GAP_HOURS = 6.5  # Auto-trigger if >6.5h since last checkpoint
MAX_LOG_ENTRIES = 50  # Keep last 50 checkpoint logs
GATE_HISTORY_ENTRIES = 10  # Keep last 10 gate results for trend analysis


def get_redis():
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def record_checkpoint_start(r: redis.Redis) -> None:
    """P0 HARDENING: Record checkpoint start timestamp."""
    try:
        now = datetime.now(timezone.utc)
        r.hset(
            CHECKPOINT_TRACKING_KEY,
            mapping={"last_run_start": now.isoformat(), "status": "running"},
        )
        logger.info(f"Recorded checkpoint start: {now.isoformat()}")
    except Exception as e:
        logger.error(f"Failed to record checkpoint start: {e}")


def record_checkpoint_complete(
    r: redis.Redis, success: bool, gate_results: List[Dict], details: str = ""
) -> None:
    """P0 HARDENING: Record checkpoint completion with gate results."""
    try:
        now = datetime.now(timezone.utc)

        # Update tracking hash
        r.hset(
            CHECKPOINT_TRACKING_KEY,
            mapping={
                "last_run_complete": now.isoformat(),
                "last_run_success": "1" if success else "0",
                "status": "complete" if success else "failed",
                "details": details[:500],
            },
        )

        # Add to checkpoint log
        log_entry = {
            "timestamp": now.isoformat(),
            "success": success,
            "pass_count": sum(1 for g in gate_results if "PASS" in g.get("status", "")),
            "fail_count": sum(1 for g in gate_results if "FAIL" in g.get("status", "")),
            "check_count": sum(
                1 for g in gate_results if "CHECK" in g.get("status", "")
            ),
        }
        r.lpush(CHECKPOINT_LOG_KEY, json.dumps(log_entry))
        r.ltrim(CHECKPOINT_LOG_KEY, 0, MAX_LOG_ENTRIES - 1)

        # Store gate history for trend analysis
        gate_summary = {
            "timestamp": now.isoformat(),
            "gates": {g["gate"]: g["status"] for g in gate_results},
        }
        r.lpush(GATE_HISTORY_KEY, json.dumps(gate_summary))
        r.ltrim(GATE_HISTORY_KEY, 0, GATE_HISTORY_ENTRIES - 1)

        logger.info(f"Recorded checkpoint completion: success={success}")
    except Exception as e:
        logger.error(f"Failed to record checkpoint completion: {e}")


def check_missed_checkpoint(r: redis.Redis) -> tuple[bool, Optional[str]]:
    """P0 HARDENING: Check if previous checkpoint was missed and auto-trigger.

    Returns:
        (should_run, reason): Tuple indicating if immediate execution should occur
    """
    try:
        tracking = r.hgetall(CHECKPOINT_TRACKING_KEY)

        if not tracking or "last_run_complete" not in tracking:
            logger.info("No previous checkpoint found - this may be first run")
            return False, None

        last_run_str = tracking.get("last_run_complete", "")
        last_run = datetime.fromisoformat(last_run_str)
        now = datetime.now(timezone.utc)
        elapsed_hours = (now - last_run).total_seconds() / 3600

        logger.info(f"Last checkpoint was {elapsed_hours:.1f} hours ago")

        if elapsed_hours > MAX_CHECKPOINT_GAP_HOURS:
            # Missed checkpoint detected
            r.hincrby(MISSED_CHECKPOINT_KEY, "count", 1)
            r.hset(MISSED_CHECKPOINT_KEY, "last_detected", now.isoformat())
            r.hset(MISSED_CHECKPOINT_KEY, "gap_hours", str(round(elapsed_hours, 2)))

            reason = f"Missed checkpoint detected: {elapsed_hours:.1f} hours since last run (threshold: {MAX_CHECKPOINT_GAP_HOURS}h)"
            logger.warning(reason)

            # Increment auto-trigger counter
            r.hincrby(AUTO_TRIGGER_KEY, "count", 1)
            r.hset(AUTO_TRIGGER_KEY, "last_triggered", now.isoformat())

            return True, reason

        return False, None

    except Exception as e:
        logger.error(f"Error checking missed checkpoint: {e}")
        return False, None


def analyze_gate_trends(r: redis.Redis) -> Dict[str, Any]:
    """P0 HARDENING: Analyze G1-G8 gate trends over time.

    Returns trend analysis showing which gates are improving or degrading.
    """
    try:
        history_entries = r.lrange(GATE_HISTORY_KEY, 0, -1)

        if len(history_entries) < 2:
            return {
                "status": "insufficient_data",
                "message": "Need more history for trend analysis",
            }

        # Parse history
        history = []
        for entry in history_entries:
            try:
                history.append(json.loads(entry))
            except:
                continue

        if len(history) < 2:
            return {"status": "insufficient_data", "message": "Need more valid history"}

        # Analyze trends for each gate
        gate_trends = {}
        gates = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]

        for gate in gates:
            statuses = []
            for h in history:
                gate_status = h.get("gates", {}).get(gate, "")
                statuses.append(gate_status)

            if len(statuses) >= 2:
                # Calculate trend
                recent = statuses[:3]  # Last 3
                older = statuses[-3:] if len(statuses) >= 3 else statuses  # Oldest 3

                recent_pass = sum(1 for s in recent if "PASS" in s)
                older_pass = sum(1 for s in older if "PASS" in s)

                if recent_pass > older_pass:
                    trend = "improving"
                elif recent_pass < older_pass:
                    trend = "degrading"
                else:
                    trend = "stable"

                gate_trends[gate] = {
                    "trend": trend,
                    "recent_pass_rate": f"{recent_pass}/{len(recent)}",
                    "total_checks": len(statuses),
                    "latest": statuses[0] if statuses else "unknown",
                }

        # Overall assessment
        improving = sum(
            1 for g in gate_trends.values() if g.get("trend") == "improving"
        )
        degrading = sum(
            1 for g in gate_trends.values() if g.get("trend") == "degrading"
        )
        stable = sum(1 for g in gate_trends.values() if g.get("trend") == "stable")

        return {
            "status": "analyzed",
            "gate_trends": gate_trends,
            "summary": {
                "improving": improving,
                "degrading": degrading,
                "stable": stable,
                "total_gates": len(gates),
            },
        }

    except Exception as e:
        logger.error(f"Error analyzing gate trends: {e}")
        return {"status": "error", "message": str(e)}


def get_checkpoint_stats(r: redis.Redis) -> Dict[str, Any]:
    """P0 HARDENING: Get checkpoint statistics for reporting."""
    try:
        tracking = r.hgetall(CHECKPOINT_TRACKING_KEY) or {}
        missed = r.hgetall(MISSED_CHECKPOINT_KEY) or {}
        auto_trigger = r.hgetall(AUTO_TRIGGER_KEY) or {}

        stats: Dict[str, Any] = {
            "last_run_complete": tracking.get("last_run_complete", "N/A"),
            "last_run_success": tracking.get("last_run_success", "unknown"),
            "missed_count": int(missed.get("count", 0)),
            "auto_trigger_count": int(auto_trigger.get("count", 0)),
        }

        # Calculate time since last checkpoint
        if tracking.get("last_run_complete"):
            try:
                last_run = datetime.fromisoformat(tracking["last_run_complete"])
                now = datetime.now(timezone.utc)
                elapsed = (now - last_run).total_seconds() / 3600
                stats["hours_since_last_checkpoint"] = f"{elapsed:.1f}"
            except:
                stats["hours_since_last_checkpoint"] = "unknown"

        return stats
    except Exception as e:
        logger.error(f"Error getting checkpoint stats: {e}")
        return {}


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


def format_checkpoint_message(
    checks: List[Dict],
    trend_analysis: Optional[Dict[str, Any]] = None,
    stats: Optional[Dict[str, Any]] = None,
):
    """Format checkpoint message with P0 HARDENING enhancements."""
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

    # P0 HARDENING: Add trend analysis if available
    if trend_analysis and trend_analysis.get("status") == "analyzed":
        lines.append("")
        lines.append("**📈 Gate Trends:**")
        summary = trend_analysis.get("summary", {})
        lines.append(
            f"Improving: {summary.get('improving', 0)} | Degrading: {summary.get('degrading', 0)} | Stable: {summary.get('stable', 0)}"
        )

        # Show degrading gates
        degrading_gates = [
            g
            for g, d in trend_analysis.get("gate_trends", {}).items()
            if d.get("trend") == "degrading"
        ]
        if degrading_gates:
            lines.append(f"⚠️ **Degrading:** {', '.join(degrading_gates)}")

    # P0 HARDENING: Add checkpoint stats
    if stats:
        lines.append("")
        lines.append("**📊 Checkpoint Stats:**")
        if stats.get("missed_count", 0) > 0:
            lines.append(f"⚠️ Missed checkpoints: {stats['missed_count']}")
        if stats.get("auto_trigger_count", 0) > 0:
            lines.append(f"🔄 Auto-triggers: {stats['auto_trigger_count']}")
        if stats.get("hours_since_last_checkpoint"):
            lines.append(f"⏱️ Hours since last: {stats['hours_since_last_checkpoint']}h")

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
    """Main checkpoint audit with P0 HARDENING."""
    logger.info("=" * 60)
    logger.info("Starting 6-hour checkpoint audit (P0 HARDENED)")
    logger.info("=" * 60)

    # P0 HARDENING: Record checkpoint start
    r = get_redis()
    if r:
        record_checkpoint_start(r)

        # P0 HARDENING: Check for missed checkpoint and auto-trigger
        should_run_immediately, missed_reason = check_missed_checkpoint(r)
        if should_run_immediately:
            logger.warning(f"AUTO-TRIGGER: {missed_reason}")
    else:
        logger.error("Redis connection failed - cannot track checkpoint")

    checks = run_all_checks()

    # P0 HARDENING: Get trend analysis and stats
    trend_analysis = {}
    stats = {}
    if r:
        trend_analysis = analyze_gate_trends(r)
        stats = get_checkpoint_stats(r)

    message = format_checkpoint_message(checks, trend_analysis, stats)

    # Try Discord, fallback to local
    discord_ok = await post_discord(message)
    if not discord_ok:
        path = log_local(message)
        print(f"Discord unavailable - logged to {path}")
        details = f"Discord failed, logged to {path}"
    else:
        print("Discord post successful")
        details = "Discord OK"

    # P0 HARDENING: Record checkpoint completion
    if r:
        success = not any("FAIL" in c["status"] for c in checks)
        record_checkpoint_complete(r, success, checks, details)

    # Return non-zero if any FAIL
    if any("FAIL" in c["status"] for c in checks):
        return 1
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
