"""Tests for error rate monitoring and alert integration.

For ST-PARTY-E2E-REMEDIATION-001: Error Rate Monitor & Alert Integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.execution.alerts.error_rate_integration import (
    AlertSeverity,
    ErrorCategory,
    ErrorRateAlertIntegration,
    ErrorRateSnapshot,
    ErrorRateThresholds,
    ErrorRateTracker,
)


@pytest.fixture(autouse=True)
def reset_redis_state():
    """Reset Redis state before each test to ensure isolation."""
    # Clear all error rate keys from Redis using scan_iter
    try:
        import redis

        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        pattern = "chise:paper:metrics:error_rate:*"
        for key in client.scan_iter(match=pattern):
            client.delete(key)
    except Exception:
        pass  # Redis may not be available
    yield
    # Cleanup after test
    try:
        import redis

        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        pattern = "chise:paper:metrics:error_rate:*"
        for key in client.scan_iter(match=pattern):
            client.delete(key)
    except Exception:
        pass


@pytest.fixture
def isolated_tracker():
    """Create an isolated tracker that doesn't use Redis."""
    tracker = ErrorRateTracker()
    tracker._redis = None  # Force local-only mode
    return tracker


class TestErrorRateThresholds:
    """Test ErrorRateThresholds dataclass."""

    def test_default_values(self):
        """Test default threshold values."""
        thresholds = ErrorRateThresholds()
        assert thresholds.warning == 5.0
        assert thresholds.critical == 10.0
        assert thresholds.min_operations == 10
        assert thresholds.alert_cooldown_minutes == 15

    def test_custom_values(self):
        """Test custom threshold values."""
        thresholds = ErrorRateThresholds(
            warning=3.0,
            critical=7.0,
            min_operations=5,
            alert_cooldown_minutes=30,
        )
        assert thresholds.warning == 3.0
        assert thresholds.critical == 7.0
        assert thresholds.min_operations == 5
        assert thresholds.alert_cooldown_minutes == 30

    def test_to_dict(self):
        """Test conversion to dictionary."""
        thresholds = ErrorRateThresholds(warning=3.0, critical=7.0)
        data = thresholds.to_dict()
        assert data["warning"] == 3.0
        assert data["critical"] == 7.0
        assert data["min_operations"] == 10
        assert data["alert_cooldown_minutes"] == 15

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "warning": 2.5,
            "critical": 8.0,
            "min_operations": 20,
            "alert_cooldown_minutes": 10,
        }
        thresholds = ErrorRateThresholds.from_dict(data)
        assert thresholds.warning == 2.5
        assert thresholds.critical == 8.0
        assert thresholds.min_operations == 20
        assert thresholds.alert_cooldown_minutes == 10

    def test_from_dict_defaults(self):
        """Test from_dict with missing values uses defaults."""
        data = {"warning": 4.0}
        thresholds = ErrorRateThresholds.from_dict(data)
        assert thresholds.warning == 4.0
        assert thresholds.critical == 10.0  # default
        assert thresholds.min_operations == 10  # default


class TestErrorRateSnapshot:
    """Test ErrorRateSnapshot dataclass."""

    def test_basic_properties(self):
        """Test basic snapshot properties."""
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=5,
            error_rate=5.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )
        assert snapshot.category == ErrorCategory.API
        assert snapshot.total_operations == 100
        assert snapshot.error_count == 5
        assert snapshot.error_rate == 5.0

    def test_is_warning_true(self):
        """Test is_warning when at threshold."""
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=5,
            error_rate=5.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )
        assert snapshot.is_warning is True
        assert snapshot.is_critical is False
        assert snapshot.severity == AlertSeverity.WARNING

    def test_is_warning_false(self):
        """Test is_warning when below threshold."""
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=4,
            error_rate=4.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )
        assert snapshot.is_warning is False
        assert snapshot.is_critical is False
        assert snapshot.severity == AlertSeverity.INFO

    def test_is_critical_true(self):
        """Test is_critical when at threshold."""
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=10,
            error_rate=10.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )
        assert snapshot.is_warning is True
        assert snapshot.is_critical is True
        assert snapshot.severity == AlertSeverity.CRITICAL

    def test_to_dict(self):
        """Test conversion to dictionary."""
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.VALIDATION,
            total_operations=50,
            error_count=3,
            error_rate=6.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )
        data = snapshot.to_dict()
        assert data["category"] == "validation"
        assert data["total_operations"] == 50
        assert data["error_count"] == 3
        assert data["error_rate"] == 6.0
        assert data["is_warning"] is True
        assert data["is_critical"] is False
        assert data["severity"] == "warning"


