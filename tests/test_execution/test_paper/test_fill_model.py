"""Tests for fill model.

Tests for SlippageConfig, LatencyConfig, and FillModel.
"""

import asyncio
import pytest

from src.execution.paper.fill_model import (
    SlippageConfig,
    LatencyConfig,
    FillModel,
    create_fill_model,
)
from src.execution.paper.models import PaperOrder


class TestSlippageConfig:
    """Test SlippageConfig dataclass."""

    def test_default_values(self):
        """Test default slippage configuration."""
        config = SlippageConfig()

        assert config.min_slippage_pct == 0.01
        assert config.max_slippage_pct == 0.05
        assert config.volatility_factor == 1.0

    def test_custom_values(self):
        """Test custom slippage configuration."""
        config = SlippageConfig(
            min_slippage_pct=0.02,
            max_slippage_pct=0.10,
            volatility_factor=2.0,
        )

        assert config.min_slippage_pct == 0.02
        assert config.max_slippage_pct == 0.10
        assert config.volatility_factor == 2.0

    def test_negative_slippage_raises(self):
        """Test that negative slippage raises ValueError."""
        with pytest.raises(
            ValueError, match="Slippage percentages must be non-negative"
        ):
            SlippageConfig(min_slippage_pct=-0.01)

        with pytest.raises(
            ValueError, match="Slippage percentages must be non-negative"
        ):
            SlippageConfig(max_slippage_pct=-0.01)

    def test_min_greater_than_max_raises(self):
        """Test that min > max raises ValueError."""
        with pytest.raises(
            ValueError, match="min_slippage_pct cannot exceed max_slippage_pct"
        ):
            SlippageConfig(min_slippage_pct=0.10, max_slippage_pct=0.05)

    def test_negative_volatility_raises(self):
        """Test that negative volatility_factor raises ValueError."""
        with pytest.raises(ValueError, match="volatility_factor must be non-negative"):
            SlippageConfig(volatility_factor=-1.0)


class TestLatencyConfig:
    """Test LatencyConfig dataclass."""

    def test_default_values(self):
        """Test default latency configuration."""
        config = LatencyConfig()

        assert config.min_latency_ms == 50.0
        assert config.max_latency_ms == 200.0

    def test_custom_values(self):
        """Test custom latency configuration."""
        config = LatencyConfig(
            min_latency_ms=100.0,
            max_latency_ms=500.0,
        )

        assert config.min_latency_ms == 100.0
        assert config.max_latency_ms == 500.0

    def test_negative_latency_raises(self):
        """Test that negative latency raises ValueError."""
        with pytest.raises(ValueError, match="Latency values must be non-negative"):
            LatencyConfig(min_latency_ms=-50.0)

        with pytest.raises(ValueError, match="Latency values must be non-negative"):
            LatencyConfig(max_latency_ms=-50.0)

    def test_min_greater_than_max_raises(self):
        """Test that min > max raises ValueError."""
        with pytest.raises(
            ValueError, match="min_latency_ms cannot exceed max_latency_ms"
        ):
            LatencyConfig(min_latency_ms=200.0, max_latency_ms=50.0)

    def test_get_latency_seconds(self):
        """Test getting latency in seconds."""
        config = LatencyConfig(min_latency_ms=100.0, max_latency_ms=100.0)

        latency = config.get_latency_seconds()

        assert latency == 0.1  # 100ms = 0.1s

    def test_get_latency_seconds_range(self):
        """Test that latency is within configured range."""
        config = LatencyConfig(min_latency_ms=50.0, max_latency_ms=200.0)

        # Test multiple times to check randomness
        for _ in range(10):
            latency = config.get_latency_seconds()
            assert 0.05 <= latency <= 0.2


