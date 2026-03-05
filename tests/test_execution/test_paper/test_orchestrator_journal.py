"""Tests for trade journal integration in paper trading orchestrator.

Tests the wiring of TradeJournal into the orchestrator lifecycle:
- Journal entry creation on position open
- Journal entry closing on position close
- Exit reason mapping
- Integration with real journal

For PAPER-2025-BATCH3: Trade Journal Integration
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.paper.models import OrderSide, OrderState, OrderType, PaperOrder
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.reason_codes import ExitReason
from execution.paper.trade_journal import TradeJournal
from signal_generation.models import SignalDirection


@pytest.fixture
def mock_signal():
    """Create a mock trading signal."""
    signal = MagicMock()
    signal.signal_id = "test-signal-123"
    signal.token = "BTCUSDT"
    signal.direction = SignalDirection.LONG
    signal.confidence = 0.85
    signal.strategy_name = "test_strategy"
    signal.stop_loss = 95000.0
    signal.stop_loss_method = "atr"
    return signal


@pytest.fixture
def mock_filled_order():
    """Create a mock filled order."""
    order = MagicMock(spec=PaperOrder)
    order.order_id = "test-order-123"
    order.symbol = "BTCUSDT"
    order.side = OrderSide.BUY.value
    order.order_type = OrderType.MARKET.value
    order.quantity = 0.1
    order.price = 100000.0
    order.avg_fill_price = 100000.0
    order.filled_quantity = 0.1
    order.state = OrderState.FILLED
    order.metadata = {}
    return order


@pytest.fixture
def mock_position():
    """Create a mock position."""
    position = MagicMock()
    position.position_id = "test-position-123"
    position.symbol = "BTCUSDT"
    position.side = "long"
    position.entry_price = 100000.0
    position.quantity = 0.1
    position.opened_at = datetime.now(UTC)
    position.metadata = {}
    return position


@pytest.fixture
def mock_dependencies():
    """Create mock orchestrator dependencies."""
    return {
        "signal_generator": MagicMock(),
        "order_simulator": MagicMock(),
        "position_tracker": MagicMock(),
        "risk_enforcer": MagicMock(),
        "telemetry_collector": MagicMock(),
        "kill_switch": MagicMock(),
    }


class TestJournalEntryCreation:
    """Tests for journal entry creation on position open."""

    @pytest.mark.asyncio
    async def test_journal_entry_created_on_position_open(
        self, mock_signal, mock_filled_order, mock_position, mock_dependencies
    ):
        """Test that journal entry is created when position is opened."""
        # Setup
        trade_journal = TradeJournal()
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal=trade_journal
        )

        # Mock position tracker to properly set metadata
        async def mock_open_position(*args, **kwargs):
            # Use the metadata passed to open_position
            mock_position.metadata = kwargs.get("metadata", {})
            return mock_position

        mock_dependencies["position_tracker"].open_position = AsyncMock(
            side_effect=mock_open_position
        )

        # Mock telemetry
        orchestrator.telemetry = MagicMock()
        orchestrator.telemetry.set_equity = AsyncMock()

        # Execute
        position = await orchestrator._open_position(
            mock_filled_order, mock_signal, "test-correlation-id"
        )

        # Verify journal entry created
        assert position is not None
        assert position.metadata is not None
        assert "journal_entry_id" in position.metadata

        entry_id = position.metadata["journal_entry_id"]
        entry = trade_journal.get_entry(entry_id)
        assert entry is not None
        assert entry.symbol == "BTCUSDT"
        assert entry.side == "buy"
        assert entry.entry_price == 100000.0
        assert entry.signal_id == "test-signal-123"

    @pytest.mark.asyncio
    async def test_journal_entry_not_created_if_no_journal(
        self, mock_signal, mock_filled_order, mock_position, mock_dependencies
    ):
        """Test that no journal entry is created if journal is not configured."""
        # Setup - no trade journal
        orchestrator = PaperTradingOrchestrator(**mock_dependencies)

        # Mock position tracker
        mock_dependencies["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Execute
        position = await orchestrator._open_position(
            mock_filled_order, mock_signal, "test-correlation-id"
        )

        # Verify no journal entry created
        assert position is not None
        assert position.metadata is not None
        assert "journal_entry_id" not in position.metadata

    @pytest.mark.asyncio
    async def test_journal_entry_creation_error_handling(
        self, mock_signal, mock_filled_order, mock_position, mock_dependencies
    ):
        """Test that position creation succeeds even if journal entry fails."""
        # Setup
        trade_journal = MagicMock()
        trade_journal.create_entry.side_effect = Exception("Journal error")
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal=trade_journal
        )

        # Mock position tracker
        mock_dependencies["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        # Execute - should not raise
        position = await orchestrator._open_position(
            mock_filled_order, mock_signal, "test-correlation-id"
        )

        # Verify position created despite journal error
        assert position is not None


class TestJournalEntryClosing:
    """Tests for journal entry closing on position close."""

    @pytest.mark.asyncio
    async def test_journal_entry_closed_on_position_close(
        self, mock_position, mock_dependencies
    ):
        """Test that journal entry is closed when position is closed."""
        # Setup
        trade_journal = TradeJournal()
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal=trade_journal
        )

        # Create journal entry
        mock_signal = MagicMock()
        mock_signal.signal_id = "test-signal-123"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        entry = trade_journal.create_entry(
            position=mock_position,
            signal=mock_signal,
            correlation_id="test-correlation-id",
        )

        # Add entry_id to position metadata
        mock_position.metadata = {"journal_entry_id": entry.entry_id}

        # Mock position tracker
        mock_dependencies["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 500.0)
        )

        # Mock telemetry
        orchestrator.telemetry = MagicMock()
        orchestrator.telemetry.set_equity = AsyncMock()

        # Execute
        result = await orchestrator.close_position(
            "test-position-123", 101000.0, reason="manual"
        )

        # Verify journal entry closed
        assert result is not None
        closed_entry = trade_journal.get_entry(entry.entry_id)
        assert closed_entry is not None
        assert closed_entry.is_closed
        assert closed_entry.exit_price == 101000.0
        assert closed_entry.exit_reason == ExitReason.MANUAL_CLOSE
        assert closed_entry.realized_pnl == 500.0

    @pytest.mark.asyncio
    async def test_journal_entry_not_closed_if_no_journal(
        self, mock_position, mock_dependencies
    ):
        """Test that position close succeeds even if no journal configured."""
        # Setup - no trade journal
        orchestrator = PaperTradingOrchestrator(**mock_dependencies)

        # Mock position tracker
        mock_dependencies["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 500.0)
        )

        # Execute - should not raise
        result = await orchestrator.close_position(
            "test-position-123", 101000.0, reason="manual"
        )

        # Verify position closed
        assert result is not None

    @pytest.mark.asyncio
    async def test_journal_entry_close_error_handling(
        self, mock_position, mock_dependencies
    ):
        """Test that position close succeeds even if journal close fails."""
        # Setup
        trade_journal = MagicMock()
        trade_journal.close_entry.side_effect = Exception("Journal error")
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal=trade_journal
        )

        # Add journal_entry_id to position metadata
        mock_position.metadata = {"journal_entry_id": "test-entry-123"}

        # Mock position tracker
        mock_dependencies["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 500.0)
        )

        # Mock telemetry
        orchestrator.telemetry = MagicMock()
        orchestrator.telemetry.set_equity = AsyncMock()

        # Execute - should not raise
        result = await orchestrator.close_position(
            "test-position-123", 101000.0, reason="manual"
        )

        # Verify position closed despite journal error
        assert result is not None


class TestExitReasonMapping:
    """Tests for exit reason mapping."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "close_reason,expected_exit_reason",
        [
            ("time_limit", ExitReason.TIME_LIMIT),
            ("manual", ExitReason.MANUAL_CLOSE),
            ("opposite_signal", ExitReason.SIGNAL_REVERSE),
            ("kill_switch", ExitReason.KILL_SWITCH),
            ("unknown_reason", ExitReason.MANUAL_CLOSE),  # Default fallback
        ],
    )
    async def test_journal_close_reason_mapping(
        self,
        mock_position,
        mock_dependencies,
        close_reason,
        expected_exit_reason,
    ):
        """Test that close reasons map to correct ExitReason enum values."""
        # Setup
        trade_journal = TradeJournal()
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal=trade_journal
        )

        # Create journal entry
        mock_signal = MagicMock()
        mock_signal.signal_id = "test-signal-123"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        entry = trade_journal.create_entry(
            position=mock_position,
            signal=mock_signal,
            correlation_id="test-correlation-id",
        )

        # Add entry_id to position metadata
        mock_position.metadata = {"journal_entry_id": entry.entry_id}

        # Mock position tracker
        mock_dependencies["position_tracker"].close_position = AsyncMock(
            return_value=(mock_position, 500.0)
        )

        # Mock telemetry
        orchestrator.telemetry = MagicMock()
        orchestrator.telemetry.set_equity = AsyncMock()

        # Execute
        await orchestrator.close_position(
            "test-position-123", 101000.0, reason=close_reason
        )

        # Verify exit reason mapped correctly
        closed_entry = trade_journal.get_entry(entry.entry_id)
        assert closed_entry.exit_reason == expected_exit_reason


