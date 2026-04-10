"""Tests for Bybit-Journal reconciliation script.

Tests the reconciliation logic with mock Bybit API responses and Redis data.

For ST-KPI-FIX-001: Bybit-Journal Reconciliation
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.validation.reconcile_bybit_journal import (
    BybitExecution,
    BybitJournalReconciler,
    JournalEntry,
    ReconciliationReport,
    main,
    print_report,
)


class TestBybitExecution:
    """Tests for BybitExecution dataclass."""

    def test_creation(self):
        """Test creating a BybitExecution."""
        exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=1700000000000,
            exec_id="exec456",
        )

        assert exec.order_id == "order123"
        assert exec.symbol == "BTCUSDT"
        assert exec.side == "Buy"
        assert exec.exec_price == 50000.0
        assert exec.exec_qty == 0.5
        assert exec.exec_fee == 2.5
        assert exec.exec_time == 1700000000000
        assert exec.exec_id == "exec456"

    def test_exec_datetime(self):
        """Test exec_datetime property."""
        exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=1700000000000,  # 2023-11-14 22:13:20 UTC
            exec_id="exec456",
        )

        dt = exec.exec_datetime
        assert dt.year == 2023
        assert dt.month == 11
        assert dt.day == 14


class TestJournalEntry:
    """Tests for JournalEntry dataclass."""

    def test_creation(self):
        """Test creating a JournalEntry."""
        entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[{"fill_id": "fill1", "price": 50000.0, "quantity": 0.5, "fee": 2.5}],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        assert entry.entry_id == "entry123"
        assert entry.symbol == "BTCUSDT"
        assert entry.side == "buy"
        assert len(entry.fills) == 1
        assert entry.realized_pnl == 100.0
        assert entry.fees == 2.5

    def test_total_qty(self):
        """Test total quantity calculation."""
        entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[
                {"fill_id": "fill1", "price": 50000.0, "quantity": 0.5, "fee": 2.5},
                {"fill_id": "fill2", "price": 50100.0, "quantity": 0.3, "fee": 1.5},
            ],
            realized_pnl=100.0,
            fees=4.0,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        assert entry.total_qty == 0.8

    def test_avg_fill_price(self):
        """Test average fill price calculation."""
        entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[
                {"fill_id": "fill1", "price": 50000.0, "quantity": 0.5, "fee": 2.5},
                {"fill_id": "fill2", "price": 50200.0, "quantity": 0.5, "fee": 2.5},
            ],
            realized_pnl=100.0,
            fees=5.0,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        # Weighted average: (50000*0.5 + 50200*0.5) / 1.0 = 50100
        assert entry.avg_fill_price == 50100.0

    def test_avg_fill_price_empty(self):
        """Test average fill price with no fills."""
        entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[],
            realized_pnl=100.0,
            fees=0.0,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        assert entry.avg_fill_price is None


class TestBybitJournalReconciler:
    """Tests for BybitJournalReconciler."""

    @pytest.fixture
    def reconciler(self):
        """Create a reconciler instance."""
        return BybitJournalReconciler(
            redis_host="localhost",
            redis_port=6380,
            tolerance_pct=0.1,
            tolerance_pnl=0.01,
        )

    def test_initialization(self, reconciler):
        """Test reconciler initialization."""
        assert reconciler.redis_host == "localhost"
        assert reconciler.redis_port == 6380
        assert reconciler.tolerance_pct == 0.1
        assert reconciler.tolerance_pnl == 0.01

    def test_is_match_success(self, reconciler):
        """Test successful match detection."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        assert reconciler._is_match(bybit_exec, journal_entry) is True

    def test_is_match_symbol_mismatch(self, reconciler):
        """Test match failure due to symbol mismatch."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="ETHUSDT",  # Different symbol
            side="buy",
            fills=[],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        assert reconciler._is_match(bybit_exec, journal_entry) is False

    def test_is_match_side_mismatch(self, reconciler):
        """Test match failure due to side mismatch."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="sell",  # Different side
            fills=[],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        assert reconciler._is_match(bybit_exec, journal_entry) is False

    def test_is_match_time_mismatch(self, reconciler):
        """Test match failure due to time mismatch."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC) - timedelta(hours=1),  # Too old
            signal_id="signal456",
        )

        assert reconciler._is_match(bybit_exec, journal_entry) is False

    def test_validate_match_perfect(self, reconciler):
        """Test validation with perfect match."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[{"fill_id": "fill1", "price": 50000.0, "quantity": 0.5, "fee": 2.5}],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        mismatches = reconciler._validate_match(bybit_exec, journal_entry)
        assert len(mismatches) == 0

    def test_validate_match_price_mismatch(self, reconciler):
        """Test validation with price mismatch exceeding tolerance."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[
                {
                    "fill_id": "fill1",
                    "price": 50500.0,
                    "quantity": 0.5,
                    "fee": 2.5,
                }  # 1% diff
            ],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        mismatches = reconciler._validate_match(bybit_exec, journal_entry)
        assert len(mismatches) == 1
        assert mismatches[0].match_type == "price"
        assert mismatches[0].pct_diff == 1.0  # 1% difference

    def test_validate_match_qty_mismatch(self, reconciler):
        """Test validation with quantity mismatch."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[
                {
                    "fill_id": "fill1",
                    "price": 50000.0,
                    "quantity": 0.6,
                    "fee": 2.5,
                }  # 20% diff
            ],
            realized_pnl=100.0,
            fees=2.5,
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        mismatches = reconciler._validate_match(bybit_exec, journal_entry)
        assert len(mismatches) == 1
        assert mismatches[0].match_type == "quantity"

    def test_validate_match_fee_mismatch(self, reconciler):
        """Test validation with fee mismatch."""
        bybit_exec = BybitExecution(
            order_id="order123",
            symbol="BTCUSDT",
            side="Buy",
            exec_price=50000.0,
            exec_qty=0.5,
            exec_fee=2.5,
            exec_time=int(datetime.now(UTC).timestamp() * 1000),
            exec_id="exec456",
        )

        journal_entry = JournalEntry(
            entry_id="entry123",
            symbol="BTCUSDT",
            side="buy",
            fills=[{"fill_id": "fill1", "price": 50000.0, "quantity": 0.5, "fee": 0.1}],
            realized_pnl=100.0,
            fees=0.1,  # Different fee
            entry_time=datetime.now(UTC),
            signal_id="signal456",
        )

        mismatches = reconciler._validate_match(bybit_exec, journal_entry)
        assert len(mismatches) == 1
        assert mismatches[0].match_type == "fee"
        assert mismatches[0].diff == 2.4  # 2.5 - 0.1

    def test_pct_diff(self, reconciler):
        """Test percentage difference calculation."""
        assert reconciler._pct_diff(100.0, 100.0) == 0.0
        assert reconciler._pct_diff(100.0, 90.0) == 10.0
        assert reconciler._pct_diff(100.0, 110.0) == 10.0
        assert reconciler._pct_diff(0.0, 0.0) == 0.0
        assert reconciler._pct_diff(0.0, 100.0) == 100.0


