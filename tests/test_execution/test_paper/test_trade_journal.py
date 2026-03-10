"""Tests for trade journal data model.

Tests for ExitReason, FillRecord, TradeEvent, TradeJournalEntry, and TradeJournal.
"""

import pytest
from datetime import UTC, datetime, timedelta

from src.execution.paper.trade_journal import (
    ExitReason,
    FillRecord,
    TradeEvent,
    TradeJournal,
    TradeJournalEntry,
)


class MockPosition:
    """Mock position object for testing."""

    def __init__(
        self,
        position_id: str = "pos_123",
        symbol: str = "BTCUSDT",
        side: str = "long",
        entry_price: float = 50000.0,
        quantity: float = 0.1,
    ):
        self.position_id = position_id
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.quantity = quantity


class MockSignal:
    """Mock signal object for testing."""

    def __init__(
        self,
        signal_id: str = "sig_456",
        confidence: float = 0.85,
        strategy: str = "momentum",
    ):
        self.signal_id = signal_id
        self.confidence = confidence
        self.strategy = strategy


class TestExitReason:
    """Test ExitReason enum."""

    def test_exit_reason_values(self):
        """Test that all exit reasons have correct values."""
        assert ExitReason.STOP_LOSS_HIT.value == "stop_loss_hit"
        assert ExitReason.TAKE_PROFIT_HIT.value == "take_profit_hit"
        assert ExitReason.SIGNAL_REVERSE.value == "signal_reverse"
        assert ExitReason.TIME_LIMIT.value == "time_limit"
        assert ExitReason.MANUAL_CLOSE.value == "manual_close"
        assert ExitReason.KILL_SWITCH.value == "kill_switch"
        assert ExitReason.RISK_REDUCTION.value == "risk_reduction"

    def test_all_exit_reasons_present(self):
        """Test that all 7 required exit reasons are present."""
        expected_reasons = {
            "STOP_LOSS_HIT",
            "TAKE_PROFIT_HIT",
            "SIGNAL_REVERSE",
            "TIME_LIMIT",
            "MANUAL_CLOSE",
            "KILL_SWITCH",
            "RISK_REDUCTION",
        }
        actual_reasons = {r.name for r in ExitReason}
        assert actual_reasons == expected_reasons


