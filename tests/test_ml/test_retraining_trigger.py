"""Comprehensive tests for model retraining trigger system.

Tests all trigger types:
- ECE-based trigger (threshold: 0.15)
- Performance-based trigger (win rate <55% over 20 trades)
- Scheduled trigger (within 1 hour of scheduled time)

Tests key features:
- Trigger deduplication (24h window)
- Pre-training validation (quality >90%)
- Discord alert integration
- Feature flag compliance

For ST-LAUNCH-011: Model Retraining Trigger
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project src to path for imports, works regardless of checkout location
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

from config.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    reset_feature_flags,
    set_feature_flags,
)
from ml.training.retraining_trigger import (
    ECE_TRIGGER_THRESHOLD,
    MIN_DATA_QUALITY_PCT,
    MIN_TRADES_FOR_PERFORMANCE,
    PERFORMANCE_WIN_RATE_THRESHOLD,
    DataQualityValidator,
    ECERetriever,
    ECETriggerConfig,
    InMemoryDeduplicationStore,
    PerformanceRetriever,
    PerformanceTriggerConfig,
    RetrainingTrigger,
    RetrainingTriggerConfig,
    ScheduledTriggerConfig,
    TriggerStatus,
    TriggerType,
)
from ml.training.training_orchestrator import (
    OrchestratorConfig,
    TrainingOrchestrator,
    TrainingRun,
    TrainingState,
    TrainingStatus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def reset_flags():
    """Reset feature flags after each test."""
    yield
    reset_feature_flags()


@pytest.fixture
def default_config():
    """Create default trigger configuration."""
    return RetrainingTriggerConfig()


@pytest.fixture
def mock_ece_retriever():
    """Create mock ECE retriever."""
    retriever = MagicMock(spec=ECERetriever)
    retriever.get_latest_ece = AsyncMock(return_value=0.10)
    return retriever


@pytest.fixture
def mock_performance_retriever():
    """Create mock performance retriever."""
    retriever = MagicMock(spec=PerformanceRetriever)
    retriever.get_win_rate = AsyncMock(return_value=(0.60, 25))
    return retriever


@pytest.fixture
def in_memory_dedup_store():
    """Create in-memory deduplication store."""
    return InMemoryDeduplicationStore()


@pytest.fixture
def default_trigger(
    mock_ece_retriever,
    mock_performance_retriever,
    in_memory_dedup_store,
    default_config,
):
    """Create default retraining trigger with mocks."""
    return RetrainingTrigger(
        config=default_config,
        dedup_store=in_memory_dedup_store,
        ece_retriever=mock_ece_retriever,
        performance_retriever=mock_performance_retriever,
    )


@pytest.fixture
def mock_data_provider():
    """Create mock data provider."""
    provider = MagicMock()
    provider.get_training_data_summary = AsyncMock(
        return_value={
            "sample_count": 1000,
            "valid_samples": 950,
            "missing_features_pct": 2.0,
            "stale_data_pct": 1.0,
        }
    )
    provider.prepare_training_data = AsyncMock(return_value=(True, 950))
    return provider


@pytest.fixture
def mock_pipeline_runner():
    """Create mock pipeline runner."""
    runner = MagicMock()
    runner.run_training = AsyncMock(
        return_value=(True, {"model_version": "v1.0.0", "accuracy": 0.85})
    )
    return runner


@pytest.fixture
def default_orchestrator(default_trigger, mock_pipeline_runner, mock_data_provider):
    """Create default orchestrator with mocks."""
    return TrainingOrchestrator(
        trigger=default_trigger,
        pipeline_runner=mock_pipeline_runner,
        data_provider=mock_data_provider,
        config=OrchestratorConfig(enable_discord_notifications=False),
    )


# =============================================================================
# ECE-Based Trigger Tests
# =============================================================================


class TestECEBasedTrigger:
    """Tests for ECE-based retraining trigger."""

    @pytest.mark.asyncio
    async def test_ece_trigger_fires_when_exceeds_threshold(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test ECE trigger fires when ECE > 0.15."""
        # Set ECE above threshold (0.20 > 0.15)
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)

        result = await default_trigger.evaluate_ece_trigger()

        assert result.triggered is True
        assert result.status == TriggerStatus.TRIGGERED
        assert "exceeds threshold" in result.message
        assert result.metrics["ece"] == 0.20
        assert result.metrics["threshold"] == ECE_TRIGGER_THRESHOLD

    @pytest.mark.asyncio
    async def test_ece_trigger_does_not_fire_when_below_threshold(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test ECE trigger does not fire when ECE <= 0.15."""
        # Set ECE below threshold
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.10)

        result = await default_trigger.evaluate_ece_trigger()

        assert result.triggered is False
        assert result.status == TriggerStatus.NOT_TRIGGERED
        assert "within threshold" in result.message

    @pytest.mark.asyncio
    async def test_ece_trigger_at_exact_threshold(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test ECE trigger at exact threshold (0.15)."""
        # Set ECE at exact threshold
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.15)

        result = await default_trigger.evaluate_ece_trigger()

        # At exact threshold, should NOT trigger (must EXCEED)
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_ece_trigger_disabled_by_feature_flag(
        self, default_trigger, reset_flags
    ):
        """Test ECE trigger respects feature flag."""
        flags = FeatureFlags(retraining_ece_trigger=False)
        set_feature_flags(flags)

        result = await default_trigger.evaluate_ece_trigger()

        assert result.status == TriggerStatus.DISABLED
        assert result.triggered is False
        assert "disabled" in result.message.lower()

    @pytest.mark.asyncio
    async def test_ece_trigger_handles_missing_retriever(
        self, default_config, in_memory_dedup_store, reset_flags
    ):
        """Test ECE trigger handles missing retriever."""
        trigger = RetrainingTrigger(
            config=default_config,
            dedup_store=in_memory_dedup_store,
            ece_retriever=None,
        )

        result = await trigger.evaluate_ece_trigger()

        assert result.triggered is False
        assert result.status == TriggerStatus.NOT_TRIGGERED
        assert "unavailable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_ece_trigger_handles_retriever_error(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test ECE trigger handles retriever error."""
        mock_ece_retriever.get_latest_ece = AsyncMock(
            side_effect=Exception("ECE service unavailable")
        )

        result = await default_trigger.evaluate_ece_trigger()

        assert result.status == TriggerStatus.ERROR
        assert result.triggered is False
        assert "Failed to retrieve ECE" in result.message


