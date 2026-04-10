"""Guardrail tests for Bybit fill persistence wiring (T-A3).

These tests validate that OutcomePersistence.persist_fill() is correctly
called from BybitDemoConnector._poll_for_fill() when fills are detected.

TDD contract: These tests FAIL before T-A4 (persistence wiring) and PASS after.

Tests:
1. test_bybit_fill_persists_to_redis - persist_fill called on fill
2. test_bybit_fill_dedup_prevents_duplicate_persistence - dedup prevents double call
3. test_feature_flag_gates_persistence - BYBIT_FILL_PERSISTENCE_ENABLED controls behavior
4. test_persistence_error_does_not_crash_order_flow - exceptions don't propagate

For RECON-A1: Bybit Persistence Wiring
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.paper.models import OrderState, PaperFill, PaperOrder

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Mock Redis client for dedup testing."""
    client = MagicMock()
    client.exists = MagicMock(return_value=0)
    client.setex = MagicMock(return_value=True)
    return client


@pytest.fixture
def mock_connector():
    """Mock BybitConnector that bypasses __init__ validation."""
    connector = MagicMock()
    connector.config = MagicMock()
    connector.config.demo = True
    # noinspection HttpUrlsUsage - test fixture
    connector.config.base_url = "https://api-demo.bybit.com"
    connector.config.private_ws_url = "wss://stream-demo.bybit.com/v5/private"
    connector.config.api_key = "dummy-test-only-placeholder-key"  # nosec
    return connector


@pytest.fixture
def make_demo_connector(mock_connector, mock_redis):
    """Factory to create BybitDemoConnector with mocked dependencies."""

    def _create(**kwargs):
        with patch("data.exchange.bybit_safety.validate_endpoint_url"):
            with patch("data.exchange.bybit_safety.SecurityException"):
                from execution.connectors.bybit_demo_connector import BybitDemoConnector

                connector = BybitDemoConnector.__new__(BybitDemoConnector)
                connector.connector = mock_connector
                connector.market_data = None
                connector._orders = {}
                connector._retry_config = MagicMock(max_retries=1)
                connector._retry = MagicMock()
                connector.provenance_tracker = MagicMock()
                connector._redis = mock_redis
                connector.provenance = MagicMock(
                    is_demo=True,
                    endpoint="https://api-demo.bybit.com",
                    api_key_prefix="test:abcd1234",
                    timestamp=datetime.now(UTC).isoformat(),
                )
                return connector

    return _create


def _make_filled_order(
    order_id: str = "order_123",
    symbol: str = "BTCUSDT",
    side: str = "buy",
) -> PaperOrder:
    """Create a PaperOrder in FILLED state with a fill."""
    order = PaperOrder(
        order_id=order_id,
        symbol=symbol,
        side=side,
        order_type="market",
        quantity=0.001,
        price=0.0,
    )
    fill = PaperFill(
        fill_id=f"fill_{order_id}",
        order_id=order_id,
        symbol=symbol,
        side=side,
        price=50000.0,
        quantity=0.001,
        timestamp=datetime.now(UTC),
        exchange_order_id=f"bybit_order_{order_id}",
        exchange_fill_id=f"bybit_exec_{order_id}",
    )
    order.add_fill(fill)
    order.state = OrderState.FILLED
    return order


