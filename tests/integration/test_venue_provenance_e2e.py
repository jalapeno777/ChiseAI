#!/usr/bin/env python3
"""End-to-end tests for venue provenance data flow.

For ST-VENUE-001: Venue provenance fields implementation
Tests end-to-end venue data flow through the entire pipeline.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from src.data.execution.fill_model import Fill, FillBatch
from src.execution.persistence.outcome_persistence import OutcomePersistence
from src.ml.models.signal_outcome import (
    SignalOutcome,
    SignalOutcomeStatus,
)


class TestVenueProvenanceE2E:
    """End-to-end tests for venue provenance data flow."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = Mock()
        mock.set = Mock(return_value=True)
        mock.expire = Mock(return_value=True)
        mock.zadd = Mock(return_value=True)
        mock.zrevrange = Mock(return_value=[])
        mock.get = Mock(return_value=None)
        mock.zcard = Mock(return_value=0)
        mock.ping = Mock(return_value=True)
        return mock

    @pytest.fixture
    def persistence(self, mock_redis):
        """Create OutcomePersistence with mock Redis."""
        return OutcomePersistence(redis_client=mock_redis)

    def test_e2e_venue_data_flow(self, persistence, mock_redis):
        """End-to-end test of venue data flow through pipeline.

        This test simulates the complete flow:
        1. Fill received from exchange with venue metadata
        2. Fill converted to SignalOutcome
        3. Outcome persisted to Redis
        4. Outcome retrieved and venue fields verified
        """
        # Step 1: Simulate fill from Bybit demo API
        fill = Fill(
            order_id="demo-order-123",
            fill_id="exec-456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(UTC),
            fee=Decimal("2.50"),
            fee_currency="USDT",
            exchange="bybit",
            execution_venue="bybit_demo",
            execution_mode="demo",
            metadata={
                "exec_type": "Trade",
                "is_maker": False,
                "api_endpoint": "https://api-demo.bybit.com",
            },
        )

        # Step 2: Convert fill to SignalOutcome (as would happen in outcome capture)
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side.capitalize(),
            direction="LONG",
            fill_price=fill.price,
            fill_quantity=fill.quantity,
            fill_timestamp=fill.timestamp,
            fee=fill.fee,
            status=SignalOutcomeStatus.FILLED,
            execution_venue=fill.execution_venue,
            execution_mode=fill.execution_mode,
            execution_source="bybit_demo_connector",
            venue_metadata={
                "fill_id": fill.fill_id,
                "exchange": fill.exchange,
                "api_endpoint": fill.metadata.get("api_endpoint"),
                "provenance_verified": True,
            },
        )

        # Step 3: Persist outcome (as would happen in persistence layer)
        key = persistence.persist_outcome(outcome)

        # Verify key was created
        assert key is not None
        assert "paper:outcome:" in key
        assert "BTCUSDT" in key

        # Step 4: Verify persisted data includes venue fields
        call_args = mock_redis.set.call_args
        stored_json = call_args[0][1]
        stored_data = json.loads(stored_json)

        # Verify all venue fields persisted
        assert stored_data["execution_venue"] == "bybit_demo"
        assert stored_data["execution_mode"] == "demo"
        assert stored_data["execution_source"] == "bybit_demo_connector"
        assert stored_data["venue_metadata"]["exchange"] == "bybit"
        assert stored_data["venue_metadata"]["provenance_verified"] is True

        # Step 5: Simulate retrieval and verify venue fields
        mock_redis.get.return_value = stored_json
        mock_redis.zrevrange.return_value = [key]

        retrieved_outcomes = persistence.get_recent_outcomes(symbol="BTCUSDT", limit=1)

        # Verify retrieved outcome has venue fields
        assert len(retrieved_outcomes) == 1
        retrieved = retrieved_outcomes[0]
        assert retrieved["execution_venue"] == "bybit_demo"
        assert retrieved["execution_mode"] == "demo"
        assert retrieved["execution_source"] == "bybit_demo_connector"

    def test_bybit_demo_orders_have_correct_venue_metadata(
        self, persistence, mock_redis
    ):
        """Test that Bybit demo orders have correct venue metadata.

        This test verifies that orders executed via Bybit demo API
        are properly tagged with venue metadata for audit purposes.
        """
        # Simulate a Bybit demo order outcome
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="bybit-demo-order-789",
            symbol="ETHUSDT",
            side="Sell",
            direction="SHORT",
            fill_price=Decimal("3000.00"),
            fill_quantity=Decimal("1.5"),
            fill_timestamp=datetime.now(UTC),
            fee=Decimal("4.50"),
            pnl=Decimal("150.00"),
            status=SignalOutcomeStatus.CLOSED,
            entry_price=Decimal("3150.00"),
            exit_price=Decimal("3000.00"),
            leverage=Decimal("10"),
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={
                "exchange": "bybit",
                "api_endpoint": "https://api-demo.bybit.com",
                "api_key_prefix": "DEMO:c775e7b757ed",
                "provenance_verified": True,
                "is_authenticated": True,
            },
        )

        # Persist the outcome
        key = persistence.persist_outcome(outcome)

        # Verify persisted data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify Bybit demo-specific venue metadata
        assert stored_data["execution_venue"] == "bybit_demo"
        assert stored_data["execution_mode"] == "demo"
        assert stored_data["execution_source"] == "bybit_demo_connector"
        assert stored_data["venue_metadata"]["exchange"] == "bybit"
        assert (
            stored_data["venue_metadata"]["api_endpoint"]
            == "https://api-demo.bybit.com"
        )
        assert stored_data["venue_metadata"]["provenance_verified"] is True
        assert stored_data["venue_metadata"]["is_authenticated"] is True

        # Verify this is distinguishable from simulation
        assert stored_data["venue_metadata"]["api_key_prefix"] == "DEMO:c775e7b757ed"

    def test_recaps_include_venue_provenance_summary(self, persistence, mock_redis):
        """Test that recaps include venue provenance summary.

        This test verifies that trade recaps include venue provenance
        information for audit and reporting purposes.
        """
        # Create multiple outcomes with different venues
        outcomes = [
            SignalOutcome(
                outcome_id=uuid4(),
                order_id="demo-order-1",
                symbol="BTCUSDT",
                side="Buy",
                execution_venue="bybit_demo",
                execution_mode="demo",
                execution_source="bybit_demo_connector",
                venue_metadata={"provenance_verified": True},
            ),
            SignalOutcome(
                outcome_id=uuid4(),
                order_id="demo-order-2",
                symbol="ETHUSDT",
                side="Buy",
                execution_venue="bybit_demo",
                execution_mode="demo",
                execution_source="bybit_demo_connector",
                venue_metadata={"provenance_verified": True},
            ),
        ]

        # Persist all outcomes
        keys = []
        for outcome in outcomes:
            key = persistence.persist_outcome(outcome)
            keys.append(key)

        # Simulate recap generation
        recap_summary = {
            "total_trades": len(outcomes),
            "venues": {},
            "provenance_summary": {
                "verified_count": 0,
                "unverified_count": 0,
            },
        }

        # Collect venue data from persisted outcomes
        for i, call_args in enumerate(mock_redis.set.call_args_list):
            stored_data = json.loads(call_args[0][1])
            venue = stored_data["execution_venue"]
            mode = stored_data["execution_mode"]
            provenance_verified = stored_data["venue_metadata"].get(
                "provenance_verified", False
            )

            # Aggregate venue counts
            venue_key = f"{venue}:{mode}"
            if venue_key not in recap_summary["venues"]:
                recap_summary["venues"][venue_key] = 0
            recap_summary["venues"][venue_key] += 1

            # Count provenance verification
            if provenance_verified:
                recap_summary["provenance_summary"]["verified_count"] += 1
            else:
                recap_summary["provenance_summary"]["unverified_count"] += 1

        # Verify recap includes venue summary
        assert recap_summary["total_trades"] == 2
        assert recap_summary["venues"]["bybit_demo:demo"] == 2
        assert recap_summary["provenance_summary"]["verified_count"] == 2
        assert recap_summary["provenance_summary"]["unverified_count"] == 0

    def test_venue_fields_support_audit_trail(self, persistence, mock_redis):
        """Test that venue fields support complete audit trail.

        This test verifies that all venue metadata needed for audit
        is properly captured and persisted.
        """
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="audit-order-001",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.00"),
            fill_quantity=Decimal("0.5"),
            fill_timestamp=datetime.now(UTC),
            fee=Decimal("12.50"),
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={
                "exchange": "bybit",
                "api_endpoint": "https://api-demo.bybit.com",
                "api_key_prefix": "ABCD",
                "provenance_verified": True,
                "is_authenticated": True,
                "connector_version": "1.0.0",
                "timestamp_verified": datetime.now(UTC).isoformat(),
            },
        )

        # Persist outcome
        key = persistence.persist_outcome(outcome)

        # Get stored data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify audit trail data is complete
        assert "execution_venue" in stored_data
        assert "execution_mode" in stored_data
        assert "execution_source" in stored_data
        assert "venue_metadata" in stored_data

        # Verify specific audit fields
        metadata = stored_data["venue_metadata"]
        assert metadata["exchange"] == "bybit"
        assert metadata["api_endpoint"] == "https://api-demo.bybit.com"
        assert metadata["api_key_prefix"] == "ABCD"
        assert metadata["provenance_verified"] is True
        assert metadata["is_authenticated"] is True
        assert "connector_version" in metadata
        assert "timestamp_verified" in metadata

    def test_fill_batch_venue_aggregation(self):
        """Test that FillBatch properly aggregates venue data.

        This test verifies that batches of fills maintain venue
        information for each fill.
        """
        fills = [
            Fill(
                order_id="order-1",
                fill_id="fill-1",
                symbol="BTCUSDT",
                side="buy",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
                timestamp=datetime.now(UTC),
                fee=Decimal("2.5"),
                fee_currency="USDT",
                exchange="bybit",
                execution_venue="bybit_demo",
                execution_mode="demo",
            ),
            Fill(
                order_id="order-2",
                fill_id="fill-2",
                symbol="BTCUSDT",
                side="buy",
                price=Decimal("50100"),
                quantity=Decimal("0.2"),
                timestamp=datetime.now(UTC),
                fee=Decimal("5.0"),
                fee_currency="USDT",
                exchange="bybit",
                execution_venue="bybit_demo",
                execution_mode="demo",
            ),
        ]

        batch = FillBatch(
            fills=fills,
            exchange="bybit",
        )

        # Verify batch serialization preserves fill venue data
        batch_dict = batch.to_dict()
        assert len(batch_dict["fills"]) == 2

        for fill_dict in batch_dict["fills"]:
            assert fill_dict["execution_venue"] == "bybit_demo"
            assert fill_dict["execution_mode"] == "demo"

    def test_venue_enforcement_verification(self, persistence, mock_redis):
        """Test venue enforcement can verify demo trades.

        This test verifies that venue fields enable enforcement
        gates to distinguish demo trades from other types.
        """
        # Create a verified demo trade
        demo_outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="demo-order-123",
            symbol="BTCUSDT",
            side="Buy",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={
                "provenance_verified": True,
                "api_endpoint": "https://api-demo.bybit.com",
            },
        )

        # Persist outcome
        key = persistence.persist_outcome(demo_outcome)

        # Get stored data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Simulate enforcement gate verification
        def verify_demo_trade(outcome_data: dict) -> dict:
            """Verify that a trade is a valid demo trade."""
            result = {
                "is_valid_demo": False,
                "checks": {},
            }

            # Check execution venue
            venue = outcome_data.get("execution_venue")
            result["checks"]["venue"] = venue == "bybit_demo"

            # Check execution mode
            mode = outcome_data.get("execution_mode")
            result["checks"]["mode"] = mode == "demo"

            # Check provenance
            metadata = outcome_data.get("venue_metadata", {})
            result["checks"]["provenance"] = metadata.get("provenance_verified", False)

            # Overall validity
            result["is_valid_demo"] = all(result["checks"].values())

            return result

        verification = verify_demo_trade(stored_data)

        # Verify all checks pass
        assert verification["is_valid_demo"] is True
        assert verification["checks"]["venue"] is True
        assert verification["checks"]["mode"] is True
        assert verification["checks"]["provenance"] is True


