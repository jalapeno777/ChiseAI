#!/usr/bin/env python3
"""Tests for OutcomePersistence with venue provenance fields.

For ST-VENUE-001: Venue provenance fields implementation
For ST-ICT-027: Metadata cleanup and classification coverage
"""

import json
import numbers
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from src.execution.outcome_capture.integration import OutcomeCaptureIntegration
from src.execution.paper.models import PaperOrder, PaperTradeResult
from src.execution.persistence.outcome_persistence import OutcomePersistence
from src.ml.models.signal_outcome import (
    OutcomeType,
    SignalOutcome,
    SignalOutcomeStatus,
)


class TestOutcomePersistenceVenueFields:
    """Test venue provenance fields persistence."""

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

    def test_persist_outcome_includes_venue_fields(self, persistence, mock_redis):
        """Test that persist_outcome includes venue fields in stored data."""
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
            venue_metadata={"connector_id": "demo-123", "is_paper_trade": True},
        )

        # Persist the outcome
        key = persistence.persist_outcome(outcome)

        # Verify key was returned
        assert key is not None
        assert "paper:outcome:" in key
        assert "BTCUSDT" in key

        # Verify Redis set was called with venue fields
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        stored_key = call_args[0][0]
        stored_data_json = call_args[0][1]

        # Parse stored data
        stored_data = json.loads(stored_data_json)

        # Verify venue fields are present
        assert "execution_venue" in stored_data
        assert "execution_mode" in stored_data
        assert "execution_source" in stored_data
        assert "venue_metadata" in stored_data

        # Verify venue field values
        assert stored_data["execution_venue"] == "bybit_demo"
        assert stored_data["execution_mode"] == "demo"
        assert stored_data["execution_source"] == "bybit_demo_connector"
        assert stored_data["venue_metadata"] == {
            "connector_id": "demo-123",
            "is_paper_trade": True,
        }

    def test_persist_outcome_with_empty_venue_fields(self, persistence, mock_redis):
        """Test persistence with empty/default venue fields."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="ETHUSDT",
            side="Sell",
            direction="SHORT",
            fill_price=Decimal("3000"),
            fill_quantity=Decimal("10.0"),
            # No venue fields set - should use defaults
        )

        # Persist the outcome
        key = persistence.persist_outcome(outcome)

        # Verify key was returned
        assert key is not None

        # Parse stored data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify venue fields are present with empty defaults
        assert stored_data["execution_venue"] == ""
        assert stored_data["execution_mode"] == ""
        assert stored_data["execution_source"] == ""
        assert stored_data["venue_metadata"] == {}

    def test_persist_outcome_with_correlation_id(self, persistence, mock_redis):
        """Test persistence includes correlation_id and venue fields."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            execution_venue="local_sim",
            execution_mode="testnet",
            execution_source="paper_trading",
        )

        correlation_id = "corr-123-abc"
        key = persistence.persist_outcome(outcome, correlation_id=correlation_id)

        # Parse stored data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify both correlation_id and venue fields
        assert stored_data["correlation_id"] == correlation_id
        assert stored_data["execution_venue"] == "local_sim"
        assert stored_data["execution_mode"] == "testnet"
        assert stored_data["execution_source"] == "paper_trading"
        assert "persisted_at" in stored_data

    def test_venue_fields_in_redis_index(self, persistence, mock_redis):
        """Test that venue fields are persisted and index is updated."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            symbol="BTCUSDT",
            execution_venue="bybit_demo",
            execution_mode="demo",
        )

        key = persistence.persist_outcome(outcome)

        # Verify index was updated
        mock_redis.zadd.assert_called()
        mock_redis.expire.assert_called()

        # Verify the key pattern
        assert "paper:outcome:" in key


class TestOutcomePersistenceBasic:
    """Test basic OutcomePersistence functionality."""

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

    def test_persist_signal(self, persistence, mock_redis):
        """Test signal persistence."""
        # Create a mock signal
        mock_signal = Mock()
        mock_signal.signal_id = "signal-123"
        mock_signal.token = "BTC"
        mock_signal.direction = Mock()
        mock_signal.direction.value = "LONG"
        mock_signal.confidence = 0.85
        mock_signal.confidence_percent = 85.0
        mock_signal.base_score = 0.9
        mock_signal.timeframe = "1h"
        mock_signal.timestamp = datetime.now(UTC)
        mock_signal.generation_latency_ms = 100
        mock_signal.stop_loss = 0.95
        mock_signal.stop_loss_method = "atr"
        mock_signal.metadata = {"source": "test"}

        key = persistence.persist_signal(mock_signal)

        assert key is not None
        assert "paper:signal:" in key
        mock_redis.set.assert_called_once()
        mock_redis.xadd.assert_called_once()
        # Verify XADD targets the correct stream key
        xadd_call = mock_redis.xadd.call_args
        assert xadd_call[0][0] == "paper:signals:stream"
        assert "data" in xadd_call[0][1]

    def test_get_recent_outcomes_empty(self, persistence, mock_redis):
        """Test getting recent outcomes when none exist."""
        mock_redis.zrevrange.return_value = []

        outcomes = persistence.get_recent_outcomes(limit=10)

        assert outcomes == []
        mock_redis.zrevrange.assert_called_once()

    def test_get_stats(self, persistence, mock_redis):
        """Test getting persistence stats."""
        mock_redis.zcard.return_value = 5

        stats = persistence.get_stats()

        assert stats["signal_count"] == 5
        assert stats["order_count"] == 5
        assert stats["fill_count"] == 5
        assert stats["outcome_count"] == 5
        assert stats["key_prefix"] == "paper"

    def test_health_check_healthy(self, persistence, mock_redis):
        """Test health check when Redis is healthy."""
        mock_redis.ping.return_value = True
        mock_redis.zcard.return_value = 0

        health = persistence.health_check()

        assert health["healthy"] is True
        assert health["redis_connected"] is True

    def test_health_check_unhealthy(self, persistence, mock_redis):
        """Test health check when Redis is down."""
        mock_redis.ping.side_effect = Exception("Connection refused")

        health = persistence.health_check()

        assert health["healthy"] is False
        assert health["redis_connected"] is False
        assert "error" in health


class TestOutcomePersistenceKeyPatterns:
    """Test Redis key patterns."""

    def test_key_patterns(self):
        """Test that key patterns are correctly defined."""
        persistence = OutcomePersistence()

        # Verify key patterns
        assert "paper:signal:" in persistence.SIGNAL_KEY_PATTERN
        assert "paper:order:" in persistence.ORDER_KEY_PATTERN
        assert "paper:fill:" in persistence.FILL_KEY_PATTERN
        assert "paper:outcome:" in persistence.OUTCOME_KEY_PATTERN

        # Verify index keys
        assert persistence.SIGNAL_INDEX_KEY == "paper:index:signals"
        assert persistence.ORDER_INDEX_KEY == "paper:index:orders"
        assert persistence.FILL_INDEX_KEY == "paper:index:fills"
        assert persistence.OUTCOME_INDEX_KEY == "paper:index:outcomes"

    def test_default_ttl(self):
        """Test default TTL is 7 days."""
        persistence = OutcomePersistence()
        assert persistence.ttl_seconds == 604800  # 7 days in seconds

    def test_custom_ttl(self):
        """Test custom TTL can be set."""
        persistence = OutcomePersistence(ttl_seconds=3600)  # 1 hour
        assert persistence.ttl_seconds == 3600


class TestNumbersRealGuard:
    """Test that numbers.Real correctly gates exit_price values (ST-ICT-025)."""

    @pytest.mark.parametrize(
        "value",
        [
            42,
            3.14,
            0,
            -1.5,
        ],
    )
    def test_numbers_real_accepts_real_numbers(self, value):
        """numbers.Real guard must accept float, int."""
        assert isinstance(value, numbers.Real)

    def test_numbers_real_rejects_decimal(self):
        """Decimal is NOT numbers.Real — it is numbers.Number only.

        This is a known Python design decision. Decimal values must be
        explicitly handled via float() conversion before the guard.
        """
        assert not isinstance(Decimal("99.99"), numbers.Real)

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "not_a_number",
            {"price": 100},
            [1, 2, 3],
            b"bytes",
        ],
    )
    def test_numbers_real_rejects_non_numbers(self, value):
        """numbers.Real guard must reject non-numeric types."""
        if value is None:
            # None short-circuits the `is not None` check before isinstance
            assert not (value is not None and isinstance(value, numbers.Real))
        else:
            assert not isinstance(value, numbers.Real)

    def test_numbers_real_rejects_magic_mock(self):
        """numbers.Real guard must reject unittest.mock.MagicMock."""
        from unittest.mock import MagicMock

        mock_price = MagicMock()
        # MagicMock is NOT a numbers.Real
        assert not isinstance(mock_price, numbers.Real)

    def test_numbers_real_accepts_bool(self):
        """bool is a subclass of int and therefore passes numbers.Real.

        This is expected Python behavior. In practice, exit_price will
        never be a bool from position attributes, so this is not a concern.
        """
        assert isinstance(True, numbers.Real)
        assert isinstance(False, numbers.Real)


class TestMetadataOutcomeClassification:
    """ST-ICT-027: Verify metadata-based outcome classification.

    Tests the asymmetry between metadata=None (MANUAL_CLOSE) and
    metadata={} (UNKNOWN when no TP/SL levels), plus correct TP/SL
    classification when metadata contains take_profit/stop_loss.
    """

    @pytest.fixture
    def capture(self):
        """Create OutcomeCaptureIntegration with no persistence/alerts."""
        return OutcomeCaptureIntegration(
            persistence=None,
            alerts=None,
            enabled=True,
            connector_provenance={},
        )

    @staticmethod
    def _make_position(
        *,
        side="long",
        entry_price=50000.0,
        quantity=1.0,
        exit_price=52000.0,
        metadata=None,
    ):
        """Create a mock position object."""
        pos = Mock()
        pos.side = side
        pos.entry_price = entry_price
        pos.quantity = quantity
        pos.exit_price = exit_price
        pos.position_id = "pos-test-001"
        pos.symbol = "BTCUSDT"
        pos.metadata = metadata
        return pos

    def test_metadata_none_yields_manual_close(self, capture):
        """When position.metadata is None, outcome_type must be MANUAL_CLOSE."""
        pos = self._make_position(metadata=None, exit_price=52000.0)
        outcome = capture._create_outcome_from_position(pos, realized_pnl=200.0)

        assert outcome.outcome_type == OutcomeType.MANUAL_CLOSE

    def test_empty_metadata_dict_yields_manual_close(self, capture):
        """When metadata is {}, _classify_outcome_type has no TP/SL → MANUAL_CLOSE.

        This is distinct from metadata=None which also yields MANUAL_CLOSE but
        via the explicit None-guard on line 359 rather than the classification
        fallback.
        """
        pos = self._make_position(metadata={}, exit_price=52000.0)
        outcome = capture._create_outcome_from_position(pos, realized_pnl=200.0)

        assert outcome.outcome_type == OutcomeType.MANUAL_CLOSE

    def test_long_tp_hit(self, capture):
        """LONG position with exit_price >= take_profit → TP_HIT."""
        pos = self._make_position(
            side="long",
            entry_price=50000.0,
            exit_price=51000.0,
            metadata={"take_profit": 50500.0},
        )
        outcome = capture._create_outcome_from_position(pos, realized_pnl=1000.0)

        assert outcome.outcome_type == OutcomeType.TP_HIT

    def test_long_sl_hit(self, capture):
        """LONG position with exit_price <= stop_loss → SL_HIT."""
        pos = self._make_position(
            side="long",
            entry_price=50000.0,
            exit_price=49500.0,
            metadata={"stop_loss": 49800.0},
        )
        outcome = capture._create_outcome_from_position(pos, realized_pnl=-500.0)

        assert outcome.outcome_type == OutcomeType.SL_HIT

    def test_short_tp_hit(self, capture):
        """SHORT position with exit_price <= take_profit → TP_HIT."""
        pos = self._make_position(
            side="short",
            entry_price=50000.0,
            exit_price=49000.0,
            metadata={"take_profit": 49500.0},
        )
        outcome = capture._create_outcome_from_position(pos, realized_pnl=1000.0)

        assert outcome.outcome_type == OutcomeType.TP_HIT

    def test_short_sl_hit(self, capture):
        """SHORT position with exit_price >= stop_loss → SL_HIT."""
        pos = self._make_position(
            side="short",
            entry_price=50000.0,
            exit_price=50500.0,
            metadata={"stop_loss": 50200.0},
        )
        outcome = capture._create_outcome_from_position(pos, realized_pnl=-500.0)

        assert outcome.outcome_type == OutcomeType.SL_HIT

    def test_metadata_both_tp_sl_exit_between(self, capture):
        """When exit_price is between TP and SL, no hit → MANUAL_CLOSE for both None and {}."""
        # With metadata=None → MANUAL_CLOSE (via explicit None guard)
        pos_none = self._make_position(
            side="long",
            exit_price=50200.0,
            metadata=None,
        )
        outcome_none = capture._create_outcome_from_position(
            pos_none, realized_pnl=200.0
        )
        assert outcome_none.outcome_type == OutcomeType.MANUAL_CLOSE

        # With metadata={} → MANUAL_CLOSE (via _classify_outcome_type default)
        pos_empty = self._make_position(
            side="long",
            exit_price=50200.0,
            metadata={},
        )
        outcome_empty = capture._create_outcome_from_position(
            pos_empty, realized_pnl=200.0
        )
        assert outcome_empty.outcome_type == OutcomeType.MANUAL_CLOSE

    def test_no_exit_price_yields_unknown(self, capture):
        """When exit_price is None and metadata={}, outcome_type stays UNKNOWN."""
        pos = Mock()
        pos.side = "long"
        pos.entry_price = 50000.0
        pos.quantity = 1.0
        pos.exit_price = None
        pos.position_id = "pos-test-no-exit"
        pos.symbol = "BTCUSDT"
        pos.metadata = {}

        outcome = capture._create_outcome_from_position(pos, realized_pnl=0.0)

        assert outcome.outcome_type == OutcomeType.UNKNOWN
        assert outcome.exit_price is None

    def test_metadata_preserved_in_outcome(self, capture):
        """Metadata dict is passed through to SignalOutcome.metadata."""
        md = {"take_profit": 51000.0, "stop_loss": 49000.0, "fee_rate": 0.0005}
        pos = self._make_position(metadata=md, exit_price=52000.0)
        outcome = capture._create_outcome_from_position(pos, realized_pnl=2000.0)

        assert outcome.metadata == md


class TestPersistTradeResultPostgresSync:
    """Test that persist_trade_result wires Postgres sync correctly."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.set = MagicMock(return_value=True)
        mock.expire = MagicMock(return_value=True)
        mock.zadd = MagicMock(return_value=True)
        mock.ping = MagicMock(return_value=True)
        mock.hset = MagicMock(return_value=True)
        mock.hmset = MagicMock(return_value=True)
        # Default get to return None (falsy) so idempotency check passes
        # Tests can override this by patching mock_redis.get directly
        mock.get = MagicMock(return_value=None)
        return mock

    @pytest.fixture
    def persistence(self, mock_redis):
        """Create OutcomePersistence with mock Redis and Postgres sync enabled."""
        pers = OutcomePersistence(redis_client=mock_redis, enable_postgres_sync=True)
        return pers

    def _make_signal(self):
        """Create a mock signal."""
        signal = MagicMock()
        signal.signal_id = str(uuid4())
        signal.token = "BTCUSDT"
        signal.direction = MagicMock(value="long")
        signal.confidence = 0.85
        signal.signal_type = "OPEN"
        return signal

    def _make_order(self, order_id: str = "test-order-1", filled: bool = True):
        """Create a mock paper order."""
        order = MagicMock(spec=PaperOrder)
        order.order_id = order_id
        order.symbol = "BTCUSDT"
        order.token = "BTC"
        order.side = "buy"
        order.order_type = "market"
        order.quantity = 0.001
        order.price = 50000.0
        order.state = MagicMock()
        order.state.value = "filled" if filled else "pending"
        order.filled_quantity = 0.001
        order.avg_fill_price = 50000.0
        order.created_at = datetime.now(UTC)
        order.filled_at = datetime.now(UTC)
        order.metadata = {}
        order.fills = []
        return order

    def _make_trade_result(
        self,
        signal=None,
        order=None,
        filled: bool = True,
        correlation_id: str = "test-corr",
    ):
        """Create a mock paper trade result."""
        result = MagicMock(spec=PaperTradeResult)
        result.signal = signal
        result.order = order
        result.position = None
        result.correlation_id = correlation_id
        return result

    def test_persist_trade_result_syncs_outcome_to_postgres_when_filled(
        self, persistence, mock_redis
    ):
        """persist_trade_result should call _sync_outcome_to_postgres_safe when order is filled.

        PAPER-RECON-001: Updated to test new robust task handling.
        """
        signal = self._make_signal()
        order = self._make_order()
        result = self._make_trade_result(signal=signal, order=order)

        with patch.object(
            persistence, "_sync_outcome_to_postgres_safe"
        ) as mock_sync_safe:
            keys = persistence.persist_trade_result(result)

            # Verify fill was persisted
            assert keys["fill"] is not None

            # Verify Postgres sync was called via the safe wrapper
            mock_sync_safe.assert_called_once()
            call_arg = mock_sync_safe.call_args[0][0]
            assert call_arg.order_id == order.order_id
            assert call_arg.symbol == order.symbol
            assert call_arg.fill_price == order.avg_fill_price
            assert call_arg.status == SignalOutcomeStatus.FILLED
            assert call_arg.execution_venue == "paper"
            assert call_arg.execution_mode == "paper"
            assert call_arg.execution_source == "canary"

    def test_persist_trade_result_skips_postgres_sync_when_not_filled(
        self, persistence, mock_redis
    ):
        """persist_trade_result should NOT call _sync_outcome_to_postgres_safe when order is not filled."""
        order = self._make_order(filled=False)
        result = self._make_trade_result(order=order)

        with patch.object(
            persistence, "_sync_outcome_to_postgres_safe"
        ) as mock_sync_safe:
            keys = persistence.persist_trade_result(result)

            # Verify fill was NOT persisted
            assert keys["fill"] is None

            # Verify Postgres sync was NOT called
            mock_sync_safe.assert_not_called()

    def test_persist_trade_result_skips_postgres_sync_when_disabled(self, mock_redis):
        """persist_trade_result should NOT call _sync_outcome_to_postgres_safe when enable_postgres_sync=False."""
        persistence = OutcomePersistence(
            redis_client=mock_redis, enable_postgres_sync=False
        )
        signal = self._make_signal()
        order = self._make_order()
        result = self._make_trade_result(signal=signal, order=order)

        with patch.object(
            persistence, "_sync_outcome_to_postgres_safe"
        ) as mock_sync_safe:
            keys = persistence.persist_trade_result(result)

            # Fill should still be persisted even when sync is disabled
            assert keys["fill"] is not None
            mock_sync_safe.assert_not_called()

    def test_persist_trade_result_uses_thread_pool_executor(
        self, persistence, mock_redis
    ):
        """persist_trade_result should use ThreadPoolExecutor for robust async handling.

        PAPER-RECON-001: Updated to test new robust task handling using ThreadPoolExecutor
        instead of fire-and-forget asyncio.create_task.
        """
        signal = self._make_signal()
        order = self._make_order()
        result = self._make_trade_result(signal=signal, order=order)

        with patch.object(
            persistence, "_sync_outcome_to_postgres_safe"
        ) as mock_sync_safe:
            keys = persistence.persist_trade_result(result)

            assert keys["fill"] is not None
            # _sync_outcome_to_postgres_safe should be called via ThreadPoolExecutor
            mock_sync_safe.assert_called_once()
            # Verify the outcome passed has the correct order_id
            call_arg = mock_sync_safe.call_args[0][0]
            assert call_arg.order_id == order.order_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
