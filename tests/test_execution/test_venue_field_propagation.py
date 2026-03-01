#!/usr/bin/env python3
"""Tests for venue field propagation through the execution pipeline.

For ST-VENUE-001: Venue provenance fields implementation
Tests that venue fields flow correctly from Signal → Order → Fill → Outcome
"""

import pytest
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import Mock, MagicMock, patch

from src.ml.models.signal_outcome import (
    SignalOutcome,
    OutcomeType,
    SignalOutcomeStatus,
)
from src.data.execution.fill_model import Fill
from src.execution.persistence.outcome_persistence import OutcomePersistence


class TestSignalOutcomeVenuePropagation:
    """Test that SignalOutcome preserves venue fields through serialization."""

    def test_venue_fields_preserved_through_serialization(self):
        """Test venue fields survive full serialization roundtrip."""
        original = SignalOutcome(
            outcome_id=uuid4(),
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

        # Serialize to dict (as would happen for persistence)
        data = original.to_dict()

        # Deserialize from dict (as would happen when loading)
        restored = SignalOutcome.from_dict(data)

        # Verify all venue fields survived
        assert restored.execution_venue == "bybit_demo"
        assert restored.execution_mode == "demo"
        assert restored.execution_source == "bybit_demo_connector"
        assert restored.venue_metadata == {
            "connector_id": "demo-123",
            "is_paper_trade": True,
        }

    def test_venue_fields_in_all_serialization_methods(self):
        """Test venue fields are in all serialization methods."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            symbol="BTCUSDT",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={"key": "value"},
        )

        # Test to_dict
        dict_data = outcome.to_dict()
        assert dict_data["execution_venue"] == "bybit_demo"
        assert dict_data["execution_mode"] == "demo"
        assert dict_data["execution_source"] == "bybit_demo_connector"
        assert dict_data["venue_metadata"] == {"key": "value"}

        # Test to_db_dict
        db_data = outcome.to_db_dict()
        assert db_data["execution_venue"] == "bybit_demo"
        assert db_data["execution_mode"] == "demo"
        assert db_data["execution_source"] == "bybit_demo_connector"
        assert db_data["venue_metadata"] == {"key": "value"}

        # Test to_notification_dict
        notif_data = outcome.to_notification_dict()
        assert notif_data["execution_venue"] == "bybit_demo"
        assert notif_data["execution_mode"] == "demo"
        assert notif_data["execution_source"] == "bybit_demo_connector"


class TestFillToSignalOutcomeVenueFlow:
    """Test that venue fields flow correctly from Fill → SignalOutcome."""

    def test_fill_includes_venue_fields(self):
        """Test that Fill model includes venue fields."""
        fill = Fill(
            order_id="order-123",
            fill_id="fill-456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("50000"),
            quantity=Decimal("1.0"),
            timestamp=datetime.now(UTC),
            fee=Decimal("5.0"),
            fee_currency="USDT",
            exchange="bybit",
            execution_venue="bybit_demo",
            execution_mode="demo",
        )

        assert fill.execution_venue == "bybit_demo"
        assert fill.execution_mode == "demo"

    def test_fill_to_dict_includes_venue_fields(self):
        """Test Fill.to_dict() includes venue fields."""
        fill = Fill(
            order_id="order-123",
            fill_id="fill-456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("50000"),
            quantity=Decimal("1.0"),
            timestamp=datetime.now(UTC),
            fee=Decimal("5.0"),
            fee_currency="USDT",
            exchange="bybit",
            execution_venue="bybit_demo",
            execution_mode="demo",
        )

        data = fill.to_dict()

        assert data["execution_venue"] == "bybit_demo"
        assert data["execution_mode"] == "demo"

    def test_fill_from_dict_preserves_venue_fields(self):
        """Test Fill.from_dict() preserves venue fields."""
        data = {
            "order_id": "order-123",
            "fill_id": "fill-456",
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "50000",
            "quantity": "1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "fee": "5.0",
            "fee_currency": "USDT",
            "exchange": "bybit",
            "metadata": {},
            "execution_venue": "bybit_demo",
            "execution_mode": "demo",
        }

        fill = Fill.from_dict(data)

        assert fill.execution_venue == "bybit_demo"
        assert fill.execution_mode == "demo"

    def test_fill_from_bybit_response_venue_extraction(self):
        """Test that Fill.from_bybit_response extracts venue fields."""
        response = {
            "orderId": "order-123",
            "execId": "exec-456",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execPrice": "50000",
            "execQty": "1.0",
            "execTime": "1704067200000",
            "execFee": "5.0",
            "feeCurrency": "USDT",
            "execution_venue": "bybit_demo",
            "execution_mode": "demo",
        }

        fill = Fill.from_bybit_response(response)

        assert fill.execution_venue == "bybit_demo"
        assert fill.execution_mode == "demo"

    def test_fill_from_bitget_response_venue_extraction(self):
        """Test that Fill.from_bitget_response extracts venue fields."""
        response = {
            "orderId": "order-123",
            "tradeId": "trade-456",
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "50000",
            "baseVolume": "1.0",
            "cTime": "1704067200000",
            "fee": "5.0",
            "feeCoin": "USDT",
            "execution_venue": "bitget_demo",
            "execution_mode": "testnet",
        }

        fill = Fill.from_bitget_response(response)

        assert fill.execution_venue == "bitget_demo"
        assert fill.execution_mode == "testnet"


class TestOutcomePersistenceVenueFields:
    """Test that OutcomePersistence correctly persists venue fields."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = Mock()
        mock.set = Mock(return_value=True)
        mock.expire = Mock(return_value=True)
        mock.zadd = Mock(return_value=True)
        mock.ping = Mock(return_value=True)
        return mock

    @pytest.fixture
    def persistence(self, mock_redis):
        """Create OutcomePersistence with mock Redis."""
        return OutcomePersistence(redis_client=mock_redis)

    def test_persist_outcome_preserves_all_venue_fields(self, persistence, mock_redis):
        """Test that persist_outcome preserves all venue fields."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
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
            venue_metadata={
                "connector_id": "demo-123",
                "is_paper_trade": True,
                "api_endpoint": "https://api-demo.bybit.com",
            },
        )

        # Persist the outcome
        key = persistence.persist_outcome(outcome)

        # Verify key was returned
        assert key is not None

        # Parse stored data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify all venue fields are present and correct
        assert stored_data["execution_venue"] == "bybit_demo"
        assert stored_data["execution_mode"] == "demo"
        assert stored_data["execution_source"] == "bybit_demo_connector"
        assert stored_data["venue_metadata"] == {
            "connector_id": "demo-123",
            "is_paper_trade": True,
            "api_endpoint": "https://api-demo.bybit.com",
        }

    def test_persist_outcome_venue_fields_roundtrip(self, persistence, mock_redis):
        """Test venue fields survive persistence roundtrip."""
        original = SignalOutcome(
            outcome_id=uuid4(),
            symbol="ETHUSDT",
            execution_venue="local_sim",
            execution_mode="paper",
            execution_source="paper_trading",
            venue_metadata={"simulator": "OrderSimulator"},
        )

        # Persist
        key = persistence.persist_outcome(original)

        # Get stored data
        call_args = mock_redis.set.call_args
        stored_json = call_args[0][1]
        stored_data = json.loads(stored_json)

        # Restore from stored data
        restored = SignalOutcome.from_dict(stored_data)

        # Verify venue fields survived
        assert restored.execution_venue == "local_sim"
        assert restored.execution_mode == "paper"
        assert restored.execution_source == "paper_trading"
        assert restored.venue_metadata == {"simulator": "OrderSimulator"}


class TestRecapVenueData:
    """Test that recap includes venue data."""

    def test_outcome_to_notification_dict_includes_venue(self):
        """Test that notification dict includes venue for recaps."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="order-123",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("1.0"),
            entry_price=Decimal("50000"),
            exit_price=Decimal("55000"),
            pnl=Decimal("5000"),
            leverage=Decimal("10"),
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
        )

        # Get notification dict (used for recaps)
        notif = outcome.to_notification_dict()

        # Verify venue fields are present
        assert "execution_venue" in notif
        assert "execution_mode" in notif
        assert "execution_source" in notif

        # Verify values
        assert notif["execution_venue"] == "bybit_demo"
        assert notif["execution_mode"] == "demo"
        assert notif["execution_source"] == "bybit_demo_connector"

    def test_recap_can_access_venue_provenance(self):
        """Test that recap generation can access venue provenance."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="order-123",
            symbol="BTCUSDT",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={
                "api_endpoint": "https://api-demo.bybit.com",
                "api_key_prefix": "ABCD",
            },
        )

        # Simulate recap generation
        recap_data = {
            "outcome_id": str(outcome.outcome_id),
            "symbol": outcome.symbol,
            "venue": {
                "execution_venue": outcome.execution_venue,
                "execution_mode": outcome.execution_mode,
                "execution_source": outcome.execution_source,
                "metadata": outcome.venue_metadata,
            },
        }

        # Verify recap includes venue data
        assert recap_data["venue"]["execution_venue"] == "bybit_demo"
        assert recap_data["venue"]["execution_mode"] == "demo"
        assert (
            recap_data["venue"]["metadata"]["api_endpoint"]
            == "https://api-demo.bybit.com"
        )


class TestVenueEnforcementGateIntegration:
    """Test venue enforcement gate integration with venue fields."""

    def test_outcome_tracks_demo_venue_for_enforcement(self):
        """Test that outcomes track demo venue for enforcement verification."""
        # Simulate an order executed via Bybit demo connector
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="demo-order-123",
            symbol="BTCUSDT",
            side="Buy",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={
                "api_endpoint": "https://api-demo.bybit.com",
                "provenance_verified": True,
            },
        )

        # Verify venue fields can be used for enforcement
        assert outcome.execution_venue == "bybit_demo"
        assert outcome.execution_mode == "demo"
        assert outcome.venue_metadata.get("provenance_verified") is True

        # Simulate enforcement check
        is_demo_trade = (
            outcome.execution_venue == "bybit_demo"
            and outcome.execution_mode == "demo"
            and outcome.venue_metadata.get("provenance_verified") is True
        )

        assert is_demo_trade is True

    def test_outcome_distinguishes_demo_from_simulation(self):
        """Test that outcomes can distinguish demo from simulation."""
        # Demo trade
        demo_outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="demo-order-123",
            symbol="BTCUSDT",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={"provenance_verified": True},
        )

        # Simulated trade
        sim_outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="sim-order-456",
            symbol="BTCUSDT",
            execution_venue="local_sim",
            execution_mode="paper",
            execution_source="order_simulator",
            venue_metadata={"simulated": True},
        )

        # Verify they can be distinguished
        assert demo_outcome.execution_venue != sim_outcome.execution_venue
        assert demo_outcome.execution_mode != sim_outcome.execution_mode

        # Enforcement check would pass for demo
        demo_is_verified = (
            demo_outcome.execution_venue == "bybit_demo"
            and demo_outcome.venue_metadata.get("provenance_verified") is True
        )
        assert demo_is_verified is True

        # Enforcement check would fail for sim
        sim_is_verified = (
            sim_outcome.execution_venue == "bybit_demo"
            and sim_outcome.venue_metadata.get("provenance_verified") is True
        )
        assert sim_is_verified is False

    def test_venue_fields_support_reconciliation(self):
        """Test that venue fields support reconciliation between telemetry and persistence."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="order-123",
            symbol="BTCUSDT",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
        )

        # Simulate reconciliation data
        telemetry_data = {
            "order_id": "order-123",
            "execution_venue": "bybit_demo",
            "execution_mode": "demo",
        }

        persisted_data = outcome.to_dict()

        # Verify venue fields match
        assert persisted_data["execution_venue"] == telemetry_data["execution_venue"]
        assert persisted_data["execution_mode"] == telemetry_data["execution_mode"]


