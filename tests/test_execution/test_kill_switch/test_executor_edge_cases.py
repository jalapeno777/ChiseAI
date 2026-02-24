"""Edge case tests for kill-switch executor.

Provides comprehensive test coverage for edge cases including:
- Redis failure during kill-switch trigger (circuit breaker integration)
- Partial position closure failures (some succeed, some fail)
- Concurrent kill-switch triggers (race condition handling)
- Exchange API outage handling
- Position tracker exception handling
- InfluxDB write failure handling
- Retry/fallback logic for transient failures

For ST-PAPER-006: Kill-Switch Edge Case Handling
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.kill_switch.executor import KillSwitchExecutor
from execution.kill_switch.retry_handler import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    RetryConfig,
    RetryHandler,
    RetryStrategy,
)
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


class TestKillSwitchEdgeCases:
    """Test kill-switch edge cases."""

    # =================================================================
    # 1. Redis Failure During Kill-Switch Trigger
    # =================================================================

    @pytest.mark.asyncio
    async def test_redis_failure_during_trigger_continues_execution(self):
        """Test that kill-switch continues even if Redis fails."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Redis connection failed"))

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
            redis_client=mock_redis,
            config=KillSwitchConfig(require_reauthorization=False),
        )

        # Trigger should succeed even if Redis fails
        result = await executor.execute_kill_switch(
            reason="test with Redis failure",
            triggered_by="test",
            environment="paper",
        )

        # Kill-switch should still execute successfully
        assert result.success is True
        assert result.positions_closed == 1
        assert executor.state == KillSwitchState.TRIGGERED

    @pytest.mark.asyncio
    async def test_redis_circuit_breaker_opens_after_failures(self):
        """Test Redis circuit breaker opens after multiple failures."""
        executor = KillSwitchExecutor()

        # Get the Redis circuit breaker
        breaker = executor._retry_handler.get_circuit_breaker("redis")
        assert breaker is not None

        # Simulate multiple failures
        for _ in range(5):
            await breaker.record_failure()

        # Circuit should be open
        can_execute = await breaker.can_execute()
        assert can_execute is False
        assert breaker.state.value == "open"

    # =================================================================
    # 2. Partial Position Closure Failures
    # =================================================================

    @pytest.mark.asyncio
    async def test_partial_position_closure_some_fail(self):
        """Test handling when some positions fail to close."""
        mock_bybit = AsyncMock()

        # First call succeeds, second fails, third succeeds
        call_count = [0]

        async def mock_close_position(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("API error for position 2")
            return {
                "order_id": f"order{call_count[0]}",
                "price": 50000.0,
                "quantity": 1.0,
            }

        mock_bybit.close_position_market = mock_close_position

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
        mock_tracker.state.add_position(
            MockPosition(
                position_id="pos3",
                token="SOLUSDT",
                direction="long",
                quantity=10.0,
                entry_price=100.0,
            )
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            config=KillSwitchConfig(
                require_reauthorization=False,
                max_close_retries=1,
            ),
        )

        result = await executor.execute_kill_switch(
            reason="test partial failures",
            triggered_by="test",
            environment="paper",
        )

        # Should report partial failures in metadata
        assert result.success is True  # Overall success
        assert result.positions_closed == 2  # 2 succeeded
        assert result.metadata["positions_failed"] == 1  # 1 failed
        assert result.metadata["has_partial_failures"] is True

        # Check that all positions were attempted
        assert len(result.close_results) == 3

        # Verify which positions succeeded/failed
        statuses = [r.status for r in result.close_results]
        assert statuses.count(CloseStatus.SUCCESS) == 2
        assert statuses.count(CloseStatus.FAILED) == 1

    @pytest.mark.asyncio
    async def test_all_positions_fail_handled_gracefully(self):
        """Test handling when all positions fail to close."""
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(side_effect=Exception("API down"))

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
            config=KillSwitchConfig(
                require_reauthorization=False,
                max_close_retries=1,
            ),
        )

        result = await executor.execute_kill_switch(
            reason="test all failures",
            triggered_by="test",
            environment="paper",
        )

        # Should still report success (we attempted)
        assert result.success is True
        assert result.positions_closed == 0
        assert result.metadata["positions_failed"] == 1
        assert result.metadata["has_partial_failures"] is True

    # =================================================================
    # 3. Concurrent Kill-Switch Triggers (Race Condition Handling)
    # =================================================================

    @pytest.mark.asyncio
    async def test_concurrent_triggers_are_deduplicated(self):
        """Test that concurrent triggers are properly deduplicated."""
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

        # Trigger kill-switch multiple times concurrently
        async def trigger_kill_switch(trigger_id):
            return await executor.execute_kill_switch(
                reason=f"concurrent trigger {trigger_id}",
                triggered_by=f"test_{trigger_id}",
                environment="paper",
            )

        # Launch multiple concurrent triggers
        results = await asyncio.gather(
            trigger_kill_switch(1),
            trigger_kill_switch(2),
            trigger_kill_switch(3),
            return_exceptions=True,
        )

        # One should succeed, others should be deduplicated
        successful_results = [
            r
            for r in results
            if isinstance(r, type(results[0]))
            and r.metadata.get("error") != "already_triggered"
        ]

        # At most one should actually execute
        assert len(successful_results) <= 1

        # State should be triggered
        assert executor.state == KillSwitchState.TRIGGERED

    @pytest.mark.asyncio
    async def test_trigger_idempotency_multiple_calls(self):
        """Test that multiple trigger calls are idempotent."""
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

        # First trigger
        result1 = await executor.execute_kill_switch(
            reason="first trigger",
            triggered_by="test",
            environment="paper",
        )
        assert result1.success is True
        assert mock_bybit.close_position_market.call_count == 1

        # Second trigger should be deduplicated
        result2 = await executor.execute_kill_switch(
            reason="second trigger",
            triggered_by="test",
            environment="paper",
        )
        assert result2.success is False
        assert result2.metadata["error"] == "already_triggered"
        # Should not have called close_position again
        assert mock_bybit.close_position_market.call_count == 1

    # =================================================================
    # 4. Exchange API Outage Handling
    # =================================================================

    @pytest.mark.asyncio
    async def test_exchange_circuit_breaker_opens_during_outage(self):
        """Test circuit breaker opens when exchange API is down."""
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            config=KillSwitchConfig(
                require_reauthorization=False,
                max_close_retries=5,
            ),
        )

        position = MockPosition(
            position_id="pos1",
            token="BTCUSDT",
            direction="long",
            quantity=1.0,
            entry_price=48000.0,
        )

        # Get circuit breaker and open it directly
        breaker = executor._retry_handler.get_circuit_breaker("exchange")

        # Record multiple failures to open the circuit
        for _ in range(5):
            await breaker.record_failure()

        # Circuit should be open
        assert breaker.state.value == "open"

        # Subsequent attempts should fail fast with circuit breaker error
        result = await executor._close_single_position(position, "paper")
        assert result.status == CloseStatus.FAILED
        assert "circuit breaker" in result.error.lower()

    @pytest.mark.asyncio
    async def test_exchange_circuit_breaker_recovery(self):
        """Test circuit breaker recovers after timeout."""
        executor = KillSwitchExecutor()
        breaker = executor._retry_handler.get_circuit_breaker("exchange")

        # Open the circuit
        for _ in range(5):
            await breaker.record_failure()

        assert breaker.state.value == "open"

        # Simulate time passing
        # In real scenario, we'd wait for recovery_timeout_seconds
        # For testing, we manually transition to half-open and then closed
        breaker._state = type(breaker.state)("half_open")  # type: ignore

        # Record success to close circuit
        await breaker.record_success()
        await breaker.record_success()

        assert breaker.state.value == "closed"

    # =================================================================
    # 5. Position Tracker Exception Handling
    # =================================================================

    @pytest.mark.asyncio
    async def test_position_tracker_exception_during_close(self):
        """Test handling when position tracker throws exception."""
        mock_bybit = AsyncMock()
        mock_bybit.close_position_market = AsyncMock(
            return_value={
                "order_id": "order123",
                "price": 50000.0,
                "quantity": 1.0,
            }
        )

        mock_tracker = MagicMock()
        mock_tracker.state = MagicMock()
        mock_tracker.state.positions = {
            "pos1": MockPosition(
                position_id="pos1",
                token="BTCUSDT",
                direction="long",
                quantity=1.0,
                entry_price=48000.0,
            )
        }
        mock_tracker.close_position = AsyncMock(
            side_effect=Exception("Tracker database error")
        )

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            config=KillSwitchConfig(require_reauthorization=False),
        )

        result = await executor.execute_kill_switch(
            reason="test tracker exception",
            triggered_by="test",
            environment="paper",
        )

        # Should still succeed - position was closed even if tracker failed
        assert result.success is True
        assert result.positions_closed == 1
        # PnL should be 0 since tracker failed
        assert result.total_pnl == 0.0

    @pytest.mark.asyncio
    async def test_position_tracker_exception_during_get_positions(self):
        """Test handling when position tracker fails to get positions."""
        mock_tracker = MagicMock()
        mock_tracker.state = MagicMock()
        # Simulate exception when accessing positions
        mock_tracker.state.positions = MagicMock()
        mock_tracker.state.positions.values = MagicMock(
            side_effect=Exception("Database connection lost")
        )

        executor = KillSwitchExecutor(
            position_tracker=mock_tracker,
            config=KillSwitchConfig(require_reauthorization=False),
        )

        result = await executor.execute_kill_switch(
            reason="test tracker get exception",
            triggered_by="test",
            environment="paper",
        )

        # Should still report success - we attempted the kill-switch
        assert result.success is True
        assert result.positions_closed == 0
        assert result.metadata["total_positions"] == 0

    # =================================================================
    # 6. InfluxDB Write Failure Handling
    # =================================================================

    @pytest.mark.asyncio
    async def test_influxdb_write_failure_continues_execution(self):
        """Test that kill-switch continues even if InfluxDB writes fail."""
        mock_influx = AsyncMock()
        mock_influx.write_point = AsyncMock(
            side_effect=Exception("InfluxDB connection failed")
        )

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
            influxdb_client=mock_influx,
            config=KillSwitchConfig(
                require_reauthorization=False,
                log_to_influxdb=True,
            ),
        )

        result = await executor.execute_kill_switch(
            reason="test InfluxDB failure",
            triggered_by="test",
            environment="paper",
        )

        # Kill-switch should still execute successfully
        assert result.success is True
        assert result.positions_closed == 1

        # InfluxDB should have been called (and failed)
        assert mock_influx.write_point.call_count > 0

    @pytest.mark.asyncio
    async def test_influxdb_circuit_breaker_opens_after_failures(self):
        """Test InfluxDB circuit breaker opens after multiple failures."""
        executor = KillSwitchExecutor()
        breaker = executor._retry_handler.get_circuit_breaker("influxdb")

        # Simulate multiple failures
        for _ in range(3):
            await breaker.record_failure()

        # Circuit should be open
        can_execute = await breaker.can_execute()
        assert can_execute is False
        assert breaker.state.value == "open"

    @pytest.mark.asyncio
    async def test_influxdb_retry_with_backoff(self):
        """Test InfluxDB writes are retried with exponential backoff."""
        mock_influx = AsyncMock()
        # Fail twice, then succeed
        call_count = [0]

        async def mock_write(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Temporary error")

        mock_influx.write_point = mock_write

        executor = KillSwitchExecutor(
            influxdb_client=mock_influx,
            config=KillSwitchConfig(log_to_influxdb=True),
        )
        executor._state = KillSwitchState.TRIGGERED

        # Should succeed after retries
        result = await executor._write_state_to_influxdb_with_retry()
        assert result is True
        assert call_count[0] == 3  # 2 failures + 1 success

    # =================================================================
    # 7. Retry/Fallback Logic for Transient Failures
    # =================================================================

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        """Test retry logic uses exponential backoff."""
        from execution.kill_switch.retry_handler import _calculate_delay

        config = RetryConfig(
            max_attempts=5,
            base_delay_seconds=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
            max_delay_seconds=10.0,
        )

        # Check exponential delays
        delay1 = _calculate_delay(1, config)
        delay2 = _calculate_delay(2, config)
        delay3 = _calculate_delay(3, config)

        # Should be exponential: 1, 2, 4
        assert delay1 == 1.0
        assert delay2 == 2.0
        assert delay3 == 4.0

    @pytest.mark.asyncio
    async def test_retry_with_jitter(self):
        """Test retry logic uses jitter."""
        from execution.kill_switch.retry_handler import _calculate_delay

        config = RetryConfig(
            max_attempts=5,
            base_delay_seconds=1.0,
            strategy=RetryStrategy.EXPONENTIAL_JITTER,
        )

        # Check jitter delays are within expected range
        for attempt in range(1, 4):
            delay = _calculate_delay(attempt, config)
            exp_max = min(1.0 * (2 ** (attempt - 1)), config.max_delay_seconds)
            assert 0 <= delay <= exp_max

    @pytest.mark.asyncio
    async def test_retry_max_attempts_exceeded(self):
        """Test behavior when max retry attempts are exceeded."""
        mock_operation = AsyncMock()
        mock_operation.side_effect = Exception("Persistent failure")

        from execution.kill_switch.retry_handler import retry_with_backoff

        config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.1,  # Short delay for test
            retryable_exceptions=(Exception,),
        )

        with pytest.raises(Exception) as exc_info:
            await retry_with_backoff(
                mock_operation,
                config,
                "test_operation",
            )

        assert "Persistent failure" in str(exc_info.value)
        assert mock_operation.call_count == 3

    # =================================================================
    # 8. State Machine Edge Cases
    # =================================================================

    @pytest.mark.asyncio
    async def test_state_machine_disabled_to_disabled(self):
        """Test staying in disabled state."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.DISABLED

        # Try to trigger
        result = await executor.execute_kill_switch("test")

        assert result.success is False
        assert result.metadata["error"] == "kill_switch_disabled"
        assert executor.state == KillSwitchState.DISABLED

    @pytest.mark.asyncio
    async def test_state_machine_triggered_to_triggered(self):
        """Test staying in triggered state."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.TRIGGERED

        # Try to trigger again
        result = await executor.execute_kill_switch("test")

        assert result.success is False
        assert result.metadata["error"] == "already_triggered"
        assert executor.state == KillSwitchState.TRIGGERED

    @pytest.mark.asyncio
    async def test_reauthorization_clears_trigger_state(self):
        """Test reauthorization properly clears trigger state."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.TRIGGERED
        executor._triggered_at = datetime.now(UTC)
        executor._triggered_by = "test"

        # Reauthorize
        result = await executor.reauthorize("packet123")

        assert result is True
        assert executor.state == KillSwitchState.ARMED
        assert executor._reauthorized_by == "packet123"
        assert executor._reauthorized_at is not None

    @pytest.mark.asyncio
    async def test_arm_from_triggered_blocked(self):
        """Test arming from triggered state is blocked."""
        executor = KillSwitchExecutor()
        executor._state = KillSwitchState.TRIGGERED

        result = await executor.arm()

        assert result is False
        assert executor.state == KillSwitchState.TRIGGERED

    # =================================================================
    # 9. Drawdown Monitor Edge Cases
    # =================================================================

    @pytest.mark.asyncio
    async def test_drawdown_monitor_exception_handled(self):
        """Test drawdown monitor exceptions don't block kill-switch."""
        mock_monitor = MagicMock()
        mock_monitor.calculate_rolling_drawdown = MagicMock(
            side_effect=Exception("Monitor error")
        )

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
            reason="test monitor exception",
            triggered_by="test",
            environment="paper",
        )

        # Should succeed even if drawdown monitor failed
        assert result.success is True
        # Drawdown should be 0 since monitor failed
        assert result.metadata.get("drawdown_pct", 0.0) == 0.0

    # =================================================================
    # 10. Comprehensive Integration Tests
    # =================================================================

    @pytest.mark.asyncio
    async def test_full_kill_switch_with_multiple_failures(self):
        """Integration test with multiple edge cases."""
        # Setup multiple positions with mixed success/failure
        mock_bybit = AsyncMock()
        call_count = [0]

        async def mock_close(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"order_id": "1", "price": 50000.0, "quantity": 1.0}
            elif call_count[0] == 2:
                raise Exception("API error")
            else:
                return {"order_id": "3", "price": 100.0, "quantity": 10.0}

        mock_bybit.close_position_market = mock_close

        # Position tracker that fails for one position
        mock_tracker = MagicMock()
        mock_tracker.state = MagicMock()
        mock_tracker.state.positions = {
            "pos1": MockPosition("pos1", "BTCUSDT", "long", 1.0, 48000.0),
            "pos2": MockPosition("pos2", "ETHUSDT", "short", 5.0, 3000.0),
            "pos3": MockPosition("pos3", "SOLUSDT", "long", 10.0, 100.0),
        }

        close_count = [0]

        async def mock_tracker_close(*args, **kwargs):
            close_count[0] += 1
            if close_count[0] == 2:
                raise Exception("Tracker error")
            return 100.0

        mock_tracker.close_position = mock_tracker_close

        # InfluxDB that fails
        mock_influx = AsyncMock()
        mock_influx.write_point = AsyncMock(side_effect=Exception("InfluxDB down"))

        executor = KillSwitchExecutor(
            bybit_connector=mock_bybit,
            position_tracker=mock_tracker,
            influxdb_client=mock_influx,
            config=KillSwitchConfig(
                require_reauthorization=False,
                log_to_influxdb=True,
                max_close_retries=1,
            ),
        )

        result = await executor.execute_kill_switch(
            reason="integration test",
            triggered_by="test",
            environment="paper",
        )

        # Should succeed despite multiple failures
        assert result.success is True
        assert result.positions_closed == 2  # 2 succeeded, 1 failed
        assert result.metadata["positions_failed"] == 1
        assert result.metadata["has_partial_failures"] is True
        assert executor.state == KillSwitchState.TRIGGERED