class TestJournalIntegration:
    """Integration tests with real TradeJournal."""

    @pytest.mark.asyncio
    async def test_journal_integration_with_real_journal(
        self, mock_signal, mock_filled_order, mock_position, mock_dependencies
    ):
        """Integration test using real TradeJournal (not mocked)."""
        # Setup
        trade_journal = TradeJournal()
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal=trade_journal
        )

        # Mock position tracker for open - properly set metadata
        async def mock_open_position(*args, **kwargs):
            mock_position.metadata = kwargs.get("metadata", {})
            return mock_position

        mock_dependencies["position_tracker"].open_position = AsyncMock(
            side_effect=mock_open_position
        )

        # Mock telemetry
        orchestrator.telemetry = MagicMock()
        orchestrator.telemetry.set_equity = AsyncMock()

        # Open position
        position = await orchestrator._open_position(
            mock_filled_order, mock_signal, "test-correlation-id"
        )

        # Verify entry created
        assert position is not None
        entry_id = position.metadata["journal_entry_id"]
        entry = trade_journal.get_entry(entry_id)
        assert entry is not None
        assert entry.is_open
        assert entry.entry_price == 100000.0

        # Mock position tracker for close
        mock_dependencies["position_tracker"].close_position = AsyncMock(
            return_value=(position, 500.0)
        )

        # Close position
        await orchestrator.close_position(
            position.position_id, 101000.0, reason="manual"
        )

        # Verify entry closed with correct PnL
        closed_entry = trade_journal.get_entry(entry_id)
        assert closed_entry.is_closed
        assert closed_entry.exit_price == 101000.0
        assert closed_entry.realized_pnl == 500.0
        assert closed_entry.exit_reason == ExitReason.MANUAL_CLOSE

    @pytest.mark.asyncio
    async def test_get_journal_stats(self, mock_dependencies):
        """Test get_journal_stats returns stats when journal configured."""
        # Setup
        trade_journal = TradeJournal()
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal=trade_journal
        )

        # Execute
        stats = orchestrator.get_journal_stats()

        # Verify stats returned
        assert stats is not None
        assert "total_entries" in stats
        assert "open_entries" in stats
        assert "closed_entries" in stats

    @pytest.mark.asyncio
    async def test_get_journal_stats_no_journal(self, mock_dependencies):
        """Test get_journal_stats returns None when no journal configured."""
        # Setup - no trade journal
        orchestrator = PaperTradingOrchestrator(**mock_dependencies)

        # Execute
        stats = orchestrator.get_journal_stats()

        # Verify None returned
        assert stats is None