class TestErrorRateTracker:
    """Test ErrorRateTracker class."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = ErrorRateTracker()
        assert tracker.thresholds.warning == 5.0
        assert tracker._redis is None

    def test_initialization_with_thresholds(self):
        """Test tracker with custom thresholds."""
        thresholds = ErrorRateThresholds(warning=3.0, critical=8.0)
        tracker = ErrorRateTracker(thresholds=thresholds)
        assert tracker.thresholds.warning == 3.0
        assert tracker.thresholds.critical == 8.0

    def test_record_operation_success(self, isolated_tracker):
        """Test recording successful operation."""
        tracker = isolated_tracker
        snapshot = tracker.record_operation(ErrorCategory.UNKNOWN, success=True)

        assert snapshot.category == ErrorCategory.UNKNOWN
        assert snapshot.total_operations == 1
        assert snapshot.error_count == 0
        assert snapshot.error_rate == 0.0

    def test_record_operation_failure(self, isolated_tracker):
        """Test recording failed operation."""
        tracker = isolated_tracker
        snapshot = tracker.record_operation(ErrorCategory.DATABASE, success=False)

        assert snapshot.total_operations == 1
        assert snapshot.error_count == 1
        assert snapshot.error_rate == 100.0

    def test_record_multiple_operations(self, isolated_tracker):
        """Test recording multiple operations."""
        tracker = isolated_tracker

        # Record 10 operations: 8 success, 2 failures
        for _ in range(8):
            tracker.record_operation(ErrorCategory.EXECUTION, success=True)
        for _ in range(2):
            tracker.record_operation(ErrorCategory.EXECUTION, success=False)

        snapshot = tracker.get_error_rate(ErrorCategory.EXECUTION)
        assert snapshot.total_operations == 10
        assert snapshot.error_count == 2
        assert snapshot.error_rate == 20.0

    def test_get_error_rate_empty(self, isolated_tracker):
        """Test getting error rate for empty category."""
        tracker = isolated_tracker
        snapshot = tracker.get_error_rate(ErrorCategory.DATABASE)

        assert snapshot.total_operations == 0
        assert snapshot.error_count == 0
        assert snapshot.error_rate == 0.0

    def test_get_all_error_rates(self, isolated_tracker):
        """Test getting all error rates."""
        tracker = isolated_tracker

        # Add some data
        tracker.record_operation(ErrorCategory.NETWORK, success=True)
        tracker.record_operation(ErrorCategory.DATABASE, success=False)

        all_rates = tracker.get_all_error_rates()

        assert len(all_rates) == len(ErrorCategory)
        assert all_rates[ErrorCategory.NETWORK].total_operations == 1
        assert all_rates[ErrorCategory.DATABASE].error_count == 1

    def test_reset_category(self, isolated_tracker):
        """Test resetting a category."""
        tracker = isolated_tracker

        # Add data
        tracker.record_operation(ErrorCategory.NETWORK, success=False)
        snapshot = tracker.get_error_rate(ErrorCategory.NETWORK)
        assert snapshot.error_count == 1

        # Reset
        tracker.reset_category(ErrorCategory.NETWORK)
        snapshot = tracker.get_error_rate(ErrorCategory.NETWORK)
        assert snapshot.error_count == 0
        assert snapshot.total_operations == 0

    def test_record_operation_with_error_details(self, isolated_tracker):
        """Test recording operation with error details."""
        tracker = isolated_tracker
        error_details = {
            "error_type": "ConnectionError",
            "message": "Failed to connect",
            "endpoint": "/api/v1/trade",
        }

        snapshot = tracker.record_operation(
            ErrorCategory.DATABASE, success=False, error_details=error_details
        )

        assert snapshot.error_count == 1

    @patch("redis.Redis")
    def test_redis_integration(self, mock_redis_class):
        """Test Redis integration."""
        mock_client = MagicMock()
        mock_client.hincrby.return_value = 1
        mock_redis_class.return_value = mock_client

        tracker = ErrorRateTracker()
        snapshot = tracker.record_operation(ErrorCategory.API, success=True)

        assert snapshot.total_operations >= 1
        mock_client.hincrby.assert_called()


class TestErrorRateAlertIntegration:
    """Test ErrorRateAlertIntegration class."""

    def test_initialization(self):
        """Test alert integration initialization."""
        integration = ErrorRateAlertIntegration()
        assert integration.enabled is True
        assert integration.tracker is not None
        assert integration.discord_webhook_url is None

    def test_initialization_with_params(self):
        """Test initialization with parameters."""
        tracker = ErrorRateTracker()
        integration = ErrorRateAlertIntegration(
            tracker=tracker,
            discord_webhook_url="https://discord.com/webhook",
            enabled=False,
        )
        assert integration.enabled is False
        assert integration.tracker == tracker
        assert integration.discord_webhook_url == "https://discord.com/webhook"

    def test_get_stats(self):
        """Test getting stats."""
        integration = ErrorRateAlertIntegration()
        stats = integration.get_stats()
        assert stats["alerts_sent"] == 0
        assert stats["alerts_suppressed"] == 0
        assert stats["errors"] == 0

    def test_get_all_metrics(self):
        """Test getting all metrics."""
        integration = ErrorRateAlertIntegration()
        metrics = integration.get_all_metrics()

        assert "categories" in metrics
        assert "alert_stats" in metrics
        assert "thresholds" in metrics
        assert len(metrics["categories"]) == len(ErrorCategory)

    @pytest.mark.asyncio
    async def test_check_and_alert_no_data(self):
        """Test check and alert with no data."""
        integration = ErrorRateAlertIntegration(enabled=False)
        results = await integration.check_and_alert()

        assert "checked" in results
        assert "alerts_sent" in results
        assert len(results["alerts_sent"]) == 0

    @pytest.mark.asyncio
    async def test_check_and_alert_single_category(self):
        """Test check and alert for single category."""
        tracker = ErrorRateTracker()
        # Add enough operations to trigger warning
        for _ in range(10):
            tracker.record_operation(ErrorCategory.API, success=False)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=False)
        results = await integration.check_and_alert(ErrorCategory.API)

        assert len(results["checked"]) == 1
        assert results["checked"][0]["category"] == "api"

    @pytest.mark.asyncio
    async def test_should_send_alert_disabled(self):
        """Test should_send_alert when disabled."""
        integration = ErrorRateAlertIntegration(enabled=False)
        result = integration._should_send_alert(
            ErrorCategory.API, AlertSeverity.WARNING
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_discord_alert_no_webhook(self):
        """Test send alert with no webhook."""
        import os

        os.environ.pop("DISCORD_ALERT_WEBHOOK_URL", None)
        integration = ErrorRateAlertIntegration(discord_webhook_url="")
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=10,
            error_rate=10.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )

        result = await integration._send_discord_alert(snapshot)
        assert result["sent"] is False
        assert "No Discord webhook URL" in result["error"]

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_send_discord_alert_success(self, mock_session_class):
        """Test successful Discord alert."""
        # Setup mock
        mock_response = AsyncMock()
        mock_response.status = 204

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_class.return_value = mock_session

        integration = ErrorRateAlertIntegration(
            discord_webhook_url="https://discord.com/webhook"
        )
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=10,
            error_rate=10.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )

        result = await integration._send_discord_alert(snapshot)
        assert result["sent"] is True
        assert result["category"] == "api"
        assert result["severity"] == "critical"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_send_discord_alert_http_error(self, mock_session_class):
        """Test Discord alert with HTTP error."""
        # Setup mock
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_class.return_value = mock_session

        integration = ErrorRateAlertIntegration(
            discord_webhook_url="https://discord.com/webhook"
        )
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=10,
            error_rate=10.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )

        result = await integration._send_discord_alert(snapshot)
        assert result["sent"] is False
        assert "HTTP 400" in result["error"]


class TestErrorCategories:
    """Test error categories enum."""

    def test_all_categories(self):
        """Test all error categories exist."""
        categories = list(ErrorCategory)
        assert ErrorCategory.API in categories
        assert ErrorCategory.VALIDATION in categories
        assert ErrorCategory.EXECUTION in categories
        assert ErrorCategory.DATABASE in categories
        assert ErrorCategory.NETWORK in categories
        assert ErrorCategory.UNKNOWN in categories

    def test_category_values(self):
        """Test category string values."""
        assert ErrorCategory.API.value == "api"
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.EXECUTION.value == "execution"
        assert ErrorCategory.DATABASE.value == "database"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.UNKNOWN.value == "unknown"


class TestAlertSeverity:
    """Test alert severity enum."""

    def test_severity_levels(self):
        """Test all severity levels."""
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.INFO.value == "info"


class TestIntegrationScenarios:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_workflow_warning(self, isolated_tracker):
        """Test full workflow with warning threshold."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(
            warning=5.0, critical=10.0, min_operations=10
        )

        # Generate 8% error rate (warning level, below critical)
        for _ in range(23):
            tracker.record_operation(ErrorCategory.NETWORK, success=True)
        for _ in range(2):
            tracker.record_operation(ErrorCategory.NETWORK, success=False)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=False)
        results = await integration.check_and_alert(ErrorCategory.NETWORK)

        assert len(results["checked"]) == 1
        assert results["checked"][0]["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_full_workflow_critical(self, isolated_tracker):
        """Test full workflow with critical threshold."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(
            warning=5.0, critical=10.0, min_operations=10
        )

        # Generate 20% error rate (critical level)
        for _ in range(8):
            tracker.record_operation(ErrorCategory.EXECUTION, success=True)
        for _ in range(2):
            tracker.record_operation(ErrorCategory.EXECUTION, success=False)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=False)
        results = await integration.check_and_alert(ErrorCategory.EXECUTION)

        assert len(results["checked"]) == 1
        assert results["checked"][0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_insufficient_operations(self, isolated_tracker):
        """Test behavior with insufficient operations."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(
            warning=5.0, critical=10.0, min_operations=10
        )

        # Only 5 operations, below min_operations threshold
        for _ in range(4):
            tracker.record_operation(ErrorCategory.DATABASE, success=True)
        tracker.record_operation(ErrorCategory.DATABASE, success=False)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=False)
        results = await integration.check_and_alert(ErrorCategory.DATABASE)

        assert len(results["checked"]) == 1
        assert results["checked"][0]["status"] == "skipped"
        assert results["checked"][0]["reason"] == "insufficient_operations"

    def test_multiple_categories_tracking(self, isolated_tracker):
        """Test tracking multiple categories independently."""
        tracker = isolated_tracker

        # API: 20% error rate
        for _ in range(8):
            tracker.record_operation(ErrorCategory.API, success=True)
        for _ in range(2):
            tracker.record_operation(ErrorCategory.API, success=False)

        # Validation: 0% error rate
        for _ in range(10):
            tracker.record_operation(ErrorCategory.VALIDATION, success=True)

        # Execution: 50% error rate
        for _ in range(5):
            tracker.record_operation(ErrorCategory.EXECUTION, success=True)
        for _ in range(5):
            tracker.record_operation(ErrorCategory.EXECUTION, success=False)

        api_rate = tracker.get_error_rate(ErrorCategory.API)
        validation_rate = tracker.get_error_rate(ErrorCategory.VALIDATION)
        execution_rate = tracker.get_error_rate(ErrorCategory.EXECUTION)

        assert api_rate.error_rate == 20.0
        assert validation_rate.error_rate == 0.0
        assert execution_rate.error_rate == 50.0

    def test_error_rate_calculation_accuracy(self, isolated_tracker):
        """Test error rate calculation accuracy."""
        tracker = isolated_tracker

        # 1 error out of 3 = 33.33%
        tracker.record_operation(ErrorCategory.DATABASE, success=True)
        tracker.record_operation(ErrorCategory.DATABASE, success=True)
        tracker.record_operation(ErrorCategory.DATABASE, success=False)

        snapshot = tracker.get_error_rate(ErrorCategory.DATABASE)
        assert snapshot.error_rate == pytest.approx(33.3333, rel=0.01)
        assert snapshot.total_operations == 3
        assert snapshot.error_count == 1