# =============================================================================
# Performance-Based Trigger Tests
# =============================================================================


class TestPerformanceBasedTrigger:
    """Tests for performance-based retraining trigger."""

    @pytest.mark.asyncio
    async def test_performance_trigger_fires_when_win_rate_below_threshold(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test performance trigger fires when win rate <55% over 20 trades."""
        # Set win rate below threshold (50% < 55%)
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.50, 25))

        result = await default_trigger.evaluate_performance_trigger()

        assert result.triggered is True
        assert result.status == TriggerStatus.TRIGGERED
        assert "below threshold" in result.message
        assert result.metrics["win_rate"] == 0.50
        assert result.metrics["trade_count"] == 25
        assert result.metrics["threshold"] == PERFORMANCE_WIN_RATE_THRESHOLD

    @pytest.mark.asyncio
    async def test_performance_trigger_does_not_fire_when_win_rate_above_threshold(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test performance trigger does not fire when win rate >=55%."""
        # Set win rate above threshold
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.60, 25))

        result = await default_trigger.evaluate_performance_trigger()

        assert result.triggered is False
        assert result.status == TriggerStatus.NOT_TRIGGERED
        assert "above threshold" in result.message

    @pytest.mark.asyncio
    async def test_performance_trigger_requires_minimum_trades(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test performance trigger requires minimum 20 trades."""
        # Set win rate below threshold but only 15 trades
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.50, 15))

        result = await default_trigger.evaluate_performance_trigger()

        assert result.triggered is False
        assert "Insufficient trades" in result.message
        assert result.metrics["trade_count"] == 15

    @pytest.mark.asyncio
    async def test_performance_trigger_at_exact_trade_threshold(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test performance trigger at exact 20 trade threshold."""
        # Set exactly 20 trades with low win rate
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.50, 20))

        result = await default_trigger.evaluate_performance_trigger()

        assert result.triggered is True
        assert result.status == TriggerStatus.TRIGGERED

    @pytest.mark.asyncio
    async def test_performance_trigger_disabled_by_feature_flag(
        self, default_trigger, reset_flags
    ):
        """Test performance trigger respects feature flag."""
        flags = FeatureFlags(retraining_performance_trigger=False)
        set_feature_flags(flags)

        result = await default_trigger.evaluate_performance_trigger()

        assert result.status == TriggerStatus.DISABLED
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_performance_trigger_handles_missing_retriever(
        self, default_config, in_memory_dedup_store, reset_flags
    ):
        """Test performance trigger handles missing retriever."""
        trigger = RetrainingTrigger(
            config=default_config,
            dedup_store=in_memory_dedup_store,
            performance_retriever=None,
        )

        result = await trigger.evaluate_performance_trigger()

        assert result.triggered is False
        assert result.status == TriggerStatus.NOT_TRIGGERED
        assert "unavailable" in result.message.lower()


