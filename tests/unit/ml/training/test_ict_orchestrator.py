"""Tests for ICT ML Pipeline Orchestration.

ST-ICT-028-C: ICT ML Pipeline Orchestration
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from src.ml.training.ict_orchestrator import (
    ICTModelState,
    ICTOrchestrator,
    ICTOrchestratorConfig,
    ICTSchedulerAdapter,
    ModelPromoter,
    OrchestrationStatus,
    PerformanceMonitor,
    PerformanceThresholds,
    RetrainingEvent,
    RetrainingReason,
)


class TestICTOrchestratorConfig:
    """Tests for ICTOrchestratorConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = ICTOrchestratorConfig()
        assert config.schedule_frequency == "daily"
        assert config.retraining_enabled is True
        assert config.promotion_enabled is True
        assert config.champion_grace_period_hours == 24
        assert config.min_training_interval_hours == 6
        assert config.max_retraining_per_day == 3

    def test_custom_config(self):
        """Test custom configuration."""
        config = ICTOrchestratorConfig(
            schedule_frequency="weekly",
            retraining_enabled=False,
            promotion_enabled=False,
            champion_grace_period_hours=48,
        )
        assert config.schedule_frequency == "weekly"
        assert config.retraining_enabled is False
        assert config.promotion_enabled is False
        assert config.champion_grace_period_hours == 48

    def test_validation_min_interval(self):
        """Test min_training_interval_hours validation."""
        with pytest.raises(ValueError, match="min_training_interval_hours"):
            ICTOrchestratorConfig(min_training_interval_hours=0)

    def test_validation_max_per_day(self):
        """Test max_retraining_per_day validation."""
        with pytest.raises(ValueError, match="max_retraining_per_day"):
            ICTOrchestratorConfig(max_retraining_per_day=0)

    def test_thresholds(self):
        """Test thresholds configuration."""
        thresholds = PerformanceThresholds(
            min_direction_accuracy=0.55,
            max_ece=0.15,
        )
        config = ICTOrchestratorConfig(thresholds=thresholds)
        assert config.thresholds.min_direction_accuracy == 0.55
        assert config.thresholds.max_ece == 0.15


class TestPerformanceThresholds:
    """Tests for PerformanceThresholds."""

    def test_default_thresholds(self):
        """Test default thresholds."""
        t = PerformanceThresholds()
        assert t.min_direction_accuracy == 0.50
        assert t.max_ece == 0.20
        assert t.min_validation_accuracy == 0.45
        assert t.degradation_margin == 0.05
        assert t.promotion_margin == 0.02

    def test_to_dict(self):
        """Test dictionary conversion."""
        t = PerformanceThresholds(min_direction_accuracy=0.55)
        d = t.to_dict()
        assert d["min_direction_accuracy"] == 0.55


class TestICTModelState:
    """Tests for ICTModelState."""

    def test_default_state(self):
        """Test default model state."""
        state = ICTModelState(model_version="0.1.0")
        assert state.model_version == "0.1.0"
        assert state.status == "challenger"
        assert state.metrics is None

    def test_custom_state(self):
        """Test custom model state."""
        from src.ml.training.ict_integration import ICTTrainingMetrics

        metrics = ICTTrainingMetrics(direction_accuracy=0.72)
        state = ICTModelState(
            model_version="0.2.0",
            metrics=metrics,
            status="champion",
        )
        assert state.model_version == "0.2.0"
        assert state.status == "champion"
        assert state.metrics.direction_accuracy == 0.72


class TestRetrainingEvent:
    """Tests for RetrainingEvent."""

    def test_default_event(self):
        """Test default event."""
        event = RetrainingEvent(
            event_id="test_001",
            reason=RetrainingReason.SCHEDULED,
            previous_version="0.1.0",
        )
        assert event.event_id == "test_001"
        assert event.reason == RetrainingReason.SCHEDULED
        assert event.success is False

    def test_successful_event(self):
        """Test successful event."""
        event = RetrainingEvent(
            event_id="test_002",
            reason=RetrainingReason.MANUAL,
            previous_version="0.1.0",
            new_version="0.2.0",
            success=True,
            metrics={"direction_accuracy": 0.72},
        )
        assert event.success is True
        assert event.new_version == "0.2.0"

    def test_to_dict(self):
        """Test dictionary conversion."""
        event = RetrainingEvent(
            event_id="test_003",
            reason=RetrainingReason.PERFORMANCE_DEGRADATION,
            previous_version="0.1.0",
            new_version="0.2.0",
            success=True,
        )
        d = event.to_dict()
        assert d["event_id"] == "test_003"
        assert d["reason"] == "performance_degradation"
        assert d["success"] is True


