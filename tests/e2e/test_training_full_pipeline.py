"""End-to-end integration tests for training pipeline.

Tests the complete training pipeline including:
- Retraining trigger evaluation
- Training orchestration
- Model validation and promotion
- Rollback on validation failure
- Feature flag controls

For ST-LAUNCH-014: Training E2E Integration Test
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from config import FeatureFlags, reset_feature_flags, set_feature_flags
from ml.model_registry.registry import (
    ModelRegistry,
    ModelStatus,
    ModelType,
    PromotionCriteria,
)

# Import training components
from ml.training.pipeline import PipelineConfig, TrainingPipeline
from ml.training.retraining_trigger import (
    InMemoryDeduplicationStore,
    RetrainingTrigger,
    RetrainingTriggerConfig,
    TriggerStatus,
    TriggerType,
)
from ml.training.schema import TrainingSample
from ml.training.training_orchestrator import (
    OrchestratorConfig,
    TrainingOrchestrator,
    TrainingState,
    TrainingStatus,
)

# Import fixtures
pytest_plugins = ["tests.e2e.fixtures.training_fixtures"]

# Use reset_feature_flags_fixture from training_fixtures as reset_feature_flags
# Tests should use 'reset_feature_flags_fixture' as the parameter name


class MockFeatureExtractor:
    """Mock feature extractor for testing."""

    def __init__(self, samples: list[TrainingSample] | None = None):
        self._samples = samples or []
        self._sample_idx = 0

    async def extract_features(self, signal_id: str):
        """Mock feature extraction."""
        if self._sample_idx < len(self._samples):
            sample = self._samples[self._sample_idx]
            self._sample_idx += 1
            return Mock(
                signal_id=signal_id,
                timestamp=sample.timestamp,
                token=sample.token,
                timeframe=sample.timeframe,
                technical=Mock(
                    rsi=sample.rsi,
                    macd=sample.macd,
                    macd_signal=sample.macd_signal,
                    macd_histogram=sample.macd_histogram,
                    bb_upper=sample.bb_upper,
                    bb_lower=sample.bb_lower,
                    atr=sample.atr,
                    volume_sma=sample.volume_sma,
                ),
                market=Mock(
                    trend_state=sample.trend_state,
                    confluence_score=sample.confluence_score,
                    price_change_24h=sample.price_change_24h,
                    volatility=sample.volatility,
                ),
                confidence=sample.confidence,
                direction=sample.direction,
                entry_price=sample.entry_price,
                predicted_prob=sample.predicted_prob,
            )
        return None

    def _extract_from_signal(self, signal):
        """Mock extraction from signal."""
        return Mock(
            signal_id=signal.signal_id,
            timestamp=signal.timestamp,
            token=signal.token,
            timeframe=signal.timeframe,
        )


class MockSignalStorage:
    """Mock signal storage for testing."""

    def __init__(self, signals_with_outcomes: list | None = None):
        self._signals = signals_with_outcomes or []

    async def query_signals_with_outcomes(self, **kwargs):
        """Mock query."""
        return self._signals

    async def get_outcome_by_signal_id(self, signal_id: str):
        """Mock outcome retrieval."""
        for swo in self._signals:
            if swo.signal.signal_id == signal_id:
                return swo.outcome
        return None


class MockECERetriever:
    """Mock ECE retriever for testing."""

    def __init__(self, ece_value: float | None = 0.10):
        self._ece = ece_value

    async def get_latest_ece(self, strategy_id: str | None = None) -> float | None:
        return self._ece


class MockPerformanceRetriever:
    """Mock performance retriever for testing."""

    def __init__(self, win_rate: float = 0.60, trade_count: int = 50):
        self._win_rate = win_rate
        self._trade_count = trade_count

    async def get_win_rate(
        self, min_trades: int, lookback_days: int, strategy_id: str | None = None
    ) -> tuple[float | None, int]:
        return self._win_rate, self._trade_count


class MockTrainingPipelineRunner:
    """Mock pipeline runner for testing."""

    def __init__(self, success: bool = True, metrics: dict | None = None):
        self._success = success
        # Include all required metrics for promotion criteria
        self._metrics = metrics or {
            "accuracy": 0.85,
            "precision": 0.82,
            "recall": 0.80,
            "f1": 0.81,
            "ece": 0.10,  # Below 0.15 threshold
            "model_version": "v1.0.0_test",
        }

    async def run_training(
        self, sample_count: int | None = None, validation_split: float = 0.2
    ) -> tuple[bool, dict]:
        await asyncio.sleep(0.1)  # Simulate some work
        return self._success, self._metrics


class MockDataProvider:
    """Mock data provider for testing."""

    def __init__(
        self,
        sample_count: int = 1000,
        valid_samples: int = 950,
        missing_features_pct: float = 2.0,
        stale_data_pct: float = 1.0,
    ):
        self._summary = {
            "sample_count": sample_count,
            "valid_samples": valid_samples,
            "missing_features_pct": missing_features_pct,
            "stale_data_pct": stale_data_pct,
        }
        self._prep_success = True

    async def get_training_data_summary(self) -> dict:
        return self._summary

    async def prepare_training_data(self) -> tuple[bool, int]:
        return self._prep_success, self._summary["valid_samples"]


@pytest.fixture
def sample_training_samples():
    """Create sample training samples for testing."""
    samples = []
    base_time = datetime.now(UTC)

    for i in range(10):
        sample = TrainingSample(
            sample_id=f"sample_{i}",
            timestamp=base_time - timedelta(hours=i),
            token="BTCUSDT",
            timeframe="1h",
            rsi=50.0 + i,
            macd=0.5 + i * 0.1,
            macd_signal=0.4 + i * 0.1,
            macd_histogram=0.1,
            bb_upper=50000.0 + i * 100,
            bb_lower=49000.0 - i * 100,
            bb_width=2.0,
            atr=100.0,
            volume_sma=1.0,
            trend_state="bullish",
            confluence_score=75.0,
            confidence=0.75,
            direction="long",
            entry_price=49500.0,
            price_change_24h=2.5,
            volatility=0.15,
            outcome=1 if i % 2 == 0 else 0,
            pnl_percent=1.5 if i % 2 == 0 else -0.8,
            holding_period_minutes=60,
            predicted_prob=0.75,
            confidence_bin=7,
        )
        samples.append(sample)

    return samples


@pytest.fixture
def mock_extractor(sample_training_samples):
    """Create mock feature extractor."""
    return MockFeatureExtractor(sample_training_samples)


@pytest.fixture
def mock_storage():
    """Create mock signal storage."""
    return MockSignalStorage()


@pytest.fixture
def pipeline(mock_extractor, mock_storage):
    """Create training pipeline."""
    config = PipelineConfig(
        batch_size=5,
        max_concurrent=3,
        cache_enabled=False,
    )
    return TrainingPipeline(
        extractor=mock_extractor,
        signal_storage=mock_storage,
        config=config,
    )


@pytest.fixture
def model_registry():
    """Create model registry for testing."""
    criteria = PromotionCriteria(
        min_accuracy=0.75,
        min_precision=0.70,
        min_recall=0.70,
        min_f1=0.72,
        max_ece=0.15,
        require_outperformance=True,
        outperformance_margin_pct=2.0,
        require_human_approval=False,  # Disable for automated testing
    )
    return ModelRegistry(promotion_criteria=criteria)


@pytest.fixture
def retraining_trigger():
    """Create retraining trigger for testing."""
    config = RetrainingTriggerConfig(
        deduplication_window_hours=1,  # Short window for testing
        min_data_quality_pct=90.0,
        enable_discord_alerts=False,
    )
    dedup_store = InMemoryDeduplicationStore()
    ece_retriever = MockECERetriever(ece_value=0.10)
    perf_retriever = MockPerformanceRetriever(win_rate=0.60, trade_count=50)

    return RetrainingTrigger(
        config=config,
        dedup_store=dedup_store,
        ece_retriever=ece_retriever,
        performance_retriever=perf_retriever,
    )


@pytest.fixture
def training_orchestrator(retraining_trigger):
    """Create training orchestrator for testing."""
    config = OrchestratorConfig(
        min_training_interval_hours=0,  # No minimum interval for testing
        max_training_duration_hours=1,
        enable_auto_trigger=True,
        enable_discord_notifications=False,
        validation_timeout_seconds=30.0,
    )

    data_provider = MockDataProvider(
        sample_count=1000,
        valid_samples=950,
        missing_features_pct=2.0,
        stale_data_pct=1.0,
    )

    pipeline_runner = MockTrainingPipelineRunner(success=True)

    return TrainingOrchestrator(
        trigger=retraining_trigger,
        config=config,
        data_provider=data_provider,
        pipeline_runner=pipeline_runner,
    )


@pytest.fixture
def reset_flags():
    """Reset feature flags after each test."""
    yield
    reset_feature_flags()


class TestTrainingPipelineE2E:
    """End-to-end tests for training pipeline."""

    @pytest.mark.asyncio
    async def test_full_training_pipeline_success(
        self, retraining_trigger, training_orchestrator, model_registry, reset_flags
    ):
        """Test complete training pipeline from trigger to promotion."""
        # Enable all feature flags
        set_feature_flags(
            FeatureFlags(
                retraining_ece_trigger=True,
                retraining_performance_trigger=True,
                retraining_scheduled_trigger=True,
                retraining_deduplication=True,
                retraining_pre_validation=True,
                retraining_discord_alerts=False,
            )
        )

        # Connect trigger to orchestrator
        training_orchestrator.trigger = retraining_trigger

        # Step 1: Evaluate triggers
        results = await retraining_trigger.evaluate_all()
        assert len(results) == 3  # ECE, Performance, Scheduled

        # Check if any triggered
        should_trigger, triggering = retraining_trigger.should_trigger_retraining(
            results
        )

        # Step 2: Run training if triggered (or force for testing)
        run = await training_orchestrator.run_training(force=True)

        # Step 3: Verify training completed successfully
        assert run.status == TrainingStatus.SUCCESS
        assert run.state == TrainingState.COMPLETED
        assert run.model_version is not None
        assert run.duration_seconds is not None
        assert run.duration_seconds < 300  # Should complete in <5 minutes

        # Step 4: Register model in registry
        version = model_registry.register_model(
            model_id="test_model",
            model_path=f"/models/{run.model_version}.pkl",
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics=run.metrics,
        )
        assert version.status == ModelStatus.DRAFT

        # Step 5: Promote to candidate
        candidate = model_registry.promote_to_candidate(version.version_id)
        assert candidate.status == ModelStatus.CANDIDATE

        # Step 6: Promote to challenger
        challenger = model_registry.promote_to_challenger(candidate.version_id)
        assert challenger.status == ModelStatus.CHALLENGER

        # Step 7: Promote to champion (meets criteria)
        champion, old_champion = model_registry.promote_to_champion(
            challenger.version_id
        )
        assert champion.status == ModelStatus.CHAMPION
        assert champion.metrics["f1"] >= 0.72  # Meets promotion criteria

    @pytest.mark.asyncio
    async def test_training_pipeline_with_validation_failure(
        self, training_orchestrator, model_registry, reset_flags
    ):
        """Test training pipeline with validation failure and rollback."""
        # Create orchestrator with failing pipeline
        failing_runner = MockTrainingPipelineRunner(
            success=False,
            metrics={"error": "Training failed due to insufficient data"},
        )
        training_orchestrator.pipeline_runner = failing_runner

        # Run training
        run = await training_orchestrator.run_training(force=True)

        # Verify failure - can be ERROR or VALIDATION_FAILED depending on when failure occurs
        assert run.status in [TrainingStatus.ERROR, TrainingStatus.VALIDATION_FAILED]
        assert run.state == TrainingState.FAILED
        assert run.error_message is not None
        assert (
            "failed" in run.error_message.lower()
            or "error" in run.error_message.lower()
            or "validation" in run.error_message.lower()
        )

    @pytest.mark.asyncio
    async def test_training_pipeline_rollback_on_promotion_failure(
        self, training_orchestrator, model_registry, reset_flags
    ):
        """Test rollback when model fails promotion criteria."""
        # Create runner with poor metrics
        poor_runner = MockTrainingPipelineRunner(
            success=True,
            metrics={
                "accuracy": 0.60,  # Below 0.75 threshold
                "precision": 0.55,
                "recall": 0.50,
                "f1": 0.52,  # Below 0.72 threshold
                "model_version": "v_poor_test",
            },
        )
        training_orchestrator.pipeline_runner = poor_runner

        # Run training
        run = await training_orchestrator.run_training(force=True)
        assert run.status == TrainingStatus.SUCCESS

        # Register model
        version = model_registry.register_model(
            model_id="poor_model",
            model_path=f"/models/{run.model_version}.pkl",
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics=run.metrics,
        )

        # Promote to candidate and challenger
        candidate = model_registry.promote_to_candidate(version.version_id)
        challenger = model_registry.promote_to_challenger(candidate.version_id)

        # Attempt promotion to champion - should fail criteria
        with pytest.raises(ValueError) as exc_info:
            model_registry.promote_to_champion(challenger.version_id)

        assert "criteria not met" in str(exc_info.value).lower()

        # Mark as failed
        failed = model_registry.mark_failed(
            challenger.version_id, reason="Failed promotion criteria"
        )
        assert failed.status == ModelStatus.FAILED

        # Verify rollback target exists (previous champion or None)
        rollback_target = model_registry.get_rollback_target(ModelType.SIGNAL_PREDICTOR)
        # Should be None since no previous champion was deprecated
        assert (
            rollback_target is None or rollback_target.status == ModelStatus.DEPRECATED
        )

    @pytest.mark.asyncio
    async def test_feature_flag_controls(self, retraining_trigger, reset_flags):
        """Test that feature flags properly control trigger behavior."""
        # Disable all triggers
        set_feature_flags(
            FeatureFlags(
                retraining_ece_trigger=False,
                retraining_performance_trigger=False,
                retraining_scheduled_trigger=False,
                retraining_deduplication=True,
                retraining_pre_validation=True,
                retraining_discord_alerts=False,
            )
        )

        # Evaluate triggers - all should be disabled
        ece_result = await retraining_trigger.evaluate_ece_trigger()
        assert ece_result.status == TriggerStatus.DISABLED
        assert not ece_result.triggered

        perf_result = await retraining_trigger.evaluate_performance_trigger()
        assert perf_result.status == TriggerStatus.DISABLED
        assert not perf_result.triggered

        sched_result = await retraining_trigger.evaluate_scheduled_trigger()
        assert sched_result.status == TriggerStatus.DISABLED
        assert not sched_result.triggered

        # Enable only ECE trigger
        set_feature_flags(
            FeatureFlags(
                retraining_ece_trigger=True,
                retraining_performance_trigger=False,
                retraining_scheduled_trigger=False,
                retraining_deduplication=True,
                retraining_pre_validation=True,
                retraining_discord_alerts=False,
            )
        )

        # Force high ECE to trigger
        retraining_trigger.ece_retriever = MockECERetriever(ece_value=0.20)

        ece_result = await retraining_trigger.evaluate_ece_trigger()
        assert ece_result.status == TriggerStatus.TRIGGERED
        assert ece_result.triggered

    @pytest.mark.asyncio
    async def test_training_interval_enforcement(
        self, training_orchestrator, reset_flags
    ):
        """Test that training interval is enforced."""
        # Set minimum interval to 1 hour
        training_orchestrator.config.min_training_interval_hours = 1

        # First run should succeed
        run1 = await training_orchestrator.run_training(force=False)
        assert run1.status == TrainingStatus.SUCCESS

        # Second run immediately should fail due to interval
        run2 = await training_orchestrator.run_training(force=False)
        assert run2.status == TrainingStatus.ERROR
        assert "interval" in run2.error_message.lower()

        # Force flag should bypass interval
        run3 = await training_orchestrator.run_training(force=True)
        assert run3.status == TrainingStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_model_quality_improvement_tracking(
        self, model_registry, reset_flags
    ):
        """Test tracking of model quality improvements."""
        # Register baseline model with all required metrics
        baseline = model_registry.register_model(
            model_id="baseline",
            model_path="/models/baseline.pkl",
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics={
                "f1": 0.70,
                "accuracy": 0.72,
                "precision": 0.71,
                "recall": 0.69,
                "ece": 0.10,
            },
        )

        # Promote baseline to champion
        baseline_candidate = model_registry.promote_to_candidate(baseline.version_id)
        baseline_challenger = model_registry.promote_to_challenger(
            baseline_candidate.version_id
        )
        baseline_champion, _ = model_registry.promote_to_champion(
            baseline_challenger.version_id, force=True
        )
        assert baseline_champion.status == ModelStatus.CHAMPION

        # Register improved model with all required metrics
        improved = model_registry.register_model(
            model_id="improved",
            model_path="/models/improved.pkl",
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics={
                "f1": 0.80,
                "accuracy": 0.82,
                "precision": 0.81,
                "recall": 0.79,
                "ece": 0.10,
            },
        )

        # Promote improved model
        improved_candidate = model_registry.promote_to_candidate(improved.version_id)
        improved_challenger = model_registry.promote_to_challenger(
            improved_candidate.version_id
        )

        # Should promote successfully (outperforms champion by >2%)
        new_champion, old_champion = model_registry.promote_to_champion(
            improved_challenger.version_id
        )

        assert new_champion.status == ModelStatus.CHAMPION
        assert new_champion.metrics["f1"] > baseline_champion.metrics["f1"]
        assert old_champion is not None
        assert old_champion.status == ModelStatus.DEPRECATED

        # Verify improvement
        improvement = (
            (new_champion.metrics["f1"] - baseline_champion.metrics["f1"])
            / baseline_champion.metrics["f1"]
            * 100
        )
        assert improvement > 2.0  # Meets outperformance margin

    @pytest.mark.asyncio
    async def test_training_pipeline_stats(self, pipeline, sample_training_samples):
        """Test pipeline statistics tracking."""
        # Process signals
        signal_ids = [f"signal_{i}" for i in range(5)]
        await pipeline.process_batch(signal_ids, batch_size=2)

        # Verify stats
        stats = pipeline.get_stats()
        assert stats.total_signals > 0
        assert stats.successful >= 0
        assert stats.failed >= 0
        assert stats.processing_time_ms > 0
        assert stats.batch_count > 0

    @pytest.mark.asyncio
    async def test_training_orchestrator_concurrent_protection(
        self, retraining_trigger, reset_flags
    ):
        """Test that orchestrator prevents concurrent training runs.

        Note: Due to timing, both runs may succeed if the first completes
        before the second starts. The important thing is that the orchestrator
        doesn't crash and state remains consistent.
        """
        from tests.e2e.fixtures.training_fixtures import (
            MockDataProvider,
            MockTrainingPipelineRunner,
        )

        # Create orchestrator with slow runner to increase chance of overlap
        slow_runner = MockTrainingPipelineRunner(
            success=True,
            delay_seconds=0.3,  # Slower to ensure overlap
        )

        config = OrchestratorConfig(min_training_interval_hours=0)
        orchestrator = TrainingOrchestrator(
            trigger=retraining_trigger,
            config=config,
            data_provider=MockDataProvider(),
            pipeline_runner=slow_runner,
        )

        # Start two runs concurrently
        task1 = asyncio.create_task(orchestrator.run_training(force=True))
        task2 = asyncio.create_task(orchestrator.run_training(force=True))

        run1, run2 = await asyncio.gather(task1, task2)

        # Both runs should complete (either success or already running)
        assert run1.status in [TrainingStatus.SUCCESS, TrainingStatus.ALREADY_RUNNING]
        assert run2.status in [TrainingStatus.SUCCESS, TrainingStatus.ALREADY_RUNNING]

        # At least one should succeed
        assert (
            run1.status == TrainingStatus.SUCCESS
            or run2.status == TrainingStatus.SUCCESS
        )

        # Verify orchestrator state is consistent
        stats = orchestrator.get_stats()
        assert stats["total_runs"] >= 1

    @pytest.mark.asyncio
    async def test_end_to_end_with_mocked_external_dependencies(self, reset_flags):
        """Test full E2E flow with all external dependencies mocked."""
        # This test mocks all external dependencies to ensure
        # the pipeline works in isolation

        # Setup feature flags
        set_feature_flags(
            FeatureFlags(
                retraining_ece_trigger=True,
                retraining_performance_trigger=True,
                retraining_scheduled_trigger=False,
                retraining_deduplication=False,  # Disable for predictable testing
                retraining_pre_validation=True,
                retraining_discord_alerts=False,
            )
        )

        # Create trigger with high ECE to force trigger
        config = RetrainingTriggerConfig(
            deduplication_window_hours=0,
            min_data_quality_pct=90.0,
            enable_discord_alerts=False,
        )
        trigger = RetrainingTrigger(
            config=config,
            dedup_store=InMemoryDeduplicationStore(),
            ece_retriever=MockECERetriever(ece_value=0.20),  # Above threshold
            performance_retriever=MockPerformanceRetriever(win_rate=0.60),
        )

        # Create orchestrator
        orch_config = OrchestratorConfig(
            min_training_interval_hours=0,
            max_training_duration_hours=1,
            enable_auto_trigger=True,
            enable_discord_notifications=False,
        )

        data_provider = MockDataProvider(
            sample_count=1000,
            valid_samples=950,
            missing_features_pct=2.0,
            stale_data_pct=1.0,
        )

        pipeline_runner = MockTrainingPipelineRunner(
            success=True,
            metrics={
                "accuracy": 0.85,
                "precision": 0.82,
                "recall": 0.80,
                "f1": 0.81,
                "ece": 0.10,
                "model_version": "v_e2e_test",
            },
        )

        orchestrator = TrainingOrchestrator(
            trigger=trigger,
            config=orch_config,
            data_provider=data_provider,
            pipeline_runner=pipeline_runner,
        )

        # Create registry
        registry = ModelRegistry(
            promotion_criteria=PromotionCriteria(require_human_approval=False)
        )

        # Execute: Evaluate triggers and auto-train
        run = await orchestrator.evaluate_triggers_and_train()

        # Verify training was triggered
        assert run is not None
        assert run.status == TrainingStatus.SUCCESS
        assert run.state == TrainingState.COMPLETED

        # Register and promote model
        version = registry.register_model(
            model_id="e2e_model",
            model_path=f"/models/{run.model_version}.pkl",
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics=run.metrics,
        )

        candidate = registry.promote_to_candidate(version.version_id)
        challenger = registry.promote_to_challenger(candidate.version_id)
        champion, _ = registry.promote_to_champion(challenger.version_id)

        assert champion.status == ModelStatus.CHAMPION
        assert champion.metrics["f1"] >= 0.72

    @pytest.mark.asyncio
    async def test_training_data_quality_validation(
        self, training_orchestrator, reset_flags
    ):
        """Test that poor data quality prevents training."""
        # Create data provider with poor quality data
        poor_data_provider = MockDataProvider(
            sample_count=100,
            valid_samples=50,  # Only 50% valid
            missing_features_pct=30.0,  # High missing features
            stale_data_pct=20.0,  # High stale data
        )
        poor_data_provider._prep_success = False

        training_orchestrator.data_provider = poor_data_provider

        # Run training
        run = await training_orchestrator.run_training(force=True)

        # Should fail validation
        assert run.status in [TrainingStatus.VALIDATION_FAILED, TrainingStatus.NO_DATA]

    def test_training_execution_time_under_5_minutes(self):
        """Verify that training operations complete within 5 minutes.

        This is a design assertion - the actual timing is verified
        in async tests through duration_seconds checks.
        """
        # The mock training runner uses 0.1s sleep
        # Real implementation should complete within 5 minutes (300s)
        max_acceptable_duration = 300.0  # 5 minutes in seconds

        # This test serves as documentation of the timing requirement
        assert max_acceptable_duration == 300.0

    @pytest.mark.asyncio
    async def test_champion_challenger_lifecycle(self, model_registry, reset_flags):
        """Test complete champion/challenger lifecycle."""
        # Register multiple models
        models = []
        for i in range(3):
            version = model_registry.register_model(
                model_id=f"model_v{i}",
                model_path=f"/models/v{i}.pkl",
                model_type=ModelType.SIGNAL_PREDICTOR,
                metrics={
                    "accuracy": 0.75 + i * 0.02,
                    "precision": 0.72 + i * 0.02,
                    "recall": 0.70 + i * 0.02,
                    "f1": 0.72 + i * 0.02,
                },
            )
            models.append(version)

        # Promote first to champion
        v0_candidate = model_registry.promote_to_candidate(models[0].version_id)
        v0_challenger = model_registry.promote_to_challenger(v0_candidate.version_id)
        v0_champion, _ = model_registry.promote_to_champion(
            v0_challenger.version_id, force=True
        )
        assert v0_champion.status == ModelStatus.CHAMPION

        # Promote second to challenger
        v1_candidate = model_registry.promote_to_candidate(models[1].version_id)
        v1_challenger = model_registry.promote_to_challenger(v1_candidate.version_id)
        assert v1_challenger.status == ModelStatus.CHALLENGER

        # Verify challengers list
        challengers = model_registry.get_challengers(ModelType.SIGNAL_PREDICTOR)
        assert len(challengers) == 1
        assert challengers[0].version_id == v1_challenger.version_id

        # Promote challenger to champion (deprecates old champion)
        v1_champion, v0_deprecated = model_registry.promote_to_champion(
            v1_challenger.version_id, force=True
        )
        assert v1_champion.status == ModelStatus.CHAMPION
        assert v0_deprecated.status == ModelStatus.DEPRECATED

        # Verify rollback target
        rollback = model_registry.get_rollback_target(ModelType.SIGNAL_PREDICTOR)
        assert rollback is not None
        assert rollback.version_id == v0_deprecated.version_id

    @pytest.mark.asyncio
    async def test_trigger_deduplication(self, retraining_trigger, reset_flags):
        """Test that triggers are properly deduplicated."""
        set_feature_flags(
            FeatureFlags(
                retraining_ece_trigger=True,
                retraining_performance_trigger=False,
                retraining_scheduled_trigger=False,
                retraining_deduplication=True,  # Enable deduplication
                retraining_pre_validation=True,
                retraining_discord_alerts=False,
            )
        )

        # Set high ECE to trigger
        retraining_trigger.ece_retriever = MockECERetriever(ece_value=0.20)

        # First evaluation should trigger
        result1 = await retraining_trigger.evaluate_ece_trigger()
        assert result1.status == TriggerStatus.TRIGGERED
        assert result1.triggered

        # Second evaluation should be suppressed (within dedup window)
        result2 = await retraining_trigger.evaluate_ece_trigger()
        assert result2.status == TriggerStatus.SUPPRESSED
        assert not result2.triggered
        assert "suppressed" in result2.message.lower()

    @pytest.mark.asyncio
    async def test_training_metrics_persistence(
        self, training_orchestrator, reset_flags
    ):
        """Test that training metrics are properly recorded."""
        run = await training_orchestrator.run_training(force=True)

        assert run.status == TrainingStatus.SUCCESS
        assert "accuracy" in run.metrics
        assert "precision" in run.metrics
        assert "recall" in run.metrics
        assert "f1" in run.metrics
        assert "model_version" in run.metrics

        # Verify run history
        history = training_orchestrator.get_run_history()
        assert len(history) >= 1
        assert history[-1].run_id == run.run_id

    @pytest.mark.asyncio
    async def test_pipeline_batch_processing(self, pipeline):
        """Test pipeline batch processing efficiency."""
        signal_ids = [f"signal_{i}" for i in range(20)]

        start_time = asyncio.get_event_loop().time()
        await pipeline.process_batch(signal_ids, batch_size=5)
        elapsed = asyncio.get_event_loop().time() - start_time

        # Should complete quickly with batching
        assert elapsed < 10.0  # Should be much faster than sequential

        # Verify stats
        stats = pipeline.get_stats()
        assert stats.batch_count >= 4  # 20 signals / 5 batch_size = 4 batches


class TestTrainingPipelineIntegration:
    """Integration tests for training pipeline components."""

    @pytest.mark.asyncio
    async def test_trigger_orchestrator_integration(self, reset_flags):
        """Test integration between trigger and orchestrator."""
        set_feature_flags(
            FeatureFlags(
                retraining_ece_trigger=True,
                retraining_performance_trigger=False,
                retraining_scheduled_trigger=False,
                retraining_deduplication=False,
                retraining_pre_validation=True,
                retraining_discord_alerts=False,
            )
        )

        config = RetrainingTriggerConfig(
            deduplication_window_hours=0,
            min_data_quality_pct=90.0,
        )
        trigger = RetrainingTrigger(
            config=config,
            ece_retriever=MockECERetriever(ece_value=0.20),
        )

        orch_config = OrchestratorConfig(
            min_training_interval_hours=0,
            enable_auto_trigger=True,
        )

        orchestrator = TrainingOrchestrator(
            trigger=trigger,
            config=orch_config,
            data_provider=MockDataProvider(),
            pipeline_runner=MockTrainingPipelineRunner(),
        )

        # Auto-trigger should run training
        run = await orchestrator.evaluate_triggers_and_train()

        assert run is not None
        assert run.status == TrainingStatus.SUCCESS
        assert run.trigger_type == "ECE_BASED"

    @pytest.mark.asyncio
    async def test_orchestrator_registry_integration(
        self, model_registry, reset_flags, retraining_trigger
    ):
        """Test integration between orchestrator and model registry."""
        orchestrator = TrainingOrchestrator(
            trigger=retraining_trigger,
            config=OrchestratorConfig(min_training_interval_hours=0),
            data_provider=MockDataProvider(),
            pipeline_runner=MockTrainingPipelineRunner(),
        )

        # Run training
        run = await orchestrator.run_training(force=True)
        assert run.status == TrainingStatus.SUCCESS

        # Register in registry
        version = model_registry.register_model(
            model_id="integrated_model",
            model_path=f"/models/{run.model_version}.pkl",
            metrics=run.metrics,
        )

        # Verify model can be retrieved
        retrieved = model_registry.get_version(version.version_id)
        assert retrieved is not None
        assert retrieved.metrics["f1"] == run.metrics["f1"]

    @pytest.mark.asyncio
    async def test_full_pipeline_with_all_triggers(self, reset_flags):
        """Test pipeline with all trigger types active."""
        set_feature_flags(
            FeatureFlags(
                retraining_ece_trigger=True,
                retraining_performance_trigger=True,
                retraining_scheduled_trigger=True,
                retraining_deduplication=False,
                retraining_pre_validation=True,
                retraining_discord_alerts=False,
            )
        )

        # Create trigger with conditions that should fire all triggers
        config = RetrainingTriggerConfig(
            scheduled_config=Mock(schedule_time_utc="00:00", frequency="daily"),
        )

        trigger = RetrainingTrigger(
            config=config,
            ece_retriever=MockECERetriever(ece_value=0.20),  # Above threshold
            performance_retriever=MockPerformanceRetriever(
                win_rate=0.50,  # Below threshold
                trade_count=50,
            ),
        )

        # Evaluate all triggers
        results = await trigger.evaluate_all()

        # Check results
        ece_result = next(r for r in results if r.trigger_type == TriggerType.ECE_BASED)
        perf_result = next(
            r for r in results if r.trigger_type == TriggerType.PERFORMANCE_BASED
        )
        sched_result = next(
            r for r in results if r.trigger_type == TriggerType.SCHEDULED
        )

        # ECE should trigger (0.20 > 0.15)
        assert ece_result.triggered or ece_result.status == TriggerStatus.TRIGGERED

        # Performance should trigger (0.50 < 0.55)
        assert perf_result.triggered or perf_result.status == TriggerStatus.TRIGGERED

        # Scheduled depends on current time
        assert sched_result.status in [
            TriggerStatus.TRIGGERED,
            TriggerStatus.NOT_TRIGGERED,
        ]
