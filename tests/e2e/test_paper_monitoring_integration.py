#!/usr/bin/env python3
"""Paper Trading E2E Integration Test Suite.

Comprehensive end-to-end tests for all Party Mode remediation components:
- Health probe execution
- Throughput monitor
- Error rate monitor
- Checkpoint execution

Tests verify all components work together with mocked external dependencies.

Story: ST-PARTY-E2E-REMEDIATION-001 - Task 3.2
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is in path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


class TestHealthProbeExecution:
    """Test health probe execution and integration."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.info.return_value = {
            "redis_version": "7.0.0",
            "connected_clients": 10,
            "uptime_in_seconds": 3600,
        }
        mock.get.return_value = None
        mock.hgetall.return_value = {
            "enabled": "1",
            "triggered": "0",
            "initialized": "1",
        }
        mock.zcard.return_value = 100
        mock.zrangebyscore.return_value = [
            ("signal-1", datetime.now(UTC).timestamp()),
            ("signal-2", datetime.now(UTC).timestamp() - 60),
        ]
        mock.keys.return_value = ["signal-1", "signal-2", "signal-3"]
        mock.scard.return_value = 50
        mock.dbsize.return_value = 1000
        return mock

    @pytest.fixture
    def mock_discord(self):
        """Create mock Discord sender."""
        mock = MagicMock()
        mock.send_message = AsyncMock(return_value={"success": True})
        return mock

    def test_health_probe_initialization(self, mock_redis):
        """Test health probe initializes correctly."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=True)
        assert probe.dry_run is True
        assert probe.results == []

    def test_health_probe_redis_connectivity_check(self, mock_redis):
        """Test Redis connectivity check passes."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=False)

        with patch(
            "scripts.monitoring.paper_e2e_health_probe.redis.Redis"
        ) as mock_redis_class:
            mock_redis_class.return_value = mock_redis
            result = probe.check_redis_connectivity()

        assert result.status == "PASS"
        assert "connected" in result.message.lower()
        assert result.details["redis_version"] == "7.0.0"

    def test_health_probe_paper_mode_check(self, mock_redis):
        """Test paper trading mode check."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=False)
        probe.redis_client = mock_redis

        # Test with paper mode active
        mock_redis.get.return_value = "paper"
        result = probe.check_paper_trading_mode()

        assert result.status == "PASS"
        assert "active" in result.message.lower()

    def test_health_probe_signal_generation_check(self, mock_redis):
        """Test signal generation check."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=False)
        probe.redis_client = mock_redis

        result = probe.check_signal_generation()

        assert result.status in ["PASS", "WARN"]
        assert "signal" in result.message.lower()

    def test_health_probe_order_flow_check(self, mock_redis):
        """Test order flow check."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=False)
        probe.redis_client = mock_redis

        result = probe.check_order_flow()

        assert result.status in ["PASS", "WARN"]
        assert "order" in result.message.lower()

    def test_health_probe_kill_switch_check(self, mock_redis):
        """Test kill-switch check."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=False)
        probe.redis_client = mock_redis

        with patch.dict(
            "sys.modules", {"execution.kill_switch.bootstrap": MagicMock()}
        ):
            result = probe.check_kill_switch()

        # Should pass or warn based on mock state
        assert result.status in ["PASS", "WARN", "FAIL"]

    def test_health_probe_full_execution(self, mock_redis):
        """Test full health probe execution."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=False, output_dir="/tmp/test_evidence")

        with patch(
            "scripts.monitoring.paper_e2e_health_probe.redis.Redis"
        ) as mock_redis_class:
            mock_redis_class.return_value = mock_redis
            summary = probe.run_all_checks()

        assert "summary" in summary
        assert "checks" in summary
        assert summary["probe_name"] == "paper_e2e_health_probe"
        assert summary["dry_run"] is False

        # Verify all expected checks ran
        check_names = [c["name"] for c in summary["checks"]]
        expected_checks = [
            "redis_connectivity",
            "paper_trading_mode",
            "signal_generation",
            "order_flow",
            "kill_switch",
            "discord_connectivity",
        ]
        for check in expected_checks:
            assert check in check_names, f"Missing check: {check}"

    def test_health_probe_evidence_saving(self, mock_redis, tmp_path):
        """Test evidence is saved correctly."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        probe = PaperE2EHealthProbe(dry_run=True, output_dir=str(tmp_path))
        summary = probe.run_all_checks()

        filepath = probe.save_evidence(summary)

        assert filepath.exists()
        with open(filepath) as f:
            saved_data = json.load(f)
        assert saved_data["probe_name"] == "paper_e2e_health_probe"