# =============================================================================
# Scheduled Trigger Tests
# =============================================================================


class TestScheduledTrigger:
    """Tests for scheduled retraining trigger."""

    @pytest.mark.asyncio
    async def test_scheduled_trigger_fires_within_one_hour(
        self, default_trigger, reset_flags
    ):
        """Test scheduled trigger fires within 1 hour of scheduled time."""
        # Create time 30 minutes after scheduled time (02:00)
        scheduled_time = datetime.now(UTC).replace(
            hour=2, minute=0, second=0, microsecond=0
        )
        current_time = scheduled_time + timedelta(minutes=30)

        result = await default_trigger.evaluate_scheduled_trigger(current_time)

        assert result.triggered is True
        assert result.status == TriggerStatus.TRIGGERED
        assert "within 1 hour" in result.message

    @pytest.mark.asyncio
    async def test_scheduled_trigger_fires_at_exact_time(
        self, default_trigger, reset_flags
    ):
        """Test scheduled trigger fires at exact scheduled time."""
        # Create time at exact scheduled time
        scheduled_time = datetime.now(UTC).replace(
            hour=2, minute=0, second=0, microsecond=0
        )

        result = await default_trigger.evaluate_scheduled_trigger(scheduled_time)

        assert result.triggered is True

    @pytest.mark.asyncio
    async def test_scheduled_trigger_fires_at_one_hour_boundary(
        self, default_trigger, reset_flags
    ):
        """Test scheduled trigger fires at exactly 1 hour after scheduled time."""
        scheduled_time = datetime.now(UTC).replace(
            hour=2, minute=0, second=0, microsecond=0
        )
        current_time = scheduled_time + timedelta(hours=1)

        result = await default_trigger.evaluate_scheduled_trigger(current_time)

        # At exactly 1 hour, should still trigger
        assert result.triggered is True

    @pytest.mark.asyncio
    async def test_scheduled_trigger_does_not_fire_after_one_hour(
        self, default_trigger, reset_flags
    ):
        """Test scheduled trigger does not fire after 1 hour window."""
        scheduled_time = datetime.now(UTC).replace(
            hour=2, minute=0, second=0, microsecond=0
        )
        current_time = scheduled_time + timedelta(hours=1, minutes=1)

        result = await default_trigger.evaluate_scheduled_trigger(current_time)

        assert result.triggered is False
        assert result.status == TriggerStatus.NOT_TRIGGERED
        assert "Not within 1 hour" in result.message

    @pytest.mark.asyncio
    async def test_scheduled_trigger_handles_previous_day(
        self, default_trigger, reset_flags
    ):
        """Test scheduled trigger handles time crossing midnight."""
        # Current time is 02:30 today, scheduled was 02:00 yesterday
        current_time = datetime.now(UTC).replace(
            hour=2, minute=30, second=0, microsecond=0
        )

        result = await default_trigger.evaluate_scheduled_trigger(current_time)

        assert result.triggered is True

    @pytest.mark.asyncio
    async def test_scheduled_trigger_disabled_by_feature_flag(
        self, default_trigger, reset_flags
    ):
        """Test scheduled trigger respects feature flag."""
        flags = FeatureFlags(retraining_scheduled_trigger=False)
        set_feature_flags(flags)

        current_time = datetime.now(UTC).replace(hour=2, minute=30)
        result = await default_trigger.evaluate_scheduled_trigger(current_time)

        assert result.status == TriggerStatus.DISABLED
        assert result.triggered is False


