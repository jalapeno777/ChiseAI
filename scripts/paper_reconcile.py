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
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import asyncpg
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6380"))

PG_DEFAULTS = {
    "host": os.environ.get("POSTGRES_HOST", "host.docker.internal"),
    "port": int(os.environ.get("POSTGRES_PORT", "5434")),
    "user": os.environ.get("POSTGRES_USER", "chiseai"),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
    "database": os.environ.get("POSTGRES_DB", "chiseai"),
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
    last_pg_outcome_time: datetime | None
    since: str
    orphaned_fills: list
    divergence: dict
    status: str  # 'clean' | 'divergence'
    exit_code: int


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


async def get_postgres_last_outcome_time() -> datetime | None:
    """Get timestamp of most recent outcome in Postgres, or None if no outcomes exist."""
    conn = await asyncpg.connect(
        host=PG_DEFAULTS["host"],
        port=PG_DEFAULTS["port"],
        user=PG_DEFAULTS["user"],
        password=PG_DEFAULTS["password"],
        database=PG_DEFAULTS["database"],
    )
    try:
        row = await conn.fetchrow(
            "SELECT created_at FROM signal_outcomes ORDER BY created_at DESC LIMIT 1"
        )
        return row["created_at"] if row else None
    finally:
        await conn.close()


def check_orphaned_fills(r: redis.Redis) -> list:
    """Find fills without matching orders."""
    # Get all order IDs from Redis
    order_keys = r.keys("paper:order:*")
    order_ids = set()
    for k in order_keys:
        parts = k.split(":")
        if len(parts) >= 5:
            order_ids.add(parts[-1])

    # Get all fill keys
    fill_keys = r.keys("paper:fill:*")
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
    pg_count = asyncio.run(get_postgres_count(since_dt))

    # Postgres last outcome time (for idle-system detection)
    last_pg_outcome = asyncio.run(get_postgres_last_outcome_time())

    # Orphaned fills
    orphaned = check_orphaned_fills(r)

    # Divergence analysis
    divergence = {}
    has_divergence = False

    # Check: Redis outcomes vs Postgres outcomes
    redis_outcomes = redis_counts["outcomes"]
    if redis_outcomes != pg_count:
        # Idle-system detection: if Redis count is 0 but Postgres has outcomes,
        # check if the sorted set expired due to 7+ days of idle time.
        # REDIS_INDEX_TTL = 604800 seconds = 7 days
        IDLE_TTL_SECONDS = 604800
        is_idle_system = False
        if redis_outcomes == 0 and pg_count > 0 and last_pg_outcome is not None:
            now = datetime.now(UTC)
            idle_seconds = (now - last_pg_outcome.replace(tzinfo=UTC)).total_seconds()
            if idle_seconds > IDLE_TTL_SECONDS:
                is_idle_system = True
                logger.info(
                    f"Idle-system detected: Redis outcomes=0 but Postgres has {pg_count} outcomes. "
                    f"Last Postgres outcome was {idle_seconds / 86400:.1f} days ago (>7 day TTL). "
                    f"Sorted set likely expired — not flagging as divergence."
                )

        if not is_idle_system:
            divergence["postgres_mismatch"] = {
                "redis_outcomes": redis_outcomes,
                "postgres_outcomes": pg_count,
                "gap": redis_outcomes - pg_count,
            }
            has_divergence = True

    # Orphaned fills = CRITICAL
    if orphaned:
        divergence["orphaned_fills"] = {
            "count": len(orphaned),
            "severity": "CRITICAL",
        }
        has_divergence = True

    return ReconcileResult(
        redis_counts=redis_counts,
        postgres_count=pg_count,
        last_pg_outcome_time=last_pg_outcome,
        since=since_iso,
        orphaned_fills=orphaned[:10],
        divergence=divergence,
        status="divergence" if has_divergence else "clean",
        exit_code=1 if has_divergence else 0,
    )


def main():
    # Password guard
    if not os.environ.get("POSTGRES_PASSWORD"):
        raise SystemExit("ERROR: POSTGRES_PASSWORD required")

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

    # Cleanup alert key if reconciliation is clean
    if result.exit_code == 0 and args.alert:
        r = get_redis_client()
        if r.exists("paper:reconcile:alert"):
            r.delete("paper:reconcile:alert")
            logger.info("Cleared stale alert key — reconciliation is clean")

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
        print(f"\nOrphaned fills: {len(result.orphaned_fills)}")
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
