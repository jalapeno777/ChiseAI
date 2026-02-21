"""Tests for paper trading tracker with alert hooks.

For ST-PAPER-008: Paper Trading Alerts and Runbooks
"""

from datetime import UTC, datetime, timedelta


from portfolio.paper_tracker import (
    PaperTracker,
    RedisHealthMetrics,
    ValidationFailure,
)
from portfolio_risk.alerts.detector import RiskAlertDetector
from portfolio_risk.alerts.types import AlertSeverity, AlertType


class TestRedisHealthMetrics:
    """Test RedisHealthMetrics class."""

    def test_initialization(self):
        """Test default initialization."""
        metrics = RedisHealthMetrics()

        assert metrics.error_count == 0
        assert metrics.total_operations == 0
        assert metrics.error_rate == 0.0
        assert metrics.circuit_breaker_open is False
        assert metrics.last_error is None

    def test_record_success(self):
        """Test recording successful operations."""
        metrics = RedisHealthMetrics()

        metrics.record_success()
        assert metrics.total_operations == 1
        assert metrics.error_count == 0
        assert metrics.error_rate == 0.0
        assert metrics.last_successful_operation is not None

    def test_record_failure(self):
        """Test recording failed operations."""
        metrics = RedisHealthMetrics()

        metrics.record_failure("Connection timeout")
        assert metrics.total_operations == 1
        assert metrics.error_count == 1
        assert metrics.error_rate == 100.0
        assert metrics.last_error == "Connection timeout"

    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        metrics = RedisHealthMetrics()

        # 2 failures out of 5 operations = 40%
        for _ in range(3):
            metrics.record_success()
        for _ in range(2):
            metrics.record_failure("Error")

        assert metrics.error_rate == 40.0

    def test_reset_window(self):
        """Test resetting metrics window."""
        metrics = RedisHealthMetrics()

        metrics.record_failure("Error")
        metrics.reset_window()

        assert metrics.error_count == 0
        assert metrics.total_operations == 0
        assert metrics.error_rate == 0.0

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = RedisHealthMetrics()
        metrics.record_success()

        d = metrics.to_dict()

        assert d["error_count"] == 0
        assert d["total_operations"] == 1
        assert d["error_rate_pct"] == 0.0
        assert d["circuit_breaker_open"] is False


class TestValidationFailure:
    """Test ValidationFailure class."""

    def test_creation(self):
        """Test basic creation."""
        failure = ValidationFailure(
            order_id="order_123",
            reason="insufficient_funds",
            details={"available": 100, "required": 200},
        )

        assert failure.order_id == "order_123"
        assert failure.reason == "insufficient_funds"
        assert failure.details["available"] == 100
        assert failure.timestamp is not None

    def test_to_dict(self):
        """Test dictionary conversion."""
        failure = ValidationFailure(
            order_id="order_123",
            reason="insufficient_funds",
        )

        d = failure.to_dict()

        assert d["order_id"] == "order_123"
        assert d["reason"] == "insufficient_funds"
        assert "timestamp" in d


class TestPaperTrackerInitialization:
    """Test PaperTracker initialization."""

    def test_default_initialization(self):
        """Test initialization with defaults."""
        tracker = PaperTracker()

        assert tracker.portfolio_id == "paper_trading"
        assert tracker.divergence_threshold_pct == 5.0
        assert tracker.validation_window_minutes == 5
        assert tracker.alert_detector is None

    def test_custom_initialization(self):
        """Test initialization with custom values."""
        detector = RiskAlertDetector()
        tracker = PaperTracker(
            portfolio_id="custom_portfolio",
            alert_detector=detector,
            divergence_threshold_pct=10.0,
            validation_window_minutes=10,
        )

        assert tracker.portfolio_id == "custom_portfolio"
        assert tracker.alert_detector == detector
        assert tracker.divergence_threshold_pct == 10.0
        assert tracker.validation_window_minutes == 10