class TestRetryHandlerEdgeCases:
    """Test retry handler edge cases."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_state(self):
        """Test circuit breaker half-open state."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig())

        # Open the circuit
        for _ in range(5):
            await breaker.record_failure()

        assert breaker.state.value == "open"

        # Manually transition to half-open for testing
        breaker._state = type(breaker.state)("half_open")  # type: ignore
        breaker._half_open_calls = 0

        # Should allow limited calls in half-open
        assert await breaker.can_execute() is True
        assert await breaker.can_execute() is True
        assert await breaker.can_execute() is True
        # Should block after max calls
        assert await breaker.can_execute() is False

    @pytest.mark.asyncio
    async def test_retry_handler_nonexistent_circuit_breaker(self):
        """Test retry handler with non-existent circuit breaker."""
        handler = RetryHandler()

        mock_operation = AsyncMock(return_value="success")

        # Should work without circuit breaker
        result = await handler.execute_with_retry(
            "nonexistent",
            mock_operation,
            RetryConfig(max_attempts=2),
        )

        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_handler_circuit_open_error(self):
        """Test retry handler raises CircuitBreakerOpenError."""
        handler = RetryHandler()
        handler.register_circuit_breaker("test", CircuitBreakerConfig())

        breaker = handler.get_circuit_breaker("test")
        for _ in range(5):
            await breaker.record_failure()

        mock_operation = AsyncMock()

        with pytest.raises(CircuitBreakerOpenError):
            await handler.execute_with_retry(
                "test",
                mock_operation,
                RetryConfig(),
            )
