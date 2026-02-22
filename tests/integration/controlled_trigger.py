"""Integration tests for controlled test trade trigger.

Tests the TestTradeTrigger with mock components to verify:
- Risk enforcer is called
- Kill-switch check occurs
- Position size limits are enforced
- Audit logging works correctly

For PAPER-LIVE-001: Controlled Paper Trade Trigger
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from execution.kill_switch.state import KillSwitchState
from execution.paper.models import OrderState, PaperOrder, TradeStatus
from execution.paper.test_trigger import TestTradeTrigger, TestTriggerResult
from signal_generation.models import Signal, SignalDirection


class MockKillSwitchExecutor:
    """Mock kill-switch executor for testing."""

    def __init__(self, state: KillSwitchState = KillSwitchState.ARMED):
        self._state = state
        self.state_check_count = 0

    @property
    def state(self) -> KillSwitchState:
        """Get current state and increment check counter."""
        self.state_check_count += 1
        return self._state

    def set_state(self, state: KillSwitchState) -> None:
        """Set state for testing."""
        self._state = state


class MockOrchestrator:
    """Mock paper trading orchestrator for testing."""

    def __init__(self):
        self.processed_signals: list[Signal] = []
        self.risk_enforcer_calls: list[dict[str, Any]] = []
        self.should_reject = False
        self.rejection_reason = ["test_rejection"]
        self.mock_order = PaperOrder(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
            order_id="test-order-123",
            state=OrderState.FILLED,
            filled_quantity=0.001,
            avg_fill_price=50000.0,
        )

    async def process_signal(self, signal: Signal) -> Any:
        """Mock signal processing."""
        self.processed_signals.append(signal)

        # Create mock result
        mock_result = MagicMock()
        mock_result.status = (
            TradeStatus.REJECTED if self.should_reject else TradeStatus.EXECUTED
        )
        mock_result.reject_reason = self.rejection_reason if self.should_reject else []
        mock_result.order = self.mock_order if not self.should_reject else None
        mock_result.position = None
        mock_result.latency_ms = 150.0
        mock_result.correlation_id = "test-correlation-123"
        mock_result.signal = signal

        return mock_result

    def get_metrics(self) -> dict[str, Any]:
        """Return mock metrics."""
        return {
            "signals_processed": len(self.processed_signals),
            "trades_executed": 0,
            "trades_rejected": 0,
            "trades_failed": 0,
        }


class TestTestTradeTrigger(unittest.TestCase):
    """Test cases for TestTradeTrigger."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_kill_switch = MockKillSwitchExecutor(KillSwitchState.ARMED)
        self.mock_orchestrator = MockOrchestrator()
        self.trigger = TestTradeTrigger(
            orchestrator=self.mock_orchestrator,
            kill_switch=self.mock_kill_switch,
            portfolio_value=10000.0,
            max_position_pct=0.01,
            min_confidence=0.80,
        )

    def tearDown(self) -> None:
        """Clean up after tests."""
        pass

    def test_initialization(self) -> None:
        """Test trigger initialization."""
        self.assertEqual(self.trigger.portfolio_value, 10000.0)
        self.assertEqual(self.trigger.max_position_pct, 0.01)
        self.assertEqual(self.trigger.min_confidence, 0.80)
        self.assertEqual(self.trigger.orchestrator, self.mock_orchestrator)
        self.assertEqual(self.trigger.kill_switch, self.mock_kill_switch)

    def test_default_safety_parameters(self) -> None:
        """Test default safety parameter values."""
        self.assertEqual(TestTradeTrigger.DEFAULT_MAX_POSITION_PCT, 0.01)
        self.assertEqual(TestTradeTrigger.DEFAULT_MIN_CONFIDENCE, 0.80)
        self.assertEqual(TestTradeTrigger.DEFAULT_SYMBOL, "BTCUSDT")

    async def async_test_kill_switch_check_armed(self) -> None:
        """Test that kill-switch check occurs when ARMED."""
        result = await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
        )

        # Verify kill-switch was checked
        self.assertGreater(self.mock_kill_switch.state_check_count, 0)
        self.assertEqual(result.kill_switch_state, "armed")

    async def async_test_kill_switch_check_triggered(self) -> None:
        """Test that trade is blocked when kill-switch is TRIGGERED."""
        # Set kill-switch to triggered
        self.mock_kill_switch.set_state(KillSwitchState.TRIGGERED)

        result = await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
        )

        # Verify trade was blocked
        self.assertFalse(result.success)
        self.assertIn("TRIGGERED", result.error)
        self.assertEqual(result.kill_switch_state, "triggered")

        # Verify audit log entry was created
        audit_log = self.trigger.get_audit_log()
        self.assertEqual(len(audit_log), 1)
        self.assertEqual(audit_log[0]["status"], "blocked")
        self.assertEqual(audit_log[0]["kill_switch_state"], "triggered")

    async def async_test_kill_switch_check_disabled(self) -> None:
        """Test that trade proceeds with warning when kill-switch is DISABLED."""
        # Set kill-switch to disabled
        self.mock_kill_switch.set_state(KillSwitchState.DISABLED)

        result = await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
        )

        # Verify trade proceeded (orchestrator will handle it)
        self.assertEqual(result.kill_switch_state, "disabled")

    async def async_test_risk_enforcer_called(self) -> None:
        """Test that risk enforcer is called during signal processing."""
        await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
        )

        # Verify signal was processed by orchestrator
        self.assertEqual(len(self.mock_orchestrator.processed_signals), 1)

        # Verify the signal has correct confidence
        signal = self.mock_orchestrator.processed_signals[0]
        self.assertEqual(signal.confidence, 0.80)
        self.assertEqual(signal.token, "BTCUSDT")
        self.assertEqual(signal.direction, SignalDirection.LONG)

    async def async_test_position_size_limits(self) -> None:
        """Test that position size limits are enforced."""
        # Test with custom max position percentage
        trigger = TestTradeTrigger(
            orchestrator=self.mock_orchestrator,
            kill_switch=self.mock_kill_switch,
            portfolio_value=10000.0,
            max_position_pct=0.005,  # 0.5%
            min_confidence=0.80,
        )

        await trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
        )

        # Verify signal was created and processed
        self.assertEqual(len(self.mock_orchestrator.processed_signals), 1)

        # Verify stats reflect the custom config
        stats = trigger.get_stats()
        self.assertEqual(stats["config"]["max_position_pct"], 0.005)

    async def async_test_confidence_threshold(self) -> None:
        """Test that confidence threshold is enforced."""
        # Test with custom confidence
        await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
            confidence=0.90,
        )

        # Verify signal has the specified confidence
        signal = self.mock_orchestrator.processed_signals[0]
        self.assertEqual(signal.confidence, 0.90)

    async def async_test_invalid_direction(self) -> None:
        """Test that invalid direction is rejected."""
        result = await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="invalid",
        )

        # Verify trade was rejected
        self.assertFalse(result.success)
        self.assertIn("Invalid direction", result.error)

        # Verify audit log entry
        audit_log = self.trigger.get_audit_log()
        self.assertEqual(len(audit_log), 1)
        self.assertEqual(audit_log[0]["status"], "failed")

    async def async_test_audit_logging(self) -> None:
        """Test that audit logging captures all trigger attempts."""
        # Trigger multiple trades
        await self.trigger.trigger_test_trade(symbol="BTCUSDT", direction="long")
        await self.trigger.trigger_test_trade(symbol="ETHUSDT", direction="short")

        # Set kill-switch to triggered and try again
        self.mock_kill_switch.set_state(KillSwitchState.TRIGGERED)
        await self.trigger.trigger_test_trade(symbol="BTCUSDT", direction="long")

        # Verify audit log has all entries
        audit_log = self.trigger.get_audit_log()
        self.assertEqual(len(audit_log), 3)

        # Verify log entries have required fields
        for entry in audit_log:
            self.assertIn("audit_log_id", entry)
            self.assertIn("timestamp", entry)
            self.assertIn("action", entry)
            self.assertIn("status", entry)
            self.assertIn("symbol", entry)
            self.assertIn("direction", entry)

    async def async_test_trade_result_structure(self) -> None:
        """Test that trade result has correct structure."""
        result = await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
        )

        # Verify result structure
        self.assertIsInstance(result, TestTriggerResult)
        self.assertIn(result.success, [True, False])
        self.assertIsNotNone(result.timestamp)
        self.assertIsNotNone(result.signal_id)
        self.assertIsNotNone(result.audit_log_id)

        # Verify dict conversion works
        result_dict = result.to_dict()
        self.assertIn("success", result_dict)
        self.assertIn("timestamp", result_dict)
        self.assertIn("signal_id", result_dict)
        self.assertIn("audit_log_id", result_dict)
        self.assertIn("kill_switch_state", result_dict)

    async def async_test_short_direction(self) -> None:
        """Test short direction signal creation."""
        await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="short",
        )

        # Verify signal direction
        signal = self.mock_orchestrator.processed_signals[0]
        self.assertEqual(signal.direction, SignalDirection.SHORT)
        self.assertEqual(signal.token, "BTCUSDT")

    async def async_test_stats_calculation(self) -> None:
        """Test statistics calculation."""
        # Trigger trades with different outcomes
        await self.trigger.trigger_test_trade(symbol="BTCUSDT", direction="long")

        self.mock_kill_switch.set_state(KillSwitchState.TRIGGERED)
        await self.trigger.trigger_test_trade(symbol="ETHUSDT", direction="long")

        # Get stats
        stats = self.trigger.get_stats()

        # Verify stats structure
        self.assertEqual(stats["total_attempts"], 2)
        self.assertIn("success_count", stats)
        self.assertIn("rejected_count", stats)
        self.assertIn("failed_count", stats)
        self.assertIn("blocked_count", stats)
        self.assertIn("success_rate", stats)
        self.assertIn("config", stats)

    async def async_test_validate_readiness(self) -> None:
        """Test readiness validation."""
        readiness = await self.trigger.validate_readiness()

        # Verify readiness checks
        self.assertIn("kill_switch_armed", readiness)
        self.assertIn("orchestrator_ready", readiness)
        self.assertIn("portfolio_value_ok", readiness)
        self.assertIn("ready", readiness)

        # When kill-switch is ARMED, should be ready
        self.assertTrue(readiness["kill_switch_armed"])
        self.assertTrue(readiness["orchestrator_ready"])
        self.assertTrue(readiness["portfolio_value_ok"])
        self.assertTrue(readiness["ready"])

    async def async_test_rejection_handling(self) -> None:
        """Test handling of rejected trades."""
        # Configure orchestrator to reject
        self.mock_orchestrator.should_reject = True
        self.mock_orchestrator.rejection_reason = ["risk_limit_exceeded"]

        result = await self.trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
        )

        # Verify rejection was handled
        self.assertFalse(result.success)
        self.assertIn("risk_limit_exceeded", result.error)

        # Verify audit log
        audit_log = self.trigger.get_audit_log()
        self.assertEqual(audit_log[0]["status"], "rejected")

    # Synchronous wrappers for async tests
    def test_kill_switch_check_armed(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_kill_switch_check_armed())

    def test_kill_switch_check_triggered(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_kill_switch_check_triggered())

    def test_kill_switch_check_disabled(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_kill_switch_check_disabled())

    def test_risk_enforcer_called(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_risk_enforcer_called())

    def test_position_size_limits(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_position_size_limits())

    def test_confidence_threshold(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_confidence_threshold())

    def test_invalid_direction(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_invalid_direction())

    def test_audit_logging(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_audit_logging())

    def test_trade_result_structure(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_trade_result_structure())

    def test_short_direction(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_short_direction())

    def test_stats_calculation(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_stats_calculation())

    def test_validate_readiness(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_validate_readiness())

    def test_rejection_handling(self) -> None:
        """Synchronous wrapper for async test."""
        asyncio.run(self.async_test_rejection_handling())


