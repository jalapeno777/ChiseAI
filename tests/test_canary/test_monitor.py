"""Tests for canary monitor."""

import asyncio
import pytest

from execution.canary.models import (
    CanaryDeployment,
    CanaryStatus,
    GateCheckResult,
    create_canary_deployment,
)
from execution.canary.monitor import (
    CanaryMonitor,
    MonitoringCheck,
    create_canary_monitor,
)
from execution.canary.rollback import RollbackResult


class TestMonitoringCheck:
    """Test MonitoringCheck class."""

    def test_to_dict(self):
        """Test serialization to dict."""
        check = MonitoringCheck(
            canary_id="test-001",
            timestamp=1609459200,
            gate_checks=[],
            status=CanaryStatus.RUNNING,
            action_taken="continue",
            message="All good",
        )

        data = check.to_dict()
        assert data["canary_id"] == "test-001"
        assert data["timestamp"] == 1609459200
        assert data["status"] == "running"
        assert data["action_taken"] == "continue"
        assert data["message"] == "All good"


class TestCanaryMonitor:
    """Test CanaryMonitor class."""

    def test_default_interval(self):
        """Test default check interval."""
        monitor = CanaryMonitor()
        assert monitor.check_interval_minutes == 15

    def test_custom_interval(self):
        """Test custom check interval."""
        monitor = CanaryMonitor(check_interval_minutes=5)
        assert monitor.check_interval_minutes == 5

    def test_register_canary(self):
        """Test registering a canary."""
        monitor = CanaryMonitor()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )

        monitor.register_canary(canary)
        assert "test-001" in monitor._monitored_canaries

    def test_unregister_canary(self):
        """Test unregistering a canary."""
        monitor = CanaryMonitor()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )

        monitor.register_canary(canary)
        unregistered = monitor.unregister_canary("test-001")

        assert unregistered == canary
        assert "test-001" not in monitor._monitored_canaries

    def test_unregister_nonexistent(self):
        """Test unregistering a non-existent canary."""
        monitor = CanaryMonitor()
        unregistered = monitor.unregister_canary("nonexistent")
        assert unregistered is None

    @pytest.mark.asyncio
    async def test_run_check_running_canary(self):
        """Test running a check on a running canary."""
        monitor = CanaryMonitor()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)

        monitor.register_canary(canary)
        result = await monitor.run_check(canary)

        assert result.canary_id == "test-001"
        assert result.status == CanaryStatus.RUNNING
        assert result.action_taken == "continue"
        assert len(result.gate_checks) == 3

    @pytest.mark.asyncio
    async def test_run_check_with_rollback(self):
        """Test running a check that triggers rollback."""
        rollback_triggered = []

        def on_rollback(result):
            rollback_triggered.append(result)

        monitor = CanaryMonitor(on_rollback=on_rollback)
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.metrics.peak_equity = 10000.0
        canary.metrics.update_equity(9400.0)  # 6% drawdown - exceeds threshold

        monitor.register_canary(canary)
        result = await monitor.run_check(canary)

        assert result.action_taken == "rollback"
        assert canary.status == CanaryStatus.ROLLED_BACK
        assert len(rollback_triggered) == 1
        assert isinstance(rollback_triggered[0], RollbackResult)

    @pytest.mark.asyncio
    async def test_run_all_checks(self):
        """Test running checks on all monitored canaries."""
        monitor = CanaryMonitor()

        # Create and register multiple canaries
        for i in range(3):
            canary = create_canary_deployment(
                canary_id=f"test-{i:03d}",
                strategy_id=f"strategy-v{i}",
            )
            canary.start(initial_equity=10000.0)
            monitor.register_canary(canary)

        results = await monitor.run_all_checks()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_run_all_checks_skips_non_running(self):
        """Test that run_all_checks skips non-running canaries."""
        monitor = CanaryMonitor()

        # Running canary
        running = create_canary_deployment(
            canary_id="running",
            strategy_id="strategy-running",
        )
        running.start(initial_equity=10000.0)
        monitor.register_canary(running)

        # Pending canary (should be skipped)
        pending = create_canary_deployment(
            canary_id="pending",
            strategy_id="strategy-pending",
        )
        # Don't start - stays in PENDING status
        monitor.register_canary(pending)

        results = await monitor.run_all_checks()
        assert len(results) == 1  # Only the running canary

    def test_get_check_history(self):
        """Test getting check history."""
        monitor = CanaryMonitor()

        # Add some check history
        for i in range(5):
            check = MonitoringCheck(
                canary_id="test-001",
                timestamp=1609459200 + i * 3600,
                gate_checks=[],
                status=CanaryStatus.RUNNING,
                action_taken="continue",
                message="Check",
            )
            monitor._check_history.append(check)

        # Get all history
        history = monitor.get_check_history()
        assert len(history) == 5

        # Get history for specific canary
        history = monitor.get_check_history(canary_id="test-001")
        assert len(history) == 5

        # Get limited history
        history = monitor.get_check_history(limit=3)
        assert len(history) == 3

    def test_get_canary_status(self):
        """Test getting canary status."""
        monitor = CanaryMonitor()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)

        monitor.register_canary(canary)
        status = monitor.get_canary_status("test-001")

        assert status == CanaryStatus.RUNNING

    def test_get_canary_status_nonexistent(self):
        """Test getting status of non-existent canary."""
        monitor = CanaryMonitor()
        status = monitor.get_canary_status("nonexistent")
        assert status is None

    def test_clear_history(self):
        """Test clearing check history."""
        monitor = CanaryMonitor()
        check = MonitoringCheck(
            canary_id="test-001",
            timestamp=1609459200,
            gate_checks=[],
            status=CanaryStatus.RUNNING,
            action_taken="continue",
            message="Check",
        )
        monitor._check_history.append(check)

        assert len(monitor._check_history) == 1
        monitor.clear_history()
        assert len(monitor._check_history) == 0

    @pytest.mark.asyncio
    async def test_start_stop_monitor(self):
        """Test starting and stopping the monitor."""
        monitor = CanaryMonitor(check_interval_minutes=1)

        assert not monitor.is_running()

        await monitor.start()
        assert monitor.is_running()

        await monitor.stop()
        assert not monitor.is_running()

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test starting monitor when already running."""
        monitor = CanaryMonitor(check_interval_minutes=1)

        await monitor.start()
        assert monitor.is_running()

        # Try to start again - should not fail
        await monitor.start()
        assert monitor.is_running()

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_status_change_callback(self):
        """Test status change callback."""
        status_changes = []

        def on_status_change(canary, new_status):
            status_changes.append((canary.canary_id, new_status))

        monitor = CanaryMonitor(on_status_change=on_status_change)
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.metrics.peak_equity = 10000.0
        canary.metrics.update_equity(9400.0)  # Trigger rollback

        monitor.register_canary(canary)
        await monitor.run_check(canary)

        # Should have status change from RUNNING to ROLLED_BACK
        assert len(status_changes) >= 1


class TestCreateCanaryMonitor:
    """Test create_canary_monitor factory function."""

    def test_create_with_defaults(self):
        """Test creating monitor with defaults."""
        monitor = create_canary_monitor()
        assert isinstance(monitor, CanaryMonitor)
        assert monitor.check_interval_minutes == 15

    def test_create_with_custom_interval(self):
        """Test creating monitor with custom interval."""
        monitor = create_canary_monitor(check_interval_minutes=5)
        assert monitor.check_interval_minutes == 5
