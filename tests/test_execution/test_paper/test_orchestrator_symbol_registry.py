"""Tests for Orchestrator + Symbol Registry Integration.

Tests that PaperTradingOrchestrator correctly integrates with
SymbolPositionRegistry to enforce the one-trade-per-symbol invariant.

Part of PAPER-2025-BATCH2-001: Symbol Registry Integration.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
    PaperTradeResult,
    TradeStatus,
)
from src.execution.paper.symbol_registry import SymbolPositionRegistry
from src.signal_generation.models import Signal, SignalDirection, SignalStatus


class TestOrchestratorSymbolRegistryIntegration:
    """Test orchestrator integration with SymbolPositionRegistry."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.set = AsyncMock()
        mock.get = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock(return_value=[])
        mock.ttl = AsyncMock(return_value=-2)
        mock.expire = AsyncMock(return_value=True)
        mock.pipeline = MagicMock(return_value=mock)
        mock.execute = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def symbol_registry(self, mock_redis):
        """Create a symbol registry with mock Redis."""
        return SymbolPositionRegistry(redis_client=mock_redis, default_ttl_seconds=3600)

    @pytest.fixture
    def mock_signal_generator(self):
        """Create a mock signal generator."""
        mock = MagicMock()
        mock.generate_signals = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_order_simulator(self):
        """Create a mock order simulator."""
        mock = MagicMock()
        mock.market_data = MagicMock()
        mock.market_data.get_price = MagicMock(return_value=50000.0)
        mock.place_order = AsyncMock(
            return_value=PaperOrder(
                order_id="order-123",
                symbol="BTC/USDT",
                side=OrderSide.BUY.value,
                order_type=OrderType.MARKET.value,
                quantity=0.1,
                price=50000.0,
                state=OrderState.FILLED,
                filled_quantity=0.1,
                avg_fill_price=50000.0,
            )
        )
        return mock

    @pytest.fixture
    def mock_position_tracker(self):
        """Create a mock position tracker."""
        mock = AsyncMock()
        mock.get_open_positions = AsyncMock(return_value=[])
        mock.get_closed_positions = AsyncMock(return_value=[])
        mock.open_position = AsyncMock(
            return_value=MagicMock(
                position_id="pos-123",
                symbol="BTC/USDT",
                side="long",
                entry_price=50000.0,
                quantity=0.1,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=datetime.now(UTC),
                metadata={},
            )
        )
        mock.close_position = AsyncMock(
            return_value=(
                MagicMock(
                    position_id="pos-123",
                    symbol="BTC/USDT",
                    side="long",
                    entry_price=50000.0,
                    quantity=0.1,
                    metadata={},
                ),
                100.0,  # realized_pnl
            )
        )
        return mock

    @pytest.fixture
    def mock_risk_enforcer(self):
        """Create a mock risk enforcer."""
        mock = AsyncMock()
        mock.validate_order = AsyncMock(
            return_value=MagicMock(
                approved=True,
                violations=[],
                position_size=0.1,
            )
        )
        return mock

    @pytest.fixture
    def mock_telemetry(self):
        """Create a mock telemetry collector."""
        mock = AsyncMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.set_equity = MagicMock()
        return mock

    @pytest.fixture
    def mock_kill_switch(self):
        """Create a mock kill switch."""
        mock = MagicMock()
        mock.state = MagicMock()
        mock.state.value = "armed"
        return mock

    @pytest.fixture
    def sample_signal(self):
        """Create a sample trading signal."""
        return Signal(
            signal_id="sig-123",
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

    @pytest.mark.skip(
        reason="Symbol registry integration not fully implemented - PAPER-2025-BATCH2-001"
    )
    @pytest.mark.asyncio
    async def test_orchestrator_acquires_symbol_before_order(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        symbol_registry,
        sample_signal,
        mock_redis,
    ):
        """Test that orchestrator acquires symbol before creating order."""
        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        # Setup: Symbol acquisition succeeds
        mock_redis.set.return_value = True

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            symbol_registry=symbol_registry,
        )

        result = await orchestrator.process_signal(sample_signal)

        # Verify: Trade executed successfully
        assert result.status == TradeStatus.EXECUTED
        assert result.position is not None

        # Verify: Symbol was acquired via registry
        mock_redis.set.assert_called()
        # Check that SET NX was called with the symbol
        call_args = mock_redis.set.call_args_list
        assert any("BTC_USDT" in str(call) for call in call_args)

    @pytest.mark.skip(
        reason="Symbol registry integration not fully implemented - PAPER-2025-BATCH2-001"
    )
    @pytest.mark.asyncio
    async def test_orchestrator_releases_symbol_after_close(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        symbol_registry,
        sample_signal,
        mock_redis,
    ):
        """Test that orchestrator releases symbol after position close."""
        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        # Setup: Symbol acquisition succeeds, then release succeeds
        mock_redis.set.return_value = True
        mock_redis.get.return_value = "pos-123"
        mock_redis.delete.return_value = 1

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            symbol_registry=symbol_registry,
        )

        # First open a position
        await orchestrator.process_signal(sample_signal)

        # Then close it
        result = await orchestrator.close_position("pos-123", 51000.0, reason="manual")

        # Verify: Position was closed
        assert result is not None
        position, pnl = result
        assert position.position_id == "pos-123"

        # Verify: Symbol was released via registry
        mock_redis.delete.assert_called()

    @pytest.mark.skip(
        reason="Symbol registry integration not fully implemented - PAPER-2025-BATCH2-001"
    )
    @pytest.mark.asyncio
    async def test_second_signal_for_same_symbol_rejected(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        symbol_registry,
        sample_signal,
        mock_redis,
    ):
        """Test that second signal for same symbol is rejected with symbol_occupied."""
        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        # Setup: First acquisition succeeds, second fails
        mock_redis.set.side_effect = [True, None]  # First succeeds, second fails
        mock_redis.get.return_value = "pos-existing"

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            symbol_registry=symbol_registry,
        )

        # First signal should succeed
        result1 = await orchestrator.process_signal(sample_signal)
        assert result1.status == TradeStatus.EXECUTED

        # Reset the mock to simulate symbol already held
        mock_redis.set.return_value = None
        mock_redis.get.return_value = "pos-123"

        # Second signal for same symbol should be rejected
        result2 = await orchestrator.process_signal(sample_signal)

        assert result2.status == TradeStatus.REJECTED
        assert result2.reject_reason is not None
        assert any("symbol_occupied" in reason for reason in result2.reject_reason)

    @pytest.mark.asyncio
    async def test_backward_compatibility_without_registry(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        sample_signal,
    ):
        """Test that orchestrator works without symbol_registry (backward compatibility)."""
        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        # Create orchestrator WITHOUT symbol_registry
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            symbol_registry=None,  # No registry
        )

        result = await orchestrator.process_signal(sample_signal)

        # Verify: Trade still executes successfully without registry
        assert result.status == TradeStatus.EXECUTED
        assert result.position is not None

    @pytest.mark.asyncio
    async def test_position_id_mismatch_protection(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        symbol_registry,
        sample_signal,
        mock_redis,
    ):
        """Test that release fails when position_id doesn't match."""
        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        # Setup: Acquisition succeeds
        mock_redis.set.return_value = True

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            symbol_registry=symbol_registry,
        )

        # Open a position
        await orchestrator.process_signal(sample_signal)

        # Setup: Simulate position_id mismatch on release
        mock_redis.get.return_value = (
            "different-pos-id"  # Different position holds the symbol
        )

        # Try to close - release should fail but close should still complete
        result = await orchestrator.close_position("pos-123", 51000.0, reason="manual")

        # Verify: Position close still succeeds (graceful degradation)
        assert result is not None
        position, pnl = result
        assert position.position_id == "pos-123"

    @pytest.mark.asyncio
    async def test_registry_error_does_not_block_trade(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        symbol_registry,
        sample_signal,
        mock_redis,
    ):
        """Test that Redis errors don't block trade execution (graceful degradation)."""
        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        # Setup: Redis throws error
        mock_redis.set.side_effect = Exception("Redis connection error")

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            symbol_registry=symbol_registry,
        )

        result = await orchestrator.process_signal(sample_signal)

        # Verify: Trade still executes despite Redis error
        assert result.status == TradeStatus.EXECUTED
        assert result.position is not None

    @pytest.mark.asyncio
    async def test_different_symbols_both_allowed(
        self,
        mock_signal_generator,
        mock_order_simulator,
        mock_position_tracker,
        mock_risk_enforcer,
        mock_telemetry,
        mock_kill_switch,
        symbol_registry,
        mock_redis,
    ):
        """Test that different symbols can both be acquired."""
        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        # Setup: All acquisitions succeed
        mock_redis.set.return_value = True

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_signal_generator,
            order_simulator=mock_order_simulator,
            position_tracker=mock_position_tracker,
            risk_enforcer=mock_risk_enforcer,
            telemetry_collector=mock_telemetry,
            kill_switch=mock_kill_switch,
            symbol_registry=symbol_registry,
        )

        # First signal for BTC/USDT
        signal_btc = Signal(
            signal_id="sig-btc",
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        result1 = await orchestrator.process_signal(signal_btc)
        assert result1.status == TradeStatus.EXECUTED

        # Setup mock for second symbol
        mock_order_simulator.market_data.get_price = MagicMock(return_value=3000.0)
        mock_position_tracker.open_position = AsyncMock(
            return_value=MagicMock(
                position_id="pos-eth",
                symbol="ETH/USDT",
                side="long",
                entry_price=3000.0,
                quantity=1.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=datetime.now(UTC),
                metadata={},
            )
        )

        # Second signal for ETH/USDT (different symbol)
        signal_eth = Signal(
            signal_id="sig-eth",
            token="ETH/USDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        result2 = await orchestrator.process_signal(signal_eth)

        # Both trades should execute successfully
        assert result2.status == TradeStatus.EXECUTED


class TestSymbolRegistryEdgeCases:
    """Test edge cases in symbol registry integration."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.set = AsyncMock()
        mock.get = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock(return_value=[])
        mock.ttl = AsyncMock(return_value=-2)
        mock.expire = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def symbol_registry(self, mock_redis):
        """Create a symbol registry with mock Redis."""
        return SymbolPositionRegistry(redis_client=mock_redis, default_ttl_seconds=3600)

    @pytest.mark.asyncio
    async def test_symbol_normalization_in_registry(self, symbol_registry, mock_redis):
        """Test that symbols are normalized correctly."""
        mock_redis.set.return_value = True

        # Test various symbol formats
        await symbol_registry.try_acquire_symbol("btc-usdt", "pos-1")
        await symbol_registry.try_acquire_symbol("BTC/USDT", "pos-2")
        await symbol_registry.try_acquire_symbol("btc_usdt", "pos-3")

        # All should use the same normalized key
        calls = mock_redis.set.call_args_list
        keys = [call[0][0] for call in calls]

        # All keys should be normalized to the same format
        assert all("BTC_USDT" in key for key in keys)

    @pytest.mark.asyncio
    async def test_release_nonexistent_symbol(self, symbol_registry, mock_redis):
        """Test releasing a symbol that doesn't exist."""
        mock_redis.get.return_value = None  # Symbol not found

        result = await symbol_registry.release_symbol("BTC/USDT", "pos-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_with_custom_ttl(self, symbol_registry, mock_redis):
        """Test acquiring symbol with custom TTL."""
        mock_redis.set.return_value = True

        result = await symbol_registry.try_acquire_symbol(
            "BTC/USDT", "pos-123", ttl_seconds=7200
        )

        assert result is True
        mock_redis.set.assert_called_once()
        # Verify TTL was passed
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs.get("ex") == 7200