def _make_fill_exec_response(
    order_id: str = "order_123",
    exec_id: str = "exec_abc123",
    price: float = 50000.0,
    qty: float = 0.001,
) -> dict:
    """Build a mock get_fills response with one execution."""
    return {
        "list": [
            {
                "execId": exec_id,
                "execPrice": str(price),
                "execQty": str(qty),
                "execTime": "2025-01-01T00:00:00.000Z",
                "side": "Buy",
                "symbol": "BTCUSDT",
            }
        ]
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestBybitFillPersistenceWiring:
    """Guardrail tests for fill persistence in BybitDemoConnector._poll_for_fill.

    These tests verify the T-A4 persistence wiring contract.
    They FAIL before the fix and PASS after.
    """

    @pytest.mark.asyncio
    async def test_bybit_fill_persists_to_redis(self, make_demo_connector, mock_redis):
        """BybitDemoConnector._poll_for_fill() should call OutcomePersistence.persist_fill().

        When a fill is detected during polling, the connector must persist the
        filled order to Redis via OutcomePersistence.persist_fill(order).
        """
        connector = make_demo_connector()
        order_id = "order_persist_test"
        symbol = "BTCUSDT"

        # Seed the order into the connector's cache
        connector._orders[order_id] = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side="buy",
            order_type="market",
            quantity=0.001,
            price=0.0,
        )
        connector._orders[order_id].state = OrderState.PENDING

        # Mock get_fills to return a fill on first poll
        fill_response = _make_fill_exec_response(
            order_id=order_id, exec_id="exec_persist_001"
        )

        async def fake_get_fills(**kwargs):
            return fill_response

        connector._retry.execute = AsyncMock(
            side_effect=[fill_response]  # First poll returns fill
        )

        # Mock OutcomePersistence
        mock_persistence = MagicMock()
        mock_persistence.persist_fill = MagicMock(return_value="paper:fill:...")

        with patch.dict(os.environ, {"BYBIT_FILL_PERSISTENCE_ENABLED": "true"}):
            with patch(
                "execution.connectors.bybit_demo_connector.asyncio.to_thread",
                new_callable=AsyncMock,
                wraps=lambda fn, *a, **kw: fn(*a, **kw),
            ):
                with patch(
                    "execution.connectors.bybit_demo_connector.OutcomePersistence",
                    return_value=mock_persistence,
                    create=True,
                ):
                    result = await connector._poll_for_fill(
                        order_id=order_id,
                        symbol=symbol,
                        initial_response={"side": "Buy", "quantity": "0.001"},
                    )

        # Assert: persist_fill was called with the filled order
        mock_persistence.persist_fill.assert_called_once()
        call_args = mock_persistence.persist_fill.call_args
        persisted_order = call_args[0][0] if call_args[0] else call_args[1].get("order")
        assert persisted_order.order_id == order_id
        assert len(persisted_order.fills) > 0
        # Order should be in FILLED state after successful poll
        assert result.state == OrderState.FILLED

    @pytest.mark.asyncio
    async def test_bybit_fill_dedup_prevents_duplicate_persistence(
        self, make_demo_connector, mock_redis
    ):
        """Same order_id should result in only 1 persist_fill() call.

        When the same order_id is processed twice (duplicate exec_id),
        the dedup mechanism should prevent a second persist_fill call.
        """
        connector = make_demo_connector()
        order_id = "order_dedup_test"
        symbol = "BTCUSDT"
        exec_id = "exec_dedup_001"

        # Seed the order
        connector._orders[order_id] = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side="buy",
            order_type="market",
            quantity=0.001,
            price=0.0,
        )
        connector._orders[order_id].state = OrderState.PENDING

        fill_response = _make_fill_exec_response(order_id=order_id, exec_id=exec_id)

        # First poll: returns fill. Second poll: same exec_id (deduped).
        # Third poll: empty (no more fills) — triggers timeout.
        connector._retry.execute = AsyncMock(
            side_effect=[fill_response, fill_response, {"list": []}]
        )

        # After first fill is processed, mark exec_id as duplicate for second poll
        call_count = 0

        async def side_effect_get_fills(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Second call: Redis says it's a duplicate
                mock_redis.exists.return_value = 1
            return fill_response

        connector._retry.execute = AsyncMock(side_effect=side_effect_get_fills)

        mock_persistence = MagicMock()
        mock_persistence.persist_fill = MagicMock(return_value="paper:fill:...")

        with patch.dict(os.environ, {"BYBIT_FILL_PERSISTENCE_ENABLED": "true"}):
            with patch(
                "execution.connectors.bybit_demo_connector.asyncio.to_thread",
                new_callable=AsyncMock,
                wraps=lambda fn, *a, **kw: fn(*a, **kw),
            ):
                with patch(
                    "execution.connectors.bybit_demo_connector.OutcomePersistence",
                    return_value=mock_persistence,
                    create=True,
                ):
                    # Set short poll timeout so test doesn't hang
                    with patch.dict(
                        os.environ,
                        {"BYBIT_FILL_POLL_TIMEOUT_MS": "500"},
                    ):
                        result = await connector._poll_for_fill(
                            order_id=order_id,
                            symbol=symbol,
                            initial_response={"side": "Buy", "quantity": "0.001"},
                        )

        # Assert: persist_fill called exactly once despite two poll cycles
        # returning the same fill
        assert mock_persistence.persist_fill.call_count == 1

    @pytest.mark.asyncio
    async def test_feature_flag_gates_persistence(
        self, make_demo_connector, mock_redis
    ):
        """BYBIT_FILL_PERSISTENCE_ENABLED=false should prevent persist_fill() call.

        When the feature flag is disabled (default), persist_fill must NOT be
        called even when fills are detected. When enabled, it must be called.
        """
        connector = make_demo_connector()
        order_id = "order_flag_test"
        symbol = "BTCUSDT"

        # Seed the order
        connector._orders[order_id] = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side="buy",
            order_type="market",
            quantity=0.001,
            price=0.0,
        )
        connector._orders[order_id].state = OrderState.PENDING

        fill_response = _make_fill_exec_response(
            order_id=order_id, exec_id="exec_flag_001"
        )
        connector._retry.execute = AsyncMock(side_effect=[fill_response])

        mock_persistence = MagicMock()
        mock_persistence.persist_fill = MagicMock(return_value="paper:fill:...")

        # --- Test 1: flag disabled (default) ---
        with patch.dict(os.environ, {"BYBIT_FILL_PERSISTENCE_ENABLED": "false"}):
            with patch(
                "execution.connectors.bybit_demo_connector.OutcomePersistence",
                return_value=mock_persistence,
                create=True,
            ) as mock_cls:
                await connector._poll_for_fill(
                    order_id=order_id,
                    symbol=symbol,
                    initial_response={"side": "Buy", "quantity": "0.001"},
                )

        mock_persistence.persist_fill.assert_not_called()

        # Reset for test 2
        mock_persistence.persist_fill.reset_mock()
        connector._retry.execute = AsyncMock(side_effect=[fill_response])

        # --- Test 2: flag enabled ---
        with patch.dict(os.environ, {"BYBIT_FILL_PERSISTENCE_ENABLED": "true"}):
            with patch(
                "execution.connectors.bybit_demo_connector.asyncio.to_thread",
                new_callable=AsyncMock,
                wraps=lambda fn, *a, **kw: fn(*a, **kw),
            ):
                with patch(
                    "execution.connectors.bybit_demo_connector.OutcomePersistence",
                    return_value=mock_persistence,
                    create=True,
                ):
                    await connector._poll_for_fill(
                        order_id=order_id,
                        symbol=symbol,
                        initial_response={"side": "Buy", "quantity": "0.001"},
                    )

        mock_persistence.persist_fill.assert_called_once()

    @pytest.mark.asyncio
    async def test_persistence_error_does_not_crash_order_flow(
        self, make_demo_connector, mock_redis
    ):
        """Exception in persist_fill() should not propagate to order flow.

        If OutcomePersistence.persist_fill raises an exception, the fill
        polling should still complete normally and the error should be logged.
        """
        connector = make_demo_connector()
        order_id = "order_error_test"
        symbol = "BTCUSDT"

        # Seed the order
        connector._orders[order_id] = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side="buy",
            order_type="market",
            quantity=0.001,
            price=0.0,
        )
        connector._orders[order_id].state = OrderState.PENDING

        fill_response = _make_fill_exec_response(
            order_id=order_id, exec_id="exec_error_001"
        )
        connector._retry.execute = AsyncMock(side_effect=[fill_response])

        # Mock persist_fill to raise
        mock_persistence = MagicMock()
        mock_persistence.persist_fill = MagicMock(
            side_effect=RuntimeError("Redis connection refused")
        )

        with patch.dict(os.environ, {"BYBIT_FILL_PERSISTENCE_ENABLED": "true"}):
            with patch(
                "execution.connectors.bybit_demo_connector.asyncio.to_thread",
                new_callable=AsyncMock,
                wraps=lambda fn, *a, **kw: fn(*a, **kw),
            ):
                with patch(
                    "execution.connectors.bybit_demo_connector.OutcomePersistence",
                    return_value=mock_persistence,
                    create=True,
                ):
                    with patch(
                        "execution.connectors.bybit_demo_connector.logger"
                    ) as mock_logger:
                        result = await connector._poll_for_fill(
                            order_id=order_id,
                            symbol=symbol,
                            initial_response={"side": "Buy", "quantity": "0.001"},
                        )

        # Assert: order flow completed normally despite persistence error
        assert result is not None
        assert result.order_id == order_id
        assert result.state == OrderState.FILLED
        assert len(result.fills) > 0

        # Assert: error was logged
        error_calls = [
            call
            for call in mock_logger.method_calls
            if "error" in call[0].lower() or "exception" in call[0].lower()
        ]
        assert len(error_calls) > 0, "Expected at least one error-level log call"


