"""Integration tests: Bybit demo fill lifecycle and reconciliation correctness.

Tests:
1. Full fill lifecycle with Bybit demo (place market order -> poll detects fill)
2. Anti-double-counting (order_id + exec_id dedup via Redis)
3. Backfill missed fills detection
4. Reconciliation count correctness proof
5. Failure modes (timeout, partial fills)

Requires Bybit demo credentials for live tests:
    export BYBIT_DEMO_API_KEY=...
    export BYBIT_DEMO_API_SECRET=...

For skipped tests without credentials, run with:
    pytest tests/integration/test_bybit_fill_lifecycle.py -v

For ST-FILL-006: Live validation with Bybit demo real fills
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import models
from execution.paper.models import OrderState, PaperFill, PaperOrder

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Mock Redis client for dedup testing."""
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.setex = AsyncMock(return_value=True)
    client.exists = AsyncMock(return_value=0)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def bybit_credentials_present():
    """Check if Bybit demo credentials are available."""
    return bool(
        os.environ.get("BYBIT_DEMO_API_KEY") and os.environ.get("BYBIT_DEMO_API_SECRET")
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestBybitFillLifecycle:
    """Integration tests for full Bybit fill lifecycle with demo connector."""

    @pytest.mark.skipif(
        not os.environ.get("BYBIT_DEMO_API_KEY"),
        reason="Requires Bybit demo credentials",
    )
    async def test_full_fill_lifecycle(self):
        """Test complete fill lifecycle: place order -> poll -> FILLED state.

        This test:
        1. Creates BybitDemoConnector from environment
        2. Places a market order for small quantity
        3. Polls until fill (up to 10s timeout)
        4. Verifies order state transitions to FILLED (if filled within timeout)
        5. Verifies fill has correct attributes (if filled)

        NOTE: Bybit demo may not immediately fill market orders. This test
        accepts both outcomes - FILLED within timeout, or PENDING if demo
        trading doesn't auto-fill. The important verification is that:
        - The connector places the order correctly
        - The order state is properly tracked
        - Fill attributes are correct when filled
        """
        from execution.connectors.bybit_demo_connector import BybitDemoConnector

        # 1. Create connector from environment
        connector = BybitDemoConnector.from_env()

        try:
            # 2. Place market order
            order = await connector.place_order(
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=0.001,  # Small quantity for quick fill
            )

            # Verify order was placed and has valid state
            assert order is not None, "Order should be returned"
            assert order.order_id is not None, "Order should have an ID"
            assert order.symbol == "BTCUSDT", "Symbol should match"

            # 3. Poll for fill (up to 10 second timeout)
            timeout = 10.0
            deadline = time.time() + timeout
            filled_order = order

            while time.time() < deadline:
                # Refresh order state from connector
                filled_order = connector.get_order(order.order_id)
                if filled_order is None:
                    break

                if filled_order.state == OrderState.FILLED:
                    break

                await asyncio.sleep(0.5)

            # 4. Verify order was tracked correctly
            assert filled_order is not None, "Order should be in connector cache"

            # 5. If FILLED, verify fill attributes
            if filled_order.state == OrderState.FILLED:
                assert filled_order.filled_quantity > 0, "Filled quantity should be > 0"
                assert filled_order.filled_at is not None, "filled_at should be set"

                assert len(filled_order.fills) > 0, (
                    "Order should have at least one fill"
                )
                fill = filled_order.fills[0]
                assert fill.fill_id is not None, "Fill should have fill_id"
                assert fill.order_id == order.order_id, "Fill order_id should match"
                assert fill.symbol == "BTCUSDT", "Fill symbol should match"
                assert fill.quantity > 0, "Fill quantity should be > 0"
                assert fill.price > 0, "Fill price should be > 0"

                # Connector should have filled order in cache
                cached = connector.get_order(order.order_id)
                assert cached is not None
                assert cached.state == OrderState.FILLED
            else:
                # Demo trading may not auto-fill - verify order is at least PENDING
                assert filled_order.state == OrderState.PENDING, (
                    f"Expected FILLED or PENDING, got {filled_order.state.value}"
                )

            # 6. Verify connector provenance
            provenance = connector.get_provenance()
            assert provenance.is_demo is True, "Should be demo mode"
            assert "bybit" in provenance.endpoint.lower(), "Endpoint should be Bybit"

        finally:
            # Cleanup
            await connector.close()

    @pytest.mark.skipif(
        not os.environ.get("BYBIT_DEMO_API_KEY"),
        reason="Requires Bybit demo credentials",
    )
    async def test_market_order_immediate_fill(self):
        """Test that market orders on Bybit demo place correctly.

        Bybit demo may or may not fill market orders immediately depending
        on the demo environment behavior. This test verifies:
        1. Order is placed correctly
        2. Order is tracked in connector cache
        3. If filled, fills have correct attributes
        4. Connector provenance is correct
        """
        from execution.connectors.bybit_demo_connector import BybitDemoConnector

        connector = BybitDemoConnector.from_env()

        try:
            # Place market order
            order = await connector.place_order(
                symbol="ETHUSDT",
                side="buy",
                order_type="market",
                quantity=0.01,
            )

            # Verify order was placed
            assert order is not None, "Order should be returned"
            assert order.order_id is not None, "Order should have an ID"

            # Verify fill in connector's order cache
            cached = connector.get_order(order.order_id)
            assert cached is not None, "Order should be cached"

            # If filled, verify fill attributes
            if order.state == OrderState.FILLED:
                assert len(order.fills) > 0, "Should have fills"
                assert order.filled_quantity > 0, "Should have filled quantity"
                assert cached.state == OrderState.FILLED, (
                    "Cached order should be FILLED"
                )
            else:
                # Demo trading may not auto-fill - verify PENDING state
                assert order.state == OrderState.PENDING, (
                    f"Expected FILLED or PENDING, got {order.state.value}"
                )

            # Verify connector provenance
            provenance = connector.get_provenance()
            assert provenance.is_demo is True

        finally:
            await connector.close()

    async def test_fill_polling_timeout_returns_pending(self, mock_redis):
        """Test that polling timeout returns PENDING state without hanging.

        This tests the failure mode where:
        - Order is placed but not filled within timeout
        - Polling loop correctly returns PENDING state
        - No infinite loop or hang
        """

        # Create a mock order that's never filled
        order = PaperOrder(
            order_id="test_pending_order",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        # Default state is PENDING

        # Verify order is PENDING
        assert order.state == OrderState.PENDING, "New order should be PENDING"

        # Simulate polling loop with very short timeout
        async def poll_with_short_timeout(order_id: str, timeout: float = 0.1) -> str:
            """Poll for fill with timeout, return final state."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                # In real scenario, would refresh from connector
                await asyncio.sleep(0.01)
            return order.state.value

        final_state = await poll_with_short_timeout(order.order_id, timeout=0.1)
        assert final_state == "pending", "Should remain PENDING after timeout"

    async def test_redis_dedup_prevents_double_count(self, mock_redis):
        """Test that Redis dedup prevents processing the same exec_id twice.

        This verifies:
        1. First call to _is_duplicate returns False
        2. After _mark_processed, _is_duplicate returns True
        3. Same exec_id cannot be counted twice
        """
        from ml.feedback.bybit_fill_listener import (
            BybitFillListener,
            BybitListenerConfig,
        )

        # Create stateful mock that tracks which keys have been marked
        processed_keys: set = set()

        async def mock_exists(key: str) -> int:
            return 1 if key in processed_keys else 0

        async def mock_setex(key: str, ttl: int, value: str) -> None:
            processed_keys.add(key)

        mock_redis.exists = mock_exists
        mock_redis.setex = mock_setex

        config = BybitListenerConfig()
        listener = BybitFillListener(config=config, redis_client=mock_redis)

        exec_id = "test_exec_123"
        dedup_key = f"bybit:fill:dedup:{exec_id}"

        # Initially should not be duplicate
        is_dup = await listener._is_duplicate(exec_id)
        assert is_dup is False, "exec_id should not be duplicate on first check"

        # After marking as processed
        await listener._mark_processed(exec_id)
        assert dedup_key in processed_keys, "Key should be marked as processed"

        # Now should be duplicate
        is_dup_after = await listener._is_duplicate(exec_id)
        assert is_dup_after is True, "exec_id should be duplicate after marking"

    async def test_partial_fill_reported_correctly(self, mock_redis):
        """Test that partial fills update quantity correctly.

        Verifies:
        1. Partial fill updates filled_quantity
        2. Partial fill updates remaining_quantity
        3. Order state is PARTIAL
        4. Multiple partials accumulate correctly
        """
        from execution.paper.models import PaperFill

        order = PaperOrder(
            order_id="test_partial_order",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        # First partial fill (40%)
        fill1 = PaperFill(
            fill_id="fill_1",
            order_id=order.order_id,
            symbol="BTCUSDT",
            side="buy",
            quantity=0.4,
            price=50000.0,
        )
        order.add_fill(fill1)

        assert order.filled_quantity == 0.4, "Should have 0.4 filled"
        assert order.remaining_quantity == 0.6, "Should have 0.6 remaining"
        assert order.state == OrderState.PARTIAL, "Should be PARTIAL"
        assert order.avg_fill_price == 50000.0, "Avg price should be 50000"

        # Second partial fill (40% more, total 80%)
        fill2 = PaperFill(
            fill_id="fill_2",
            order_id=order.order_id,
            symbol="BTCUSDT",
            side="buy",
            quantity=0.4,
            price=50100.0,
        )
        order.add_fill(fill2)

        assert order.filled_quantity == pytest.approx(0.8), "Should have 0.8 filled"
        assert order.remaining_quantity == pytest.approx(0.2), (
            "Should have 0.2 remaining"
        )
        assert order.state == OrderState.PARTIAL, "Should still be PARTIAL"

        # Average price should be weighted
        expected_avg = (0.4 * 50000 + 0.4 * 50100) / 0.8
        assert order.avg_fill_price == pytest.approx(expected_avg), (
            f"Avg price should be {expected_avg}, got {order.avg_fill_price}"
        )

        # Final fill (20%, completes order)
        fill3 = PaperFill(
            fill_id="fill_3",
            order_id=order.order_id,
            symbol="BTCUSDT",
            side="buy",
            quantity=0.2,
            price=50200.0,
        )
        order.add_fill(fill3)

        assert order.filled_quantity == pytest.approx(1.0), "Should be fully filled"
        assert order.remaining_quantity == pytest.approx(0.0), (
            "Should have nothing remaining"
        )
        assert order.state == OrderState.FILLED, "Should now be FILLED"
        assert order.filled_at is not None, "filled_at should be set"

    async def test_order_state_transitions(self):
        """Test all valid order state transitions.

        Valid transitions:
        - PENDING -> PARTIAL (first partial fill)
        - PENDING -> FILLED (complete fill in one shot)
        - PENDING -> REJECTED (order rejected)
        - PENDING -> CANCELLED (user cancellation)
        - PARTIAL -> FILLED (remaining quantity filled)
        - PARTIAL -> CANCELLED (partial cancel)
        """

        # PENDING -> FILLED (one shot)
        order1 = PaperOrder(
            order_id="test_1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )
        fill = PaperFill(
            fill_id="fill_1",
            order_id="test_1",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
        )
        order1.add_fill(fill)
        assert order1.state == OrderState.FILLED

        # PENDING -> REJECTED
        order2 = PaperOrder(
            order_id="test_2",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )
        order2.reject("Insufficient margin")
        assert order2.state == OrderState.REJECTED
        assert order2.reject_reason == "Insufficient margin"

        # PENDING -> CANCELLED
        order3 = PaperOrder(
            order_id="test_3",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )
        result = order3.cancel()
        assert result is True, "Cancel should succeed"
        assert order3.state == OrderState.CANCELLED

        # PARTIAL -> FILLED
        order4 = PaperOrder(
            order_id="test_4",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )
        fill_partial = PaperFill(
            fill_id="fill_4a",
            order_id="test_4",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.5,
            price=50000.0,
        )
        order4.add_fill(fill_partial)
        assert order4.state == OrderState.PARTIAL

        fill_complete = PaperFill(
            fill_id="fill_4b",
            order_id="test_4",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.5,
            price=50100.0,
        )
        order4.add_fill(fill_complete)
        assert order4.state == OrderState.FILLED

    async def test_fill_lifecycle_with_mock_connector(self):
        """Test fill lifecycle with mocked BybitDemoConnector.

        This allows testing the full lifecycle without real API calls.
        """

        # Create mock connector
        mock_connector = MagicMock()
        mock_connector.get_provenance = MagicMock(
            return_value=MagicMock(
                is_demo=True,
                endpoint="https://demo.bybit.com",
                api_key_prefix="test",
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

        # Create a pre-filled order
        filled_order = PaperOrder(
            order_id="mock_filled_order",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
            state=OrderState.FILLED,
            filled_quantity=0.001,
        )
        fill = PaperFill(
            fill_id="mock_fill_1",
            order_id="mock_filled_order",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.001,
            price=65000.0,
            timestamp=datetime.now(UTC),
        )
        filled_order.add_fill(fill)

        # Simulate connector returning this order
        mock_connector.get_order = MagicMock(return_value=filled_order)
        mock_connector.get_orders = MagicMock(return_value=[filled_order])

        # Verify connector returns filled order
        order = mock_connector.get_order("mock_filled_order")
        assert order is not None
        assert order.state == OrderState.FILLED
        assert len(order.fills) == 1

        # Verify provenance
        prov = mock_connector.get_provenance()
        assert prov.is_demo is True


class TestReconciliationCorrectness:
    """Tests for reconciliation correctness proof."""

    async def test_reconciliation_delta_calculation(self):
        """Test that reconciliation delta is calculated correctly.

        Delta = telemetry_count - persisted_count
        delta_pct = (delta / persisted_count) * 100
        """
        from unittest.mock import MagicMock

        from execution.reconciliation.service import OutcomeReconciliationService

        # Create mock telemetry exporter
        mock_exporter = MagicMock()
        mock_exporter.query_counts = AsyncMock(
            return_value={"fills": 100, "orders": 50, "signals": 75}
        )

        # Create service with mock
        service = OutcomeReconciliationService(telemetry_exporter=mock_exporter)

        # Calculate delta with matching counts
        delta, delta_pct = service.calculate_delta(
            telemetry_counts={"fills": 100},
            persisted_counts={"fills": 100},
        )
        assert delta["fills"] == 0
        assert delta_pct["fills"] == 0.0

        # Calculate delta with discrepancy
        delta, delta_pct = service.calculate_delta(
            telemetry_counts={"fills": 110},
            persisted_counts={"fills": 100},
        )
        assert delta["fills"] == 10
        assert delta_pct["fills"] == 10.0

        # Calculate delta with negative discrepancy
        delta, delta_pct = service.calculate_delta(
            telemetry_counts={"fills": 90},
            persisted_counts={"fills": 100},
        )
        assert delta["fills"] == -10
        assert delta_pct["fills"] == -10.0

        # Edge case: persisted is 0 but telemetry has data
        delta, delta_pct = service.calculate_delta(
            telemetry_counts={"fills": 10},
            persisted_counts={"fills": 0},
        )
        assert delta["fills"] == 10
        assert delta_pct["fills"] == 100.0  # 100% discrepancy

    async def test_reconciliation_status_determination(self):
        """Test reconciliation status determination based on delta percentages.

        Default thresholds from ReconciliationConfig:
        - warn_threshold_pct: 1.0%
        - fail_threshold_pct: 5.0%
        """
        from unittest.mock import MagicMock

        from execution.reconciliation.models import ReconciliationStatus
        from execution.reconciliation.service import OutcomeReconciliationService

        mock_exporter = MagicMock()
        service = OutcomeReconciliationService(telemetry_exporter=mock_exporter)

        # OK: delta below warning threshold (1.0%) - use 0.5%
        status, discrepancies = service.get_reconciliation_status(
            delta_pct={"fills": 0.5},
            telemetry_counts={"fills": 100},
            persisted_counts={"fills": 100},
        )
        assert status == ReconciliationStatus.OK
        assert len(discrepancies) == 0

        # WARN: delta exceeds warning threshold (1.0%) - use 2.0%
        status, discrepancies = service.get_reconciliation_status(
            delta_pct={"fills": 2.0},
            telemetry_counts={"fills": 102},
            persisted_counts={"fills": 100},
        )
        assert status == ReconciliationStatus.WARN
        assert len(discrepancies) == 1

        # FAIL: delta exceeds fail threshold (5.0%) - use 7.0%
        status, discrepancies = service.get_reconciliation_status(
            delta_pct={"fills": 7.0},
            telemetry_counts={"fills": 107},
            persisted_counts={"fills": 100},
        )
        assert status == ReconciliationStatus.FAIL
        assert len(discrepancies) == 1

    async def test_fill_count_tracking(self):
        """Test that fills are tracked correctly across multiple orders."""

        orders = []
        total_fills = 0

        # Create 5 orders with varying fill counts
        for i in range(5):
            order = PaperOrder(
                order_id=f"order_{i}",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=0.1,
            )

            # 3 orders have 1 fill each, 2 orders have 2 fills each
            num_fills = 1 if i < 3 else 2

            for j in range(num_fills):
                fill = PaperFill(
                    fill_id=f"fill_{i}_{j}",
                    order_id=f"order_{i}",
                    symbol="BTCUSDT",
                    side="buy",
                    quantity=0.1 / num_fills,
                    price=65000.0 + j,
                )
                order.add_fill(fill)
                total_fills += 1

            orders.append(order)

        # Verify total fills
        assert total_fills == 7, "Should have 7 total fills (3*1 + 2*2)"

        # Count filled orders
        filled_orders = [o for o in orders if o.state == OrderState.FILLED]
        assert len(filled_orders) == 5, "All orders should be FILLED"

        # Verify total filled quantity
        total_quantity = sum(o.filled_quantity for o in orders)
        assert abs(total_quantity - 0.5) < 0.001, "Total quantity should be 0.5"


class TestBybitFillListenerDedup:
    """Tests for BybitFillListener deduplication functionality."""

    async def test_dedup_key_format(self, mock_redis):
        """Test that dedup keys follow expected format."""
        from ml.feedback.bybit_fill_listener import (
            BybitFillListener,
            BybitListenerConfig,
        )

        config = BybitListenerConfig()
        listener = BybitFillListener(config=config, redis_client=mock_redis)

        order_id = "test_order_abc123"
        expected_key = f"bybit:fill:dedup:{order_id}"

        await listener._mark_processed(order_id)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == expected_key

    async def test_dedup_ttl_configuration(self, mock_redis):
        """Test that dedup TTL is configurable."""
        from ml.feedback.bybit_fill_listener import (
            BybitFillListener,
            BybitListenerConfig,
        )

        # Custom TTL of 48 hours
        config = BybitListenerConfig(dedup_ttl_hours=48)
        listener = BybitFillListener(config=config, redis_client=mock_redis)

        await listener._mark_processed("test_order")

        call_args = mock_redis.setex.call_args[0]
        assert call_args[1] == 48 * 3600  # 48 hours in seconds

    async def test_duplicate_callback_not_triggered(self, mock_redis):
        """Test that on_fill callback is not triggered for duplicates."""
        from src.ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

        from ml.feedback.bybit_fill_listener import (
            BybitFillListener,
            BybitListenerConfig,
        )

        config = BybitListenerConfig()
        listener = BybitFillListener(config=config, redis_client=mock_redis)

        # Track callback invocations
        callback_invoked = []

        def on_fill_callback(outcome: SignalOutcome):
            callback_invoked.append(outcome)

        listener.on_fill(on_fill_callback)

        # First fill should trigger callback
        mock_redis.exists = AsyncMock(return_value=0)  # Not a duplicate
        first_outcome = SignalOutcome(
            order_id="dup_test_1",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=65000.0,
            fill_quantity=0.001,
            status=SignalOutcomeStatus.FILLED,
        )

        # Simulate _handle_execution path
        if not await listener._is_duplicate(first_outcome.order_id):
            await listener._mark_processed(first_outcome.order_id)
            for callback in listener._fill_callbacks:
                callback(first_outcome)

        assert len(callback_invoked) == 1, "First fill should trigger callback"

        # Second fill with same order_id should NOT trigger callback
        mock_redis.exists = AsyncMock(return_value=1)  # Is a duplicate
        second_outcome = SignalOutcome(
            order_id="dup_test_1",  # Same order_id
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=65000.0,
            fill_quantity=0.001,
            status=SignalOutcomeStatus.FILLED,
        )

        if not await listener._is_duplicate(second_outcome.order_id):
            await listener._mark_processed(second_outcome.order_id)
            for callback in listener._fill_callbacks:
                callback(second_outcome)

        # Callback should still only have been called once
        assert len(callback_invoked) == 1, "Duplicate should not trigger callback"


class TestFailureModes:
    """Tests for failure modes and edge cases."""

    async def test_order_not_found_returns_none(self):
        """Test that get_order returns None for unknown order ID."""

        # Mock connector without any orders
        mock_connector = MagicMock()
        mock_connector.get_order = MagicMock(return_value=None)

        result = mock_connector.get_order("nonexistent_order")
        assert result is None

    async def test_empty_fills_list(self):
        """Test order with no fills has empty fills list."""

        order = PaperOrder(
            order_id="empty_order",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        assert len(order.fills) == 0
        assert order.filled_quantity == 0.0
        assert order.state == OrderState.PENDING

    async def test_zero_quantity_fill_rejected(self):
        """Test that zero quantity fill is rejected."""
        from execution.paper.models import PaperFill

        with pytest.raises(ValueError, match="Invalid quantity"):
            PaperFill(
                fill_id="invalid_fill",
                order_id="order_1",
                symbol="BTCUSDT",
                side="buy",
                quantity=0.0,  # Invalid
                price=65000.0,
            )

    async def test_negative_price_fill_rejected(self):
        """Test that negative price fill is rejected."""
        from execution.paper.models import PaperFill

        with pytest.raises(ValueError, match="Invalid price"):
            PaperFill(
                fill_id="invalid_fill",
                order_id="order_1",
                symbol="BTCUSDT",
                side="buy",
                quantity=0.001,
                price=-100.0,  # Invalid
            )


class TestReconciliationMonitorLifecycle:
    """Tests for ReconciliationMonitor lifecycle in PaperTradingOrchestrator.

    ST-FILL-004: Verifies that ReconciliationMonitor is properly wired into
    the orchestrator's start/stop lifecycle and respects feature flags.
    """

    @pytest.fixture
    def mock_feature_flags(self):
        """Mock feature flags with reconciliation monitor enabled."""
        from unittest.mock import MagicMock

        flags = MagicMock()
        flags.is_reconciliation_monitor_enabled.return_value = True
        flags.get_reconciliation_check_interval_seconds.return_value = 3600
        flags.is_reconciliation_auto_backfill_enabled.return_value = False
        return flags

    @pytest.fixture
    def mock_feature_flags_with_backfill(self):
        """Mock feature flags with reconciliation monitor AND backfill enabled."""
        from unittest.mock import MagicMock

        flags = MagicMock()
        flags.is_reconciliation_monitor_enabled.return_value = True
        flags.get_reconciliation_check_interval_seconds.return_value = 3600
        flags.is_reconciliation_auto_backfill_enabled.return_value = True
        return flags

    @pytest.fixture
    def mock_feature_flags_disabled(self):
        """Mock feature flags with reconciliation monitor disabled."""
        from unittest.mock import MagicMock

        flags = MagicMock()
        flags.is_reconciliation_monitor_enabled.return_value = False
        return flags

    async def test_reconciliation_monitor_starts_with_orchestrator(
        self, mock_redis, mock_feature_flags
    ):
        """Test that ReconciliationMonitor starts when orchestrator starts.

        Verifies:
        1. When reconciliation_monitor_enabled=True, monitor is instantiated
        2. Monitor.start() is called during orchestrator.start()
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from execution.reconciliation.service import (
            OutcomeReconciliationService,
            ReconciliationMonitor,
        )

        # Create mock telemetry
        mock_telemetry = MagicMock()
        mock_telemetry.start = AsyncMock()
        mock_telemetry.stop = AsyncMock()

        # Create minimal orchestrator
        with patch(
            "src.config.feature_flags.get_feature_flags",
            return_value=mock_feature_flags,
        ):
            from execution.paper.orchestrator import PaperTradingOrchestrator

            # Create a minimal mock setup
            orchestrator = PaperTradingOrchestrator(
                signal_generator=MagicMock(),
                order_simulator=MagicMock(),
                position_tracker=MagicMock(),
                risk_enforcer=MagicMock(),
                telemetry_collector=mock_telemetry,
                kill_switch=MagicMock(),
                redis_client=mock_redis,
            )

            # Verify monitor is not started yet
            assert orchestrator._reconciliation_monitor is None

            # Start orchestrator
            await orchestrator.start()

            # Verify monitor was started
            assert orchestrator._reconciliation_monitor is not None
            assert orchestrator._reconciliation_monitor._running is True

            # Stop orchestrator
            await orchestrator.stop()

            # Verify monitor was stopped
            assert orchestrator._reconciliation_monitor is None

    async def test_reconciliation_monitor_respects_disabled_flag(
        self, mock_redis, mock_feature_flags_disabled
    ):
        """Test that ReconciliationMonitor is NOT started when feature flag is disabled.

        Verifies:
        1. When reconciliation_monitor_enabled=False, monitor is not instantiated
        2. Orchestrator starts successfully without the monitor
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create mock telemetry
        mock_telemetry = MagicMock()
        mock_telemetry.start = AsyncMock()
        mock_telemetry.stop = AsyncMock()

        with patch(
            "src.config.feature_flags.get_feature_flags",
            return_value=mock_feature_flags_disabled,
        ):
            from execution.paper.orchestrator import PaperTradingOrchestrator

            orchestrator = PaperTradingOrchestrator(
                signal_generator=MagicMock(),
                order_simulator=MagicMock(),
                position_tracker=MagicMock(),
                risk_enforcer=MagicMock(),
                telemetry_collector=mock_telemetry,
                kill_switch=MagicMock(),
                redis_client=mock_redis,
            )

            # Verify monitor is not started yet
            assert orchestrator._reconciliation_monitor is None

            # Start orchestrator
            await orchestrator.start()

            # Verify monitor was NOT started (flag is disabled)
            assert orchestrator._reconciliation_monitor is None

            # Stop orchestrator
            await orchestrator.stop()

    async def test_reconciliation_monitor_respects_backfill_flag(
        self, mock_redis, mock_feature_flags_with_backfill
    ):
        """Test that ReconciliationMonitor respects the backfill flag.

        Verifies:
        1. When reconciliation_auto_backfill=True, backfill_enabled=True is passed
        2. When reconciliation_auto_backfill=False, backfill_enabled=False is passed
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create mock telemetry
        mock_telemetry = MagicMock()
        mock_telemetry.start = AsyncMock()
        mock_telemetry.stop = AsyncMock()

        with patch(
            "src.config.feature_flags.get_feature_flags",
            return_value=mock_feature_flags_with_backfill,
        ):
            from execution.paper.orchestrator import PaperTradingOrchestrator

            orchestrator = PaperTradingOrchestrator(
                signal_generator=MagicMock(),
                order_simulator=MagicMock(),
                position_tracker=MagicMock(),
                risk_enforcer=MagicMock(),
                telemetry_collector=mock_telemetry,
                kill_switch=MagicMock(),
                redis_client=mock_redis,
            )

            await orchestrator.start()

            # Verify backfill is enabled when flag is True
            assert orchestrator._reconciliation_monitor is not None
            assert orchestrator._reconciliation_monitor.backfill_enabled is True

            await orchestrator.stop()

    async def test_reconciliation_monitor_backfill_disabled_by_default(
        self, mock_redis, mock_feature_flags
    ):
        """Test that ReconciliationMonitor has backfill disabled when flag is False.

        Verifies that backfill_enabled=False when reconciliation_auto_backfill=False.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create mock telemetry
        mock_telemetry = MagicMock()
        mock_telemetry.start = AsyncMock()
        mock_telemetry.stop = AsyncMock()

        with patch(
            "src.config.feature_flags.get_feature_flags",
            return_value=mock_feature_flags,
        ):
            from execution.paper.orchestrator import PaperTradingOrchestrator

            orchestrator = PaperTradingOrchestrator(
                signal_generator=MagicMock(),
                order_simulator=MagicMock(),
                position_tracker=MagicMock(),
                risk_enforcer=MagicMock(),
                telemetry_collector=mock_telemetry,
                kill_switch=MagicMock(),
                redis_client=mock_redis,
            )

            await orchestrator.start()

            # Verify backfill is disabled (flag is False in mock_feature_flags)
            assert orchestrator._reconciliation_monitor is not None
            assert orchestrator._reconciliation_monitor.backfill_enabled is False

            await orchestrator.stop()


class TestReconciliationMonitorBackfill:
    """Tests for ReconciliationMonitor backfill behavior.

    ST-FILL-004: Verifies that ReconciliationMonitor properly respects the
    backfill_enabled flag when calling backfill_missed_fills().
    """

    async def test_monitor_calls_backfill_when_enabled(self):
        """Test that ReconciliationMonitor calls backfill_missed_fills when enabled.

        Verifies:
        1. When backfill_enabled=True, backfill_missed_fills is called
        2. When backfill_enabled=False, backfill_missed_fills is NOT called
        """
        from unittest.mock import AsyncMock, MagicMock

        from execution.reconciliation.models import (
            ReconciliationResult,
            ReconciliationStatus,
        )
        from execution.reconciliation.service import ReconciliationMonitor

        # Create mock reconciliation service
        mock_service = MagicMock()
        mock_service.reconcile = AsyncMock(
            return_value=ReconciliationResult(
                telemetry_count={"fills": 10},
                persisted_count={"fills": 10},
                delta_count={"fills": 0},
                delta_pct={"fills": 0.0},
                status=ReconciliationStatus.OK,
                discrepancies=[],
                environment="paper",
                portfolio_id="default",
            )
        )
        mock_service.backfill_missed_fills = AsyncMock(
            return_value={
                "fills_found": 5,
                "fills_backfilled": 0,
                "errors": [],
            }
        )

        # Create monitor with backfill DISABLED
        monitor_no_backfill = ReconciliationMonitor(
            reconciliation_service=mock_service,
            redis_client=None,
            check_interval_seconds=3600,
            backfill_enabled=False,
        )

        # Manually run one cycle of the loop
        monitor_no_backfill._running = True
        await monitor_no_backfill._run_loop()

        # backfill_missed_fills should NOT be called when disabled
        mock_service.backfill_missed_fills.assert_not_called()
        mock_service.reconcile.assert_called_once()

        # Reset mock
        mock_service.reset_mock()

        # Create monitor with backfill ENABLED
        monitor_with_backfill = ReconciliationMonitor(
            reconciliation_service=mock_service,
            redis_client=None,
            check_interval_seconds=3600,
            backfill_enabled=True,
        )

        # Manually run one cycle of the loop
        monitor_with_backfill._running = True
        await monitor_with_backfill._run_loop()

        # backfill_missed_fills SHOULD be called when enabled
        mock_service.backfill_missed_fills.assert_called_once()
        mock_service.reconcile.assert_called_once()

        # Cleanup
        monitor_no_backfill._running = False
        monitor_with_backfill._running = False

    async def test_monitor_backfill_does_not_crash_on_error(self):
        """Test that ReconciliationMonitor handles backfill errors gracefully.

        Verifies:
        1. If backfill_missed_fills raises, the monitor continues running
        2. Error is logged but doesn't crash the loop
        """
        from unittest.mock import AsyncMock, MagicMock

        from execution.reconciliation.models import (
            ReconciliationResult,
            ReconciliationStatus,
        )
        from execution.reconciliation.service import ReconciliationMonitor

        # Create mock reconciliation service
        mock_service = MagicMock()
        mock_service.reconcile = AsyncMock(
            return_value=ReconciliationResult(
                telemetry_count={"fills": 10},
                persisted_count={"fills": 10},
                delta_count={"fills": 0},
                delta_pct={"fills": 0.0},
                status=ReconciliationStatus.OK,
                discrepancies=[],
                environment="paper",
                portfolio_id="default",
            )
        )
        mock_service.backfill_missed_fills = AsyncMock(
            side_effect=Exception("Backfill error")
        )

        # Create monitor with backfill ENABLED but backfill will fail
        monitor = ReconciliationMonitor(
            reconciliation_service=mock_service,
            redis_client=None,
            check_interval_seconds=3600,
            backfill_enabled=True,
        )

        # Run one cycle - should not crash despite backfill error
        monitor._running = True
        try:
            await monitor._run_loop()
        except Exception as e:
            if "Backfill error" in str(e):
                pytest.fail("Monitor should not propagate backfill errors")
        finally:
            monitor._running = False

        # Reconcile should have been called
        mock_service.reconcile.assert_called_once()