class TestCompareExecutions:
    """Tests for the compare_executions method."""

    @pytest.fixture
    def reconciler(self):
        """Create a reconciler instance."""
        return BybitJournalReconciler(
            redis_host="localhost",
            redis_port=6380,
            tolerance_pct=0.5,  # 0.5% tolerance
            tolerance_pnl=0.01,
            tolerance_qty=0.5,
        )

    def test_compare_all_match(self, reconciler):
        """Test comparison when all trades match."""
        now = datetime.now(UTC)
        now_ms = int(now.timestamp() * 1000)

        bybit_execs = [
            BybitExecution(
                order_id="order1",
                symbol="BTCUSDT",
                side="Buy",
                exec_price=50000.0,
                exec_qty=0.5,
                exec_fee=2.5,
                exec_time=now_ms,
                exec_id="exec1",
            ),
        ]

        journal_entries = [
            JournalEntry(
                entry_id="entry1",
                symbol="BTCUSDT",
                side="buy",
                fills=[
                    {"fill_id": "order1", "price": 50000.0, "quantity": 0.5, "fee": 2.5}
                ],
                realized_pnl=-2.5,  # Match Bybit fees for PnL reconciliation
                fees=2.5,
                entry_time=now,
                signal_id="signal1",
            ),
        ]

        report = reconciler.compare_executions(bybit_execs, journal_entries)

        assert report.bybit_trade_count == 1
        assert report.journal_trade_count == 1
        assert report.matched_count == 1
        assert report.mismatched_count == 0
        assert len(report.missing_in_journal) == 0
        assert len(report.missing_in_bybit) == 0
        assert (
            report.pnl_diff <= reconciler.tolerance_pnl
        )  # PnL should be within tolerance
        assert report.overall_passed is True

    def test_compare_missing_in_journal(self, reconciler):
        """Test comparison with trades missing in journal."""
        now = datetime.now(UTC)
        now_ms = int(now.timestamp() * 1000)

        bybit_execs = [
            BybitExecution(
                order_id="order1",
                symbol="BTCUSDT",
                side="Buy",
                exec_price=50000.0,
                exec_qty=0.5,
                exec_fee=2.5,
                exec_time=now_ms,
                exec_id="exec1",
            ),
        ]

        journal_entries = []  # No journal entries

        report = reconciler.compare_executions(bybit_execs, journal_entries)

        assert report.bybit_trade_count == 1
        assert report.journal_trade_count == 0
        assert report.matched_count == 0
        assert len(report.missing_in_journal) == 1
        # exec_id is reported as missing since it's the most precise identifier
        assert report.missing_in_journal[0] == "exec1"
        assert report.overall_passed is False  # Fail-closed

    def test_compare_missing_in_bybit(self, reconciler):
        """Test comparison with trades missing in Bybit."""
        now = datetime.now(UTC)

        bybit_execs = []  # No Bybit executions

        journal_entries = [
            JournalEntry(
                entry_id="entry1",
                symbol="BTCUSDT",
                side="buy",
                fills=[],
                realized_pnl=100.0,
                fees=2.5,
                entry_time=now,
                signal_id="signal1",
            ),
        ]

        report = reconciler.compare_executions(bybit_execs, journal_entries)

        assert report.bybit_trade_count == 0
        assert report.journal_trade_count == 1
        assert report.matched_count == 0
        assert len(report.missing_in_bybit) == 1
        assert report.missing_in_bybit[0] == "entry1"

    def test_compare_mismatch_detected(self, reconciler):
        """Test comparison with mismatched trade data."""
        now = datetime.now(UTC)
        now_ms = int(now.timestamp() * 1000)

        bybit_execs = [
            BybitExecution(
                order_id="order1",
                symbol="BTCUSDT",
                side="Buy",
                exec_price=50000.0,
                exec_qty=0.5,
                exec_fee=2.5,
                exec_time=now_ms,
                exec_id="exec1",
            ),
        ]

        journal_entries = [
            JournalEntry(
                entry_id="entry1",
                symbol="BTCUSDT",
                side="buy",
                fills=[
                    {
                        "fill_id": "order1",
                        "price": 60000.0,
                        "quantity": 0.5,
                        "fee": 2.5,
                    }  # 20% price diff
                ],
                realized_pnl=100.0,
                fees=2.5,
                entry_time=now,
                signal_id="signal1",
            ),
        ]

        report = reconciler.compare_executions(bybit_execs, journal_entries)

        assert report.bybit_trade_count == 1
        assert report.journal_trade_count == 1
        assert report.matched_count == 0
        assert report.mismatched_count == 1
        assert len(report.mismatches) == 1
        assert report.mismatches[0]["type"] == "price"
        assert report.overall_passed is False  # Fail-closed


