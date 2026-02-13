"""Tests for Bitget connector.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

import time
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from data.exchange.bitget_connector import BitgetConfig, BitgetConnector


class TestBitgetConfig:
    """Test BitgetConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BitgetConfig()
        assert config.api_key == ""
        assert config.api_secret == ""
        assert config.passphrase == ""
        assert config.base_url == "https://api.bitget.com"
        assert config.testnet is False


class TestBitgetConnector:
    """Test BitgetConnector functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return BitgetConfig(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_passphrase",
        )

    @pytest.fixture
    def connector(self, config):
        """Create test connector."""
        return BitgetConnector(config)

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
        async with BitgetConnector(config) as connector:
            assert connector._session is not None
        assert connector._session is None

    @pytest.mark.asyncio
    async def test_get_ticker(self, connector):
        """Test get_ticker method."""
        mock_response = {
            "code": "00000",
            "msg": "success",
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "lastPr": "65000.00",
                    "high24h": "66000.00",
                    "low24h": "64000.00",
                }
            ],
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_ticker("BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/api/v2/mix/market/ticker",
                params={"symbol": "BTCUSDT", "productType": "USDT-FUTURES"},
            )

    @pytest.mark.asyncio
    async def test_get_orderbook(self, connector):
        """Test get_orderbook method."""
        mock_response = {
            "code": "00000",
            "data": {
                "asks": [["65000.00", "2.0"]],
                "bids": [["64999.00", "1.5"]],
                "ts": "1704067200000",
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
                "/api/v2/mix/market/orderbook",
                params={
                    "symbol": "BTCUSDT",
                    "productType": "USDT-FUTURES",
                    "limit": 50,
                },
            )

    @pytest.mark.asyncio
    async def test_get_fills(self, connector):
        """Test get_fills method."""
        mock_response = {
            "code": "00000",
            "data": [
                {
                    "orderId": "test_order_1",
                    "tradeId": "trade_1",
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "price": "65000.00",
                    "baseVolume": "0.1",
                    "cTime": "1704067200000",
                    "fee": "6.50",
                    "feeCoin": "USDT",
                }
            ],
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_fills(
                symbol="BTCUSDT",
                order_id="test_order_1",
                limit=100,
            )

            assert result == mock_response
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_positions(self, connector):
        """Test get_positions method."""
        mock_response = {
            "code": "00000",
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "holdSide": "long",
                    "total": "0.5",
                    "averageOpenPrice": "64000.00",
                    "leverage": 10,
                    "marketPrice": "65000.00",
                }
            ],
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_positions(symbol="BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/api/v2/mix/position/all-position",
                params={"productType": "USDT-FUTURES", "symbol": "BTCUSDT"},
                signed=True,
            )

    @pytest.mark.asyncio
    async def test_get_stop_orders(self, connector):
        """Test get_stop_orders method."""
        mock_response = {
            "code": "00000",
            "data": [
                {
                    "orderId": "stop_1",
                    "symbol": "BTCUSDT",
                    "planType": "loss_plan",
                    "triggerPrice": "60000.00",
                }
            ],
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
            mock_ticker.return_value = {"code": "00000"}
            connector._health.is_connected = True
            connector._health.last_message = time.time()

            result = await connector.health_check()

            assert result["healthy"] is True
            assert result["connected"] is True

    def test_callback_registration(self, connector):
        """Test callback registration."""

        def test_callback(data):
            pass

        connector.on_message(test_callback)
        assert len(connector._message_callbacks) == 1

        def price_callback(symbol, price):
            pass

        connector.on_price(price_callback)
        assert len(connector._price_callbacks) == 1


class TestBitgetWebSocket:
    """Test WebSocket functionality."""

    @pytest.fixture
    def connector(self):
        """Create test connector."""
        config = BitgetConfig(api_key="test", api_secret="test", passphrase="test")
        return BitgetConnector(config)

    @pytest.mark.asyncio
    async def test_handle_message_ticker(self, connector):
        """Test handling ticker message."""
        price_updates = []

        def price_callback(symbol, price):
            price_updates.append((symbol, price))

        connector.on_price(price_callback)

        message = {
            "arg": {"channel": "ticker", "instId": "BTCUSDT"},
            "data": [{"instId": "BTCUSDT", "lastPr": "65000.00"}],
        }

        await connector._handle_message(message)

        assert len(price_updates) == 1
        assert price_updates[0][0] == "BTCUSDT"
        assert price_updates[0][1] == Decimal("65000.00")

    @pytest.mark.asyncio
    async def test_handle_message_subscribe(self, connector):
        """Test handling subscribe confirmation."""
        message = {"event": "subscribe", "arg": {"channel": "ticker"}}

        await connector._handle_message(message)
        # Should log but not raise

    @pytest.mark.asyncio
    async def test_handle_message_error(self, connector):
        """Test handling error message."""
        message = {"event": "error", "code": "400", "msg": "Invalid request"}

        await connector._handle_message(message)
        # Should log error but not raise


class TestBitgetSignature:
    """Test signature generation."""

    def test_generate_signature(self):
        """Test HMAC signature generation."""
        config = BitgetConfig(
            api_key="key", api_secret="secret", passphrase="passphrase"
        )
        connector = BitgetConnector(config)

        timestamp = "1704067200"
        signature, passphrase_sig = connector._generate_signature(
            timestamp, "GET", "/api/v2/test"
        )

        assert isinstance(signature, str)
        assert isinstance(passphrase_sig, str)
        # Base64 encoded SHA256
        assert len(signature) > 0
        assert len(passphrase_sig) > 0

    def test_generate_signature_with_body(self):
        """Test signature with request body."""
        config = BitgetConfig(
            api_key="key", api_secret="secret", passphrase="passphrase"
        )
        connector = BitgetConnector(config)

        timestamp = "1704067200"
        body = '{"symbol":"BTCUSDT"}'
        signature, passphrase_sig = connector._generate_signature(
            timestamp, "POST", "/api/v2/order", body
        )

        assert isinstance(signature, str)
        assert isinstance(passphrase_sig, str)
