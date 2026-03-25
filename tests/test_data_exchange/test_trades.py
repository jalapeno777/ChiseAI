"""Tests for Binance client trades endpoint."""

from unittest.mock import AsyncMock, patch

import pytest

from exchange_data.binance.client import BinanceClient
from exchange_data.binance.config import BinanceConfig


class TestGetRecentTrades:
    """Tests for get_recent_trades method."""

    @pytest.fixture
    def client(self):
        """Create BinanceClient instance."""
        return BinanceClient()

    @pytest.mark.asyncio
    async def test_get_recent_trades_success(self, client):
        """Test successful fetch of recent trades."""
        mock_response = [
            {
                "id": 12345,
                "price": "50000.00",
                "qty": "0.100",
                "time": 1700000000000,
                "isBuyerMaker": True,
            },
            {
                "id": 12344,
                "price": "49900.00",
                "qty": "0.200",
                "time": 1700000010000,
                "isBuyerMaker": False,
            },
        ]

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get_recent_trades("BTCUSDT", limit=500)

            assert len(result) == 2
            assert result[0]["id"] == 12345
            assert result[0]["price"] == "50000.00"
            assert result[1]["id"] == 12344
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][1] == "https://fapi.binance.com/fapi/v1/trades"
            assert call_args[1]["params"]["symbol"] == "BTCUSDT"
            assert call_args[1]["params"]["limit"] == 500

    @pytest.mark.asyncio
    async def test_get_recent_trades_empty(self, client):
        """Test empty response handling."""
        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = []
            result = await client.get_recent_trades("BTCUSDT")
            assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_trades_default_limit(self, client):
        """Test default limit is 500."""
        mock_response = [
            {"id": 1, "price": "100.00", "qty": "1.0", "time": 1, "isBuyerMaker": True}
        ]

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            await client.get_recent_trades("ETHUSDT")

            call_args = mock_request.call_args
            assert call_args[1]["params"]["limit"] == 500

    @pytest.mark.asyncio
    async def test_get_recent_trades_custom_limit(self, client):
        """Test custom limit parameter."""
        mock_response = []

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            await client.get_recent_trades("SOLUSDT", limit=100)

            call_args = mock_request.call_args
            assert call_args[1]["params"]["limit"] == 100


@pytest.mark.skipif(
    not __import__("os").getenv("CHISEAI_LIVE_API_TEST"),
    reason="Live API test - requires CHISEAI_LIVE_API_TEST=1",
)
class TestGetRecentTradesLive:
    """Live smoke tests for get_recent_trades (requires API credentials)."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return BinanceConfig()

    @pytest.mark.asyncio
    async def test_live_trades_fetch(self, config):
        """Live smoke test - fetch recent trades."""
        async with BinanceClient(config) as client:
            trades = await client.get_recent_trades("BTCUSDT", limit=10)
            assert isinstance(trades, list)
            if trades:
                assert "id" in trades[0]
                assert "price" in trades[0]
                assert "qty" in trades[0]