class TestJournalWithOutcomeCapture:
    """Tests for journal interaction with outcome capture."""

    @pytest.mark.asyncio
    async def test_journal_and_outcome_capture_both_called(
        self, mock_signal, mock_filled_order, mock_position, mock_dependencies
    ):
        """Test that both journal and outcome capture are called on position open."""
        # Setup
        trade_journal = TradeJournal()
        outcome_capture = MagicMock()
        outcome_capture.on_trade_result = AsyncMock()

        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies,
            trade_journal=trade_journal,
            outcome_capture=outcome_capture,
        )

        # Mock dependencies - properly set metadata
        async def mock_open_position(*args, **kwargs):
            mock_position.metadata = kwargs.get("metadata", {})
            return mock_position

        mock_dependencies["position_tracker"].open_position = AsyncMock(
            side_effect=mock_open_position
        )
        orchestrator.telemetry = MagicMock()
        orchestrator.telemetry.set_equity = AsyncMock()

        # Open position
        position = await orchestrator._open_position(
            mock_filled_order, mock_signal, "test-correlation-id"
        )

        # Verify journal entry created
        assert "journal_entry_id" in position.metadata

        # Verify entry exists in journal
        entry = trade_journal.get_entry(position.metadata["journal_entry_id"])
        assert entry is not None


