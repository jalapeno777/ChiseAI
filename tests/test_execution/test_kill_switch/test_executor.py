"""Tests for kill-switch executor.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.kill_switch.executor import KillSwitchExecutor
from execution.kill_switch.state import (
    CloseStatus,
    KillSwitchConfig,
    KillSwitchState,
)


class MockPosition:
    """Mock position for testing."""

    def __init__(
        self,
        position_id: str,
        token: str,
        direction: str,
        quantity: float,
        entry_price: float,
        is_open: bool = True,
    ):
        self.position_id = position_id
        self.token = token
        self.direction = MagicMock()
        self.direction.value = direction
        self.quantity = quantity
        self.entry_price = entry_price
        self.is_open = is_open


class MockPortfolioState:
    """Mock portfolio state for testing."""

    def __init__(self):
        self.positions = {}

    def add_position(self, position):
        self.positions[position.position_id] = position


class MockPortfolioTracker:
    """Mock portfolio tracker for testing."""

    def __init__(self):
        self.state = MockPortfolioState()

    async def close_position(self, position_id: str, exit_price: float) -> float:
        return 100.0  # Mock PnL


class TestKillSwitchExecutor:
    """Test KillSwitchExecutor class."""

    def test_initialization_defaults(self):
        """Test executor initialization with defaults."""
        executor = KillSwitchExecutor()

        assert executor.bybit_connector is None
        assert executor.bitget_connector is None
        assert executor.position_tracker is None
        assert executor.influxdb_client is None
        assert executor.drawdown_monitor is None
        assert executor.state == KillSwitchState.ARMED

    def test_initialization_with_connectors(self):
        """Test executor with provided connectors."""
        mock_bybit = MagicMock()
        mock_bitget = MagicMock()
        mock_tracker = MagicMock()
        mock_influx = MagicMock()
        mock_monitor = MagicMock()

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            bitget_connector=mock_bitget,
            position_tracker=mock_tracker,
            influxdb_client=mock_influx,
            drawdown_monitor=mock_monitor,
        )

        assert executor.bybit_connector == mock_bybit
        assert executor.bitget_connector == mock_bitget
        assert executor.position_tracker == mock_tracker
        assert executor.influxdb_client == mock_influx
        assert executor.drawdown_monitor == mock_monitor

    @pytest.mark.asyncio
    async def test_arm_from_disabled(self):
        """Test arming from disabled state."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.DISABLED

        result = await executor.arm()

        assert result is True
        assert executor.state == KillSwitchState.ARMED

    @pytest.mark.asyncio
    async def test_arm_from_armed(self):
        """Test arming when already armed."""
        executor = KillSwitchExecutor()

        result = await executor.arm()

        assert result is True
        assert executor.state == KillSwitchState.ARMED

    @pytest.mark.asyncio
    async def test_arm_from_triggered_blocked(self):
        """Test arming from triggered state is blocked."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.TRIGGERED

        result = await executor.arm()

        assert result is False
        assert executor.state == KillSwitchState.TRIGGERED

    @pytest.mark.asyncio
    async def test_disable_from_armed(self):
        """Test disabling from armed state."""
        executor = KillSwitchExecutor()

        result = await executor.disable()

        assert result is True
        assert executor.state == KillSwitchState.DISABLED

    @pytest.mark.asyncio
    async def test_disable_from_triggered_blocked(self):
        """Test disabling from triggered state is blocked."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.TRIGGERED

        result = await executor.disable()

        assert result is False
        assert executor.state == KillSwitchState.TRIGGERED

    @pytest.mark.asyncio
    async def test_disable_from_triggered_forced(self):
        """Test forcing disable from triggered state."""
        executor = KillSwitchExecutor(
            config=KillSwitchConfig(require_reauthorization=False)
        )
        executor._state = KillSwitchState.TRIGGERED

        result = await executor.disable()

        assert result is True
        assert executor.state == KillSwitchState.DISABLED

    @pytest.mark.asyncio
    async def test_reauthorize_from_triggered(self):
        """Test reauthorization from triggered state."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.TRIGGERED
        executor._triggered_at = datetime.now(UTC)

        result = await executor.reauthorize("signed_packet_123")

        assert result is True
        assert executor.state == KillSwitchState.ARMED
        assert executor._reauthorized_by == "signed_packet_123"
        assert executor._reauthorized_at is not None

    @pytest.mark.asyncio
    async def test_reauthorize_from_armed_fails(self):
        """Test reauthorization from armed state fails."""
        executor = KillSwitchExecutor()

        result = await executor.reauthorize("signed_packet_123")

        assert result is False
        assert executor.state == KillSwitchState.ARMED

    @pytest.mark.asyncio
    async def test_execute_kill_switch_when_disabled(self):
        """Test execution when disabled."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.DISABLED

        result = await executor.execute_kill_switch("test reason")

        assert result.success is False
        assert result.metadata["error"] == "kill_switch_disabled"

    @pytest.mark.asyncio
    async def test_execute_kill_switch_when_already_triggered(self):
        """Test execution when already triggered."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.TRIGGERED

        result = await executor.execute_kill_switch("test reason")

        assert result.success is False
        assert result.metadata["error"] == "already_triggered"

    @pytest.mark.asyncio
    async def test_execute_kill_switch_success(self):
        """Test successful kill-switch execution."""
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={
                "order_id": "order123",
                "price": 50000.0,
                "quantity": 1.0,
            }
        )

        mock_tracker = MockPortfolioTracker()
        mock_tracker.state.add_position(
            MockPosition(
                position_id="pos1",
                token="BTCUSDT",
                direction="long",
                quantity=1.0,
                entry_price=48000.0,
            )
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            config=KillSwitchConfig(require_reauthorization=False),
        )

        result = await executor.execute_kill_switch(
            reason="manual test",
            triggered_by="test",
            environment="paper",
        )

        assert result.success is True
        assert result.positions_closed == 1
        assert result.reason == "manual test"
        assert result.environment == "paper"
        assert executor.state == KillSwitchState.TRIGGERED

    @pytest.mark.asyncio
    async def test_close_all_positions_no_positions(self):
        """Test closing when no positions exist."""
        mock_tracker = MockPortfolioTracker()
        executor = KillSwitchExecutor(position_tracker=mock_tracker)

        results = await executor.close_all_positions("paper")

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_close_all_positions_with_positions(self):
        """Test closing multiple positions."""
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={
                "order_id": "order123",
                "price": 50000.0,
                "quantity": 1.0,
            }
        )

        mock_tracker = MockPortfolioTracker()
        mock_tracker.state.add_position(
            MockPosition(
                position_id="pos1",
                token="BTCUSDT",
                direction="long",
                quantity=1.0,
                entry_price=48000.0,
            )
        )
        mock_tracker.state.add_position(
            MockPosition(
                position_id="pos2",
                token="ETHUSDT",
                direction="short",
                quantity=5.0,
                entry_price=3000.0,
            )
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
        )

        results = await executor.close_all_positions("paper")

        assert len(results) == 2
        assert mock_bybit.close_position_market.call_count == 2

    @pytest.mark.asyncio
    async def test_close_single_position_success(self):
        """Test closing a single position successfully."""
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={
                "order_id": "order123",
                "price": 50000.0,
                "quantity": 1.0,
            }
        )

        mock_tracker = MockPortfolioTracker()
        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
        )

        position = MockPosition(
            position_id="pos1",
            token="BTCUSDT",
            direction="long",
            quantity=1.0,
            entry_price=48000.0,
        )

        result = await executor._close_single_position(position, "paper")

        assert result.status == CloseStatus.SUCCESS
        assert result.symbol == "BTCUSDT"
        assert result.side == "sell"
        assert result.order_id == "order123"

    @pytest.mark.asyncio
    async def test_close_single_position_failure(self):
        """Test closing a position that fails."""
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(side_effect=Exception("API error"))

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            config=KillSwitchConfig(max_close_retries=1),
        )

        position = MockPosition(
            position_id="pos1",
            token="BTCUSDT",
            direction="long",
            quantity=1.0,
            entry_price=48000.0,
        )

        result = await executor._close_single_position(position, "paper")

        assert result.status == CloseStatus.FAILED
        assert "API error" in result.error

    @pytest.mark.asyncio
    async def test_close_single_position_no_connector(self):
        """Test closing without available connector."""
        executor = KillSwitchExecutor()

        position = MockPosition(
            position_id="pos1",
            token="BTCUSDT",
            direction="long",
            quantity=1.0,
            entry_price=48000.0,
        )

        result = await executor._close_single_position(position, "paper")

        assert result.status == CloseStatus.FAILED
        assert "No exchange connector available" in result.error

    @pytest.mark.asyncio
    async def test_close_single_position_uses_bitget_for_live(self):
        """Test that live environment uses Bitget connector."""
        mock_bitget = AsyncMock()
        mock_bitget.close_position_market = AsyncMock(
            return_value={
                "order_id": "order456",
                "price": 51000.0,
                "quantity": 1.0,
            }
        )

        executor = KillSwitchExecutor(
            bitget_connector=mock_bitget,
        )

        position = MockPosition(
            position_id="pos1",
            token="BTCUSDT",
            direction="long",
            quantity=1.0,
            entry_price=48000.0,
        )

        result = await executor._close_single_position(position, "live")

        assert result.status == CloseStatus.SUCCESS
        mock_bitget.close_position_market.assert_called_once()

    def test_get_state(self):
        """Test get_state method."""
        executor = KillSwitchExecutor()

        assert executor.get_state() == KillSwitchState.ARMED

        executor._state = KillSwitchState.TRIGGERED
        assert executor.get_state() == KillSwitchState.TRIGGERED

    def test_get_summary(self):
        """Test get_summary method."""
        executor = KillSwitchExecutor()
        executor._triggered_at = datetime.now(UTC)
        executor._triggered_by = "test"
        executor._trigger_reason = "manual"

        summary = executor.get_summary()

        assert summary["state"] == "armed"
        assert summary["triggered_by"] == "test"
        assert summary["trigger_reason"] == "manual"
        assert summary["config"]["drawdown_threshold_pct"] == 15.0

    def test_get_log_history(self):
        """Test get_log_history method."""
        executor = KillSwitchExecutor()

        # Initial log entry from initialization
        history = executor.get_log_history()
        assert len(history) >= 1

    def test_get_last_result(self):
        """Test get_last_result method."""
        executor = KillSwitchExecutor()

        assert executor.get_last_result() is None

        # Simulate a result
        mock_result = MagicMock()
        executor._last_result = mock_result

        assert executor.get_last_result() == mock_result

    @pytest.mark.asyncio
    async def test_write_state_to_influxdb_no_client(self):
        """Test writing state without InfluxDB client."""
        executor = KillSwitchExecutor(influxdb_client=None)

        result = await executor._write_state_to_influxdb()

        assert result is False

    @pytest.mark.asyncio
    async def test_write_state_to_influxdb_success(self):
        """Test successful state write to InfluxDB."""
        mock_influx = AsyncMock()
        executor = KillSwitchExecutor(influxdb_client=mock_influx)

        result = await executor._write_state_to_influxdb()

        assert result is True
        mock_influx.write_point.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_result_to_influxdb_no_client(self):
        """Test writing result without InfluxDB client."""
        executor = KillSwitchExecutor(influxdb_client=None)
        mock_result = MagicMock()

        result = await executor._write_result_to_influxdb(mock_result)

        assert result is False

    @pytest.mark.asyncio
    async def test_write_result_to_influxdb_success(self):
        """Test successful result write to InfluxDB."""
        mock_influx = AsyncMock()
        executor = KillSwitchExecutor(influxdb_client=mock_influx)

        from execution.kill_switch.state import KillSwitchResult

        result_obj = KillSwitchResult(
            success=True,
            positions_closed=2,
            total_pnl=100.0,
            environment="paper",
        )

        result = await executor._write_result_to_influxdb(result_obj)

        assert result is True
        mock_influx.write_point.assert_called_once()

    def test_get_state_numeric(self):
        """Test state numeric conversion."""
        executor = KillSwitchExecutor()

        executor._state = KillSwitchState.DISABLED
        assert executor._get_state_numeric() == 0

        executor._state = KillSwitchState.ARMED
        assert executor._get_state_numeric() == 1

        executor._state = KillSwitchState.TRIGGERED
        assert executor._get_state_numeric() == 2

    @pytest.mark.asyncio
    async def test_execute_kill_switch_with_drawdown_monitor(self):
        """Test execution with drawdown monitor."""
        mock_monitor = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.current_drawdown_pct = 16.5
        mock_monitor.calculate_rolling_drawdown.return_value = mock_metrics
        mock_monitor.get_current_value.return_value = 83500.0

        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={
                "order_id": "order123",
                "price": 50000.0,
                "quantity": 1.0,
            }
        )

        mock_tracker = MockPortfolioTracker()
        mock_tracker.state.add_position(
            MockPosition(
                position_id="pos1",
                token="BTCUSDT",
                direction="long",
                quantity=1.0,
                entry_price=48000.0,
            )
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            drawdown_monitor=mock_monitor,
            config=KillSwitchConfig(require_reauthorization=False),
        )

        result = await executor.execute_kill_switch(
            reason="drawdown threshold exceeded",
            triggered_by="monitor",
            environment="paper",
        )

        assert result.success is True
        assert result.metadata["drawdown_pct"] == 16.5
        assert result.metadata["portfolio_value"] == 83500.0


class TestKillSwitchExecutorCoverageGaps:
    """Tests to fill coverage gaps identified in T-05.

    Targets uncovered lines:
    - 285-286: Race condition double-check after state lock
    - 310-311: Drawdown monitor exception
    - 351-354: Partial failure logging
    - 427-436: Position tracker exception during listing
    - 453, 466-482, 494: Failed positions + unexpected close exception
    - 544-545: Circuit breaker open in _close_single_position
    - 582-588: Position tracker error during close
    - 609: Retry delay between attempts
    - 690-692, 725-727: InfluxDB write exceptions
    - 792-829, 848-885: InfluxDB retry versions
    """

    # --- Lines 285-286: Race condition double-check after state lock ---

    @pytest.mark.asyncio
    async def test_race_condition_double_check_after_lock(self):
        """Test that kill-switch ignores when state becomes TRIGGERED between initial check and lock acquisition.

        Covers lines 285-286: the double-check guard inside the state lock.
        We simulate the race by having the state change to TRIGGERED inside the lock.
        """
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={"order_id": "o1", "price": 50000.0, "quantity": 1.0}
        )
        mock_tracker = MockPortfolioTracker()

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            config=KillSwitchConfig(require_reauthorization=False),
        )

        # Simulate race condition: state is ARMED initially but becomes
        # TRIGGERED between the initial check and the lock acquisition.
        # We do this by acquiring the state_lock first and setting state
        # to TRIGGERED, then calling execute_kill_switch from a task that
        # will see TRIGGERED inside the lock.
        await executor._state_lock.acquire()
        executor._state = KillSwitchState.TRIGGERED

        result = await executor.execute_kill_switch(
            reason="race test", triggered_by="concurrent_caller", environment="paper"
        )

        # The state_lock is now released (execute_kill_switch timed out waiting
        # for the lock, or we need to release it). Let's use a different approach.
        executor._state_lock.release()

        # Use a simpler approach: directly set state to TRIGGERED before
        # the state lock check. The initial check (line 267) happens before
        # the lock, so we can set state after that check returns ARMED.
        # We patch asyncio.Lock to manipulate timing.

        # Actually, the simplest approach: since the initial check at line 267
        # is outside the lock and the double-check at line 284 is inside the lock,
        # we can't easily race with a single-threaded test. Instead, we test
        # the path directly by ensuring state is TRIGGERED when the lock body
        # executes.

        # Reset state
        executor._state = KillSwitchState.ARMED

        # Use a task to set the state to TRIGGERED while the lock is held
        # by execute_kill_switch. The _trigger_lock is acquired first, then
        # inside it the _state_lock is acquired. Between the initial state
        # check and the lock, we change the state.

        state_change_done = asyncio.Event()
        original_acquire = executor._state_lock.acquire
        original_release = executor._state_lock.release
        acquire_count = 0

        async def patched_acquire():
            nonlocal acquire_count
            acquire_count += 1
            if acquire_count == 1:
                # First acquire (in execute_kill_switch) - change state before returning
                executor._state = KillSwitchState.TRIGGERED
                state_change_done.set()
            return await original_acquire()

        with patch.object(executor._state_lock, "acquire", side_effect=patched_acquire):
            result = await executor.execute_kill_switch(
                reason="race test",
                triggered_by="concurrent_caller",
                environment="paper",
            )

        assert result.success is False
        assert result.metadata["error"] == "already_triggered"
        # Positions should NOT have been closed since we short-circuited
        mock_bybit.close_position_market.assert_not_called()

    # --- Lines 310-311: Drawdown monitor exception ---

    @pytest.mark.asyncio
    async def test_drawdown_monitor_exception_continues(self):
        """Test that kill-switch continues when drawdown monitor raises an exception.

        Covers lines 310-311: exception handler for calculate_rolling_drawdown().
        """
        mock_monitor = MagicMock()
        mock_monitor.calculate_rolling_drawdown.side_effect = RuntimeError(
            "Monitor unavailable"
        )

        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={"order_id": "o1", "price": 50000.0, "quantity": 1.0}
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            drawdown_monitor=mock_monitor,
            config=KillSwitchConfig(require_reauthorization=False),
        )

        result = await executor.execute_kill_switch(
            reason="drawdown test", environment="paper"
        )

        # Kill-switch should still succeed despite monitor failure
        assert result.success is True
        # drawdown_pct should be 0.0 (default) since monitor failed
        assert result.metadata.get("drawdown_pct", 0.0) == 0.0

    # --- Lines 351-354: Partial failure logging ---

    @pytest.mark.asyncio
    async def test_partial_failure_logging(self):
        """Test that partial failures are tracked and logged.

        Covers lines 351-354: has_partial_failures branch with failed_symbols.
        """
        mock_bybit = AsyncMock()
        # First call succeeds, second call fails
        mock_bybit.close_position_market = AsyncMock(
            side_effect=[
                {"order_id": "o1", "price": 50000.0, "quantity": 1.0},
                Exception("Exchange timeout"),
            ]
        )

        mock_tracker = MockPortfolioTracker()
        mock_tracker.state.add_position(
            MockPosition("pos1", "BTCUSDT", "long", 1.0, 48000.0)
        )
        mock_tracker.state.add_position(
            MockPosition("pos2", "ETHUSDT", "short", 5.0, 3000.0)
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            config=KillSwitchConfig(max_close_retries=1, require_reauthorization=False),
        )

        result = await executor.execute_kill_switch(
            reason="partial fail test", environment="paper"
        )

        # Overall kill-switch is still a success (we attempted)
        assert result.success is True
        # One position closed, one failed
        assert result.positions_closed == 1
        failed_count = sum(
            1 for r in result.close_results if r.status == CloseStatus.FAILED
        )
        assert failed_count == 1
        assert result.metadata.get("has_partial_failures") is True

    # --- Lines 427-436: Position tracker exception during listing ---

    @pytest.mark.asyncio
    async def test_position_tracker_exception_during_listing(self):
        """Test that position tracker exception during listing returns empty results.

        Covers lines 427-436: exception handler when iterating tracker.state.positions.
        """
        mock_tracker = MagicMock()
        # Simulate exception when accessing .state.positions.values()
        mock_tracker.state.positions.values.side_effect = RuntimeError(
            "Tracker corrupted"
        )

        executor = KillSwitchExecutor(position_tracker=mock_tracker)

        results = await executor.close_all_positions("paper")

        assert results == []
        # Should log error but not crash

    # --- Lines 453: Tracking failed positions ---

    @pytest.mark.asyncio
    async def test_failed_positions_tracked_in_close_loop(self):
        """Test that failed positions are appended to failed_positions list.

        Covers line 453: failed_positions.append((position, result)).
        """
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(side_effect=Exception("API down"))

        mock_tracker = MockPortfolioTracker()
        mock_tracker.state.add_position(
            MockPosition("pos1", "BTCUSDT", "long", 1.0, 48000.0)
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            config=KillSwitchConfig(max_close_retries=1),
        )

        results = await executor.close_all_positions("paper")

        assert len(results) == 1
        assert results[0].status == CloseStatus.FAILED

    # --- Lines 466-482: Unexpected exception during position close ---

    @pytest.mark.asyncio
    async def test_unexpected_exception_during_position_close(self):
        """Test that unexpected exceptions during close are caught and converted to CloseResult.

        Covers lines 466-482: the except block in close_all_positions loop.
        """
        mock_bybit = AsyncMock()
        mock_tracker = MockPortfolioTracker()
        mock_tracker.state.add_position(
            MockPosition("pos1", "BTCUSDT", "long", 1.0, 48000.0)
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
        )

        # Make _close_single_position raise an unexpected exception
        # We patch it directly to raise something unexpected
        original_method = executor._close_single_position

        async def raising_close(position, environment):
            raise RuntimeError("Unexpected serialization error")

        with patch.object(
            executor, "_close_single_position", side_effect=raising_close
        ):
            results = await executor.close_all_positions("paper")

        assert len(results) == 1
        assert results[0].status == CloseStatus.FAILED
        assert "Unexpected exception" in results[0].error

    # --- Lines 544-545: Circuit breaker open in _close_single_position ---

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_blocks_position_close(self):
        """Test that circuit breaker open state prevents position closing.

        Covers lines 544-545: circuit breaker check returns failed CloseResult.
        """
        mock_bybit = AsyncMock()
        executor = KillSwitchExecutor(bybit_connector=mock_bybit)

        # Create a mock circuit breaker that reports open
        mock_breaker = AsyncMock()
        mock_breaker.can_execute = AsyncMock(return_value=False)

        # Replace the registered circuit breaker
        executor._retry_handler._circuit_breakers["exchange"] = mock_breaker

        position = MockPosition("pos1", "BTCUSDT", "long", 1.0, 48000.0)

        result = await executor._close_single_position(position, "paper")

        assert result.status == CloseStatus.FAILED
        assert "circuit breaker open" in result.error.lower()
        # Exchange should NOT have been called
        mock_bybit.close_position_market.assert_not_called()

    # --- Lines 582-588: Position tracker error during close ---

    @pytest.mark.asyncio
    async def test_position_tracker_error_during_close(self):
        """Test that position tracker exception during close doesn't fail the close.

        Covers lines 582-588: tracker exception is caught, pnl defaults to 0.0.
        """
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={"order_id": "o1", "price": 50000.0, "quantity": 1.0}
        )

        # Tracker that raises on close_position
        mock_tracker = MagicMock()
        mock_tracker.close_position = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
        )

        position = MockPosition("pos1", "BTCUSDT", "long", 1.0, 48000.0)

        result = await executor._close_single_position(position, "paper")

        # Position close should still succeed
        assert result.status == CloseStatus.SUCCESS
        # PnL should default to 0.0 when tracker fails
        assert result.pnl == 0.0

    # --- Lines 609: Retry delay between attempts ---

    @pytest.mark.asyncio
    async def test_retry_delay_between_close_attempts(self):
        """Test that retry delay is respected between close attempts.

        Covers line 609: asyncio.sleep(self.config.close_retry_delay_seconds).
        """
        mock_bybit = AsyncMock()
        # Fail first 2 attempts, succeed on 3rd
        mock_bybit.close_position_market = AsyncMock(
            side_effect=[
                Exception("timeout"),
                Exception("timeout"),
                {"order_id": "o1", "price": 50000.0, "quantity": 1.0},
            ]
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            config=KillSwitchConfig(
                max_close_retries=3, close_retry_delay_seconds=0.01
            ),
        )

        position = MockPosition("pos1", "BTCUSDT", "long", 1.0, 48000.0)

        with patch(
            "execution.kill_switch.executor.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await executor._close_single_position(position, "paper")

        assert result.status == CloseStatus.SUCCESS
        # Should have slept between attempts (2 times: after attempt 1 and after attempt 2)
        assert mock_sleep.call_count == 2

    # --- Lines 690-692: InfluxDB state write exception ---

    @pytest.mark.asyncio
    async def test_write_state_to_influxdb_exception(self):
        """Test that InfluxDB write exception is caught gracefully.

        Covers lines 690-692: exception handler in _write_state_to_influxdb.
        """
        mock_influx = AsyncMock()
        mock_influx.write_point = AsyncMock(
            side_effect=ConnectionError("InfluxDB down")
        )

        executor = KillSwitchExecutor(influxdb_client=mock_influx)

        result = await executor._write_state_to_influxdb()

        assert result is False

    # --- Lines 725-727: InfluxDB result write exception ---

    @pytest.mark.asyncio
    async def test_write_result_to_influxdb_exception(self):
        """Test that InfluxDB result write exception is caught gracefully.

        Covers lines 725-727: exception handler in _write_result_to_influxdb.
        """
        mock_influx = AsyncMock()
        mock_influx.write_point = AsyncMock(
            side_effect=ConnectionError("InfluxDB down")
        )

        from execution.kill_switch.state import KillSwitchResult

        executor = KillSwitchExecutor(influxdb_client=mock_influx)

        result_obj = KillSwitchResult(
            success=True, positions_closed=1, total_pnl=50.0, environment="paper"
        )

        result = await executor._write_result_to_influxdb(result_obj)

        assert result is False

    # --- Lines 824-829: InfluxDB retry with circuit breaker open ---

    @pytest.mark.asyncio
    async def test_write_state_to_influxdb_with_retry_circuit_breaker_open(self):
        """Test InfluxDB state write with retry when circuit breaker is open.

        Covers lines 824-826: CircuitBreakerOpenError handler in retry version.
        """
        mock_influx = AsyncMock()
        mock_influx.write_point = AsyncMock(
            side_effect=ConnectionError("InfluxDB down")
        )

        # Set log_to_influxdb=True so the retry path is used
        executor = KillSwitchExecutor(
            influxdb_client=mock_influx,
            config=KillSwitchConfig(log_to_influxdb=True),
        )

        # Force circuit breaker open by tripping it
        breaker = executor._retry_handler.get_circuit_breaker("influxdb")
        # Record enough failures to open the breaker
        for _ in range(breaker.config.failure_threshold):
            await breaker.record_failure()

        result = await executor._write_state_to_influxdb_with_retry()

        assert result is False

    @pytest.mark.asyncio
    async def test_write_result_to_influxdb_with_retry_circuit_breaker_open(self):
        """Test InfluxDB result write with retry when circuit breaker is open.

        Covers lines 880-882: CircuitBreakerOpenError handler in result retry version.
        """
        mock_influx = AsyncMock()

        from execution.kill_switch.state import KillSwitchResult

        executor = KillSwitchExecutor(
            influxdb_client=mock_influx,
            config=KillSwitchConfig(log_to_influxdb=True),
        )

        # Force circuit breaker open
        breaker = executor._retry_handler.get_circuit_breaker("influxdb")
        for _ in range(breaker.config.failure_threshold):
            await breaker.record_failure()

        result_obj = KillSwitchResult(
            success=True, positions_closed=1, total_pnl=50.0, environment="paper"
        )

        result = await executor._write_result_to_influxdb_with_retry(result_obj)

        assert result is False

    @pytest.mark.asyncio
    async def test_write_state_to_influxdb_with_retry_generic_exception(self):
        """Test InfluxDB state write with retry when generic exception occurs.

        Covers lines 827-829: generic exception handler in state retry version.
        """
        mock_influx = AsyncMock()
        mock_influx.write_point = AsyncMock(side_effect=ValueError("Invalid data"))

        executor = KillSwitchExecutor(
            influxdb_client=mock_influx,
            config=KillSwitchConfig(log_to_influxdb=True),
        )

        # The retry handler will exhaust retries and raise
        result = await executor._write_state_to_influxdb_with_retry()

        assert result is False

    @pytest.mark.asyncio
    async def test_write_result_to_influxdb_with_retry_generic_exception(self):
        """Test InfluxDB result write with retry when generic exception occurs.

        Covers lines 883-885: generic exception handler in result retry version.
        """
        mock_influx = AsyncMock()
        mock_influx.write_point = AsyncMock(side_effect=ValueError("Invalid data"))

        from execution.kill_switch.state import KillSwitchResult

        executor = KillSwitchExecutor(
            influxdb_client=mock_influx,
            config=KillSwitchConfig(log_to_influxdb=True),
        )

        result_obj = KillSwitchResult(
            success=True, positions_closed=1, total_pnl=50.0, environment="paper"
        )

        result = await executor._write_result_to_influxdb_with_retry(result_obj)

        assert result is False
