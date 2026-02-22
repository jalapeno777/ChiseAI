"""Tests for order simulator.

Tests for OrderSimulator, MarketDataProvider, and OrderSimulatorConfig.
"""

import pytest
from src.execution.paper.fill_model import FillModel, LatencyConfig, SlippageConfig
from src.execution.paper.models import OrderState, PaperOrder
from src.execution.paper.order_simulator import (
    MarketDataProvider,
    OrderSimulator,
    OrderSimulatorConfig,
)


class TestMarketDataProvider:
    """Test MarketDataProvider class."""

    def test_initialization(self):
        """Test initialization with empty cache."""
        provider = MarketDataProvider()

        assert provider.price_cache == {}
        assert provider.get_price("BTCUSDT") is None

    def test_set_and_get_price(self):
        """Test setting and getting prices."""
        provider = MarketDataProvider()

        provider.set_price("BTCUSDT", 50000.0)

        assert provider.get_price("BTCUSDT") == 50000.0
        assert provider.get_price("ETHUSDT") is None

    def test_set_price_uppercase(self):
        """Test that symbol is stored uppercase."""
        provider = MarketDataProvider()

        provider.set_price("btcusdt", 50000.0)

        # Should be accessible by uppercase
        assert provider.get_price("BTCUSDT") == 50000.0

    def test_update_prices(self):
        """Test updating multiple prices."""
        provider = MarketDataProvider()

        provider.update_prices(
            {
                "BTCUSDT": 50000.0,
                "ETHUSDT": 3000.0,
            }
        )

        assert provider.get_price("BTCUSDT") == 50000.0
        assert provider.get_price("ETHUSDT") == 3000.0


