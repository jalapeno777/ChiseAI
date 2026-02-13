"""Tests for Bybit connector.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

import time
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from data.exchange.bybit_connector import BybitConfig, BybitConnector


class TestBybitConfig:
    """Test BybitConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BybitConfig()
        assert config.api_key == ""
        assert config.api_secret == ""
        assert config.base_url == "https://api.bybit.com"
        assert config.testnet is False

    def test_testnet_config(self):
        """Test testnet configuration."""
        config = BybitConfig(testnet=True)
        assert config.base_url == "https://api-testnet.bybit.com"
        assert config.ws_url == "wss://stream-testnet.bybit.com/v5/public/linear"


class TestBybitConnector:
    """Test BybitConnector functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return BybitConfig(
            api_key="test_key",
            api_secret="test_secret",
        )

    @pytest.fixture
    def connector(self, config):
        """Create test connector."""
        return BybitConnector(config)

    @pytest.mark.asyncio
    async def test_connect(self, connector):
        """Test HTTP session initialization."""
        await connector.connect()
        assert connector._session is not None
        assert not connector._session.closed
        await connector.close()

    @pytest.mark.asyncio
    async def test_close(self, connector):
        """Test connection cleanup."""
        await connector.connect()
        await connector.close()
        assert connector._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self, config):
        """Test async context manager."""
        async with BybitConnector(config) as connector:
            assert connector._session is not None
        assert connector._session is None

    @pytest.mark.asyncio
    async def test_get_ticker(self, connector):
        """Test get_ticker method."""
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "65000.00",
                        "volume24h": "1000",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_ticker("BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/v5/market/tickers",
                params={"category": "linear", "symbol": "BTCUSDT"},
            )

    @pytest.mark.asyncio
    async def test_get_orderbook(self, connector):
        """Test get_orderbook method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "s": "BTCUSDT",
                "b": [["64999.00", "1.5"]],
                "a": [["65000.00", "2.0"]],
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_orderbook("BTCUSDT", limit=50)

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/v5/market/orderbook",
                params={"category": "linear", "symbol": "BTCUSDT", "limit": 50},
            )

    @pytest.mark.asyncio
    async def test_get_fills(self, connector):
        """Test get_fills method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "orderId": "test_order_1",
                        "execId": "exec_1",
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "execPrice": "65000.00",
                        "execQty": "0.1",
                        "execTime": "1704067200000",
                        "execFee": "6.50",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_fills(
                symbol="BTCUSDT",
                order_id="test_order_1",
                limit=50,
            )

            assert result == mock_response
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_positions(self, connector):
        """Test get_positions method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0.5",
                        "avgPrice": "64000.00",
                        "leverage": "10",
                        "markPrice": "65000.00",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_positions(symbol="BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/v5/position/list",
                params={"category": "linear", "symbol": "BTCUSDT"},
                signed=True,
            )

    @pytest.mark.asyncio
    async def test_get_stop_orders(self, connector):
        """Test get_stop_orders method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "orderId": "stop_1",
                        "symbol": "BTCUSDT",
                        "stopOrderType": "StopLoss",
                        "triggerPrice": "60000.00",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_stop_orders(symbol="BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once()

    def test_health_status(self, connector):
        """Test health status tracking."""
        health = connector.get_health()
        assert health.is_connected is False
        assert health.reconnect_count == 0

    def test_is_healthy(self, connector):
        """Test health check logic."""
        import time

        assert connector.is_healthy() is False

        connector._health.is_connected = True
        connector._health.last_message = time.time()
        assert connector.is_healthy() is True

    @pytest.mark.asyncio
    async def test_health_check(self, connector):
        """Test health_check method."""
        with patch.object(
            connector, "get_ticker", new_callable=AsyncMock
        ) as mock_ticker:
            mock_ticker.return_value = {"retCode": 0}
            connector._health.is_connected = True
            connector._health.last_message = time.time()

            result = await connector.health_check()

            assert result["healthy"] is True
            assert result["connected"] is True

    def test_callback_registration(self, connector):
        """Test callback registration."""
        callback_called = False

        def test_callback(data):
            nonlocal callback_called
            callback_called = True

        connector.on_message(test_callback)
        assert len(connector._message_callbacks) == 1

        # Test price callback
        price_called = False

        def price_callback(symbol, price):
            nonlocal price_called
            price_called = True

        connector.on_price(price_callback)
        assert len(connector._price_callbacks) == 1

    def test_reconnect_delays(self):
        """Test exponential backoff delays."""
        assert BybitConnector.RECONNECT_DELAYS == [1, 2, 4, 8, 16, 32, 60]
        assert BybitConnector.HEARTBEAT_INTERVAL == 30


class TestBybitWebSocket:
    """Test WebSocket functionality."""

    @pytest.fixture
    def connector(self):
        """Create test connector."""
        config = BybitConfig(api_key="test", api_secret="test")
        return BybitConnector(config)

    @pytest.mark.asyncio
    async def test_handle_message_ticker(self, connector):
        """Test handling ticker message."""
        price_updates = []

        def price_callback(symbol, price):
            price_updates.append((symbol, price))

        connector.on_price(price_callback)

        message = {
            "topic": "tickers.BTCUSDT",
            "data": {
                "symbol": "BTCUSDT",
                "lastPrice": "65000.00",
            },
        }

        await connector._handle_message(message)

        assert len(price_updates) == 1
        assert price_updates[0][0] == "BTCUSDT"
        assert price_updates[0][1] == Decimal("65000.00")

    @pytest.mark.asyncio
    async def test_handle_message_pong(self, connector):
        """Test handling pong message."""
        message = {"op": "pong"}

        await connector._handle_message(message)

        # Should update heartbeat timestamp
        assert connector._health.last_message > 0


class TestBybitSignature:
    """Test signature generation."""

    def test_generate_signature(self):
        """Test HMAC signature generation."""
        config = BybitConfig(api_key="key", api_secret="secret")
        connector = BybitConnector(config)

        timestamp = "1704067200000"
        signature = connector._generate_signature(timestamp, "")

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest

    def test_generate_signature_with_payload(self):
        """Test signature with payload."""
        config = BybitConfig(api_key="key", api_secret="secret")
        connector = BybitConnector(config)

        timestamp = "1704067200000"
        payload = "param1=value1&param2=value2"
        signature = connector._generate_signature(timestamp, payload)

        assert isinstance(signature, str)
        assert len(signature) == 64
