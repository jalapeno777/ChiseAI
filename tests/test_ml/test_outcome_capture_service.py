"""Tests for Outcome Capture Service.

Tests the Bybit fill listener, outcome capture service, and signal outcome models.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# Import the modules under test
from ml.feedback.bybit_fill_listener import (
    BybitFillListener,
    BybitListenerConfig,
)
from ml.feedback.outcome_capture_service import (
    CaptureMetrics,
    OutcomeCaptureConfig,
    OutcomeCaptureService,
)
from ml.models.signal_outcome import (
    BybitFillEvent,
    OutcomeType,
    SignalOutcome,
    SignalOutcomeStatus,
)


class TestSignalOutcome:
    """Tests for SignalOutcome model."""

    def test_default_creation(self):
        """Test creating SignalOutcome with defaults."""
        outcome = SignalOutcome()

        assert isinstance(outcome.outcome_id, UUID)
        assert outcome.order_id == ""
        assert outcome.symbol == ""
        assert outcome.fill_price == Decimal("0")
        assert outcome.fill_quantity == Decimal("0")
        assert outcome.status == SignalOutcomeStatus.PENDING

    def test_full_creation(self):
        """Test creating SignalOutcome with all fields."""
        signal_id = uuid4()
        fill_time = datetime(2026, 2, 21, 12, 0, 0, tzinfo=UTC)

        outcome = SignalOutcome(
            signal_id=signal_id,
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            fill_price=Decimal("50000.50"),
            fill_quantity=Decimal("0.1"),
            fill_timestamp=fill_time,
            outcome_type=OutcomeType.TP_HIT,
            pnl=Decimal("100.50"),
            fee=Decimal("0.50"),
            status=SignalOutcomeStatus.FILLED,
        )

        assert outcome.signal_id == signal_id
        assert outcome.order_id == "test-order-123"
        assert outcome.symbol == "BTCUSDT"
        assert outcome.side == "Buy"
        assert outcome.fill_price == Decimal("50000.50")
        assert outcome.fill_quantity == Decimal("0.1")
        assert outcome.fill_value == Decimal("5000.050")
        assert outcome.outcome_type == OutcomeType.TP_HIT
        assert outcome.pnl == Decimal("100.50")
        assert outcome.fee == Decimal("0.50")
        assert outcome.is_filled is True
        assert outcome.has_signal_match is True

    def test_side_normalization(self):
        """Test side is normalized to Title Case."""
        outcome = SignalOutcome(side="buy")
        assert outcome.side == "Buy"

        outcome = SignalOutcome(side="SELL")
        assert outcome.side == "Sell"

    def test_string_uuid_conversion(self):
        """Test UUID conversion from string."""
        uuid_str = "12345678-1234-1234-1234-123456789abc"
        outcome = SignalOutcome(
            outcome_id=uuid_str,
            signal_id=uuid_str,
        )
        assert outcome.outcome_id == UUID(uuid_str)
        assert outcome.signal_id == UUID(uuid_str)

    def test_decimal_conversion(self):
        """Test Decimal conversion from various types."""
        outcome = SignalOutcome(
            fill_price=50000.50,  # float
            fill_quantity="0.1",  # string
            pnl=100,  # int
        )
        assert isinstance(outcome.fill_price, Decimal)
        assert isinstance(outcome.fill_quantity, Decimal)
        assert isinstance(outcome.pnl, Decimal)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        outcome = SignalOutcome(
            order_id="test-123",
            symbol="BTCUSDT",
            fill_price=Decimal("50000"),
        )
        data = outcome.to_dict()

        assert data["order_id"] == "test-123"
        assert data["symbol"] == "BTCUSDT"
        assert data["fill_price"] == "50000"
        assert isinstance(data["outcome_id"], str)

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "outcome_id": str(uuid4()),
            "signal_id": str(uuid4()),
            "order_id": "test-123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "fill_price": "50000",
            "fill_quantity": "0.1",
            "fill_timestamp": "2026-02-21T12:00:00+00:00",
            "outcome_type": "tp_hit",
            "status": "filled",
        }

        outcome = SignalOutcome.from_dict(data)

        assert outcome.order_id == "test-123"
        assert outcome.symbol == "BTCUSDT"
        assert outcome.outcome_type == OutcomeType.TP_HIT
        assert outcome.status == SignalOutcomeStatus.FILLED

    def test_to_db_dict(self):
        """Test conversion to database dictionary."""
        outcome = SignalOutcome(
            order_id="test-123",
            fill_price=Decimal("50000.50"),
            fill_quantity=Decimal("0.1"),
        )
        db_dict = outcome.to_db_dict()

        assert db_dict["order_id"] == "test-123"
        assert db_dict["fill_price"] == 50000.50
        assert db_dict["fill_quantity"] == 0.1
        assert isinstance(db_dict["fill_timestamp"], datetime)


class TestBybitFillEvent:
    """Tests for BybitFillEvent model."""

    def test_from_websocket_data(self):
        """Test parsing WebSocket data."""
        ws_data = {
            "orderId": "test-order-123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "price": "50000.50",
            "qty": "0.1",
            "execTime": "1708536000000",
            "execType": "Trade",
            "fee": "0.50",
            "feeRate": "0.0001",
        }

        event = BybitFillEvent.from_websocket_data(ws_data)

        assert event.order_id == "test-order-123"
        assert event.symbol == "BTCUSDT"
        assert event.side == "Buy"
        assert event.price == Decimal("50000.50")
        assert event.qty == Decimal("0.1")
        assert event.exec_time == 1708536000000
        assert event.fee == Decimal("0.50")
        assert event.fee_rate == Decimal("0.0001")

    def test_to_signal_outcome(self):
        """Test conversion to SignalOutcome."""
        event = BybitFillEvent(
            order_id="test-123",
            symbol="BTCUSDT",
            side="Buy",
            price=Decimal("50000"),
            qty=Decimal("0.1"),
            exec_time=1708536000000,
            fee=Decimal("0.50"),
        )

        outcome = event.to_signal_outcome()

        assert outcome.order_id == "test-123"
        assert outcome.symbol == "BTCUSDT"
        assert outcome.fill_price == Decimal("50000")
        assert outcome.fill_quantity == Decimal("0.1")
        assert outcome.fee == Decimal("0.50")
        assert outcome.status == SignalOutcomeStatus.FILLED


class TestBybitFillListener:
    """Tests for BybitFillListener."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return BybitListenerConfig(
            api_key="test_key",
            api_secret="test_secret",
            ws_url="wss://stream-demo.bybit.com/v5/private",
        )

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.exists.return_value = False
        return redis

    @pytest.mark.asyncio
    async def test_initialization(self, config):
        """Test listener initialization."""
        listener = BybitFillListener(config)

        assert listener.config == config
        assert listener.state.is_connected is False
        assert listener._running is False

    @pytest.mark.asyncio
    async def test_start_stop(self, config):
        """Test starting and stopping listener."""
        listener = BybitFillListener(config)

        # Mock the WebSocket connection
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.recv.return_value = '{"success": true, "ret_msg": "OK"}'
            mock_connect.return_value.__aenter__.return_value = mock_ws

            # Start should work (though it won't connect without real WS)
            await listener.start()
            assert listener._running is True

            # Stop should clean up
            await listener.stop()
            assert listener._running is False

    @pytest.mark.asyncio
    async def test_is_healthy(self, config):
        """Test health check."""
        listener = BybitFillListener(config)

        # Not connected
        assert listener.is_healthy() is False

        # Connected with recent message
        listener.state.is_connected = True
        listener.state.last_message = time.time()
        assert listener.is_healthy() is True

        # Connected but stale
        listener.state.last_message = time.time() - 100  # 100 seconds ago
        assert listener.is_healthy() is False

    @pytest.mark.asyncio
    async def test_on_fill_callback(self, config):
        """Test fill callback registration and triggering."""
        listener = BybitFillListener(config)
        callback_mock = MagicMock()

        listener.on_fill(callback_mock)

        # Create a test outcome
        outcome = SignalOutcome(order_id="test-123")

        # Simulate callback invocation
        for cb in listener._fill_callbacks:
            cb(outcome)

        callback_mock.assert_called_once_with(outcome)

    @pytest.mark.asyncio
    async def test_deduplication_with_redis(self, config, mock_redis):
        """Test deduplication using Redis."""
        listener = BybitFillListener(config, redis_client=mock_redis)

        # First check should not be duplicate
        is_dup = await listener._is_duplicate("order-123")
        assert is_dup is False

        # Mark as processed
        await listener._mark_processed("order-123")

        # Now should be duplicate
        mock_redis.exists.return_value = True
        is_dup = await listener._is_duplicate("order-123")
        assert is_dup is True