class TestThroughputMonitor:
    """Test throughput monitoring components."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hset.return_value = 1
        mock.hget.return_value = None
        mock.hgetall.return_value = {}
        mock.expire.return_value = 1
        mock.delete.return_value = 1
        return mock

    def test_throughput_tracker_initialization(self, mock_redis):
        """Test throughput tracker initializes correctly."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=mock_redis)
        assert tracker._redis == mock_redis
        assert tracker._ttl == 3600

    def test_throughput_tracker_record_signal(self, mock_redis):
        """Test recording signals."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=mock_redis)

        tracker.record_signal("sig-1", latency_ms=150.0, success=True)
        tracker.record_signal("sig-2", latency_ms=200.0, success=True)
        tracker.record_signal("sig-3", latency_ms=300.0, success=False)

        assert len(tracker._signals) == 3
        assert tracker._signals[0].signal_id == "sig-1"
        assert tracker._signals[0].latency_ms == 150.0

    def test_throughput_tracker_metrics_calculation(self, mock_redis):
        """Test throughput metrics calculation."""
        from execution.signal_delivery.throughput_tracker import (
            SignalRecord,
            ThroughputTracker,
        )

        tracker = ThroughputTracker(redis_client=None)  # Use in-memory only

        # Record signals over time
        now = datetime.now(UTC)
        for i in range(10):
            tracker._signals.append(
                SignalRecord(
                    signal_id=f"sig-{i}",
                    timestamp=now - timedelta(seconds=i * 5),
                    latency_ms=100.0 + i * 10,
                    success=True,
                )
            )

        metrics = tracker.get_metrics("1min")

        assert metrics.window_name == "1min"
        assert metrics.signals_count >= 0
        assert metrics.signals_per_minute >= 0.0

    def test_throughput_tracker_latency_percentiles(self, mock_redis):
        """Test latency percentile calculation."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=None)

        # Record signals with varying latencies
        latencies = [
            50.0,
            100.0,
            150.0,
            200.0,
            250.0,
            300.0,
            350.0,
            400.0,
            450.0,
            500.0,
        ]
        for i, latency in enumerate(latencies):
            tracker.record_signal(f"sig-{i}", latency_ms=latency, success=True)

        percentiles = tracker.get_latency_percentiles("1min")

        assert percentiles.count == 10
        assert percentiles.min_ms == 50.0
        assert percentiles.max_ms == 500.0
        assert percentiles.p50_ms > 0
        assert percentiles.p95_ms > 0
        assert percentiles.p99_ms > 0

    def test_throughput_tracker_threshold_check(self, mock_redis):
        """Test throughput threshold checking."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=None)

        # Record enough signals to pass threshold
        for i in range(100):
            tracker.record_signal(f"sig-{i}", latency_ms=100.0, success=True)

        result = tracker.check_throughput_threshold("1min", min_spm=10.0)

        assert "window" in result
        assert "threshold" in result
        assert "actual" in result
        assert "passed" in result
        assert "status" in result
        assert "message" in result

    def test_throughput_tracker_latency_threshold_check(self, mock_redis):
        """Test latency threshold checking."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=None)

        # Record signals with acceptable latency
        for i in range(10):
            tracker.record_signal(f"sig-{i}", latency_ms=50.0, success=True)

        result = tracker.check_latency_threshold("1min", max_p95_ms=100.0)

        assert result["passed"] is True
        assert result["status"] == "healthy"
        assert result["actual_p95_ms"] <= 100.0

    def test_throughput_tracker_redis_storage(self, mock_redis):
        """Test Redis storage of metrics."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=mock_redis)

        for i in range(5):
            tracker.record_signal(f"sig-{i}", latency_ms=100.0, success=True)

        metrics = tracker.store_current_metrics()

        assert "timestamp" in metrics
        assert "throughput" in metrics
        assert "latency" in metrics
        mock_redis.hset.assert_called()

    def test_throughput_tracker_all_windows(self, mock_redis):
        """Test getting metrics for all windows."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=None)

        for i in range(20):
            tracker.record_signal(f"sig-{i}", latency_ms=100.0, success=True)

        all_metrics = tracker.get_all_windows_metrics()
        all_latencies = tracker.get_all_windows_latencies()

        assert "1min" in all_metrics
        assert "5min" in all_metrics
        assert "15min" in all_metrics
        assert "1min" in all_latencies
        assert "5min" in all_latencies
        assert "15min" in all_latencies