class TestFetchMethods:
    """Tests for fetch methods with mocking."""

    @pytest.fixture
    def reconciler(self):
        """Create a reconciler instance."""
        return BybitJournalReconciler(
            redis_host="localhost",
            redis_port=6380,
        )

    @pytest.mark.asyncio
    async def test_fetch_journal_entries(self, reconciler):
        """Test fetching journal entries with mocked Redis."""
        now = datetime.now(UTC)
        entry_data = {
            "entry_id": "entry1",
            "symbol": "BTCUSDT",
            "side": "buy",
            "fills": [
                {"fill_id": "fill1", "price": 50000.0, "quantity": 0.5, "fee": 2.5}
            ],
            "realized_pnl": 100.0,
            "fees": 2.5,
            "entry_time": now.isoformat(),
            "signal_id": "signal1",
        }

        with patch.object(reconciler, "_get_redis") as mock_get_redis:
            mock_redis = MagicMock()
            mock_redis.smembers.return_value = {"session1"}
            mock_redis.lrange.return_value = ["entry1"]
            mock_redis.hget.return_value = json.dumps(entry_data)
            mock_get_redis.return_value = mock_redis

            entries = await reconciler.fetch_journal_entries(days=7)

            assert len(entries) == 1
            assert entries[0].entry_id == "entry1"
            assert entries[0].symbol == "BTCUSDT"


