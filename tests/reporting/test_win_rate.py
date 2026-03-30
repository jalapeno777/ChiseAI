"""Tests for win_rate.py"""

from datetime import datetime
from decimal import Decimal

from src.reporting.core.win_rate import TradeResult, WinRateCalculator, WinRateResult


class TestWinRateCalculator:
    """Test suite for WinRateCalculator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.calculator = WinRateCalculator()

    def test_initialization(self):
        """Test calculator initializes"""
        assert self.calculator is not None

    def test_add_trade_win(self):
        """Test adding a winning trade"""
        self.calculator.add_trade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            timestamp=datetime.now(),
        )
        result = self.calculator.calculate_win_rate()
        assert result.total_trades == 1
        assert result.winning_trades == 1
        assert result.win_rate == 100.0

    def test_add_trade_loss(self):
        """Test adding a losing trade"""
        self.calculator.add_trade(
            trade_id="T2",
            symbol="AAPL",
            pnl=Decimal("-100"),
            timestamp=datetime.now(),
        )
        result = self.calculator.calculate_win_rate()
        assert result.total_trades == 1
        assert result.losing_trades == 1
        assert result.win_rate == 0.0

    def test_add_trades_and_clear(self):
        """Test adding multiple trades and clearing"""
        self.calculator.add_trade(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            timestamp=datetime.now(),
        )
        self.calculator.add_trade(
            trade_id="T2",
            symbol="GOOG",
            pnl=Decimal("50"),
            timestamp=datetime.now(),
        )
        assert len(self.calculator._trades) == 2
        self.calculator.clear()
        assert len(self.calculator._trades) == 0

    def test_calculate_win_rate_mixed(self):
        """Test win rate with mixed trades"""
        for i in range(3):
            self.calculator.add_trade(
                trade_id=f"T{i}_win",
                symbol="AAPL",
                pnl=Decimal("100"),
                timestamp=datetime.now(),
            )
        for i in range(2):
            self.calculator.add_trade(
                trade_id=f"T{i}_loss",
                symbol="GOOG",
                pnl=Decimal("-100"),
                timestamp=datetime.now(),
            )
        result = self.calculator.calculate_win_rate()
        assert result.total_trades == 5
        assert result.winning_trades == 3
        assert result.losing_trades == 2
        assert result.win_rate == 60.0

    def test_calculate_win_rate_empty(self):
        """Test win rate with no trades"""
        result = self.calculator.calculate_win_rate()
        assert result.total_trades == 0
        assert result.winning_trades == 0
        assert result.losing_trades == 0
        assert result.win_rate == 0.0

    def test_add_trades_batch(self):
        """Test adding multiple trades at once"""
        trades = [
            ("T1", "AAPL", Decimal("100"), datetime.now()),
            ("T2", "AAPL", Decimal("-50"), datetime.now()),
            ("T3", "GOOG", Decimal("75"), datetime.now()),
        ]
        self.calculator.add_trades(trades)
        result = self.calculator.calculate_win_rate()
        assert result.total_trades == 3
        assert result.winning_trades == 2
        assert result.losing_trades == 1


class TestWinRateResult:
    """Test suite for WinRateResult"""

    def test_defaults(self):
        """Test default values"""
        result = WinRateResult()
        assert result.total_trades == 0
        assert result.winning_trades == 0
        assert result.losing_trades == 0
        assert result.win_rate == 0.0
        assert result.avg_win == Decimal("0")

    def test_with_values(self):
        """Test with actual values"""
        result = WinRateResult(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=60.0,
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
        )
        assert result.total_trades == 10
        assert result.winning_trades == 6
        assert result.win_rate == 60.0

    def test_to_dict(self):
        """Test conversion to dict"""
        result = WinRateResult(
            total_trades=5,
            winning_trades=3,
            losing_trades=2,
            win_rate=60.0,
        )
        d = result.to_dict()
        assert d["total_trades"] == 5
        assert d["winning_trades"] == 3
        assert d["win_rate"] == 60.0


class TestTradeResult:
    """Test suite for TradeResult"""

    def test_defaults(self):
        """Test default values"""
        # TradeResult requires trade_id, symbol, pnl as positional args
        result = TradeResult(trade_id="T1", symbol="AAPL", pnl=Decimal("0"))
        assert result.symbol == "AAPL"
        assert result.pnl == Decimal("0")

    def test_with_values(self):
        """Test with actual values"""
        result = TradeResult(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("100"),
            timestamp=datetime.now(),
        )
        assert result.trade_id == "T1"
        assert result.symbol == "AAPL"
        assert result.pnl == Decimal("100")
        assert result.is_win is True

    def test_is_win_false(self):
        """Test is_win is False for losing trade"""
        result = TradeResult(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("-50"),
        )
        assert result.is_win is False

    def test_is_win_true(self):
        """Test is_win is True for winning trade"""
        result = TradeResult(
            trade_id="T1",
            symbol="AAPL",
            pnl=Decimal("50"),
        )
        assert result.is_win is True
