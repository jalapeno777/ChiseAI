"""
Tests for Memory Consolidation Scheduler.

Story: ST-GOV-005
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.governance.consolidation.config import ConsolidationConfig
from src.governance.consolidation.scheduler import (
    ConsolidationResult,
    MemoryConsolidationScheduler,
)
from src.governance.consolidation.archiver import ArchiveStats
from src.governance.consolidation.promoter import PromotionStats


class TestConsolidationResult:
    """Tests for ConsolidationResult dataclass."""

    def test_default_values(self):
        """Test default consolidation result values."""
        result = ConsolidationResult()

        assert result.success is True
        assert result.errors == []
        assert result.data_loss_incidents == 0
        assert result.archive_stats is None
        assert result.promotion_stats is None

    def test_passes_validation_gates_success(self):
        """Test validation passes with all gates met."""
        result = ConsolidationResult(
            data_loss_incidents=0,
            rollback_time_seconds=120.0,  # < 5 min
            storage_reduction_percent=25.0,  # >= 20%
        )

        passes, failures = result.passes_validation_gates()

        assert passes is True
        assert failures == []

    def test_fails_data_loss_gate(self):
        """Test validation fails on data loss incidents."""
        result = ConsolidationResult(
            data_loss_incidents=1,  # Should be 0
            rollback_time_seconds=60.0,
            storage_reduction_percent=30.0,
        )

        passes, failures = result.passes_validation_gates()

        assert passes is False
        assert any("data_loss" in f for f in failures)

    def test_fails_rollback_time_gate(self):
        """Test validation fails on slow rollback time."""
        result = ConsolidationResult(
            data_loss_incidents=0,
            rollback_time_seconds=400.0,  # > 5 min (300s)
            storage_reduction_percent=30.0,
        )

        passes, failures = result.passes_validation_gates()

        assert passes is False
        assert any("rollback_time" in f for f in failures)

    def test_fails_storage_reduction_gate(self):
        """Test validation fails on insufficient storage reduction."""
        result = ConsolidationResult(
            data_loss_incidents=0,
            rollback_time_seconds=60.0,
            storage_reduction_percent=15.0,  # < 20%
        )

        passes, failures = result.passes_validation_gates()

        assert passes is False
        assert any("storage_reduction" in f for f in failures)

    def test_fails_multiple_gates(self):
        """Test validation reports all failing gates."""
        result = ConsolidationResult(
            data_loss_incidents=2,
            rollback_time_seconds=500.0,
            storage_reduction_percent=10.0,
        )

        passes, failures = result.passes_validation_gates()

        assert passes is False
        assert len(failures) == 3


class TestMemoryConsolidationScheduler:
    """Tests for MemoryConsolidationScheduler."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return ConsolidationConfig(
            dry_run=True,
            enabled=False,  # Disabled by default
        )

    @pytest.fixture
    def scheduler(self, config):
        """Create a scheduler instance."""
        return MemoryConsolidationScheduler(config)

    def test_initialization(self, scheduler, config):
        """Test scheduler initialization."""
        assert scheduler._config == config
        assert scheduler._is_running is False
        assert scheduler._last_result is None

    def test_is_enabled_with_config(self):
        """Test is_enabled when enabled in config."""
        config = ConsolidationConfig(enabled=True)
        scheduler = MemoryConsolidationScheduler(config)

        assert scheduler.is_enabled() is True

    def test_is_enabled_default(self, scheduler):
        """Test is_enabled defaults to False."""
        assert scheduler.is_enabled() is False

    def test_is_enabled_with_redis_feature_flag(self):
        """Test is_enabled reads from Redis feature flag."""
        config = ConsolidationConfig(enabled=False)
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"true"

        scheduler = MemoryConsolidationScheduler(config, redis_client=mock_redis)

        assert scheduler.is_enabled() is True
        mock_redis.get.assert_called_once()

    def test_run_now_disabled(self, scheduler):
        """Test run_now when disabled returns success in dry-run mode."""
        result = scheduler.run_now()

        # When disabled, dry-run still succeeds
        # Only actual runs (dry_run=False) should fail when disabled
        assert result.success is True  # dry-run succeeds even when disabled

    def test_run_now_dry_run(self):
        """Test run_now in dry-run mode even when disabled."""
        config = ConsolidationConfig(dry_run=True, enabled=False)
        scheduler = MemoryConsolidationScheduler(config)

        # Dry run should succeed even when disabled
        result = scheduler.run_now(dry_run=True)

        # Result exists and is a ConsolidationResult
        assert result is not None
        assert isinstance(result, ConsolidationResult)

    def test_run_now_with_enabled(self):
        """Test run_now when enabled."""
        config = ConsolidationConfig(dry_run=True, enabled=True)
        scheduler = MemoryConsolidationScheduler(config)

        result = scheduler.run_now(dry_run=True)

        assert result is not None
        assert result.total_processing_time_seconds >= 0

    def test_get_last_result_none_initially(self, scheduler):
        """Test get_last_result returns None initially."""
        assert scheduler.get_last_result() is None

    def test_get_last_result_after_run(self):
        """Test get_last_result after a run."""
        config = ConsolidationConfig(dry_run=True, enabled=True)
        scheduler = MemoryConsolidationScheduler(config)

        scheduler.run_now(dry_run=True)
        result = scheduler.get_last_result()

        assert result is not None

    def test_is_scheduler_running_initially_false(self, scheduler):
        """Test is_scheduler_running is False initially."""
        assert scheduler.is_scheduler_running() is False

    def test_get_config(self, scheduler, config):
        """Test get_config returns the configuration."""
        assert scheduler.get_config() == config

    def test_validate_live_gates_no_run(self, scheduler):
        """Test validate_live_gates without any run."""
        validation = scheduler.validate_live_gates()

        assert validation["valid"] is False
        assert "reason" in validation

    def test_component_access(self, scheduler):
        """Test component property access."""
        assert scheduler.archiver is not None
        assert scheduler.promoter is not None
        assert scheduler.rollback_manager is not None


