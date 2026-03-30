"""Tests for drawdown_analyzer.py"""

from datetime import datetime
from decimal import Decimal

from src.reporting.core.drawdown_analyzer import (
    DrawdownAnalyzer,
    DrawdownResult,
    EquityPoint,
)


class TestDrawdownAnalyzer:
    """Test suite for DrawdownAnalyzer"""

    def setup_method(self):
        """Set up test fixtures"""
        self.analyzer = DrawdownAnalyzer()

    def test_initialization(self):
        """Test analyzer initializes"""
        assert self.analyzer is not None

    def test_initialization_with_threshold(self):
        """Test analyzer with custom threshold"""
        analyzer = DrawdownAnalyzer(min_peak_threshold=10000)
        assert analyzer._min_peak_threshold == Decimal("10000")

    def test_add_equity_point(self):
        """Test adding equity points"""
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 10, 0),
            equity=10000,
        )
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 11, 0),
            equity=9500,
        )
        assert len(self.analyzer._equity_curve) == 2
        # Peak equity is calculated internally
        assert self.analyzer._equity_curve[0].peak_equity == Decimal("10000")
        assert self.analyzer._equity_curve[1].peak_equity == Decimal("10000")

    def test_add_equity_curve(self):
        """Test adding multiple equity points via add_equity_curve"""
        data = [
            (datetime(2026, 3, 29, 10, 0), 10000),
            (datetime(2026, 3, 29, 11, 0), 9500),
            (datetime(2026, 3, 29, 12, 0), 9000),
        ]
        self.analyzer.add_equity_curve(data)
        assert len(self.analyzer._equity_curve) == 3

    def test_calculate_max_drawdown(self):
        """Test calculating max drawdown"""
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 10, 0),
            equity=10000,
        )
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 11, 0),
            equity=8000,
        )
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 12, 0),
            equity=9000,
        )
        result = self.analyzer.calculate_max_drawdown()
        assert isinstance(result, DrawdownResult)
        assert result.max_drawdown == Decimal("2000")
        assert result.max_drawdown_pct == 20.0

    def test_calculate_max_drawdown_no_drawdown(self):
        """Test calculating when no drawdown occurs"""
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 10, 0),
            equity=10000,
        )
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 11, 0),
            equity=11000,
        )
        result = self.analyzer.calculate_max_drawdown()
        assert isinstance(result, DrawdownResult)
        assert result.max_drawdown == Decimal("0")

    def test_get_current_drawdown(self):
        """Test getting current drawdown"""
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 10, 0),
            equity=10000,
        )
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 11, 0),
            equity=8500,
        )
        result = self.analyzer.get_current_drawdown()
        assert isinstance(result, DrawdownResult)
        assert result.current_drawdown == Decimal("1500")
        assert result.current_drawdown_pct == 15.0

    def test_analyze_drawdown_events(self):
        """Test analyzing drawdown events"""
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 10, 0),
            equity=10000,
        )
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 11, 0),
            equity=8000,
        )
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 12, 0),
            equity=10500,
        )
        events = self.analyzer.analyze_drawdown_events(min_drawdown_pct=5.0)
        assert isinstance(events, list)

    def test_clear(self):
        """Test clearing analyzer data"""
        self.analyzer.add_equity_point(
            timestamp=datetime(2026, 3, 29, 10, 0),
            equity=10000,
        )
        self.analyzer.clear()
        assert len(self.analyzer._equity_curve) == 0


class TestDrawdownResult:
    """Test suite for DrawdownResult"""

    def test_defaults(self):
        """Test default values"""
        result = DrawdownResult()
        assert result.max_drawdown == Decimal("0")
        assert result.max_drawdown_pct == 0.0
        assert result.current_drawdown == Decimal("0")
        assert result.current_drawdown_pct == 0.0

    def test_with_values(self):
        """Test with actual values"""
        result = DrawdownResult(
            max_drawdown=Decimal("2000"),
            max_drawdown_pct=20.0,
            current_drawdown=Decimal("500"),
            current_drawdown_pct=5.0,
        )
        assert result.max_drawdown == Decimal("2000")
        assert result.max_drawdown_pct == 20.0


class TestEquityPoint:
    """Test suite for EquityPoint"""

    def test_defaults(self):
        """Test default values"""
        # EquityPoint requires timestamp and equity as positional args
        point = EquityPoint(
            timestamp=datetime(2026, 3, 29, 10, 0), equity=Decimal("10000")
        )
        assert point.equity == Decimal("10000")
        assert point.timestamp == datetime(2026, 3, 29, 10, 0)
        assert point.peak_equity == Decimal("0")  # Default is 0

    def test_with_values(self):
        """Test with actual values"""
        point = EquityPoint(
            timestamp=datetime(2026, 3, 29, 10, 0),
            equity=Decimal("10000"),
            peak_equity=Decimal("10500"),
        )
        assert point.equity == Decimal("10000")
        assert point.peak_equity == Decimal("10500")