# =============================================================================
# Deduplication Tests
# =============================================================================


class TestDeduplication:
    """Tests for trigger deduplication (24h window)."""

    @pytest.mark.asyncio
    async def test_ece_trigger_suppressed_within_24h_window(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test ECE trigger suppressed when fired within 24h."""
        # First trigger should fire
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)
        result1 = await default_trigger.evaluate_ece_trigger()
        assert result1.triggered is True

        # Second trigger within window should be suppressed
        result2 = await default_trigger.evaluate_ece_trigger()
        assert result2.triggered is False
        assert result2.status == TriggerStatus.SUPPRESSED
        assert "suppressed" in result2.message.lower()
        assert "24h" in result2.message or "window" in result2.message

    @pytest.mark.asyncio
    async def test_performance_trigger_suppressed_within_24h_window(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test performance trigger suppressed when fired within 24h."""
        # First trigger should fire
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.50, 25))
        result1 = await default_trigger.evaluate_performance_trigger()
        assert result1.triggered is True

        # Second trigger within window should be suppressed
        result2 = await default_trigger.evaluate_performance_trigger()
        assert result2.triggered is False
        assert result2.status == TriggerStatus.SUPPRESSED

    @pytest.mark.asyncio
    async def test_different_trigger_types_not_deduplicated(
        self,
        default_trigger,
        mock_ece_retriever,
        mock_performance_retriever,
        reset_flags,
    ):
        """Test different trigger types are deduplicated independently."""
        # Fire ECE trigger
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)
        ece_result = await default_trigger.evaluate_ece_trigger()
        assert ece_result.triggered is True

        # Performance trigger should still be able to fire
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.50, 25))
        perf_result = await default_trigger.evaluate_performance_trigger()
        assert perf_result.triggered is True

    @pytest.mark.asyncio
    async def test_deduplication_disabled_by_feature_flag(
        self, mock_ece_retriever, in_memory_dedup_store, default_config, reset_flags
    ):
        """Test deduplication can be disabled by feature flag."""
        flags = FeatureFlags(
            retraining_deduplication=False, retraining_ece_trigger=True
        )
        set_feature_flags(flags)

        trigger = RetrainingTrigger(
            config=default_config,
            dedup_store=in_memory_dedup_store,
            ece_retriever=mock_ece_retriever,
        )

        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)

        # First trigger
        result1 = await trigger.evaluate_ece_trigger()
        assert result1.triggered is True

        # Second trigger should also fire (deduplication disabled)
        result2 = await trigger.evaluate_ece_trigger()
        assert result2.triggered is True
        assert result2.status == TriggerStatus.TRIGGERED

    @pytest.mark.asyncio
    async def test_in_memory_dedup_store_triggers_independently(self, reset_flags):
        """Test in-memory dedup store works correctly."""
        store = InMemoryDeduplicationStore()

        # Should not be recent initially
        is_recent = await store.is_trigger_recent(TriggerType.ECE_BASED, 24)
        assert is_recent is False

        # Record trigger
        await store.record_trigger(TriggerType.ECE_BASED)

        # Should now be recent
        is_recent = await store.is_trigger_recent(TriggerType.ECE_BASED, 24)
        assert is_recent is True

        # Different type should not be affected
        is_recent = await store.is_trigger_recent(TriggerType.PERFORMANCE_BASED, 24)
        assert is_recent is False


# =============================================================================
# Pre-Training Validation Tests
# =============================================================================


