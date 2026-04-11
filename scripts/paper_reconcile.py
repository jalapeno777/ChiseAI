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

    # Orphaned fills
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
        since=since_iso,
        orphaned_fills=orphaned[:10],
        divergence=divergence,
        status="divergence" if has_divergence else "clean",
        exit_code=1 if has_divergence else 0,
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
