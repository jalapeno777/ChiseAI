#!/usr/bin/env python3
"""Reconciliation script for Bybit execution data vs Redis journal entries.

Compares actual Bybit API execution data with Redis journal entries to ensure
data consistency. Uses tolerance-based comparison with fail-closed design.

Usage:
    python3 scripts/validation/reconcile_bybit_journal.py --days 7 --price-tolerance-pct 0.1

Exit codes:
    0 - All trades match within tolerance
    1 - Mismatches found but within tolerance
    2 - Critical mismatches (PnL difference > tolerance)
    3 - Missing trades detected
    4 - Configuration or connection error

For ST-KPI-FIX-001: Bybit-Journal Reconciliation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class BybitExecution:
    """Normalized Bybit execution data.

    Attributes:
        order_id: Bybit order ID
        symbol: Trading pair symbol
        side: Trade side ("Buy" or "Sell")
        exec_price: Execution/fill price
        exec_qty: Executed quantity
        exec_fee: Execution fee
        exec_time: Execution timestamp (ms)
        exec_id: Unique execution ID from Bybit
    """

    order_id: str
    symbol: str
    side: str
    exec_price: float
    exec_qty: float
    exec_fee: float
    exec_time: int  # milliseconds
    exec_id: str

    @property
    def exec_datetime(self) -> datetime:
        """Convert exec_time to datetime."""
        return datetime.fromtimestamp(self.exec_time / 1000, tz=UTC)


@dataclass
class JournalEntry:
    """Normalized Redis journal entry data.

    Attributes:
        entry_id: Journal entry ID
        symbol: Trading pair symbol
        side: Trade side ("buy" or "sell")
        fills: List of fill records
        realized_pnl: Realized PnL
        fees: Total fees
        entry_time: Entry timestamp
        signal_id: Associated signal ID
    """

    entry_id: str
    symbol: str
    side: str
    fills: list[dict[str, Any]]
    realized_pnl: float
    fees: float
    entry_time: datetime
    signal_id: str

    @property
    def total_qty(self) -> float:
        """Calculate total filled quantity."""
        return sum(f.get("quantity", 0) for f in self.fills)

    @property
    def avg_fill_price(self) -> float | None:
        """Calculate average fill price."""
        if not self.fills:
            return None
        total_value = sum(f.get("price", 0) * f.get("quantity", 0) for f in self.fills)
        total_qty = self.total_qty
        return total_value / total_qty if total_qty > 0 else None


@dataclass
class TradeMismatch:
    """Details of a trade mismatch.

    Attributes:
        match_type: Type of match issue ("price", "qty", "fee", "pnl", "side", "symbol")
        bybit_value: Value from Bybit
        journal_value: Value from journal
        tolerance: Applied tolerance
        diff: Absolute difference
        pct_diff: Percentage difference
    """

    match_type: str
    bybit_value: Any
    journal_value: Any
    tolerance: float
    diff: float
    pct_diff: float


@dataclass
class MatchedTrade:
    """Successfully matched trade.

    Attributes:
        order_id: Order ID
        symbol: Trading symbol
        side: Trade side
        bybit_exec: Bybit execution data
        journal_entry: Journal entry data
        price_diff_pct: Price difference percentage
        qty_diff_pct: Quantity difference percentage
        fee_diff: Fee difference
    """

    order_id: str
    symbol: str
    side: str
    bybit_exec: BybitExecution
    journal_entry: JournalEntry
    price_diff_pct: float
    qty_diff_pct: float
    fee_diff: float


@dataclass
class ReconciliationReport:
    """Complete reconciliation report.

    Attributes:
        execution_id: Unique execution ID
        timestamp_utc: Report generation timestamp
        period_start: Start of reconciliation period
        period_end: End of reconciliation period
        bybit_trade_count: Total trades from Bybit
        journal_trade_count: Total trades from journal
        matched_count: Number of matched trades
        mismatched_count: Number of mismatched trades
        missing_in_journal: Trades in Bybit but not journal
        missing_in_bybit: Trades in journal but not Bybit
        mismatches: List of detailed mismatches
        matched: List of successfully matched trades
        tolerance_pct: Applied price tolerance percentage
        tolerance_pnl: Applied PnL tolerance
        overall_passed: Whether reconciliation passed
        bybit_total_pnl: Total PnL from Bybit
        journal_total_pnl: Total PnL from journal
        pnl_diff: Difference in total PnL
    """

    execution_id: str = field(default_factory=lambda: str(uuid4())[:8])
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    period_start: str = ""
    period_end: str = ""
    bybit_trade_count: int = 0
    journal_trade_count: int = 0
    matched_count: int = 0
    mismatched_count: int = 0
    missing_in_journal: list[str] = field(default_factory=list)
    missing_in_bybit: list[str] = field(default_factory=list)
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    matched: list[dict[str, Any]] = field(default_factory=list)
    tolerance_pct: float = 0.1
    tolerance_pnl: float = 0.01
    overall_passed: bool = False
    bybit_total_pnl: float = 0.0
    journal_total_pnl: float = 0.0
    pnl_diff: float = 0.0
    critical_mismatches: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "execution_id": self.execution_id,
            "timestamp_utc": self.timestamp_utc,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "bybit_trade_count": self.bybit_trade_count,
            "journal_trade_count": self.journal_trade_count,
            "matched_count": self.matched_count,
            "mismatched_count": self.mismatched_count,
            "critical_mismatches": self.critical_mismatches,
            "missing_in_journal": self.missing_in_journal,
            "missing_in_bybit": self.missing_in_bybit,
            "tolerance_pct": self.tolerance_pct,
            "tolerance_pnl": self.tolerance_pnl,
            "overall_passed": self.overall_passed,
            "bybit_total_pnl": self.bybit_total_pnl,
            "journal_total_pnl": self.journal_total_pnl,
            "pnl_diff": self.pnl_diff,
            "mismatches": self.mismatches,
            "matched": self.matched,
        }


class BybitJournalReconciler:
    """Reconciles Bybit execution data with Redis journal entries.

    Fetches data from both sources, compares trade-by-trade with
    tolerance-based matching, and produces a reconciliation report.

    Attributes:
        redis_host: Redis host address
        redis_port: Redis port
        tolerance_pct: Price comparison tolerance percentage
        tolerance_pnl: PnL comparison tolerance in USD
        tolerance_qty: Quantity comparison tolerance percentage
        dry_run: If True, use mock data instead of real APIs
    """

    def __init__(
        self,
        redis_host: str = "host.docker.internal",
        redis_port: int = 6380,
        tolerance_pct: float = 0.1,
        tolerance_pnl: float = 0.01,
        tolerance_qty: float = 0.1,
        dry_run: bool = False,
    ):
        """Initialize the reconciler.

        Args:
            redis_host: Redis host address
            redis_port: Redis port
            tolerance_pct: Price tolerance percentage (e.g., 0.1 = 0.1%)
            tolerance_pnl: PnL tolerance in USD (e.g., 0.01 = $0.01)
            tolerance_qty: Quantity tolerance percentage
            dry_run: If True, use mock data for testing
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.tolerance_pct = tolerance_pct
        self.tolerance_pnl = tolerance_pnl
        self.tolerance_qty = tolerance_qty
        self.dry_run = dry_run
        self._redis: Any = None

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis as redis_lib

                self._redis = redis_lib.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    decode_responses=True,
                )
                # Test connection
                self._redis.ping()
                logger.debug(
                    f"Connected to Redis at {self.redis_host}:{self.redis_port}"
                )
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        return self._redis

    def _generate_mock_bybit_executions(self, days: int = 7) -> list[BybitExecution]:
        """Generate mock Bybit execution data for dry-run mode.

        Args:
            days: Number of days to simulate

        Returns:
            List of mock BybitExecution objects
        """
        logger.info("Generating mock Bybit executions (dry-run mode)...")
        executions: list[BybitExecution] = []
        base_time = datetime.now(UTC)

        # Generate mock trades
        mock_trades = [
            {
                "order_id": "ord-001",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "price": 65000.0,
                "qty": 0.5,
                "fee": 1.5,
            },
            {
                "order_id": "ord-002",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "price": 65500.0,
                "qty": 0.5,
                "fee": 1.55,
            },
            {
                "order_id": "ord-003",
                "symbol": "ETHUSDT",
                "side": "Buy",
                "price": 3500.0,
                "qty": 2.0,
                "fee": 0.7,
            },
            {
                "order_id": "ord-004",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "price": 3520.0,
                "qty": 2.0,
                "fee": 0.704,
            },
            {
                "order_id": "ord-005",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "price": 64800.0,
                "qty": 1.0,
                "fee": 3.24,
            },  # Will mismatch price slightly
        ]

        for i, trade in enumerate(mock_trades):
            exec_time = int((base_time - timedelta(hours=i)).timestamp() * 1000)
            execution = BybitExecution(
                order_id=trade["order_id"],
                symbol=trade["symbol"],
                side=trade["side"],
                exec_price=trade["price"],
                exec_qty=trade["qty"],
                exec_fee=trade["fee"],
                exec_time=exec_time,
                exec_id=f"exec-{trade['order_id']}",
            )
            executions.append(execution)

        logger.info(f"Generated {len(executions)} mock Bybit executions")
        return executions

    def _generate_mock_journal_entries(self, days: int = 7) -> list[JournalEntry]:
        """Generate mock Redis journal entries for dry-run mode.

        Args:
            days: Number of days to simulate

        Returns:
            List of mock JournalEntry objects
        """
        logger.info("Generating mock journal entries (dry-run mode)...")
        entries: list[JournalEntry] = []
        base_time = datetime.now(UTC)

        # Generate mock entries - most match, some have slight variations
        mock_entries = [
            {
                "entry_id": "entry-001",
                "symbol": "BTCUSDT",
                "side": "buy",
                "fills": [{"price": 65000.0, "quantity": 0.5, "fill_id": "ord-001"}],
                "realized_pnl": 0.0,
                "fees": 1.5,
                "signal_id": "sig-001",
            },
            {
                "entry_id": "entry-002",
                "symbol": "BTCUSDT",
                "side": "sell",
                "fills": [{"price": 65500.0, "quantity": 0.5, "fill_id": "ord-002"}],
                "realized_pnl": 250.0,
                "fees": 1.55,
                "signal_id": "sig-002",
            },
            {
                "entry_id": "entry-003",
                "symbol": "ETHUSDT",
                "side": "buy",
                "fills": [{"price": 3500.0, "quantity": 2.0, "fill_id": "ord-003"}],
                "realized_pnl": 0.0,
                "fees": 0.7,
                "signal_id": "sig-003",
            },
            {
                "entry_id": "entry-004",
                "symbol": "ETHUSDT",
                "side": "sell",
                "fills": [{"price": 3520.0, "quantity": 2.0, "fill_id": "ord-004"}],
                "realized_pnl": 40.0,
                "fees": 0.704,
                "signal_id": "sig-004",
            },
            {
                "entry_id": "entry-005",
                "symbol": "BTCUSDT",
                "side": "buy",
                "fills": [
                    {"price": 64900.0, "quantity": 1.0, "fill_id": "ord-005"}
                ],  # Price mismatch (0.15%)
                "realized_pnl": 0.0,
                "fees": 3.24,
                "signal_id": "sig-005",
            },
            {
                "entry_id": "entry-phantom",
                "symbol": "SOLUSDT",
                "side": "buy",
                "fills": [{"price": 150.0, "quantity": 10.0, "fill_id": "ord-phantom"}],
                "realized_pnl": 0.0,
                "fees": 1.5,
                "signal_id": "sig-phantom",
            },
        ]

        for i, entry_data in enumerate(mock_entries):
            entry_time = base_time - timedelta(hours=i)
            journal_entry = JournalEntry(
                entry_id=entry_data["entry_id"],
                symbol=entry_data["symbol"],
                side=entry_data["side"],
                fills=entry_data["fills"],
                realized_pnl=entry_data["realized_pnl"],
                fees=entry_data["fees"],
                entry_time=entry_time,
                signal_id=entry_data["signal_id"],
            )
            entries.append(journal_entry)

        logger.info(f"Generated {len(entries)} mock journal entries")
        return entries

    async def fetch_bybit_executions(
        self,
        days: int = 7,
        symbol: str | None = None,
    ) -> list[BybitExecution]:
        """Fetch execution data from Bybit API.

        Args:
            days: Number of days to look back
            symbol: Optional symbol filter

        Returns:
            List of normalized BybitExecution objects
        """
        if self.dry_run:
            return self._generate_mock_bybit_executions(days)

        executions: list[BybitExecution] = []

        try:
            # Import here to avoid dependency issues in tests
            from data.exchange.bybit_connector import BybitConnector

            end_time = int(datetime.now(UTC).timestamp() * 1000)
            start_time = int(
                (datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000
            )

            logger.info(f"Fetching Bybit executions from {days} days ago...")

            async with BybitConnector.from_env() as connector:
                # Get execution history
                response = await connector.get_fills(
                    symbol=symbol,
                    start_time=start_time,
                    end_time=end_time,
                    limit=100,
                )

                result = response.get("result", {})
                exec_list = result.get("list", [])

                logger.info(f"Retrieved {len(exec_list)} executions from Bybit")

                for exec_data in exec_list:
                    try:
                        execution = BybitExecution(
                            order_id=exec_data.get("orderId", ""),
                            symbol=exec_data.get("symbol", ""),
                            side=exec_data.get("side", ""),
                            exec_price=float(exec_data.get("execPrice", 0)),
                            exec_qty=float(exec_data.get("execQty", 0)),
                            exec_fee=float(exec_data.get("execFee", 0)),
                            exec_time=int(exec_data.get("execTime", 0)),
                            exec_id=exec_data.get("execId", ""),
                        )
                        executions.append(execution)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse execution data: {e}")
                        continue

        except ImportError as e:
            logger.error(f"Failed to import BybitConnector: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Bybit executions: {e}")
            raise

        return executions

    async def fetch_journal_entries(
        self,
        days: int = 7,
        session_id: str | None = None,
    ) -> list[JournalEntry]:
        """Fetch journal entries from Redis.

        Args:
            days: Number of days to look back
            session_id: Optional session ID filter (fetches all sessions if None)

        Returns:
            List of normalized JournalEntry objects
        """
        if self.dry_run:
            return self._generate_mock_journal_entries(days)

        entries: list[JournalEntry] = []
        redis = self._get_redis()

        try:
            cutoff_time = datetime.now(UTC) - timedelta(days=days)

            logger.info(f"Fetching journal entries from {days} days ago...")

            if session_id:
                # Fetch specific session
                session_entries = await self._fetch_session_entries(
                    session_id, cutoff_time
                )
                entries.extend(session_entries)
            else:
                # Fetch all sessions
                sessions_key = "paper:journal:sessions"
                session_ids = redis.smembers(sessions_key)

                logger.info(f"Found {len(session_ids)} sessions")

                for sid in session_ids:
                    session_entries = await self._fetch_session_entries(
                        sid, cutoff_time
                    )
                    entries.extend(session_entries)

            logger.info(f"Retrieved {len(entries)} journal entries")

        except Exception as e:
            logger.error(f"Failed to fetch journal entries: {e}")
            raise

        return entries

    async def _fetch_session_entries(
        self,
        session_id: str,
        cutoff_time: datetime,
    ) -> list[JournalEntry]:
        """Fetch entries for a specific session.

        Args:
            session_id: Session ID to fetch
            cutoff_time: Only fetch entries after this time

        Returns:
            List of JournalEntry objects
        """
        entries: list[JournalEntry] = []
        redis = self._get_redis()

        try:
            # Get entry IDs for this session
            entries_key = f"paper:journal:{session_id}:entries"
            entry_ids = redis.lrange(entries_key, 0, -1)

            for entry_id in entry_ids:
                # Fetch entry data
                entry_key = f"paper:journal:{session_id}:entry:{entry_id}"
                entry_data_raw = redis.hget(entry_key, "data")

                if not entry_data_raw:
                    continue

                entry_data = json.loads(entry_data_raw)

                # Parse entry time
                entry_time_str = entry_data.get("entry_time", "")
                if entry_time_str:
                    entry_time = datetime.fromisoformat(
                        entry_time_str.replace("Z", "+00:00")
                    )
                else:
                    continue

                # Skip if too old
                if entry_time < cutoff_time:
                    continue

                # Normalize side
                side = entry_data.get("side", "").lower()

                journal_entry = JournalEntry(
                    entry_id=entry_id,
                    symbol=entry_data.get("symbol", ""),
                    side=side,
                    fills=entry_data.get("fills", []),
                    realized_pnl=entry_data.get("realized_pnl", 0.0),
                    fees=entry_data.get("fees", 0.0),
                    entry_time=entry_time,
                    signal_id=entry_data.get("signal_id", ""),
                )
                entries.append(journal_entry)

        except Exception as e:
            logger.warning(f"Failed to fetch session {session_id} entries: {e}")

        return entries

    def compare_executions(
        self,
        bybit_execs: list[BybitExecution],
        journal_entries: list[JournalEntry],
    ) -> ReconciliationReport:
        """Compare Bybit executions with journal entries.

        Args:
            bybit_execs: List of Bybit executions
            journal_entries: List of journal entries

        Returns:
            ReconciliationReport with comparison results
        """
        report = ReconciliationReport(
            tolerance_pct=self.tolerance_pct,
            tolerance_pnl=self.tolerance_pnl,
        )

        # Set period bounds
        if bybit_execs:
            min_time = min(e.exec_datetime for e in bybit_execs)
            max_time = max(e.exec_datetime for e in bybit_execs)
            report.period_start = min_time.isoformat()
            report.period_end = max_time.isoformat()

        report.bybit_trade_count = len(bybit_execs)
        report.journal_trade_count = len(journal_entries)

        # Calculate total PnL from Bybit (using exec_fee as proxy for cost)
        report.bybit_total_pnl = sum(
            -e.exec_fee for e in bybit_execs
        )  # Fees represent cost

        # Calculate total PnL from journal
        report.journal_total_pnl = sum(e.realized_pnl for e in journal_entries)

        report.pnl_diff = abs(report.bybit_total_pnl - report.journal_total_pnl)

        # Build lookup maps
        bybit_by_order: dict[str, BybitExecution] = {}
        bybit_without_order_id: list[BybitExecution] = []

        for exec in bybit_execs:
            if exec.order_id:
                # Aggregate by order_id (multiple fills can have same order_id)
                if exec.order_id not in bybit_by_order:
                    bybit_by_order[exec.order_id] = exec
                else:
                    # Aggregate quantities and fees for same order
                    existing = bybit_by_order[exec.order_id]
                    existing.exec_qty += exec.exec_qty
                    existing.exec_fee += exec.exec_fee
            else:
                bybit_without_order_id.append(exec)

        journal_by_entry: dict[str, JournalEntry] = {
            e.entry_id: e for e in journal_entries
        }

        # Track matched entries
        matched_bybit_ids: set[str] = set()
        matched_journal_ids: set[str] = set()

        # Compare matches
        for order_id, bybit_exec in bybit_by_order.items():
            match_found = False

            for entry_id, journal_entry in journal_by_entry.items():
                if entry_id in matched_journal_ids:
                    continue

                # Check if fills contain order_id
                fill_order_ids = [f.get("fill_id", "") for f in journal_entry.fills]

                if order_id in fill_order_ids or self._is_match(
                    bybit_exec, journal_entry
                ):
                    # Found potential match - validate details
                    mismatches = self._validate_match(bybit_exec, journal_entry)

                    if mismatches:
                        # Mismatch found
                        report.mismatched_count += 1
                        for mm in mismatches:
                            report.mismatches.append(
                                {
                                    "order_id": order_id,
                                    "entry_id": entry_id,
                                    "type": mm.match_type,
                                    "bybit_value": mm.bybit_value,
                                    "journal_value": mm.journal_value,
                                    "diff": mm.diff,
                                    "pct_diff": mm.pct_diff,
                                    "tolerance": mm.tolerance,
                                    "within_tolerance": mm.pct_diff <= mm.tolerance,
                                }
                            )
                            # Check if this is a critical mismatch (PnL-related)
                            if (
                                mm.match_type in ("fee", "pnl")
                                and mm.diff > self.tolerance_pnl
                            ):
                                report.critical_mismatches += 1
                    else:
                        # Perfect match
                        report.matched_count += 1
                        report.matched.append(
                            {
                                "order_id": order_id,
                                "entry_id": entry_id,
                                "symbol": bybit_exec.symbol,
                                "side": bybit_exec.side,
                                "price_diff_pct": self._pct_diff(
                                    bybit_exec.exec_price,
                                    journal_entry.avg_fill_price
                                    or bybit_exec.exec_price,
                                ),
                                "qty_diff_pct": self._pct_diff(
                                    bybit_exec.exec_qty,
                                    journal_entry.total_qty,
                                ),
                                "fee_diff": bybit_exec.exec_fee - journal_entry.fees,
                            }
                        )

                    matched_bybit_ids.add(order_id)
                    matched_journal_ids.add(entry_id)
                    match_found = True
                    break

            if not match_found:
                report.missing_in_journal.append(order_id)

        # Find journal entries not in Bybit
        for entry_id, journal_entry in journal_by_entry.items():
            if entry_id not in matched_journal_ids:
                report.missing_in_bybit.append(entry_id)

        # Determine overall result
        has_missing = (
            len(report.missing_in_journal) > 0 or len(report.missing_in_bybit) > 0
        )
        has_critical = (
            report.critical_mismatches > 0 or report.pnl_diff > self.tolerance_pnl
        )
        has_mismatches = report.mismatched_count > 0

        # Fail-closed logic:
        # - Critical mismatches or missing trades = fail
        # - Minor mismatches within tolerance = warning
        report.overall_passed = (
            not has_missing and not has_critical and not has_mismatches
        )

        return report

    def _is_match(
        self,
        bybit_exec: BybitExecution,
        journal_entry: JournalEntry,
    ) -> bool:
        """Check if Bybit execution matches journal entry.

        Uses symbol, side, and time proximity for matching.

        Args:
            bybit_exec: Bybit execution
            journal_entry: Journal entry

        Returns:
            True if likely match
        """
        # Symbol match (case insensitive)
        if bybit_exec.symbol.upper() != journal_entry.symbol.upper():
            return False

        # Side match (normalize to buy/sell)
        bybit_side = bybit_exec.side.lower()
        journal_side = journal_entry.side.lower()

        if bybit_side != journal_side:
            return False

        # Time proximity (within 60 seconds as per spec)
        time_diff = abs(
            (bybit_exec.exec_datetime - journal_entry.entry_time).total_seconds()
        )
        return time_diff <= 60  # 60 seconds tolerance

    def _validate_match(
        self,
        bybit_exec: BybitExecution,
        journal_entry: JournalEntry,
    ) -> list[TradeMismatch]:
        """Validate that a matched trade has consistent data.

        Args:
            bybit_exec: Bybit execution
            journal_entry: Journal entry

        Returns:
            List of mismatches (empty if all within tolerance)
        """
        mismatches: list[TradeMismatch] = []

        # Price comparison
        journal_price = journal_entry.avg_fill_price
        if journal_price is not None and bybit_exec.exec_price > 0:
            price_diff = abs(bybit_exec.exec_price - journal_price)
            price_pct_diff = (price_diff / bybit_exec.exec_price) * 100

            if price_pct_diff > self.tolerance_pct:
                mismatches.append(
                    TradeMismatch(
                        match_type="price",
                        bybit_value=bybit_exec.exec_price,
                        journal_value=journal_price,
                        tolerance=self.tolerance_pct,
                        diff=price_diff,
                        pct_diff=price_pct_diff,
                    )
                )

        # Quantity comparison
        if bybit_exec.exec_qty > 0:
            qty_diff = abs(bybit_exec.exec_qty - journal_entry.total_qty)
            qty_pct_diff = (qty_diff / bybit_exec.exec_qty) * 100

            if qty_pct_diff > self.tolerance_qty:
                mismatches.append(
                    TradeMismatch(
                        match_type="quantity",
                        bybit_value=bybit_exec.exec_qty,
                        journal_value=journal_entry.total_qty,
                        tolerance=self.tolerance_qty,
                        diff=qty_diff,
                        pct_diff=qty_pct_diff,
                    )
                )

        # Fee comparison
        fee_diff = abs(bybit_exec.exec_fee - journal_entry.fees)

        if fee_diff > self.tolerance_pnl:
            mismatches.append(
                TradeMismatch(
                    match_type="fee",
                    bybit_value=bybit_exec.exec_fee,
                    journal_value=journal_entry.fees,
                    tolerance=self.tolerance_pnl,
                    diff=fee_diff,
                    pct_diff=(fee_diff / max(abs(bybit_exec.exec_fee), 0.0001)) * 100,
                )
            )

        return mismatches

    @staticmethod
    def _pct_diff(val1: float, val2: float) -> float:
        """Calculate percentage difference.

        Args:
            val1: First value
            val2: Second value

        Returns:
            Percentage difference
        """
        if val1 == 0:
            return 0.0 if val2 == 0 else 100.0
        return (abs(val1 - val2) / val1) * 100

    async def reconcile(
        self,
        days: int = 7,
        symbol: str | None = None,
        session_id: str | None = None,
    ) -> ReconciliationReport:
        """Run full reconciliation.

        Args:
            days: Number of days to look back
            symbol: Optional symbol filter
            session_id: Optional session ID filter

        Returns:
            ReconciliationReport
        """
        logger.info(f"Starting reconciliation for last {days} days...")

        # Fetch data from both sources
        bybit_execs = await self.fetch_bybit_executions(days=days, symbol=symbol)
        journal_entries = await self.fetch_journal_entries(
            days=days, session_id=session_id
        )

        logger.info(f"Bybit executions: {len(bybit_execs)}")
        logger.info(f"Journal entries: {len(journal_entries)}")

        # Compare
        report = self.compare_executions(bybit_execs, journal_entries)

        return report


def print_report(report: ReconciliationReport) -> None:
    """Print reconciliation report to console.

    Args:
        report: Reconciliation report to print
    """
    print("\n" + "=" * 70)
    print("BYBIT - JOURNAL RECONCILIATION REPORT")
    print("=" * 70)
    print(f"Execution ID: {report.execution_id}")
    print(f"Timestamp: {report.timestamp_utc}")
    print(f"Period: {report.period_start} to {report.period_end}")
    print(f"Tolerance: {report.tolerance_pct}% price, ${report.tolerance_pnl} PnL")
    print("-" * 70)

    print("\n📊 SUMMARY")
    print(f"  Bybit trades:       {report.bybit_trade_count}")
    print(f"  Journal entries:    {report.journal_trade_count}")
    print(f"  Matched:            {report.matched_count} ✓")
    print(f"  Mismatched:         {report.mismatched_count}")
    print(f"  Critical issues:    {report.critical_mismatches}")
    print(f"  Missing in Journal: {len(report.missing_in_journal)}")
    print(f"  Missing in Bybit:   {len(report.missing_in_bybit)}")

    print("\n💰 PnL COMPARISON")
    print(f"  Bybit total:   ${report.bybit_total_pnl:.4f}")
    print(f"  Journal total: ${report.journal_total_pnl:.4f}")
    print(f"  Difference:    ${report.pnl_diff:.4f}")

    status_icon = "✓" if report.overall_passed else "✗"
    status_text = "PASSED" if report.overall_passed else "FAILED"
    print(f"\n  Overall: {status_icon} {status_text}")

    if report.mismatches:
        print("\n⚠️  MISMATCHES DETECTED")
        print("-" * 70)
        for i, mm in enumerate(report.mismatches[:10], 1):  # Show first 10
            within_tol = "✓" if mm.get("within_tolerance") else "✗"
            print(f"\n  {i}. Order: {mm.get('order_id', 'N/A')}")
            print(f"     Type: {mm['type']}")
            print(f"     Bybit:   {mm['bybit_value']}")
            print(f"     Journal: {mm['journal_value']}")
            print(f"     Diff: {mm['diff']:.6f} ({mm['pct_diff']:.2f}%)")
            print(f"     Tolerance: {mm['tolerance']} {within_tol}")
        if len(report.mismatches) > 10:
            print(f"\n  ... and {len(report.mismatches) - 10} more mismatches")

    if report.missing_in_journal:
        print("\n🔍 MISSING IN JOURNAL (orphaned Bybit trades)")
        print("-" * 70)
        for order_id in report.missing_in_journal[:10]:
            print(f"  - {order_id}")
        if len(report.missing_in_journal) > 10:
            print(f"  ... and {len(report.missing_in_journal) - 10} more")

    if report.missing_in_bybit:
        print("\n🔍 MISSING IN BYBIT (phantom journal entries)")
        print("-" * 70)
        for entry_id in report.missing_in_bybit[:10]:
            print(f"  - {entry_id}")
        if len(report.missing_in_bybit) > 10:
            print(f"  ... and {len(report.missing_in_bybit) - 10} more")

    if report.matched:
        print("\n✓ MATCHED TRADES (sample)")
        print("-" * 70)
        for mt in report.matched[:5]:
            print(f"  {mt['order_id']} -> {mt['entry_id']}")
            print(f"    Symbol: {mt['symbol']}, Side: {mt['side']}")
            print(f"    Price diff: {mt['price_diff_pct']:.4f}%")
            print(f"    Qty diff: {mt['qty_diff_pct']:.4f}%")
            print(f"    Fee diff: ${mt['fee_diff']:.6f}")

    print("\n" + "=" * 70)


def generate_markdown_report(report: ReconciliationReport) -> str:
    """Generate a Markdown formatted reconciliation report.

    Args:
        report: Reconciliation report

    Returns:
        Markdown formatted string
    """
    lines = [
        "# Bybit - Journal Reconciliation Report",
        "",
        "## Metadata",
        f"- **Execution ID**: {report.execution_id}",
        f"- **Timestamp**: {report.timestamp_utc}",
        f"- **Period**: {report.period_start} to {report.period_end}",
        f"- **Price Tolerance**: {report.tolerance_pct}%",
        f"- **PnL Tolerance**: ${report.tolerance_pnl}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Bybit trades | {report.bybit_trade_count} |",
        f"| Journal entries | {report.journal_trade_count} |",
        f"| Matched | {report.matched_count} ✓ |",
        f"| Mismatched | {report.mismatched_count} |",
        f"| Critical issues | {report.critical_mismatches} |",
        f"| Missing in Journal | {len(report.missing_in_journal)} |",
        f"| Missing in Bybit | {len(report.missing_in_bybit)} |",
        "",
        "## PnL Comparison",
        "",
        "| Source | Total PnL |",
        "|--------|-----------|",
        f"| Bybit | ${report.bybit_total_pnl:.4f} |",
        f"| Journal | ${report.journal_total_pnl:.4f} |",
        f"| **Difference** | **${report.pnl_diff:.4f}** |",
        "",
        f"## Overall Result: {'✓ PASSED' if report.overall_passed else '✗ FAILED'}",
        "",
    ]

    if report.mismatches:
        lines.extend(
            [
                "## Mismatches Detected",
                "",
            ]
        )
        for i, mm in enumerate(report.mismatches, 1):
            within_tol = "✓" if mm.get("within_tolerance") else "✗"
            lines.extend(
                [
                    f"### {i}. Order: {mm.get('order_id', 'N/A')}",
                    "",
                    f"- **Type**: {mm['type']}",
                    f"- **Bybit Value**: {mm['bybit_value']}",
                    f"- **Journal Value**: {mm['journal_value']}",
                    f"- **Difference**: {mm['diff']:.6f} ({mm['pct_diff']:.2f}%)",
                    f"- **Tolerance**: {mm['tolerance']} {within_tol}",
                    "",
                ]
            )

    if report.missing_in_journal:
        lines.extend(
            [
                "## Missing in Journal (Orphaned Bybit Trades)",
                "",
            ]
        )
        for order_id in report.missing_in_journal:
            lines.append(f"- {order_id}")
        lines.append("")

    if report.missing_in_bybit:
        lines.extend(
            [
                "## Missing in Bybit (Phantom Journal Entries)",
                "",
            ]
        )
        for entry_id in report.missing_in_bybit:
            lines.append(f"- {entry_id}")
        lines.append("")

    if report.matched:
        lines.extend(
            [
                "## Matched Trades",
                "",
                "| Order ID | Entry ID | Symbol | Side | Price Diff % | Qty Diff % | Fee Diff |",
                "|----------|----------|--------|------|--------------|------------|----------|",
            ]
        )
        for mt in report.matched:
            lines.append(
                f"| {mt['order_id']} | {mt['entry_id']} | {mt['symbol']} | {mt['side']} | "
                f"{mt['price_diff_pct']:.4f}% | {mt['qty_diff_pct']:.4f}% | ${mt['fee_diff']:.6f} |"
            )
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "*Generated by reconcile_bybit_journal.py*",
        ]
    )

    return "\n".join(lines)