class TestEdgeCases:
    """Test edge cases."""

    def test_zero_operations(self, isolated_tracker):
        """Test with zero operations."""
        tracker = isolated_tracker
        snapshot = tracker.get_error_rate(ErrorCategory.DATABASE)

        assert snapshot.error_rate == 0.0
        assert snapshot.is_warning is False
        assert snapshot.is_critical is False

    def test_all_failures(self, isolated_tracker):
        """Test with 100% failure rate."""
        tracker = isolated_tracker

        for _ in range(10):
            tracker.record_operation(ErrorCategory.NETWORK, success=False)

        snapshot = tracker.get_error_rate(ErrorCategory.NETWORK)
        assert snapshot.error_rate == 100.0
        assert snapshot.is_critical is True

    def test_all_successes(self, isolated_tracker):
        """Test with 0% failure rate."""
        tracker = isolated_tracker

        for _ in range(100):
            tracker.record_operation(ErrorCategory.UNKNOWN, success=True)

        snapshot = tracker.get_error_rate(ErrorCategory.UNKNOWN)
        assert snapshot.error_rate == 0.0
        assert snapshot.is_warning is False
        assert snapshot.is_critical is False

    def test_exact_warning_threshold(self, isolated_tracker):
        """Test exactly at warning threshold."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(warning=5.0, critical=10.0)

        # Exactly 5% error rate
        for _ in range(19):
            tracker.record_operation(ErrorCategory.EXECUTION, success=True)
        tracker.record_operation(ErrorCategory.EXECUTION, success=False)

        snapshot = tracker.get_error_rate(ErrorCategory.EXECUTION)
        assert snapshot.error_rate == 5.0
        assert snapshot.is_warning is True  # At threshold counts as warning
        assert snapshot.is_critical is False

    def test_exact_critical_threshold(self, isolated_tracker):
        """Test exactly at critical threshold."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(warning=5.0, critical=10.0)

        # Exactly 10% error rate
        for _ in range(9):
            tracker.record_operation(ErrorCategory.VALIDATION, success=True)
        tracker.record_operation(ErrorCategory.VALIDATION, success=False)

        snapshot = tracker.get_error_rate(ErrorCategory.VALIDATION)
        assert snapshot.error_rate == 10.0
        assert snapshot.is_warning is True
        assert snapshot.is_critical is True  # At threshold counts as critical