class TestVenueProvenanceEdgeCases:
    """Test edge cases for venue provenance."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = Mock()
        mock.set = Mock(return_value=True)
        mock.expire = Mock(return_value=True)
        mock.zadd = Mock(return_value=True)
        mock.zrevrange = Mock(return_value=[])
        mock.get = Mock(return_value=None)
        mock.zcard = Mock(return_value=0)
        mock.ping = Mock(return_value=True)
        return mock

    @pytest.fixture
    def persistence(self, mock_redis):
        """Create OutcomePersistence with mock Redis."""
        return OutcomePersistence(redis_client=mock_redis)

    def test_empty_venue_fields_persisted_correctly(self, persistence, mock_redis):
        """Test that empty venue fields are persisted correctly."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="order-123",
            symbol="BTCUSDT",
            side="Buy",
            # No venue fields set - should use defaults
        )

        key = persistence.persist_outcome(outcome)

        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify empty defaults are persisted
        assert stored_data["execution_venue"] == ""
        assert stored_data["execution_mode"] == ""
        assert stored_data["execution_source"] == ""
        assert stored_data["venue_metadata"] == {}

    def test_venue_metadata_with_complex_types(self, persistence, mock_redis):
        """Test venue metadata with complex nested types."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="order-123",
            symbol="BTCUSDT",
            side="Buy",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={
                "nested": {
                    "level1": {
                        "level2": "value",
                    },
                },
                "list": [1, 2, 3],
                "boolean": True,
                "number": 42,
                "null_value": None,
            },
        )

        key = persistence.persist_outcome(outcome)

        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify complex metadata is preserved
        assert stored_data["venue_metadata"]["nested"]["level1"]["level2"] == "value"
        assert stored_data["venue_metadata"]["list"] == [1, 2, 3]
        assert stored_data["venue_metadata"]["boolean"] is True
        assert stored_data["venue_metadata"]["number"] == 42

    def test_venue_fields_with_unicode(self, persistence, mock_redis):
        """Test venue fields with unicode characters."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="order-123",
            symbol="BTCUSDT",
            side="Buy",
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={
                "description": "Demo trading 日本語",
                "symbols": "€£¥",
            },
        )

        key = persistence.persist_outcome(outcome)

        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify unicode is preserved
        assert stored_data["venue_metadata"]["description"] == "Demo trading 日本語"
        assert stored_data["venue_metadata"]["symbols"] == "€£¥"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
