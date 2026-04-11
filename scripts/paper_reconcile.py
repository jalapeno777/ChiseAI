#!/usr/bin/env python3
"""
Paper Canary Reconciliation Check

Compares Redis index counts to Postgres outcome count and detects orphaned fills.
Monitors data integrity between operational (Redis) and durable (Postgres) stores.

Usage:
    python3 scripts/paper_reconcile.py [--since ISO_TIMESTAMP] [--json]

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


def _scan_keys(r, pattern):
    """Scan Redis keys matching pattern using SCAN (non-blocking)."""
    keys = []
    cursor = 0
    while True:
        cursor, batch = r.scan(cursor=cursor, match=pattern, count=500)
        keys.extend(batch)
        if cursor == 0:
            break
    return keys


def check_orphaned_fills(r: redis.Redis) -> list:
    """Find fills without matching orders."""
    # Get all order IDs from Redis
    order_keys = _scan_keys(r, "paper:order:*")
    order_ids = set()
    for k in order_keys:
        parts = k.split(":")
        if len(parts) >= 5:
            order_ids.add(parts[-1])

    # Get all fill keys
    fill_keys = _scan_keys(r, "paper:fill:*")
    orphaned = []
    for k in fill_keys:
        parts = k.split(":")
        if len(parts) >= 5:
            fill_order_id = parts[-1]
            if fill_order_id not in order_ids:
                orphaned.append(k)

    return orphaned


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
    args = parser.parse_args()

    try:
        result = reconcile(args.since)
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        if args.json:
            print(json.dumps({"error": str(e), "exit_code": 2}))
        sys.exit(2)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
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

    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
