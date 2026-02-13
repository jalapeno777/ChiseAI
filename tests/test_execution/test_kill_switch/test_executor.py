"""Tests for kill-switch executor.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from execution.kill_switch.executor import KillSwitchExecutor
from execution.kill_switch.state import (
    CloseResult,
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