class TestOrderSimulator:
    """Test OrderSimulator class."""

    @pytest.fixture
    def simulator(self):
        """Create a simulator for testing."""
        return OrderSimulator()

    @pytest.fixture
    def fast_simulator(self):
        """Create a simulator with minimal latency for fast tests."""
        fill_model = FillModel(
            slippage_config=SlippageConfig(
                min_slippage_pct=0.01, max_slippage_pct=0.01
            ),
            latency_config=LatencyConfig(min_latency_ms=1.0, max_latency_ms=1.0),
        )
        return OrderSimulator(fill_model=fill_model)

    def test_initialization(self):
        """Test simulator initialization."""
        sim = OrderSimulator()

        assert sim.fill_model is not None
        assert sim.market_data is not None
        assert sim.orders == {}

    def test_initialization_with_custom_fill_model(self):
        """Test simulator with custom fill model."""
        fill_model = FillModel(
            slippage_config=SlippageConfig(
                min_slippage_pct=0.02, max_slippage_pct=0.03
            ),
        )
        sim = OrderSimulator(fill_model=fill_model)

        assert sim.fill_model.slippage_config.min_slippage_pct == 0.02

    def test_generate_order_id_unique(self):
        """Test that generated order IDs are unique."""
        sim = OrderSimulator()

        id1 = sim._generate_order_id()
        id2 = sim._generate_order_id()

        assert id1 != id2
        assert id1.startswith("paper_")
        assert id2.startswith("paper_")

    def test_validate_order_valid_market(self):
        """Test validation of valid market order."""
        sim = OrderSimulator()
        sim.set_market_price("BTCUSDT", 50000.0)

        order = PaperOrder(
            order_id="test",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        is_valid, error = sim._validate_order(order)

        assert is_valid is True
        assert error is None

    def test_validate_order_valid_limit(self):
        """Test validation of valid limit order."""
        sim = OrderSimulator()

        order = PaperOrder(
            order_id="test",
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=48000.0,
        )

        is_valid, error = sim._validate_order(order)

        assert is_valid is True
        assert error is None

    def test_validate_order_invalid_symbol(self):
        """Test validation with invalid symbol."""
        sim = OrderSimulator()

        order = PaperOrder(
            order_id="test",
            symbol="",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        is_valid, error = sim._validate_order(order)

        assert is_valid is False
        assert error is not None
        assert "symbol" in error.lower()

    def test_validate_order_negative_quantity(self):
        """Test validation with negative quantity."""
        sim = OrderSimulator()
        sim.set_market_price("BTCUSDT", 50000.0)

        # PaperOrder validates in __post_init__, so we expect ValueError
        with pytest.raises(ValueError, match="Invalid quantity"):
            PaperOrder(
                order_id="test",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=-1.0,
            )

    def test_validate_order_limit_no_price(self):
        """Test validation of limit order without price."""
        sim = OrderSimulator()

        # PaperOrder validates in __post_init__, so we expect ValueError
        with pytest.raises(ValueError, match="Limit orders require positive price"):
            PaperOrder(
                order_id="test",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=1.0,
                price=None,
            )

    def test_validate_order_market_no_price_available(self):
        """Test validation of market order without market price."""
        sim = OrderSimulator()
        # No price set for BTCUSDT

        order = PaperOrder(
            order_id="test",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        is_valid, error = sim._validate_order(order)

        assert is_valid is False
        assert error is not None
        assert "price" in error.lower() or "market" in error.lower()

    @pytest.mark.asyncio
    async def test_place_market_order_buy(self, fast_simulator):
        """Test placing a market buy order."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.5,
        )

        assert order.symbol == "BTCUSDT"
        assert order.side == "buy"
        assert order.order_type == "market"
        assert order.quantity == 0.5
        assert order.state == OrderState.FILLED
        assert order.is_filled()
        assert len(order.fills) == 1
        assert order.filled_quantity == 0.5
        assert order.remaining_quantity == 0.0

    @pytest.mark.asyncio
    async def test_place_market_order_sell(self, fast_simulator):
        """Test placing a market sell order."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="sell",
            order_type="market",
            quantity=1.0,
        )

        assert order.side == "sell"
        assert order.state == OrderState.FILLED
        assert len(order.fills) == 1

    @pytest.mark.asyncio
    async def test_place_market_order_slippage(self, fast_simulator):
        """Test that market orders have slippage applied."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        fill = order.fills[0]
        # Buy should have higher price (slippage)
        assert fill.price > 50000.0

    @pytest.mark.asyncio
    async def test_place_limit_order_pending(self, fast_simulator):
        """Test placing a limit order that doesn't immediately fill."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="sell",
            order_type="limit",
            quantity=1.0,
            price=55000.0,  # Above market
        )

        assert order.order_type == "limit"
        assert order.price == 55000.0
        # Should be pending since price hasn't crossed
        assert order.state == OrderState.PENDING
        assert len(order.fills) == 0

    @pytest.mark.asyncio
    async def test_place_limit_order_immediate_fill(self, fast_simulator):
        """Test placing a limit order that fills immediately."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        # Buy limit at 51000 when market is 50000 - should fill
        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=1.0,
            price=51000.0,
        )

        assert order.state == OrderState.FILLED
        assert len(order.fills) == 1
        assert order.fills[0].price == 51000.0  # Fills at limit price

    @pytest.mark.asyncio
    async def test_place_invalid_order(self, fast_simulator):
        """Test that invalid orders are rejected."""
        # No market price set, so market order should be rejected
        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        assert order.state == OrderState.REJECTED
        assert order.reject_reason is not None

    @pytest.mark.asyncio
    async def test_place_order_negative_quantity(self, fast_simulator):
        """Test that negative quantity orders are rejected."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        # PaperOrder validates in __post_init__, which raises ValueError
        # The simulator catches this and rejects the order
        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=-1.0,
        )

        assert order.state == OrderState.REJECTED
        assert "Invalid quantity" in (order.reject_reason or "")

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, fast_simulator):
        """Test cancelling a pending order."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        # Place a limit order above market (won't fill)
        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="sell",
            order_type="limit",
            quantity=1.0,
            price=55000.0,
        )

        assert order.state == OrderState.PENDING

        # Cancel it
        result = await fast_simulator.cancel_order(order.order_id)

        assert result is True
        assert order.state == OrderState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_order_filled_fails(self, fast_simulator):
        """Test that cancelling a filled order fails."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        assert order.state == OrderState.FILLED

        result = await fast_simulator.cancel_order(order.order_id)

        assert result is False
        assert order.state == OrderState.FILLED

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, fast_simulator):
        """Test cancelling a non-existent order."""
        result = await fast_simulator.cancel_order("non_existent_id")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_order(self, fast_simulator):
        """Test getting an order by ID."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        retrieved = fast_simulator.get_order(order.order_id)

        assert retrieved is not None
        assert retrieved.order_id == order.order_id

    def test_get_order_not_found(self, fast_simulator):
        """Test getting a non-existent order."""
        order = fast_simulator.get_order("non_existent")

        assert order is None

    @pytest.mark.asyncio
    async def test_get_orders_no_filter(self, fast_simulator):
        """Test getting all orders."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)
        fast_simulator.set_market_price("ETHUSDT", 3000.0)

        await fast_simulator.place_order("BTCUSDT", "buy", "market", 1.0)
        await fast_simulator.place_order("ETHUSDT", "sell", "market", 2.0)

        orders = fast_simulator.get_orders()

        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_get_orders_filter_symbol(self, fast_simulator):
        """Test getting orders filtered by symbol."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)
        fast_simulator.set_market_price("ETHUSDT", 3000.0)

        await fast_simulator.place_order("BTCUSDT", "buy", "market", 1.0)
        await fast_simulator.place_order("ETHUSDT", "sell", "market", 2.0)

        btc_orders = fast_simulator.get_orders(symbol="BTCUSDT")

        assert len(btc_orders) == 1
        assert btc_orders[0].symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_get_orders_filter_state(self, fast_simulator):
        """Test getting orders filtered by state."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        await fast_simulator.place_order("BTCUSDT", "buy", "market", 1.0)

        filled_orders = fast_simulator.get_orders(state=OrderState.FILLED)
        pending_orders = fast_simulator.get_orders(state=OrderState.PENDING)

        assert len(filled_orders) == 1
        assert len(pending_orders) == 0

    @pytest.mark.asyncio
    async def test_get_orders_filter_side(self, fast_simulator):
        """Test getting orders filtered by side."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        await fast_simulator.place_order("BTCUSDT", "buy", "market", 1.0)
        await fast_simulator.place_order("BTCUSDT", "sell", "market", 1.0)

        buy_orders = fast_simulator.get_orders(side="buy")

        assert len(buy_orders) == 1
        assert buy_orders[0].side == "buy"

    @pytest.mark.asyncio
    async def test_update_limit_orders_fill(self, fast_simulator):
        """Test updating limit orders when price crosses."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        # Place a sell limit at 52000 (above market)
        order = await fast_simulator.place_order(
            symbol="BTCUSDT",
            side="sell",
            order_type="limit",
            quantity=1.0,
            price=52000.0,
        )

        assert order.state == OrderState.PENDING

        # Update market price to cross the limit
        fast_simulator.set_market_price("BTCUSDT", 53000.0)

        # Update limit orders
        fills = await fast_simulator.update_limit_orders()

        assert len(fills) == 1
        assert order.state == OrderState.FILLED

    @pytest.mark.asyncio
    async def test_update_limit_orders_filter_symbol(self, fast_simulator):
        """Test updating limit orders for specific symbol."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)
        fast_simulator.set_market_price("ETHUSDT", 3000.0)

        # Place limit orders for both symbols
        await fast_simulator.place_order("BTCUSDT", "sell", "limit", 1.0, 52000.0)
        await fast_simulator.place_order("ETHUSDT", "sell", "limit", 1.0, 3200.0)

        # Update prices
        fast_simulator.set_market_price("BTCUSDT", 53000.0)
        fast_simulator.set_market_price("ETHUSDT", 3300.0)

        # Update only BTC orders
        fills = await fast_simulator.update_limit_orders(symbol="BTCUSDT")

        assert len(fills) == 1
        assert fills[0].symbol == "BTCUSDT"

    def test_set_market_price(self, fast_simulator):
        """Test setting market price convenience method."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        assert fast_simulator.get_market_price("BTCUSDT") == 50000.0

    def test_get_market_price(self, fast_simulator):
        """Test getting market price convenience method."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        price = fast_simulator.get_market_price("BTCUSDT")

        assert price == 50000.0

    @pytest.mark.asyncio
    async def test_get_position(self, fast_simulator):
        """Test getting position for a symbol."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        # Buy 1.0 BTC
        await fast_simulator.place_order("BTCUSDT", "buy", "market", 1.0)

        position = fast_simulator.get_position("BTCUSDT")

        assert position["symbol"] == "BTCUSDT"
        assert position["quantity"] == 1.0
        assert position["total_filled"] == 1.0
        assert position["avg_entry_price"] > 0

    @pytest.mark.asyncio
    async def test_get_position_with_sells(self, fast_simulator):
        """Test getting position with both buys and sells."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)

        # Buy 2.0 BTC, then sell 0.5 BTC
        await fast_simulator.place_order("BTCUSDT", "buy", "market", 2.0)
        await fast_simulator.place_order("BTCUSDT", "sell", "market", 0.5)

        position = fast_simulator.get_position("BTCUSDT")

        assert position["quantity"] == 1.5  # 2.0 - 0.5
        assert position["total_filled"] == 2.5  # 2.0 + 0.5

    @pytest.mark.asyncio
    async def test_get_position_empty(self, fast_simulator):
        """Test getting position with no orders."""
        position = fast_simulator.get_position("BTCUSDT")

        assert position["symbol"] == "BTCUSDT"
        assert position["quantity"] == 0.0
        assert position["avg_entry_price"] == 0.0
        assert position["total_filled"] == 0.0

    @pytest.mark.asyncio
    async def test_reset(self, fast_simulator):
        """Test resetting the simulator."""
        fast_simulator.set_market_price("BTCUSDT", 50000.0)
        await fast_simulator.place_order("BTCUSDT", "buy", "market", 1.0)

        assert len(fast_simulator.orders) == 1

        fast_simulator.reset()

        assert len(fast_simulator.orders) == 0
        assert fast_simulator.get_market_price("BTCUSDT") is None


class TestOrderSimulatorConfig:
    """Test OrderSimulatorConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = OrderSimulatorConfig()

        assert config.min_slippage_pct == 0.01
        assert config.max_slippage_pct == 0.05
        assert config.min_latency_ms == 50.0
        assert config.max_latency_ms == 200.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = OrderSimulatorConfig(
            min_slippage_pct=0.02,
            max_slippage_pct=0.10,
            min_latency_ms=100.0,
            max_latency_ms=500.0,
        )

        assert config.min_slippage_pct == 0.02
        assert config.max_slippage_pct == 0.10
        assert config.min_latency_ms == 100.0
        assert config.max_latency_ms == 500.0

    def test_create_simulator(self):
        """Test creating simulator from config."""
        config = OrderSimulatorConfig(
            min_slippage_pct=0.02,
            max_slippage_pct=0.03,
        )

        sim = config.create_simulator()

        assert isinstance(sim, OrderSimulator)
        assert sim.fill_model.slippage_config.min_slippage_pct == 0.02
        assert sim.fill_model.slippage_config.max_slippage_pct == 0.03