class TestRetrainingReason:
    """Tests for RetrainingReason enum."""

    def test_all_reasons(self):
        """Test all retraining reasons."""
        assert RetrainingReason.SCHEDULED.value == "scheduled"
        assert (
            RetrainingReason.PERFORMANCE_DEGRADATION.value == "performance_degradation"
        )
        assert RetrainingReason.THRESHOLD_BREACH.value == "threshold_breach"
        assert RetrainingReason.MANUAL.value == "manual"
        assert RetrainingReason.NEW_DATA_AVAILABLE.value == "new_data_available"


class TestICTSchedulerAdapter:
    """Tests for ICTSchedulerAdapter."""

    def test_init_default(self):
        """Test default initialization."""
        adapter = ICTSchedulerAdapter()
        assert adapter._frequency == "daily"
        assert adapter._hour == 2
        assert adapter._minute == 0

    def test_init_custom(self):
        """Test custom initialization."""
        adapter = ICTSchedulerAdapter(
            schedule_frequency="weekly",
            hour=3,
            minute=30,
        )
        assert adapter._frequency == "weekly"
        assert adapter._hour == 3
        assert adapter._minute == 30

    def test_get_schedule_config(self):
        """Test schedule config generation."""
        adapter = ICTSchedulerAdapter(schedule_frequency="weekly")
        config = adapter.get_schedule_config()
        assert "frequency" in config
        assert config["hour"] == 2
        assert config["minute"] == 0

    def test_should_run_no_last_run(self):
        """Test should_run when no previous run."""
        adapter = ICTSchedulerAdapter()
        assert adapter.should_run(None) is True

    def test_should_run_recent(self):
        """Test should_run when last run was recent."""
        adapter = ICTSchedulerAdapter(schedule_frequency="daily")
        last_run = datetime.now(UTC) - timedelta(hours=12)
        assert adapter.should_run(last_run) is False

    def test_should_run_old(self):
        """Test should_run when last run was old."""
        adapter = ICTSchedulerAdapter(schedule_frequency="daily")
        last_run = datetime.now(UTC) - timedelta(days=2)
        assert adapter.should_run(last_run) is True

    def test_should_run_weekly(self):
        """Test weekly schedule check."""
        adapter = ICTSchedulerAdapter(schedule_frequency="weekly")
        last_run = datetime.now(UTC) - timedelta(days=3)
        assert adapter.should_run(last_run) is False

        last_run = datetime.now(UTC) - timedelta(days=10)
        assert adapter.should_run(last_run) is True


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor."""

    def test_init_default(self):
        """Test default initialization."""
        monitor = PerformanceMonitor()
        assert monitor._thresholds.min_direction_accuracy == 0.50
        assert len(monitor._history) == 0

    def test_init_custom_thresholds(self):
        """Test custom thresholds."""
        thresholds = PerformanceThresholds(min_direction_accuracy=0.55)
        monitor = PerformanceMonitor(thresholds=thresholds)
        assert monitor._thresholds.min_direction_accuracy == 0.55

    def test_add_model_state(self):
        """Test adding model state."""
        monitor = PerformanceMonitor()
        state = ICTModelState(model_version="0.1.0")
        monitor.add_model_state(state)
        assert len(monitor._history) == 1

    def test_add_model_state_limit(self):
        """Test model state history limit."""
        monitor = PerformanceMonitor()
        for i in range(150):
            state = ICTModelState(model_version=f"0.{i}.0")
            monitor.add_model_state(state)
        assert len(monitor._history) == 100

    def test_should_retrain_no_champion(self):
        """Test should_retrain when no champion exists."""
        monitor = PerformanceMonitor()
        should, reason = monitor.should_retrain(None, [])
        assert should is True
        assert reason == RetrainingReason.NEW_DATA_AVAILABLE

    def test_should_retrain_recent_training(self):
        """Test should_retrain when recent training occurred."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        recent_event = RetrainingEvent(
            event_id="test",
            reason=RetrainingReason.SCHEDULED,
            previous_version="0.1.0",
            success=True,
            timestamp=datetime.now(UTC) - timedelta(hours=1),
        )

        should, _ = monitor.should_retrain(
            ICTTrainingMetrics(direction_accuracy=0.70),
            [recent_event],
        )
        assert should is False

    def test_should_retrain_max_per_day(self):
        """Test should_retrain when max per day reached."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        today = datetime.now(UTC).date()
        events = [
            RetrainingEvent(
                event_id=f"test_{i}",
                reason=RetrainingReason.SCHEDULED,
                previous_version="0.1.0",
                success=True,
                timestamp=datetime.combine(today, datetime.min.time()).replace(
                    tzinfo=UTC
                )
                + timedelta(hours=i),
            )
            for i in range(3)
        ]

        should, _ = monitor.should_retrain(
            ICTTrainingMetrics(direction_accuracy=0.70),
            events,
        )
        assert should is False

    def test_should_retrain_performance_degradation(self):
        """Test should_retrain due to performance degradation."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        # Champion with poor accuracy
        metrics = ICTTrainingMetrics(
            direction_accuracy=0.52,  # Just above min threshold but below grace margin
            confidence_calibration=0.18,
        )

        should, reason = monitor.should_retrain(metrics, [])
        assert should is True
        assert reason == RetrainingReason.PERFORMANCE_DEGRADATION

    def test_should_promote_no_champion(self):
        """Test should_promote when no champion."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        metrics = ICTTrainingMetrics(direction_accuracy=0.70)
        assert monitor.should_promote(None, metrics) is True

    def test_should_promote_insufficient_accuracy(self):
        """Test should_promote with insufficient accuracy."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        champion = ICTTrainingMetrics(direction_accuracy=0.70)
        challenger = ICTTrainingMetrics(direction_accuracy=0.48)  # Below threshold

        assert monitor.should_promote(champion, challenger) is False

    def test_should_promote_insufficient_ece(self):
        """Test should_promote with poor ECE."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        champion = ICTTrainingMetrics(direction_accuracy=0.70)
        challenger = ICTTrainingMetrics(
            direction_accuracy=0.65,
            confidence_calibration=0.25,  # Above max ECE
        )

        assert monitor.should_promote(champion, challenger) is False

    def test_should_promote_success(self):
        """Test successful promotion."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        champion = ICTTrainingMetrics(
            direction_accuracy=0.70,
            confidence_calibration=0.08,
        )
        challenger = ICTTrainingMetrics(
            direction_accuracy=0.74,  # Better by margin
            confidence_calibration=0.06,  # Better ECE
        )

        assert monitor.should_promote(champion, challenger) is True

    def test_should_demote(self):
        """Test should_demote."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        champion = ICTTrainingMetrics(
            direction_accuracy=0.70,
            confidence_calibration=0.08,
        )
        challenger = ICTTrainingMetrics(
            direction_accuracy=0.75,
            confidence_calibration=0.05,
        )

        assert monitor.should_demote(champion, challenger) is True

    def test_should_demote_insufficient_margin(self):
        """Test should_demote with insufficient margin."""
        monitor = PerformanceMonitor()
        from src.ml.training.ict_integration import ICTTrainingMetrics

        champion = ICTTrainingMetrics(direction_accuracy=0.70)
        challenger = ICTTrainingMetrics(direction_accuracy=0.71)  # Only 1% better

        assert monitor.should_demote(champion, challenger) is False


class TestModelPromoter:
    """Tests for ModelPromoter."""

    def test_init_default(self):
        """Test default initialization."""
        promoter = ModelPromoter()
        assert promoter._grace_period == timedelta(hours=24)
        assert promoter.get_champion() is None
        assert promoter.get_challenger() is None

    def test_init_custom_grace(self):
        """Test custom grace period."""
        promoter = ModelPromoter(grace_period_hours=48)
        assert promoter._grace_period == timedelta(hours=48)

    def test_set_champion(self):
        """Test setting champion."""
        promoter = ModelPromoter()
        state = ICTModelState(model_version="0.1.0")
        promoter.set_champion(state)

        champion = promoter.get_champion()
        assert champion is not None
        assert champion.model_version == "0.1.0"
        assert champion.status == "champion"

    def test_set_challenger(self):
        """Test setting challenger."""
        promoter = ModelPromoter()
        state = ICTModelState(model_version="0.2.0")
        promoter.set_challenger(state)

        challenger = promoter.get_challenger()
        assert challenger is not None
        assert challenger.model_version == "0.2.0"
        assert challenger.status == "challenger"

    def test_promote(self):
        """Test promotion."""
        promoter = ModelPromoter()

        champion = ICTModelState(model_version="0.1.0")
        promoter.set_champion(champion)

        challenger = ICTModelState(model_version="0.2.0")
        promoter.set_challenger(challenger)

        new_ver, old_ver = promoter.promote()

        assert new_ver == "0.2.0"
        assert old_ver == "0.1.0"
        assert promoter.get_champion().model_version == "0.2.0"
        assert promoter.get_challenger() is None

    def test_promote_no_challenger(self):
        """Test promotion with no challenger."""
        promoter = ModelPromoter()
        new_ver, old_ver = promoter.promote()
        assert new_ver is None
        assert old_ver is None

    def test_can_demote_no_champion(self):
        """Test can_demote with no champion."""
        promoter = ModelPromoter()
        assert promoter.can_demote() is True

    def test_can_demote_grace_period(self):
        """Test can_demote during grace period."""
        promoter = ModelPromoter(grace_period_hours=24)

        champion = ICTModelState(
            model_version="0.1.0",
            promoted_at=datetime.now(UTC) - timedelta(hours=12),  # Still in grace
        )
        promoter.set_champion(champion)

        assert promoter.can_demote() is False

    def test_can_demote_after_grace(self):
        """Test can_demote after grace period."""
        promoter = ModelPromoter(grace_period_hours=24)

        champion = ICTModelState(
            model_version="0.1.0",
            promoted_at=datetime.now(UTC) - timedelta(hours=48),  # Past grace
        )
        promoter.set_champion(champion)

        assert promoter.can_demote() is True


class TestICTOrchestrator:
    """Tests for ICTOrchestrator."""

    def test_init_default(self):
        """Test default initialization."""
        orchestrator = ICTOrchestrator()
        assert orchestrator._config.retraining_enabled is True
        assert orchestrator._status == OrchestrationStatus.IDLE
        assert orchestrator._running is False

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = ICTOrchestratorConfig(
            schedule_frequency="weekly",
            retraining_enabled=False,
        )
        orchestrator = ICTOrchestrator(config=config)
        assert orchestrator._config.schedule_frequency == "weekly"
        assert orchestrator._config.retraining_enabled is False

    @pytest.mark.asyncio
    async def test_trigger_retraining_no_pipeline(self):
        """Test triggering retraining without pipeline."""
        orchestrator = ICTOrchestrator()
        event = await orchestrator.trigger_retraining(RetrainingReason.MANUAL)

        assert event.success is False
        assert event.error_message == "No training pipeline configured"

    @pytest.mark.asyncio
    async def test_evaluate_and_retrain_disabled(self):
        """Test evaluate_and_retrain when disabled."""
        config = ICTOrchestratorConfig(retraining_enabled=False)
        orchestrator = ICTOrchestrator(config=config)

        result = await orchestrator.evaluate_and_retrain()
        assert result is None

    @pytest.mark.asyncio
    async def test_check_promotion_no_challenger(self):
        """Test check_promotion with no challenger."""
        orchestrator = ICTOrchestrator()
        new_ver, old_ver = await orchestrator.check_promotion()
        assert new_ver is None
        assert old_ver is None

    def test_get_status(self):
        """Test getting status."""
        orchestrator = ICTOrchestrator()
        assert orchestrator.get_status() == OrchestrationStatus.IDLE

    def test_get_champion(self):
        """Test getting champion."""
        orchestrator = ICTOrchestrator()
        assert orchestrator.get_champion() is None

    def test_get_challenger(self):
        """Test getting challenger."""
        orchestrator = ICTOrchestrator()
        assert orchestrator.get_challenger() is None

    def test_get_retraining_history_empty(self):
        """Test empty retraining history."""
        orchestrator = ICTOrchestrator()
        history = orchestrator.get_retraining_history()
        assert len(history) == 0

    def test_get_retraining_history_limit(self):
        """Test retraining history with limit."""
        orchestrator = ICTOrchestrator()

        # Add events
        for i in range(15):
            event = RetrainingEvent(
                event_id=f"test_{i}",
                reason=RetrainingReason.SCHEDULED,
                previous_version="0.1.0",
            )
            orchestrator._retraining_history.append(event)

        history = orchestrator.get_retraining_history(limit=10)
        assert len(history) == 10

    def test_get_stats(self):
        """Test getting statistics."""
        orchestrator = ICTOrchestrator()
        stats = orchestrator.get_stats()

        assert "status" in stats
        assert "is_running" in stats
        assert "champion_version" in stats
        assert "total_retrains" in stats
        assert stats["total_retrains"] == 0

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping orchestrator."""
        orchestrator = ICTOrchestrator()

        # Mock evaluate_and_retrain to avoid actual training
        with patch.object(orchestrator, "evaluate_and_retrain", new_callable=AsyncMock):
            await orchestrator.start(poll_interval_seconds=0.1)
            assert orchestrator._running is True

            await asyncio.sleep(0.2)  # Let it run briefly

            await orchestrator.stop()
            assert orchestrator._running is False

    def test_get_config(self):
        """Test getting configuration."""
        config = ICTOrchestratorConfig(schedule_frequency="weekly")
        orchestrator = ICTOrchestrator(config=config)
        assert orchestrator.get_config().schedule_frequency == "weekly"


class TestOrchestrationStatus:
    """Tests for OrchestrationStatus enum."""

    def test_all_statuses(self):
        """Test all orchestration statuses."""
        assert OrchestrationStatus.IDLE.name == "IDLE"
        assert OrchestrationStatus.MONITORING.name == "MONITORING"
        assert OrchestrationStatus.TRAINING.name == "TRAINING"
        assert OrchestrationStatus.VALIDATING.name == "VALIDATING"
        assert OrchestrationStatus.PROMOTING.name == "PROMOTING"
        assert OrchestrationStatus.DEMOTING.name == "DEMOTING"
        assert OrchestrationStatus.FAILED.name == "FAILED"