class TestFillRecord:
    """Test FillRecord dataclass."""

    def test_create_fill_record(self):
        """Test creating a fill record."""
        now = datetime.now(UTC)
        fill = FillRecord(
            fill_id="fill_123",
            timestamp=now,
            price=50000.0,
            quantity=0.1,
            fee=0.5,
        )

        assert fill.fill_id == "fill_123"
        assert fill.timestamp == now
        assert fill.price == 50000.0
        assert fill.quantity == 0.1
        assert fill.fee == 0.5

    def test_create_fill_record_default_fee(self):
        """Test creating a fill record with default fee."""
        fill = FillRecord(
            fill_id="fill_123",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.1,
        )

        assert fill.fee == 0.0

    def test_fill_record_validation_negative_price(self):
        """Test that negative price raises ValueError."""
        with pytest.raises(ValueError, match="Price must be positive"):
            FillRecord(
                fill_id="fill_123",
                timestamp=datetime.now(UTC),
                price=-100.0,
                quantity=0.1,
            )

    def test_fill_record_validation_zero_price(self):
        """Test that zero price raises ValueError."""
        with pytest.raises(ValueError, match="Price must be positive"):
            FillRecord(
                fill_id="fill_123",
                timestamp=datetime.now(UTC),
                price=0.0,
                quantity=0.1,
            )

    def test_fill_record_validation_negative_quantity(self):
        """Test that negative quantity raises ValueError."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            FillRecord(
                fill_id="fill_123",
                timestamp=datetime.now(UTC),
                price=50000.0,
                quantity=-0.1,
            )

    def test_fill_record_validation_negative_fee(self):
        """Test that negative fee raises ValueError."""
        with pytest.raises(ValueError, match="Fee cannot be negative"):
            FillRecord(
                fill_id="fill_123",
                timestamp=datetime.now(UTC),
                price=50000.0,
                quantity=0.1,
                fee=-0.5,
            )

    def test_fill_record_timezone_aware(self):
        """Test that timestamp is made timezone-aware."""
        naive_time = datetime.now().replace(tzinfo=None)
        fill = FillRecord(
            fill_id="fill_123",
            timestamp=naive_time,
            price=50000.0,
            quantity=0.1,
        )
        assert fill.timestamp.tzinfo is not None

    def test_fill_record_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(UTC)
        fill = FillRecord(
            fill_id="fill_123",
            timestamp=now,
            price=50000.0,
            quantity=0.1,
            fee=0.5,
        )

        data = fill.to_dict()

        assert data["fill_id"] == "fill_123"
        assert data["timestamp"] == now.isoformat()
        assert data["price"] == 50000.0
        assert data["quantity"] == 0.1
        assert data["fee"] == 0.5

    def test_fill_record_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(UTC)
        data = {
            "fill_id": "fill_123",
            "timestamp": now.isoformat(),
            "price": 50000.0,
            "quantity": 0.1,
            "fee": 0.5,
        }

        fill = FillRecord.from_dict(data)

        assert fill.fill_id == "fill_123"
        assert fill.price == 50000.0
        assert fill.quantity == 0.1
        assert fill.fee == 0.5

    def test_fill_record_from_dict_default_fee(self):
        """Test deserialization with default fee."""
        data = {
            "fill_id": "fill_123",
            "timestamp": datetime.now(UTC).isoformat(),
            "price": 50000.0,
            "quantity": 0.1,
        }

        fill = FillRecord.from_dict(data)
        assert fill.fee == 0.0

    def test_fill_record_roundtrip(self):
        """Test serialization roundtrip."""
        now = datetime.now(UTC)
        original = FillRecord(
            fill_id="fill_123",
            timestamp=now,
            price=50000.0,
            quantity=0.1,
            fee=0.5,
        )

        data = original.to_dict()
        restored = FillRecord.from_dict(data)

        assert restored.fill_id == original.fill_id
        assert restored.timestamp == original.timestamp
        assert restored.price == original.price
        assert restored.quantity == original.quantity
        assert restored.fee == original.fee


class TestTradeEvent:
    """Test TradeEvent dataclass."""

    def test_create_trade_event(self):
        """Test creating a trade event."""
        now = datetime.now(UTC)
        event = TradeEvent(
            event_type="position_update",
            timestamp=now,
            details={"key": "value"},
        )

        assert event.event_type == "position_update"
        assert event.timestamp == now
        assert event.details == {"key": "value"}

    def test_create_trade_event_default_details(self):
        """Test creating a trade event with default details."""
        event = TradeEvent(
            event_type="position_update",
            timestamp=datetime.now(UTC),
        )

        assert event.details == {}

    def test_trade_event_validation_empty_type(self):
        """Test that empty event type raises ValueError."""
        with pytest.raises(ValueError, match="event_type cannot be empty"):
            TradeEvent(
                event_type="",
                timestamp=datetime.now(UTC),
            )

    def test_trade_event_timezone_aware(self):
        """Test that timestamp is made timezone-aware."""
        naive_time = datetime.now().replace(tzinfo=None)
        event = TradeEvent(
            event_type="position_update",
            timestamp=naive_time,
        )
        assert event.timestamp.tzinfo is not None

    def test_trade_event_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(UTC)
        event = TradeEvent(
            event_type="position_update",
            timestamp=now,
            details={"key": "value"},
        )

        data = event.to_dict()

        assert data["event_type"] == "position_update"
        assert data["timestamp"] == now.isoformat()
        assert data["details"] == {"key": "value"}

    def test_trade_event_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(UTC)
        data = {
            "event_type": "position_update",
            "timestamp": now.isoformat(),
            "details": {"key": "value"},
        }

        event = TradeEvent.from_dict(data)

        assert event.event_type == "position_update"
        assert event.details == {"key": "value"}

    def test_trade_event_from_dict_default_details(self):
        """Test deserialization with default details."""
        data = {
            "event_type": "position_update",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        event = TradeEvent.from_dict(data)
        assert event.details == {}

    def test_trade_event_roundtrip(self):
        """Test serialization roundtrip."""
        now = datetime.now(UTC)
        original = TradeEvent(
            event_type="position_update",
            timestamp=now,
            details={"key": "value"},
        )

        data = original.to_dict()
        restored = TradeEvent.from_dict(data)

        assert restored.event_type == original.event_type
        assert restored.timestamp == original.timestamp
        assert restored.details == original.details


class TestTradeJournalEntry:
    """Test TradeJournalEntry dataclass."""

    def test_create_entry(self):
        """Test creating a trade journal entry."""
        now = datetime.now(UTC)
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=now,
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        assert entry.entry_id == "entry_123"
        assert entry.symbol == "BTCUSDT"
        assert entry.side == "buy"
        assert entry.entry_price == 50000.0
        assert entry.entry_time == now
        assert entry.position_size == 0.1
        assert entry.signal_id == "sig_456"
        assert entry.signal_confidence == 0.85
        assert entry.signal_strategy == "momentum"
        assert entry.is_open is True
        assert entry.is_closed is False

    def test_entry_side_normalization(self):
        """Test that side is normalized to lowercase."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="BUY",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        assert entry.side == "buy"

    def test_entry_validation_invalid_side(self):
        """Test that invalid side raises ValueError."""
        with pytest.raises(ValueError, match="Invalid side"):
            TradeJournalEntry(
                entry_id="entry_123",
                symbol="BTCUSDT",
                side="invalid",
                entry_price=50000.0,
                entry_time=datetime.now(UTC),
                position_size=0.1,
                signal_id="sig_456",
                signal_confidence=0.85,
                signal_strategy="momentum",
            )

    def test_entry_validation_negative_price(self):
        """Test that negative entry price raises ValueError."""
        with pytest.raises(ValueError, match="Entry price must be positive"):
            TradeJournalEntry(
                entry_id="entry_123",
                symbol="BTCUSDT",
                side="buy",
                entry_price=-100.0,
                entry_time=datetime.now(UTC),
                position_size=0.1,
                signal_id="sig_456",
                signal_confidence=0.85,
                signal_strategy="momentum",
            )

    def test_entry_validation_negative_position_size(self):
        """Test that negative position size raises ValueError."""
        with pytest.raises(ValueError, match="Position size must be positive"):
            TradeJournalEntry(
                entry_id="entry_123",
                symbol="BTCUSDT",
                side="buy",
                entry_price=50000.0,
                entry_time=datetime.now(UTC),
                position_size=-0.1,
                signal_id="sig_456",
                signal_confidence=0.85,
                signal_strategy="momentum",
            )

    def test_entry_validation_confidence_range(self):
        """Test that confidence outside 0-1 range raises ValueError."""
        with pytest.raises(ValueError, match="Signal confidence must be between"):
            TradeJournalEntry(
                entry_id="entry_123",
                symbol="BTCUSDT",
                side="buy",
                entry_price=50000.0,
                entry_time=datetime.now(UTC),
                position_size=0.1,
                signal_id="sig_456",
                signal_confidence=1.5,
                signal_strategy="momentum",
            )

    def test_entry_validation_negative_confidence(self):
        """Test that negative confidence raises ValueError."""
        with pytest.raises(ValueError, match="Signal confidence must be between"):
            TradeJournalEntry(
                entry_id="entry_123",
                symbol="BTCUSDT",
                side="buy",
                entry_price=50000.0,
                entry_time=datetime.now(UTC),
                position_size=0.1,
                signal_id="sig_456",
                signal_confidence=-0.1,
                signal_strategy="momentum",
            )

    def test_entry_timezone_aware(self):
        """Test that timestamps are made timezone-aware."""
        naive_time = datetime.now().replace(tzinfo=None)
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=naive_time,
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )
        assert entry.entry_time.tzinfo is not None
        assert entry.created_at.tzinfo is not None

    def test_add_fill(self):
        """Test adding a fill to an entry."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        fill = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.05,
            fee=0.25,
        )

        entry.add_fill(fill)

        assert len(entry.fills) == 1
        assert entry.fills[0] == fill
        assert entry.fees == 0.25

    def test_add_multiple_fills(self):
        """Test adding multiple fills to an entry."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        fill1 = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.05,
            fee=0.25,
        )
        fill2 = FillRecord(
            fill_id="fill_2",
            timestamp=datetime.now(UTC),
            price=50100.0,
            quantity=0.05,
            fee=0.25,
        )

        entry.add_fill(fill1)
        entry.add_fill(fill2)

        assert len(entry.fills) == 2
        assert entry.fees == 0.5

    def test_add_fill_to_closed_entry(self):
        """Test that adding fill to closed entry raises ValueError."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        # Close the entry
        entry.close(
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            realized_pnl=100.0,
        )

        fill = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.05,
            fee=0.25,
        )

        with pytest.raises(ValueError, match="Cannot add fill to closed trade"):
            entry.add_fill(fill)

    def test_add_event(self):
        """Test adding an event to an entry."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        event = TradeEvent(
            event_type="position_update",
            timestamp=datetime.now(UTC),
            details={"key": "value"},
        )

        entry.add_event(event)

        assert len(entry.events) == 1
        assert entry.events[0] == event

    def test_close_entry(self):
        """Test closing a trade entry."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        entry.close(
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            realized_pnl=100.0,
            exit_signal_id="sig_789",
        )

        assert entry.is_closed is True
        assert entry.is_open is False
        assert entry.exit_price == 51000.0
        assert entry.exit_reason == ExitReason.TAKE_PROFIT_HIT
        assert entry.realized_pnl == 100.0
        assert entry.exit_signal_id == "sig_789"
        assert entry.exit_time is not None

    def test_close_already_closed_entry(self):
        """Test that closing an already closed entry raises ValueError."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        entry.close(
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            realized_pnl=100.0,
        )

        with pytest.raises(ValueError, match="Trade is already closed"):
            entry.close(
                exit_price=52000.0,
                exit_reason=ExitReason.MANUAL_CLOSE,
                realized_pnl=200.0,
            )

    def test_close_invalid_exit_price(self):
        """Test that closing with invalid exit price raises ValueError."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        with pytest.raises(ValueError, match="Exit price must be positive"):
            entry.close(
                exit_price=-100.0,
                exit_reason=ExitReason.TAKE_PROFIT_HIT,
                realized_pnl=100.0,
            )

    def test_net_pnl_property(self):
        """Test net_pnl property calculation."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
            realized_pnl=100.0,
            fees=5.0,
        )

        assert entry.net_pnl == 95.0

    def test_total_filled_quantity_property(self):
        """Test total_filled_quantity property."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        fill1 = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.05,
            fee=0.25,
        )
        fill2 = FillRecord(
            fill_id="fill_2",
            timestamp=datetime.now(UTC),
            price=50100.0,
            quantity=0.03,
            fee=0.15,
        )

        entry.add_fill(fill1)
        entry.add_fill(fill2)

        assert entry.total_filled_quantity == 0.08

    def test_avg_fill_price_property(self):
        """Test avg_fill_price property."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        # No fills yet
        assert entry.avg_fill_price is None

        fill1 = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.05,
            fee=0.25,
        )
        fill2 = FillRecord(
            fill_id="fill_2",
            timestamp=datetime.now(UTC),
            price=51000.0,
            quantity=0.05,
            fee=0.25,
        )

        entry.add_fill(fill1)
        entry.add_fill(fill2)

        # Weighted average: (50000*0.05 + 51000*0.05) / 0.1 = 50500
        assert entry.avg_fill_price == 50500.0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(UTC)
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=now,
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
            correlation_id="corr_789",
            session_id="session_abc",
        )

        data = entry.to_dict()

        assert data["entry_id"] == "entry_123"
        assert data["symbol"] == "BTCUSDT"
        assert data["side"] == "buy"
        assert data["entry_price"] == 50000.0
        assert data["entry_time"] == now.isoformat()
        assert data["position_size"] == 0.1
        assert data["signal_id"] == "sig_456"
        assert data["signal_confidence"] == 0.85
        assert data["signal_strategy"] == "momentum"
        assert data["correlation_id"] == "corr_789"
        assert data["session_id"] == "session_abc"
        assert data["is_open"] is True
        assert data["is_closed"] is False

    def test_to_dict_closed_entry(self):
        """Test serialization of closed entry."""
        now = datetime.now(UTC)
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=now,
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
        )

        entry.close(
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            realized_pnl=100.0,
        )

        data = entry.to_dict()

        assert data["exit_price"] == 51000.0
        assert data["exit_reason"] == "take_profit_hit"
        assert data["realized_pnl"] == 100.0
        assert data["is_open"] is False
        assert data["is_closed"] is True

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(UTC)
        data = {
            "entry_id": "entry_123",
            "symbol": "BTCUSDT",
            "side": "buy",
            "entry_price": 50000.0,
            "entry_time": now.isoformat(),
            "position_size": 0.1,
            "signal_id": "sig_456",
            "signal_confidence": 0.85,
            "signal_strategy": "momentum",
            "correlation_id": "corr_789",
            "session_id": "session_abc",
            "created_at": now.isoformat(),
            "fills": [],
            "events": [],
        }

        entry = TradeJournalEntry.from_dict(data)

        assert entry.entry_id == "entry_123"
        assert entry.symbol == "BTCUSDT"
        assert entry.side == "buy"
        assert entry.entry_price == 50000.0
        assert entry.position_size == 0.1
        assert entry.signal_id == "sig_456"
        assert entry.signal_confidence == 0.85
        assert entry.signal_strategy == "momentum"
        assert entry.correlation_id == "corr_789"
        assert entry.session_id == "session_abc"

    def test_from_dict_closed_entry(self):
        """Test deserialization of closed entry."""
        now = datetime.now(UTC)
        exit_time = now + timedelta(hours=1)
        data = {
            "entry_id": "entry_123",
            "symbol": "BTCUSDT",
            "side": "buy",
            "entry_price": 50000.0,
            "entry_time": now.isoformat(),
            "position_size": 0.1,
            "signal_id": "sig_456",
            "signal_confidence": 0.85,
            "signal_strategy": "momentum",
            "exit_price": 51000.0,
            "exit_time": exit_time.isoformat(),
            "exit_reason": "take_profit_hit",
            "exit_signal_id": "sig_789",
            "realized_pnl": 100.0,
            "fees": 5.0,
            "created_at": now.isoformat(),
            "fills": [],
            "events": [],
        }

        entry = TradeJournalEntry.from_dict(data)

        assert entry.exit_price == 51000.0
        assert entry.exit_reason == ExitReason.TAKE_PROFIT_HIT
        assert entry.exit_signal_id == "sig_789"
        assert entry.realized_pnl == 100.0
        assert entry.fees == 5.0

    def test_from_dict_with_fills_and_events(self):
        """Test deserialization with fills and events."""
        now = datetime.now(UTC)
        data = {
            "entry_id": "entry_123",
            "symbol": "BTCUSDT",
            "side": "buy",
            "entry_price": 50000.0,
            "entry_time": now.isoformat(),
            "position_size": 0.1,
            "signal_id": "sig_456",
            "signal_confidence": 0.85,
            "signal_strategy": "momentum",
            "created_at": now.isoformat(),
            "fills": [
                {
                    "fill_id": "fill_1",
                    "timestamp": now.isoformat(),
                    "price": 50000.0,
                    "quantity": 0.1,
                    "fee": 0.5,
                }
            ],
            "events": [
                {
                    "event_type": "position_update",
                    "timestamp": now.isoformat(),
                    "details": {"key": "value"},
                }
            ],
        }

        entry = TradeJournalEntry.from_dict(data)

        assert len(entry.fills) == 1
        assert entry.fills[0].fill_id == "fill_1"
        assert len(entry.events) == 1
        assert entry.events[0].event_type == "position_update"

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        now = datetime.now(UTC)
        original = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=now,
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
            correlation_id="corr_789",
            session_id="session_abc",
        )

        fill = FillRecord(
            fill_id="fill_1",
            timestamp=now,
            price=50000.0,
            quantity=0.1,
            fee=0.5,
        )
        original.add_fill(fill)

        event = TradeEvent(
            event_type="position_update",
            timestamp=now,
            details={"key": "value"},
        )
        original.add_event(event)

        original.close(
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            realized_pnl=100.0,
            exit_signal_id="sig_789",
        )

        data = original.to_dict()
        restored = TradeJournalEntry.from_dict(data)

        assert restored.entry_id == original.entry_id
        assert restored.symbol == original.symbol
        assert restored.side == original.side
        assert restored.entry_price == original.entry_price
        assert restored.position_size == original.position_size
        assert restored.signal_id == original.signal_id
        assert restored.signal_confidence == original.signal_confidence
        assert restored.signal_strategy == original.signal_strategy
        assert restored.correlation_id == original.correlation_id
        assert restored.session_id == original.session_id
        assert restored.exit_price == original.exit_price
        assert restored.exit_reason == original.exit_reason
        assert restored.exit_signal_id == original.exit_signal_id
        assert restored.realized_pnl == original.realized_pnl
        assert restored.fees == original.fees
        assert len(restored.fills) == len(original.fills)
        assert len(restored.events) == len(original.events)


