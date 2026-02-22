"""Integration tests for Bybit connector with idempotency.

For ST-LAUNCH-003: Order Idempotency
"""

import pytest
from unittest.mock import AsyncMock, patch

from execution.order_idempotency import (
    DuplicateOrderException,
    IdempotencyStore,
    generate_client_order_id,
)


class TestBybitIdempotencyIntegration:
    """Test Bybit connector idempotency integration."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config that bypasses production check."""
        from data.exchange.bybit_connector import BybitConfig

        config = BybitConfig(demo=True, api_key="test", api_secret="test")
        return config

    @pytest.fixture
    def idempotency_store(self):
        """Create a fresh idempotency store."""
        store = IdempotencyStore(redis_client=None)
        yield store
        store.clear_local_store()

    @pytest.fixture
    def connector(self, mock_config, idempotency_store):
        """Create Bybit connector with idempotency store."""
        from data.exchange.bybit_connector import BybitConnector

        return BybitConnector(config=mock_config, idempotency_store=idempotency_store)

    def test_connector_has_idempotency_store(self, connector, idempotency_store):
        """Test that connector has the idempotency store."""
        assert connector._idempotency_store is idempotency_store

    @pytest.mark.asyncio
    async def test_place_order_generates_client_order_id(self, connector):
        """Test that place_order generates client_order_id."""
        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "retCode": 0,
                "result": {"orderId": "test_order_123", "orderStatus": "Created"},
            }

            result = await connector.place_order(
                symbol="BTCUSDT", side="Buy", order_type="Market", quantity=0.1
            )

            # Verify client_order_id was generated
            assert "client_order_id" in result
            assert result["client_order_id"] is not None
            assert "BTCUSDT" in result["client_order_id"]

    @pytest.mark.asyncio
    async def test_place_order_uses_provided_client_order_id(self, connector):
        """Test that place_order uses provided client_order_id."""
        custom_id = generate_client_order_id("BTCUSDT")

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "retCode": 0,
                "result": {"orderId": "test_order_123", "orderStatus": "Created"},
            }

            result = await connector.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                quantity=0.1,
                client_order_id=custom_id,
            )

            assert result["client_order_id"] == custom_id

    @pytest.mark.asyncio
    async def test_place_order_detects_duplicates(self, connector):
        """Test that duplicate orders are rejected."""
        client_id = generate_client_order_id("BTCUSDT")

        # First submission should succeed
        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "retCode": 0,
                "result": {"orderId": "test_order_1", "orderStatus": "Created"},
            }

            result1 = await connector.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                quantity=0.1,
                client_order_id=client_id,
            )
            assert result1["client_order_id"] == client_id

        # Second submission with same ID should fail
        with pytest.raises(DuplicateOrderException) as exc_info:
            await connector.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                quantity=0.1,
                client_order_id=client_id,
            )

        assert exc_info.value.client_order_id == client_id
        assert exc_info.value.symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_place_order_includes_orderlinkid(self, connector):
        """Test that orderLinkId is included in API request."""
        client_id = generate_client_order_id("BTCUSDT")

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "retCode": 0,
                "result": {"orderId": "test_order_123", "orderStatus": "Created"},
            }

            await connector.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                quantity=0.1,
                client_order_id=client_id,
            )

            # Verify orderLinkId was in the request params
            call_args = mock_request.call_args
            params = call_args[1]["params"] if call_args[1] else call_args[0][2]
            assert params["orderLinkId"] == client_id

    @pytest.mark.asyncio
    async def test_place_order_clears_on_failure(self, connector):
        """Test that idempotency key is cleared on API failure."""
        client_id = generate_client_order_id("BTCUSDT")

        # First attempt fails
        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = ValueError("API Error")

            with pytest.raises(ValueError):
                await connector.place_order(
                    symbol="BTCUSDT",
                    side="Buy",
                    order_type="Market",
                    quantity=0.1,
                    client_order_id=client_id,
                )

        # Should be able to retry since key was cleared
        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "retCode": 0,
                "result": {"orderId": "test_order_123", "orderStatus": "Created"},
            }

            # This should succeed now
            result = await connector.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                quantity=0.1,
                client_order_id=client_id,
            )

            assert result["client_order_id"] == client_id

    @pytest.mark.asyncio
    async def test_place_order_per_token_isolation(self, connector):
        """Test that different tokens allow same client_order_id."""
        shared_id = "shared_client_id"

        # Submit for BTC
        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "retCode": 0,
                "result": {"orderId": "btc_order", "orderStatus": "Created"},
            }

            result1 = await connector.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                quantity=0.1,
                client_order_id=shared_id,
            )
            assert result1["symbol"] == "BTCUSDT"

        # Same ID should work for ETH
        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "retCode": 0,
                "result": {"orderId": "eth_order", "orderStatus": "Created"},
            }

            result2 = await connector.place_order(
                symbol="ETHUSDT",
                side="Buy",
                order_type="Market",
                quantity=0.1,
                client_order_id=shared_id,
            )
            assert result2["symbol"] == "ETHUSDT"