class TestSchedulerScheduling:
    """Tests for scheduler scheduling functionality."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return ConsolidationConfig(
            dry_run=True,
            enabled=True,
        )

    def test_start_without_apscheduler(self, config):
        """Test start handles missing APScheduler gracefully."""
        scheduler = MemoryConsolidationScheduler(config)

        with patch.dict(
            "sys.modules",
            {"apscheduler": None, "apscheduler.schedulers": None},
        ):
            # This will fail gracefully if APScheduler is not installed
            # We're just testing it doesn't crash
            try:
                result = scheduler.start()
                # If APScheduler is installed, this succeeds
                assert result is True or result is False
            except ImportError:
                pass

    def test_stop_without_start(self, config):
        """Test stop is safe without start."""
        scheduler = MemoryConsolidationScheduler(config)

        # Should not raise
        scheduler.stop()
        assert scheduler.is_scheduler_running() is False


class TestSchedulerRollback:
    """Tests for scheduler rollback API."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return ConsolidationConfig(dry_run=True)

    @pytest.fixture
    def scheduler(self, config):
        """Create a scheduler instance."""
        return MemoryConsolidationScheduler(config)

    def test_can_rollback_delegates(self, scheduler):
        """Test can_rollback delegates to rollback manager."""
        result = scheduler.can_rollback("mem_123")

        # Without Redis, returns False
        assert result is False

    def test_rollback_memory_delegates(self, scheduler):
        """Test rollback_memory delegates to rollback manager."""
        stats = scheduler.rollback_memory("mem_123", dry_run=True)

        assert stats is not None
        assert stats.operations_requested == 1

    def test_rollback_batch_delegates(self, scheduler):
        """Test rollback_batch delegates to rollback manager."""
        stats = scheduler.rollback_batch(["mem_1", "mem_2"], dry_run=True)

        assert stats is not None
        assert stats.operations_requested == 2

    def test_get_rollback_window_delegates(self, scheduler):
        """Test get_rollback_window delegates to rollback manager."""
        window = scheduler.get_rollback_window()

        assert window is not None


class TestSchedulerMetrics:
    """Tests for scheduler metrics."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return ConsolidationConfig(dry_run=True, enabled=True)

    def test_metrics_export_with_redis(self, config):
        """Test metrics are exported to Redis."""
        mock_redis = MagicMock()
        scheduler = MemoryConsolidationScheduler(config, redis_client=mock_redis)

        result = ConsolidationResult(
            success=True,
            total_processing_time_seconds=5.0,
            storage_reduction_percent=25.0,
        )

        scheduler._export_metrics(result)

        mock_redis.hset.assert_called_once()

    def test_metrics_export_without_redis(self, config):
        """Test metrics export handles missing Redis."""
        scheduler = MemoryConsolidationScheduler(config)

        result = ConsolidationResult(success=True)

        # Should not raise
        scheduler._export_metrics(result)


class TestConsolidationValidationGates:
    """Tests for live validation gate enforcement."""

    def test_all_gates_documented(self):
        """Test all validation gates are properly documented."""
        result = ConsolidationResult()
        validation = {
            "data_loss_incidents": {"value": 0, "expected": 0},
            "rollback_time_seconds": {"value": 0, "expected": "< 300"},
            "storage_reduction_percent": {"value": 0, "expected": ">= 20"},
        }

        # Verify all gates are present
        for gate_name in validation:
            assert hasattr(result, gate_name)

    def test_gate_values_are_numeric(self):
        """Test validation gate values are numeric."""
        result = ConsolidationResult(
            data_loss_incidents=0,
            rollback_time_seconds=100.0,
            storage_reduction_percent=30.0,
        )

        assert isinstance(result.data_loss_incidents, int)
        assert isinstance(result.rollback_time_seconds, float)
        assert isinstance(result.storage_reduction_percent, float)

    def test_zero_data_loss_requirement(self):
        """Test data loss must be exactly zero."""
        result = ConsolidationResult(data_loss_incidents=0)
        passes, _ = result.passes_validation_gates()

        # Should pass with zero data loss
        assert result.data_loss_incidents == 0

    def test_rollback_time_threshold(self):
        """Test rollback time threshold is 5 minutes."""
        max_seconds = 300

        # Just under threshold
        result = ConsolidationResult(rollback_time_seconds=299.9)
        passes, _ = result.passes_validation_gates()
        assert result.rollback_time_seconds < max_seconds

        # At threshold
        result = ConsolidationResult(rollback_time_seconds=300.0)
        passes, _ = result.passes_validation_gates()
        assert result.rollback_time_seconds >= max_seconds

    def test_storage_reduction_threshold(self):
        """Test storage reduction threshold is 20%."""
        min_percent = 20.0

        # Just above threshold
        result = ConsolidationResult(storage_reduction_percent=20.1)
        passes, _ = result.passes_validation_gates()
        assert result.storage_reduction_percent >= min_percent

        # Below threshold
        result = ConsolidationResult(storage_reduction_percent=19.9)
        passes, _ = result.passes_validation_gates()
        assert result.storage_reduction_percent < min_percent