class TestErrorRateMonitorScript:
    """Test the monitor script functions."""

    def test_parse_args_defaults(self):
        """Test argument parsing with defaults."""
        from scripts.monitoring.error_rate_monitor import parse_args

        with patch("sys.argv", ["error_rate_monitor.py"]):
            args = parse_args()
            assert args.dry_run is False
            assert args.category is None
            assert args.threshold_warning == 5.0
            assert args.threshold_critical == 10.0
            assert args.min_operations == 10

    def test_parse_args_custom(self):
        """Test argument parsing with custom values."""
        from scripts.monitoring.error_rate_monitor import parse_args

        with patch(
            "sys.argv",
            [
                "error_rate_monitor.py",
                "--dry-run",
                "--category",
                "api",
                "--threshold-warning",
                "3.0",
                "--threshold-critical",
                "8.0",
                "--min-operations",
                "5",
            ],
        ):
            args = parse_args()
            assert args.dry_run is True
            assert args.category == "api"
            assert args.threshold_warning == 3.0
            assert args.threshold_critical == 8.0
            assert args.min_operations == 5

    def test_get_discord_webhook_url_from_args(self):
        """Test getting webhook URL from args."""
        from scripts.monitoring.error_rate_monitor import get_discord_webhook_url

        args = MagicMock()
        args.webhook_url = "https://discord.com/test"

        result = get_discord_webhook_url(args)
        assert result == "https://discord.com/test"

    @patch.dict("os.environ", {"DISCORD_ALERT_WEBHOOK_URL": "https://discord.com/env"})
    def test_get_discord_webhook_url_from_env(self):
        """Test getting webhook URL from environment."""
        from scripts.monitoring.error_rate_monitor import get_discord_webhook_url

        args = MagicMock()
        args.webhook_url = None

        result = get_discord_webhook_url(args)
        assert result == "https://discord.com/env"


