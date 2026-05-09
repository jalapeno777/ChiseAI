"""Tests for LLM health monitor.

Tests lifecycle management, circuit breaker integration,
and thread safety of the background health monitor.

For ST-MVP-007: LLM Provider Redundancy Enhancement
"""

import time
from unittest.mock import MagicMock, patch

from llm.circuit_breaker import CircuitBreaker, CircuitState
from llm.health_check import HealthCheckResult, HealthStatus, ProviderHealthChecker
from llm.health_monitor import HealthMonitor


class TestHealthMonitorLifecycle:
    """Tests for health monitor start/stop lifecycle."""

    def test_start_creates_daemon_thread(self):
        """Start creates a daemon thread."""
        monitor = HealthMonitor(
            health_checker=MagicMock(spec=ProviderHealthChecker),
            circuit_breaker=CircuitBreaker(),
            check_interval_seconds=60,
        )
        monitor.start()
        try:
            assert monitor._thread is not None
            assert monitor._thread.daemon is True
            assert monitor.is_running is True
        finally:
            monitor.stop()

    def test_stop_joins_thread(self):
        """Stop joins the background thread."""
        monitor = HealthMonitor(
            health_checker=MagicMock(spec=ProviderHealthChecker),
            circuit_breaker=CircuitBreaker(),
            check_interval_seconds=60,
        )
        monitor.start()
        monitor.stop()
        assert not monitor.is_running
        assert monitor._thread is None

    def test_stop_when_not_running_is_noop(self):
        """Stop when not running is a safe no-op."""
        monitor = HealthMonitor(
            health_checker=MagicMock(spec=ProviderHealthChecker),
            circuit_breaker=CircuitBreaker(),
            check_interval_seconds=60,
        )
        monitor.stop()  # Should not raise
        assert not monitor.is_running

    def test_double_start_protection(self):
        """Calling start() twice does not create a second thread."""
        monitor = HealthMonitor(
            health_checker=MagicMock(spec=ProviderHealthChecker),
            circuit_breaker=CircuitBreaker(),
            check_interval_seconds=60,
        )
        monitor.start()
        thread1 = monitor._thread
        monitor.start()  # Should be no-op
        thread2 = monitor._thread
        assert thread1 is thread2
        monitor.stop()


class TestHealthMonitorCircuitBreakerUpdates:
    """Tests for circuit breaker updates from health results."""

    def test_check_now_records_success_for_healthy(self):
        """HEALTHY result records success on circuit breaker."""
        cb = CircuitBreaker()
        checker = MagicMock(spec=ProviderHealthChecker)
        healthy_result = HealthCheckResult(
            provider="test_provider",
            status=HealthStatus.HEALTHY,
            latency_ms=100.0,
            message="ok",
        )
        checker.check_health.return_value = healthy_result

        monitor = HealthMonitor(
            health_checker=checker,
            circuit_breaker=cb,
            check_interval_seconds=60,
            providers=["test_provider"],
        )
        monitor.check_now()

        state = cb.get_state("test_provider")
        assert state == CircuitState.CLOSED  # healthy = success

    def test_check_now_records_failure_for_unavailable(self):
        """UNAVAILABLE result records failure on circuit breaker."""
        cb = CircuitBreaker(failure_threshold=5, failure_window_seconds=60.0)
        checker = MagicMock(spec=ProviderHealthChecker)
        unhealthy_result = HealthCheckResult(
            provider="test_provider",
            status=HealthStatus.UNAVAILABLE,
            latency_ms=0.0,
            message="down",
        )
        checker.check_health.return_value = unhealthy_result

        monitor = HealthMonitor(
            health_checker=checker,
            circuit_breaker=cb,
            check_interval_seconds=60,
            providers=["test_provider"],
        )

        # Trigger enough failures to open circuit
        for _ in range(6):
            monitor.check_now()

        state = cb.get_state("test_provider")
        assert state == CircuitState.OPEN

    def test_check_now_degraded_does_not_update_circuit(self):
        """DEGRADED result does not update circuit breaker state."""
        cb = CircuitBreaker(failure_threshold=3, failure_window_seconds=60.0)
        # Pre-populate some failures
        cb.record_failure("test_provider")
        cb.record_failure("test_provider")

        checker = MagicMock(spec=ProviderHealthChecker)
        degraded_result = HealthCheckResult(
            provider="test_provider",
            status=HealthStatus.DEGRADED,
            latency_ms=5000.0,
            message="slow",
        )
        checker.check_health.return_value = degraded_result

        monitor = HealthMonitor(
            health_checker=checker,
            circuit_breaker=cb,
            check_interval_seconds=60,
            providers=["test_provider"],
        )
        monitor.check_now()

        # DEGRADED should not add another failure, so count stays at 2
        assert cb.get_failure_count("test_provider") == 2
        assert cb.get_state("test_provider") == CircuitState.CLOSED

    def test_check_now_unknown_does_not_update_circuit(self):
        """UNKNOWN result does not update circuit breaker state."""
        cb = CircuitBreaker()
        checker = MagicMock(spec=ProviderHealthChecker)
        unknown_result = HealthCheckResult(
            provider="test_provider",
            status=HealthStatus.UNKNOWN,
            message="no check strategy",
        )
        checker.check_health.return_value = unknown_result

        monitor = HealthMonitor(
            health_checker=checker,
            circuit_breaker=cb,
            check_interval_seconds=60,
            providers=["test_provider"],
        )
        monitor.check_now()

        # UNKNOWN should not affect circuit state
        assert cb.get_state("test_provider") == CircuitState.CLOSED

    def test_check_now_returns_results(self):
        """check_now returns a dict of provider -> status name."""
        checker = MagicMock(spec=ProviderHealthChecker)
        healthy_result = HealthCheckResult(
            provider="kimi",
            status=HealthStatus.HEALTHY,
            message="ok",
        )
        checker.check_health.return_value = healthy_result

        monitor = HealthMonitor(
            health_checker=checker,
            circuit_breaker=CircuitBreaker(),
            check_interval_seconds=60,
            providers=["kimi"],
        )
        results = monitor.check_now()
        assert results == {"kimi": "HEALTHY"}