class TestPaperTrackerRedisAlerts:
    """Test Redis failure alert hooks."""

    def test_on_redis_failure_triggers_alert(self):
        """Test that Redis failure triggers alert."""
        detector = RiskAlertDetector()
        tracker = PaperTracker(alert_detector=detector)

        alert = tracker.on_redis_failure(
            error="Connection refused",
            affected_operations=["state_sync"],
            circuit_breaker_open=True,
        )

        assert alert is not None
        assert alert.alert_type == AlertType.REDIS_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL
        assert tracker._redis_health.error_count == 1

    def test_on_redis_failure_no_detector(self):
        """Test Redis failure without detector."""
        tracker = PaperTracker(alert_detector=None)

        alert = tracker.on_redis_failure(
            error="Connection refused",
            circuit_breaker_open=True,
        )

        assert alert is None
        assert tracker._redis_health.error_count == 1

    def test_on_redis_success(self):
        """Test recording successful Redis operation."""
        tracker = PaperTracker()

        tracker.on_redis_success()

        assert tracker._redis_health.total_operations == 1
        assert tracker._redis_health.error_count == 0

    def test_on_redis_circuit_breaker_open(self):
        """Test circuit breaker open hook."""
        detector = RiskAlertDetector()
        tracker = PaperTracker(alert_detector=detector)

        alert = tracker.on_redis_circuit_breaker_open("Too many failures")

        assert alert is not None
        assert alert.alert_type == AlertType.REDIS_FAILURE
        assert tracker._redis_health.circuit_breaker_open is True

    def test_alert_rate_limiting(self):
        """Test that alerts are rate limited."""
        detector = RiskAlertDetector()
        tracker = PaperTracker(alert_detector=detector)

        # First alert should trigger
        alert1 = tracker.on_redis_failure(
            error="Error 1",
            circuit_breaker_open=True,
        )
        assert alert1 is not None

        # Second alert immediately after should be suppressed
        alert2 = tracker.on_redis_failure(
            error="Error 2",
            circuit_breaker_open=True,
        )
        assert alert2 is None  # Rate limited

    def test_get_redis_health(self):
        """Test getting Redis health metrics."""
        tracker = PaperTracker()
        tracker.on_redis_failure("Test error")
        tracker.on_redis_success()

        health = tracker.get_redis_health()

        assert health["error_count"] == 1
        assert health["total_operations"] == 2
        assert health["error_rate_pct"] == 50.0


class TestPaperTrackerDivergence:
    """Test divergence detection."""

    def test_check_divergence_no_detector(self):
        """Test divergence check without detector."""
        tracker = PaperTracker(alert_detector=None)

        alert = tracker.check_divergence()

        assert alert is None

    def test_check_divergence_no_redis(self):
        """Test divergence when Redis unavailable."""
        detector = RiskAlertDetector()
        tracker = PaperTracker(alert_detector=detector)

        # _fetch_redis_state returns None (simulating Redis unavailable)
        alert = tracker.check_divergence()

        assert alert is None

    def test_check_divergence_detected(self):
        """Test divergence detection triggers alert."""
        detector = RiskAlertDetector()
        tracker = PaperTracker(
            alert_detector=detector,
            divergence_threshold_pct=5.0,
        )

        # Set up positions in memory
        tracker._positions = {
            "BTC": {"size": 1.0, "notional_value": 11000.0, "entry_price": 10000.0},
        }

        # Provide Redis state with divergence
        redis_state = {
            "BTC": {"notional_value": 10000.0},  # 10% divergence
        }

        alert = tracker.check_divergence(redis_state=redis_state)

        assert alert is not None
        assert alert.alert_type == AlertType.PAPER_SYNC_DIVERGENCE