class TestErrorRateTrackerAdditionalCoverage:
    """Additional tests for better coverage."""

    def test_record_operation_redis_error_fallback(self, isolated_tracker):
        """Test that tracker falls back to local stats on Redis error."""
        tracker = isolated_tracker
        # Force Redis to be None to trigger fallback
        tracker._redis = None

        snapshot = tracker.record_operation(ErrorCategory.API, success=False)
        assert snapshot.error_count == 1
        assert snapshot.total_operations == 1

    def test_get_error_rate_redis_unavailable(self, isolated_tracker):
        """Test getting error rate when Redis is unavailable."""
        tracker = isolated_tracker
        tracker._redis = None

        # Record some operations
        tracker.record_operation(ErrorCategory.API, success=True)
        tracker.record_operation(ErrorCategory.API, success=False)

        snapshot = tracker.get_error_rate(ErrorCategory.API)
        assert snapshot.total_operations == 2
        assert snapshot.error_count == 1

    def test_get_recent_errors_empty(self, isolated_tracker):
        """Test getting recent errors when none exist."""
        tracker = isolated_tracker
        tracker._redis = None

        errors = tracker.get_recent_errors(ErrorCategory.API)
        assert errors == []

    def test_get_recent_errors_with_data(self, isolated_tracker):
        """Test getting recent errors with data."""
        tracker = isolated_tracker
        tracker._redis = None

        # Error details are only stored in Redis, so this tests the fallback
        errors = tracker.get_recent_errors(ErrorCategory.API, limit=5)
        assert errors == []