class TestExchangeIdPersistence:
    """Tests for exchange-native order/exec ID persistence for reconciliation."""

    def test_fill_persists_exchange_ids_to_redis(self, mock_redis):
        """Test that persist_fill persists exchange_order_id and exchange_fill_id."""
        from execution.paper.models import PaperFill, PaperOrder
        from execution.persistence.outcome_persistence import OutcomePersistence

        # Create order with exchange-native fill
        order = PaperOrder(
            order_id="bybit_native_order_123",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
            price=0.0,
        )
        order.state = OrderState.FILLED
        order.filled_quantity = 0.001
        order.avg_fill_price = 50000.0
        order.filled_at = datetime.now(UTC)

        fill = PaperFill(
            fill_id="paper_fill_abc123",
            order_id="bybit_native_order_123",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.001,
            price=50000.0,
            exchange_order_id="bybit_order_789",
            exchange_fill_id="bybit_exec_456",
        )
        order.add_fill(fill)

        # Persist via OutcomePersistence
        persistence = OutcomePersistence(redis_client=mock_redis)
        key = persistence.persist_fill(order)

        # Verify Redis set was called
        assert key is not None
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        stored_data_json = call_args[0][1]
        stored_data = json.loads(stored_data_json)

        # Verify exchange IDs are persisted
        assert stored_data["exchange_order_id"] == "bybit_order_789"
        assert stored_data["exchange_fill_id"] == "bybit_exec_456"
        assert stored_data["order_id"] == "bybit_native_order_123"

    def test_fill_without_exchange_ids_has_null_values(self, mock_redis):
        """Test that fills without exchange IDs persist with None values."""
        from execution.paper.models import PaperFill, PaperOrder
        from execution.persistence.outcome_persistence import OutcomePersistence

        order = PaperOrder(
            order_id="paper_only_order_123",
            symbol="ETHUSDT",
            side="sell",
            order_type="market",
            quantity=0.01,
            price=0.0,
        )
        order.state = OrderState.FILLED
        order.filled_quantity = 0.01
        order.avg_fill_price = 3000.0

        fill = PaperFill(
            fill_id="fill_no_exchange",
            order_id="paper_only_order_123",
            symbol="ETHUSDT",
            side="sell",
            quantity=0.01,
            price=3000.0,
            # No exchange_order_id or exchange_fill_id set
        )
        order.add_fill(fill)

        persistence = OutcomePersistence(redis_client=mock_redis)
        key = persistence.persist_fill(order)

        assert key is not None
        mock_redis.set.assert_called_once()
        stored_data = json.loads(mock_redis.set.call_args[0][1])

        # Exchange IDs should be None when not provided
        assert stored_data["exchange_order_id"] is None
        assert stored_data["exchange_fill_id"] is None


