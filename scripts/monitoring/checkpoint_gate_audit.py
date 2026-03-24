#!/usr/bin/env python3
"""6-hour checkpoint gate audit (G1-G12) for ACTIVATION-001.

Posts detailed audit to Discord #development or logs locally.
"""

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

import redis

# Load .env file for cron environment
env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
)
if os.path.exists(env_path):
    with open(env_path) as f:
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


def get_redis() -> Any | None:
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.error(f"Redis error: {e}")
        return None


def check_g1_scheduler(r: Any) -> dict[str, Any]:
    """G1: Scheduler Continuity - Check Redis heartbeat"""
    from datetime import datetime

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
        now = datetime.now(UTC)
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


def check_g2_signal_cadence(r: Any) -> dict[str, Any]:
    """G2: Signal Cadence - Check for active signal generation.

    Paper-aware: checks both bmad:chiseai:signals:* and paper:signal:* keys.
    Returns detail in format: "PAPER:X LIVE:Y signals, Z actionable..."
    """
    try:
        # Count live signals (bmad:chiseai:signals:*)
        live_signals = len(r.keys("bmad:chiseai:signals:*"))

        # Count paper signals (paper:signal:*)
        paper_signals = len(r.keys("paper:signal:*"))

        # Get scheduler heartbeat for actionable count
        heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")
        actionable_15m = int(heartbeat.get("actionable_15m", "0"))
        backlog = int(heartbeat.get("consumer_backlog", "0"))
        pipeline_status = heartbeat.get("pipeline_status", "unknown")

        # Total signals for decision logic
        total_signals = live_signals + paper_signals

        # Backlog threshold for bottleneck detection
        backlog_threshold = int(os.getenv("G2_BACKLOG_THRESHOLD", "10"))

        # G2 Message Taxonomy implementation
        # State 1: NO_SIGNALS - No signals generated in window
        if total_signals == 0:
            if pipeline_status == "stale":
                return {
                    "gate": "G2",
                    "status": "❌ FAIL",
                    "detail": f"NO_SIGNALS: PAPER:{paper_signals} LIVE:{live_signals} signals in 15m window (pipeline stale)",
                }
            return {
                "gate": "G2",
                "status": "✅ PASS",
                "detail": f"NO_SIGNALS: PAPER:{paper_signals} LIVE:{live_signals} signals in 15m window (healthy idle)",
            }

        # State 2: FILTERED - Signals generated but none actionable
        if total_signals > 0 and actionable_15m == 0:
            return {
                "gate": "G2",
                "status": "✅ PASS",
                "detail": f"FILTERED: PAPER:{paper_signals} LIVE:{live_signals} signals, 0 actionable (filters active)",
            }

        # State 3: BOTTLENECK - Actionable signals present but downstream stalled
        if actionable_15m > 0 and backlog > backlog_threshold:
            return {
                "gate": "G2",
                "status": "⚠️ CHECK",
                "detail": f"BOTTLENECK: PAPER:{paper_signals} LIVE:{live_signals} signals, {actionable_15m} actionable, {backlog} backlog (downstream stalled)",
            }

        # State 4: HEALTHY - Normal operation
        return {
            "gate": "G2",
            "status": "✅ PASS",
            "detail": f"HEALTHY: PAPER:{paper_signals} LIVE:{live_signals} signals, {actionable_15m} actionable, backlog {backlog} (normal)",
        }

    except Exception as e:
        return {"gate": "G2", "status": "❌ FAIL", "detail": str(e)}


def check_g3_data_flow(r: Any) -> dict[str, Any]:
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


def check_g4_kill_switch(r: Any) -> dict[str, Any]:
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


