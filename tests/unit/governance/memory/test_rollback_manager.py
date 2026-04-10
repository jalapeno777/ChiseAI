"""
Unit tests for rollback_manager.py.

Tests per-metric 3-consecutive-day breach detection and R1 invariant preservation.
"""

from unittest.mock import MagicMock, patch

# Import the module under test
from src.governance.memory.rollback_manager import (
    KILL_CRITERIA,
    REDIS_METRIC_BREACH_COUNT_KEY,
    REDIS_METRIC_PREFIX,
    ObserverFabricationError,
    ObserverInformationLoss,
    ObserverInsufficientCompression,
    ObserverNoImprovement,
    _get_metric_value,
    _is_breaching,
    check_rollback_conditions,
    get_metric_status,
    increment_breach_count,
    reset_breach_count,
    set_memory_hybrid_enabled,
    set_metric_value,
)


class TestKillCriteriaDefined:
    """AC1: Verify kill criteria structure."""

    def test_all_metrics_have_consecutive_days(self):
        """All metrics must define consecutive_days = 3."""
        for metric_name, criteria in KILL_CRITERIA.items():
            assert "consecutive_days" in criteria
            assert (
                criteria["consecutive_days"] == 3
            ), f"{metric_name} must have consecutive_days=3"

    def test_fp_rate_threshold_defined(self):
        """FP rate kill threshold must be 0.15."""
        assert KILL_CRITERIA["fp_rate"]["kill_threshold"] == 0.15
        assert KILL_CRITERIA["fp_rate"]["threshold"] == 0.05

    def test_compression_ratio_threshold_defined(self):
        """Compression ratio kill threshold must be 0.2."""
        assert KILL_CRITERIA["compression_ratio"]["kill_threshold"] == 0.2
        assert KILL_CRITERIA["compression_ratio"]["threshold"] == 0.4

    def test_information_retention_threshold_defined(self):
        """Information retention kill threshold must be 0.60."""
        assert KILL_CRITERIA["information_retention"]["kill_threshold"] == 0.60
        assert KILL_CRITERIA["information_retention"]["threshold"] == 0.80


class TestIsBreachingLogic:
    """Test breach detection logic per metric type."""

    def test_fp_rate_breaches_when_above_threshold(self):
        """FP rate > 0.15 means breaching."""
        assert _is_breaching("fp_rate", 0.20, 0.15) is True
        assert _is_breaching("fp_rate", 0.10, 0.15) is False

    def test_compression_ratio_breaches_when_above_threshold(self):
        """Compression ratio > 0.2 means breaching."""
        assert _is_breaching("compression_ratio", 0.25, 0.2) is True
        assert _is_breaching("compression_ratio", 0.15, 0.2) is False

    def test_information_retention_breaches_when_below_threshold(self):
        """Information retention < 0.60 means breaching."""
        assert _is_breaching("information_retention", 0.50, 0.60) is True
        assert _is_breaching("information_retention", 0.70, 0.60) is False

    def test_recall_accuracy_breaches_when_below_threshold(self):
        """Recall accuracy < threshold means breaching."""
        assert _is_breaching("recall_accuracy", 0.55, 0.70) is True
        assert _is_breaching("recall_accuracy", 0.80, 0.70) is False


class TestGetMetricStatus:
    """Test get_metric_status function."""

    @patch("src.governance.memory.rollback_manager._get_metric_value")
    def test_returns_none_value_when_unavailable(self, mock_get_value):
        """If metric value is None, status shows no breach."""
        mock_get_value.return_value = None

        status = get_metric_status("fp_rate")

        assert status["value"] is None
        assert status["breaching"] is False

    @patch("src.governance.memory.rollback_manager._get_metric_value")
    def test_returns_breaching_when_above_threshold(self, mock_get_value):
        """FP rate > kill_threshold means breaching."""
        mock_get_value.return_value = 0.20

        status = get_metric_status("fp_rate")

        assert status["value"] == 0.20
        assert status["breaching"] is True

    @patch("src.governance.memory.rollback_manager._get_metric_value")
    def test_returns_not_breaching_when_below_threshold(self, mock_get_value):
        """FP rate < kill_threshold means not breaching."""
        mock_get_value.return_value = 0.10

        status = get_metric_status("fp_rate")

        assert status["value"] == 0.10
        assert status["breaching"] is False


