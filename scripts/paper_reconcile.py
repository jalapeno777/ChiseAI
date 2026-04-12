#!/usr/bin/env python3
"""
Paper Canary Reconciliation Check

Compares Redis index counts to Postgres outcome count and detects orphaned fills.
Monitors data integrity between operational (Redis) and durable (Postgres) stores.

Usage:
    python3 scripts/paper_reconcile.py [--since ISO_TIMESTAMP] [--json] [--alert]

Exit codes:
    0 - All systems consistent
    1 - Divergence detected
    2 - Error
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import asyncpg
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REDIS_HOST = "host.docker.internal"
REDIS_PORT = 6380

PG_DEFAULTS = {
    "host": "host.docker.internal",
    "port": 5434,
    "user": "chiseai",
    "password": "change-me",
    "database": "chiseai",
}

REDIS_INDEXES = {
    "orders": "paper:index:orders",
    "fills": "paper:index:fills",
    "outcomes": "paper:index:outcomes",
}


@dataclass
class ReconcileResult:
    redis_counts: dict
    postgres_count: int
    since: str
    orphaned_fills: list  # Redis fills without matching orders (reported, not blocking)
    divergence: dict
    status: str  # 'clean' | 'divergence'
    exit_code: int
    # Postgres-level orphaned fill tracking (PAPER-RECON-ORPHANED-POLICY)
    pg_orphaned_fills: int = 0  # fills with NULL signal_id (expected in paper mode)
    pg_missing_signal_fills: int = (
        0  # fills that SHOULD have signals but don't (anomaly)
    )


def get_redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


async def get_postgres_count(since: datetime) -> int:
    conn = await asyncpg.connect(
        host=PG_DEFAULTS["host"],
        port=PG_DEFAULTS["port"],
        user=PG_DEFAULTS["user"],
        password=PG_DEFAULTS["password"],
        database=PG_DEFAULTS["database"],
    )
    try:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM signal_outcomes WHERE created_at >= $1", since
        )
        return row["cnt"]
    finally:
        await conn.close()


async def get_postgres_orphaned_fill_counts(since: datetime) -> tuple[int, int]:
    """Get orphaned fill counts from Postgres.

    Returns:
        Tuple of (orphaned_fills, missing_signal_fills)
        - orphaned_fills: fills with signal_id IS NULL (expected in paper mode)
        - missing_signal_fills: fills with signal_id NOT NULL but signal doesn't exist (anomaly)

    Note: missing_signal_fills requires a signals table to check existence.
    If signals table doesn't exist, we can only count orphaned fills.
    """
    conn = await asyncpg.connect(
        host=PG_DEFAULTS["host"],
        port=PG_DEFAULTS["port"],
        user=PG_DEFAULTS["user"],
        password=PG_DEFAULTS["password"],
        database=PG_DEFAULTS["database"],
    )
    try:
        # First get orphaned fills (signal_id IS NULL)
        orphaned_row = await conn.fetchrow(
            """
            SELECT COUNT(*) as cnt
            FROM signal_outcomes
            WHERE outcome_type = 'fill' AND signal_id IS NULL AND created_at >= $1
            """,
            since,
        )
        orphaned_fills = orphaned_row["cnt"]

        # Try to get missing signal fills (signal_id NOT NULL but signal doesn't exist)
        # This requires the signals table to exist
        missing_signal_fills = 0
        try:
            missing_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as cnt
                FROM signal_outcomes so
                WHERE so.outcome_type = 'fill'
                  AND so.signal_id IS NOT NULL
                  AND so.created_at >= $1
                  AND NOT EXISTS (SELECT 1 FROM signals s WHERE s.signal_id = so.signal_id)
                """,
                since,
            )
            missing_signal_fills = missing_row["cnt"]
        except Exception:
            # signals table doesn't exist - can't check for missing signals
            pass

        return (orphaned_fills, missing_signal_fills)
    finally:
        await conn.close()