class TestPreTrainingValidation:
    """Tests for pre-training validation (quality >90%)."""

    @pytest.mark.asyncio
    async def test_validation_passes_above_90_percent(
        self, default_trigger, reset_flags
    ):
        """Test validation passes when quality >90%."""
        result = await default_trigger.validate_training_readiness(
            sample_count=1000,
            valid_samples=950,
            missing_features_pct=2.0,
            stale_data_pct=1.0,
        )

        is_valid, quality_pct, message = result
        assert is_valid is True
        assert quality_pct > 90.0
        assert "meets threshold" in message

    @pytest.mark.asyncio
    async def test_validation_fails_below_90_percent(
        self, default_trigger, reset_flags
    ):
        """Test validation fails when quality <90%."""
        result = await default_trigger.validate_training_readiness(
            sample_count=1000,
            valid_samples=500,
            missing_features_pct=20.0,
            stale_data_pct=10.0,
        )

        is_valid, quality_pct, message = result
        assert is_valid is False
        assert quality_pct < 90.0
        assert "below threshold" in message

    @pytest.mark.asyncio
    async def test_validation_handles_zero_samples(self, default_trigger, reset_flags):
        """Test validation handles zero samples."""
        result = await default_trigger.validate_training_readiness(
            sample_count=0,
            valid_samples=0,
        )

        is_valid, quality_pct, message = result
        assert is_valid is False
        assert quality_pct == 0.0
        assert "No samples" in message

    @pytest.mark.asyncio
    async def test_validation_disabled_by_feature_flag(
        self, default_config, in_memory_dedup_store, reset_flags
    ):
        """Test validation can be disabled by feature flag."""
        flags = FeatureFlags(retraining_pre_validation=False)
        set_feature_flags(flags)

        trigger = RetrainingTrigger(
            config=default_config,
            dedup_store=in_memory_dedup_store,
        )

        result = await trigger.validate_training_readiness(
            sample_count=0,
            valid_samples=0,
        )

        is_valid, quality_pct, message = result
        assert is_valid is True  # Should pass when disabled
        assert "disabled" in message.lower()

    def test_data_quality_validator_calculation(self):
        """Test data quality validator calculation."""
        validator = DataQualityValidator(min_quality_pct=90.0)

        # Perfect quality
        is_valid, quality, msg = asyncio.run(
            validator.validate(
                sample_count=1000,
                valid_samples=1000,
                missing_features_pct=0.0,
                stale_data_pct=0.0,
            )
        )
        assert quality == 100.0
        assert is_valid is True

        # Borderline quality
        is_valid, quality, msg = asyncio.run(
            validator.validate(
                sample_count=1000,
                valid_samples=900,
                missing_features_pct=5.0,
                stale_data_pct=5.0,
            )
        )
        # Quality = 90*0.5 + 95*0.3 + 95*0.2 = 45 + 28.5 + 19 = 92.5
        assert quality > 90.0
        assert is_valid is True


# =============================================================================
# Discord Alert Tests
# =============================================================================


class TestDiscordAlerts:
    """Tests for Discord alert integration."""

    @pytest.mark.asyncio
    async def test_discord_alert_sent_on_ece_trigger(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test Discord alert sent when ECE trigger fires."""
        with patch.object(default_trigger, "_discord") as mock_discord:
            mock_discord.send_trigger_alert = AsyncMock(return_value=True)

            mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)
            result = await default_trigger.evaluate_ece_trigger()

            assert result.triggered is True
            mock_discord.send_trigger_alert.assert_called_once()
            call_args = mock_discord.send_trigger_alert.call_args
            assert call_args[0][0] == TriggerType.ECE_BASED

    @pytest.mark.asyncio
    async def test_discord_alert_sent_on_performance_trigger(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test Discord alert sent when performance trigger fires."""
        with patch.object(default_trigger, "_discord") as mock_discord:
            mock_discord.send_trigger_alert = AsyncMock(return_value=True)

            mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.50, 25))
            result = await default_trigger.evaluate_performance_trigger()

            assert result.triggered is True
            mock_discord.send_trigger_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_discord_alert_disabled_by_feature_flag(
        self, mock_ece_retriever, in_memory_dedup_store, default_config, reset_flags
    ):
        """Test Discord alerts can be disabled by feature flag."""
        flags = FeatureFlags(
            retraining_discord_alerts=False, retraining_ece_trigger=True
        )
        set_feature_flags(flags)

        with patch(
            "ml.training.retraining_trigger.DiscordNotifier"
        ) as mock_notifier_class:
            mock_notifier = MagicMock()
            mock_notifier.send_trigger_alert = AsyncMock(return_value=True)
            mock_notifier_class.return_value = mock_notifier

            trigger = RetrainingTrigger(
                config=RetrainingTriggerConfig(enable_discord_alerts=True),
                dedup_store=in_memory_dedup_store,
                ece_retriever=mock_ece_retriever,
            )

            mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)
            await trigger.evaluate_ece_trigger()

            # Discord notifier should not be called due to feature flag
            mock_notifier.send_trigger_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_discord_alert_not_sent_when_not_triggered(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test Discord alert not sent when trigger doesn't fire."""
        with patch.object(default_trigger, "_discord") as mock_discord:
            mock_discord.send_trigger_alert = AsyncMock(return_value=True)

            mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.10)
            result = await default_trigger.evaluate_ece_trigger()

            assert result.triggered is False
            mock_discord.send_trigger_alert.assert_not_called()