class TestHealthMonitorGetLastResults:
    """Tests for get_last_results method."""

    def test_empty_before_first_check(self):
        """get_last_results returns empty dict before first check."""
        monitor = HealthMonitor(
            health_checker=MagicMock(spec=ProviderHealthChecker),
            circuit_breaker=CircuitBreaker(),
            check_interval_seconds=60,
        )
        assert monitor.get_last_results() == {}

    def test_returns_copy_of_last_results(self):
        """get_last_results returns a copy, not the original."""
        checker = MagicMock(spec=ProviderHealthChecker)
        healthy_result = HealthCheckResult(
            provider="kimi",
            status=HealthStatus.HEALTHY,
            message="ok",
        )
        checker.check_health.return_value = healthy_result

        monitor = HealthMonitor(
            health_checker=checker,
            circuit_breaker=CircuitBreaker(),
            check_interval_seconds=60,
            providers=["kimi"],
        )
        monitor.check_now()

        results = monitor.get_last_results()
        results["kimi"] = "MODIFIED"  # Modify the copy

        # Original should be unchanged
        assert monitor.get_last_results() == {"kimi": "HEALTHY"}


class TestHealthMonitorIntegration:
    """Integration tests with real circuit breaker and health checker."""

    def test_monitor_with_real_checker_and_cb(self):
        """Integration test with real ProviderHealthChecker and CircuitBreaker."""
        cb = CircuitBreaker(failure_threshold=3, failure_window_seconds=60.0)
        checker = ProviderHealthChecker(cache_ttl_seconds=0.01)

        monitor = HealthMonitor(
            health_checker=checker,
            circuit_breaker=cb,
            check_interval_seconds=60,
            providers=["kimi"],
        )

        # check_now should work without error
        with patch.dict(
            "os.environ",
            {"KIMI_API_KEY": "test-key"},
            clear=False,
        ):
            results = monitor.check_now()
            assert "kimi" in results

    def test_thread_stop_with_slow_health_checks(self):
        """Monitor stops cleanly even when health checks are slow."""
        cb = CircuitBreaker()
        slow_checker = MagicMock(spec=ProviderHealthChecker)

        def slow_check(provider):
            time.sleep(0.5)
            return HealthCheckResult(
                provider=provider,
                status=HealthStatus.HEALTHY,
                message="slow check done",
            )

        slow_checker.check_health.side_effect = slow_check

        monitor = HealthMonitor(
            health_checker=slow_checker,
            circuit_breaker=cb,
            check_interval_seconds=0.1,
            providers=["kimi"],
        )
        monitor.start()
        time.sleep(0.2)  # Let it start a check
        monitor.stop()

        assert not monitor.is_running