class TestFillModel:
    """Test FillModel class."""

    def test_default_initialization(self):
        """Test FillModel with default configuration."""
        model = FillModel()

        assert model.slippage_config.min_slippage_pct == 0.01
        assert model.latency_config.min_latency_ms == 50.0

    def test_custom_initialization(self):
        """Test FillModel with custom configuration."""
        slippage = SlippageConfig(min_slippage_pct=0.02, max_slippage_pct=0.08)
        latency = LatencyConfig(min_latency_ms=100.0, max_latency_ms=300.0)

        model = FillModel(slippage_config=slippage, latency_config=latency)

        assert model.slippage_config.min_slippage_pct == 0.02
        assert model.latency_config.min_latency_ms == 100.0

    @pytest.mark.asyncio
    async def test_simulate_latency(self):
        """Test latency simulation."""
        model = FillModel(
            latency_config=LatencyConfig(min_latency_ms=50.0, max_latency_ms=50.0)
        )

        start = asyncio.get_event_loop().time()
        await model.simulate_latency()
        elapsed = asyncio.get_event_loop().time() - start

        # Should take approximately 50ms (0.05s)
        assert 0.04 <= elapsed <= 0.15  # Allow some tolerance

    def test_calculate_market_fill_price_buy(self):
        """Test market fill price calculation for buy orders."""
        model = FillModel()

        # With default slippage of 0.01-0.05%, buy price should be higher
        fill_price = model.calculate_market_fill_price(
            market_price=50000.0,
            side="buy",
            quantity=1.0,
        )

        # Buy should have slippage added (worse price for buyer)
        assert fill_price > 50000.0
        # Max slippage is 0.05%, so price should be less than 50000 * 1.0005
        assert fill_price <= 50000.0 * 1.0005 * 1.01  # Allow for quantity factor

    def test_calculate_market_fill_price_sell(self):
        """Test market fill price calculation for sell orders."""
        model = FillModel()

        # With slippage, sell price should be lower
        fill_price = model.calculate_market_fill_price(
            market_price=50000.0,
            side="sell",
            quantity=1.0,
        )

        # Sell should have slippage subtracted (worse price for seller)
        assert fill_price < 50000.0
        assert fill_price >= 50000.0 * 0.9994  # Allow for some tolerance

    def test_calculate_market_fill_price_invalid_inputs(self):
        """Test that invalid inputs raise ValueError."""
        model = FillModel()

        with pytest.raises(ValueError, match="Invalid market_price"):
            model.calculate_market_fill_price(0.0, "buy", 1.0)

        with pytest.raises(ValueError, match="Invalid market_price"):
            model.calculate_market_fill_price(-100.0, "buy", 1.0)

        with pytest.raises(ValueError, match="Invalid side"):
            model.calculate_market_fill_price(50000.0, "invalid", 1.0)

        with pytest.raises(ValueError, match="Invalid quantity"):
            model.calculate_market_fill_price(50000.0, "buy", 0.0)

    def test_calculate_market_fill_price_quantity_impact(self):
        """Test that larger quantities have more slippage."""
        model = FillModel(
            slippage_config=SlippageConfig(min_slippage_pct=0.01, max_slippage_pct=0.01)
        )

        small_qty_price = model.calculate_market_fill_price(
            market_price=50000.0,
            side="buy",
            quantity=0.1,
        )

        large_qty_price = model.calculate_market_fill_price(
            market_price=50000.0,
            side="buy",
            quantity=100.0,
        )

        # Larger quantity should have higher price (more slippage)
        assert large_qty_price >= small_qty_price

    def test_should_limit_order_fill_buy(self):
        """Test limit order fill check for buy orders."""
        model = FillModel()

        order = PaperOrder(
            order_id="test_001",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )

        # Should fill when market price is at or below limit price
        assert model.should_limit_order_fill(order, 48000.0) is True  # At limit
        assert model.should_limit_order_fill(order, 47000.0) is True  # Below limit
        assert model.should_limit_order_fill(order, 49000.0) is False  # Above limit

    def test_should_limit_order_fill_sell(self):
        """Test limit order fill check for sell orders."""
        model = FillModel()

        order = PaperOrder(
            order_id="test_002",
            symbol="BTCUSDT",
            side="sell",
            order_type="limit",
            quantity=1.0,
            price=52000.0,
        )

        # Should fill when market price is at or above limit price
        assert model.should_limit_order_fill(order, 52000.0) is True  # At limit
        assert model.should_limit_order_fill(order, 53000.0) is True  # Above limit
        assert model.should_limit_order_fill(order, 51000.0) is False  # Below limit

    def test_should_limit_order_fill_not_limit_order(self):
        """Test that non-limit orders never fill via this method."""
        model = FillModel()

        market_order = PaperOrder(
            order_id="test_003",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        assert model.should_limit_order_fill(market_order, 48000.0) is False

    def test_should_limit_order_fill_no_price(self):
        """Test that limit orders without price never fill."""
        model = FillModel()

        order = PaperOrder(
            order_id="test_004",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )
        order.price = None  # Manually remove price

        assert model.should_limit_order_fill(order, 47000.0) is False

    def test_calculate_limit_fill_price(self):
        """Test limit fill price calculation."""
        model = FillModel()

        order = PaperOrder(
            order_id="test_005",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )

        fill_price = model.calculate_limit_fill_price(order, 47000.0)

        assert fill_price == 48000.0  # Fills at limit price

    def test_calculate_limit_fill_price_not_limit_order(self):
        """Test that non-limit orders raise error."""
        model = FillModel()

        market_order = PaperOrder(
            order_id="test_006",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        with pytest.raises(ValueError, match="Expected limit order"):
            model.calculate_limit_fill_price(market_order, 50000.0)

    @pytest.mark.asyncio
    async def test_create_fill(self):
        """Test creating a fill with latency."""
        model = FillModel(
            latency_config=LatencyConfig(min_latency_ms=10.0, max_latency_ms=10.0)
        )

        order = PaperOrder(
            order_id="test_007",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        start = asyncio.get_event_loop().time()
        fill = await model.create_fill(order, fill_price=50000.0)
        elapsed = asyncio.get_event_loop().time() - start

        assert fill.order_id == "test_007"
        assert fill.symbol == "BTCUSDT"
        assert fill.side == "buy"
        assert fill.price == 50000.0
        assert fill.quantity == 1.0  # Full quantity
        assert elapsed >= 0.005  # Should have some latency

    @pytest.mark.asyncio
    async def test_create_fill_partial(self):
        """Test creating a partial fill."""
        model = FillModel()

        order = PaperOrder(
            order_id="test_008",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        fill = await model.create_fill(order, fill_price=50000.0, fill_quantity=0.5)

        assert fill.quantity == 0.5

    @pytest.mark.asyncio
    async def test_fill_market_order(self):
        """Test filling a market order."""
        model = FillModel(
            latency_config=LatencyConfig(min_latency_ms=10.0, max_latency_ms=10.0)
        )

        order = PaperOrder(
            order_id="test_009",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        fill = await model.fill_market_order(order, market_price=50000.0)

        assert fill.symbol == "BTCUSDT"
        assert fill.quantity == 1.0
        # Should have slippage applied
        assert fill.price != 50000.0
        assert fill.price > 50000.0  # Buy = higher price

    @pytest.mark.asyncio
    async def test_fill_market_order_not_market(self):
        """Test that non-market orders raise error."""
        model = FillModel()

        limit_order = PaperOrder(
            order_id="test_010",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )

        with pytest.raises(ValueError, match="Expected market order"):
            await model.fill_market_order(limit_order, market_price=50000.0)

    @pytest.mark.asyncio
    async def test_fill_limit_order_should_fill(self):
        """Test filling a limit order when price crosses."""
        model = FillModel(
            latency_config=LatencyConfig(min_latency_ms=10.0, max_latency_ms=10.0)
        )

        order = PaperOrder(
            order_id="test_011",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )

        fill = await model.fill_limit_order(order, market_price=47000.0)

        assert fill is not None
        assert fill.price == 48000.0  # Fills at limit price

    @pytest.mark.asyncio
    async def test_fill_limit_order_should_not_fill(self):
        """Test that limit order doesn't fill when price doesn't cross."""
        model = FillModel()

        order = PaperOrder(
            order_id="test_012",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )

        fill = await model.fill_limit_order(order, market_price=49000.0)

        assert fill is None

    @pytest.mark.asyncio
    async def test_fill_limit_order_partial(self):
        """Test partial fill of limit order."""
        model = FillModel(
            latency_config=LatencyConfig(min_latency_ms=10.0, max_latency_ms=10.0)
        )

        order = PaperOrder(
            order_id="test_013",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )

        fill = await model.fill_limit_order(order, market_price=47000.0, partial=True)

        assert fill is not None
        # Partial fill should be 10-50% of quantity
        assert 0.1 <= fill.quantity <= 0.5


class TestCreateFillModel:
    """Test create_fill_model factory function."""

    def test_create_fill_model_defaults(self):
        """Test creating fill model with defaults."""
        model = create_fill_model()

        assert model.slippage_config.min_slippage_pct == 0.01
        assert model.slippage_config.max_slippage_pct == 0.05
        assert model.latency_config.min_latency_ms == 50.0
        assert model.latency_config.max_latency_ms == 200.0

    def test_create_fill_model_custom(self):
        """Test creating fill model with custom values."""
        model = create_fill_model(
            min_slippage_pct=0.02,
            max_slippage_pct=0.10,
            min_latency_ms=100.0,
            max_latency_ms=500.0,
        )

        assert model.slippage_config.min_slippage_pct == 0.02
        assert model.slippage_config.max_slippage_pct == 0.10
        assert model.latency_config.min_latency_ms == 100.0
        assert model.latency_config.max_latency_ms == 500.0
