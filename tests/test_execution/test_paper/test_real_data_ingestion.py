"""Tests for RealDataIngestion module."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.paper.real_data_ingestion import (
    DataFreshness,
    DataSource,
    MarketDataSnapshot,
    OrderBookEntry,
    OrderBookSnapshot,
    RealDataIngestion,
    TradeEntry,
)


class TestRealDataIngestion:
    """Test suite for RealDataIngestion class."""

    @pytest.fixture
    def mock_connector(self):
        """Create mock BybitDemoConnector."""
        connector = MagicMock()
        connector.health_check = AsyncMock(
            return_value={
                "healthy": True,
                "demo_mode": True,
                "endpoint": "https://demo.bybit.com",
            }
        )
        connector.close = AsyncMock()
        connector.connector = MagicMock()
        connector.connector.get_ticker = AsyncMock(
            return_value={
                "result": {
                    "orderbook": [
                        {"side": "buy", "price": "50000.0", "size": "1.5"},
                        {"side": "buy", "price": "49999.0", "size": "2.0"},
                        {"side": "sell", "price": "50001.0", "size": "1.0"},
                        {"side": "sell", "price": "50002.0", "size": "2.5"},
                    ],
                    "list": [{"lastPrice": "50000"}],
                }
            }
        )
        connector.connector.get_public_trade = AsyncMock(
            return_value={
                "result": [
                    {
                        "tradeId": "123",
                        "side": "Buy",
                        "price": "50000.0",
                        "size": "0.5",
                        "tradeTime": "1700000000000",
                    },
                    {
                        "tradeId": "124",
                        "side": "Sell",
                        "price": "50001.0",
                        "size": "0.3",
                        "tradeTime": "1700000001000",
                    },
                ]
            }
        )
        return connector

    @pytest.fixture
    def ingestion(self, mock_connector):
        """Create RealDataIngestion with mock connector."""
        return RealDataIngestion(
            connector=mock_connector,
            max_age_seconds=30,
        )

    @pytest.mark.asyncio
    async def test_connect_to_bybit_demo_success(self, ingestion, mock_connector):
        """Test successful connection to Bybit demo."""
        result = await ingestion.connect_to_bybit_demo()

        assert result is True
        assert ingestion.is_connected is True
        mock_connector.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_to_bybit_demo_failure(self, mock_connector):
        """Test failed connection to Bybit demo."""
        mock_connector.health_check = AsyncMock(return_value={"healthy": False})

        ingestion = RealDataIngestion(connector=mock_connector)
        result = await ingestion.connect_to_bybit_demo()

        assert result is False
        assert ingestion.is_connected is False

    @pytest.mark.asyncio
    async def test_subscribe_to_orderbook(self, ingestion, mock_connector):
        """Test order book subscription."""
        result = await ingestion.subscribe_to_orderbook("BTCUSDT")

        assert result is True
        order_book = ingestion.get_cached_order_book("BTCUSDT")
        assert order_book is not None
        assert order_book.symbol == "BTCUSDT"
        assert len(order_book.bids) == 2
        assert len(order_book.asks) == 2

    @pytest.mark.asyncio
    async def test_subscribe_to_trades(self, ingestion, mock_connector):
        """Test trade subscription."""
        result = await ingestion.subscribe_to_trades("BTCUSDT")

        assert result is True
        trades = ingestion.get_cached_trades("BTCUSDT")
        assert len(trades) == 2
        assert trades[0].symbol == "BTCUSDT"
        assert trades[0].side in ["buy", "sell"]

    def test_validate_data_freshness_fresh(self, ingestion):
        """Test fresh data validation."""
        ingestion._last_update["BTCUSDT"] = datetime.now(UTC)

        freshness = ingestion.validate_data_freshness("BTCUSDT")
        assert freshness == DataFreshness.FRESH

    def test_validate_data_freshness_stale(self, ingestion):
        """Test stale data validation."""
        ingestion._last_update["BTCUSDT"] = datetime.now(UTC) - timedelta(seconds=60)

        freshness = ingestion.validate_data_freshness("BTCUSDT", max_age_seconds=30)
        assert freshness == DataFreshness.STALE

    def test_validate_data_freshness_unknown(self, ingestion):
        """Test unknown data freshness."""
        freshness = ingestion.validate_data_freshness("BTCUSDT")
        assert freshness == DataFreshness.UNKNOWN

    @pytest.mark.asyncio
    async def test_fallback_to_historical(self, ingestion):
        """Test fallback to historical data."""
        fallback_called = False

        def fallback_handler(symbol):
            nonlocal fallback_called
            fallback_called = True
            return [
                TradeEntry(
                    trade_id="fallback_1",
                    symbol=symbol,
                    side="buy",
                    price=50000.0,
                    quantity=1.0,
                    timestamp=datetime.now(UTC),
                )
            ]

        ingestion._fallback_handler = fallback_handler
        result = await ingestion.fallback_to_historical("BTCUSDT")

        assert result is True
        assert fallback_called is True
        trades = ingestion.get_cached_trades("BTCUSDT")
        assert len(trades) == 1

    @pytest.mark.asyncio
    async def test_get_market_snapshot(self, ingestion, mock_connector):
        """Test getting complete market snapshot."""
        snapshot = await ingestion.get_market_snapshot("BTCUSDT")

        assert snapshot is not None
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.order_book is not None
        assert len(snapshot.recent_trades) >= 0
        assert snapshot.source in [DataSource.LIVE_BYBIT, DataSource.HISTORICAL]

    def test_clear_cache_all(self, ingestion):
        """Test clearing all cache."""
        ingestion._order_book_cache["BTCUSDT"] = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
        )
        ingestion._trades_cache["BTCUSDT"] = []
        ingestion._last_update["BTCUSDT"] = datetime.now(UTC)

        ingestion.clear_cache()

        assert len(ingestion._order_book_cache) == 0
        assert len(ingestion._trades_cache) == 0
        assert len(ingestion._last_update) == 0

    def test_clear_cache_symbol(self, ingestion):
        """Test clearing cache for specific symbol."""
        ingestion._order_book_cache["BTCUSDT"] = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
        )
        ingestion._order_book_cache["ETHUSDT"] = OrderBookSnapshot(
            symbol="ETHUSDT",
            timestamp=datetime.now(UTC),
        )

        ingestion.clear_cache("BTCUSDT")

        assert "BTCUSDT" not in ingestion._order_book_cache
        assert "ETHUSDT" in ingestion._order_book_cache

    @pytest.mark.asyncio
    async def test_close(self, ingestion, mock_connector):
        """Test closing ingestion."""
        await ingestion.close()

        assert ingestion.is_connected is False
        mock_connector.close.assert_called_once()

    def test_normalize_symbol(self):
        """Test symbol normalization."""
        assert RealDataIngestion._normalize_symbol("BTC/USDT") == "BTCUSDT"
        assert RealDataIngestion._normalize_symbol("ETH-USDT") == "ETHUSDT"
        assert RealDataIngestion._normalize_symbol("BTC:USDT") == "BTCUSDT"
        assert RealDataIngestion._normalize_symbol("btcusdt") == "BTCUSDT"


class TestOrderBookSnapshot:
    """Test suite for OrderBookSnapshot."""

    def test_is_valid(self):
        """Test order book validity check."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            bids=[OrderBookEntry(price=50000, quantity=1.0, side="bid")],
            asks=[OrderBookEntry(price=50001, quantity=1.0, side="ask")],
        )
        assert snapshot.is_valid() is True

    def test_is_valid_empty(self):
        """Test empty order book is invalid."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            bids=[],
            asks=[],
        )
        assert snapshot.is_valid() is False

    def test_get_mid_price(self):
        """Test mid price calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            bids=[OrderBookEntry(price=50000, quantity=1.0, side="bid")],
            asks=[OrderBookEntry(price=50002, quantity=1.0, side="ask")],
        )
        mid = snapshot.get_mid_price()
        assert mid == 50001.0

    def test_get_mid_price_no_entries(self):
        """Test mid price with no entries."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
        )
        mid = snapshot.get_mid_price()
        assert mid is None


class TestMarketDataSnapshot:
    """Test suite for MarketDataSnapshot."""

    def test_is_complete(self):
        """Test complete snapshot detection."""
        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            order_book=OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC),
                bids=[OrderBookEntry(price=50000, quantity=1.0, side="bid")],
                asks=[OrderBookEntry(price=50001, quantity=1.0, side="ask")],
            ),
            recent_trades=[
                TradeEntry(
                    trade_id="1",
                    symbol="BTCUSDT",
                    side="buy",
                    price=50000.0,
                    quantity=1.0,
                    timestamp=datetime.now(UTC),
                )
            ],
        )
        assert snapshot.is_complete() is True

    def test_is_complete_missing_orderbook(self):
        """Test incomplete snapshot without order book."""
        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            recent_trades=[],
        )
        assert snapshot.is_complete() is False
