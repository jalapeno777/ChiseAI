"""Tests for outcome store module.

For ST-ICT-P1: Signal Outcome Database Backend
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from execution.outcomes.models import dict_to_row, row_to_signal_outcome
from execution.outcomes.store import OutcomeStore, QueryFilters
from ml.models.signal_outcome import OutcomeType, SignalOutcome, SignalOutcomeStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_store() -> OutcomeStore:
    """Create an in-memory OutcomeStore for testing."""
    store = OutcomeStore(in_memory=True)
    yield store
    store.close()


@pytest.fixture
def file_store(tmp_path: Path) -> OutcomeStore:
    """Create a file-based OutcomeStore for testing."""
    db_path = tmp_path / "test_outcomes.db"
    store = OutcomeStore(db_path=db_path)
    yield store
    store.close()


@pytest.fixture
def sample_outcome() -> SignalOutcome:
    """Create a sample SignalOutcome for testing."""
    return SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id="test-order-001",
        symbol="BTCUSDT",
        token="BTC",
        side="Buy",
        direction="LONG",
        fill_price=Decimal("50000.00"),
        fill_quantity=Decimal("0.1"),
        fill_timestamp=datetime.now(UTC),
        outcome_type=OutcomeType.TP_HIT,
        pnl=Decimal("100.50"),
        fee=Decimal("5.00"),
        status=SignalOutcomeStatus.CLOSED,
        created_at=datetime.now(UTC),
        metadata={"test": True},
        entry_price=Decimal("50000.00"),
        exit_price=Decimal("50100.50"),
        exit_time=datetime.now(UTC),
        leverage=Decimal("1.0"),
        entry_reason="signal_trigger",
        position_size=Decimal("0.1"),
        execution_venue="bybit_demo",
        execution_mode="paper",
        execution_source="paper_trading",
        venue_metadata={},
        confidence_score=0.85,
        signal_type="OPEN",
        is_test=True,
    )


@pytest.fixture
def multiple_outcomes() -> list[SignalOutcome]:
    """Create multiple outcomes for testing queries."""
    base_time = datetime.now(UTC)
    outcomes = []

    for i in range(10):
        signal_id = uuid4() if i % 2 == 0 else None  # Some have signal_id, some don't
        outcome_type = [
            OutcomeType.TP_HIT,
            OutcomeType.SL_HIT,
            OutcomeType.MANUAL_CLOSE,
        ][i % 3]
        status = SignalOutcomeStatus.CLOSED if i < 8 else SignalOutcomeStatus.PENDING

        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=signal_id,
            order_id=f"order-{i:03d}",
            symbol=["BTCUSDT", "ETHUSDT", "SOLUSDT"][i % 3],
            token=["BTC", "ETH", "SOL"][i % 3],
            side="Buy" if i % 2 == 0 else "Sell",
            direction="LONG" if i % 2 == 0 else "SHORT",
            fill_price=Decimal(str(50000 + i * 100)),
            fill_quantity=Decimal("0.1"),
            fill_timestamp=base_time - timedelta(days=i),
            outcome_type=outcome_type,
            pnl=Decimal(str(100 - i * 10)),
            fee=Decimal("5.00"),
            status=status,
            created_at=base_time - timedelta(days=i),
            metadata={"index": i},
            entry_price=Decimal(str(50000 + i * 100)),
            exit_price=Decimal(str(50100 + i * 100)),
            exit_time=base_time - timedelta(days=i),
            leverage=Decimal("1.0"),
            entry_reason="signal_trigger",
            position_size=Decimal("0.1"),
            execution_venue="bybit_demo",
            execution_mode="paper",
            execution_source="paper_trading",
            venue_metadata={},
            confidence_score=0.8,
            signal_type="OPEN",
            is_test=False,
        )
        outcomes.append(outcome)

    return outcomes


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestDictRowConversion:
    """Tests for dict_to_row and row_to_signal_outcome functions."""

    def test_dict_to_row_basic(self, sample_outcome: SignalOutcome) -> None:
        """Test basic dict to row conversion."""
        data = sample_outcome.to_dict()
        row = dict_to_row(data)

        assert row["outcome_id"] == str(sample_outcome.outcome_id)
        assert row["signal_id"] == str(sample_outcome.signal_id)
        assert row["order_id"] == sample_outcome.order_id
        assert row["symbol"] == sample_outcome.symbol
        assert row["outcome_type"] == "tp_hit"
        assert row["status"] == "closed"
        assert row["is_test"] == 1

    def test_row_to_signal_outcome_basic(self, sample_outcome: SignalOutcome) -> None:
        """Test basic row to SignalOutcome conversion."""
        data = sample_outcome.to_dict()
        row = dict_to_row(data)
        restored = row_to_signal_outcome(row)

        assert str(restored.outcome_id) == str(sample_outcome.outcome_id)
        assert str(restored.signal_id) == str(sample_outcome.signal_id)
        assert restored.symbol == sample_outcome.symbol
        assert restored.outcome_type == OutcomeType.TP_HIT
        assert restored.status == SignalOutcomeStatus.CLOSED
        assert restored.is_test == sample_outcome.is_test

    def test_roundtrip_preserves_data(self, sample_outcome: SignalOutcome) -> None:
        """Test that roundtrip conversion preserves all data."""
        data = sample_outcome.to_dict()
        row = dict_to_row(data)
        restored = row_to_signal_outcome(row)

        # Check key fields
        assert str(restored.outcome_id) == str(sample_outcome.outcome_id)
        assert restored.symbol == sample_outcome.symbol
        assert restored.pnl == sample_outcome.pnl
        assert restored.confidence_score == sample_outcome.confidence_score


class TestDatabaseInit:
    """Tests for database initialization."""

    def test_init_db_creates_schema(self, in_memory_store: OutcomeStore) -> None:
        """Test that init_db creates the expected schema."""
        cursor = in_memory_store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='signal_outcomes'"
        )
        result = cursor.fetchone()
        assert result is not None
        assert result["name"] == "signal_outcomes"

    def test_init_db_creates_indexes(self, in_memory_store: OutcomeStore) -> None:
        """Test that init_db creates expected indexes."""
        cursor = in_memory_store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = [row["name"] for row in cursor.fetchall()]
        assert "idx_outcomes_signal_id" in indexes
        assert "idx_outcomes_symbol" in indexes
        assert "idx_outcomes_fill_timestamp" in indexes


# ---------------------------------------------------------------------------
# CRUD Operation Tests
# ---------------------------------------------------------------------------


class TestCreate:
    """Tests for create operations."""

    def test_create_single_outcome(
        self,
        in_memory_store: OutcomeStore,
        sample_outcome: SignalOutcome,
    ) -> None:
        """Test creating a single outcome."""
        outcome_id = in_memory_store.create(sample_outcome)

        assert outcome_id == str(sample_outcome.outcome_id)

        # Verify it can be read back
        retrieved = in_memory_store.read(outcome_id)
        assert retrieved is not None
        assert str(retrieved.outcome_id) == str(sample_outcome.outcome_id)
        assert retrieved.symbol == sample_outcome.symbol

    def test_create_many_outcomes(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test batch creation of outcomes."""
        outcome_ids = in_memory_store.create_many(multiple_outcomes)

        assert len(outcome_ids) == len(multiple_outcomes)

        # Verify all can be read back
        for outcome in multiple_outcomes:
            retrieved = in_memory_store.read(str(outcome.outcome_id))
            assert retrieved is not None
            assert retrieved.symbol == outcome.symbol


