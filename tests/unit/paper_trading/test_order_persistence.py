"""Tests for paper trading order persistence.

Tests for PAPER-NOGO-REMEDIATION-001: PaperOrder filled_at attribute fix.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

# Add src to path
sys.path.insert(0, "src")

from paper_trading.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
)


class TestPaperOrderFilledAt:
    """Test PaperOrder filled_at attribute."""

    def test_paper_order_has_filled_at_attribute(self):
        """Verify PaperOrder has filled_at attribute."""
        order = PaperOrder(
            order_id="test-001",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            state=OrderState.PENDING,
            created_at=datetime.now(UTC),
        )
        # Check attribute exists
        assert hasattr(order, "filled_at")

    def test_filled_at_is_none_for_new_orders(self):
        """Verify filled_at is None for newly created orders."""
        order = PaperOrder(
            order_id="test-002",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            state=OrderState.PENDING,
            created_at=datetime.now(UTC),
        )
        assert order.filled_at is None

    def test_filled_at_can_be_set_explicitly(self):
        """Verify filled_at can be set explicitly."""
        fill_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
        order = PaperOrder(
            order_id="test-003",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            state=OrderState.FILLED,
            created_at=datetime.now(UTC),
            filled_at=fill_time,
        )
        assert order.filled_at == fill_time

    def test_filled_at_serialization(self):
        """Verify filled_at serializes correctly."""
        fill_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
        order = PaperOrder(
            order_id="test-004",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            state=OrderState.FILLED,
            created_at=datetime.now(UTC),
            filled_at=fill_time,
        )
        data = order.to_dict()
        assert "filled_at" in data
        assert data["filled_at"] == "2026-03-15T12:00:00+00:00"

    def test_filled_at_serialization_none(self):
        """Verify filled_at serializes as None when not set."""
        order = PaperOrder(
            order_id="test-005",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            state=OrderState.PENDING,
            created_at=datetime.now(UTC),
        )
        data = order.to_dict()
        assert "filled_at" in data
        assert data["filled_at"] is None

    def test_persistence_roundtrip_with_filled_at(self):
        """Verify persistence roundtrip works with filled_at."""
        fill_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)

        # Create order with filled_at
        original_order = PaperOrder(
            order_id="test-006",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            filled_quantity=1.0,
            state=OrderState.FILLED,
            created_at=datetime.now(UTC),
            filled_at=fill_time,
        )

        # Serialize to dict (simulating persistence)
        order_data = original_order.to_dict()

        # Deserialize back (simulating loading from persistence)
        # Note: PaperOrder doesn't have a from_dict method, but it accepts
        # the dict via **kwargs when the field names match
        restored_order = PaperOrder(**order_data)

        # Verify filled_at is preserved
        assert restored_order.filled_at is not None
        assert restored_order.filled_at.isoformat() == fill_time.isoformat()

    def test_persistence_roundtrip_without_filled_at(self):
        """Verify persistence roundtrip works when filled_at is None."""
        # Create order without filled_at
        original_order = PaperOrder(
            order_id="test-007",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            state=OrderState.PENDING,
            created_at=datetime.now(UTC),
        )

        # Serialize to dict
        order_data = original_order.to_dict()

        # Deserialize back
        restored_order = PaperOrder(**order_data)

        # Verify filled_at is still None
        assert restored_order.filled_at is None


class TestPaperOrderCompatibility:
    """Test compatibility with existing code."""

    def test_order_creation_without_filled_at(self):
        """Verify existing code that doesn't pass filled_at still works."""
        # This is how orders were created before the fix
        order = PaperOrder(
            order_id="compat-001",
            symbol="ETH-USD",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=10.0,
            price=3000.0,
            filled_quantity=0.0,
            state=OrderState.OPEN,
            created_at=datetime.now(UTC),
        )
        assert order.filled_at is None
        assert order.order_id == "compat-001"

    def test_all_fields_preserved_in_dict(self):
        """Verify all fields are preserved when converting to dict."""
        created_time = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
        updated_time = datetime(2026, 3, 15, 11, 0, 0, tzinfo=UTC)
        fill_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)

        order = PaperOrder(
            order_id="compat-002",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.5,
            price=None,
            filled_quantity=1.5,
            avg_fill_price=65000.0,
            state=OrderState.FILLED,
            signal_id="signal-123",
            correlation_id="corr-456",
            created_at=created_time,
            updated_at=updated_time,
            filled_at=fill_time,
            metadata={"strategy": "test"},
        )

        data = order.to_dict()

        assert data["order_id"] == "compat-002"
        assert data["symbol"] == "BTC-USD"
        assert data["side"] == "buy"
        assert data["order_type"] == "market"
        assert data["quantity"] == 1.5
        assert data["price"] is None
        assert data["filled_quantity"] == 1.5
        assert data["avg_fill_price"] == 65000.0
        assert data["state"] == "filled"
        assert data["signal_id"] == "signal-123"
        assert data["correlation_id"] == "corr-456"
        assert data["created_at"] == "2026-03-15T10:00:00+00:00"
        assert data["updated_at"] == "2026-03-15T11:00:00+00:00"
        assert data["filled_at"] == "2026-03-15T12:00:00+00:00"
        assert data["metadata"] == {"strategy": "test"}