def check_g5_cron_cadence(r: Any) -> dict[str, Any]:
    """G5: Cron Job Cadence Evidence

    Verifies that all cron jobs are executing on their expected cadence:
    - pager (5m = 300s)
    - signal-growth (30m = 1800s)
    - hourly-health (60m = 3600s)
    - checkpoint-audit (6h = 21600s)

    Reports PASS if all jobs executed within expected interval + 20% grace.
    Reports FAIL if any job missed more than 2 consecutive expected runs.
    """
    try:
        # Import cron evidence checker
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from cron_evidence import check_cron_cadence

        results = check_cron_cadence(r)

        if "error" in results:
            return {
                "gate": "G5",
                "status": "❌ FAIL",
                "detail": f"Cron cadence check failed: {results['error']}",
            }

        overall = results.get("overall_status", "UNKNOWN")
        jobs = results.get("jobs", {})

        # Build detail string
        job_details = []
        for job_name, job_data in jobs.items():
            status = job_data.get("status", "UNKNOWN")
            elapsed = job_data.get("elapsed_seconds")
            missed = job_data.get("missed_count", 0)

            if elapsed is not None:
                if elapsed < 60:
                    time_str = f"{elapsed}s"
                elif elapsed < 3600:
                    time_str = f"{elapsed // 60}m"
                else:
                    time_str = f"{elapsed // 3600}h"

                if missed > 0:
                    job_details.append(
                        f"{job_name}:{status}({time_str},missed={missed})"
                    )
                else:
                    job_details.append(f"{job_name}:{status}({time_str})")
            else:
                job_details.append(f"{job_name}:{status}(no data)")

        detail = " | ".join(job_details) if job_details else "No cron data available"

        # Map overall status to gate status
        if overall == "PASS":
            return {"gate": "G5", "status": "✅ PASS", "detail": detail}
        elif overall == "CHECK":
            return {"gate": "G5", "status": "⚠️ CHECK", "detail": detail}
        else:  # FAIL or UNKNOWN
            return {"gate": "G5", "status": "❌ FAIL", "detail": detail}

    except Exception as e:
        return {
            "gate": "G5",
            "status": "❌ FAIL",
            "detail": f"Error checking cron cadence: {str(e)[:100]}",
        }


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


def check_g7_observability(r: Any) -> dict[str, Any]:
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
                "detail": "Redis OK but uptime <1h",
            }
        else:
            return {"gate": "G7", "status": "❌ FAIL", "detail": "Redis ping failed"}
    except Exception as e:
        return {"gate": "G7", "status": "❌ FAIL", "detail": str(e)}


def check_g8_pipeline(r: Any) -> dict[str, Any]:
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


def check_g12_bybit_freshness(r: Any) -> dict[str, Any]:
    """G12: Bybit Truth Freshness - Check if Bybit truth data is fresh.

    Validates that Bybit truth data collection is recent by checking:
    - bmad:chiseai:bybit_truth:last_collection_timestamp (ISO format timestamp)
    - bmad:chiseai:bybit_truth:last_collection_status (optional context)

    Freshness threshold: 60 minutes (3600 seconds)
    """
    from datetime import datetime

    try:
        # Get the last collection timestamp
        timestamp_str = r.get("bmad:chiseai:bybit_truth:last_collection_timestamp")
        status = r.get("bmad:chiseai:bybit_truth:last_collection_status")

        if not timestamp_str:
            return {
                "gate": "G12",
                "status": "⚠️ CHECK",
                "detail": "no collection data",
            }

        # Parse ISO timestamp
        try:
            last_collection = datetime.fromisoformat(timestamp_str)
        except ValueError:
            return {
                "gate": "G12",
                "status": "⚠️ CHECK",
                "detail": f"unparseable timestamp: {timestamp_str[:50]}",
            }

        # Calculate age in minutes
        now = datetime.now(UTC)
        age_seconds = (now - last_collection).total_seconds()
        age_minutes = age_seconds / 60

        # Freshness threshold: 60 minutes
        max_age_minutes = 60

        # Build detail string
        detail_parts = [f"last_collection={age_minutes:.0f}m ago"]
        if status:
            detail_parts.append(f"status={status}")

        detail = " | ".join(detail_parts)

        if age_minutes > max_age_minutes:
            return {
                "gate": "G12",
                "status": "❌ FAIL",
                "detail": detail,
            }
        else:
            return {
                "gate": "G12",
                "status": "✅ PASS",
                "detail": detail,
            }

    except Exception as e:
        return {"gate": "G12", "status": "❌ FAIL", "detail": str(e)[:100]}