# =============================================================================
# Training Orchestrator Tests
# =============================================================================


class TestTrainingOrchestrator:
    """Tests for training orchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_respects_training_interval(
        self, default_orchestrator, reset_flags
    ):
        """Test orchestrator respects minimum training interval."""
        # First training
        run1 = await default_orchestrator.run_training(force=True)
        assert run1.status == TrainingStatus.SUCCESS

        # Immediate second training should be rejected
        run2 = await default_orchestrator.run_training()
        assert run2.status == TrainingStatus.ERROR
        assert "interval" in run2.error_message.lower()

    @pytest.mark.asyncio
    async def test_orchestrator_force_overrides_interval(
        self, default_orchestrator, reset_flags
    ):
        """Test force flag overrides training interval check."""
        # First training
        run1 = await default_orchestrator.run_training(force=True)
        assert run1.status == TrainingStatus.SUCCESS

        # Second training with force should succeed
        run2 = await default_orchestrator.run_training(force=True)
        assert run2.status == TrainingStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_orchestrator_prevents_concurrent_training(
        self, default_orchestrator, reset_flags
    ):
        """Test orchestrator prevents concurrent training runs."""
        # Manually set a current run in TRAINING state to simulate concurrent run
        from ml.training.training_orchestrator import TrainingRun, TrainingState

        default_orchestrator._current_run = TrainingRun(
            run_id="existing_run",
            trigger_type="test",
            state=TrainingState.TRAINING,
            started_at=datetime.now(UTC),
        )

        # Try to start second run while first is running
        run2 = await default_orchestrator.run_training(force=True)

        # Second should be rejected
        assert run2.status == TrainingStatus.ALREADY_RUNNING

    @pytest.mark.asyncio
    async def test_orchestrator_validates_data_before_training(
        self, default_orchestrator, mock_data_provider, reset_flags
    ):
        """Test orchestrator validates data before training."""
        # Make validation fail
        mock_data_provider.get_training_data_summary = AsyncMock(
            return_value={
                "sample_count": 100,
                "valid_samples": 10,
                "missing_features_pct": 50.0,
                "stale_data_pct": 50.0,
            }
        )

        run = await default_orchestrator.run_training(force=True)

        assert run.status == TrainingStatus.VALIDATION_FAILED
        assert run.state == TrainingState.FAILED

    @pytest.mark.asyncio
    async def test_orchestrator_handles_training_timeout(
        self, default_orchestrator, mock_pipeline_runner, reset_flags
    ):
        """Test orchestrator handles training timeout."""

        # Make training take too long
        async def slow_training(*args, **kwargs):
            await asyncio.sleep(1000)  # Longer than timeout
            return True, {}

        mock_pipeline_runner.run_training = slow_training

        # Set short timeout for test
        default_orchestrator.config.max_training_duration_hours = 0.001  # ~3.6 seconds

        run = await default_orchestrator.run_training(force=True)

        assert run.status == TrainingStatus.ERROR
        assert "timeout" in run.error_message.lower()

    @pytest.mark.asyncio
    async def test_orchestrator_evaluates_triggers_and_trains(
        self, default_orchestrator, mock_ece_retriever, reset_flags
    ):
        """Test orchestrator evaluates triggers and runs training when triggered."""
        # Set up ECE trigger to fire
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)

        run = await default_orchestrator.evaluate_triggers_and_train()

        assert run is not None
        assert run.status == TrainingStatus.SUCCESS
        assert run.trigger_type == "ECE_BASED"

    @pytest.mark.asyncio
    async def test_orchestrator_no_training_when_no_triggers(
        self, default_orchestrator, mock_ece_retriever, reset_flags
    ):
        """Test orchestrator doesn't train when no triggers fire."""
        # Set up ECE to not trigger
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.10)

        run = await default_orchestrator.evaluate_triggers_and_train()

        assert run is None

    def test_orchestrator_stats_tracking(self, default_orchestrator, reset_flags):
        """Test orchestrator tracks training statistics."""
        stats = default_orchestrator.get_stats()

        assert "total_runs" in stats
        assert "successful_runs" in stats
        assert "failed_runs" in stats
        assert "success_rate" in stats
        assert "current_state" in stats

    def test_training_run_duration_calculation(self):
        """Test TrainingRun duration calculation."""
        start = datetime.now(UTC)
        end = start + timedelta(minutes=5)

        run = TrainingRun(
            run_id="test",
            trigger_type="test",
            state=TrainingState.COMPLETED,
            started_at=start,
            completed_at=end,
        )

        assert run.duration_seconds == 300.0

    def test_training_run_to_dict(self):
        """Test TrainingRun serialization."""
        run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE_BASED",
            state=TrainingState.COMPLETED,
            status=TrainingStatus.SUCCESS,
            model_version="v1.0.0",
            metrics={"accuracy": 0.85},
        )

        data = run.to_dict()
        assert data["run_id"] == "test_001"
        assert data["trigger_type"] == "ECE_BASED"
        assert data["state"] == "COMPLETED"
        assert data["status"] == "SUCCESS"
        assert data["model_version"] == "v1.0.0"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the complete retraining system."""

    @pytest.mark.asyncio
    async def test_full_ece_trigger_flow(self, reset_flags):
        """Test complete ECE trigger flow from evaluation to training."""
        # Set up all components
        ece_retriever = MagicMock(spec=ECERetriever)
        ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)

        data_provider = MagicMock()
        data_provider.get_training_data_summary = AsyncMock(
            return_value={
                "sample_count": 1000,
                "valid_samples": 950,
                "missing_features_pct": 2.0,
                "stale_data_pct": 1.0,
            }
        )
        data_provider.prepare_training_data = AsyncMock(return_value=(True, 950))

        pipeline_runner = MagicMock()
        pipeline_runner.run_training = AsyncMock(
            return_value=(True, {"model_version": "v1.0.0", "accuracy": 0.85})
        )

        trigger = RetrainingTrigger(
            ece_retriever=ece_retriever,
            config=RetrainingTriggerConfig(enable_discord_alerts=False),
        )

        orchestrator = TrainingOrchestrator(
            trigger=trigger,
            pipeline_runner=pipeline_runner,
            data_provider=data_provider,
            config=OrchestratorConfig(enable_discord_notifications=False),
        )

        # Run full flow
        run = await orchestrator.evaluate_triggers_and_train()

        assert run is not None
        assert run.status == TrainingStatus.SUCCESS
        assert run.trigger_type == "ECE_BASED"
        assert run.state == TrainingState.COMPLETED

    @pytest.mark.asyncio
    async def test_full_performance_trigger_flow(self, reset_flags):
        """Test complete performance trigger flow from evaluation to training."""
        perf_retriever = MagicMock(spec=PerformanceRetriever)
        perf_retriever.get_win_rate = AsyncMock(return_value=(0.50, 25))

        data_provider = MagicMock()
        data_provider.get_training_data_summary = AsyncMock(
            return_value={
                "sample_count": 1000,
                "valid_samples": 950,
                "missing_features_pct": 2.0,
                "stale_data_pct": 1.0,
            }
        )
        data_provider.prepare_training_data = AsyncMock(return_value=(True, 950))

        pipeline_runner = MagicMock()
        pipeline_runner.run_training = AsyncMock(
            return_value=(True, {"model_version": "v1.0.0"})
        )

        trigger = RetrainingTrigger(
            performance_retriever=perf_retriever,
            config=RetrainingTriggerConfig(enable_discord_alerts=False),
        )

        orchestrator = TrainingOrchestrator(
            trigger=trigger,
            pipeline_runner=pipeline_runner,
            data_provider=data_provider,
            config=OrchestratorConfig(enable_discord_notifications=False),
        )

        run = await orchestrator.evaluate_triggers_and_train()

        assert run is not None
        assert run.status == TrainingStatus.SUCCESS
        assert run.trigger_type == "PERFORMANCE_BASED"

    @pytest.mark.asyncio
    async def test_trigger_result_serialization(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test TriggerResult can be serialized to dict."""
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=0.20)

        result = await default_trigger.evaluate_ece_trigger()

        data = result.to_dict()
        assert "trigger_type" in data
        assert "status" in data
        assert "triggered" in data
        assert "message" in data
        assert "timestamp" in data
        assert "metrics" in data