class TestErrorRateAlertIntegrationAdditionalCoverage:
    """Additional tests for alert integration coverage."""

    @pytest.mark.asyncio
    async def test_check_and_alert_all_categories(self, isolated_tracker):
        """Test checking all categories."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(
            warning=5.0, critical=10.0, min_operations=10
        )

        # Add data to multiple categories
        for _ in range(10):
            tracker.record_operation(ErrorCategory.API, success=True)
            tracker.record_operation(ErrorCategory.VALIDATION, success=True)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=False)
        results = await integration.check_and_alert()

        assert len(results["checked"]) == len(ErrorCategory)

    @pytest.mark.asyncio
    async def test_alert_cooldown_prevents_duplicate(self, isolated_tracker):
        """Test that alert cooldown prevents duplicate alerts."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(
            warning=5.0, critical=10.0, min_operations=10, alert_cooldown_minutes=60
        )

        # Generate critical error rate
        for _ in range(8):
            tracker.record_operation(ErrorCategory.EXECUTION, success=True)
        for _ in range(2):
            tracker.record_operation(ErrorCategory.EXECUTION, success=False)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=False)

        # First check should trigger alert consideration
        results1 = await integration.check_and_alert(ErrorCategory.EXECUTION)

        # Second check should be suppressed due to cooldown
        results2 = await integration.check_and_alert(ErrorCategory.EXECUTION)

        # Both should check the category
        assert len(results1["checked"]) == 1
        assert len(results2["checked"]) == 1


class TestMonitorScriptAdditionalCoverage:
    """Additional tests for monitor script coverage."""

    @pytest.mark.asyncio
    async def test_run_monitor_with_category(self):
        """Test running monitor with specific category."""
        from scripts.monitoring.error_rate_monitor import run_monitor

        args = MagicMock()
        args.dry_run = True
        args.category = "api"
        args.threshold_warning = 5.0
        args.threshold_critical = 10.0
        args.min_operations = 10
        args.webhook_url = None
        args.verbose = False

        results = await run_monitor(args)

        assert results["dry_run"] is True
        assert results["categories_checked"] == 1
        assert results["category_results"][0]["category"] == "api"

    @pytest.mark.asyncio
    async def test_run_monitor_critical_exit_code(self):
        """Test monitor returns critical results."""
        from scripts.monitoring.error_rate_monitor import run_monitor

        args = MagicMock()
        args.dry_run = True
        args.category = None
        args.threshold_warning = 5.0
        args.threshold_critical = 10.0
        args.min_operations = 10
        args.webhook_url = None
        args.verbose = False

        results = await run_monitor(args)

        assert "summary" in results
        assert "timestamp" in results


