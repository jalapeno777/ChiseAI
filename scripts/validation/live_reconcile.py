#!/usr/bin/env python3
"""LIVE reconciliation script for Bybit demo API vs Redis journal.

Fetches REAL execution data from Bybit demo API and compares with Redis journal
to answer the critical question: Are all trades net negative?

Usage:
    python3 scripts/validation/live_reconcile.py --days 7 --output /tmp/live-recon.json

For ST-KPI-FIX-001: Live Reconciliation
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
    """Normalized Bybit execution data from LIVE API."""

    order_id: str
    symbol: str
    side: str
    exec_price: float
    exec_qty: float
    exec_fee: float
    exec_time: int  # milliseconds
    exec_id: str
    exec_value: float  # exec_price * exec_qty
    exec_type: str  # Trade, ADL, etc.
    closed_pnl: float  # Realized PnL for closing trades

    @property
    def exec_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.exec_time / 1000, tz=UTC)

    @property
    def net_pnl(self) -> float:
        """Net PnL after fees."""
        return self.closed_pnl - self.exec_fee


@dataclass
class JournalEntry:
    """Normalized Redis journal entry."""

    entry_id: str
    symbol: str
    side: str
    fills: list[dict[str, Any]]
    realized_pnl: float
    fees: float
    entry_time: datetime
    signal_id: str
    order_ids: list[str]

    @property
    def total_qty(self) -> float:
        return sum(f.get("quantity", 0) for f in self.fills)

    @property
    def avg_fill_price(self) -> float | None:
        if not self.fills:
            return None
        total_value = sum(f.get("price", 0) * f.get("quantity", 0) for f in self.fills)
        total_qty = self.total_qty
        return total_value / total_qty if total_qty > 0 else None

    @property
    def net_pnl(self) -> float:
        """Net PnL after fees."""
        return self.realized_pnl - self.fees


@dataclass
class TradeMatch:
    """A matched trade between Bybit and journal."""

    order_id: str
    exec_id: str
    symbol: str
    side: str
    exec_time: datetime
    bybit_price: float
    bybit_qty: float
    bybit_fee: float
    bybit_closed_pnl: float
    bybit_net_pnl: float
    journal_price: float | None
    journal_qty: float
    journal_fee: float
    journal_realized_pnl: float
    journal_net_pnl: float
    price_diff_pct: float
    qty_diff_pct: float
    pnl_diff: float
    is_profitable: bool  # Is this trade net positive?


@dataclass
class LiveReconciliationReport:
    """Complete live reconciliation report."""

    execution_id: str = field(default_factory=lambda: str(uuid4())[:8])
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    period_start: str = ""
    period_end: str = ""

    # Raw counts
    bybit_trade_count: int = 0
    journal_trade_count: int = 0
    matched_count: int = 0
    mismatched_count: int = 0
    missing_in_journal: list[str] = field(default_factory=list)
    missing_in_bybit: list[str] = field(default_factory=list)

    # PnL analysis
    bybit_total_closed_pnl: float = 0.0
    bybit_total_fees: float = 0.0
    bybit_net_pnl: float = 0.0
    journal_total_realized_pnl: float = 0.0
    journal_total_fees: float = 0.0
    journal_net_pnl: float = 0.0
    pnl_diff: float = 0.0

    # Trade analysis
    profitable_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    all_trades_net_negative: bool = True  # The critical question

    # Sample trades
    sample_trades: list[dict[str, Any]] = field(default_factory=list)
    mismatches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "timestamp_utc": self.timestamp_utc,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "bybit_trade_count": self.bybit_trade_count,
            "journal_trade_count": self.journal_trade_count,
            "matched_count": self.matched_count,
            "mismatched_count": self.mismatched_count,
            "missing_in_journal": self.missing_in_journal,
            "missing_in_bybit": self.missing_in_bybit,
            "bybit_total_closed_pnl": self.bybit_total_closed_pnl,
            "bybit_total_fees": self.bybit_total_fees,
            "bybit_net_pnl": self.bybit_net_pnl,
            "journal_total_realized_pnl": self.journal_total_realized_pnl,
            "journal_total_fees": self.journal_total_fees,
            "journal_net_pnl": self.journal_net_pnl,
            "pnl_diff": self.pnl_diff,
            "profitable_trades": self.profitable_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "all_trades_net_negative": self.all_trades_net_negative,
            "sample_trades": self.sample_trades,
            "mismatches": self.mismatches,
        }


class LiveReconciler:
    """Performs live reconciliation between Bybit API and Redis journal."""

    def __init__(
        self,
        redis_host: str = "host.docker.internal",
        redis_port: int = 6380,
        tolerance_pct: float = 0.1,
    ):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.tolerance_pct = tolerance_pct
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
                self._redis.ping()
                logger.info(
                    f"Connected to Redis at {self.redis_host}:{self.redis_port}"
                )
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        return self._redis

    async def fetch_bybit_executions(
        self,
        days: int = 7,
        symbol: str | None = None,
    ) -> list[BybitExecution]:
        """Fetch LIVE execution data from Bybit demo API.

        Handles >7 day ranges by chunking into 7-day windows (Bybit API limit).
        Results are deduplicated by exec_id and sorted by exec_time.
        """
        executions: list[BybitExecution] = []

        try:
            from data.exchange.bybit_connector import BybitConnector

            now_ts = int(datetime.now(UTC).timestamp() * 1000)
            total_start_ts = int(
                (datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000
            )

            logger.info(f"Fetching LIVE Bybit executions from {days} days ago...")

            # Chunk into 7-day windows (Bybit API limit)
            CHUNK_MS = timedelta(days=7).total_seconds() * 1000  # 604800000 ms
            total_range_ms = now_ts - total_start_ts

            if total_range_ms <= CHUNK_MS:
                # Single chunk — no chunking needed
                chunks = [(total_start_ts, now_ts)]
            else:
                # Multiple 7-day chunks
                chunks = []
                cursor = total_start_ts
                while cursor < now_ts:
                    chunk_end = min(cursor + int(CHUNK_MS), now_ts)
                    chunks.append((int(cursor), int(chunk_end)))
                    cursor = chunk_end
                logger.info(
                    f"Split {days}-day range into {len(chunks)} chunks (7-day max each)"
                )

            logger.info(
                f"Time range: {datetime.fromtimestamp(total_start_ts / 1000, tz=UTC)} to {datetime.fromtimestamp(now_ts / 1000, tz=UTC)}"
            )

            async with BybitConnector.from_env() as connector:
                all_exec_ids: set[str] = set()
                for i, (chunk_start, chunk_end) in enumerate(chunks):
                    logger.info(
                        f"  Chunk {i + 1}/{len(chunks)}: {datetime.fromtimestamp(chunk_start / 1000, tz=UTC).date()} → {datetime.fromtimestamp(chunk_end / 1000, tz=UTC).date()}"
                    )

                    response = await connector.get_fills(
                        symbol=symbol,
                        start_time=chunk_start,
                        end_time=chunk_end,
                        limit=100,
                    )

                    result = response.get("result", {})
                    exec_list = result.get("list", [])

                    for exec_data in exec_list:
                        exec_id = exec_data.get("execId", "")
                        # Skip duplicates across chunks
                        if exec_id and exec_id in all_exec_ids:
                            continue
                        if exec_id:
                            all_exec_ids.add(exec_id)

                        try:
                            # Parse closed PnL (only present for closing trades)
                            closed_pnl = float(exec_data.get("closedPnl", 0) or 0)

                            execution = BybitExecution(
                                order_id=exec_data.get("orderId", ""),
                                symbol=exec_data.get("symbol", ""),
                                side=exec_data.get("side", ""),
                                exec_price=float(exec_data.get("execPrice", 0) or 0),
                                exec_qty=float(exec_data.get("execQty", 0) or 0),
                                exec_fee=float(exec_data.get("execFee", 0) or 0),
                                exec_time=int(exec_data.get("execTime", 0) or 0),
                                exec_id=exec_id,
                                exec_value=float(exec_data.get("execValue", 0) or 0),
                                exec_type=exec_data.get("execType", "Trade"),
                                closed_pnl=closed_pnl,
                            )
                            executions.append(execution)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Failed to parse execution data: {e}")
                            continue

            # Sort by exec_time ascending (gap-free stitching)
            executions.sort(key=lambda e: e.exec_time)

            logger.info(
                f"Retrieved {len(executions)} unique executions from Bybit API across {len(chunks)} chunk(s)"
            )

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
    ) -> list[JournalEntry]:
        """Fetch journal entries from Redis."""
        entries: list[JournalEntry] = []
        redis = self._get_redis()

        try:
            cutoff_time = datetime.now(UTC) - timedelta(days=days)

            logger.info(f"Fetching journal entries from {days} days ago...")

            # Fetch all sessions
            sessions_key = "paper:journal:sessions"
            session_ids = redis.smembers(sessions_key)

            logger.info(f"Found {len(session_ids)} sessions in Redis")

            for sid in session_ids:
                session_entries = await self._fetch_session_entries(sid, cutoff_time)
                entries.extend(session_entries)

            logger.info(f"Retrieved {len(entries)} journal entries from Redis")

        except Exception as e:
            logger.error(f"Failed to fetch journal entries: {e}")
            raise

        return entries

    async def _fetch_session_entries(
        self,
        session_id: str,
        cutoff_time: datetime,
    ) -> list[JournalEntry]:
        """Fetch entries for a specific session."""
        entries: list[JournalEntry] = []
        redis = self._get_redis()

        try:
            entries_key = f"paper:journal:{session_id}:entries"
            entry_ids = redis.lrange(entries_key, 0, -1)

            for entry_id in entry_ids:
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

                # Extract order IDs from fills
                fills = entry_data.get("fills", [])
                order_ids = [f.get("fill_id", "") for f in fills if f.get("fill_id")]

                journal_entry = JournalEntry(
                    entry_id=entry_id,
                    symbol=entry_data.get("symbol", ""),
                    side=entry_data.get("side", "").lower(),
                    fills=fills,
                    realized_pnl=float(entry_data.get("realized_pnl", 0) or 0),
                    fees=float(entry_data.get("fees", 0) or 0),
                    entry_time=entry_time,
                    signal_id=entry_data.get("signal_id", ""),
                    order_ids=order_ids,
                )
                entries.append(journal_entry)

        except Exception as e:
            logger.warning(f"Failed to fetch session {session_id} entries: {e}")

        return entries

    def match_and_compare(
        self,
        bybit_execs: list[BybitExecution],
        journal_entries: list[JournalEntry],
    ) -> LiveReconciliationReport:
        """Match executions with journal entries and analyze."""
        report = LiveReconciliationReport()

        # Set period bounds
        if bybit_execs:
            min_time = min(e.exec_datetime for e in bybit_execs)
            max_time = max(e.exec_datetime for e in bybit_execs)
            report.period_start = min_time.isoformat()
            report.period_end = max_time.isoformat()

        report.bybit_trade_count = len(bybit_execs)
        report.journal_trade_count = len(journal_entries)

        # Calculate Bybit totals
        report.bybit_total_closed_pnl = sum(e.closed_pnl for e in bybit_execs)
        report.bybit_total_fees = sum(e.exec_fee for e in bybit_execs)
        report.bybit_net_pnl = report.bybit_total_closed_pnl - report.bybit_total_fees

        # Calculate journal totals
        report.journal_total_realized_pnl = sum(e.realized_pnl for e in journal_entries)
        report.journal_total_fees = sum(e.fees for e in journal_entries)
        report.journal_net_pnl = (
            report.journal_total_realized_pnl - report.journal_total_fees
        )

        report.pnl_diff = abs(report.bybit_net_pnl - report.journal_net_pnl)

        # Build lookup maps
        bybit_by_exec_id: dict[str, BybitExecution] = {
            e.exec_id: e for e in bybit_execs if e.exec_id
        }
        bybit_by_order_id: dict[str, list[BybitExecution]] = {}
        for e in bybit_execs:
            if e.order_id:
                if e.order_id not in bybit_by_order_id:
                    bybit_by_order_id[e.order_id] = []
                bybit_by_order_id[e.order_id].append(e)

        journal_by_entry_id: dict[str, JournalEntry] = {
            e.entry_id: e for e in journal_entries
        }

        # Track matched items
        matched_exec_ids: set[str] = set()
        matched_entry_ids: set[str] = set()

        # Match trades
        sample_trades: list[TradeMatch] = []

        for exec_id, bybit_exec in bybit_by_exec_id.items():
            match_found = False

            # Try to find matching journal entry
            for entry_id, journal_entry in journal_by_entry_id.items():
                if entry_id in matched_entry_ids:
                    continue

                # Match by order_id or symbol+time proximity
                is_match = (
                    bybit_exec.order_id in journal_entry.order_ids
                    or self._is_time_symbol_match(bybit_exec, journal_entry)
                )

                if is_match:
                    # Calculate diffs
                    price_diff_pct = 0.0
                    if journal_entry.avg_fill_price and bybit_exec.exec_price > 0:
                        price_diff_pct = (
                            abs(bybit_exec.exec_price - journal_entry.avg_fill_price)
                            / bybit_exec.exec_price
                            * 100
                        )

                    qty_diff_pct = 0.0
                    if bybit_exec.exec_qty > 0:
                        qty_diff_pct = (
                            abs(bybit_exec.exec_qty - journal_entry.total_qty)
                            / bybit_exec.exec_qty
                            * 100
                        )

                    pnl_diff = abs(bybit_exec.closed_pnl - journal_entry.realized_pnl)

                    # Determine if profitable
                    is_profitable = bybit_exec.net_pnl > 0

                    trade_match = TradeMatch(
                        order_id=bybit_exec.order_id,
                        exec_id=exec_id,
                        symbol=bybit_exec.symbol,
                        side=bybit_exec.side,
                        exec_time=bybit_exec.exec_datetime,
                        bybit_price=bybit_exec.exec_price,
                        bybit_qty=bybit_exec.exec_qty,
                        bybit_fee=bybit_exec.exec_fee,
                        bybit_closed_pnl=bybit_exec.closed_pnl,
                        bybit_net_pnl=bybit_exec.net_pnl,
                        journal_price=journal_entry.avg_fill_price,
                        journal_qty=journal_entry.total_qty,
                        journal_fee=journal_entry.fees,
                        journal_realized_pnl=journal_entry.realized_pnl,
                        journal_net_pnl=journal_entry.net_pnl,
                        price_diff_pct=price_diff_pct,
                        qty_diff_pct=qty_diff_pct,
                        pnl_diff=pnl_diff,
                        is_profitable=is_profitable,
                    )

                    sample_trades.append(trade_match)

                    # Track counts
                    if is_profitable:
                        report.profitable_trades += 1
                    elif bybit_exec.net_pnl < 0:
                        report.losing_trades += 1
                    else:
                        report.breakeven_trades += 1

                    # Check for mismatches
                    if (
                        price_diff_pct > self.tolerance_pct
                        or qty_diff_pct > self.tolerance_pct
                    ):
                        report.mismatched_count += 1
                        report.mismatches.append(
                            {
                                "exec_id": exec_id,
                                "entry_id": entry_id,
                                "order_id": bybit_exec.order_id,
                                "symbol": bybit_exec.symbol,
                                "price_diff_pct": price_diff_pct,
                                "qty_diff_pct": qty_diff_pct,
                                "pnl_diff": pnl_diff,
                                "bybit_net_pnl": bybit_exec.net_pnl,
                                "journal_net_pnl": journal_entry.net_pnl,
                            }
                        )
                    else:
                        report.matched_count += 1

                    matched_exec_ids.add(exec_id)
                    matched_entry_ids.add(entry_id)
                    match_found = True
                    break

            if not match_found:
                report.missing_in_journal.append(f"{bybit_exec.order_id} ({exec_id})")

                # Still count for PnL analysis
                if bybit_exec.net_pnl > 0:
                    report.profitable_trades += 1
                elif bybit_exec.net_pnl < 0:
                    report.losing_trades += 1
                else:
                    report.breakeven_trades += 1

        # Find journal entries not in Bybit
        for entry_id, journal_entry in journal_by_entry_id.items():
            if entry_id not in matched_entry_ids:
                report.missing_in_bybit.append(entry_id)

        # Answer the critical question
        report.all_trades_net_negative = report.profitable_trades == 0

        # Store sample trades (up to 20)
        report.sample_trades = [
            {
                "order_id": t.order_id,
                "exec_id": t.exec_id,
                "symbol": t.symbol,
                "side": t.side,
                "exec_time": t.exec_time.isoformat(),
                "bybit_price": t.bybit_price,
                "bybit_qty": t.bybit_qty,
                "bybit_fee": t.bybit_fee,
                "bybit_closed_pnl": t.bybit_closed_pnl,
                "bybit_net_pnl": t.bybit_net_pnl,
                "journal_price": t.journal_price,
                "journal_qty": t.journal_qty,
                "journal_fee": t.journal_fee,
                "journal_realized_pnl": t.journal_realized_pnl,
                "journal_net_pnl": t.journal_net_pnl,
                "price_diff_pct": t.price_diff_pct,
                "qty_diff_pct": t.qty_diff_pct,
                "pnl_diff": t.pnl_diff,
                "is_profitable": t.is_profitable,
            }
            for t in sample_trades[:20]
        ]

        return report

    def _is_time_symbol_match(
        self,
        bybit_exec: BybitExecution,
        journal_entry: JournalEntry,
    ) -> bool:
        """Check if execution matches journal entry by symbol and time."""
        # Symbol match (case insensitive)
        if bybit_exec.symbol.upper() != journal_entry.symbol.upper():
            return False

        # Side match (normalize)
        bybit_side = bybit_exec.side.lower()
        journal_side = journal_entry.side.lower()
        if bybit_side != journal_side:
            return False

        # Time proximity (within 5 minutes)
        time_diff = abs(
            (bybit_exec.exec_datetime - journal_entry.entry_time).total_seconds()
        )
        return time_diff <= 300  # 5 minutes

    async def reconcile(self, days: int = 7) -> LiveReconciliationReport:
        """Run full live reconciliation."""
        logger.info(f"Starting LIVE reconciliation for last {days} days...")
        logger.info("=" * 70)

        # Fetch data from both sources
        bybit_execs = await self.fetch_bybit_executions(days=days)
        journal_entries = await self.fetch_journal_entries(days=days)

        logger.info(f"Bybit executions: {len(bybit_execs)}")
        logger.info(f"Journal entries: {len(journal_entries)}")

        # Compare
        report = self.match_and_compare(bybit_execs, journal_entries)

        return report


def print_live_report(report: LiveReconciliationReport) -> None:
    """Print live reconciliation report."""
    print("\n" + "=" * 70)
    print("LIVE BYBIT - JOURNAL RECONCILIATION REPORT")
    print("=" * 70)
    print(f"Execution ID: {report.execution_id}")
    print(f"Timestamp: {report.timestamp_utc}")
    print(f"Period: {report.period_start} to {report.period_end}")
    print("-" * 70)

    print("\n📊 RAW COUNTS")
    print(f"  Bybit executions:   {report.bybit_trade_count}")
    print(f"  Journal entries:    {report.journal_trade_count}")
    print(f"  Matched:            {report.matched_count} ✓")
    print(f"  Mismatched:         {report.mismatched_count}")
    print(f"  Missing in Journal: {len(report.missing_in_journal)}")
    print(f"  Missing in Bybit:   {len(report.missing_in_bybit)}")

    print("\n💰 PnL ANALYSIS (Bybit Truth)")
    print(f"  Total Closed PnL:   ${report.bybit_total_closed_pnl:,.4f}")
    print(f"  Total Fees:         ${report.bybit_total_fees:,.4f}")
    print(f"  Net PnL:            ${report.bybit_net_pnl:,.4f}")

    print("\n💰 PnL ANALYSIS (Journal)")
    print(f"  Total Realized PnL: ${report.journal_total_realized_pnl:,.4f}")
    print(f"  Total Fees:         ${report.journal_total_fees:,.4f}")
    print(f"  Net PnL:            ${report.journal_net_pnl:,.4f}")

    print(f"\n  PnL Difference:     ${report.pnl_diff:,.4f}")

    print("\n📈 TRADE ANALYSIS")
    print(f"  Profitable trades:  {report.profitable_trades}")
    print(f"  Losing trades:      {report.losing_trades}")
    print(f"  Breakeven trades:   {report.breakeven_trades}")

    # The critical answer
    print("\n" + "=" * 70)
    print("🎯 CRITICAL QUESTION: Are all trades net negative?")
    print("=" * 70)
    if report.all_trades_net_negative:
        print("  ✅ YES - All trades are net negative (or breakeven)")
        print(
            f"     No profitable trades detected out of {report.profitable_trades + report.losing_trades + report.breakeven_trades} total"
        )
    else:
        print("  ❌ NO - Profitable trades detected!")
        print(f"     {report.profitable_trades} trades were net positive")
    print("=" * 70)

    if report.sample_trades:
        print("\n📋 SAMPLE TRADES (showing up to 5)")
        print("-" * 70)
        for i, t in enumerate(report.sample_trades[:5], 1):
            profit_icon = "📈" if t["is_profitable"] else "📉"
            print(f"\n  {i}. {profit_icon} Order: {t['order_id']}")
            print(f"     Exec ID: {t['exec_id']}")
            print(f"     Symbol: {t['symbol']}, Side: {t['side']}")
            print(f"     Time: {t['exec_time']}")
            print(
                f"     Bybit:  Price=${t['bybit_price']:.2f}, Qty={t['bybit_qty']:.4f}, Fee=${t['bybit_fee']:.4f}"
            )
            print(
                f"             Closed PnL=${t['bybit_closed_pnl']:.4f}, Net=${t['bybit_net_pnl']:.4f}"
            )
            if t["journal_price"]:
                print(
                    f"     Journal: Price=${t['journal_price']:.2f}, Qty={t['journal_qty']:.4f}, Fee=${t['journal_fee']:.4f}"
                )
                print(
                    f"              Realized PnL=${t['journal_realized_pnl']:.4f}, Net=${t['journal_net_pnl']:.4f}"
                )
            print(
                f"     Diff: Price={t['price_diff_pct']:.4f}%, Qty={t['qty_diff_pct']:.4f}%, PnL=${t['pnl_diff']:.4f}"
            )

    if report.mismatches:
        print("\n⚠️  MISMATCHES")
        print("-" * 70)
        for i, mm in enumerate(report.mismatches[:5], 1):
            print(f"\n  {i}. Order: {mm['order_id']}")
            print(f"     Exec ID: {mm['exec_id']}, Entry ID: {mm['entry_id']}")
            print(f"     Symbol: {mm['symbol']}")
            print(f"     Price diff: {mm['price_diff_pct']:.4f}%")
            print(f"     Qty diff: {mm['qty_diff_pct']:.4f}%")
            print(f"     PnL diff: ${mm['pnl_diff']:.4f}")

    print("\n" + "=" * 70)


def generate_markdown_report(report: LiveReconciliationReport) -> str:
    """Generate Markdown report."""
    lines = [
        "# Live Bybit - Journal Reconciliation Report",
        "",
        "## Metadata",
        f"- **Execution ID**: {report.execution_id}",
        f"- **Timestamp**: {report.timestamp_utc}",
        f"- **Period**: {report.period_start} to {report.period_end}",
        "",
        "## Raw Counts",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Bybit executions | {report.bybit_trade_count} |",
        f"| Journal entries | {report.journal_trade_count} |",
        f"| Matched | {report.matched_count} ✓ |",
        f"| Mismatched | {report.mismatched_count} |",
        f"| Missing in Journal | {len(report.missing_in_journal)} |",
        f"| Missing in Bybit | {len(report.missing_in_bybit)} |",
        "",
        "## PnL Analysis (Bybit Truth)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Closed PnL | ${report.bybit_total_closed_pnl:,.4f} |",
        f"| Total Fees | ${report.bybit_total_fees:,.4f} |",
        f"| **Net PnL** | **${report.bybit_net_pnl:,.4f}** |",
        "",
        "## PnL Analysis (Journal)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Realized PnL | ${report.journal_total_realized_pnl:,.4f} |",
        f"| Total Fees | ${report.journal_total_fees:,.4f} |",
        f"| **Net PnL** | **${report.journal_net_pnl:,.4f}** |",
        "",
        f"**PnL Difference**: ${report.pnl_diff:,.4f}",
        "",
        "## Trade Analysis",
        "",
        "| Category | Count |",
        "|----------|-------|",
        f"| Profitable trades | {report.profitable_trades} |",
        f"| Losing trades | {report.losing_trades} |",
        f"| Breakeven trades | {report.breakeven_trades} |",
        "",
        "## 🎯 Critical Question: Are all trades net negative?",
        "",
    ]

    if report.all_trades_net_negative:
        lines.extend(
            [
                "**✅ YES** - All trades are net negative (or breakeven)",
                "",
                f"No profitable trades detected out of {report.profitable_trades + report.losing_trades + report.breakeven_trades} total trades.",
            ]
        )
    else:
        lines.extend(
            [
                "**❌ NO** - Profitable trades detected!",
                "",
                f"{report.profitable_trades} trades were net positive.",
            ]
        )

    lines.append("")

    if report.sample_trades:
        lines.extend(
            [
                "## Sample Trades",
                "",
                "| # | Order ID | Exec ID | Symbol | Side | Bybit Net PnL | Journal Net PnL | Profitable? |",
                "|---|----------|---------|--------|------|---------------|-----------------|-------------|",
            ]
        )
        for i, t in enumerate(report.sample_trades[:10], 1):
            profitable = "✅ Yes" if t["is_profitable"] else "❌ No"
            lines.append(
                f"| {i} | {t['order_id'][:20]}... | {t['exec_id'][:15]}... | "
                f"{t['symbol']} | {t['side']} | ${t['bybit_net_pnl']:.4f} | "
                f"${t['journal_net_pnl']:.4f} | {profitable} |"
            )
        lines.append("")

    if report.mismatches:
        lines.extend(
            [
                "## Mismatches",
                "",
                "| # | Order ID | Symbol | Price Diff % | Qty Diff % | PnL Diff |",
                "|---|----------|--------|--------------|------------|----------|",
            ]
        )
        for i, mm in enumerate(report.mismatches[:10], 1):
            lines.append(
                f"| {i} | {mm['order_id'][:20]}... | {mm['symbol']} | "
                f"{mm['price_diff_pct']:.4f}% | {mm['qty_diff_pct']:.4f}% | ${mm['pnl_diff']:.4f} |"
            )
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "*Generated by live_reconcile.py*",
        ]
    )

    return "\n".join(lines)


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Live reconciliation between Bybit API and Redis journal"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="/tmp/live-recon.json",
        help="Output file for JSON report (default: /tmp/live-recon.json)",
    )
    parser.add_argument(
        "--redis-host",
        type=str,
        default=os.getenv("REDIS_HOST", "host.docker.internal"),
        help="Redis host",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=int(os.getenv("REDIS_PORT", "6380")),
        help="Redis port",
    )
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=0.1,
        help="Tolerance percentage for comparisons (default: 0.1)",
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
        reconciler = LiveReconciler(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            tolerance_pct=args.tolerance_pct,
        )

        report = await reconciler.reconcile(days=args.days)

        # Print to console
        print_live_report(report)

        # Write JSON output
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\n📄 JSON report written to: {output_path}")

        # Write Markdown output
        md_path = output_path.with_suffix(".md")
        with open(md_path, "w") as f:
            f.write(generate_markdown_report(report))
        print(f"📄 Markdown report written to: {md_path}")

        return 0

    except Exception as e:
        logger.error(f"Live reconciliation failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