# =============================================================================
# Configuration Tests
# =============================================================================


class TestConfiguration:
    """Tests for configuration classes."""

    def test_ece_trigger_config_defaults(self):
        """Test ECE trigger config has correct defaults."""
        config = ECETriggerConfig()
        assert config.threshold == ECE_TRIGGER_THRESHOLD
        assert config.min_samples == 10
        assert config.strategy_id is None

    def test_performance_trigger_config_defaults(self):
        """Test performance trigger config has correct defaults."""
        config = PerformanceTriggerConfig()
        assert config.min_win_rate == PERFORMANCE_WIN_RATE_THRESHOLD
        assert config.min_trades == MIN_TRADES_FOR_PERFORMANCE
        assert config.lookback_days == 30

    def test_scheduled_trigger_config_defaults(self):
        """Test scheduled trigger config has correct defaults."""
        config = ScheduledTriggerConfig()
        assert config.schedule_time_utc == "02:00"
        assert config.timezone == "UTC"
        assert config.frequency == "daily"

    def test_scheduled_trigger_config_validates_time(self):
        """Test scheduled trigger config validates time format."""
        with pytest.raises(ValueError, match="Invalid schedule_time_utc"):
            ScheduledTriggerConfig(schedule_time_utc="invalid")

    def test_retraining_trigger_config_defaults(self):
        """Test retraining trigger config has correct defaults."""
        config = RetrainingTriggerConfig()
        assert config.deduplication_window_hours == 24
        assert config.min_data_quality_pct == MIN_DATA_QUALITY_PCT
        assert config.enable_discord_alerts is True

    def test_orchestrator_config_defaults(self):
        """Test orchestrator config has correct defaults."""
        config = OrchestratorConfig()
        assert config.min_training_interval_hours == 1
        assert config.max_training_duration_hours == 4
        assert config.enable_auto_trigger is True


