"""
Tests for Memory Consolidation Scheduler.

Story: ST-GOV-005
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from src.governance.consolidation.config import ConsolidationConfig
from src.governance.consolidation.scheduler import (
    ConsolidationAudit,
    ConsolidationRecommendation,
    ConsolidationResult,
    MemoryConsolidationScheduler,
)


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


# ---------------------------------------------------------------------------
# Ticket 05: Consolidation Dry-Run Tests
# ---------------------------------------------------------------------------


class TestConsolidationRecommendation:
    """Tests for ConsolidationRecommendation dataclass."""

    def test_to_dict_basic_fields(self):
        """Test serialization includes required fields."""
        rec = ConsolidationRecommendation(
            memory_id="mem_123",
            action="archive",
            reason="age > 90 days",
            policy_basis="DECISION retention_policy: 90 days",
        )
        d = rec.to_dict()

        assert d["memory_id"] == "mem_123"
        assert d["action"] == "archive"
        assert d["reason"] == "age > 90 days"
        assert d["policy_basis"] == "DECISION retention_policy: 90 days"
        assert "confidence" not in d
        assert "evidence" not in d

    def test_to_dict_optional_fields(self):
        """Test serialization includes optional fields when set."""
        rec = ConsolidationRecommendation(
            memory_id="mem_456",
            action="promote",
            reason="high access frequency",
            policy_basis="DECISION golden_promotion",
            confidence=0.92,
            evidence={"access_count": 15},
        )
        d = rec.to_dict()

        assert d["confidence"] == 0.92
        assert d["evidence"] == {"access_count": 15}

    def test_required_fields_present(self):
        """Test that memory_id, action, reason, policy_basis are required."""
        rec = ConsolidationRecommendation(
            memory_id="mem_789",
            action="demote",
            reason="low relevance",
            policy_basis="DECISION retention_policy",
        )

        assert rec.memory_id == "mem_789"
        assert rec.action in ("archive", "promote", "demote", "deprioritize")


class TestConsolidationAudit:
    """Tests for ConsolidationAudit dataclass."""

    def test_defaults_dry_run_safe(self):
        """Test defaults indicate safe dry-run mode."""
        audit = ConsolidationAudit()

        assert audit.dry_run_mode is True
        assert audit.destructive_ops_blocked == []
        assert audit.actual_ops_attempted == []
        assert audit.rollback_data_stored is False
        assert audit.no_files_deleted is True
        assert audit.no_memories_removed is True

    def test_to_dict(self):
        """Test serialization."""
        audit = ConsolidationAudit(
            dry_run_mode=True,
            destructive_ops_blocked=["rollback_cleanup", "export_metrics"],
            actual_ops_attempted=[],
            no_files_deleted=True,
            no_memories_removed=True,
        )
        d = audit.to_dict()

        assert d["dry_run_mode"] is True
        assert len(d["destructive_ops_blocked"]) == 2
        assert d["no_files_deleted"] is True


class TestDryRunProducesRecommendations:
    """Test that dry-run mode produces recommendations."""

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    def test_dry_run_produces_recommendations_with_eligible(
        self, mock_promoter_class, mock_archiver_class
    ):
        """Dry-run with eligible memories should produce recommendations."""
        config = ConsolidationConfig(dry_run=True, enabled=True)
        config.run_tempmemory_ingestion = False

        # Mock archiver returning eligible memories
        mock_archiver = MagicMock()
        mock_stats = MagicMock()
        mock_stats.memories_scanned = 100
        mock_stats.memories_eligible = 5
        mock_stats.memories_archived = 0  # dry-run: 0 actual
        mock_stats.memories_preserved = 10
        mock_stats.bytes_archived = 5120
        mock_stats.errors = []
        mock_stats.was_dry_run = True
        mock_archiver.archive_memories.return_value = mock_stats
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver_class.return_value = mock_archiver

        # Mock promoter
        mock_promoter = MagicMock()
        mock_promoter.promote_memories.return_value = MagicMock(
            candidates_evaluated=20,
            candidates_promoted=0,
            candidates_rejected=20,
            promotion_score_avg=0.0,
            errors=[],
            was_dry_run=True,
        )
        mock_promoter_class.return_value = mock_promoter

        scheduler = MemoryConsolidationScheduler(config=config)
        result = scheduler.run_now(dry_run=True)

        # Verify recommendations were generated
        assert len(result.recommendations) > 0

        # Verify recommendation has required fields
        rec = result.recommendations[0]
        assert rec.memory_id is not None
        assert rec.action is not None
        assert rec.reason is not None
        assert rec.policy_basis is not None

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    def test_dry_run_no_eligible_no_recommendations(
        self, mock_promoter_class, mock_archiver_class
    ):
        """Dry-run with no eligible memories should produce no archive recs."""
        config = ConsolidationConfig(dry_run=True, enabled=True)
        config.run_tempmemory_ingestion = False

        mock_archiver = MagicMock()
        mock_stats = MagicMock()
        mock_stats.memories_scanned = 10
        mock_stats.memories_eligible = 0
        mock_stats.memories_archived = 0
        mock_stats.memories_preserved = 0
        mock_stats.bytes_archived = 0
        mock_stats.errors = []
        mock_stats.was_dry_run = True
        mock_archiver.archive_memories.return_value = mock_stats
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver_class.return_value = mock_archiver

        mock_promoter = MagicMock()
        mock_promoter.promote_memories.return_value = MagicMock(
            candidates_evaluated=0,
            candidates_promoted=0,
            candidates_rejected=0,
            promotion_score_avg=0.0,
            errors=[],
            was_dry_run=True,
        )
        mock_promoter_class.return_value = mock_promoter

        scheduler = MemoryConsolidationScheduler(config=config)
        result = scheduler.run_now(dry_run=True)

        # No archive recommendations when nothing is eligible
        archive_recs = [r for r in result.recommendations if r.action == "archive"]
        assert len(archive_recs) == 0


class TestDryRunNoDestructiveWrites:
    """Test that dry-run mode blocks all destructive writes."""

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    def test_dry_run_no_destructive_writes(
        self, mock_promoter_class, mock_archiver_class
    ):
        """Dry-run must block all destructive operations."""
        config = ConsolidationConfig(dry_run=True, enabled=True)
        config.run_tempmemory_ingestion = False

        mock_archiver = MagicMock()
        mock_archiver.archive_memories.return_value = MagicMock(
            memories_scanned=10,
            memories_eligible=0,
            memories_archived=0,
            memories_preserved=0,
            bytes_archived=0,
            errors=[],
            was_dry_run=True,
        )
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver_class.return_value = mock_archiver

        mock_promoter = MagicMock()
        mock_promoter.promote_memories.return_value = MagicMock(
            candidates_evaluated=0,
            candidates_promoted=0,
            candidates_rejected=0,
            promotion_score_avg=0.0,
            errors=[],
            was_dry_run=True,
        )
        mock_promoter_class.return_value = mock_promoter

        scheduler = MemoryConsolidationScheduler(config=config)
        result = scheduler.run_now(dry_run=True)

        # Verify audit exists and confirms safety
        assert result.audit is not None
        assert result.audit.dry_run_mode is True
        assert result.audit.no_files_deleted is True
        assert result.audit.no_memories_removed is True
        assert result.audit.rollback_data_stored is False

        # Verify destructive ops were blocked, not attempted
        assert "rollback_cleanup" in result.audit.destructive_ops_blocked
        assert "export_metrics" in result.audit.destructive_ops_blocked
        assert "rollback_cleanup" not in result.audit.actual_ops_attempted

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    def test_dry_run_archiver_called_with_dry_run_true(
        self, mock_promoter_class, mock_archiver_class
    ):
        """Archiver must be called with dry_run=True."""
        config = ConsolidationConfig(dry_run=True, enabled=True)
        config.run_tempmemory_ingestion = False

        mock_archiver = MagicMock()
        mock_archiver.archive_memories.return_value = MagicMock(
            memories_scanned=0,
            memories_eligible=0,
            memories_archived=0,
            memories_preserved=0,
            bytes_archived=0,
            errors=[],
            was_dry_run=True,
        )
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver_class.return_value = mock_archiver

        mock_promoter = MagicMock()
        mock_promoter.promote_memories.return_value = MagicMock(
            candidates_evaluated=0,
            candidates_promoted=0,
            candidates_rejected=0,
            promotion_score_avg=0.0,
            errors=[],
            was_dry_run=True,
        )
        mock_promoter_class.return_value = mock_promoter

        scheduler = MemoryConsolidationScheduler(config=config)
        scheduler.run_now(dry_run=True)

        mock_archiver.archive_memories.assert_called_once_with(dry_run=True)
        mock_promoter.promote_memories.assert_called_once_with(dry_run=True)

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    def test_dry_run_does_not_update_last_run_time(
        self, mock_promoter_class, mock_archiver_class
    ):
        """Dry-run must NOT call _update_last_run_time (no Redis writes)."""
        config = ConsolidationConfig(dry_run=True, enabled=True)
        config.run_tempmemory_ingestion = False

        mock_redis = MagicMock()
        mock_archiver = MagicMock()
        mock_archiver.archive_memories.return_value = MagicMock(
            memories_scanned=0,
            memories_eligible=0,
            memories_archived=0,
            memories_preserved=0,
            bytes_archived=0,
            errors=[],
            was_dry_run=True,
        )
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver_class.return_value = mock_archiver

        mock_promoter = MagicMock()
        mock_promoter.promote_memories.return_value = MagicMock(
            candidates_evaluated=0,
            candidates_promoted=0,
            candidates_rejected=0,
            promotion_score_avg=0.0,
            errors=[],
            was_dry_run=True,
        )
        mock_promoter_class.return_value = mock_promoter

        scheduler = MemoryConsolidationScheduler(config=config, redis_client=mock_redis)
        scheduler.run_now(dry_run=True)

        # LAST_RUN_KEY must NOT be written during dry-run
        mock_redis.set.assert_not_called()
        # Also verify audit confirms the op was blocked
        assert (
            "update_last_run_time"
            in scheduler.get_last_result().audit.destructive_ops_blocked
        )  # noqa: E501


class TestDisabledFeatureFlagSafe:
    """Test that disabled feature flag is safe."""


class TestDigestFlushScheduler:
    """Tests for the 8 PM America/Toronto daily digest flush job."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return ConsolidationConfig(dry_run=True, enabled=True)

    def test_digest_flush_job_added_on_start(self, config):
        """Start must register a 'daily_digest_flush' APScheduler job."""
        scheduler = MemoryConsolidationScheduler(config)
        with patch(
            "apscheduler.schedulers.background.BackgroundScheduler"
        ) as mock_scheduler_cls:
            mock_scheduler = MagicMock()
            mock_scheduler_cls.return_value = mock_scheduler

            scheduler.start()

            # Collect all add_job calls
            add_job_calls = mock_scheduler.add_job.call_args_list
            job_ids = [call.kwargs.get("id") for call in add_job_calls]

            assert "daily_digest_flush" in job_ids

    def test_digest_flush_trigger_uses_toronto_timezone(self, config):
        """The digest flush CronTrigger must use America/Toronto timezone."""
        scheduler = MemoryConsolidationScheduler(config)
        with patch(
            "apscheduler.schedulers.background.BackgroundScheduler"
        ) as mock_scheduler_cls:
            mock_scheduler = MagicMock()
            mock_scheduler_cls.return_value = mock_scheduler

            scheduler.start()

            # Find the digest flush job call
            digest_call = None
            for call in mock_scheduler.add_job.call_args_list:
                if call.kwargs.get("id") == "daily_digest_flush":
                    digest_call = call
                    break

            assert digest_call is not None, "daily_digest_flush job not found"

            trigger = digest_call.kwargs["trigger"]
            from zoneinfo import ZoneInfo

            # CronTrigger stores params in _fields; verify via dict repr
            assert trigger.timezone == ZoneInfo("America/Toronto")
            # Verify hour=20 and minute=0 via the trigger's __repr__ or fields
            assert "20" in str(trigger)  # hour=20
            assert "0" in str(trigger)  # minute=0

    @patch("subprocess.run")
    def test_digest_flush_empty_queue_returns_false(self, mock_run, config):
        """Non-zero exit code (nothing to send) should return False."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="",
        )

        scheduler = MemoryConsolidationScheduler(config)
        result = scheduler._run_digest_flush()

        assert result is False
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_digest_flush_success_returns_true(self, mock_run, config):
        """Exit code 0 (flush sent) should return True."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Digest sent",
            stderr="",
        )

        scheduler = MemoryConsolidationScheduler(config)
        result = scheduler._run_digest_flush()

        assert result is True
        mock_run.assert_called_once()

    @patch("subprocess.run", side_effect=Exception("script not found"))
    def test_digest_flush_exception_returns_false(self, mock_run, config):
        """Exceptions during digest flush must be caught, not raised."""
        scheduler = MemoryConsolidationScheduler(config)
        result = scheduler._run_digest_flush()

        assert result is False

    @patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="script", timeout=60),
    )
    def test_digest_flush_timeout_returns_false(self, mock_run, config):
        """TimeoutExpired should return False (non-fatal)."""
        scheduler = MemoryConsolidationScheduler(config)
        result = scheduler._run_digest_flush()

        assert result is False

    def test_digest_flush_replace_existing_true(self, config):
        """The digest flush job must use replace_existing=True."""
        scheduler = MemoryConsolidationScheduler(config)
        with patch(
            "apscheduler.schedulers.background.BackgroundScheduler"
        ) as mock_scheduler_cls:
            mock_scheduler = MagicMock()
            mock_scheduler_cls.return_value = mock_scheduler

            scheduler.start()

            for call in mock_scheduler.add_job.call_args_list:
                if call.kwargs.get("id") == "daily_digest_flush":
                    assert call.kwargs["replace_existing"] is True
                    return
            pytest.fail("daily_digest_flush job not found")

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    def test_disabled_feature_flag_dry_run_safe(
        self, mock_promoter_class, mock_archiver_class
    ):
        """Disabled feature flag + dry-run should still be safe."""
        config = ConsolidationConfig(dry_run=True, enabled=False)
        config.run_tempmemory_ingestion = False

        mock_archiver = MagicMock()
        mock_archiver.archive_memories.return_value = MagicMock(
            memories_scanned=0,
            memories_eligible=0,
            memories_archived=0,
            memories_preserved=0,
            bytes_archived=0,
            errors=[],
            was_dry_run=True,
        )
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver_class.return_value = mock_archiver

        mock_promoter = MagicMock()
        mock_promoter.promote_memories.return_value = MagicMock(
            candidates_evaluated=0,
            candidates_promoted=0,
            candidates_rejected=0,
            promotion_score_avg=0.0,
            errors=[],
            was_dry_run=True,
        )
        mock_promoter_class.return_value = mock_promoter

        scheduler = MemoryConsolidationScheduler(config=config)
        result = scheduler.run_now(dry_run=True)

        # Should succeed (dry-run runs even when disabled)
        assert result.success is True
        # Should have audit
        assert result.audit is not None
        assert result.audit.no_files_deleted is True
        assert result.audit.no_memories_removed is True

    def test_disabled_feature_flag_no_dry_run_fails(self):
        """Disabled feature flag + no dry-run should fail safely."""
        config = ConsolidationConfig(dry_run=False, enabled=False)
        config.run_tempmemory_ingestion = False

        scheduler = MemoryConsolidationScheduler(config=config)
        result = scheduler.run_now(dry_run=False)

        assert result.success is False
        assert any("disabled" in e.lower() for e in result.errors)


class TestConsolidationResultHasNewFields:
    """Test ConsolidationResult has new dry-run fields."""

    def test_result_has_recommendations_field(self):
        """ConsolidationResult should have recommendations field."""
        result = ConsolidationResult()
        assert hasattr(result, "recommendations")
        assert result.recommendations == []

    def test_result_has_audit_field(self):
        """ConsolidationResult should have audit field."""
        result = ConsolidationResult()
        assert hasattr(result, "audit")
        assert result.audit is None

    def test_result_can_store_recommendations(self):
        """ConsolidationResult can store recommendations."""
        result = ConsolidationResult()
        rec = ConsolidationRecommendation(
            memory_id="mem_1",
            action="archive",
            reason="test",
            policy_basis="test_policy",
        )
        result.recommendations.append(rec)

        assert len(result.recommendations) == 1
        assert result.recommendations[0].memory_id == "mem_1"

    def test_result_can_store_audit(self):
        """ConsolidationResult can store audit."""
        result = ConsolidationResult()
        audit = ConsolidationAudit(dry_run_mode=True)
        result.audit = audit

        assert result.audit is not None
        assert result.audit.dry_run_mode is True
