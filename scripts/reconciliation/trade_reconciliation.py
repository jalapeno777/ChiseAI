#!/usr/bin/env python3
"""Trade reconciliation script for ChiseAI.

Compares runtime executed trades vs persisted outcomes to detect
mismatches, missing persistence records, and orphaned records.

For RECON-001: Trade Schema Reconciliation

Usage:
    python3 scripts/reconciliation/trade_reconciliation.py [--dry-run]

Exit codes:
    0 - Reconciliation successful, data consistent
    1 - Inconsistencies detected
    2 - Error during reconciliation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ml.models.signal_outcome import (
    ReconciliationResult,
    SignalOutcome,
    SignalOutcomeStatus,
)

logger = logging.getLogger(__name__)


class TradeReconciler:
    """Reconcile runtime trades with persisted outcomes.

    Queries Redis for runtime trade records and PostgreSQL/InfluxDB
    for persisted outcomes, then compares to detect mismatches.
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        postgres_client: Any | None = None,
        influxdb_client: Any | None = None,
    ) -> None:
        """Initialize reconciler with database clients.

        Args:
            redis_client: Redis client for runtime trade data
            postgres_client: PostgreSQL client for persisted outcomes
            influxdb_client: InfluxDB client for time-series data
        """
        self._redis = redis_client
        self._postgres = postgres_client
        self._influxdb = influxdb_client
        self._dry_run = False

    async def reconcile(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        dry_run: bool = False,
    ) -> ReconciliationResult:
        """Run reconciliation between runtime and persisted trades.

        Args:
            start_time: Start of time range (default: 24 hours ago)
            end_time: End of time range (default: now)
            dry_run: If True, don't modify any data

        Returns:
            ReconciliationResult with comparison results
        """
        self._dry_run = dry_run

        # Default to last 24 hours
        if end_time is None:
            end_time = datetime.now(UTC)
        if start_time is None:
            start_time = end_time - timedelta(hours=24)

        logger.info(
            f"Starting reconciliation from {start_time.isoformat()} "
            f"to {end_time.isoformat()}"
        )

        result = ReconciliationResult(timestamp=datetime.now(UTC))

        try:
            # Query runtime trades from Redis
            runtime_trades = await self._query_runtime_trades(start_time, end_time)
            result.total_executed = len(runtime_trades)
            logger.info(f"Found {len(runtime_trades)} runtime trades")

            # Query persisted outcomes from PostgreSQL
            persisted_outcomes = await self._query_persisted_outcomes(
                start_time, end_time
            )
            result.total_persisted = len(persisted_outcomes)
            logger.info(f"Found {len(persisted_outcomes)} persisted outcomes")

            # Query InfluxDB for additional verification
            influx_trades = await self._query_influxdb_trades(start_time, end_time)
            logger.info(f"Found {len(influx_trades)} trades in InfluxDB")

            # Compare and find mismatches
            result = self._compare_trades(
                runtime_trades,
                persisted_outcomes,
                influx_trades,
                result,
            )

            # Log summary
            logger.info(result.get_summary())

            return result

        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            result.errors.append(str(e))
            return result

    async def _query_runtime_trades(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Query runtime trades from Redis.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of runtime trade records
        """
        trades = []

        if self._redis is None:
            # Try to initialize Redis client
            try:
                import redis as redis_lib

                redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
                redis_port = int(os.getenv("REDIS_PORT", "6380"))
                self._redis = redis_lib.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                )
            except Exception as e:
                logger.warning(f"Could not connect to Redis: {e}")
                return trades

        try:
            # Query trades using pattern: chiseai:trades:*
            # Also check: chiseai:paper:trades:* and chiseai:signal:outcomes:*
            patterns = [
                "chiseai:trades:*",
                "chiseai:paper:trades:*",
                "chiseai:signal:outcomes:*",
                "bmad:chiseai:trades:*",
            ]

            for pattern in patterns:
                try:
                    keys = self._redis.scan_iter(match=pattern, count=1000)
                    for key in keys:
                        try:
                            data = self._redis.get(key)
                            if data:
                                trade = json.loads(data)
                                # Filter by time range
                                trade_time = self._parse_trade_time(trade)
                                if trade_time and start_time <= trade_time <= end_time:
                                    trade["_source"] = "redis"
                                    trade["_key"] = key
                                    trades.append(trade)
                        except Exception as e:
                            logger.debug(f"Error reading key {key}: {e}")
                except Exception as e:
                    logger.debug(f"Error scanning pattern {pattern}: {e}")

            # Also check Redis hashes for trade data
            hash_patterns = [
                "chiseai:trades",
                "chiseai:paper:trades",
                "bmad:chiseai:trades",
            ]

            for hash_key in hash_patterns:
                try:
                    if self._redis.exists(hash_key):
                        all_fields = self._redis.hgetall(hash_key)
                        for field, data in all_fields.items():
                            try:
                                trade = json.loads(data)
                                trade_time = self._parse_trade_time(trade)
                                if trade_time and start_time <= trade_time <= end_time:
                                    trade["_source"] = "redis_hash"
                                    trade["_key"] = f"{hash_key}:{field}"
                                    trades.append(trade)
                            except Exception as e:
                                logger.debug(f"Error parsing hash field {field}: {e}")
                except Exception as e:
                    logger.debug(f"Error reading hash {hash_key}: {e}")

        except Exception as e:
            logger.error(f"Error querying Redis: {e}")

        return trades

    async def _query_persisted_outcomes(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Query persisted outcomes from PostgreSQL.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of persisted outcome records
        """
        outcomes = []

        if self._postgres is None:
            # Try to initialize PostgreSQL client
            try:
                import asyncpg

                db_host = os.getenv("DB_HOST", "host.docker.internal")
                db_port = int(os.getenv("DB_PORT", "5434"))
                db_name = os.getenv("DB_NAME", "chiseai")
                db_user = os.getenv("DB_USER", "chiseai")
                db_pass = os.getenv("DB_PASSWORD", "chiseai")

                dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                self._postgres = await asyncpg.connect(dsn)
            except Exception as e:
                logger.warning(f"Could not connect to PostgreSQL: {e}")
                return outcomes

        try:
            # Query signal_outcomes table
            query = """
                SELECT * FROM signal_outcomes
                WHERE created_at >= $1 AND created_at <= $2
                ORDER BY created_at DESC
            """

            rows = await self._postgres.fetch(query, start_time, end_time)

            for row in rows:
                outcome = dict(row)
                outcome["_source"] = "postgres"
                outcomes.append(outcome)

        except Exception as e:
            logger.error(f"Error querying PostgreSQL: {e}")

        return outcomes

    async def _query_influxdb_trades(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Query trades from InfluxDB for verification.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of trade records from InfluxDB
        """
        trades = []

        if self._influxdb is None:
            # Try to initialize InfluxDB client
            try:
                from influxdb_client import InfluxDBClient

                influx_url = os.getenv(
                    "INFLUXDB_URL", "http://host.docker.internal:18087"
                )
                influx_token = os.getenv("INFLUXDB_TOKEN", "chiseai-token")
                influx_org = os.getenv("INFLUXDB_ORG", "chiseai")

                self._influxdb = InfluxDBClient(
                    url=influx_url,
                    token=influx_token,
                    org=influx_org,
                )
            except Exception as e:
                logger.warning(f"Could not connect to InfluxDB: {e}")
                return trades

        try:
            query_api = self._influxdb.query_api()
            bucket = os.getenv("INFLUXDB_BUCKET", "chiseai")

            query = f'''
                from(bucket: "{bucket}")
                    |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                    |> filter(fn: (r) => r._measurement == "paper_trades" or r._measurement == "trades")
                    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''

            tables = query_api.query(query)

            for table in tables:
                for record in table.records:
                    trade = {
                        "timestamp": record.get_time(),
                        "symbol": record.values.get("symbol", ""),
                        "side": record.values.get("side", ""),
                        "pnl": record.values.get("pnl", 0.0),
                        "quantity": record.values.get("quantity", 0.0),
                        "price": record.values.get("price", 0.0),
                        "order_id": record.values.get("order_id", ""),
                        "_source": "influxdb",
                    }
                    trades.append(trade)

        except Exception as e:
            logger.error(f"Error querying InfluxDB: {e}")

        return trades

    def _parse_trade_time(self, trade: dict[str, Any]) -> datetime | None:
        """Parse timestamp from trade record.

        Args:
            trade: Trade record dictionary

        Returns:
            Parsed datetime or None
        """
        # Try various timestamp fields
        for field in [
            "fill_timestamp",
            "entry_time",
            "timestamp",
            "created_at",
            "time",
        ]:
            value = trade.get(field)
            if value:
                try:
                    if isinstance(value, str):
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    elif isinstance(value, (int, float)):
                        # Assume milliseconds if large number
                        if value > 1e10:
                            return datetime.fromtimestamp(value / 1000, tz=UTC)
                        else:
                            return datetime.fromtimestamp(value, tz=UTC)
                except Exception:
                    continue
        return None

    def _compare_trades(
        self,
        runtime_trades: list[dict[str, Any]],
        persisted_outcomes: list[dict[str, Any]],
        influx_trades: list[dict[str, Any]],
        result: ReconciliationResult,
    ) -> ReconciliationResult:
        """Compare runtime trades with persisted outcomes.

        Args:
            runtime_trades: List of runtime trade records
            persisted_outcomes: List of persisted outcome records
            influx_trades: List of InfluxDB trade records
            result: ReconciliationResult to populate

        Returns:
            Updated ReconciliationResult
        """
        # Create lookup maps
        runtime_by_order_id: dict[str, dict[str, Any]] = {}
        runtime_by_symbol_time: dict[tuple[str, str], dict[str, Any]] = {}

        for trade in runtime_trades:
            order_id = trade.get("order_id", "")
            if order_id:
                runtime_by_order_id[order_id] = trade

            symbol = trade.get("symbol", "")
            trade_time = self._parse_trade_time(trade)
            time_key = trade_time.isoformat() if trade_time else ""
            if symbol and time_key:
                runtime_by_symbol_time[(symbol, time_key)] = trade

        persisted_by_order_id: dict[str, dict[str, Any]] = {}
        persisted_by_symbol_time: dict[tuple[str, str], dict[str, Any]] = {}

        for outcome in persisted_outcomes:
            order_id = outcome.get("order_id", "")
            if order_id:
                persisted_by_order_id[order_id] = outcome

            symbol = outcome.get("symbol", "")
            outcome_time = self._parse_trade_time(outcome)
            time_key = outcome_time.isoformat() if outcome_time else ""
            if symbol and time_key:
                persisted_by_symbol_time[(symbol, time_key)] = outcome

        # Find matches and mismatches
        matched_order_ids = set()

        # Check runtime trades against persisted
        for trade in runtime_trades:
            order_id = trade.get("order_id", "")
            symbol = trade.get("symbol", "")
            trade_time = self._parse_trade_time(trade)
            time_key = trade_time.isoformat() if trade_time else ""

            # Try to match by order_id
            if order_id and order_id in persisted_by_order_id:
                result.matched_count += 1
                matched_order_ids.add(order_id)
            # Try to match by symbol + time
            elif (symbol, time_key) in persisted_by_symbol_time:
                result.matched_count += 1
            else:
                # No match found - runtime trade without persistence
                result.mismatched_trades.append(
                    {
                        "trade": trade,
                        "reason": "no_persistence_record",
                        "identifiers": {
                            "order_id": order_id,
                            "symbol": symbol,
                            "time": time_key,
                        },
                    }
                )

        # Check for orphaned persisted records (no runtime match)
        for outcome in persisted_outcomes:
            order_id = outcome.get("order_id", "")
            symbol = outcome.get("symbol", "")
            outcome_time = self._parse_trade_time(outcome)
            time_key = outcome_time.isoformat() if outcome_time else ""

            if order_id and order_id not in runtime_by_order_id:
                if (symbol, time_key) not in runtime_by_symbol_time:
                    result.orphaned_records.append(
                        {
                            "outcome": outcome,
                            "reason": "no_runtime_record",
                            "identifiers": {
                                "order_id": order_id,
                                "symbol": symbol,
                                "time": time_key,
                            },
                        }
                    )

        # Cross-reference with InfluxDB for additional verification
        influx_order_ids = {t.get("order_id", "") for t in influx_trades}
        for trade in result.mismatched_trades:
            order_id = trade["identifiers"]["order_id"]
            if order_id and order_id in influx_order_ids:
                trade["influxdb_verified"] = True

        return result

    async def fix_missing_persistence(
        self,
        result: ReconciliationResult,
    ) -> list[SignalOutcome]:
        """Attempt to fix missing persistence records.

        Args:
            result: ReconciliationResult with mismatched trades

        Returns:
            List of created SignalOutcome records
        """
        if self._dry_run:
            logger.info("Dry run mode - not creating missing persistence records")
            return []

        created = []

        for mismatch in result.mismatched_trades:
            trade = mismatch.get("trade", {})
            try:
                # Convert runtime trade to SignalOutcome
                outcome = SignalOutcome(
                    signal_id=trade.get("signal_id"),
                    order_id=trade.get("order_id", ""),
                    symbol=trade.get("symbol", ""),
                    token=trade.get("token", ""),
                    side=trade.get("side", ""),
                    direction=trade.get("direction", ""),
                    fill_price=Decimal(str(trade.get("fill_price", 0))),
                    fill_quantity=Decimal(str(trade.get("fill_quantity", 0))),
                    fill_timestamp=self._parse_trade_time(trade) or datetime.now(UTC),
                    outcome_type=trade.get("outcome_type", "unknown"),
                    pnl=Decimal(str(trade.get("pnl"))) if trade.get("pnl") else None,
                    fee=Decimal(str(trade.get("fee"))) if trade.get("fee") else None,
                    status=SignalOutcomeStatus.FILLED,
                    entry_price=Decimal(
                        str(trade.get("entry_price", trade.get("fill_price", 0)))
                    ),
                    exit_price=Decimal(str(trade.get("exit_price")))
                    if trade.get("exit_price")
                    else None,
                    entry_time=self._parse_trade_time(trade) or datetime.now(UTC),
                    exit_time=self._parse_trade_time(trade)
                    if trade.get("exit_price")
                    else None,
                    leverage=Decimal(str(trade.get("leverage", 1.0))),
                    entry_reason=trade.get("entry_reason", ""),
                    position_size=Decimal(
                        str(trade.get("position_size", trade.get("fill_quantity", 0)))
                    ),
                )

                # Persist to database
                if self._postgres:
                    await self._persist_outcome(outcome)
                    created.append(outcome)
                    logger.info(
                        f"Created persistence record for trade {outcome.order_id}"
                    )

            except Exception as e:
                logger.error(f"Failed to create persistence record: {e}")
                result.errors.append(f"Failed to persist trade: {e}")

        return created

    async def _persist_outcome(self, outcome: SignalOutcome) -> None:
        """Persist SignalOutcome to PostgreSQL.

        Args:
            outcome: SignalOutcome to persist
        """
        if self._postgres is None:
            return

        query = """
            INSERT INTO signal_outcomes (
                outcome_id, signal_id, order_id, symbol, token, side, direction,
                fill_price, fill_quantity, fill_timestamp, outcome_type, pnl, fee,
                status, created_at, metadata,
                entry_price, exit_price, entry_time, exit_time,
                leverage, entry_reason, position_size
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                      $17, $18, $19, $20, $21, $22, $23)
            ON CONFLICT (outcome_id) DO UPDATE SET
                status = EXCLUDED.status,
                exit_price = EXCLUDED.exit_price,
                exit_time = EXCLUDED.exit_time,
                pnl = EXCLUDED.pnl
        """

        await self._postgres.execute(
            query,
            str(outcome.outcome_id),
            str(outcome.signal_id) if outcome.signal_id else None,
            outcome.order_id,
            outcome.symbol,
            outcome.token,
            outcome.side,
            outcome.direction,
            float(outcome.fill_price),
            float(outcome.fill_quantity),
            outcome.fill_timestamp,
            outcome.outcome_type.value,
            float(outcome.pnl) if outcome.pnl else None,
            float(outcome.fee) if outcome.fee else None,
            outcome.status.value,
            outcome.created_at,
            json.dumps(outcome.metadata),
            float(outcome.entry_price),
            float(outcome.exit_price) if outcome.exit_price else None,
            outcome.entry_time,
            outcome.exit_time,
            float(outcome.leverage),
            outcome.entry_reason,
            float(outcome.position_size),
        )


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration.

    Args:
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def main() -> int:
    """Main entry point for reconciliation script.

    Returns:
        Exit code (0=success, 1=inconsistencies, 2=error)
    """
    parser = argparse.ArgumentParser(
        description="Reconcile runtime trades with persisted outcomes"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making changes",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        help="Start time (ISO format, default: 24 hours ago)",
    )
    parser.add_argument(
        "--end-time",
        type=str,
        help="End time (ISO format, default: now)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix missing persistence records",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for reconciliation report (JSON)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    # Parse time range
    start_time = None
    end_time = None

    if args.start_time:
        start_time = datetime.fromisoformat(args.start_time)
    if args.end_time:
        end_time = datetime.fromisoformat(args.end_time)

    # Create reconciler
    reconciler = TradeReconciler()

    try:
        # Run reconciliation
        result = await reconciler.reconcile(
            start_time=start_time,
            end_time=end_time,
            dry_run=args.dry_run,
        )

        # Fix missing records if requested
        if args.fix and not args.dry_run:
            fixed = await reconciler.fix_missing_persistence(result)
            logger.info(f"Fixed {len(fixed)} missing persistence records")

        # Output report
        print("\n" + result.get_summary())

        # Save to file if requested
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
            logger.info(f"Report saved to {args.output}")

        # Return appropriate exit code
        if result.errors:
            return 2
        elif not result.is_consistent:
            return 1
        else:
            return 0

    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
