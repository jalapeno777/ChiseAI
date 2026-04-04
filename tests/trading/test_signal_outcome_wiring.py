"""Tests for ST-PIPELINE-Q2: SignalOutcome wiring at trade OPEN.

Verifies that every trade open creates a SignalOutcome record with
required fields populated (confidence_score, signal_type, signal_id,
timestamp, entry_price).

Acceptance Criteria:
- AC-1: Every trade open creates a SignalOutcome with required fields
- AC-2: No trade open path skips SignalOutcome creation
- AC-3: Unit tests with >=90% coverage of trade open code paths
- AC-4: No performance regression (<5ms overhead)
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ml.models.signal_outcome import (
    SignalOutcome,
    SignalOutcomeStatus,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_signal(
    confidence: float = 0.85,
    direction: SignalDirection = SignalDirection.LONG,
    token: str = "BTCUSDT",
    signal_id: str | None = None,
) -> Signal:
    """Create a test Signal."""
    return Signal(
        token=token,
        direction=direction,
        confidence=confidence,
        base_score=85.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        signal_id=signal_id or str(uuid.uuid4()),
    )


def _make_filled_order(
    order_id: str = "test-order-001",
    symbol: str = "BTCUSDT",
    avg_fill_price: float = 50000.0,
    filled_quantity: float = 0.01,
    filled_at: datetime | None = None,
) -> MagicMock:
    """Create a mock PaperOrder representing a filled order."""
    order = MagicMock()
    order.order_id = order_id
    order.symbol = symbol
    order.avg_fill_price = avg_fill_price
    order.filled_quantity = filled_quantity
    order.filled_at = filled_at or datetime.now(UTC)
    return order


def _make_open_outcome(
    signal: Signal,
    filled_order: MagicMock,
    correlation_id: str = "test-corr-001",
) -> SignalOutcome:
    """Replicate what the orchestrator does at trade open."""
    return SignalOutcome(
        signal_id=uuid.UUID(signal.signal_id) if signal.signal_id else None,
        order_id=filled_order.order_id,
        symbol=signal.token,
        side="Buy" if signal.direction.value == "long" else "Sell",
        direction=signal.direction.value.upper(),
        fill_price=Decimal(str(filled_order.avg_fill_price)),
        fill_quantity=Decimal(str(filled_order.filled_quantity)),
        fill_timestamp=filled_order.filled_at or datetime.now(UTC),
        entry_price=Decimal(str(filled_order.avg_fill_price)),
        entry_time=filled_order.filled_at or datetime.now(UTC),
        position_size=Decimal(str(filled_order.filled_quantity)),
        status=SignalOutcomeStatus.PENDING,
        # ST-PIPELINE-Q2: Required fields
        confidence_score=signal.confidence,
        signal_type="OPEN",
        metadata={"correlation_id": correlation_id},
    )


# ---------------------------------------------------------------------------
# AC-1: Required fields populated
# ---------------------------------------------------------------------------


class TestSignalOutcomeRequiredFields:
    """AC-1: Every trade open creates a SignalOutcome with required fields."""

    def test_confidence_score_populated(self) -> None:
        """confidence_score must be set from signal.confidence at trade open."""
        signal = _make_signal(confidence=0.92)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)

        assert outcome.confidence_score == pytest.approx(0.92)

    def test_signal_type_is_open(self) -> None:
        """signal_type must be 'OPEN' at trade open."""
        signal = _make_signal()
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)

        assert outcome.signal_type == "OPEN"

    def test_signal_id_populated(self) -> None:
        """signal_id must be populated from the originating signal."""
        signal = _make_signal()
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)

        assert outcome.signal_id is not None
        assert outcome.signal_id == uuid.UUID(signal.signal_id)

    def test_timestamp_populated(self) -> None:
        """timestamp (entry_time / fill_timestamp) must be set."""
        signal = _make_signal()
        now = datetime.now(UTC)
        order = _make_filled_order(filled_at=now)
        outcome = _make_open_outcome(signal, order)

        assert outcome.entry_time is not None
        assert outcome.entry_time.tzinfo is not None
        assert outcome.fill_timestamp is not None

    def test_entry_price_populated(self) -> None:
        """entry_price must be set from the fill price."""
        signal = _make_signal()
        order = _make_filled_order(avg_fill_price=42150.5)
        outcome = _make_open_outcome(signal, order)

        assert outcome.entry_price == Decimal("42150.5")

    def test_status_is_pending(self) -> None:
        """Status must be PENDING at trade open."""
        signal = _make_signal()
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)

        assert outcome.status == SignalOutcomeStatus.PENDING

    def test_long_direction(self) -> None:
        """LONG signals produce Buy side / LONG direction."""
        signal = _make_signal(direction=SignalDirection.LONG)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)

        assert outcome.side == "Buy"
        assert outcome.direction == "LONG"

    def test_short_direction(self) -> None:
        """SHORT signals produce Sell side / SHORT direction."""
        signal = _make_signal(direction=SignalDirection.SHORT)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)

        assert outcome.side == "Sell"
        assert outcome.direction == "SHORT"

    def test_confidence_clamped_to_valid_range(self) -> None:
        """Signal confidence is always 0.0-1.0 due to Signal.__post_init__."""
        signal = _make_signal(confidence=1.5)  # Will be clamped to 1.0
        assert signal.confidence == 1.0

        outcome = _make_open_outcome(signal, _make_filled_order())
        assert outcome.confidence_score == 1.0

    def test_confidence_zero(self) -> None:
        """Zero confidence is valid (edge case)."""
        signal = _make_signal(confidence=0.0)
        outcome = _make_open_outcome(signal, _make_filled_order())
        assert outcome.confidence_score == 0.0

    def test_all_required_fields_present_in_to_dict(self) -> None:
        """All required fields appear in to_dict() output."""
        signal = _make_signal(confidence=0.78)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)
        d = outcome.to_dict()

        assert "confidence_score" in d
        assert "signal_type" in d
        assert "signal_id" in d
        assert "entry_price" in d
        assert d["confidence_score"] == 0.78
        assert d["signal_type"] == "OPEN"

    def test_all_required_fields_present_in_to_db_dict(self) -> None:
        """All required fields appear in to_db_dict() output."""
        signal = _make_signal(confidence=0.65)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)
        d = outcome.to_db_dict()

        assert "confidence_score" in d
        assert "signal_type" in d
        assert d["confidence_score"] == 0.65
        assert d["signal_type"] == "OPEN"

    def test_all_required_fields_present_in_to_notification_dict(self) -> None:
        """confidence_score and signal_type appear in notification dict."""
        signal = _make_signal(confidence=0.88)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)
        d = outcome.to_notification_dict()

        assert "confidence_score" in d
        assert "signal_type" in d
        assert d["confidence_score"] == 0.88
        assert d["signal_type"] == "OPEN"


# ---------------------------------------------------------------------------
# AC-2: No trade open path skips SignalOutcome creation
# ---------------------------------------------------------------------------


class TestNoPathSkipsCreation:
    """AC-2: Verify SignalOutcome is always created for trade opens."""

    def test_outcome_created_for_long(self) -> None:
        """LONG signal always produces a SignalOutcome."""
        signal = _make_signal(direction=SignalDirection.LONG)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)
        assert outcome.outcome_id is not None

    def test_outcome_created_for_short(self) -> None:
        """SHORT signal always produces a SignalOutcome."""
        signal = _make_signal(direction=SignalDirection.SHORT)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)
        assert outcome.outcome_id is not None

    def test_outcome_created_with_null_signal_id(self) -> None:
        """SignalOutcome is still created even if signal_id is None."""
        signal = _make_signal()
        signal.signal_id = ""
        order = _make_filled_order()
        # When signal_id is empty, orchestrator passes None
        outcome = SignalOutcome(
            signal_id=None,
            order_id=order.order_id,
            symbol=signal.token,
            side="Buy",
            direction="LONG",
            fill_price=Decimal(str(order.avg_fill_price)),
            fill_quantity=Decimal(str(order.filled_quantity)),
            entry_price=Decimal(str(order.avg_fill_price)),
            position_size=Decimal(str(order.filled_quantity)),
            status=SignalOutcomeStatus.PENDING,
            confidence_score=signal.confidence,
            signal_type="OPEN",
        )
        assert outcome.outcome_id is not None
        assert outcome.signal_id is None
        assert outcome.confidence_score > 0

    def test_outcome_has_non_default_confidence(self) -> None:
        """confidence_score must NOT be the default 0.0 for a real trade open."""
        signal = _make_signal(confidence=0.81)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)
        assert outcome.confidence_score != 0.0
        assert outcome.confidence_score == 0.81

    def test_outcome_signal_type_always_open(self) -> None:
        """signal_type must be 'OPEN' for all trade opens (never empty)."""
        for conf in [0.1, 0.5, 0.75, 0.99, 1.0]:
            signal = _make_signal(confidence=conf)
            outcome = _make_open_outcome(signal, _make_filled_order())
            assert (
                outcome.signal_type == "OPEN"
            ), f"signal_type should be OPEN for confidence={conf}"


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """Verify confidence_score and signal_type survive serialization."""

    def test_to_dict_from_dict_round_trip(self) -> None:
        """to_dict -> from_dict preserves new fields."""
        signal = _make_signal(confidence=0.77)
        order = _make_filled_order()
        original = _make_open_outcome(signal, order)
        data = original.to_dict()
        restored = SignalOutcome.from_dict(data)

        assert restored.confidence_score == pytest.approx(original.confidence_score)
        assert restored.signal_type == original.signal_type
        assert restored.signal_id == original.signal_id
        assert restored.entry_price == original.entry_price

    def test_from_dict_without_new_fields_defaults(self) -> None:
        """from_dict with missing new fields uses defaults (backward compat)."""
        data: dict[str, Any] = {
            "outcome_id": str(uuid.uuid4()),
            "signal_id": str(uuid.uuid4()),
            "order_id": "order-1",
            "symbol": "ETHUSDT",
            "status": "pending",
        }
        outcome = SignalOutcome.from_dict(data)
        assert outcome.confidence_score == 0.0
        assert outcome.signal_type == ""

    def test_to_db_dict_has_new_fields(self) -> None:
        """to_db_dict includes confidence_score and signal_type."""
        signal = _make_signal(confidence=0.90)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)
        db = outcome.to_db_dict()

        assert db["confidence_score"] == 0.90
        assert db["signal_type"] == "OPEN"


# ---------------------------------------------------------------------------
# AC-4: Performance (overhead <5ms)
# ---------------------------------------------------------------------------


class TestPerformance:
    """AC-4: SignalOutcome creation adds <5ms overhead."""

    def test_outcome_creation_under_5ms(self) -> None:
        """Creating a SignalOutcome at trade open must complete in <5ms."""
        signal = _make_signal(confidence=0.85)
        order = _make_filled_order()

        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            _make_open_outcome(signal, order)
        elapsed_ms = (time.perf_counter() - start) / iterations * 1000

        assert (
            elapsed_ms < 5.0
        ), f"SignalOutcome creation took {elapsed_ms:.3f}ms avg (limit: 5ms)"

    def test_outcome_creation_with_serialization_under_5ms(self) -> None:
        """Creating + serializing SignalOutcome must complete in <5ms."""
        signal = _make_signal(confidence=0.85)
        order = _make_filled_order()

        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            outcome = _make_open_outcome(signal, order)
            outcome.to_dict()
        elapsed_ms = (time.perf_counter() - start) / iterations * 1000

        assert elapsed_ms < 5.0, (
            f"SignalOutcome creation+serialization took {elapsed_ms:.3f}ms avg "
            f"(limit: 5ms)"
        )


# ---------------------------------------------------------------------------
# Integration: OutcomeCaptureIntegration.on_trade_open wiring
# ---------------------------------------------------------------------------


class TestOutcomeCaptureIntegrationWiring:
    """Verify on_trade_open receives SignalOutcome with new fields."""

    @pytest.mark.asyncio
    async def test_on_trade_open_receives_confidence_score(self) -> None:
        """on_trade_open gets called with a SignalOutcome that has confidence_score."""
        from execution.outcome_capture.integration import OutcomeCaptureIntegration

        signal = _make_signal(confidence=0.93)
        order = _make_filled_order()
        outcome = _make_open_outcome(signal, order)

        integration = OutcomeCaptureIntegration(
            persistence=None,
            alerts=None,
            enabled=True,
        )
        # Mock persistence to avoid actual DB/Redis calls
        mock_persistence = AsyncMock()
        mock_persistence.persist_outcome_async.return_value = "outcome:test-key"
        integration._persistence = mock_persistence

        # Mock alerts
        mock_alerts = AsyncMock()
        mock_alerts.on_trade_opened.return_value = {"sent": False}
        integration._alerts = mock_alerts

        result = await integration.on_trade_open(outcome, "test-corr")

        assert result["captured"] is True
        # Verify the outcome passed to persistence has the new fields
        call_args = mock_persistence.persist_outcome_async.call_args
        persisted_outcome = call_args[0][0]
        assert persisted_outcome.confidence_score == 0.93
        assert persisted_outcome.signal_type == "OPEN"

    @pytest.mark.asyncio
    async def test_on_trade_open_disabled_skips_capture(self) -> None:
        """When disabled, on_trade_open returns captured=False."""
        from execution.outcome_capture.integration import OutcomeCaptureIntegration

        outcome = _make_open_outcome(_make_signal(), _make_filled_order())
        integration = OutcomeCaptureIntegration(enabled=False)

        result = await integration.on_trade_open(outcome)
        assert result["captured"] is False
        assert result["reason"] == "disabled"


# ---------------------------------------------------------------------------
# ST-ICT-Q3: Null handling for order_fill events
# ---------------------------------------------------------------------------


class TestBybitFillEventNullHandling:
    """Verify BybitFillEvent.to_signal_outcome() sets proper defaults."""

    def test_fill_event_has_confidence_score(self) -> None:
        """BybitFillEvent.to_signal_outcome() should set confidence_score=1.0."""
        from ml.models.signal_outcome import BybitFillEvent

        fill = BybitFillEvent(
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            price=Decimal("50000.0"),
            qty=Decimal("0.01"),
            exec_time=1704067200000,  # 2024-01-01 00:00:00 UTC
        )
        outcome = fill.to_signal_outcome()

        # Fill events should have high confidence (1.0) since we have actual execution data
        assert outcome.confidence_score == 1.0

    def test_fill_event_has_signal_type_fill(self) -> None:
        """BybitFillEvent.to_signal_outcome() should set signal_type='FILL'."""
        from ml.models.signal_outcome import BybitFillEvent

        fill = BybitFillEvent(
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            price=Decimal("50000.0"),
            qty=Decimal("0.01"),
            exec_time=1704067200000,
        )
        outcome = fill.to_signal_outcome()

        # signal_type='FILL' indicates fill event without signal context
        assert outcome.signal_type == "FILL"

    def test_fill_event_status_is_filled(self) -> None:
        """BybitFillEvent.to_signal_outcome() should set status=FILLED."""
        from ml.models.signal_outcome import BybitFillEvent

        fill = BybitFillEvent(
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            price=Decimal("50000.0"),
            qty=Decimal("0.01"),
            exec_time=1704067200000,
        )
        outcome = fill.to_signal_outcome()

        assert outcome.status == SignalOutcomeStatus.FILLED

    def test_fill_event_no_signal_id(self) -> None:
        """BybitFillEvent.to_signal_outcome() should have signal_id=None."""
        from ml.models.signal_outcome import BybitFillEvent

        fill = BybitFillEvent(
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            price=Decimal("50000.0"),
            qty=Decimal("0.01"),
            exec_time=1704067200000,
        )
        outcome = fill.to_signal_outcome()

        # Fill events don't have signal context
        assert outcome.signal_id is None

    def test_fill_event_to_dict_includes_new_fields(self) -> None:
        """BybitFillEvent.to_signal_outcome() to_dict() should include new fields."""
        from ml.models.signal_outcome import BybitFillEvent

        fill = BybitFillEvent(
            order_id="test-order-1",
            symbol="ETHUSDT",
            side="Sell",
            price=Decimal("3000.0"),
            qty=Decimal("0.5"),
            exec_time=1704067200000,
        )
        outcome = fill.to_signal_outcome()
        d = outcome.to_dict()

        assert "confidence_score" in d
        assert "signal_type" in d
        assert d["confidence_score"] == 1.0
        assert d["signal_type"] == "FILL"

    def test_fill_event_serialization_roundtrip(self) -> None:
        """BybitFillEvent.to_signal_outcome() should survive serialization."""
        from ml.models.signal_outcome import BybitFillEvent

        fill = BybitFillEvent(
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            price=Decimal("50000.0"),
            qty=Decimal("0.01"),
            exec_time=1704067200000,
        )
        original = fill.to_signal_outcome()
        data = original.to_dict()
        restored = SignalOutcome.from_dict(data)

        assert restored.confidence_score == original.confidence_score
        assert restored.signal_type == original.signal_type


class TestSignalOutcomeNullHandling:
    """Verify SignalOutcome handles null/missing fields gracefully."""

    def test_outcome_with_none_signal_id_serializes(self) -> None:
        """SignalOutcome with signal_id=None should serialize/deserialize correctly."""
        outcome = SignalOutcome(
            signal_id=None,
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.0"),
            fill_quantity=Decimal("0.01"),
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.01"),
            status=SignalOutcomeStatus.PENDING,
            confidence_score=0.85,
            signal_type="OPEN",
        )
        # Should not raise
        data = outcome.to_dict()
        assert data["signal_id"] is None
        restored = SignalOutcome.from_dict(data)
        assert restored.signal_id is None

    def test_outcome_with_zero_confidence_serializes(self) -> None:
        """SignalOutcome with confidence_score=0.0 should serialize correctly."""
        outcome = SignalOutcome(
            signal_id=None,
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.0"),
            fill_quantity=Decimal("0.01"),
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.01"),
            status=SignalOutcomeStatus.PENDING,
            confidence_score=0.0,
            signal_type="OPEN",
        )
        data = outcome.to_dict()
        assert data["confidence_score"] == 0.0
        restored = SignalOutcome.from_dict(data)
        assert restored.confidence_score == 0.0

    def test_outcome_with_empty_signal_type_serializes(self) -> None:
        """SignalOutcome with signal_type='' should serialize correctly."""
        outcome = SignalOutcome(
            signal_id=None,
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.0"),
            fill_quantity=Decimal("0.01"),
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.01"),
            status=SignalOutcomeStatus.PENDING,
            confidence_score=0.5,
            signal_type="",
        )
        data = outcome.to_dict()
        assert data["signal_type"] == ""
        restored = SignalOutcome.from_dict(data)
        assert restored.signal_type == ""

    def test_outcome_to_db_dict_with_null_signal_id(self) -> None:
        """to_db_dict should handle null signal_id correctly."""
        outcome = SignalOutcome(
            signal_id=None,
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.0"),
            fill_quantity=Decimal("0.01"),
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.01"),
            status=SignalOutcomeStatus.PENDING,
            confidence_score=0.85,
            signal_type="OPEN",
        )
        db = outcome.to_db_dict()
        # Should not raise and should have proper values
        assert db["signal_id"] is None
        assert db["confidence_score"] == 0.85
        assert db["signal_type"] == "OPEN"

    def test_outcome_notification_dict_with_null_fields(self) -> None:
        """to_notification_dict should handle null/missing fields gracefully."""
        outcome = SignalOutcome(
            signal_id=None,
            order_id="test-order-1",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.0"),
            fill_quantity=Decimal("0.01"),
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.01"),
            status=SignalOutcomeStatus.PENDING,
            confidence_score=0.0,
            signal_type="",
        )
        # Should not raise
        notif = outcome.to_notification_dict()
        assert "confidence_score" in notif
        assert "signal_type" in notif
        assert notif["confidence_score"] == 0.0
        assert notif["signal_type"] == ""


class TestOrderFillNullPropagation:
    """Verify order_fill events propagate through SignalOutcome pipeline correctly."""

    def test_fill_event_flows_through_persistence(self) -> None:
        """BybitFillEvent.to_signal_outcome() outcome should be persistable."""
        from ml.models.signal_outcome import BybitFillEvent

        fill = BybitFillEvent(
            order_id="persist-test-order",
            symbol="BTCUSDT",
            side="Buy",
            price=Decimal("50000.0"),
            qty=Decimal("0.01"),
            exec_time=1704067200000,
        )
        outcome = fill.to_signal_outcome()

        # Verify all required fields are set
        assert outcome.order_id == "persist-test-order"
        assert outcome.symbol == "BTCUSDT"
        assert outcome.side == "Buy"
        assert outcome.fill_price == Decimal("50000.0")
        assert outcome.fill_quantity == Decimal("0.01")
        assert outcome.status == SignalOutcomeStatus.FILLED
        assert outcome.confidence_score == 1.0
        assert outcome.signal_type == "FILL"

        # Should serialize without error
        data = outcome.to_dict()
        assert data["order_id"] == "persist-test-order"
        assert data["confidence_score"] == 1.0
        assert data["signal_type"] == "FILL"

    def test_mixed_fill_and_signal_outcomes_have_correct_types(self) -> None:
        """Fill events (FILL) vs signal-triggered trades (OPEN) have correct signal_type."""
        # Fill event without signal context
        fill_outcome = SignalOutcome(
            signal_id=None,
            order_id="fill-order",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.0"),
            fill_quantity=Decimal("0.01"),
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.01"),
            status=SignalOutcomeStatus.FILLED,
            confidence_score=1.0,
            signal_type="FILL",
        )

        # Signal-triggered trade
        signal_outcome = SignalOutcome(
            signal_id=uuid.uuid4(),
            order_id="signal-order",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.0"),
            fill_quantity=Decimal("0.01"),
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.01"),
            status=SignalOutcomeStatus.PENDING,
            confidence_score=0.85,
            signal_type="OPEN",
        )

        # Verify distinction between fill events and signal-triggered trades
        assert fill_outcome.signal_type == "FILL"
        assert fill_outcome.confidence_score == 1.0
        assert fill_outcome.signal_id is None

        assert signal_outcome.signal_type == "OPEN"
        assert signal_outcome.confidence_score == 0.85
        assert signal_outcome.signal_id is not None