def check_orphaned_fills(r: redis.Redis) -> list:
    """Find fills without matching orders."""
    # Get all order IDs from Redis
    # HIGH-2: Use scan_iter instead of keys() for production safety
    order_keys = list(r.scan_iter(match="paper:order:*", count=1000))
    order_ids = set()
    for k in order_keys:
        parts = k.split(":")
        if len(parts) >= 5:
            order_ids.add(parts[-1])

    # Get all fill keys
    # HIGH-2: Use scan_iter instead of keys() for production safety
    fill_keys = list(r.scan_iter(match="paper:fill:*", count=1000))
    orphaned = []
    for k in fill_keys:
        parts = k.split(":")
        if len(parts) >= 5:
            fill_order_id = parts[-1]
            if fill_order_id not in order_ids:
                orphaned.append(k)

    return orphaned


def write_alert_key(result: ReconcileResult) -> str:
    """Write reconciliation alert to Redis for Grafana alerting.

    When divergence is detected, writes a JSON payload to the alert key
    that Grafana can query to fire alerts.

    Key: paper:reconcile:alert
    TTL: 1 hour — if next reconcile doesn't run or clears the alert, it expires
    """
    r = get_redis_client()
    alert_key = "paper:reconcile:alert"
    alert_data = {
        "status": result.status,
        "exit_code": result.exit_code,
        "divergence": result.divergence,
        "orphaned_fills_count": len(result.orphaned_fills),
        "postgres_outcomes": result.postgres_count,
        "redis_outcomes": result.redis_counts.get("outcomes", 0),
        # PAPER-RECON-ORPHANED-POLICY: Postgres-level orphaned fill tracking
        "pg_orphaned_fills": result.pg_orphaned_fills,
        "pg_missing_signal_fills": result.pg_missing_signal_fills,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    r.set(alert_key, json.dumps(alert_data))
    # TTL: 1 hour — if next reconcile doesn't run, alert expires
    r.expire(alert_key, 3600)
    return alert_key


def reconcile(since_iso: str) -> ReconcileResult:
    r = get_redis_client()

    since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))

    # Redis counts
    redis_counts = {}
    for name, key in REDIS_INDEXES.items():
        count = r.zcard(key)
        redis_counts[name] = count

    # Postgres count
    # HIGH-3: asyncio.run() is safe here since this is always called from __main__ (sync CLI entrypoint)
    pg_count = asyncio.run(get_postgres_count(since_dt))

    # Postgres orphaned fill counts (PAPER-RECON-ORPHANED-POLICY)
    # - orphaned_fills: signal_id IS NULL (expected in paper mode)
    # - missing_signal_fills: signal_id exists but no corresponding signal (anomaly)
    pg_orphaned, pg_missing_signal = asyncio.run(
        get_postgres_orphaned_fill_counts(since_dt)
    )

    # Orphaned fills (Redis-level: fills without matching orders)
    orphaned = check_orphaned_fills(r)

    # Divergence analysis
    divergence = {}
    has_divergence = False

    # Check: Redis outcomes vs Postgres outcomes
    redis_outcomes = redis_counts["outcomes"]
    if redis_outcomes != pg_count:
        divergence["postgres_mismatch"] = {
            "redis_outcomes": redis_outcomes,
            "postgres_outcomes": pg_count,
            "gap": redis_outcomes - pg_count,
        }
        has_divergence = True

    # Check: fills vs orders (fill count should be >= order count in normal operation)
    if redis_counts["fills"] > redis_counts["orders"]:
        divergence["fill_order_gap"] = {
            "fills": redis_counts["fills"],
            "orders": redis_counts["orders"],
            "extra_fills": redis_counts["fills"] - redis_counts["orders"],
        }
        # This is expected if some orders have multiple fills, but flag if orphaned too
        pass

    # Redis-level orphaned fills (fills without orders) = still reported as divergence
    # because this indicates a data integrity issue in Redis
    if orphaned:
        divergence["orphaned_fills"] = {
            "count": len(orphaned),
            "severity": "WARNING",  # Changed from CRITICAL - these are Redis-level only
            "note": "Redis fills without matching orders - investigate Redis data integrity",
        }

    # Postgres-level missing signal fills = ANOMALY (should have signal but doesn't)
    # This is different from orphaned fills (signal_id IS NULL is expected)
    if pg_missing_signal > 0:
        divergence["missing_signal_fills"] = {
            "count": pg_missing_signal,
            "severity": "CRITICAL",
            "note": "Fills with signal_id but no corresponding signal - data anomaly",
        }
        has_divergence = True

    # Orphaned fills (signal_id IS NULL) are EXPECTED in paper mode - report but don't block
    # These represent manual fills, exchange repositioning, etc.
    # Only add to divergence if we want to track it (not as blocking)
    if pg_orphaned > 0:
        divergence["pg_orphaned_fills"] = {
            "count": pg_orphaned,
            "severity": "INFO",
            "note": "Orphaned fills (signal_id IS NULL) - expected in paper mode for manual/exchange fills",
        }

    return ReconcileResult(
        redis_counts=redis_counts,
        postgres_count=pg_count,
        since=since_iso,
        orphaned_fills=orphaned[:10],
        divergence=divergence,
        status="divergence" if has_divergence else "clean",
        exit_code=1 if has_divergence else 0,
        pg_orphaned_fills=pg_orphaned,
        pg_missing_signal_fills=pg_missing_signal,
    )


