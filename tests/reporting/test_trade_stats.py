"""Tests for trade_stats.py"""

from datetime import datetime, timedelta
from decimal import Decimal

from src.reporting.core.trade_stats import (
    AggregatedTrade,
    TradeStatsAggregator,
    TradeStatsResult,
)


class TestTradeStatsAggregator:
    """Test suite for TradeStatsAggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.aggregator = TradeStatsAggregator()

    def test_initialization(self):
        """Test aggregator initializes"""
        assert self.aggregator is not None

    def test_add_trade(self):
        """Test adding a trade"""
        self.aggregator.add_trade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            entry_time=datetime.now(),
            exit_time=datetime.now(),
        )
        assert len(self.aggregator._trades) == 1

    def test_add_trades(self):
        """Test adding multiple trades"""
        trades = [
            ("T1", "AAPL", Decimal("100"), datetime.now(), datetime.now()),
            ("T2", "GOOG", Decimal("50"), datetime.now(), datetime.now()),
        ]
        self.aggregator.add_trades(trades)
        assert len(self.aggregator._trades) == 2

    def test_clear(self):
        """Test clearing trades"""
        self.aggregator.add_trade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            entry_time=datetime.now(),
            exit_time=datetime.now(),
        )
        self.aggregator.clear()
        assert len(self.aggregator._trades) == 0

    def test_calculate_stats(self):
        """Test calculating stats"""
        self.aggregator.add_trade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            entry_time=datetime.now(),
            exit_time=datetime.now(),
        )
        stats = self.aggregator.calculate_stats()
        assert isinstance(stats, TradeStatsResult)
        assert stats.total_trades == 1

    def test_calculate_stats_with_open_trade(self):
        """Test calculating stats with open trade"""
        self.aggregator.add_trade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            entry_time=datetime.now(),
            exit_time=datetime.now(),
        )
        self.aggregator.add_trade(
            trade_id="T2",
            symbol="GOOG",
            pnl=Decimal("50"),
            entry_time=datetime.now(),
            exit_time=None,  # Open trade
        )
        stats = self.aggregator.calculate_stats()
        assert stats.total_trades == 2
        assert stats.closed_trades == 1
        assert stats.open_trades == 1


class TestTradeStatsResult:
    """Test suite for TradeStatsResult"""

    def test_defaults(self):
        """Test default values"""
        result = TradeStatsResult()
        assert result.total_trades == 0
        assert result.total_pnl == Decimal("0")
        assert result.profit_factor == 0.0

    def test_with_values(self):
        """Test with actual values"""
        result = TradeStatsResult(
            total_trades=10,
            total_pnl=Decimal("1000"),
            profit_factor=1.5,
        )
        assert result.total_trades == 10
        assert result.total_pnl == Decimal("1000")
        assert result.profit_factor == 1.5

    def test_to_dict(self):
        """Test conversion to dict"""
        result = TradeStatsResult(
            total_trades=5,
            total_pnl=Decimal("500"),
        )
        d = result.to_dict()
        assert d["total_trades"] == 5
        assert d["total_pnl"] == 500.0


class TestAggregatedTrade:
    """Test suite for AggregatedTrade"""

    def test_defaults(self):
        """Test default values"""
        # AggregatedTrade requires trade_id, symbol, pnl, entry_time as positional args
        trade = AggregatedTrade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("0"),
            entry_time=datetime.now(),
        )
        assert trade.symbol == "AAPL"
        assert trade.pnl == Decimal("0")

    def test_with_values(self):
        """Test with actual values"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=2)
        trade = AggregatedTrade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            entry_time=entry_time,
            exit_time=exit_time,
            is_closed=True,
        )
        assert trade.trade_id == "T1"
        assert trade.symbol == "AAPL"
        assert trade.pnl == Decimal("100")
        assert trade.is_closed is True

    def test_duration(self):
        """Test duration calculation"""
        entry = datetime.now()
        exit_time = entry + timedelta(hours=2)
        trade = AggregatedTrade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            entry_time=entry,
            exit_time=exit_time,
            is_closed=True,
        )
        dur = trade.duration
        assert dur is not None
        assert dur >= timedelta(hours=1, minutes=59, seconds=59)

    def test_duration_none_for_open_trade(self):
        """Test duration is None for open trade"""
        trade = AggregatedTrade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("50"),
            entry_time=datetime.now(),
            exit_time=None,
            is_closed=False,
        )
        assert trade.duration is None