def check_g11_provenance() -> dict[str, Any]:
    """G11: Provenance - Check signal_outcomes table for missing provenance fields.

    Validates that execution_venue, execution_mode, and execution_source fields
    are populated for all records in the last 60 minutes.

    Returns:
        dict with gate, status, and detail:
        - PASS: No data in window OR all records have all provenance fields
        - FAIL: Any records missing provenance fields
        - CHECK: Connection error or query failure
    """
    import os

    # Database connection parameters
    db_host = os.getenv("DB_HOST", "host.docker.internal")
    db_port = os.getenv("DB_PORT", "5434")
    db_name = os.getenv("DB_NAME", "chiseai")
    db_user = os.getenv("DB_USER", "chiseai")
    db_password = os.getenv("DB_PASSWORD", "chiseai")

    try:
        # Try psycopg2 first, fallback to asyncpg if available
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                connect_timeout=5,
            )
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(execution_venue) as with_venue,
                    COUNT(execution_mode) as with_mode,
                    COUNT(execution_source) as with_source
                FROM signal_outcomes
                WHERE created_at >= NOW() - INTERVAL '60 minutes'
            """)
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            total, with_venue, with_mode, with_source = row

        except ImportError:
            # Fallback to asyncpg if psycopg2 not available
            try:
                import asyncio

                import asyncpg

                async def query():
                    conn = await asyncpg.connect(
                        host=db_host,
                        port=db_port,
                        database=db_name,
                        user=db_user,
                        password=db_password,
                        timeout=5,
                    )
                    row = await conn.fetchrow("""
                        SELECT
                            COUNT(*) as total,
                            COUNT(execution_venue) as with_venue,
                            COUNT(execution_mode) as with_mode,
                            COUNT(execution_source) as with_source
                        FROM signal_outcomes
                        WHERE created_at >= NOW() - INTERVAL '60 minutes'
                    """)
                    await conn.close()
                    return row

                row = asyncio.run(query())
                total = row["total"]
                with_venue = row["with_venue"]
                with_mode = row["with_mode"]
                with_source = row["with_source"]

            except ImportError:
                return {
                    "gate": "G11",
                    "status": "⚠️ CHECK",
                    "detail": "No PostgreSQL driver available (psycopg2 or asyncpg required)",
                }

        # Calculate missing counts
        missing_venue = total - with_venue
        missing_mode = total - with_mode
        missing_source = total - with_source

        # Build detail string
        detail = f"total={total} venue={with_venue} mode={with_mode} source={with_source} missing_venue={missing_venue} missing_mode={missing_mode} missing_source={missing_source}"

        # Determine status
        if total == 0:
            # No data in window - PASS (no provenance to check)
            return {
                "gate": "G11",
                "status": "✅ PASS",
                "detail": f"{detail} | No data in 60m window",
            }
        elif missing_venue == 0 and missing_mode == 0 and missing_source == 0:
            # All records have all provenance fields
            return {
                "gate": "G11",
                "status": "✅ PASS",
                "detail": f"{detail} | All records have provenance",
            }
        else:
            # Some records missing provenance fields
            missing_fields = []
            if missing_venue > 0:
                missing_fields.append(f"venue({missing_venue})")
            if missing_mode > 0:
                missing_fields.append(f"mode({missing_mode})")
            if missing_source > 0:
                missing_fields.append(f"source({missing_source})")
            return {
                "gate": "G11",
                "status": "❌ FAIL",
                "detail": f"{detail} | Missing: {', '.join(missing_fields)}",
            }

    except Exception as e:
        logger.error(f"Error checking G11: {e}")
        return {
            "gate": "G11",
            "status": "⚠️ CHECK",
            "detail": f"Connection/query error: {str(e)[:100]}",
        }


def check_g10_chain_integrity(r: Any) -> dict[str, Any]:
    """G10: Chain Integrity - Count signals -> orders -> fills -> outcomes in last 6h.

    Validates the complete pipeline chain by counting entities in the last 6 hours:
    - Signals (bmad:chiseai:signals:* and paper:signal:*)
    - Orders (paper:order:* keys with timestamp >= now-6h)
    - Fills (paper:fill:* keys with timestamp >= now-6h)
    - Outcomes (bmad:chiseai:outcomes:index members with timestamp >= now-6h)

    Status logic:
    - PASS: signals > 0 AND orders > 0 AND fills > 0 AND outcomes > 0
    - CHECK: signals = 0 (no activity in window)
    - FAIL: signals > 0 but any downstream stage = 0 (pipeline broken)
    """
    from datetime import UTC, datetime

    try:
        # Calculate 6-hour window threshold
        now = datetime.now(UTC)
        six_hours_ago = now.timestamp() - 21600  # 6 hours in seconds

        # Count signals in last 6h (both bmad and paper signal keys)
        signal_keys = r.keys("bmad:chiseai:signals:*") + r.keys("paper:signal:*")
        signal_count = len(signal_keys)

        # Count orders in last 6h (paper:order:* keys with timestamp >= now-6h)
        order_keys = r.keys("paper:order:*")
        order_count = 0
        for key in order_keys:
            try:
                # Extract timestamp from key (format: paper:order:<timestamp>:<id>)
                parts = key.split(":")
                if len(parts) >= 3:
                    ts = float(parts[2])
                    if ts >= six_hours_ago:
                        order_count += 1
            except (ValueError, IndexError):
                continue

        # Count fills in last 6h (paper:fill:* keys with timestamp >= now-6h)
        fill_keys = r.keys("paper:fill:*")
        fill_count = 0
        for key in fill_keys:
            try:
                # Extract timestamp from key (format: paper:fill:<timestamp>:<id>)
                parts = key.split(":")
                if len(parts) >= 3:
                    ts = float(parts[2])
                    if ts >= six_hours_ago:
                        fill_count += 1
            except (ValueError, IndexError):
                continue

        # Count outcomes in last 6h (bmad:chiseai:outcomes:index members)
        outcome_ids = r.smembers("bmad:chiseai:outcomes:index")
        outcome_count = 0
        for outcome_id in outcome_ids:
            try:
                # Try to get the outcome hash for timestamp
                outcome_data = r.hgetall(f"bmad:chiseai:outcome:{outcome_id}")
                if outcome_data:
                    ts_str = outcome_data.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str).timestamp()
                        if ts >= six_hours_ago:
                            outcome_count += 1
                    else:
                        # If no timestamp in hash, check if outcome_id contains timestamp
                        parts = outcome_id.split(":")
                        for part in parts:
                            try:
                                ts = float(part)
                                if ts >= six_hours_ago:
                                    outcome_count += 1
                                    break
                            except ValueError:
                                continue
            except Exception:
                continue

        # Build detail string
        detail = f"signals={signal_count} orders={order_count} fills={fill_count} outcomes={outcome_count}"

        # Determine status based on chain integrity
        if signal_count == 0:
            # No signals = no activity in window (CHECK status)
            return {
                "gate": "G10",
                "status": "⚠️ CHECK",
                "detail": f"{detail} | No activity in 6h window",
            }
        elif (
            signal_count > 0
            and order_count > 0
            and fill_count > 0
            and outcome_count > 0
        ):
            # Complete chain - all stages have activity
            return {
                "gate": "G10",
                "status": "✅ PASS",
                "detail": f"{detail} | Chain intact",
            }
        else:
            # Pipeline broken - signals exist but downstream stage is empty
            missing = []
            if order_count == 0:
                missing.append("orders")
            if fill_count == 0:
                missing.append("fills")
            if outcome_count == 0:
                missing.append("outcomes")
            return {
                "gate": "G10",
                "status": "❌ FAIL",
                "detail": f"{detail} | Pipeline broken: no {'/'.join(missing)}",
            }

    except Exception as e:
        return {"gate": "G10", "status": "❌ FAIL", "detail": str(e)}


def run_all_checks():
    """Run all G1-G12 checks."""
    r = get_redis()
    if not r:
        return [{"gate": "ALL", "status": "❌ FAIL", "detail": "Redis unavailable"}]

    checks = [
        check_g1_scheduler(r),
        check_g2_signal_cadence(r),
        check_g3_data_flow(r),
        check_g4_kill_switch(r),
        check_g5_cron_cadence(r),
        check_g6_bybit_connectivity(),
        check_g7_observability(r),
        check_g8_pipeline(r),
        check_g10_chain_integrity(r),
        check_g11_provenance(),
        check_g12_bybit_freshness(r),
    ]

    return checks


def format_checkpoint_message(checks: list[dict]):
    """Format checkpoint message."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    pass_count = sum(1 for c in checks if "PASS" in c["status"])
    fail_count = sum(1 for c in checks if "FAIL" in c["status"])
    check_count = sum(1 for c in checks if "CHECK" in c["status"])

    lines = [
        f"**📊 Burn-in Checkpoint (6h)** | {timestamp}",
        "",
        f"**Gate Status:** {pass_count} ✅ | {check_count} ⚠️ | {fail_count} ❌",
        "",
    ]

    for check in checks:
        lines.append(f"**{check['gate']}:** {check['status']} - {check['detail']}")

    lines.extend(["", "_Next checkpoint in 6 hours_"])

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
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
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

    # Write cron evidence
    try:
        from cron_evidence import write_cron_evidence

        has_fail = any("FAIL" in c["status"] for c in checks)
        status = "error" if has_fail else "success"
        error_msg = None
        if has_fail:
            failed_gates = [c["gate"] for c in checks if "FAIL" in c["status"]]
            error_msg = f"Gates failed: {', '.join(failed_gates)}"
        write_cron_evidence("checkpoint-audit", status=status, error_message=error_msg)
    except Exception as e:
        logger.warning(f"Failed to write cron evidence: {e}")

    # Return non-zero if any FAIL
    if any("FAIL" in c["status"] for c in checks):
        return 1
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