# =============================================================================
# Feature Flags Tests
# =============================================================================


class TestFeatureFlags:
    """Tests for feature flags configuration."""

    def test_feature_flags_defaults(self):
        """Test feature flags have correct defaults."""
        flags = FeatureFlags()
        assert flags.retraining_ece_trigger is True
        assert flags.retraining_performance_trigger is True
        assert flags.retraining_scheduled_trigger is True
        assert flags.retraining_deduplication is True
        assert flags.retraining_pre_validation is True
        assert flags.retraining_discord_alerts is True

    def test_feature_flags_to_dict(self):
        """Test feature flags serialization."""
        flags = FeatureFlags()
        data = flags.to_dict()
        assert "retraining_ece_trigger" in data
        assert "retraining_performance_trigger" in data

    def test_get_feature_flags_lazy_init(self):
        """Test get_feature_flags lazily initializes."""
        reset_feature_flags()
        flags = get_feature_flags()
        assert flags is not None
        # Second call should return same instance
        flags2 = get_feature_flags()
        assert flags is flags2


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_trigger_handles_none_ece_value(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test trigger handles None ECE value gracefully."""
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=None)

        result = await default_trigger.evaluate_ece_trigger()

        assert result.triggered is False
        assert "unavailable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_trigger_handles_none_win_rate(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test trigger handles None win rate gracefully."""
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(None, 0))

        result = await default_trigger.evaluate_performance_trigger()

        assert result.triggered is False
        assert "unavailable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_trigger_handles_negative_ece(
        self, default_trigger, mock_ece_retriever, reset_flags
    ):
        """Test trigger handles negative ECE value."""
        mock_ece_retriever.get_latest_ece = AsyncMock(return_value=-0.1)

        result = await default_trigger.evaluate_ece_trigger()

        # Negative ECE should not trigger
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_trigger_handles_zero_trades(
        self, default_trigger, mock_performance_retriever, reset_flags
    ):
        """Test trigger handles zero trades gracefully."""
        mock_performance_retriever.get_win_rate = AsyncMock(return_value=(0.0, 0))

        result = await default_trigger.evaluate_performance_trigger()

        assert result.triggered is False
        assert "Insufficient trades" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