class TestVenueFieldPropagationPipeline:
    """End-to-end test of venue field propagation through the pipeline."""

    def test_full_pipeline_venue_propagation(self):
        """Test venue fields propagate through the entire pipeline."""
        # 1. Create a fill with venue data (from exchange)
        fill = Fill(
            order_id="order-123",
            fill_id="fill-456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("50000"),
            quantity=Decimal("1.0"),
            timestamp=datetime.now(UTC),
            fee=Decimal("5.0"),
            fee_currency="USDT",
            exchange="bybit",
            execution_venue="bybit_demo",
            execution_mode="demo",
        )

        # 2. Create outcome from fill (propagate venue fields)
        outcome = SignalOutcome(
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side.capitalize(),
            fill_price=fill.price,
            fill_quantity=fill.quantity,
            fill_timestamp=fill.timestamp,
            fee=fill.fee,
            execution_venue=fill.execution_venue,
            execution_mode=fill.execution_mode,
            execution_source="bybit_demo_connector",
            venue_metadata={"fill_id": fill.fill_id},
        )

        # 3. Verify venue fields propagated
        assert outcome.execution_venue == "bybit_demo"
        assert outcome.execution_mode == "demo"
        assert outcome.execution_source == "bybit_demo_connector"

        # 4. Serialize for persistence
        data = outcome.to_dict()

        # 5. Verify venue fields in serialized data
        assert data["execution_venue"] == "bybit_demo"
        assert data["execution_mode"] == "demo"
        assert data["execution_source"] == "bybit_demo_connector"

        # 6. Deserialize
        restored = SignalOutcome.from_dict(data)

        # 7. Verify venue fields survived
        assert restored.execution_venue == "bybit_demo"
        assert restored.execution_mode == "demo"
        assert restored.execution_source == "bybit_demo_connector"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