class TestMain:
    """Tests for main CLI function."""

    @pytest.mark.asyncio
    async def test_main_success(self):
        """Test main function with successful reconciliation."""
        with patch(
            "scripts.validation.reconcile_bybit_journal.BybitJournalReconciler"
        ) as MockReconciler:
            mock_reconciler = MagicMock()
            # Create a proper mock report with all required fields
            mock_report = MagicMock()
            mock_report.execution_id = "test123"
            mock_report.timestamp_utc = "2024-01-01T00:00:00+00:00"
            mock_report.period_start = "2024-01-01T00:00:00+00:00"
            mock_report.period_end = "2024-01-01T00:00:00+00:00"
            mock_report.bybit_trade_count = 1
            mock_report.journal_trade_count = 1
            mock_report.matched_count = 1
            mock_report.mismatched_count = 0
            mock_report.critical_mismatches = 0
            mock_report.missing_in_journal = []
            mock_report.missing_in_bybit = []
            mock_report.mismatches = []
            mock_report.matched = []
            mock_report.tolerance_pct = 0.1
            mock_report.tolerance_pnl = 0.01
            mock_report.overall_passed = True
            mock_report.bybit_total_pnl = 0.0
            mock_report.journal_total_pnl = 0.0
            mock_report.pnl_diff = 0.0
            mock_report.to_dict.return_value = {"overall_passed": True}
            mock_reconciler.reconcile = AsyncMock(return_value=mock_report)
            MockReconciler.return_value = mock_reconciler

            # Mock sys.argv
            with patch.object(
                sys, "argv", ["reconcile_bybit_journal.py", "--days", "1"]
            ):
                exit_code = await main()

            assert exit_code == 0

    @pytest.mark.asyncio
    async def test_main_failure(self):
        """Test main function with failed reconciliation."""
        with patch(
            "scripts.validation.reconcile_bybit_journal.BybitJournalReconciler"
        ) as MockReconciler:
            mock_reconciler = MagicMock()
            mock_report = MagicMock()
            mock_report.execution_id = "test123"
            mock_report.timestamp_utc = "2024-01-01T00:00:00+00:00"
            mock_report.period_start = "2024-01-01T00:00:00+00:00"
            mock_report.period_end = "2024-01-01T00:00:00+00:00"
            mock_report.bybit_trade_count = 1
            mock_report.journal_trade_count = 1
            mock_report.matched_count = 0
            mock_report.mismatched_count = 1
            mock_report.critical_mismatches = 0
            mock_report.missing_in_journal = ["order1"]
            mock_report.missing_in_bybit = []
            # Include all required fields for mismatches
            mock_report.mismatches = [
                {
                    "order_id": "order1",
                    "entry_id": "entry1",
                    "type": "price",
                    "bybit_value": 50000.0,
                    "journal_value": 50500.0,
                    "diff": 500.0,
                    "pct_diff": 1.0,
                    "tolerance": 0.1,
                    "within_tolerance": False,
                }
            ]
            mock_report.matched = []
            mock_report.tolerance_pct = 0.1
            mock_report.tolerance_pnl = 0.01
            mock_report.overall_passed = False
            mock_report.bybit_total_pnl = 0.0
            mock_report.journal_total_pnl = 0.0
            mock_report.pnl_diff = 0.0
            mock_report.to_dict.return_value = {"overall_passed": False}
            mock_reconciler.reconcile = AsyncMock(return_value=mock_report)
            MockReconciler.return_value = mock_reconciler

            with patch.object(
                sys, "argv", ["reconcile_bybit_journal.py", "--days", "1"]
            ):
                exit_code = await main()

            assert exit_code == 3  # Missing trades detected

    @pytest.mark.asyncio
    async def test_main_error(self):
        """Test main function with error."""
        with patch(
            "scripts.validation.reconcile_bybit_journal.BybitJournalReconciler"
        ) as MockReconciler:
            mock_reconciler = MagicMock()
            mock_reconciler.reconcile = AsyncMock(
                side_effect=Exception("Connection error")
            )
            MockReconciler.return_value = mock_reconciler

            with patch.object(
                sys, "argv", ["reconcile_bybit_journal.py", "--days", "1"]
            ):
                exit_code = await main()

            assert exit_code == 4  # Error exit code