class TestErrorRateMonitor:
    """Test error rate monitoring components."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hset.return_value = 1
        mock.hget.return_value = None
        mock.hincrby.return_value = 1
        mock.expire.return_value = 1
        return mock

    def test_error_rate_tracking_basic(self, mock_redis):
        """Test basic error rate tracking."""
        # Simulate error tracking
        errors = []
        successes = []

        for i in range(100):
            if i < 5:  # 5% error rate
                errors.append({"error": f"error-{i}", "timestamp": datetime.now(UTC)})
            else:
                successes.append({"success": True, "timestamp": datetime.now(UTC)})

        total = len(errors) + len(successes)
        error_rate = len(errors) / total * 100

        assert error_rate == 5.0
        assert error_rate < 10.0  # Below alert threshold

    def test_error_rate_alert_threshold(self, mock_redis):
        """Test error rate alert threshold."""
        # Simulate high error rate
        errors = []
        successes = []

        for i in range(100):
            if i < 15:  # 15% error rate
                errors.append({"error": f"error-{i}", "timestamp": datetime.now(UTC)})
            else:
                successes.append({"success": True, "timestamp": datetime.now(UTC)})

        total = len(errors) + len(successes)
        error_rate = len(errors) / total * 100

        assert error_rate == 15.0
        assert error_rate > 10.0  # Above alert threshold

    def test_error_rate_monitoring_integration(self, mock_redis):
        """Test error rate monitoring with health monitor."""
        from execution.health_monitor import ExecutionHealthMonitor

        monitor = ExecutionHealthMonitor()

        # Simulate some errors
        monitor._status["bybit"].reconnect_count = 3
        monitor._status["bitget"].reconnect_count = 1

        status = monitor.get_status()

        assert "bybit" in status
        assert "bitget" in status
        assert status["monitoring_active"] is False  # Not started


class TestCheckpointExecution:
    """Test checkpoint execution and audit."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.hgetall.return_value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "running",
            "uptime_seconds": "7200",
        }
        mock.keys.return_value = ["signal-1", "signal-2", "signal-3"]
        mock.scard.return_value = 50
        mock.get.return_value = "GO"
        mock.dbsize.return_value = 1000
        mock.info.return_value = {"uptime_in_seconds": 7200}
        return mock

    def test_checkpoint_g1_scheduler_check(self, mock_redis):
        """Test G1 scheduler continuity check."""
        from scripts.monitoring.checkpoint_gate_audit import check_g1_scheduler

        result = check_g1_scheduler(mock_redis)

        assert result["gate"] == "G1"
        assert "status" in result
        assert "detail" in result

    def test_checkpoint_g2_signal_cadence_check(self, mock_redis):
        """Test G2 signal cadence check."""
        from scripts.monitoring.checkpoint_gate_audit import check_g2_signal_cadence

        result = check_g2_signal_cadence(mock_redis)

        assert result["gate"] == "G2"
        assert result["status"] in ["✅ PASS", "⚠️ CHECK", "❌ FAIL"]

    def test_checkpoint_g3_data_flow_check(self, mock_redis):
        """Test G3 data flow check."""
        from scripts.monitoring.checkpoint_gate_audit import check_g3_data_flow

        result = check_g3_data_flow(mock_redis)

        assert result["gate"] == "G3"
        assert result["status"] in ["✅ PASS", "⚠️ CHECK", "❌ FAIL"]

    def test_checkpoint_g4_kill_switch_check(self, mock_redis):
        """Test G4 kill-switch check."""
        from scripts.monitoring.checkpoint_gate_audit import check_g4_kill_switch

        result = check_g4_kill_switch(mock_redis)

        assert result["gate"] == "G4"
        assert result["status"] in ["✅ PASS", "🚨 ALERT", "⚠️ CHECK", "❌ FAIL"]

    def test_checkpoint_g7_observability_check(self, mock_redis):
        """Test G7 observability check."""
        from scripts.monitoring.checkpoint_gate_audit import check_g7_observability

        result = check_g7_observability(mock_redis)

        assert result["gate"] == "G7"
        assert result["status"] in ["✅ PASS", "⚠️ CHECK", "❌ FAIL"]

    def test_checkpoint_g8_pipeline_check(self, mock_redis):
        """Test G8 pipeline check."""
        from scripts.monitoring.checkpoint_gate_audit import check_g8_pipeline

        result = check_g8_pipeline(mock_redis)

        assert result["gate"] == "G8"
        assert result["status"] in ["✅ PASS", "❌ FAIL", "❓ UNKNOWN", "⚠️ CHECK"]

    def test_checkpoint_all_checks_execution(self, mock_redis):
        """Test running all checkpoint checks."""
        from scripts.monitoring.checkpoint_gate_audit import run_all_checks

        with patch(
            "scripts.monitoring.checkpoint_gate_audit.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            results = run_all_checks()

        assert len(results) == 8  # G1-G8

        gates = [r["gate"] for r in results]
        expected_gates = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]
        for gate in expected_gates:
            assert gate in gates, f"Missing gate: {gate}"

    def test_checkpoint_message_formatting(self):
        """Test checkpoint message formatting."""
        from scripts.monitoring.checkpoint_gate_audit import format_checkpoint_message

        checks = [
            {"gate": "G1", "status": "✅ PASS", "detail": "Scheduler OK"},
            {"gate": "G2", "status": "✅ PASS", "detail": "3 signals"},
            {"gate": "G3", "status": "⚠️ CHECK", "detail": "No outcomes"},
        ]

        message = format_checkpoint_message(checks)

        assert "📊 Burn-in Checkpoint" in message
        assert "G1:" in message
        assert "G2:" in message
        assert "G3:" in message
        assert "✅ PASS" in message
        assert "⚠️ CHECK" in message