class TestIntegration:
    """Integration tests for the full paper trading flow."""

    @pytest.mark.asyncio
    async def test_full_trading_scenario(self):
        """Test a full trading scenario with multiple orders."""
        fill_model = FillModel(
            slippage_config=SlippageConfig(
                min_slippage_pct=0.01, max_slippage_pct=0.01
            ),
            latency_config=LatencyConfig(min_latency_ms=1.0, max_latency_ms=1.0),
        )
        sim = OrderSimulator(fill_model=fill_model)

        # Set up market
        sim.set_market_price("BTCUSDT", 50000.0)
        sim.set_market_price("ETHUSDT", 3000.0)

        # Place market buy for BTC
        btc_buy = await sim.place_order("BTCUSDT", "buy", "market", 0.5)
        assert btc_buy.state == OrderState.FILLED

        # Place limit sell for BTC at profit target
        btc_sell = await sim.place_order("BTCUSDT", "sell", "limit", 0.5, 55000.0)
        assert btc_sell.state == OrderState.PENDING

        # Place market buy for ETH
        eth_buy = await sim.place_order("ETHUSDT", "buy", "market", 2.0)
        assert eth_buy.state == OrderState.FILLED

        # Update BTC price to hit profit target
        sim.set_market_price("BTCUSDT", 56000.0)
        fills = await sim.update_limit_orders()

        assert len(fills) == 1
        assert btc_sell.state == OrderState.FILLED
        assert btc_sell.fills[0].price == 55000.0

        # Check positions
        btc_position = sim.get_position("BTCUSDT")
        assert btc_position["quantity"] == 0.0  # Bought and sold

        eth_position = sim.get_position("ETHUSDT")
        assert eth_position["quantity"] == 2.0

        # Verify all orders tracked
        all_orders = sim.get_orders()
        assert len(all_orders) == 3

        filled_orders = sim.get_orders(state=OrderState.FILLED)
        assert len(filled_orders) == 3