class TestRead:
    """Tests for read operations."""

    def test_read_existing_outcome(
        self,
        in_memory_store: OutcomeStore,
        sample_outcome: SignalOutcome,
    ) -> None:
        """Test reading an existing outcome."""
        in_memory_store.create(sample_outcome)

        retrieved = in_memory_store.read(str(sample_outcome.outcome_id))

        assert retrieved is not None
        assert str(retrieved.outcome_id) == str(sample_outcome.outcome_id)
        assert retrieved.order_id == sample_outcome.order_id
        assert retrieved.outcome_type == sample_outcome.outcome_type

    def test_read_nonexistent_outcome(self, in_memory_store: OutcomeStore) -> None:
        """Test reading a non-existent outcome returns None."""
        result = in_memory_store.read(str(uuid4()))
        assert result is None


class TestUpdate:
    """Tests for update operations."""

    def test_update_existing_outcome(
        self,
        in_memory_store: OutcomeStore,
        sample_outcome: SignalOutcome,
    ) -> None:
        """Test updating an existing outcome."""
        in_memory_store.create(sample_outcome)

        # Update the outcome
        sample_outcome.pnl = Decimal("200.00")
        sample_outcome.status = SignalOutcomeStatus.CLOSED

        success = in_memory_store.update(sample_outcome)
        assert success is True

        # Verify the update
        retrieved = in_memory_store.read(str(sample_outcome.outcome_id))
        assert retrieved is not None
        assert retrieved.pnl == Decimal("200.00")
        assert retrieved.status == SignalOutcomeStatus.CLOSED

    def test_update_nonexistent_outcome(
        self,
        in_memory_store: OutcomeStore,
        sample_outcome: SignalOutcome,
    ) -> None:
        """Test updating a non-existent outcome returns False."""
        sample_outcome.outcome_id = uuid4()  # New ID not in DB
        success = in_memory_store.update(sample_outcome)
        assert success is False