class TestCheckRollbackConditions:
    """AC1 & AC2: Test 3-day breach detection for rollback triggering."""

    @patch("src.governance.memory.rollback_manager._get_breach_count")
    @patch("src.governance.memory.rollback_manager._get_metric_value")
    @patch("src.governance.memory.rollback_manager._set_memory_hybrid_disabled")
    def test_3_day_breach_triggers_rollback(
        self, mock_set_disabled, mock_get_value, mock_breach_count
    ):
        """
        AC1: Per-metric 3-consecutive-day breach triggers rollback.

        When a metric breaches for 3 consecutive days, should_rollback = True.
        """
        # Mock: FP rate at 0.20 (> 0.15 kill threshold) for 3+ days
        mock_get_value.return_value = 0.20
        mock_breach_count.return_value = 3

        should_rollback, breached = check_rollback_conditions()

        assert should_rollback is True
        assert len(breached) > 0
        assert any("fp_rate" in m for m in breached)

    @patch("src.governance.memory.rollback_manager._get_breach_count")
    @patch("src.governance.memory.rollback_manager._get_metric_value")
    @patch("src.governance.memory.rollback_manager._set_memory_hybrid_disabled")
    def test_1_day_breach_does_not_trigger_rollback(
        self, mock_set_disabled, mock_get_value, mock_breach_count
    ):
        """
        AC2: Single-day breach does NOT trigger rollback.

        When a metric breaches for only 1 day, should_rollback = False.
        """
        # Mock: FP rate at 0.20 (> 0.15 kill threshold) but only 1 day
        mock_get_value.return_value = 0.20
        mock_breach_count.return_value = 1

        should_rollback, breached = check_rollback_conditions()

        assert should_rollback is False
        assert len(breached) == 0

    @patch("src.governance.memory.rollback_manager._get_breach_count")
    @patch("src.governance.memory.rollback_manager._get_metric_value")
    @patch("src.governance.memory.rollback_manager._set_memory_hybrid_disabled")
    def test_2_day_breach_does_not_trigger_rollback(
        self, mock_set_disabled, mock_get_value, mock_breach_count
    ):
        """
        AC2: Two consecutive days is still insufficient for rollback.

        Only 3+ consecutive days triggers rollback.
        """
        mock_get_value.return_value = 0.20
        mock_breach_count.return_value = 2

        should_rollback, breached = check_rollback_conditions()

        assert should_rollback is False

    @patch("src.governance.memory.rollback_manager._get_breach_count")
    @patch("src.governance.memory.rollback_manager._get_metric_value")
    @patch("src.governance.memory.rollback_manager._set_memory_hybrid_disabled")
    def test_no_breach_returns_false(
        self, mock_set_disabled, mock_get_value, mock_breach_count
    ):
        """When no metrics are breaching, should_rollback = False."""
        mock_get_value.return_value = 0.05  # Below kill threshold
        mock_breach_count.return_value = 0

        should_rollback, breached = check_rollback_conditions()

        assert should_rollback is False
        assert len(breached) == 0

    @patch("src.governance.memory.rollback_manager._get_breach_count")
    @patch("src.governance.memory.rollback_manager._get_metric_value")
    @patch("src.governance.memory.rollback_manager._set_memory_hybrid_disabled")
    def test_disables_hybrid_on_rollback(
        self, mock_set_disabled, mock_get_value, mock_breach_count
    ):
        """AC4: When rollback triggers, MEMORY_HYBRID_ENABLED is set to False."""
        mock_get_value.return_value = 0.20
        mock_breach_count.return_value = 3

        check_rollback_conditions()

        mock_set_disabled.assert_called_once()


class TestR1InvariantPreservation:
    """
    AC3: R1 invariant preservation test.

    The rollback manager must NEVER compute staleness at query time.
    All staleness values must be precomputed and stored in Redis/Qdrant.
    """

    def test_get_metric_status_reads_only_from_redis_no_timedelta(self):
        """
        Verify _get_metric_value only reads from Redis, never computes.

        R1 invariant: no datetime.now(), timedelta, or age calculation at query time.
        """
        import inspect

        source = inspect.getsource(_get_metric_value)

        # Should NOT have any time computation patterns
        assert "datetime.now" not in source, "datetime.now detected - R1 violation"
        assert (
            "datetime.utcnow" not in source
        ), "datetime.utcnow detected - R1 violation"
        assert "timedelta" not in source, "timedelta detected - R1 violation"
        assert (
            "updated_at" not in source
        ), "updated_at calculation detected - R1 violation"
        assert "(now" not in source, "(now detected - R1 violation"

    def test_check_rollback_conditions_has_no_staleness_compute_calls(self):
        """
        Verify check_rollback_conditions source contains no staleness compute calls.
        """
        import inspect

        source = inspect.getsource(check_rollback_conditions)

        # Should not have any staleness compute calls
        assert "_compute_staleness" not in source
        assert "compute_staleness" not in source
        assert "staleness_score" not in source  # We READ, don't compute

    def test_rollback_manager_does_not_call_staleness_compute(self):
        """
        Verify that the rollback manager never calls staleness compute functions.

        This is the critical AC3 test: the source code inspection tests prove
        that no staleness compute functions are called. We verify via source
        inspection rather than runtime patching to avoid recursion issues.
        """
        # This test verifies R1 compliance through source inspection.
        # The other tests (test_get_metric_status_reads_only_from_redis_no_timedelta
        # and test_check_rollback_conditions_has_no_staleness_compute_calls)
        # already prove this by inspecting the actual source code.
        # If those pass, this invariant is preserved.
        import inspect

        # Verify the entire module source doesn't call staleness compute
        import src.governance.memory.rollback_manager as rm_module

        module_source = inspect.getsource(rm_module)

        # The module should NOT have any staleness compute calls
        assert (
            "compute_staleness" not in module_source
        ), "Staleness compute found in module - R1 violation"
        assert (
            "StalenessComputeError" not in module_source
        ), "StalenessComputeError imported/called - may indicate staleness compute"


