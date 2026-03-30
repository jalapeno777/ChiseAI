"""Tests for pnl_calculator.py"""

from decimal import Decimal

from src.reporting.core.pnl_calculator import (
    PnLCalculator,
    PnLResult,
    TradePnL,
)


class TestPnLCalculator:
    """Test suite for PnLCalculator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.calculator = PnLCalculator()

    def test_initialization(self):
        """Test calculator initializes with default values"""
        assert self.calculator._default_currency == "USD"
        assert self.calculator._use_decimal is True
        assert "USD" in self.calculator._exchange_rates

    def test_initialization_custom(self):
        """Test calculator with custom params"""
        calc = PnLCalculator(default_currency="EUR", use_decimal=False)
        assert calc._default_currency == "EUR"
        assert calc._use_decimal is False

    def test_set_exchange_rate(self):
        """Test setting exchange rate"""
        self.calculator.set_exchange_rate("EUR", 1.5)
        assert self.calculator._exchange_rates["EUR"] == Decimal("1.5")

    def test_set_exchange_rate_decimal(self):
        """Test setting exchange rate with Decimal"""
        self.calculator.set_exchange_rate("GBP", Decimal("1.25"))
        assert self.calculator._exchange_rates["GBP"] == Decimal("1.25")

    def test_convert_to_default_from_decimal(self):
        """Test currency conversion from Decimal"""
        result = self.calculator.convert_to_default(Decimal("100"), "EUR")
        assert isinstance(result, Decimal)

    def test_convert_to_default_from_float(self):
        """Test currency conversion from float"""
        result = self.calculator.convert_to_default(100.0, "EUR")
        assert isinstance(result, Decimal)

    def test_convert_to_default_known_rate(self):
        """Test conversion with known rate"""
        self.calculator.set_exchange_rate("EUR", 0.85)
        result = self.calculator.convert_to_default(Decimal("100"), "EUR")
        assert result == Decimal("85.0")

    def test_calculate_trade_pnl_long_profitable(self):
        """Test long trade P&L calculation - profitable"""
        trade = self.calculator.calculate_trade_pnl(
            entry_price=100,
            exit_price=110,
            quantity=10,
            direction="long",
            fees=5,
        )
        assert trade.realized_pnl == Decimal("95")  # (110-100) * 10 - 5
        assert trade.direction == "long"
        assert trade.is_closed is True

    def test_calculate_trade_pnl_long_loss(self):
        """Test long trade P&L calculation - loss"""
        trade = self.calculator.calculate_trade_pnl(
            entry_price=100,
            exit_price=90,
            quantity=10,
            direction="long",
            fees=5,
        )
        assert trade.realized_pnl == Decimal("-105")  # (90-100) * 10 - 5

    def test_calculate_trade_pnl_short_profitable(self):
        """Test short trade P&L calculation - profitable"""
        trade = self.calculator.calculate_trade_pnl(
            entry_price=100,
            exit_price=90,
            quantity=10,
            direction="short",
            fees=5,
        )
        assert trade.realized_pnl == Decimal("95")  # (100-90) * 10 - 5

    def test_calculate_trade_pnl_short_loss(self):
        """Test short trade P&L calculation - loss"""
        trade = self.calculator.calculate_trade_pnl(
            entry_price=100,
            exit_price=110,
            quantity=10,
            direction="short",
            fees=5,
        )
        assert trade.realized_pnl == Decimal("-105")  # (100-110) * 10 - 5

    def test_calculate_daily_pnl(self):
        """Test calculating daily P&L"""
        trade1 = TradePnL(
            trade_id="T1",
            symbol="AAPL",
            realized_pnl=Decimal("100"),
            is_closed=True,
        )
        trade2 = TradePnL(
            trade_id="T2",
            symbol="AAPL",
            realized_pnl=Decimal("-50"),
            is_closed=True,
        )
        result = self.calculator.calculate_daily_pnl([trade1, trade2])
        assert result.realized_pnl == Decimal("50")
        assert result.trade_count == 2

    def test_calculate_daily_pnl_with_unrealized(self):
        """Test calculating daily P&L with unrealized"""
        trade1 = TradePnL(
            trade_id="T1",
            symbol="AAPL",
            realized_pnl=Decimal("100"),
            is_closed=True,
        )
        trade2 = TradePnL(
            trade_id="T2",
            symbol="AAPL",
            unrealized_pnl=Decimal("50"),
            is_closed=False,
        )
        result = self.calculator.calculate_daily_pnl([trade1, trade2])
        assert result.realized_pnl == Decimal("100")
        assert result.unrealized_pnl == Decimal("50")
        assert result.total_pnl == Decimal("150")

    def test_compare_periods(self):
        """Test comparing two periods"""
        current = PnLResult(
            realized_pnl=Decimal("100"),
            total_pnl=Decimal("100"),
            trade_count=5,
        )
        previous = PnLResult(
            realized_pnl=Decimal("50"),
            total_pnl=Decimal("50"),
            trade_count=3,
        )
        summary = self.calculator.compare_periods(current, previous)
        assert summary.period_over_period_change == Decimal("50")


class TestPnLResult:
    """Test suite for PnLResult"""

    def test_defaults(self):
        """Test default values"""
        result = PnLResult()
        assert result.realized_pnl == Decimal("0")
        assert result.unrealized_pnl == Decimal("0")
        assert result.total_pnl == Decimal("0")
        assert result.currency == "USD"
        assert result.trade_count == 0

    def test_with_values(self):
        """Test with actual values"""
        result = PnLResult(
            realized_pnl=Decimal("1000"),
            unrealized_pnl=Decimal("500"),
            total_pnl=Decimal("1500"),
            currency="USD",
            trade_count=10,
        )
        assert result.realized_pnl == Decimal("1000")
        assert result.unrealized_pnl == Decimal("500")
        assert result.total_pnl == Decimal("1500")
        assert result.trade_count == 10

    def test_to_dict(self):
        """Test conversion to dictionary"""
        result = PnLResult(
            realized_pnl=Decimal("1000"),
            total_pnl=Decimal("1000"),
            trade_count=5,
        )
        d = result.to_dict()
        assert d["realized_pnl"] == 1000.0
        assert d["trade_count"] == 5


class TestTradePnL:
    """Test suite for TradePnL"""

    def test_defaults(self):
        """Test default values"""
        # TradePnL requires trade_id and symbol as positional args
        trade = TradePnL(trade_id="T1", symbol="AAPL")
        assert trade.realized_pnl == Decimal("0")
        assert trade.unrealized_pnl == Decimal("0")
        assert trade.is_closed is False

    def test_with_values(self):
        """Test with actual values"""
        trade = TradePnL(
            trade_id="T1",
            symbol="AAPL",
            direction="long",
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("10"),
            realized_pnl=Decimal("95"),
            fees=Decimal("5"),
            is_closed=True,
        )
        assert trade.trade_id == "T1"
        assert trade.symbol == "AAPL"
        assert trade.direction == "long"
        assert trade.realized_pnl == Decimal("95")

    def test_calculate_total_pnl(self):
        """Test total P&L calculation"""
        trade = TradePnL(
            trade_id="T1",
            symbol="AAPL",
            realized_pnl=Decimal("100"),
            unrealized_pnl=Decimal("0"),
            fees=Decimal("10"),
            is_closed=True,
        )
        assert trade.calculate_total_pnl() == Decimal("90")

    def test_calculate_total_pnl_open_trade(self):
        """Test total P&L for open trade"""
        trade = TradePnL(
            trade_id="T1",
            symbol="AAPL",
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("50"),
            fees=Decimal("5"),
            is_closed=False,
        )
        assert trade.calculate_total_pnl() == Decimal("45")