def main():
    parser = argparse.ArgumentParser(description="Paper canary reconciliation check")
    parser.add_argument("--since", default="2026-04-08T00:00:00Z")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Write alert to Redis on divergence (for Grafana alerting)",
    )
    args = parser.parse_args()

    try:
        result = reconcile(args.since)
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        if args.json:
            print(json.dumps({"error": str(e), "exit_code": 2}))
        sys.exit(2)

    # Write alert key if divergence detected and --alert flag is set
    alert_key = None
    if result.exit_code == 1 and args.alert:
        alert_key = write_alert_key(result)
        logger.warning(f"Divergence detected — alert written to Redis: {alert_key}")

    if args.json:
        output = asdict(result)
        if alert_key:
            output["alert_key"] = alert_key
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'=' * 50}")
        print(f"Paper Canary Reconciliation — {result.since}")
        print(f"{'=' * 50}")
        print("\nRedis Index Counts:")
        for k, v in result.redis_counts.items():
            print(f"  {k}: {v}")
        print(f"\nPostgres outcomes (since {result.since}): {result.postgres_count}")
        # PAPER-RECON-ORPHANED-POLICY: Report Postgres-level orphaned fills
        print(
            f"\nPostgres Orphaned Fills (signal_id IS NULL): {result.pg_orphaned_fills}"
        )
        if result.pg_orphaned_fills > 0:
            print(
                "  ℹ️  These are EXPECTED in paper mode (manual fills, exchange repositioning)"
            )
        print(
            f"Postgres Missing Signal Fills (anomaly): {result.pg_missing_signal_fills}"
        )
        if result.pg_missing_signal_fills > 0:
            print("  ⚠️  These indicate a DATA ANOMALY - requires investigation")
        print(
            f"\nRedis Orphaned Fills (fills without orders): {len(result.orphaned_fills)}"
        )
        if result.orphaned_fills:
            for f in result.orphaned_fills[:5]:
                print(f"  ! {f}")
        if result.divergence:
            print("\nDivergence detected:")
            for k, v in result.divergence.items():
                print(f"  [{k}] {v}")
        else:
            print("\n✅ Status: CLEAN — no divergence")
        print(f"\nResult: {result.status.upper()} (exit {result.exit_code})")
        if alert_key:
            print(f"\n⚠️  ALERT written to Redis: {alert_key}")

    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
