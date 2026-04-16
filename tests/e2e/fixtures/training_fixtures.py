"""Fixtures for training E2E tests.

Provides reusable fixtures for training pipeline testing including:
- Mock data providers
- Mock external services
- Sample training data
- Pre-configured pipeline components

For ST-LAUNCH-014: Training E2E Integration Test
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from src.config import FeatureFlags, reset_feature_flags

from ml.model_registry.registry import (
    ModelRegistry,
    ModelStatus,
    ModelType,
    ModelVersion,
    PromotionCriteria,
)
from ml.training.pipeline import PipelineConfig, TrainingPipeline
from ml.training.retraining_trigger import (
    InMemoryDeduplicationStore,
    RetrainingTrigger,
    RetrainingTriggerConfig,
)
from ml.training.schema import TrainingDataset, TrainingSample
from ml.training.training_orchestrator import (
    OrchestratorConfig,
    TrainingOrchestrator,
)

# =============================================================================
# Training Sample Fixtures
# =============================================================================


@pytest.fixture
def sample_training_sample() -> TrainingSample:
    """Create a single valid training sample."""
    return TrainingSample(
        sample_id="sample_001",
        timestamp=datetime.now(UTC),
        token="BTCUSDT",
        timeframe="1h",
        rsi=55.0,
        macd=0.5,
        macd_signal=0.3,
        macd_histogram=0.2,
        bb_upper=51000.0,
        bb_lower=49000.0,
        bb_width=4.0,
        atr=150.0,
        volume_sma=1.2,
        trend_state="bullish",
        confluence_score=75.0,
        confidence=0.75,
        direction="long",
        entry_price=50000.0,
        price_change_24h=2.5,
        volatility=0.15,
        outcome=1,
        pnl_percent=1.5,
        holding_period_minutes=60,
        predicted_prob=0.75,
        confidence_bin=7,
    )


@pytest.fixture
def sample_training_samples() -> list[TrainingSample]:
    """Create a list of training samples with varying outcomes."""
    samples = []
    base_time = datetime.now(UTC)

    for i in range(20):
        is_win = i % 2 == 0
        sample = TrainingSample(
            sample_id=f"sample_{i:03d}",
            timestamp=base_time - timedelta(hours=i),
            token="BTCUSDT" if i % 2 == 0 else "ETHUSDT",
            timeframe="1h",
            rsi=45.0 + (i * 2),
            macd=0.1 * i,
            macd_signal=0.05 * i,
            macd_histogram=0.05 * i,
            bb_upper=50000.0 + (i * 100),
            bb_lower=48000.0 - (i * 50),
            bb_width=4.0 + (i * 0.1),
            atr=100.0 + (i * 5),
            volume_sma=1.0 + (i * 0.05),
            trend_state="bullish" if i % 3 == 0 else "bearish",
            confluence_score=60.0 + (i * 2),
            confidence=0.6 + (i * 0.02),
            direction="long" if i % 2 == 0 else "short",
            entry_price=49000.0 + (i * 100),
            price_change_24h=(-2.0 if i % 2 else 2.0) + (i * 0.1),
            volatility=0.1 + (i * 0.01),
            outcome=1 if is_win else 0,
            pnl_percent=(1.5 if is_win else -0.8) + (i * 0.05),
            holding_period_minutes=30 + (i * 5),
            predicted_prob=0.6 + (i * 0.02),
            confidence_bin=min(6 + i, 10),
        )
        samples.append(sample)

    return samples


@pytest.fixture
def training_dataset(sample_training_samples: list[TrainingSample]) -> TrainingDataset:
    """Create a training dataset with samples."""
    dataset = TrainingDataset()
    for sample in sample_training_samples:
        dataset.add_sample(sample)
    return dataset


# =============================================================================
# Mock Component Fixtures
# =============================================================================


class MockFeatureExtractor:
    """Mock feature extractor for testing."""

    def __init__(self, samples: list[TrainingSample] | None = None):
        self._samples = samples or []
        self._sample_idx = 0
        self.extract_calls: list[str] = []

    async def extract_features(self, signal_id: str) -> Mock | None:
        """Mock feature extraction."""
        self.extract_calls.append(signal_id)

        if self._sample_idx < len(self._samples):
            sample = self._samples[self._sample_idx]
            self._sample_idx += 1
            return self._create_mock_features(sample, signal_id)
        return None

    def _create_mock_features(self, sample: TrainingSample, signal_id: str) -> Mock:
        """Create mock features from sample."""
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

    def _extract_from_signal(self, signal: Any) -> Mock:
        """Mock extraction from signal."""
        return Mock(
            signal_id=getattr(signal, "signal_id", "unknown"),
            timestamp=getattr(signal, "timestamp", datetime.now(UTC)),
            token=getattr(signal, "token", "UNKNOWN"),
            timeframe=getattr(signal, "timeframe", "1h"),
        )


class MockSignalStorage:
    """Mock signal storage for testing."""

    def __init__(self, signals_with_outcomes: list | None = None):
        self._signals = signals_with_outcomes or []
        self.query_calls: list[dict] = []
        self.get_outcome_calls: list[str] = []

    async def query_signals_with_outcomes(self, **kwargs) -> list:
        """Mock query."""
        self.query_calls.append(kwargs)
        return self._signals

    async def get_outcome_by_signal_id(self, signal_id: str) -> Any | None:
        """Mock outcome retrieval."""
        self.get_outcome_calls.append(signal_id)
        for swo in self._signals:
            if hasattr(swo, "signal") and swo.signal.signal_id == signal_id:
                return getattr(swo, "outcome", None)
        return None


class MockECERetriever:
    """Mock ECE retriever for testing."""

    def __init__(self, ece_value: float | None = 0.10):
        self._ece = ece_value
        self.call_count = 0

    async def get_latest_ece(self, strategy_id: str | None = None) -> float | None:
        """Get mock ECE value."""
        self.call_count += 1
        return self._ece

    def set_ece(self, value: float | None) -> None:
        """Update ECE value."""
        self._ece = value


class MockPerformanceRetriever:
    """Mock performance retriever for testing."""

    def __init__(self, win_rate: float = 0.60, trade_count: int = 50):
        self._win_rate = win_rate
        self._trade_count = trade_count
        self.call_count = 0

    async def get_win_rate(
        self, min_trades: int, lookback_days: int, strategy_id: str | None = None
    ) -> tuple[float | None, int]:
        """Get mock win rate."""
        self.call_count += 1
        return self._win_rate, self._trade_count

    def set_metrics(self, win_rate: float, trade_count: int) -> None:
        """Update performance metrics."""
        self._win_rate = win_rate
        self._trade_count = trade_count


class MockTrainingPipelineRunner:
    """Mock pipeline runner for testing."""

    def __init__(
        self,
        success: bool = True,
        metrics: dict | None = None,
        delay_seconds: float = 0.01,
    ):
        self._success = success
        self._metrics = metrics or {
            "accuracy": 0.85,
            "precision": 0.82,
            "recall": 0.80,
            "f1": 0.81,
            "model_version": "v1.0.0_test",
        }
        self._delay = delay_seconds
        self.run_calls: list[dict] = []

    async def run_training(
        self, sample_count: int | None = None, validation_split: float = 0.2
    ) -> tuple[bool, dict]:
        """Run mock training."""
        self.run_calls.append(
            {
                "sample_count": sample_count,
                "validation_split": validation_split,
            }
        )
        await asyncio.sleep(self._delay)
        return self._success, self._metrics

    def set_success(self, success: bool, metrics: dict | None = None) -> None:
        """Update training result."""
        self._success = success
        if metrics:
            self._metrics = metrics


class MockDataProvider:
    """Mock data provider for testing."""

    def __init__(
        self,
        sample_count: int = 1000,
        valid_samples: int = 950,
        missing_features_pct: float = 2.0,
        stale_data_pct: float = 1.0,
        prep_success: bool = True,
    ):
        self._summary = {
            "sample_count": sample_count,
            "valid_samples": valid_samples,
            "missing_features_pct": missing_features_pct,
            "stale_data_pct": stale_data_pct,
        }
        self._prep_success = prep_success
        self.summary_calls: list = []
        self.prep_calls: list = []

    async def get_training_data_summary(self) -> dict:
        """Get mock data summary."""
        self.summary_calls.append({})
        return self._summary

    async def prepare_training_data(self) -> tuple[bool, int]:
        """Prepare mock training data."""
        self.prep_calls.append({})
        return self._prep_success, self._summary["valid_samples"]

    def set_quality(
        self,
        sample_count: int,
        valid_samples: int,
        missing_features_pct: float = 0.0,
        stale_data_pct: float = 0.0,
    ) -> None:
        """Update data quality metrics."""
        self._summary = {
            "sample_count": sample_count,
            "valid_samples": valid_samples,
            "missing_features_pct": missing_features_pct,
            "stale_data_pct": stale_data_pct,
        }


class InMemoryModelStorage:
    """In-memory model storage for testing."""

    def __init__(self):
        self._versions: dict[str, ModelVersion] = {}
        self._champions: dict[ModelType, str] = {}

    async def save(self, version: ModelVersion) -> bool:
        """Save model version."""
        self._versions[version.version_id] = version
        if version.status == ModelStatus.CHAMPION:
            self._champions[version.model_type] = version.version_id
        return True

    async def load(self, version_id: str) -> ModelVersion | None:
        """Load model version."""
        return self._versions.get(version_id)

    async def list_versions(
        self,
        model_type: ModelType | None = None,
        status: ModelStatus | None = None,
    ) -> list[ModelVersion]:
        """List model versions."""
        versions = list(self._versions.values())
        if model_type:
            versions = [v for v in versions if v.model_type == model_type]
        if status:
            versions = [v for v in versions if v.status == status]
        return versions

    async def get_champion(self, model_type: ModelType) -> ModelVersion | None:
        """Get current champion."""
        champion_id = self._champions.get(model_type)
        if champion_id:
            return self._versions.get(champion_id)
        return None


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def mock_extractor(
    sample_training_samples: list[TrainingSample],
) -> MockFeatureExtractor:
    """Create mock feature extractor with sample data."""
    return MockFeatureExtractor(sample_training_samples)


@pytest.fixture
def mock_storage() -> MockSignalStorage:
    """Create mock signal storage."""
    return MockSignalStorage()


@pytest.fixture
def pipeline_config() -> PipelineConfig:
    """Create pipeline configuration for testing."""
    return PipelineConfig(
        batch_size=5,
        max_concurrent=3,
        cache_enabled=False,
        skip_on_missing_data=True,
        enrichment_enabled=True,
    )


@pytest.fixture
def training_pipeline(
    mock_extractor: MockFeatureExtractor,
    mock_storage: MockSignalStorage,
    pipeline_config: PipelineConfig,
) -> TrainingPipeline:
    """Create training pipeline with mock components."""
    return TrainingPipeline(
        extractor=mock_extractor,
        signal_storage=mock_storage,
        config=pipeline_config,
    )


@pytest.fixture
def promotion_criteria() -> PromotionCriteria:
    """Create promotion criteria for testing."""
    return PromotionCriteria(
        min_accuracy=0.75,
        min_precision=0.70,
        min_recall=0.70,
        min_f1=0.72,
        max_ece=0.15,
        require_outperformance=True,
        outperformance_margin_pct=2.0,
        require_human_approval=False,  # Disable for automated testing
    )


@pytest.fixture
def model_registry(promotion_criteria: PromotionCriteria) -> ModelRegistry:
    """Create model registry with test criteria."""
    return ModelRegistry(promotion_criteria=promotion_criteria)


@pytest.fixture
def model_registry_with_storage(
    promotion_criteria: PromotionCriteria,
) -> tuple[ModelRegistry, InMemoryModelStorage]:
    """Create model registry with in-memory storage."""
    storage = InMemoryModelStorage()
    registry = ModelRegistry(storage=storage, promotion_criteria=promotion_criteria)
    return registry, storage


@pytest.fixture
def retraining_trigger_config() -> RetrainingTriggerConfig:
    """Create retraining trigger configuration for testing."""
    return RetrainingTriggerConfig(
        deduplication_window_hours=1,
        min_data_quality_pct=90.0,
        enable_discord_alerts=False,
    )


@pytest.fixture
def retraining_trigger(
    retraining_trigger_config: RetrainingTriggerConfig,
) -> RetrainingTrigger:
    """Create retraining trigger with mock retrievers."""
    dedup_store = InMemoryDeduplicationStore()
    ece_retriever = MockECERetriever(ece_value=0.10)
    perf_retriever = MockPerformanceRetriever(win_rate=0.60, trade_count=50)

    return RetrainingTrigger(
        config=retraining_trigger_config,
        dedup_store=dedup_store,
        ece_retriever=ece_retriever,
        performance_retriever=perf_retriever,
    )


@pytest.fixture
def orchestrator_config() -> OrchestratorConfig:
    """Create orchestrator configuration for testing."""
    return OrchestratorConfig(
        min_training_interval_hours=0,
        max_training_duration_hours=1,
        enable_auto_trigger=True,
        enable_discord_notifications=False,
        validation_timeout_seconds=30.0,
    )


@pytest.fixture
def training_orchestrator(
    orchestrator_config: OrchestratorConfig,
    retraining_trigger: RetrainingTrigger,
) -> TrainingOrchestrator:
    """Create training orchestrator with mock components."""
    data_provider = MockDataProvider(
        sample_count=1000,
        valid_samples=950,
        missing_features_pct=2.0,
        stale_data_pct=1.0,
    )

    pipeline_runner = MockTrainingPipelineRunner(success=True)

    return TrainingOrchestrator(
        trigger=retraining_trigger,
        config=orchestrator_config,
        data_provider=data_provider,
        pipeline_runner=pipeline_runner,
    )


@pytest.fixture
def all_enabled_feature_flags() -> FeatureFlags:
    """Create feature flags with all retraining features enabled."""
    return FeatureFlags(
        retraining_ece_trigger=True,
        retraining_performance_trigger=True,
        retraining_scheduled_trigger=True,
        retraining_deduplication=True,
        retraining_pre_validation=True,
        retraining_discord_alerts=False,
    )


@pytest.fixture
def all_disabled_feature_flags() -> FeatureFlags:
    """Create feature flags with all retraining features disabled."""
    return FeatureFlags(
        retraining_ece_trigger=False,
        retraining_performance_trigger=False,
        retraining_scheduled_trigger=False,
        retraining_deduplication=False,
        retraining_pre_validation=False,
        retraining_discord_alerts=False,
    )


@pytest.fixture
def reset_feature_flags_fixture():
    """Reset feature flags after test."""
    yield
    reset_feature_flags()


# =============================================================================
# Helper Functions
# =============================================================================


def create_test_model_version(
    registry: ModelRegistry,
    model_id: str,
    metrics: dict[str, float] | None = None,
    model_type: ModelType = ModelType.SIGNAL_PREDICTOR,
) -> ModelVersion:
    """Helper to create a test model version."""
    default_metrics = {
        "accuracy": 0.80,
        "precision": 0.78,
        "recall": 0.76,
        "f1": 0.77,
    }
    return registry.register_model(
        model_id=model_id,
        model_path=f"/models/{model_id}.pkl",
        model_type=model_type,
        metrics=metrics or default_metrics,
    )


def promote_to_champion(
    registry: ModelRegistry,
    version: ModelVersion,
    force: bool = False,
) -> ModelVersion:
    """Helper to promote a version through the full lifecycle to champion."""
    candidate = registry.promote_to_candidate(version.version_id)
    challenger = registry.promote_to_challenger(candidate.version_id)
    champion, _ = registry.promote_to_champion(challenger.version_id, force=force)
    return champion


def create_poor_quality_data_provider() -> MockDataProvider:
    """Create a data provider with poor quality data for testing failures."""
    return MockDataProvider(
        sample_count=100,
        valid_samples=50,
        missing_features_pct=30.0,
        stale_data_pct=20.0,
        prep_success=False,
    )


def create_high_ece_trigger() -> RetrainingTrigger:
    """Create a trigger with high ECE to force triggering."""
    config = RetrainingTriggerConfig(
        deduplication_window_hours=0,
        min_data_quality_pct=90.0,
        enable_discord_alerts=False,
    )
    return RetrainingTrigger(
        config=config,
        dedup_store=InMemoryDeduplicationStore(),
        ece_retriever=MockECERetriever(ece_value=0.20),  # Above threshold
        performance_retriever=MockPerformanceRetriever(win_rate=0.60),
    )


def create_low_performance_trigger() -> RetrainingTrigger:
    """Create a trigger with low performance to force triggering."""
    config = RetrainingTriggerConfig(
        deduplication_window_hours=0,
        min_data_quality_pct=90.0,
        enable_discord_alerts=False,
    )
    return RetrainingTrigger(
        config=config,
        dedup_store=InMemoryDeduplicationStore(),
        ece_retriever=MockECERetriever(ece_value=0.10),
        performance_retriever=MockPerformanceRetriever(
            win_rate=0.50,  # Below threshold
            trade_count=50,
        ),
    )


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Configure pytest for training E2E tests."""
    config.addinivalue_line(
        "markers",
        "training_e2e: marks tests as training E2E tests (may be slow)",
    )
    config.addinivalue_line(
        "markers",
        "training_integration: marks tests as training integration tests",
    )


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
