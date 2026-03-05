"""Tests for trade journal query functionality.

For ST-JOURNAL-QUERY-001: Trade Journal Query/Reporting Surface
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.execution.paper.trade_journal import ExitReason, FillRecord, TradeJournalEntry
from src.execution.paper.trade_journal_query import (
    JournalQueryFilters,
    JournalSummaryStats,
    TradeJournalQuery,
)


class TestJournalQueryFilters:
    """Test JournalQueryFilters dataclass."""

    def test_default_values(self):
        """Test that all filter fields default to None."""
        filters = JournalQueryFilters()
        assert filters.start_time is None
        assert filters.end_time is None
        assert filters.symbol is None
        assert filters.status is None
        assert filters.exit_reason is None
        assert filters.strategy is None

    def test_custom_values(self):
        """Test setting custom filter values."""
        start = datetime.now(UTC)
        end = start + timedelta(hours=1)
        filters = JournalQueryFilters(
            start_time=start,
            end_time=end,
            symbol="BTCUSDT",
            status="closed",
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            strategy="momentum",
        )
        assert filters.start_time == start
        assert filters.end_time == end
        assert filters.symbol == "BTCUSDT"
        assert filters.status == "closed"
        assert filters.exit_reason == ExitReason.TAKE_PROFIT_HIT
        assert filters.strategy == "momentum"


class TestJournalSummaryStats:
    """Test JournalSummaryStats dataclass."""

    def test_stats_creation(self):
        """Test creating summary stats with all fields."""
        stats = JournalSummaryStats(
            total_trades=10,
            open_trades=2,
            closed_trades=8,
            total_pnl=1000.0,
            winning_trades=5,
            losing_trades=3,
            win_rate=0.625,
            avg_pnl=125.0,
            avg_win=300.0,
            avg_loss=-100.0,
            max_win=500.0,
            max_loss=-200.0,
        )
        assert stats.total_trades == 10
        assert stats.open_trades == 2
        assert stats.closed_trades == 8
        assert stats.total_pnl == 1000.0
        assert stats.winning_trades == 5
        assert stats.losing_trades == 3
        assert stats.win_rate == 0.625
        assert stats.avg_pnl == 125.0
        assert stats.avg_win == 300.0
        assert stats.avg_loss == -100.0
        assert stats.max_win == 500.0
        assert stats.max_loss == -200.0


class TestTradeJournalQuery:
    """Test TradeJournalQuery class."""

    @pytest.fixture
    def sample_entries(self):
        """Create sample journal entries for testing."""
        now = datetime.now(UTC)

        # Entry 1: Open BTC buy
        entry1 = TradeJournalEntry(
            entry_id="entry-1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=now - timedelta(hours=2),
            position_size=0.1,
            signal_id="signal-1",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        # Entry 2: Closed BTC sell (win)
        entry2 = TradeJournalEntry(
            entry_id="entry-2",
            symbol="BTCUSDT",
            side="sell",
            entry_price=51000.0,
            entry_time=now - timedelta(hours=4),
            position_size=0.1,
            signal_id="signal-2",
            signal_confidence=0.75,
            signal_strategy="mean_reversion",
        )
        entry2.close(
            exit_price=50500.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            realized_pnl=500.0,
        )
        entry2.fees = 10.0  # net_pnl = 490.0

        # Entry 3: Closed ETH buy (loss)
        entry3 = TradeJournalEntry(
            entry_id="entry-3",
            symbol="ETHUSDT",
            side="buy",
            entry_price=3000.0,
            entry_time=now - timedelta(hours=6),
            position_size=1.0,
            signal_id="signal-3",
            signal_confidence=0.65,
            signal_strategy="momentum",
        )
        entry3.close(
            exit_price=2900.0,
            exit_reason=ExitReason.STOP_LOSS_HIT,
            realized_pnl=-100.0,
        )
        entry3.fees = 5.0  # net_pnl = -105.0

        # Entry 4: Closed BTC buy (win)
        entry4 = TradeJournalEntry(
            entry_id="entry-4",
            symbol="BTCUSDT",
            side="buy",
            entry_price=48000.0,
            entry_time=now - timedelta(hours=8),
            position_size=0.2,
            signal_id="signal-4",
            signal_confidence=0.90,
            signal_strategy="momentum",
        )
        entry4.close(
            exit_price=49000.0,
            exit_reason=ExitReason.SIGNAL_REVERSE,
            realized_pnl=200.0,
        )
        entry4.fees = 8.0  # net_pnl = 192.0

        return [entry1, entry2, entry3, entry4]

    @pytest.fixture
    def query(self, sample_entries):
        """Create a TradeJournalQuery with sample entries."""
        return TradeJournalQuery(sample_entries)

    def test_init(self, sample_entries):
        """Test TradeJournalQuery initialization."""
        query = TradeJournalQuery(sample_entries)
        assert query._entries == sample_entries

    def test_query_no_filters(self, query):
        """Test querying without filters returns all entries."""
        results = query.query()
        assert len(results) == 4

    def test_query_with_none_filters(self, query):
        """Test querying with None filters returns all entries."""
        filters = JournalQueryFilters()
        results = query.query(filters)
        assert len(results) == 4

    def test_query_by_symbol(self, query):
        """Test filtering by symbol."""
        filters = JournalQueryFilters(symbol="BTCUSDT")
        results = query.query(filters)
        assert len(results) == 3
        assert all(e.symbol == "BTCUSDT" for e in results)

    def test_query_by_symbol_case_insensitive(self, query):
        """Test symbol filtering is case insensitive."""
        filters = JournalQueryFilters(symbol="btcusdt")
        results = query.query(filters)
        assert len(results) == 3

        filters = JournalQueryFilters(symbol="BTCusdt")
        results = query.query(filters)
        assert len(results) == 3

    def test_query_by_status_open(self, query):
        """Test filtering by open status."""
        filters = JournalQueryFilters(status="open")
        results = query.query(filters)
        assert len(results) == 1
        assert all(e.is_open for e in results)

    def test_query_by_status_closed(self, query):
        """Test filtering by closed status."""
        filters = JournalQueryFilters(status="closed")
        results = query.query(filters)
        assert len(results) == 3
        assert all(e.is_closed for e in results)

    def test_query_by_status_case_insensitive(self, query):
        """Test status filtering is case insensitive."""
        filters = JournalQueryFilters(status="OPEN")
        results = query.query(filters)
        assert len(results) == 1

        filters = JournalQueryFilters(status="Closed")
        results = query.query(filters)
        assert len(results) == 3

    def test_query_by_strategy(self, query):
        """Test filtering by strategy."""
        filters = JournalQueryFilters(strategy="momentum")
        results = query.query(filters)
        assert len(results) == 3
        assert all(e.signal_strategy == "momentum" for e in results)

    def test_query_by_exit_reason(self, query):
        """Test filtering by exit reason."""
        filters = JournalQueryFilters(exit_reason=ExitReason.TAKE_PROFIT_HIT)
        results = query.query(filters)
        assert len(results) == 1
        assert all(e.exit_reason == ExitReason.TAKE_PROFIT_HIT for e in results)

    def test_query_by_time_range_start(self, query, sample_entries):
        """Test filtering by start time."""
        now = datetime.now(UTC)
        filters = JournalQueryFilters(start_time=now - timedelta(hours=3))
        results = query.query(filters)
        # Should include entries with entry_time >= start_time or exit_time >= start_time
        assert len(results) >= 1

    def test_query_by_time_range_end(self, query, sample_entries):
        """Test filtering by end time."""
        now = datetime.now(UTC)
        filters = JournalQueryFilters(end_time=now - timedelta(hours=3))
        results = query.query(filters)
        # Should include entries with entry_time <= end_time or exit_time <= end_time
        assert len(results) >= 1

    def test_query_combined_filters(self, query):
        """Test combining multiple filters."""
        filters = JournalQueryFilters(
            symbol="BTCUSDT",
            status="closed",
            strategy="momentum",
        )
        results = query.query(filters)
        # Only entry-4 matches all three: BTCUSDT, closed, momentum
        # entry-2 is BTCUSDT and closed, but strategy is "mean_reversion"
        assert len(results) == 1
        for e in results:
            assert e.symbol == "BTCUSDT"
            assert e.is_closed
            assert e.signal_strategy == "momentum"

    def test_query_no_matches(self, query):
        """Test query that returns no matches."""
        filters = JournalQueryFilters(symbol="NONEXISTENT")
        results = query.query(filters)
        assert len(results) == 0


class TestTradeJournalQuerySummary:
    """Test summary statistics computation."""

    @pytest.fixture
    def mixed_entries(self):
        """Create entries with mixed PnL for summary testing."""
        now = datetime.now(UTC)

        # Winning trade
        entry1 = TradeJournalEntry(
            entry_id="win-1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=now - timedelta(hours=2),
            position_size=0.1,
            signal_id="signal-1",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )
        entry1.close(
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            realized_pnl=1000.0,
        )
        entry1.fees = 50.0  # net_pnl = 950.0

        # Losing trade
        entry2 = TradeJournalEntry(
            entry_id="loss-1",
            symbol="ETHUSDT",
            side="buy",
            entry_price=3000.0,
            entry_time=now - timedelta(hours=4),
            position_size=1.0,
            signal_id="signal-2",
            signal_confidence=0.75,
            signal_strategy="mean_reversion",
        )
        entry2.close(
            exit_price=2900.0,
            exit_reason=ExitReason.STOP_LOSS_HIT,
            realized_pnl=-100.0,
        )
        entry2.fees = 10.0  # net_pnl = -110.0

        # Another winning trade
        entry3 = TradeJournalEntry(
            entry_id="win-2",
            symbol="BTCUSDT",
            side="sell",
            entry_price=52000.0,
            entry_time=now - timedelta(hours=6),
            position_size=0.1,
            signal_id="signal-3",
            signal_confidence=0.80,
            signal_strategy="momentum",
        )
        entry3.close(
            exit_price=51000.0,
            exit_reason=ExitReason.SIGNAL_REVERSE,
            realized_pnl=1000.0,
        )
        entry3.fees = 50.0  # net_pnl = 950.0

        # Open trade (should not affect PnL stats)
        entry4 = TradeJournalEntry(
            entry_id="open-1",
            symbol="SOLUSDT",
            side="buy",
            entry_price=100.0,
            entry_time=now - timedelta(hours=1),
            position_size=10.0,
            signal_id="signal-4",
            signal_confidence=0.70,
            signal_strategy="breakout",
        )

        return [entry1, entry2, entry3, entry4]

    def test_summary_with_no_entries(self):
        """Test summary stats with empty entries list."""
        query = TradeJournalQuery([])
        stats = query.get_summary()

        assert stats.total_trades == 0
        assert stats.open_trades == 0
        assert stats.closed_trades == 0
        assert stats.total_pnl == 0.0
        assert stats.winning_trades == 0
        assert stats.losing_trades == 0
        assert stats.win_rate == 0.0
        assert stats.avg_pnl == 0.0
        assert stats.avg_win == 0.0
        assert stats.avg_loss == 0.0
        assert stats.max_win == 0.0
        assert stats.max_loss == 0.0

    def test_summary_accuracy(self, mixed_entries):
        """Test summary statistics are calculated correctly."""
        query = TradeJournalQuery(mixed_entries)
        stats = query.get_summary()

        # Total counts
        assert stats.total_trades == 4
        assert stats.open_trades == 1
        assert stats.closed_trades == 3

        # PnL calculations (net_pnl = realized_pnl - fees)
        # win-1: 1000 - 50 = 950
        # loss-1: -100 - 10 = -110
        # win-2: 1000 - 50 = 950
        # Total: 950 - 110 + 950 = 1790
        assert stats.total_pnl == 1790.0

        # Win/loss counts
        assert stats.winning_trades == 2
        assert stats.losing_trades == 1

        # Win rate: 2 wins / 3 closed = 66.67%
        assert stats.win_rate == pytest.approx(2 / 3, abs=0.01)

        # Average PnL: 1790 / 3 = 596.67
        assert stats.avg_pnl == pytest.approx(1790.0 / 3, abs=0.01)

        # Average win: (950 + 950) / 2 = 950
        assert stats.avg_win == 950.0

        # Average loss: -110 / 1 = -110
        assert stats.avg_loss == -110.0

        # Max win: 950
        assert stats.max_win == 950.0

        # Max loss: -110
        assert stats.max_loss == -110.0

    def test_summary_with_filters(self, mixed_entries):
        """Test summary with applied filters."""
        query = TradeJournalQuery(mixed_entries)

        # Filter to only BTC trades
        filters = JournalQueryFilters(symbol="BTCUSDT")
        stats = query.get_summary(filters)

        assert stats.total_trades == 2  # win-1 and win-2
        assert stats.closed_trades == 2
        assert stats.total_pnl == 1900.0  # 950 + 950
        assert stats.winning_trades == 2
        assert stats.losing_trades == 0
        assert stats.win_rate == 1.0

    def test_summary_only_open_trades(self, mixed_entries):
        """Test summary when filtering to only open trades."""
        query = TradeJournalQuery(mixed_entries)

        filters = JournalQueryFilters(status="open")
        stats = query.get_summary(filters)

        assert stats.total_trades == 1
        assert stats.open_trades == 1
        assert stats.closed_trades == 0
        # No PnL stats for open trades
        assert stats.total_pnl == 0.0
        assert stats.winning_trades == 0
        assert stats.losing_trades == 0


class TestTradeJournalQueryHelpers:
    """Test helper methods on TradeJournalQuery."""

    @pytest.fixture
    def diverse_entries(self):
        """Create entries with diverse symbols and strategies."""
        now = datetime.now(UTC)

        entries = []
        for i, (symbol, strategy) in enumerate(
            [
                ("BTCUSDT", "momentum"),
                ("ETHUSDT", "mean_reversion"),
                ("BTCUSDT", "breakout"),
                ("SOLUSDT", "momentum"),
                ("ETHUSDT", "momentum"),
            ]
        ):
            entry = TradeJournalEntry(
                entry_id=f"entry-{i}",
                symbol=symbol,
                side="buy",
                entry_price=100.0 * (i + 1),
                entry_time=now - timedelta(hours=i),
                position_size=1.0,
                signal_id=f"signal-{i}",
                signal_confidence=0.8,
                signal_strategy=strategy,
            )
            if i % 2 == 0:  # Close every other entry
                entry.close(
                    exit_price=entry.entry_price + 10,
                    exit_reason=ExitReason.TAKE_PROFIT_HIT,
                    realized_pnl=100.0,
                )
                entry.fees = 5.0
            entries.append(entry)

        return entries

    def test_get_symbols(self, diverse_entries):
        """Test getting unique symbols."""
        query = TradeJournalQuery(diverse_entries)
        symbols = query.get_symbols()

        assert symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_get_symbols_empty(self):
        """Test getting symbols with no entries."""
        query = TradeJournalQuery([])
        symbols = query.get_symbols()

        assert symbols == []

    def test_get_strategies(self, diverse_entries):
        """Test getting unique strategies."""
        query = TradeJournalQuery(diverse_entries)
        strategies = query.get_strategies()

        assert strategies == ["breakout", "mean_reversion", "momentum"]

    def test_get_strategies_empty(self):
        """Test getting strategies with no entries."""
        query = TradeJournalQuery([])
        strategies = query.get_strategies()

        assert strategies == []

    def test_get_exit_reasons(self, diverse_entries):
        """Test getting unique exit reasons."""
        query = TradeJournalQuery(diverse_entries)
        reasons = query.get_exit_reasons()

        assert len(reasons) == 1
        assert reasons[0] == ExitReason.TAKE_PROFIT_HIT

    def test_get_exit_reasons_empty(self):
        """Test getting exit reasons with no entries."""
        query = TradeJournalQuery([])
        reasons = query.get_exit_reasons()

        assert reasons == []

    def test_get_time_range(self, diverse_entries):
        """Test getting time range."""
        query = TradeJournalQuery(diverse_entries)
        start, end = query.get_time_range()

        assert start is not None
        assert end is not None
        assert start <= end

    def test_get_time_range_empty(self):
        """Test getting time range with no entries."""
        query = TradeJournalQuery([])
        start, end = query.get_time_range()

        assert start is None
        assert end is None

    def test_get_pnl_by_symbol(self, diverse_entries):
        """Test getting PnL grouped by symbol."""
        query = TradeJournalQuery(diverse_entries)
        pnl_by_symbol = query.get_pnl_by_symbol()

        # Closed entries are 0, 2, 4 (indices)
        # entry-0: BTCUSDT, net_pnl = 95
        # entry-2: BTCUSDT, net_pnl = 95
        # entry-4: ETHUSDT, net_pnl = 95
        assert "BTCUSDT" in pnl_by_symbol
        assert "ETHUSDT" in pnl_by_symbol
        assert pnl_by_symbol["BTCUSDT"] == 190.0  # 95 + 95
        assert pnl_by_symbol["ETHUSDT"] == 95.0

    def test_get_pnl_by_strategy(self, diverse_entries):
        """Test getting PnL grouped by strategy."""
        query = TradeJournalQuery(diverse_entries)
        pnl_by_strategy = query.get_pnl_by_strategy()

        # entry-0: momentum, net_pnl = 95
        # entry-2: breakout, net_pnl = 95
        # entry-4: momentum, net_pnl = 95
        assert "momentum" in pnl_by_strategy
        assert "breakout" in pnl_by_strategy
        assert pnl_by_strategy["momentum"] == 190.0  # 95 + 95
        assert pnl_by_strategy["breakout"] == 95.0

    def test_get_pnl_by_exit_reason(self, diverse_entries):
        """Test getting PnL grouped by exit reason."""
        query = TradeJournalQuery(diverse_entries)
        pnl_by_reason = query.get_pnl_by_exit_reason()

        assert ExitReason.TAKE_PROFIT_HIT in pnl_by_reason
        assert pnl_by_reason[ExitReason.TAKE_PROFIT_HIT] == 285.0  # 95 * 3

    def test_to_dict(self, diverse_entries):
        """Test converting query to dictionary."""
        query = TradeJournalQuery(diverse_entries)
        data = query.to_dict()

        assert data["entry_count"] == 5
        assert "BTCUSDT" in data["symbols"]
        assert "ETHUSDT" in data["symbols"]
        assert "SOLUSDT" in data["symbols"]
        assert "momentum" in data["strategies"]
        assert "time_range" in data
        assert "start" in data["time_range"]
        assert "end" in data["time_range"]

    def test_to_dict_empty(self):
        """Test converting empty query to dictionary."""
        query = TradeJournalQuery([])
        data = query.to_dict()

        assert data["entry_count"] == 0
        assert data["symbols"] == []
        assert data["strategies"] == []
        assert data["time_range"]["start"] is None
        assert data["time_range"]["end"] is None