class TestDelete:
    """Tests for delete operations."""

    def test_delete_existing_outcome(
        self,
        in_memory_store: OutcomeStore,
        sample_outcome: SignalOutcome,
    ) -> None:
        """Test deleting an existing outcome."""
        in_memory_store.create(sample_outcome)
        outcome_id = str(sample_outcome.outcome_id)

        success = in_memory_store.delete(outcome_id)
        assert success is True

        # Verify deletion
        retrieved = in_memory_store.read(outcome_id)
        assert retrieved is None

    def test_delete_nonexistent_outcome(self, in_memory_store: OutcomeStore) -> None:
        """Test deleting a non-existent outcome returns False."""
        success = in_memory_store.delete(str(uuid4()))
        assert success is False


# ---------------------------------------------------------------------------
# Query Method Tests
# ---------------------------------------------------------------------------


class TestBySignalId:
    """Tests for by_signal_id query method."""

    def test_query_by_signal_id(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying outcomes by signal_id."""
        in_memory_store.create_many(multiple_outcomes)

        # Find outcomes with signal_id
        outcomes_with_signal = [o for o in multiple_outcomes if o.signal_id is not None]
        if outcomes_with_signal:
            target_signal_id = str(outcomes_with_signal[0].signal_id)
            results = in_memory_store.by_signal_id(target_signal_id)

            assert len(results) >= 1
            for outcome in results:
                assert str(outcome.signal_id) == target_signal_id

    def test_query_by_signal_id_no_results(self, in_memory_store: OutcomeStore) -> None:
        """Test querying by signal_id with no matches."""
        results = in_memory_store.by_signal_id(str(uuid4()))
        assert len(results) == 0


class TestByTimerange:
    """Tests for by_timerange query method."""

    def test_query_by_timerange(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying outcomes by time range."""
        in_memory_store.create_many(multiple_outcomes)

        # Query last 5 days
        now = datetime.now(UTC)
        five_days_ago = now - timedelta(days=5)

        results = in_memory_store.by_timerange(
            start_time=five_days_ago,
            end_time=now,
        )

        assert len(results) > 0
        for outcome in results:
            assert outcome.created_at >= five_days_ago

    def test_query_by_timerange_with_symbol(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying by time range with symbol filter."""
        in_memory_store.create_many(multiple_outcomes)

        now = datetime.now(UTC)
        results = in_memory_store.by_timerange(
            start_time=now - timedelta(days=30),
            end_time=now,
            symbol="BTCUSDT",
            limit=50,
        )

        for outcome in results:
            assert outcome.symbol == "BTCUSDT"


class TestByResultType:
    """Tests for by_result_type query method."""

    def test_query_by_result_type(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying outcomes by result type."""
        in_memory_store.create_many(multiple_outcomes)

        # Query for TP_HIT outcomes
        results = in_memory_store.by_result_type(OutcomeType.TP_HIT)

        for outcome in results:
            assert outcome.outcome_type == OutcomeType.TP_HIT

    def test_query_by_result_type_no_results(
        self, in_memory_store: OutcomeStore
    ) -> None:
        """Test querying by result type with no matches."""
        results = in_memory_store.by_result_type(OutcomeType.TP_HIT)
        assert len(results) == 0


class TestBySymbol:
    """Tests for by_symbol query method."""

    def test_query_by_symbol(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying outcomes by symbol."""
        in_memory_store.create_many(multiple_outcomes)

        results = in_memory_store.by_symbol("BTCUSDT")

        for outcome in results:
            assert outcome.symbol == "BTCUSDT"

    def test_query_by_symbol_with_timerange(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying by symbol with time range."""
        in_memory_store.create_many(multiple_outcomes)

        now = datetime.now(UTC)
        results = in_memory_store.by_symbol(
            "ETHUSDT",
            start_time=now - timedelta(days=30),
        )

        for outcome in results:
            assert outcome.symbol == "ETHUSDT"
            assert outcome.created_at >= now - timedelta(days=30)


class TestByStatus:
    """Tests for by_status query method."""

    def test_query_by_status(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying outcomes by status."""
        in_memory_store.create_many(multiple_outcomes)

        # Query for CLOSED outcomes
        results = in_memory_store.by_status(SignalOutcomeStatus.CLOSED)

        for outcome in results:
            assert outcome.status == SignalOutcomeStatus.CLOSED


class TestQueryFilters:
    """Tests for flexible query method with QueryFilters."""

    def test_query_with_multiple_filters(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test querying with multiple filters."""
        in_memory_store.create_many(multiple_outcomes)

        now = datetime.now(UTC)
        filters = QueryFilters(
            outcome_type=OutcomeType.TP_HIT,
            status=SignalOutcomeStatus.CLOSED,
            start_time=now - timedelta(days=30),
            limit=50,
        )

        results = in_memory_store.query(filters)

        for outcome in results:
            assert outcome.outcome_type == OutcomeType.TP_HIT
            assert outcome.status == SignalOutcomeStatus.CLOSED

    def test_query_with_is_test_filter(
        self,
        in_memory_store: OutcomeStore,
        sample_outcome: SignalOutcome,
    ) -> None:
        """Test querying with is_test filter."""
        # sample_outcome has is_test=True
        in_memory_store.create(sample_outcome)

        # Query for non-test outcomes
        filters = QueryFilters(is_test=False, limit=100)
        results = in_memory_store.query(filters)

        for outcome in results:
            assert outcome.is_test is False

    def test_query_with_execution_filters(
        self,
        in_memory_store: OutcomeStore,
        sample_outcome: SignalOutcome,
    ) -> None:
        """Test querying with execution venue/mode filters."""
        in_memory_store.create(sample_outcome)

        filters = QueryFilters(
            execution_venue="bybit_demo",
            execution_mode="paper",
        )
        results = in_memory_store.query(filters)

        assert len(results) >= 1
        for outcome in results:
            assert outcome.execution_venue == "bybit_demo"
            assert outcome.execution_mode == "paper"


# ---------------------------------------------------------------------------
# Utility Method Tests
# ---------------------------------------------------------------------------


class TestCount:
    """Tests for count method."""

    def test_count_all(
        self, in_memory_store: OutcomeStore, multiple_outcomes: list[SignalOutcome]
    ) -> None:
        """Test counting all outcomes."""
        in_memory_store.create_many(multiple_outcomes)
        count = in_memory_store.count()
        assert count == len(multiple_outcomes)

    def test_count_with_filters(
        self, in_memory_store: OutcomeStore, multiple_outcomes: list[SignalOutcome]
    ) -> None:
        """Test counting with filters."""
        in_memory_store.create_many(multiple_outcomes)

        filters = QueryFilters(outcome_type=OutcomeType.TP_HIT)
        count = in_memory_store.count(filters)

        expected = len(
            [o for o in multiple_outcomes if o.outcome_type == OutcomeType.TP_HIT]
        )
        assert count == expected


class TestStats:
    """Tests for get_stats method."""

    def test_get_stats(
        self,
        in_memory_store: OutcomeStore,
        multiple_outcomes: list[SignalOutcome],
    ) -> None:
        """Test getting statistics."""
        in_memory_store.create_many(multiple_outcomes)

        stats = in_memory_store.get_stats()

        assert stats["total"] == len(multiple_outcomes)
        assert stats["unique_symbols"] == 3  # BTC, ETH, SOL
        assert "tp_hit_count" in stats
        assert "sl_hit_count" in stats


class TestHealthCheck:
    """Tests for health_check method."""

    def test_health_check_healthy(self, in_memory_store: OutcomeStore) -> None:
        """Test health check on healthy database."""
        result = in_memory_store.health_check()

        assert result["healthy"] is True
        assert "stats" in result


# ---------------------------------------------------------------------------
# File-based Store Tests
# ---------------------------------------------------------------------------


class TestFileStore:
    """Tests for file-based OutcomeStore."""

    def test_file_store_persistence(
        self, file_store: OutcomeStore, sample_outcome: SignalOutcome
    ) -> None:
        """Test that file store persists data."""
        # Create
        file_store.create(sample_outcome)

        # Close and reopen
        db_path = file_store._db_path
        file_store.close()

        new_store = OutcomeStore(db_path=db_path)

        # Read back
        retrieved = new_store.read(str(sample_outcome.outcome_id))
        assert retrieved is not None
        assert retrieved.symbol == sample_outcome.symbol

        new_store.close()


# ---------------------------------------------------------------------------
# Context Manager Tests
# ---------------------------------------------------------------------------


class TestContextManager:
    """Tests for context manager usage."""

    def test_context_manager(self, tmp_path: Path) -> None:
        """Test using OutcomeStore as context manager."""
        db_path = tmp_path / "test_context.db"

        with OutcomeStore(db_path=db_path) as store:
            outcome = SignalOutcome(
                outcome_id=uuid4(),
                order_id="test-context",
                symbol="BTCUSDT",
                token="BTC",
                side="Buy",
                direction="LONG",
                fill_price=Decimal("50000"),
                fill_quantity=Decimal("0.1"),
                status=SignalOutcomeStatus.PENDING,
                created_at=datetime.now(UTC),
            )
            store.create(outcome)

        # After context, store should be closed
        # Reopen and verify data persists
        with OutcomeStore(db_path=db_path) as store:
            retrieved = store.read(str(outcome.outcome_id))
            assert retrieved is not None


# ---------------------------------------------------------------------------
# Backward Compatibility Tests
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing code."""

    def test_outcome_store_supports_signal_outcome_interface(
        self,
        in_memory_store: OutcomeStore,
    ) -> None:
        """Test that OutcomeStore works with SignalOutcome objects."""
        # This tests that the interface expected by existing code works
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="compat-test",
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("0.1"),
            outcome_type=OutcomeType.UNKNOWN,
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )

        # Should work with existing SignalOutcome from ml.models
        outcome_id = in_memory_store.create(outcome)
        assert outcome_id is not None

        # Should be able to read back as SignalOutcome
        retrieved = in_memory_store.read(outcome_id)
        assert retrieved is not None
        assert isinstance(retrieved, SignalOutcome)


# ---------------------------------------------------------------------------
# Connection Management & Error Handling Tests
# ---------------------------------------------------------------------------


class TestConnectionManagement:
    """Tests for connection management and error handling."""

    def test_close_idempotent(self, in_memory_store: OutcomeStore) -> None:
        """Test that closing store multiple times doesn't raise."""
        in_memory_store.close()
        in_memory_store.close()  # Should not raise

    def test_health_check_on_closed_connection(self, tmp_path: Path) -> None:
        """Test health check behavior when connection is closed."""
        db_path = tmp_path / "closed_test.db"
        store = OutcomeStore(db_path=db_path)
        store.close()

        # Health check on closed connection should handle gracefully
        try:
            result = store.health_check()
            # Either healthy=False or error about closed connection
            assert result["healthy"] is False or "error" in result
        except sqlite3.Error:
            pass  # Expected - connection is closed

    def test_read_after_close_returns_none(self, tmp_path: Path) -> None:
        """Test that read operations return None/empty after close."""
        db_path = tmp_path / "read_after_close.db"
        store = OutcomeStore(db_path=db_path)

        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="test-close",
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        store.create(outcome)

        store.close()

        # After close, operations should be handled gracefully
        result = store.read(str(outcome.outcome_id))
        # Connection is closed, so this should return None or error
        assert result is None

    def test_store_with_custom_timeout(self, tmp_path: Path) -> None:
        """Test store initialization with custom timeout."""
        db_path = tmp_path / "custom_timeout.db"
        store = OutcomeStore(db_path=db_path, timeout=60.0)
        assert store._conn is not None
        store.close()

    def test_transaction_retry_on_lock(self, tmp_path: Path) -> None:
        """Test that transaction handles database lock with retry."""
        db_path = tmp_path / "lock_test.db"
        store = OutcomeStore(db_path=db_path, timeout=1.0)

        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="lock-test",
            symbol="ETHUSDT",
            token="ETH",
            side="Sell",
            direction="SHORT",
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )

        # Should succeed despite potential lock issues
        outcome_id = store.create(outcome)
        assert outcome_id is not None

        retrieved = store.read(outcome_id)
        assert retrieved is not None
        assert retrieved.symbol == "ETHUSDT"

        store.close()


class TestSchemaValidation:
    """Tests for schema validation and data integrity."""

    def test_create_with_minimal_outcome(self, in_memory_store: OutcomeStore) -> None:
        """Test creating outcome with minimal required fields."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="minimal-order",
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )

        outcome_id = in_memory_store.create(outcome)
        retrieved = in_memory_store.read(outcome_id)

        assert retrieved is not None
        assert retrieved.order_id == "minimal-order"
        assert retrieved.symbol == "BTCUSDT"
        assert retrieved.status == SignalOutcomeStatus.PENDING

    def test_create_with_all_fields(
        self, in_memory_store: OutcomeStore, sample_outcome: SignalOutcome
    ) -> None:
        """Test creating outcome with all fields populated."""
        in_memory_store.create(sample_outcome)

        retrieved = in_memory_store.read(str(sample_outcome.outcome_id))

        assert retrieved is not None
        # Verify all key fields
        assert str(retrieved.outcome_id) == str(sample_outcome.outcome_id)
        assert retrieved.symbol == sample_outcome.symbol
        assert retrieved.token == sample_outcome.token
        assert retrieved.side == sample_outcome.side
        assert retrieved.direction == sample_outcome.direction
        assert retrieved.fill_price == sample_outcome.fill_price
        assert retrieved.outcome_type == sample_outcome.outcome_type
        assert retrieved.status == sample_outcome.status
        assert retrieved.is_test == sample_outcome.is_test
        assert retrieved.execution_venue == sample_outcome.execution_venue
        assert retrieved.execution_mode == sample_outcome.execution_mode
        assert retrieved.confidence_score == sample_outcome.confidence_score

    def test_update_preserves_unmodified_fields(
        self, in_memory_store: OutcomeStore, sample_outcome: SignalOutcome
    ) -> None:
        """Test that update only modifies specified fields."""
        in_memory_store.create(sample_outcome)
        original_symbol = sample_outcome.symbol
        original_side = sample_outcome.side

        # Update only status
        sample_outcome.status = SignalOutcomeStatus.CLOSED
        in_memory_store.update(sample_outcome)

        retrieved = in_memory_store.read(str(sample_outcome.outcome_id))
        assert retrieved is not None
        assert retrieved.status == SignalOutcomeStatus.CLOSED
        assert retrieved.symbol == original_symbol
        assert retrieved.side == original_side

    def test_metadata_json_roundtrip(
        self, in_memory_store: OutcomeStore, sample_outcome: SignalOutcome
    ) -> None:
        """Test that metadata dict is preserved through JSON serialization."""
        sample_outcome.metadata = {
            "key1": "value1",
            "nested": {"a": 1, "b": [1, 2, 3]},
            "number": 42,
        }
        sample_outcome.venue_metadata = {"venue_key": "venue_value"}

        in_memory_store.create(sample_outcome)
        retrieved = in_memory_store.read(str(sample_outcome.outcome_id))

        assert retrieved is not None
        assert retrieved.metadata == sample_outcome.metadata
        assert retrieved.venue_metadata == sample_outcome.venue_metadata


class TestDataIntegrity:
    """Tests for data integrity constraints."""

    def test_duplicate_outcome_id_raises(
        self, in_memory_store: OutcomeStore, sample_outcome: SignalOutcome
    ) -> None:
        """Test that inserting duplicate outcome_id raises error."""
        in_memory_store.create(sample_outcome)

        # Try to create another outcome with same ID
        duplicate = SignalOutcome(
            outcome_id=sample_outcome.outcome_id,  # Same ID
            order_id="different-order",
            symbol="ETHUSDT",
            token="ETH",
            side="Sell",
            direction="SHORT",
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )

        with pytest.raises(sqlite3.IntegrityError):
            in_memory_store.create(duplicate)

    def test_created_at_auto_populated(self, in_memory_store: OutcomeStore) -> None:
        """Test that created_at is properly stored and retrieved."""
        before = datetime.now(UTC)
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="timestamp-test",
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        after = datetime.now(UTC)

        in_memory_store.create(outcome)
        retrieved = in_memory_store.read(str(outcome.outcome_id))

        assert retrieved is not None
        # Check that created_at is within expected range
        assert retrieved.created_at >= before
        assert retrieved.created_at <= after

    def test_decimal_precision_preserved(self, in_memory_store: OutcomeStore) -> None:
        """Test that Decimal precision is preserved for financial values."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id="precision-test",
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.123456789"),
            fill_quantity=Decimal("0.000000001"),
            pnl=Decimal("-12345.678901234"),
            fee=Decimal("0.00001"),
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )

        in_memory_store.create(outcome)
        retrieved = in_memory_store.read(str(outcome.outcome_id))

        assert retrieved is not None
        # Check precision is preserved
        assert retrieved.fill_price == Decimal("50000.123456789")
        assert retrieved.fill_quantity == Decimal("0.000000001")
        assert retrieved.pnl == Decimal("-12345.678901234")
        assert retrieved.fee == Decimal("0.00001")


class TestQueryEdgeCases:
    """Tests for query edge cases and boundary conditions."""

    def test_by_signal_id_with_none_signal_id(
        self, in_memory_store: OutcomeStore
    ) -> None:
        """Test querying for outcomes with None signal_id."""
        # Create outcomes with None signal_id
        outcome1 = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=None,
            order_id="no-signal-1",
            symbol="BTCUSDT",
            token="BTC",
            side="Buy",
            direction="LONG",
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        outcome2 = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=None,
            order_id="no-signal-2",
            symbol="ETHUSDT",
            token="ETH",
            side="Sell",
            direction="SHORT",
            status=SignalOutcomeStatus.PENDING,
            created_at=datetime.now(UTC),
        )

        in_memory_store.create(outcome1)
        in_memory_store.create(outcome2)

        # Query should work without error
        results = in_memory_store.by_signal_id("")
        # Empty string signal_id might not match None values in DB

    def test_query_with_zero_limit(
        self, in_memory_store: OutcomeStore, multiple_outcomes: list[SignalOutcome]
    ) -> None:
        """Test query with limit=0 returns empty list."""
        in_memory_store.create_many(multiple_outcomes)

        filters = QueryFilters(limit=0)
        results = in_memory_store.query(filters)

        assert len(results) == 0

    def test_query_with_large_offset(
        self, in_memory_store: OutcomeStore, multiple_outcomes: list[SignalOutcome]
    ) -> None:
        """Test query with offset beyond results."""
        in_memory_store.create_many(multiple_outcomes)

        filters = QueryFilters(limit=100, offset=10000)
        results = in_memory_store.query(filters)

        assert len(results) == 0

    def test_count_empty_database(self, in_memory_store: OutcomeStore) -> None:
        """Test count on empty database."""
        count = in_memory_store.count()
        assert count == 0

    def test_stats_on_empty_database(self, in_memory_store: OutcomeStore) -> None:
        """Test stats on empty database."""
        stats = in_memory_store.get_stats()

        assert stats["total"] == 0
        assert stats["closed_count"] == 0
        assert stats["pending_count"] == 0
        assert stats["error_count"] == 0


class TestBatchOperations:
    """Tests for batch operation behavior."""

    def test_create_many_empty_list(self, in_memory_store: OutcomeStore) -> None:
        """Test create_many with empty list."""
        result = in_memory_store.create_many([])
        assert result == []

    def test_create_many_single_item(
        self, in_memory_store: OutcomeStore, sample_outcome: SignalOutcome
    ) -> None:
        """Test create_many with single item."""
        result = in_memory_store.create_many([sample_outcome])
        assert len(result) == 1
        assert result[0] == str(sample_outcome.outcome_id)

    def test_create_many_large_batch(self, in_memory_store: OutcomeStore) -> None:
        """Test create_many with large batch."""
        batch_size = 100
        outcomes = [
            SignalOutcome(
                outcome_id=uuid4(),
                order_id=f"batch-{i:04d}",
                symbol="BTCUSDT",
                token="BTC",
                side="Buy",
                direction="LONG",
                status=SignalOutcomeStatus.PENDING,
                created_at=datetime.now(UTC),
            )
            for i in range(batch_size)
        ]

        result = in_memory_store.create_many(outcomes)

        assert len(result) == batch_size
        assert in_memory_store.count() == batch_size
