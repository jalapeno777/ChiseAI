"""Tests for liquidity metrics."""

from datetime import UTC, datetime

import pytest

from exchange_data.binance.liquidity import LiquidityCalculator, LiquidityMetrics
from exchange_data.binance.orderbook import OrderBookLevel, OrderBookSnapshot


class TestLiquidityMetrics:
    """Test LiquidityMetrics dataclass."""

    def test_creation(self) -> None:
        """Test creating liquidity metrics."""
        metrics = LiquidityMetrics(
            symbol="BTCUSDT",
            timestamp="2024-01-01T12:00:00",
            bid_ask_spread=10.0,
            bid_ask_spread_pct=0.02,
            bid_depth_1pct=100.0,
            ask_depth_1pct=100.0,
            bid_depth_5pct=500.0,
            ask_depth_5pct=500.0,
            bid_depth_10pct=1000.0,
            ask_depth_10pct=1000.0,
            imbalance_ratio=1.0,
            slippage_1000usd=0.01,
            slippage_10000usd=0.1,
        )

        assert metrics.symbol == "BTCUSDT"
        assert metrics.bid_ask_spread == 10.0

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        metrics = LiquidityMetrics(
            symbol="BTCUSDT",
            timestamp="2024-01-01T12:00:00",
            bid_ask_spread=10.0,
            bid_ask_spread_pct=0.02,
            bid_depth_1pct=100.0,
            ask_depth_1pct=100.0,
            bid_depth_5pct=500.0,
            ask_depth_5pct=500.0,
            bid_depth_10pct=1000.0,
            ask_depth_10pct=1000.0,
            imbalance_ratio=1.0,
            slippage_1000usd=0.01,
            slippage_10000usd=0.1,
        )

        data = metrics.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["bid_ask_spread"] == 10.0


class TestLiquidityCalculator:
    """Test LiquidityCalculator functionality."""

    def test_calculate_basic(self) -> None:
        """Test basic liquidity calculation."""
        calculator = LiquidityCalculator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            last_update_id=1,
            bids=[
                OrderBookLevel(price=50000.0, quantity=10.0),
                OrderBookLevel(price=49900.0, quantity=20.0),
                OrderBookLevel(price=49800.0, quantity=30.0),
            ],
            asks=[
                OrderBookLevel(price=50010.0, quantity=10.0),
                OrderBookLevel(price=50100.0, quantity=20.0),
                OrderBookLevel(price=50200.0, quantity=30.0),
            ],
        )

        metrics = calculator.calculate(snapshot)

        assert metrics is not None
        assert metrics.symbol == "BTCUSDT"
        assert metrics.bid_ask_spread == 10.0
        assert metrics.bid_ask_spread_pct == pytest.approx(0.02, rel=0.01)

    def test_calculate_empty_book(self) -> None:
        """Test calculation with empty order book."""
        calculator = LiquidityCalculator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            last_update_id=1,
            bids=[],
            asks=[],
        )

        metrics = calculator.calculate(snapshot)

        assert metrics is None

    def test_depth_calculation(self) -> None:
        """Test depth calculations at various thresholds."""
        calculator = LiquidityCalculator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            last_update_id=1,
            bids=[
                OrderBookLevel(price=50000.0, quantity=10.0),
                OrderBookLevel(price=49750.0, quantity=20.0),
                OrderBookLevel(price=49500.0, quantity=30.0),
            ],
            asks=[
                OrderBookLevel(price=50050.0, quantity=10.0),
                OrderBookLevel(price=50250.0, quantity=20.0),
                OrderBookLevel(price=50500.0, quantity=30.0),
            ],
        )

        metrics = calculator.calculate(snapshot)

        assert metrics is not None
        # Depth includes all levels at or above the threshold price
        # 1% threshold: best_bid * 0.99 = 49500, so all 60 included
        assert metrics.bid_depth_1pct == 60.0
        assert metrics.bid_depth_5pct == 60.0
        assert metrics.bid_depth_10pct == 60.0

    def test_imbalance_ratio(self) -> None:
        """Test imbalance ratio calculation."""
        calculator = LiquidityCalculator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            last_update_id=1,
            bids=[
                OrderBookLevel(price=50000.0, quantity=100.0),
                OrderBookLevel(price=49750.0, quantity=100.0),
            ],
            asks=[
                OrderBookLevel(price=50050.0, quantity=50.0),
                OrderBookLevel(price=50250.0, quantity=50.0),
            ],
        )

        metrics = calculator.calculate(snapshot)

        assert metrics is not None
        assert metrics.imbalance_ratio == 2.0  # 200 / 100

    def test_slippage_estimation(self) -> None:
        """Test slippage estimation."""
        calculator = LiquidityCalculator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[
                OrderBookLevel(price=50000.0, quantity=1.0),
                OrderBookLevel(price=50100.0, quantity=1.0),
            ],
        )

        metrics = calculator.calculate(snapshot)

        assert metrics is not None
        # Slippage should be positive
        assert metrics.slippage_1000usd >= 0
        assert metrics.slippage_10000usd >= metrics.slippage_1000usd

    def test_depth_imbalance(self) -> None:
        """Test depth imbalance calculation."""
        calculator = LiquidityCalculator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            last_update_id=1,
            bids=[
                OrderBookLevel(price=50000.0, quantity=100.0),
                OrderBookLevel(price=47500.0, quantity=100.0),  # 5% below
            ],
            asks=[
                OrderBookLevel(price=50050.0, quantity=50.0),
                OrderBookLevel(price=52550.0, quantity=50.0),  # 5% above
            ],
        )

        imbalance = calculator.calculate_depth_imbalance(snapshot, threshold_pct=0.05)

        assert imbalance == 2.0  # 200 / 100

    def test_liquidity_score(self) -> None:
        """Test liquidity score calculation."""
        calculator = LiquidityCalculator()
        metrics = LiquidityMetrics(
            symbol="BTCUSDT",
            timestamp="2024-01-01T12:00:00",
            bid_ask_spread=0.01,  # Very tight spread
            bid_ask_spread_pct=0.01,
            bid_depth_5pct=10000.0,  # High depth
            ask_depth_5pct=10000.0,
            bid_depth_1pct=1000.0,
            ask_depth_1pct=1000.0,
            bid_depth_10pct=20000.0,
            ask_depth_10pct=20000.0,
            imbalance_ratio=1.0,
            slippage_1000usd=0.001,  # Low slippage
            slippage_10000usd=0.01,
        )

        score = calculator.get_liquidity_score(metrics)

        assert 0 <= score <= 100
        assert score > 80  # Should be high for good liquidity

    def test_liquidity_score_poor_liquidity(self) -> None:
        """Test liquidity score for poor liquidity."""
        calculator = LiquidityCalculator()
        metrics = LiquidityMetrics(
            symbol="BTCUSDT",
            timestamp="2024-01-01T12:00:00",
            bid_ask_spread=100.0,  # Wide spread
            bid_ask_spread_pct=1.0,
            bid_depth_5pct=10.0,  # Low depth
            ask_depth_5pct=10.0,
            bid_depth_1pct=1.0,
            ask_depth_1pct=1.0,
            bid_depth_10pct=20.0,
            ask_depth_10pct=20.0,
            imbalance_ratio=5.0,
            slippage_1000usd=1.0,  # High slippage
            slippage_10000usd=10.0,
        )

        score = calculator.get_liquidity_score(metrics)

        assert 0 <= score <= 100
        assert score < 50  # Should be low for poor liquidity