class TestTradeJournal:
    """Test TradeJournal class."""

    def test_create_journal(self):
        """Test creating a trade journal."""
        journal = TradeJournal()

        assert journal.session_id is not None
        assert len(journal.get_all_entries()) == 0

    def test_create_journal_with_session_id(self):
        """Test creating a trade journal with custom session ID."""
        journal = TradeJournal(session_id="custom_session")

        assert journal.session_id == "custom_session"

    def test_create_entry(self):
        """Test creating a trade journal entry."""
        journal = TradeJournal()
        position = MockPosition()
        signal = MockSignal()

        entry = journal.create_entry(
            position=position,
            signal=signal,
            correlation_id="corr_123",
        )

        assert entry.entry_id == position.position_id
        assert entry.symbol == position.symbol
        assert entry.side == "buy"  # "long" is normalized to "buy"
        assert entry.entry_price == position.entry_price
        assert entry.position_size == position.quantity
        assert entry.signal_id == signal.signal_id
        assert entry.signal_confidence == signal.confidence
        assert entry.signal_strategy == signal.strategy
        assert entry.correlation_id == "corr_123"
        assert entry.session_id == journal.session_id

    def test_create_entry_with_strategy_name(self):
        """Test creating entry with strategy_name attribute."""
        journal = TradeJournal()
        position = MockPosition()

        class SignalWithStrategyName:
            def __init__(self):
                self.signal_id = "sig_789"
                self.confidence = 0.9
                self.strategy_name = "mean_reversion"

        signal = SignalWithStrategyName()

        entry = journal.create_entry(position=position, signal=signal)

        assert entry.signal_strategy == "mean_reversion"

    def test_create_entry_missing_position_attributes(self):
        """Test that missing position attributes raise ValueError."""
        journal = TradeJournal()

        class BadPosition:
            pass

        signal = MockSignal()

        with pytest.raises(ValueError, match="Position must have"):
            journal.create_entry(position=BadPosition(), signal=signal)

    def test_create_entry_missing_signal_attributes(self):
        """Test that missing signal attributes raise ValueError."""
        journal = TradeJournal()
        position = MockPosition()

        class BadSignal:
            pass

        with pytest.raises(ValueError, match="Signal must have"):
            journal.create_entry(position=position, signal=BadSignal())

    def test_create_entry_invalid_side(self):
        """Test that invalid position side raises ValueError."""
        journal = TradeJournal()

        class BadPosition:
            position_id = "pos_bad"
            symbol = "BTCUSDT"
            side = "invalid_side"
            entry_price = 50000.0
            quantity = 0.1

        signal = MockSignal()

        with pytest.raises(ValueError, match="Invalid position side"):
            journal.create_entry(position=BadPosition(), signal=signal)

    def test_record_fill(self):
        """Test recording a fill."""
        journal = TradeJournal()
        position = MockPosition()
        signal = MockSignal()

        entry = journal.create_entry(position=position, signal=signal)

        fill = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.05,
            fee=0.25,
        )

        updated = journal.record_fill(entry.entry_id, fill)

        assert len(updated.fills) == 1
        assert updated.fills[0] == fill

    def test_record_fill_not_found(self):
        """Test that recording fill for non-existent entry raises KeyError."""
        journal = TradeJournal()

        fill = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.05,
            fee=0.25,
        )

        with pytest.raises(KeyError):
            journal.record_fill("non_existent", fill)

    def test_close_entry(self):
        """Test closing a trade entry."""
        journal = TradeJournal()
        position = MockPosition()
        signal = MockSignal()

        entry = journal.create_entry(position=position, signal=signal)

        closed = journal.close_entry(
            entry_id=entry.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
            exit_signal_id="sig_exit",
        )

        assert closed.is_closed is True
        assert closed.exit_price == 51000.0
        assert closed.exit_reason == ExitReason.TAKE_PROFIT_HIT
        assert closed.realized_pnl == 100.0
        assert closed.exit_signal_id == "sig_exit"

    def test_close_entry_not_found(self):
        """Test that closing non-existent entry raises KeyError."""
        journal = TradeJournal()

        with pytest.raises(KeyError):
            journal.close_entry(
                entry_id="non_existent",
                exit_price=51000.0,
                exit_reason=ExitReason.TAKE_PROFIT_HIT,
                pnl=100.0,
            )

    def test_get_entry(self):
        """Test getting a specific entry."""
        journal = TradeJournal()
        position = MockPosition()
        signal = MockSignal()

        entry = journal.create_entry(position=position, signal=signal)
        retrieved = journal.get_entry(entry.entry_id)

        assert retrieved == entry

    def test_get_entry_not_found(self):
        """Test that getting non-existent entry returns None."""
        journal = TradeJournal()

        assert journal.get_entry("non_existent") is None

    def test_list_entries_no_filter(self):
        """Test listing all entries without filter."""
        journal = TradeJournal()

        # Create multiple entries
        for i in range(3):
            position = MockPosition(position_id=f"pos_{i}", symbol=f"SYM{i}")
            signal = MockSignal(signal_id=f"sig_{i}")
            journal.create_entry(position=position, signal=signal)

        entries = journal.list_entries()

        assert len(entries) == 3

    def test_list_entries_filter_symbol(self):
        """Test filtering entries by symbol."""
        journal = TradeJournal()

        journal.create_entry(
            position=MockPosition(position_id="pos_1", symbol="BTCUSDT"),
            signal=MockSignal(),
        )
        journal.create_entry(
            position=MockPosition(position_id="pos_2", symbol="ETHUSDT"),
            signal=MockSignal(),
        )
        journal.create_entry(
            position=MockPosition(position_id="pos_3", symbol="BTCUSDT"),
            signal=MockSignal(),
        )

        entries = journal.list_entries(symbol="BTCUSDT")

        assert len(entries) == 2
        assert all(e.symbol == "BTCUSDT" for e in entries)

    def test_list_entries_filter_side(self):
        """Test filtering entries by side."""
        journal = TradeJournal()

        journal.create_entry(
            position=MockPosition(position_id="pos_1", side="long"),
            signal=MockSignal(),
        )
        journal.create_entry(
            position=MockPosition(position_id="pos_2", side="short"),
            signal=MockSignal(),
        )

        entries = journal.list_entries(side="buy")

        assert len(entries) == 1
        assert entries[0].side == "buy"

    def test_list_entries_filter_is_open(self):
        """Test filtering entries by open status."""
        journal = TradeJournal()

        entry1 = journal.create_entry(
            position=MockPosition(position_id="pos_1"),
            signal=MockSignal(),
        )
        entry2 = journal.create_entry(
            position=MockPosition(position_id="pos_2"),
            signal=MockSignal(),
        )

        # Close one entry
        journal.close_entry(
            entry_id=entry1.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        open_entries = journal.list_entries(is_open=True)
        closed_entries = journal.list_entries(is_open=False)

        assert len(open_entries) == 1
        assert len(closed_entries) == 1
        assert open_entries[0].entry_id == entry2.entry_id
        assert closed_entries[0].entry_id == entry1.entry_id

    def test_list_entries_filter_exit_reason(self):
        """Test filtering entries by exit reason."""
        journal = TradeJournal()

        entry1 = journal.create_entry(
            position=MockPosition(position_id="pos_1"),
            signal=MockSignal(),
        )
        entry2 = journal.create_entry(
            position=MockPosition(position_id="pos_2"),
            signal=MockSignal(),
        )

        journal.close_entry(
            entry_id=entry1.entry_id,
            exit_price=49000.0,
            exit_reason=ExitReason.STOP_LOSS_HIT,
            pnl=-100.0,
        )
        journal.close_entry(
            entry_id=entry2.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        stop_loss_entries = journal.list_entries(exit_reason=ExitReason.STOP_LOSS_HIT)

        assert len(stop_loss_entries) == 1
        assert stop_loss_entries[0].entry_id == entry1.entry_id

    def test_list_entries_filter_signal_strategy(self):
        """Test filtering entries by signal strategy."""
        journal = TradeJournal()

        journal.create_entry(
            position=MockPosition(position_id="pos_1"),
            signal=MockSignal(signal_id="sig_1", strategy="momentum"),
        )
        journal.create_entry(
            position=MockPosition(position_id="pos_2"),
            signal=MockSignal(signal_id="sig_2", strategy="mean_reversion"),
        )

        entries = journal.list_entries(signal_strategy="momentum")

        assert len(entries) == 1
        assert entries[0].signal_strategy == "momentum"

    def test_list_entries_filter_session_id(self):
        """Test filtering entries by session ID."""
        journal1 = TradeJournal(session_id="session_1")
        journal2 = TradeJournal(session_id="session_2")

        entry1 = journal1.create_entry(
            position=MockPosition(position_id="pos_1"),
            signal=MockSignal(),
        )
        entry2 = journal2.create_entry(
            position=MockPosition(position_id="pos_2"),
            signal=MockSignal(),
        )

        # Add both entries to journal1 for testing (simulate cross-session)
        journal1._entries[entry2.entry_id] = entry2

        entries = journal1.list_entries(session_id="session_1")

        assert len(entries) == 1
        assert entries[0].session_id == "session_1"

    def test_get_all_entries(self):
        """Test getting all entries."""
        journal = TradeJournal()

        for i in range(3):
            journal.create_entry(
                position=MockPosition(position_id=f"pos_{i}"),
                signal=MockSignal(),
            )

        entries = journal.get_all_entries()

        assert len(entries) == 3

    def test_get_open_entries(self):
        """Test getting open entries."""
        journal = TradeJournal()

        entry1 = journal.create_entry(
            position=MockPosition(position_id="pos_1"),
            signal=MockSignal(),
        )
        entry2 = journal.create_entry(
            position=MockPosition(position_id="pos_2"),
            signal=MockSignal(),
        )

        journal.close_entry(
            entry_id=entry1.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        open_entries = journal.get_open_entries()

        assert len(open_entries) == 1
        assert open_entries[0].entry_id == entry2.entry_id

    def test_get_closed_entries(self):
        """Test getting closed entries."""
        journal = TradeJournal()

        entry1 = journal.create_entry(
            position=MockPosition(position_id="pos_1"),
            signal=MockSignal(),
        )
        entry2 = journal.create_entry(
            position=MockPosition(position_id="pos_2"),
            signal=MockSignal(),
        )

        journal.close_entry(
            entry_id=entry1.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        closed_entries = journal.get_closed_entries()

        assert len(closed_entries) == 1
        assert closed_entries[0].entry_id == entry1.entry_id

    def test_get_stats_empty(self):
        """Test getting stats with no entries."""
        journal = TradeJournal()

        stats = journal.get_stats()

        assert stats["total_entries"] == 0
        assert stats["open_entries"] == 0
        assert stats["closed_entries"] == 0
        assert stats["total_pnl"] == 0.0
        assert stats["winning_trades"] == 0
        assert stats["losing_trades"] == 0
        assert stats["win_rate"] == 0.0
        assert stats["avg_pnl"] == 0.0
        assert stats["session_id"] == journal.session_id

    def test_get_stats_with_trades(self):
        """Test getting stats with trades."""
        journal = TradeJournal()

        # Create winning trade
        entry1 = journal.create_entry(
            position=MockPosition(position_id="pos_1"),
            signal=MockSignal(),
        )
        journal.close_entry(
            entry_id=entry1.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        # Create losing trade
        entry2 = journal.create_entry(
            position=MockPosition(position_id="pos_2"),
            signal=MockSignal(),
        )
        journal.close_entry(
            entry_id=entry2.entry_id,
            exit_price=49000.0,
            exit_reason=ExitReason.STOP_LOSS_HIT,
            pnl=-50.0,
        )

        # Create open trade
        journal.create_entry(
            position=MockPosition(position_id="pos_3"),
            signal=MockSignal(),
        )

        stats = journal.get_stats()

        assert stats["total_entries"] == 3
        assert stats["open_entries"] == 1
        assert stats["closed_entries"] == 2
        assert stats["total_pnl"] == 50.0
        assert stats["winning_trades"] == 1
        assert stats["losing_trades"] == 1
        assert stats["win_rate"] == 0.5
        assert stats["avg_pnl"] == 25.0

    def test_clear(self):
        """Test clearing all entries."""
        journal = TradeJournal()

        for i in range(3):
            journal.create_entry(
                position=MockPosition(position_id=f"pos_{i}"),
                signal=MockSignal(),
            )

        journal.clear()

        assert len(journal.get_all_entries()) == 0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        journal = TradeJournal(session_id="test_session")

        entry = journal.create_entry(
            position=MockPosition(),
            signal=MockSignal(),
        )

        data = journal.to_dict()

        assert data["session_id"] == "test_session"
        assert len(data["entries"]) == 1
        assert data["stats"]["total_entries"] == 1

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(UTC)
        data = {
            "session_id": "test_session",
            "entries": [
                {
                    "entry_id": "entry_123",
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "entry_price": 50000.0,
                    "entry_time": now.isoformat(),
                    "position_size": 0.1,
                    "signal_id": "sig_456",
                    "signal_confidence": 0.85,
                    "signal_strategy": "momentum",
                    "created_at": now.isoformat(),
                    "fills": [],
                    "events": [],
                }
            ],
        }

        journal = TradeJournal.from_dict(data)

        assert journal.session_id == "test_session"
        assert len(journal.get_all_entries()) == 1
        assert journal.get_entry("entry_123") is not None

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = TradeJournal(session_id="test_session")

        entry = original.create_entry(
            position=MockPosition(),
            signal=MockSignal(),
        )

        fill = FillRecord(
            fill_id="fill_1",
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.1,
            fee=0.5,
        )
        original.record_fill(entry.entry_id, fill)

        original.close_entry(
            entry_id=entry.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        data = original.to_dict()
        restored = TradeJournal.from_dict(data)

        assert restored.session_id == original.session_id
        assert len(restored.get_all_entries()) == len(original.get_all_entries())

        restored_entry = restored.get_entry(entry.entry_id)
        assert restored_entry is not None
        assert restored_entry.is_closed is True
        assert restored_entry.exit_price == 51000.0


class TestTradeJournalTestTradeSegregation:
    """Test test trade segregation (P0-KPI-GUARDRAILS-002)."""

    def test_trade_entry_is_test_field(self):
        """Test that TradeJournalEntry has is_test field."""
        entry = TradeJournalEntry(
            entry_id="entry_123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_456",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=False,
        )
        assert entry.is_test is False

        test_entry = TradeJournalEntry(
            entry_id="test-entry-123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="test-sig-456",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=True,
        )
        assert test_entry.is_test is True

    def test_trade_journal_get_test_trades(self):
        """Test TradeJournal.get_test_trades() method."""
        journal = TradeJournal()

        # Create production trade
        prod_entry = TradeJournalEntry(
            entry_id="prod_1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_1",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=False,
        )

        # Create test trade
        test_entry = TradeJournalEntry(
            entry_id="test_1",
            symbol="ETHUSDT",
            side="buy",
            entry_price=3000.0,
            entry_time=datetime.now(UTC),
            position_size=0.5,
            signal_id="sig_2",
            signal_confidence=0.75,
            signal_strategy="e2e_test",
            is_test=True,
        )

        journal._entries[prod_entry.entry_id] = prod_entry
        journal._entries[test_entry.entry_id] = test_entry

        test_trades = journal.get_test_trades()
        assert len(test_trades) == 1
        assert test_trades[0].entry_id == "test_1"

    def test_trade_journal_get_production_trades(self):
        """Test TradeJournal.get_production_trades() method."""
        journal = TradeJournal()

        # Create production trade
        prod_entry = TradeJournalEntry(
            entry_id="prod_1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_1",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=False,
        )

        # Create test trade
        test_entry = TradeJournalEntry(
            entry_id="test_1",
            symbol="ETHUSDT",
            side="buy",
            entry_price=3000.0,
            entry_time=datetime.now(UTC),
            position_size=0.5,
            signal_id="sig_2",
            signal_confidence=0.75,
            signal_strategy="e2e_test",
            is_test=True,
        )

        journal._entries[prod_entry.entry_id] = prod_entry
        journal._entries[test_entry.entry_id] = test_entry

        prod_trades = journal.get_production_trades()
        assert len(prod_trades) == 1
        assert prod_trades[0].entry_id == "prod_1"

    def test_list_entries_include_test_trades_default_false(self):
        """Test that list_entries excludes test trades by default."""
        journal = TradeJournal()

        # Create production trade
        prod_entry = TradeJournalEntry(
            entry_id="prod_1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_1",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=False,
        )

        # Create test trade
        test_entry = TradeJournalEntry(
            entry_id="test_1",
            symbol="ETHUSDT",
            side="buy",
            entry_price=3000.0,
            entry_time=datetime.now(UTC),
            position_size=0.5,
            signal_id="sig_2",
            signal_confidence=0.75,
            signal_strategy="e2e_test",
            is_test=True,
        )

        journal._entries[prod_entry.entry_id] = prod_entry
        journal._entries[test_entry.entry_id] = test_entry

        # Default should exclude test trades
        entries = journal.list_entries()
        assert len(entries) == 1
        assert entries[0].entry_id == "prod_1"

    def test_list_entries_include_test_trades_true(self):
        """Test that list_entries includes test trades when requested."""
        journal = TradeJournal()

        # Create production trade
        prod_entry = TradeJournalEntry(
            entry_id="prod_1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_1",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=False,
        )

        # Create test trade
        test_entry = TradeJournalEntry(
            entry_id="test_1",
            symbol="ETHUSDT",
            side="buy",
            entry_price=3000.0,
            entry_time=datetime.now(UTC),
            position_size=0.5,
            signal_id="sig_2",
            signal_confidence=0.75,
            signal_strategy="e2e_test",
            is_test=True,
        )

        journal._entries[prod_entry.entry_id] = prod_entry
        journal._entries[test_entry.entry_id] = test_entry

        # Include test trades
        entries = journal.list_entries(include_test_trades=True)
        assert len(entries) == 2

    def test_detect_test_trade_by_signal_id(self):
        """Test detect_test_trade detects test trades by signal_id."""
        journal = TradeJournal()

        entry = TradeJournalEntry(
            entry_id="entry_1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="test-signal-123",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=False,
        )

        assert journal.detect_test_trade(entry) is True

    def test_detect_test_trade_by_entry_id(self):
        """Test detect_test_trade detects test trades by entry_id."""
        journal = TradeJournal()

        entry = TradeJournalEntry(
            entry_id="test-entry-123",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_1",
            signal_confidence=0.85,
            signal_strategy="momentum",
            is_test=False,
        )

        assert journal.detect_test_trade(entry) is True

    def test_detect_test_trade_by_strategy(self):
        """Test detect_test_trade detects test trades by signal_strategy."""
        journal = TradeJournal()

        entry = TradeJournalEntry(
            entry_id="entry_1",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_1",
            signal_confidence=0.85,
            signal_strategy="e2e_test_strategy",
            is_test=False,
        )

        assert journal.detect_test_trade(entry) is True

    def test_serialization_preserves_is_test(self):
        """Test that is_test field is preserved during serialization."""
        entry = TradeJournalEntry(
            entry_id="test_entry",
            symbol="BTCUSDT",
            side="buy",
            entry_price=50000.0,
            entry_time=datetime.now(UTC),
            position_size=0.1,
            signal_id="sig_1",
            signal_confidence=0.85,
            signal_strategy="e2e_test",
            is_test=True,
        )

        data = entry.to_dict()
        assert data["is_test"] is True

        restored = TradeJournalEntry.from_dict(data)
        assert restored.is_test is True
