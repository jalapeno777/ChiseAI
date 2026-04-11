#!/usr/bin/env python3
"""
Paper Canary Backfill Script

Drains paper trading events from Redis to Postgres for the canary window.

Usage:
    python3 scripts/paper_backfill.py [--dry-run] [--since ISO_TIMESTAMP]

This script is IDEMPOTENT — safe to run multiple times.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REDIS_HOST = "host.docker.internal"
REDIS_PORT = 6380

POSTGRES_DEFAULTS = {
    "host": "host.docker.internal",
    "port": 5434,
    "user": "chiseai",
    "password": "change-me",
    "database": "chiseai",
}

ORDER_KEY_PATTERN = "paper:order:*"
FILL_KEY_PATTERN = "paper:fill:*"
OUTCOME_KEY_PATTERN = "paper:outcome:*"
ORDER_INDEX = "paper:index:orders"
FILL_INDEX = "paper:index:fills"
OUTCOME_INDEX = "paper:index:outcomes"


def get_redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


async def get_postgres_pool():
    return await asyncpg.create_pool(
        host=POSTGRES_DEFAULTS["host"],
        port=POSTGRES_DEFAULTS["port"],
        user=POSTGRES_DEFAULTS["user"],
        password=POSTGRES_DEFAULTS["password"],
        database=POSTGRES_DEFAULTS["database"],
        min_size=1,
        max_size=5,
    )


def parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def extract_order_id_from_key(key: str) -> str | None:
    """Extract order_id from paper:order:<ts>:<sym>:<order_id>."""
    parts = key.split(":")
    if len(parts) >= 5:
        return parts[-1]
    return None


async def upsert_outcome(conn, outcome_data: dict[str, Any]) -> bool:
    """Upsert a single outcome record to Postgres. Returns True if inserted/updated."""
    try:
        # HIGH-1: outcome_id must be UUID for Postgres uuid column
        outcome_id_raw = outcome_data.get("outcome_id") or str(uuid4())
        if isinstance(outcome_id_raw, str):
            try:
                outcome_id = UUID(outcome_id_raw)
            except ValueError:
                outcome_id = uuid4()  # fallback to new valid UUID
        else:
            outcome_id = outcome_id_raw

        # HIGH-1: signal_id must be UUID or None for Postgres uuid column
        signal_id_raw = outcome_data.get("signal_id")
        if signal_id_raw and isinstance(signal_id_raw, str):
            try:
                signal_id = UUID(signal_id_raw)
            except ValueError:
                signal_id = None
        else:
            signal_id = signal_id_raw  # None or UUID object

        # HIGH-1: fill_timestamp must be datetime for Postgres timestamptz column
        fill_ts_raw = outcome_data.get("fill_timestamp") or outcome_data.get(
            "created_at"
        )
        if isinstance(fill_ts_raw, str):
            fill_timestamp = parse_timestamp(fill_ts_raw)
        else:
            fill_timestamp = fill_ts_raw

        # HIGH-1: created_at must be datetime for Postgres timestamptz column
        created_at_raw = outcome_data.get("created_at", datetime.now(UTC).isoformat())
        if isinstance(created_at_raw, str):
            created_at = parse_timestamp(created_at_raw)
        else:
            created_at = created_at_raw

        # HIGH-1: entry_time must be datetime or None
        entry_time_raw = outcome_data.get("entry_time")
        if entry_time_raw and isinstance(entry_time_raw, str):
            entry_time = parse_timestamp(entry_time_raw)
        else:
            entry_time = entry_time_raw

        # HIGH-1: exit_time must be datetime or None
        exit_time_raw = outcome_data.get("exit_time")
        if exit_time_raw and isinstance(exit_time_raw, str):
            exit_time = parse_timestamp(exit_time_raw)
        else:
            exit_time = exit_time_raw

        # asyncpg handles dict -> jsonb natively; no json.dumps() needed
        metadata_val = outcome_data.get("metadata", {})
        venue_metadata_val = outcome_data.get("venue_metadata", {})

        await conn.execute(
            """
            INSERT INTO signal_outcomes (
                outcome_id, signal_id, order_id, symbol, token, side, direction,
                fill_price, fill_quantity, fill_timestamp, outcome_type, pnl, fee,
                status, created_at, metadata,
                entry_price, exit_price, entry_time, exit_time,
                leverage, entry_reason, position_size,
                execution_venue, execution_mode, execution_source, venue_metadata
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27)
            ON CONFLICT (outcome_id) DO UPDATE SET
                fill_price = EXCLUDED.fill_price,
                fill_quantity = EXCLUDED.fill_quantity,
                fill_timestamp = EXCLUDED.fill_timestamp,
                status = EXCLUDED.status,
                exit_price = EXCLUDED.exit_price,
                exit_time = EXCLUDED.exit_time,
                pnl = EXCLUDED.pnl,
                metadata = EXCLUDED.metadata
        """,
            outcome_id,
            signal_id,
            outcome_data.get("order_id", ""),
            outcome_data.get("symbol", ""),
            outcome_data.get("token", ""),
            outcome_data.get("side", ""),
            outcome_data.get("direction", ""),
            float(outcome_data.get("fill_price") or 0),
            float(outcome_data.get("fill_quantity") or 0),
            fill_timestamp,
            outcome_data.get("outcome_type", "unknown"),
            (
                float(outcome_data.get("pnl") or 0)
                if outcome_data.get("pnl") is not None
                else None
            ),
            (
                float(outcome_data.get("fee") or 0)
                if outcome_data.get("fee") is not None
                else None
            ),
            outcome_data.get("status", "filled"),
            created_at,
            metadata_val,
            float(outcome_data.get("entry_price") or 0),
            (
                float(outcome_data.get("exit_price") or 0)
                if outcome_data.get("exit_price")
                else None
            ),
            entry_time,
            exit_time,
            float(outcome_data.get("leverage") or 1.0),
            outcome_data.get("entry_reason", ""),
            float(outcome_data.get("position_size") or 0),
            outcome_data.get("execution_venue", "paper"),
            outcome_data.get("execution_mode", "paper"),
            outcome_data.get("execution_source", "canary_backfill"),
            venue_metadata_val,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to upsert outcome {outcome_id}: {e}")
        return False


def read_order_data(r: redis.Redis, key: str) -> dict[str, Any] | None:
    """Read and parse order data from Redis key."""
    try:
        raw = r.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        return data
    except Exception as e:
        logger.warning(f"Failed to read order {key}: {e}")
        return None


def construct_outcome_from_order_fill(
    order_data: dict, fill_data: dict | None
) -> dict[str, Any]:
    """Construct an outcome dict from order + optional fill data."""
    outcome = {
        "outcome_id": str(uuid4()),
        "order_id": order_data.get("order_id", ""),
        "symbol": order_data.get("symbol", ""),
        "token": order_data.get("token") or order_data.get("symbol", ""),
        "side": order_data.get("side", ""),
        "direction": order_data.get("signal_direction", "long"),
        "signal_id": order_data.get("signal_id"),
        "status": order_data.get("state", "filled"),
        "created_at": order_data.get("created_at", datetime.now(UTC).isoformat()),
        "metadata": order_data.get("metadata", {}),
        "execution_source": "canary_backfill",
    }

    if fill_data:
        outcome["fill_price"] = fill_data.get("avg_fill_price") or fill_data.get(
            "fill_price", 0
        )
        outcome["fill_quantity"] = fill_data.get("filled_quantity") or fill_data.get(
            "fill_quantity", 0
        )
        outcome["fill_timestamp"] = fill_data.get("filled_at") or fill_data.get(
            "fill_timestamp"
        )
        outcome["pnl"] = fill_data.get("pnl")
        outcome["fee"] = fill_data.get("fee")
    else:
        outcome["fill_price"] = order_data.get("price", 0)
        outcome["fill_quantity"] = order_data.get("quantity", 0)
        outcome["fill_timestamp"] = order_data.get("filled_at")

    outcome["outcome_type"] = "fill" if fill_data else "order"

    return outcome


async def run_backfill(since: datetime, dry_run: bool = False):
    """Main backfill function."""
    logger.info(f"Starting backfill from {since.isoformat()} (dry_run={dry_run})")

    r = get_redis_client()
    pool = None if dry_run else await get_postgres_pool()

    try:
        # Get all order keys with timestamps in window
        order_keys = []
        for key in r.scan_iter(match="paper:order:*", count=10000):
            try:
                # Extract timestamp from key: paper:order:<timestamp>:<symbol>:<order_id>
                parts = key.split(":")
                if len(parts) >= 3:
                    ts_str = parts[2]
                    ts = datetime.strptime(ts_str, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                    if ts >= since:
                        order_keys.append((key, ts))
            except (ValueError, IndexError):
                continue

        logger.info(f"Found {len(order_keys)} order keys in window")

        outcomes_upserted = 0
        orphaned_fills = []

        for order_key, order_ts in sorted(order_keys, key=lambda x: x[1]):
            order_data = read_order_data(r, order_key)
            if not order_data:
                continue

            order_id = order_data.get("order_id")

            # Try to find matching fill
            fill_key = f"paper:fill:*:{order_id}"
            # HIGH-2: Use scan_iter instead of keys() for production safety
            fill_keys = list(r.scan_iter(match=fill_key, count=1000))
            fill_data = None
            if fill_keys:
                try:
                    raw = r.get(fill_keys[0])
                    fill_data = json.loads(raw) if raw else None
                except Exception:
                    pass

            outcome = construct_outcome_from_order_fill(order_data, fill_data)

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would upsert: outcome_id={outcome['outcome_id']} order_id={order_id}"
                )
            else:
                async with pool.acquire() as conn:
                    success = await upsert_outcome(conn, outcome)
                    if success:
                        outcomes_upserted += 1

            # Track orphaned fills
            if not fill_keys and order_data.get("state") == "filled":
                orphaned_fills.append(order_key)

        # Check for orphaned fills (fills without matching orders)
        all_fill_keys = list(r.scan_iter(match="paper:fill:*", count=10000))
        order_ids_in_window = {ok[0].split(":")[-1] for ok in order_keys}

        orphaned = []
        for fk in all_fill_keys:
            fill_order_id = fk.split(":")[-1]
            if fill_order_id not in order_ids_in_window:
                orphaned.append(fk)

        logger.info(f"Backfill complete: {outcomes_upserted} rows upserted")
        logger.info(f"Orphaned fills (no matching order): {len(orphaned)}")
        if orphaned:
            for fk in orphaned[:5]:
                logger.warning(f"  Orphaned fill: {fk}")

        return {
            "outcomes_upserted": outcomes_upserted,
            "orphaned_fills": len(orphaned),
            "orphaned_fill_keys": orphaned[:10],
            "dry_run": dry_run,
        }

    finally:
        if pool:
            await pool.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Paper canary backfill Redis → Postgres"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without writing"
    )
    parser.add_argument(
        "--since", default="2026-04-08T00:00:00Z", help="ISO timestamp to backfill from"
    )
    args = parser.parse_args()

    since = parse_timestamp(args.since) or datetime.strptime(
        "2026-04-08T00:00:00Z", "%Y-%m-%dT%H:%M:%SZ"
    )

    result = await run_backfill(since, dry_run=args.dry_run)

    print(
        json.dumps(
            {
                "status": "ok",
                "since": since.isoformat(),
                **result,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