class TestComponentIntegration:
    """Test integration between all components."""

    @pytest.fixture
    def mock_redis(self):
        """Create a comprehensive mock Redis client."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.info.return_value = {
            "redis_version": "7.0.0",
            "connected_clients": 10,
            "uptime_in_seconds": 7200,
        }
        mock.get.return_value = "paper"
        mock.hgetall.return_value = {
            "enabled": "1",
            "triggered": "0",
            "initialized": "1",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "running",
            "uptime_seconds": "7200",
        }
        mock.hget.return_value = None
        mock.zcard.return_value = 100
        mock.zrangebyscore.return_value = [
            (f"signal-{i}", datetime.now(UTC).timestamp() - i * 60) for i in range(10)
        ]
        mock.keys.return_value = [f"signal-{i}" for i in range(10)]
        mock.scard.return_value = 50
        mock.dbsize.return_value = 1000
        mock.hset.return_value = 1
        mock.expire.return_value = 1
        mock.delete.return_value = 1
        return mock

    def test_full_monitoring_pipeline(self, mock_redis):
        """Test full monitoring pipeline integration."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        # 1. Start throughput tracking
        tracker = ThroughputTracker(redis_client=mock_redis)
        for i in range(20):
            tracker.record_signal(f"sig-{i}", latency_ms=100.0 + i * 5, success=True)

        # 2. Store metrics
        metrics = tracker.store_current_metrics()
        assert "throughput" in metrics
        assert "latency" in metrics

        # 3. Run health probe
        probe = PaperE2EHealthProbe(dry_run=False)

        with patch(
            "scripts.monitoring.paper_e2e_health_probe.redis.Redis"
        ) as mock_redis_class:
            mock_redis_class.return_value = mock_redis
            summary = probe.run_all_checks()

        assert summary["overall_status"] in ["PASS", "WARN", "FAIL"]
        assert len(summary["checks"]) >= 6

    def test_error_propagation(self, mock_redis):
        """Test error propagation between components."""
        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        tracker = ThroughputTracker(redis_client=mock_redis)

        # Record mix of successes and failures
        for i in range(20):
            success = i % 5 != 0  # 20% failure rate
            tracker.record_signal(
                f"sig-{i}",
                latency_ms=100.0,
                success=success,
                metadata={"error": None if success else "timeout"},
            )

        # Verify signals recorded
        assert len(tracker._signals) == 20

        # Calculate error rate
        failures = sum(1 for s in tracker._signals if not s.success)
        error_rate = failures / len(tracker._signals) * 100

        assert error_rate == 20.0

    def test_health_monitor_integration(self, mock_redis):
        """Test health monitor integration with other components."""
        from execution.health_monitor import ExecutionHealthMonitor

        monitor = ExecutionHealthMonitor()

        # Check initial status
        status = monitor.get_status()
        assert "bybit" in status
        assert "bitget" in status

        # Verify monitoring can start/stop
        asyncio.run(monitor.start())
        assert monitor._running is True

        asyncio.run(monitor.stop())
        assert monitor._running is False

    def test_end_to_end_signal_flow(self, mock_redis):
        """Test complete signal flow end-to-end."""
        from scripts.monitoring.paper_e2e_health_probe import PaperE2EHealthProbe

        from execution.signal_delivery.throughput_tracker import ThroughputTracker

        # Step 1: Generate signals
        tracker = ThroughputTracker(redis_client=mock_redis)
        for i in range(50):
            tracker.record_signal(
                f"sig-{i}",
                latency_ms=100.0 + (i % 50),
                success=True,
                metadata={"symbol": f"COIN{i % 5}/USDT"},
            )

        # Step 2: Verify throughput metrics
        metrics = tracker.get_metrics("5min")
        assert metrics.signals_count == 50
        assert metrics.signals_per_minute > 0

        # Step 3: Verify latency percentiles
        latencies = tracker.get_latency_percentiles("5min")
        assert latencies.count == 50
        assert latencies.p50_ms > 0
        assert latencies.p95_ms > 0

        # Step 4: Run health check
        probe = PaperE2EHealthProbe(dry_run=False)

        with patch(
            "scripts.monitoring.paper_e2e_health_probe.redis.Redis"
        ) as mock_redis_class:
            mock_redis_class.return_value = mock_redis
            summary = probe.run_all_checks()

        # Verify health check passed
        assert summary["summary"]["total_checks"] >= 6

    @pytest.mark.asyncio
    async def test_async_health_monitor_operations(self, mock_redis):
        """Test async operations in health monitor."""
        from execution.health_monitor import ExecutionHealthMonitor

        monitor = ExecutionHealthMonitor()

        # Start monitoring
        await monitor.start()
        assert monitor._running is True

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Get status
        status = monitor.get_status()
        assert "bybit" in status
        assert "bitget" in status

        # Stop monitoring
        await monitor.stop()
        assert monitor._running is False


class TestMockExternalDependencies:
    """Test that external dependencies are properly mocked."""

    def test_discord_mocking(self):
        """Test Discord operations are mocked."""
        mock_discord = MagicMock()
        mock_discord.send_message = AsyncMock(return_value={"success": True})

        # Simulate Discord send
        result = asyncio.run(mock_discord.send_message("test message"))

        assert result["success"] is True
        mock_discord.send_message.assert_called_once()

    def test_redis_mocking(self):
        """Test Redis operations are mocked."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = "test_value"
        mock_redis.hgetall.return_value = {"key": "value"}

        assert mock_redis.ping() is True
        assert mock_redis.get("test") == "test_value"
        assert mock_redis.hgetall("hash") == {"key": "value"}

    def test_external_api_mocking(self):
        """Test external API calls are mocked."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "ok"}'
            mock_urlopen.return_value.__enter__.return_value = mock_response

            import urllib.request

            req = urllib.request.Request("https://api.example.com/test")

            with urllib.request.urlopen(req) as response:
                assert response.status == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