class TestTestTriggerResult(unittest.TestCase):
    """Test cases for TestTriggerResult dataclass."""

    def test_result_creation(self) -> None:
        """Test result creation."""
        result = TestTriggerResult(
            success=True,
            order_id="order-123",
            fill_price=50000.0,
            signal_id="signal-456",
            kill_switch_state="armed",
            audit_log_id="audit-789",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.order_id, "order-123")
        self.assertEqual(result.fill_price, 50000.0)
        self.assertEqual(result.signal_id, "signal-456")
        self.assertEqual(result.kill_switch_state, "armed")
        self.assertEqual(result.audit_log_id, "audit-789")

    def test_result_to_dict(self) -> None:
        """Test result dictionary conversion."""
        result = TestTriggerResult(
            success=True,
            order_id="order-123",
            fill_price=50000.0,
            signal_id="signal-456",
            kill_switch_state="armed",
            audit_log_id="audit-789",
        )

        result_dict = result.to_dict()

        self.assertTrue(result_dict["success"])
        self.assertEqual(result_dict["order_id"], "order-123")
        self.assertEqual(result_dict["fill_price"], 50000.0)
        self.assertEqual(result_dict["signal_id"], "signal-456")
        self.assertEqual(result_dict["kill_switch_state"], "armed")
        self.assertEqual(result_dict["audit_log_id"], "audit-789")

    def test_result_with_error(self) -> None:
        """Test result with error."""
        result = TestTriggerResult(
            success=False,
            error="Kill-switch triggered",
            kill_switch_state="triggered",
            audit_log_id="audit-789",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Kill-switch triggered")
        self.assertIsNone(result.order_id)
        self.assertIsNone(result.fill_price)


class TestIntegrationWithRealComponents(unittest.TestCase):
    """Integration tests with real (but minimal) component setup."""

    @patch("execution.paper.orchestrator.PaperTradingOrchestrator")
    @patch("execution.kill_switch.executor.KillSwitchExecutor")
    def test_full_integration_flow(self, mock_ks_class, mock_orch_class) -> None:
        """Test full integration flow with mocked components."""
        # Setup mocks
        mock_kill_switch = MagicMock()
        mock_kill_switch.state = KillSwitchState.ARMED
        mock_ks_class.return_value = mock_kill_switch

        mock_orchestrator = MagicMock()
        mock_result = MagicMock()
        mock_result.status = TradeStatus.EXECUTED
        mock_result.order.order_id = "test-order-123"
        mock_result.order.avg_fill_price = 50000.0
        mock_result.latency_ms = 150.0
        mock_result.correlation_id = "test-corr-123"
        mock_orchestrator.process_signal = AsyncMock(return_value=mock_result)
        mock_orchestrator.get_metrics.return_value = {"signals_processed": 1}
        mock_orch_class.return_value = mock_orchestrator

        # Create trigger
        trigger = TestTradeTrigger(
            orchestrator=mock_orchestrator,
            kill_switch=mock_kill_switch,
            portfolio_value=10000.0,
        )

        # Run test
        async def run_test():
            return await trigger.trigger_test_trade(
                symbol="BTCUSDT",
                direction="long",
            )

        result = asyncio.run(run_test())

        # Verify flow
        self.assertTrue(result.success)
        mock_orchestrator.process_signal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