class TestPaperTrackerValidationFailures:
    """Test validation failure tracking."""

    def test_record_validation_failure(self):
        """Test recording a validation failure."""
        tracker = PaperTracker()

        alert = tracker.record_validation_failure(
            order_id="order_1",
            reason="insufficient_funds",
        )

        # Single failure shouldn't trigger alert (<10%)
        assert alert is None
        assert len(tracker._validation_failures) == 1

    def test_validation_failure_rate_alert(self):
        """Test high validation failure rate triggers alert."""
        detector = RiskAlertDetector()
        tracker = PaperTracker(
            alert_detector=detector,
            validation_window_minutes=5,
        )

        # Reset alert timer to ensure alert can fire
        tracker._last_validation_alert = None

        # Record many failures to trigger alert (>10%)
        # We need enough failures to exceed 10% of total orders
        # With the default estimate of max(10, failures*2) successful orders,
        # we need: failures / (failures + max(10, failures*2)) > 0.10
        # For 15 failures: 15 / (15 + 30) = 15/45 = 33% > 10%
        triggered_alerts = []
        for i in range(20):  # Use 20 to ensure we trigger the alert
            alert = tracker.record_validation_failure(
                order_id=f"order_{i}",
                reason="insufficient_funds",
            )
            if alert:
                triggered_alerts.append(alert)

        # Alert should have been triggered at least once
        assert len(triggered_alerts) >= 1
        assert triggered_alerts[0].alert_type == AlertType.VALIDATION_FAILURE_RATE

    def test_get_validation_failure_summary(self):
        """Test getting validation failure summary."""
        tracker = PaperTracker()

        tracker.record_validation_failure("order_1", "insufficient_funds")
        tracker.record_validation_failure("order_2", "price_stale")
        tracker.record_validation_failure("order_3", "insufficient_funds")

        summary = tracker.get_validation_failure_summary()

        assert summary["total_failures"] == 3
        assert "insufficient_funds" in summary["failure_breakdown"]
        assert "price_stale" in summary["failure_breakdown"]
        assert summary["failure_breakdown"]["insufficient_funds"] == 2

    def test_clean_old_failures(self):
        """Test cleaning old validation failures."""
        tracker = PaperTracker(validation_window_minutes=5)

        # Add a failure
        tracker.record_validation_failure("order_1", "insufficient_funds")

        # Manually set timestamp to be old
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        tracker._validation_failures[0].timestamp = old_time

        # Clean should remove it
        tracker._clean_old_failures()

        assert len(tracker._validation_failures) == 0


class TestPaperTrackerUtilityMethods:
    """Test utility methods."""

    def test_should_trigger_alert_no_last_alert(self):
        """Test alert triggering when no previous alert."""
        tracker = PaperTracker()

        assert tracker._should_trigger_alert(None) is True

    def test_should_trigger_alert_after_interval(self):
        """Test alert triggering after interval."""
        tracker = PaperTracker()

        old_time = datetime.now(UTC) - timedelta(minutes=10)
        assert tracker._should_trigger_alert(old_time) is True

    def test_should_not_trigger_alert_within_interval(self):
        """Test alert suppression within interval."""
        tracker = PaperTracker()

        recent_time = datetime.now(UTC) - timedelta(seconds=30)
        assert tracker._should_trigger_alert(recent_time) is False

    def test_reset_alert_timers(self):
        """Test resetting alert timers."""
        tracker = PaperTracker()

        # Set some timers
        tracker._last_redis_alert = datetime.now(UTC)
        tracker._last_divergence_alert = datetime.now(UTC)
        tracker._last_validation_alert = datetime.now(UTC)

        tracker.reset_alert_timers()

        assert tracker._last_redis_alert is None
        assert tracker._last_divergence_alert is None
        assert tracker._last_validation_alert is None

    def test_get_sync_status_no_redis(self):
        """Test sync status when Redis unavailable."""
        tracker = PaperTracker()

        status = tracker.get_sync_status()

        assert status["redis_connected"] is False
        assert status["divergence_pct"] == 100.0

    def test_build_memory_state(self):
        """Test building memory state."""
        tracker = PaperTracker()
        tracker._positions = {
            "BTC": {"size": 1.0, "notional_value": 10000.0, "entry_price": 10000.0},
            "ETH": {"size": 10.0, "notional_value": 5000.0, "entry_price": 500.0},
        }

        state = tracker._build_memory_state()

        assert "BTC" in state
        assert "ETH" in state
        assert state["BTC"]["notional_value"] == 10000.0
        assert state["ETH"]["notional_value"] == 5000.0
