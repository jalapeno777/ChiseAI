#!/usr/bin/env python3
"""Tests for SignalOutcome model with venue provenance fields.

For ST-VENUE-001: Venue provenance fields implementation
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from src.ml.models.signal_outcome import (
    SignalOutcome,
    SignalOutcomeStatus,
)


class TestSignalOutcomeVenueProvenance:
    """Test venue provenance fields in SignalOutcome."""

    def test_venue_fields_exist(self):
        """Test that venue provenance fields exist on SignalOutcome."""
        outcome = SignalOutcome()

        # Verify all venue fields exist
        assert hasattr(outcome, "execution_venue")
        assert hasattr(outcome, "execution_mode")
        assert hasattr(outcome, "execution_source")
        assert hasattr(outcome, "venue_metadata")

    def test_venue_fields_defaults(self):
        """Test venue fields have correct default values."""
        outcome = SignalOutcome()

        # Verify default values
        assert outcome.execution_venue == ""
        assert outcome.execution_mode == ""
        assert outcome.execution_source == ""
        assert outcome.venue_metadata == {}

    def test_venue_fields_assignment(self):
        """Test venue fields can be assigned values."""
        outcome = SignalOutcome()

        # Set venue fields
        outcome.execution_venue = "bybit_demo"
        outcome.execution_mode = "demo"
        outcome.execution_source = "bybit_demo_connector"
        outcome.venue_metadata = {"connector_id": "demo-123", "is_paper_trade": True}

        # Verify values
        assert outcome.execution_venue == "bybit_demo"
        assert outcome.execution_mode == "demo"
        assert outcome.execution_source == "bybit_demo_connector"
        assert outcome.venue_metadata == {
            "connector_id": "demo-123",
            "is_paper_trade": True,
        }

    def test_venue_fields_in_to_dict(self):
        """Test venue fields are included in to_dict() serialization."""
        outcome = SignalOutcome(
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("1.0"),
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={"connector_id": "demo-123"},
        )

        data = outcome.to_dict()

        # Verify venue fields in dict
        assert "execution_venue" in data
        assert "execution_mode" in data
        assert "execution_source" in data
        assert "venue_metadata" in data

        assert data["execution_venue"] == "bybit_demo"
        assert data["execution_mode"] == "demo"
        assert data["execution_source"] == "bybit_demo_connector"
        assert data["venue_metadata"] == {"connector_id": "demo-123"}

    def test_venue_fields_in_from_dict(self):
        """Test venue fields are correctly deserialized from dict."""
        signal_id = uuid4()
        data = {
            "outcome_id": str(uuid4()),
            "signal_id": str(signal_id),
            "order_id": "test-order-123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "direction": "LONG",
            "fill_price": "50000",
            "fill_quantity": "1.0",
            "fill_timestamp": datetime.now(UTC).isoformat(),
            "outcome_type": "filled",
            "status": "filled",
            "execution_venue": "bybit_demo",
            "execution_mode": "demo",
            "execution_source": "bybit_demo_connector",
            "venue_metadata": {"connector_id": "demo-123"},
        }

        outcome = SignalOutcome.from_dict(data)

        # Verify venue fields
        assert outcome.execution_venue == "bybit_demo"
        assert outcome.execution_mode == "demo"
        assert outcome.execution_source == "bybit_demo_connector"
        assert outcome.venue_metadata == {"connector_id": "demo-123"}

    def test_venue_fields_in_to_db_dict(self):
        """Test venue fields are included in to_db_dict() for database storage."""
        outcome = SignalOutcome(
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={"connector_id": "demo-123"},
        )

        data = outcome.to_db_dict()

        # Verify venue fields in db dict
        assert "execution_venue" in data
        assert "execution_mode" in data
        assert "execution_source" in data
        assert "venue_metadata" in data

        assert data["execution_venue"] == "bybit_demo"
        assert data["execution_mode"] == "demo"
        assert data["execution_source"] == "bybit_demo_connector"
        assert data["venue_metadata"] == {"connector_id": "demo-123"}

    def test_venue_fields_in_to_notification_dict(self):
        """Test venue fields are included in to_notification_dict()."""
        outcome = SignalOutcome(
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
        )

        data = outcome.to_notification_dict()

        # Verify venue fields in notification dict
        assert "execution_venue" in data
        assert "execution_mode" in data
        assert "execution_source" in data

        assert data["execution_venue"] == "bybit_demo"
        assert data["execution_mode"] == "demo"
        assert data["execution_source"] == "bybit_demo_connector"

    def test_venue_fields_roundtrip(self):
        """Test venue fields survive full serialization roundtrip."""
        original = SignalOutcome(
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("1.0"),
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={"connector_id": "demo-123", "is_paper_trade": True},
        )

        # Serialize to dict
        data = original.to_dict()

        # Deserialize from dict
        restored = SignalOutcome.from_dict(data)

        # Verify venue fields survived roundtrip
        assert restored.execution_venue == original.execution_venue
        assert restored.execution_mode == original.execution_mode
        assert restored.execution_source == original.execution_source
        assert restored.venue_metadata == original.venue_metadata

    def test_venue_fields_with_empty_defaults(self):
        """Test venue fields work with empty/default values."""
        outcome = SignalOutcome(
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
        )

        # Should have empty strings as defaults
        assert outcome.execution_venue == ""
        assert outcome.execution_mode == ""
        assert outcome.execution_source == ""
        assert outcome.venue_metadata == {}

        # Should serialize correctly
        data = outcome.to_dict()
        assert data["execution_venue"] == ""
        assert data["execution_mode"] == ""
        assert data["execution_source"] == ""
        assert data["venue_metadata"] == {}

    def test_venue_metadata_is_dict(self):
        """Test that venue_metadata is always a dict."""
        # Test default
        outcome = SignalOutcome()
        assert isinstance(outcome.venue_metadata, dict)

        # Test with values
        outcome.venue_metadata = {"key": "value"}
        assert isinstance(outcome.venue_metadata, dict)

        # Test after serialization
        data = outcome.to_dict()
        restored = SignalOutcome.from_dict(data)
        assert isinstance(restored.venue_metadata, dict)


class TestSignalOutcomeBasicFunctionality:
    """Test basic SignalOutcome functionality still works."""

    def test_basic_creation(self):
        """Test basic SignalOutcome creation."""
        signal_id = uuid4()
        outcome = SignalOutcome(
            signal_id=signal_id,
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("1.0"),
        )

        assert outcome.signal_id == signal_id
        assert outcome.order_id == "test-order-123"
        assert outcome.symbol == "BTCUSDT"
        assert outcome.side == "Buy"
        assert outcome.direction == "LONG"
        assert outcome.fill_price == Decimal("50000")
        assert outcome.fill_quantity == Decimal("1.0")

    def test_token_derivation(self):
        """Test token is derived from symbol."""
        outcome = SignalOutcome(symbol="BTCUSDT")
        assert outcome.token == "BTC"

        outcome2 = SignalOutcome(symbol="ETHUSD")
        assert outcome2.token == "ETH"

    def test_direction_derivation(self):
        """Test direction is derived from side."""
        outcome_buy = SignalOutcome(side="Buy")
        assert outcome_buy.direction == "LONG"

        outcome_sell = SignalOutcome(side="Sell")
        assert outcome_sell.direction == "SHORT"

    def test_fill_value_property(self):
        """Test fill_value property calculation."""
        outcome = SignalOutcome(
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("2.0"),
        )
        assert outcome.fill_value == Decimal("100000")

    def test_is_filled_property(self):
        """Test is_filled property."""
        outcome_pending = SignalOutcome(status=SignalOutcomeStatus.PENDING)
        assert not outcome_pending.is_filled

        outcome_filled = SignalOutcome(status=SignalOutcomeStatus.FILLED)
        assert outcome_filled.is_filled


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