class TestSetMemoryHybridEnabled:
    """Test MEMORY_HYBRID_ENABLED feature flag control."""

    @patch("src.config.feature_flags.FeatureFlags.set_memory_hybrid_enabled")
    def test_set_memory_hybrid_enabled_calls_feature_flag(self, mock_set_enabled):
        """set_memory_hybrid_enabled delegates to FeatureFlags.set_memory_hybrid_enabled."""
        set_memory_hybrid_enabled(False)

        mock_set_enabled.assert_called_once_with(False)

    @patch("src.config.feature_flags.FeatureFlags.set_memory_hybrid_enabled")
    def test_set_memory_hybrid_enabled_can_enable(self, mock_set_enabled):
        """set_memory_hybrid_enabled can also enable the flag."""
        set_memory_hybrid_enabled(True)

        mock_set_enabled.assert_called_once_with(True)


class TestRedisKeyPatterns:
    """Test Redis key patterns used by rollback manager."""

    def test_redis_metric_prefix_defined(self):
        """REDIS_METRIC_PREFIX must be defined."""
        assert REDIS_METRIC_PREFIX is not None
        assert "bmad" in REDIS_METRIC_PREFIX.lower()

    def test_breach_count_key_format(self):
        """Breach count key must include metric_name placeholder."""
        key = REDIS_METRIC_BREACH_COUNT_KEY.format(metric_name="fp_rate")
        assert "fp_rate" in key


class TestIncrementBreachCount:
    """Test breach count management functions."""

    @patch("redis.Redis")
    def test_increment_breach_count_returns_new_count(self, mock_redis_class):
        """increment_breach_count returns the new count after increment."""
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client
        mock_client.incr.return_value = 4

        result = increment_breach_count("fp_rate")

        assert result == 4
        mock_client.incr.assert_called_once()
        mock_client.expire.assert_called_once()

    @patch("redis.Redis")
    def test_increment_breach_count_handles_redis_error(self, mock_redis_class):
        """increment_breach_count returns 0 on Redis error."""
        import redis

        mock_redis_class.side_effect = redis.RedisError("Connection failed")

        result = increment_breach_count("fp_rate")

        assert result == 0


class TestResetBreachCount:
    """Test breach count reset function."""

    @patch("redis.Redis")
    def test_reset_breach_count_deletes_key(self, mock_redis_class):
        """reset_breach_count deletes the breach count key."""
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client

        reset_breach_count("fp_rate")

        mock_client.delete.assert_called_once()


class TestSetMetricValue:
    """Test metric value setter function."""

    @patch("redis.Redis")
    def test_set_metric_value_stores_value(self, mock_redis_class):
        """set_metric_value stores the metric value in Redis."""
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client

        set_metric_value("fp_rate", 0.15)

        # Verify set was called with the metric key
        calls = mock_client.set.call_args_list
        # First call should be for the value
        assert len(calls) >= 1
        # Check that one call has the metric name in the key
        keys = [str(c) for c in calls]
        assert any(
            "fp_rate:current" in k for k in keys
        ), f"Expected key with fp_rate:current, got {keys}"


class TestExceptionClasses:
    """Test kill criterion exception classes are defined."""

    def test_observer_fabrication_error_exists(self):
        """ObserverFabricationError must be defined."""
        assert ObserverFabricationError is not None
        assert issubclass(ObserverFabricationError, Exception)

    def test_observer_insufficient_compression_exists(self):
        """ObserverInsufficientCompression must be defined."""
        assert ObserverInsufficientCompression is not None

    def test_observer_information_loss_exists(self):
        """ObserverInformationLoss must be defined."""
        assert ObserverInformationLoss is not None

    def test_observer_no_improvement_exists(self):
        """ObserverNoImprovement must be defined."""
        assert ObserverNoImprovement is not None


# Run with: pytest tests/unit/governance/memory/test_rollback_manager.py -v