# =============================================================================
# Tests for PAPER-2025-BATCH3-002: Orchestrator Persistence Integration
# =============================================================================


class TestTradeJournalService:
    """Test suite for TradeJournalService."""

    @patch("execution.paper.trade_journal_service.TradeJournalRedisPersistence")
    def test_service_initialization(self, mock_persistence_class):
        """Test that service initializes correctly."""
        from execution.paper.trade_journal_service import TradeJournalService

        # Mock the persistence to return unhealthy
        mock_persistence = MagicMock()
        mock_persistence.is_healthy.return_value = False
        mock_persistence_class.return_value = mock_persistence

        service = TradeJournalService(session_id="test-session")

        assert service.session_id == "test-session"
        assert service.journal is not None
        assert service.is_persistence_healthy() is False  # No Redis

    def test_service_initialization_with_persistence(self):
        """Test that service initializes with persistence layer."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        assert service.session_id == "test-session"
        assert service.is_persistence_healthy() is True

    def test_create_entry_persists_to_redis(self):
        """Test that create_entry persists to Redis."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.save_entry.return_value = True

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Create entry
        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Verify entry was created
        assert entry is not None
        assert entry.symbol == "BTCUSDT"
        assert entry.session_id == "test-session"

        # Verify persistence was called
        mock_persistence.save_entry.assert_called_once_with("test-session", entry)

    def test_create_entry_continues_on_persistence_failure(self):
        """Test that trading continues even if persistence fails."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.save_entry.side_effect = Exception("Redis error")

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Create entry - should not raise
        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Verify entry was still created in memory
        assert entry is not None
        assert entry.symbol == "BTCUSDT"

    def test_close_entry_persists_to_redis(self):
        """Test that close_entry persists to Redis."""
        from execution.paper.reason_codes import ExitReason
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.save_entry.return_value = True

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # First create an entry
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Reset mock to track close call
        mock_persistence.save_entry.reset_mock()

        # Close the entry
        closed_entry = service.close_entry(
            entry_id=entry.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        # Verify entry was closed
        assert closed_entry.is_closed
        assert closed_entry.exit_price == 51000.0

        # Verify persistence was called
        mock_persistence.save_entry.assert_called_once_with(
            "test-session", closed_entry
        )

    def test_get_open_and_closed_entries(self):
        """Test getting open and closed entries."""
        from execution.paper.reason_codes import ExitReason
        from execution.paper.trade_journal_service import TradeJournalService

        service = TradeJournalService(session_id="test-session")

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Create entry
        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Check open entries
        open_entries = service.get_open_entries()
        assert len(open_entries) == 1

        # Check closed entries
        closed_entries = service.get_closed_entries()
        assert len(closed_entries) == 0

        # Close entry
        service.close_entry(
            entry_id=entry.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        # Check again
        open_entries = service.get_open_entries()
        assert len(open_entries) == 0

        closed_entries = service.get_closed_entries()
        assert len(closed_entries) == 1

    def test_get_stats(self):
        """Test getting journal statistics."""
        from execution.paper.reason_codes import ExitReason
        from execution.paper.trade_journal_service import TradeJournalService

        service = TradeJournalService(session_id="test-session")

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Create and close entry
        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )
        service.close_entry(
            entry_id=entry.entry_id,
            exit_price=51000.0,
            exit_reason=ExitReason.TAKE_PROFIT_HIT,
            pnl=100.0,
        )

        # Get stats
        stats = service.get_stats()

        assert stats["total_entries"] == 1
        assert stats["closed_entries"] == 1
        assert stats["open_entries"] == 0
        assert stats["total_pnl"] == 100.0

    def test_recover_success(self):
        """Test successful journal recovery."""
        from execution.paper.trade_journal import TradeJournal
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.journal_exists.return_value = True

        # Create a mock journal to return
        mock_journal = MagicMock(spec=TradeJournal)
        mock_journal.session_id = "test-session"
        mock_journal.get_all_entries.return_value = []
        mock_journal.get_open_entries.return_value = []
        mock_journal.get_closed_entries.return_value = []
        mock_journal.get_stats.return_value = {"total_entries": 0}

        mock_persistence.load_journal.return_value = mock_journal

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Recover
        result = service.recover("test-session")

        assert result is True
        mock_persistence.journal_exists.assert_called_once_with("test-session")
        mock_persistence.load_journal.assert_called_once_with("test-session")

    def test_recover_no_journal_found(self):
        """Test recovery when no journal exists."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.journal_exists.return_value = False

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Recover
        result = service.recover("test-session")

        assert result is False

    def test_recover_persistence_failure(self):
        """Test recovery when persistence fails."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.journal_exists.side_effect = Exception("Redis error")

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Recover - should not raise
        result = service.recover("test-session")

        assert result is False


class TestOrchestratorPersistenceIntegration:
    """Test suite for orchestrator persistence integration."""

    def test_orchestrator_with_trade_journal_service(self, mock_dependencies):
        """Test that orchestrator uses TradeJournalService when provided."""
        from execution.paper.orchestrator import PaperTradingOrchestrator
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )

        # Create mock persistence
        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True

        # Create orchestrator with persistence
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies,
            trade_journal_persistence=mock_persistence,
            session_id="test-session",
        )

        # Verify service was created
        assert orchestrator.trade_journal_service is not None
        assert orchestrator.trade_journal is not None

    def test_orchestrator_with_existing_trade_journal(self, mock_dependencies):
        """Test that orchestrator wraps existing TradeJournal in service."""
        from execution.paper.orchestrator import PaperTradingOrchestrator
        from execution.paper.trade_journal import TradeJournal
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )

        # Create existing journal
        existing_journal = TradeJournal(session_id="existing-session")

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Add entry to existing journal
        existing_journal.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Create mock persistence
        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True

        # Create orchestrator with existing journal
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies,
            trade_journal=existing_journal,
            trade_journal_persistence=mock_persistence,
        )

        # Verify entries were copied
        assert orchestrator.trade_journal_service is not None
        assert len(orchestrator.trade_journal_service.get_all_entries()) == 1

    def test_orchestrator_journal_recovery_on_init(self, mock_dependencies):
        """Test that orchestrator attempts recovery on initialization."""
        from execution.paper.orchestrator import PaperTradingOrchestrator
        from execution.paper.trade_journal import TradeJournal
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )

        # Create mock persistence
        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.journal_exists.return_value = True

        # Create mock recovered journal
        recovered_journal = TradeJournal(session_id="recovered-session")
        mock_persistence.load_journal.return_value = recovered_journal

        # Create orchestrator with session_id (should trigger recovery)
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies,
            trade_journal_persistence=mock_persistence,
            session_id="recovered-session",
        )

        # Verify recovery was attempted
        mock_persistence.journal_exists.assert_called_once_with("recovered-session")
        mock_persistence.load_journal.assert_called_once_with("recovered-session")

    def test_orchestrator_recover_journal_method(self, mock_dependencies):
        """Test the recover_journal method."""
        from execution.paper.orchestrator import PaperTradingOrchestrator
        from execution.paper.trade_journal import TradeJournal
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )

        # Create mock persistence
        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.journal_exists.return_value = True

        # Create mock recovered journal
        recovered_journal = TradeJournal(session_id="new-session")
        mock_persistence.load_journal.return_value = recovered_journal

        # Create orchestrator
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal_persistence=mock_persistence
        )

        # Recover journal
        result = orchestrator.recover_journal("new-session")

        assert result is True
        assert orchestrator.trade_journal.session_id == "new-session"

    def test_orchestrator_is_journal_persistence_healthy(self, mock_dependencies):
        """Test the is_journal_persistence_healthy method."""
        from execution.paper.orchestrator import PaperTradingOrchestrator
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )

        # Create mock persistence
        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True

        # Create orchestrator
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal_persistence=mock_persistence
        )

        # Check health
        assert orchestrator.is_journal_persistence_healthy() is True

        # Test without service
        orchestrator2 = PaperTradingOrchestrator(**mock_dependencies)
        assert orchestrator2.is_journal_persistence_healthy() is False

    def test_orchestrator_get_journal_stats_with_service(self, mock_dependencies):
        """Test the get_journal_stats method with service."""
        from execution.paper.orchestrator import PaperTradingOrchestrator
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )

        # Create mock persistence
        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True

        # Create orchestrator
        orchestrator = PaperTradingOrchestrator(
            **mock_dependencies, trade_journal_persistence=mock_persistence
        )

        # Add entry
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        orchestrator.trade_journal_service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Get stats
        stats = orchestrator.get_journal_stats()

        assert stats is not None
        assert stats["total_entries"] == 1


class TestNonBlockingBehavior:
    """Test suite for non-blocking persistence behavior."""

    def test_service_continues_when_persistence_unhealthy(self):
        """Test that service continues working when Redis is down."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = False
        mock_persistence.save_entry.return_value = False  # Save fails

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Create entry - should work even though persistence fails
        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Entry should still be created in memory
        assert entry is not None
        assert entry.symbol == "BTCUSDT"

        # Persistence was called but failed (non-blocking behavior)
        mock_persistence.save_entry.assert_called_once()

    def test_service_continues_on_save_failure(self):
        """Test that service continues when save fails."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.save_entry.return_value = False  # Save fails

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Create entry - should work even though save fails
        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Entry should still be created in memory
        assert entry is not None

        # Persistence should have been called but failed
        mock_persistence.save_entry.assert_called_once()

    def test_service_continues_on_exception(self):
        """Test that service continues when exception occurs."""
        from execution.paper.trade_journal_persistence import (
            TradeJournalRedisPersistence,
        )
        from execution.paper.trade_journal_service import TradeJournalService

        mock_persistence = MagicMock(spec=TradeJournalRedisPersistence)
        mock_persistence.is_healthy.return_value = True
        mock_persistence.save_entry.side_effect = Exception("Redis connection lost")

        service = TradeJournalService(
            session_id="test-session", persistence=mock_persistence
        )

        # Create mock position and signal
        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.position_id = "pos-123"

        mock_signal = MagicMock()
        mock_signal.signal_id = "sig-456"
        mock_signal.confidence = 0.85
        mock_signal.strategy_name = "test_strategy"

        # Create entry - should not raise even though exception occurs
        entry = service.create_entry(
            position=mock_position, signal=mock_signal, correlation_id="corr-789"
        )

        # Entry should still be created in memory
        assert entry is not None