class TestOutcomeCaptureService:
    """Tests for OutcomeCaptureService."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return OutcomeCaptureConfig(
            batch_size=10,
            flush_interval_seconds=1,
            enable_signal_matching=True,
        )

    @pytest.fixture
    def mock_db_pool(self):
        """Create mock database pool."""
        pool = AsyncMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        return pool

    @pytest.fixture
    def mock_signal_tracker(self):
        """Create mock signal tracker."""
        tracker = AsyncMock()
        tracker.get_signal_history.return_value = []
        return tracker

    @pytest.mark.asyncio
    async def test_initialization(self, config):
        """Test service initialization."""
        service = OutcomeCaptureService(config=config)

        assert service.config == config
        assert service._running is False
        assert len(service._pending_outcomes) == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, config, mock_db_pool):
        """Test starting and stopping service."""
        service = OutcomeCaptureService(
            config=config,
            db_pool=mock_db_pool,
        )

        with patch.object(service, "_listener", None):
            # Can't fully test without mocking WebSocket
            # Just verify state management
            service._running = True
            assert service.get_status()["running"] is True

            service._running = False
            assert service.get_status()["running"] is False

    @pytest.mark.asyncio
    async def test_process_outcome_no_matching(self, config):
        """Test processing outcome without signal matching."""
        service = OutcomeCaptureService(
            config=config,
            db_pool=None,  # Skip DB storage for this test
        )

        outcome = SignalOutcome(
            order_id="test-123",
            symbol="BTCUSDT",
            fill_price=Decimal("50000"),
        )

        result = await service.process_outcome(outcome, match_to_signal=False)

        assert result.matched is False
        assert result.match_method == "skipped"
        # Metrics are updated even if DB is not available (the outcome was "processed")
        assert service.metrics.outcomes_stored == 1

    @pytest.mark.asyncio
    async def test_match_confidence_calculation(self, config):
        """Test match confidence calculation."""
        service = OutcomeCaptureService(config=config)

        # Create mock signal
        mock_signal = MagicMock()
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=30)).timestamp() * 1000
        )

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        confidence = service._calculate_match_confidence(outcome, mock_signal)

        # Should have high confidence (symbol match + direction match + time proximity)
        assert confidence > 0.5
        assert confidence <= 1.0

    @pytest.mark.asyncio
    async def test_capture_metrics(self):
        """Test capture metrics."""
        metrics = CaptureMetrics()

        # Record some latencies
        metrics.record_latency(0.1)
        metrics.record_latency(0.2)
        metrics.record_latency(0.3)

        assert (
            abs(metrics.avg_latency_seconds - 0.2) < 0.001
        )  # Floating point comparison

        # Update counters
        metrics.fills_received = 10
        metrics.outcomes_stored = 8
        metrics.signals_matched = 5

        data = metrics.to_dict()
        assert data["fills_received"] == 10
        assert data["outcomes_stored"] == 8
        assert data["signals_matched"] == 5
        assert data["avg_latency_seconds"] == 0.2


class TestIntegration:
    """Integration-style tests."""

    @pytest.mark.asyncio
    async def test_full_flow_no_db(self):
        """Test full flow without database."""
        # Create service with no database (for unit testing)
        config = OutcomeCaptureConfig(
            enable_signal_matching=False,
            batch_size=5,
        )
        service = OutcomeCaptureService(config=config)

        # Process some outcomes
        for i in range(3):
            outcome = SignalOutcome(
                order_id=f"order-{i}",
                symbol="BTCUSDT",
                fill_price=Decimal("50000"),
                fill_quantity=Decimal("0.1"),
            )
            result = await service.process_outcome(outcome, match_to_signal=False)
            assert result.outcome.order_id == f"order-{i}"

        # Check metrics
        assert service.metrics.fills_received == 0  # Not via listener
        assert service.metrics.outcomes_stored == 3

    def test_outcome_enum_values(self):
        """Test outcome type enum values."""
        assert OutcomeType.TP_HIT.value == "tp_hit"
        assert OutcomeType.SL_HIT.value == "sl_hit"
        assert OutcomeType.MANUAL_CLOSE.value == "manual_close"
        assert OutcomeType.EXPIRED.value == "expired"

    def test_status_enum_values(self):
        """Test status enum values."""
        assert SignalOutcomeStatus.PENDING.value == "pending"
        assert SignalOutcomeStatus.FILLED.value == "filled"
        assert SignalOutcomeStatus.MATCHED.value == "matched"
        assert SignalOutcomeStatus.ERROR.value == "error"