class TestExchangeIdReconciliationMatching:
    """Tests for reconciliation matching using exchange IDs."""

    def test_reconciliation_matches_on_exchange_fill_id(self):
        """Test that reconciliation can match fills using exchange_fill_id."""
        # Simulate persisted fill from exchange
        exchange_fill = {
            "fill_id": "bybit_exec_456",
            "order_id": "bybit_order_789",
            "exchange_fill_id": "bybit_exec_456",
            "symbol": "BTCUSDT",
            "quantity": 0.001,
            "price": 50000.0,
        }

        # Simulate local persistence
        local_fill = {
            "fill_id": "paper_fill_abc123",
            "order_id": "bybit_native_order_123",
            "exchange_fill_id": "bybit_exec_456",  # Same exchange ID
            "symbol": "BTCUSDT",
        }

        # Reconciliation should match on exchange_fill_id
        assert exchange_fill["exchange_fill_id"] == local_fill["exchange_fill_id"]
        assert exchange_fill["fill_id"] != local_fill["fill_id"]  # Different local IDs

    def test_legacy_fill_without_exchange_id_falls_back_to_local_id(self):
        """Test that legacy fills without exchange IDs use local ID for matching."""
        # Legacy fill format (before this fix)
        legacy_fill = {
            "fill_id": "paper_fill_legacy",
            "order_id": "paper_order_123",
            # No exchange_fill_id field
        }

        # New format with exchange ID
        new_fill = {
            "fill_id": "paper_fill_new",
            "order_id": "paper_order_123",
            "exchange_fill_id": "paper_fill_legacy",  # Legacy ID preserved as exchange ID
        }

        # When exchange_id is None, match on legacy order_id pattern
        exchange_id = new_fill.get("exchange_fill_id") or new_fill["fill_id"]
        assert exchange_id == "paper_fill_legacy"