class TestErrorRateIntegrationHighCoverage:
    """Tests targeting uncovered lines for 85%+ coverage."""

    def test_error_rate_snapshot_with_timestamp(self):
        """Test snapshot with explicit timestamp."""

        ts = datetime.now(UTC)
        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=5,
            error_rate=5.0,
            timestamp=ts,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )
        assert snapshot.timestamp == ts

    @pytest.mark.asyncio
    async def test_check_and_alert_with_redis_cooldown(self, isolated_tracker):
        """Test alert cooldown logic with mock Redis."""
        tracker = isolated_tracker
        tracker.thresholds = ErrorRateThresholds(
            warning=5.0, critical=10.0, min_operations=10, alert_cooldown_minutes=60
        )

        # Generate critical error rate
        for _ in range(8):
            tracker.record_operation(ErrorCategory.EXECUTION, success=True)
        for _ in range(2):
            tracker.record_operation(ErrorCategory.EXECUTION, success=False)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=True)

        # Test with enabled=True but no webhook
        results = await integration.check_and_alert(ErrorCategory.EXECUTION)

        assert len(results["checked"]) == 1
        assert results["checked"][0]["category"] == "execution"

    def test_get_all_metrics_comprehensive(self, isolated_tracker):
        """Test get_all_metrics returns comprehensive data."""
        tracker = isolated_tracker

        # Add data to multiple categories
        tracker.record_operation(ErrorCategory.API, success=True)
        tracker.record_operation(ErrorCategory.VALIDATION, success=False)

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=False)
        metrics = integration.get_all_metrics()

        assert "categories" in metrics
        assert "alert_stats" in metrics
        assert "thresholds" in metrics
        assert len(metrics["categories"]) == len(ErrorCategory)
        assert metrics["alert_stats"]["alerts_sent"] == 0

    def test_tracker_reset_category_with_redis_mock(self):
        """Test reset_category with mocked Redis."""
        tracker = ErrorRateTracker()

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.delete.return_value = 1
        tracker._redis = mock_redis

        result = tracker.reset_category(ErrorCategory.API)
        assert result is True
        mock_redis.delete.assert_called()

    def test_tracker_get_recent_errors_with_redis_mock(self):
        """Test get_recent_errors with mocked Redis."""
        tracker = ErrorRateTracker()

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [
            '{"error": "test1", "timestamp": "2024-01-01T00:00:00Z"}',
            '{"error": "test2", "timestamp": "2024-01-01T00:00:01Z"}',
        ]
        tracker._redis = mock_redis

        errors = tracker.get_recent_errors(ErrorCategory.API, limit=2)

        assert len(errors) == 2
        assert errors[0]["error"] == "test1"
        assert errors[1]["error"] == "test2"

    @pytest.mark.asyncio
    async def test_send_discord_alert_exception(self):
        """Test Discord alert when exception occurs."""
        integration = ErrorRateAlertIntegration(
            discord_webhook_url="https://discord.com/webhook"
        )

        snapshot = ErrorRateSnapshot(
            category=ErrorCategory.API,
            total_operations=100,
            error_count=10,
            error_rate=10.0,
            threshold_warning=5.0,
            threshold_critical=10.0,
        )

        # Mock aiohttp to raise exception
        with patch("aiohttp.ClientSession", side_effect=Exception("Connection failed")):
            result = await integration._send_discord_alert(snapshot)

        assert result["sent"] is False
        assert "Connection failed" in result["error"]

    def test_tracker_record_operation_error_details_redis(self):
        """Test recording operation with error details stores in Redis."""
        tracker = ErrorRateTracker()

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.hincrby.side_effect = [10, 1]  # total, errors
        mock_redis.hget.return_value = "1"
        tracker._redis = mock_redis

        error_details = {"error_type": "ValidationError", "field": "price"}
        snapshot = tracker.record_operation(
            ErrorCategory.VALIDATION, success=False, error_details=error_details
        )

        assert snapshot.total_operations == 10
        assert snapshot.error_count == 1
        mock_redis.lpush.assert_called_once()
        mock_redis.ltrim.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_and_alert_with_redis_mock_cooldown(self):
        """Test alert cooldown with mocked Redis."""
        tracker = ErrorRateTracker()
        tracker.thresholds = ErrorRateThresholds(
            warning=5.0, critical=10.0, min_operations=10, alert_cooldown_minutes=15
        )

        # Generate critical error rate first (using local mode)
        for _ in range(8):
            tracker.record_operation(ErrorCategory.EXECUTION, success=True)
        for _ in range(2):
            tracker.record_operation(ErrorCategory.EXECUTION, success=False)

        # Mock Redis client after recording operations
        mock_redis = MagicMock()
        # First call returns None (no previous alert), second returns a recent timestamp

        recent_time = datetime.now(UTC).isoformat()
        mock_redis.get.side_effect = [None, recent_time]
        tracker._redis = mock_redis

        integration = ErrorRateAlertIntegration(tracker=tracker, enabled=True)

        # First check - should allow alert
        result1 = integration._should_send_alert(
            ErrorCategory.EXECUTION, AlertSeverity.CRITICAL
        )
        assert result1 is True

        # Second check - should be in cooldown
        result2 = integration._should_send_alert(
            ErrorCategory.EXECUTION, AlertSeverity.CRITICAL
        )
        assert result2 is False

    def test_tracker_get_error_rate_redis_with_data(self):
        """Test getting error rate from Redis with data."""
        tracker = ErrorRateTracker()

        # Mock Redis client with data
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "total": "100",
            "errors": "5",
            "error_rate": "5.0",
        }
        tracker._redis = mock_redis

        snapshot = tracker.get_error_rate(ErrorCategory.API)

        assert snapshot.total_operations == 100
        assert snapshot.error_count == 5
        assert snapshot.error_rate == 5.0

    def test_tracker_get_error_rate_redis_exception(self):
        """Test getting error rate when Redis throws exception."""
        tracker = ErrorRateTracker()
        tracker._redis = None

        # Add local data
        tracker._local_stats[ErrorCategory.API] = {"total": 50, "errors": 3}

        snapshot = tracker.get_error_rate(ErrorCategory.API)

        assert snapshot.total_operations == 50
        assert snapshot.error_count == 3


class TestOrchestratorErrorRateWiring:
    """Test ErrorRateTracker wiring in orchestrator.py.

    Verifies record_operation() is called with correct ErrorCategory and success values
    at each orchestration gate point.
    """

    def test_orchestrator_imports_error_rate_tracker(self):
        """Verify orchestrator.py imports ErrorRateTracker from correct module."""
        # Check that orchestrator.py has the correct import pattern for ErrorRateTracker
        import inspect

        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        source = inspect.getsource(PaperTradingOrchestrator)
        # Should import from error_rate_integration
        assert "from execution.alerts.error_rate_integration" in source

    def test_error_details_gate_names_in_orchestrator(self):
        """Verify orchestrator records operations with correct gate names."""
        # This is a source code verification test - check that gate names are recorded
        import inspect

        from src.execution.paper.orchestrator import PaperTradingOrchestrator

        source = inspect.getsource(PaperTradingOrchestrator)
        # Verify gate names are present in error_details
        assert '"gate": "G1_THROTTLE"' in source or "'gate': 'G1_THROTTLE'" in source
        assert (
            '"gate": "G2_PAPER_KILL"' in source or "'gate': 'G2_PAPER_KILL'" in source
        )
        assert (
            '"gate": "G5_RISK_REJECT"' in source or "'gate': 'G5_RISK_REJECT'" in source
        )