def determine_exit_code(report: ReconciliationReport) -> int:
    """Determine exit code based on report results.

    Exit codes:
        0 - All trades match within tolerance
        1 - Mismatches found but within tolerance
        2 - Critical mismatches (PnL difference > tolerance)
        3 - Missing trades detected

    Args:
        report: Reconciliation report

    Returns:
        Exit code
    """
    has_missing = len(report.missing_in_journal) > 0 or len(report.missing_in_bybit) > 0
    has_critical = (
        report.critical_mismatches > 0 or report.pnl_diff > report.tolerance_pnl
    )
    has_mismatches = report.mismatched_count > 0

    if has_missing:
        return 3
    elif has_critical:
        return 2
    elif has_mismatches:
        return 1
    else:
        return 0


async def main() -> int:
    """Main entry point for CLI execution.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Reconcile Bybit executions with Redis journal entries"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)",
    )
    parser.add_argument(
        "--price-tolerance-pct",
        type=float,
        default=0.1,
        help="Price tolerance percentage (default: 0.1)",
    )
    parser.add_argument(
        "--pnl-tolerance",
        type=float,
        default=0.01,
        help="PnL/fee tolerance in USD (default: 0.01)",
    )
    parser.add_argument(
        "--qty-tolerance-pct",
        type=float,
        default=0.1,
        help="Quantity tolerance percentage (default: 0.1)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Filter by symbol (e.g., BTCUSDT)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Filter by session ID",
    )
    parser.add_argument(
        "--redis-host",
        type=str,
        default=os.getenv("REDIS_HOST", "host.docker.internal"),
        help="Redis host (default: host.docker.internal)",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=int(os.getenv("REDIS_PORT", "6380")),
        help="Redis port (default: 6380)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="docs/validation/evidence",
        help="Output directory for reports (default: docs/validation/evidence)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use mock data instead of real APIs (no credentials required)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Create reconciler
        reconciler = BybitJournalReconciler(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            tolerance_pct=args.price_tolerance_pct,
            tolerance_pnl=args.pnl_tolerance,
            tolerance_qty=args.qty_tolerance_pct,
            dry_run=args.dry_run,
        )

        # Run reconciliation
        report = await reconciler.reconcile(
            days=args.days,
            symbol=args.symbol,
            session_id=args.session_id,
        )

        # Print report to console
        print_report(report)

        # Generate output paths
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

        # Write JSON report
        json_path = output_dir / f"reconciliation-report-{timestamp}.json"
        with open(json_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\n📄 JSON report written to: {json_path}")

        # Write Markdown report
        md_path = output_dir / f"reconciliation-report-{timestamp}.md"
        with open(md_path, "w") as f:
            f.write(generate_markdown_report(report))
        print(f"📄 Markdown report written to: {md_path}")

        # Determine and return exit code
        exit_code = determine_exit_code(report)
        return exit_code

    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        return 4


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