class TestPrintReport:
    """Tests for print_report function."""

    def test_print_report_passed(self, capsys):
        """Test printing a passed report."""
        report = ReconciliationReport(
            execution_id="test123",
            timestamp_utc="2024-01-01T00:00:00+00:00",
            period_start="2024-01-01T00:00:00+00:00",
            period_end="2024-01-01T23:59:59+00:00",
            bybit_trade_count=10,
            journal_trade_count=10,
            matched_count=10,
            mismatched_count=0,
            critical_mismatches=0,
            missing_in_journal=[],
            missing_in_bybit=[],
            mismatches=[],
            matched=[],
            tolerance_pct=0.1,
            tolerance_pnl=0.01,
            overall_passed=True,
            bybit_total_pnl=0.0,
            journal_total_pnl=0.0,
            pnl_diff=0.0,
        )

        print_report(report)
        captured = capsys.readouterr()

        assert "BYBIT - JOURNAL RECONCILIATION REPORT" in captured.out
        assert "PASSED" in captured.out
        assert "Bybit trades:" in captured.out
        assert "Journal entries:" in captured.out

    def test_print_report_failed(self, capsys):
        """Test printing a failed report with mismatches."""
        report = ReconciliationReport(
            execution_id="test123",
            timestamp_utc="2024-01-01T00:00:00+00:00",
            period_start="2024-01-01T00:00:00+00:00",
            period_end="2024-01-01T23:59:59+00:00",
            bybit_trade_count=10,
            journal_trade_count=9,
            matched_count=8,
            mismatched_count=1,
            missing_in_journal=["order1"],
            missing_in_bybit=[],
            mismatches=[
                {
                    "order_id": "order2",
                    "entry_id": "entry2",
                    "type": "price",
                    "bybit_value": 50000.0,
                    "journal_value": 50500.0,
                    "diff": 500.0,
                    "pct_diff": 1.0,
                    "tolerance": 0.1,
                }
            ],
            matched=[],
            tolerance_pct=0.1,
            tolerance_pnl=0.01,
            overall_passed=False,
        )

        print_report(report)
        captured = capsys.readouterr()

        assert "FAILED" in captured.out
        assert "MISMATCHES DETECTED" in captured.out
        assert "MISSING IN JOURNAL" in captured.out

    def test_print_report_with_matched(self, capsys):
        """Test printing report with matched trades."""
        report = ReconciliationReport(
            execution_id="test123",
            timestamp_utc="2024-01-01T00:00:00+00:00",
            period_start="2024-01-01T00:00:00+00:00",
            period_end="2024-01-01T23:59:59+00:00",
            bybit_trade_count=2,
            journal_trade_count=2,
            matched_count=2,
            mismatched_count=0,
            missing_in_journal=[],
            missing_in_bybit=[],
            mismatches=[],
            matched=[
                {
                    "order_id": "order1",
                    "entry_id": "entry1",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "price_diff_pct": 0.01,
                    "qty_diff_pct": 0.0,
                    "fee_diff": 0.0,
                }
            ],
            tolerance_pct=0.1,
            tolerance_pnl=0.01,
            overall_passed=True,
        )

        print_report(report)
        captured = capsys.readouterr()

        assert "MATCHED TRADES" in captured.out
        assert "order1" in captured.out
        assert "BTCUSDT" in captured.out


class TestReconciliationReport:
    """Tests for ReconciliationReport dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        report = ReconciliationReport(
            execution_id="test123",
            bybit_trade_count=10,
            journal_trade_count=10,
            overall_passed=True,
        )

        data = report.to_dict()

        assert data["execution_id"] == "test123"
        assert data["bybit_trade_count"] == 10
        assert data["journal_trade_count"] == 10
        assert data["overall_passed"] is True
        assert "mismatches" in data
        assert "matched" in data

    def test_default_values(self):
        """Test default values are set correctly."""
        report = ReconciliationReport()

        assert len(report.execution_id) == 8  # UUID short form
        assert report.timestamp_utc is not None
        assert report.mismatches == []
        assert report.matched == []
        assert report.missing_in_journal == []
        assert report.missing_in_bybit == []