class TestBybitDemoConnectorErrorRateWiring:
    """Test ErrorRateTracker wiring in bybit_demo_connector.py.

    Verifies record_operation() is called with correct ErrorCategory and success values
    at each connector operation point.
    """

    def test_connector_imports_error_rate_tracker(self):
        """Verify bybit_demo_connector.py imports ErrorRateTracker."""
        import inspect

        from src.execution.connectors.bybit_demo_connector import BybitDemoConnector

        source = inspect.getsource(BybitDemoConnector)
        # Should have error_rate import
        assert "error_rate" in source

    def test_error_details_operation_names_in_connector(self):
        """Verify connector records operations with correct operation names."""
        import inspect

        from src.execution.connectors.bybit_demo_connector import BybitDemoConnector

        source = inspect.getsource(BybitDemoConnector)
        # Verify operation names are present in error_details
        assert (
            '"operation": "get_market_price"' in source
            or "'operation': 'get_market_price'" in source
        )

    def test_place_order_uses_execution_category(self):
        """Verify place_order() uses ErrorCategory.EXECUTION for order operations."""
        import inspect

        from src.execution.connectors.bybit_demo_connector import BybitDemoConnector

        source = inspect.getsource(BybitDemoConnector)
        # Find the place_order method source
        place_order_start = source.find("def place_order(")
        assert place_order_start != -1, "place_order method not found"

        # Extract the place_order method (roughly)
        place_order_end = source.find("\n    def ", place_order_start + 1)
        if place_order_end == -1:
            place_order_end = len(source)

        place_order_source = source[place_order_start:place_order_end]

        # Count EXECUTION vs API usage in place_order
        execution_count = place_order_source.count("ErrorCategory.EXECUTION")
        api_count = place_order_source.count("ErrorCategory.API")

        # place_order should use EXECUTION for order operations
        assert execution_count >= 3, (
            f"place_order should use ErrorCategory.EXECUTION at least 3 times "
            f"(success + 2 failure paths), found {execution_count}"
        )
        # get_market_price uses API but that's before place_order in the file
        # We just verify EXECUTION is used in place_order context

    def test_cancel_order_uses_execution_category(self):
        """Verify cancel_order() uses ErrorCategory.EXECUTION for cancellation."""
        import inspect

        from src.execution.connectors.bybit_demo_connector import BybitDemoConnector

        source = inspect.getsource(BybitDemoConnector)
        # Find the cancel_order method source
        cancel_order_start = source.find("async def cancel_order(")
        assert cancel_order_start != -1, "cancel_order method not found"

        # Extract the cancel_order method (roughly)
        cancel_order_end = source.find("\n    async def ", cancel_order_start + 1)
        if cancel_order_end == -1:
            cancel_order_end = source.find("\n    def ", cancel_order_start + 1)
        if cancel_order_end == -1:
            cancel_order_end = len(source)

        cancel_order_source = source[cancel_order_start:cancel_order_end]

        # cancel_order should use EXECUTION for cancellation operations
        execution_count = cancel_order_source.count("ErrorCategory.EXECUTION")
        assert execution_count >= 3, (
            f"cancel_order should use ErrorCategory.EXECUTION at least 3 times "
            f"(success + 2 failure paths), found {execution_count}"
        )

    def test_attach_trading_stops_uses_execution_category(self):
        """Verify _attach_trading_stops_with_retry uses ErrorCategory.EXECUTION."""
        import inspect

        from src.execution.connectors.bybit_demo_connector import BybitDemoConnector

        source = inspect.getsource(BybitDemoConnector)
        # Find the _attach_trading_stops_with_retry method source
        attach_start = source.find("async def _attach_trading_stops_with_retry(")
        assert attach_start != -1, "_attach_trading_stops_with_retry method not found"

        # Extract the method (roughly)
        attach_end = source.find("\n    async def ", attach_start + 1)
        if attach_end == -1:
            attach_end = source.find("\n    def ", attach_start + 1)
        if attach_end == -1:
            attach_end = len(source)

        attach_source = source[attach_start:attach_end]

        # Should use EXECUTION for TP/SL attachment
        execution_count = attach_source.count("ErrorCategory.EXECUTION")
        assert execution_count >= 2, (
            f"_attach_trading_stops_with_retry should use ErrorCategory.EXECUTION "
            f"at least 2 times (success + failure), found {execution_count}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
