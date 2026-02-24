"""Training Data Module for ChiseAI.

This module provides training data schema and storage for ML model retraining.

Components:
- schema: Pydantic models for training samples and datasets
- features: Feature specifications and validation
- storage_format: Export/import handlers (Parquet, CSV, JSON)
- version: Schema versioning and compatibility
- extractor: Feature extraction from signals and market data
- pipeline: End-to-end training data pipeline
- exporter: Dataset export for ML frameworks
- retraining_trigger: Automatic retraining triggers (ECE, performance, scheduled)
- training_orchestrator: Training workflow orchestration with trigger integration
- pipeline_integration: Training pipeline integration with feedback loop
  and model registry

Usage:
    from ml.training import (
        TrainingSample,
        TrainingDataset,
        FeatureValidator,
        FeatureSpec,
        FeatureType,
        TrendState,
        StorageFormatManager,
        DatasetMetadata,
        SchemaVersion,
        SchemaVersionManager,
        FeatureExtractor,
        TrainingPipeline,
        PipelineConfig,
        PipelineStats,
        DatasetExporter,
        ExportFormat,
        DatasetInfo,
        DatasetStatistics,
    )

    # Create a training sample
    sample = TrainingSample(
        token="BTC",
        timeframe="1h",
        rsi=65.5,
        macd=0.5,
        trend_state="bullish",
        outcome=1,
        pnl_percent=2.5,
    )

    # Build a dataset
    dataset = TrainingDataset()
    dataset.add_sample(sample)

    # Export to Parquet
    dataset.export_parquet("training_data.parquet")

    # Use feature extraction pipeline
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    sample = await pipeline.process_signal("signal-id-123")

    # Export dataset for ML training
    from ml.training.exporter import DatasetExporter, ExportFormat
    exporter = DatasetExporter(pipeline)
    info = exporter.export_dataset(
        samples=[sample],
        output_path="training.parquet",
        format=ExportFormat.PARQUET,
    )
"""

from __future__ import annotations

# Exporter components
from ml.training.exporter import (
    DatasetExporter,
    DatasetInfo,
    DatasetStatistics,
    ExportFormat,
    ModelType,
    export_from_samples,
)

# Extraction and pipeline components
from ml.training.extractor import (
    ExtractedFeatures,
    FeatureExtractor,
    MarketContext,
    TechnicalIndicators,
)

# Feature components
from ml.training.features import (
    FEATURE_GROUPS,
    FEATURE_SPECS,
    FeatureSpec,
    FeatureType,
    FeatureValidator,
    TrendState,
)
from ml.training.pipeline import (
    PipelineConfig,
    PipelineStats,
    TrainingPipeline,
)

# Pipeline integration components (ST-LAUNCH-012)
from ml.training.pipeline_integration import (
    AsyncJobScheduler,
    DataFetchError,
    FeedbackLoopDataFetcher,
    GrafanaMetricsExporter,
    Hyperparameters,
    ModelRegistrationError,
    TrainingData,
    TrainingDataFetcher,
    TrainingExecutionError,
    TrainingJob,
    TrainingJobStatus,
    TrainingPipelineError,
    TrainingPipelineIntegration,
)

# Retraining trigger components
from ml.training.retraining_trigger import (
    ECE_TRIGGER_THRESHOLD,
    MIN_DATA_QUALITY_PCT,
    MIN_TRADES_FOR_PERFORMANCE,
    PERFORMANCE_WIN_RATE_THRESHOLD,
    DataQualityValidator,
    DeduplicationStore,
    DiscordNotifier,
    ECERetriever,
    ECETriggerConfig,
    InMemoryDeduplicationStore,
    PerformanceRetriever,
    PerformanceTriggerConfig,
    RedisDeduplicationStore,
    RetrainingTrigger,
    RetrainingTriggerConfig,
    ScheduledTriggerConfig,
    TriggerResult,
    TriggerStatus,
    TriggerType,
)

# Schema components
from ml.training.schema import TrainingDataset, TrainingSample

# Storage format components
from ml.training.storage_format import (
    CSVHandler,
    DatasetMetadata,
    JSONHandler,
    ParquetHandler,
    StorageFormatManager,
)

# Training orchestrator components
from ml.training.training_orchestrator import (
    OrchestratorConfig,
    TrainingOrchestrator,
    TrainingRun,
    TrainingState,
    TrainingStatus,
)

# Version components
from ml.training.version import (
    CURRENT_SCHEMA_VERSION,
    VERSION_HISTORY,
    SchemaVersion,
    SchemaVersionManager,
)

__all__ = [
    # Schema
    "TrainingSample",
    "TrainingDataset",
    # Features
    "FeatureSpec",
    "FeatureType",
    "FeatureValidator",
    "FEATURE_SPECS",
    "FEATURE_GROUPS",
    "TrendState",
    # Storage Format
    "StorageFormatManager",
    "DatasetMetadata",
    "ParquetHandler",
    "CSVHandler",
    "JSONHandler",
    # Version
    "SchemaVersion",
    "SchemaVersionManager",
    "CURRENT_SCHEMA_VERSION",
    "VERSION_HISTORY",
    # Extraction
    "FeatureExtractor",
    "ExtractedFeatures",
    "TechnicalIndicators",
    "MarketContext",
    # Pipeline
    "TrainingPipeline",
    "PipelineConfig",
    "PipelineStats",
    # Exporter
    "DatasetExporter",
    "DatasetInfo",
    "DatasetStatistics",
    "ExportFormat",
    "ModelType",
    "export_from_samples",
    # Retraining Trigger
    "RetrainingTrigger",
    "RetrainingTriggerConfig",
    "ECETriggerConfig",
    "PerformanceTriggerConfig",
    "ScheduledTriggerConfig",
    "TriggerType",
    "TriggerStatus",
    "TriggerResult",
    "DeduplicationStore",
    "InMemoryDeduplicationStore",
    "RedisDeduplicationStore",
    "DataQualityValidator",
    "DiscordNotifier",
    "ECERetriever",
    "PerformanceRetriever",
    "ECE_TRIGGER_THRESHOLD",
    "PERFORMANCE_WIN_RATE_THRESHOLD",
    "MIN_TRADES_FOR_PERFORMANCE",
    "MIN_DATA_QUALITY_PCT",
    # Training Orchestrator
    "TrainingOrchestrator",
    "OrchestratorConfig",
    "TrainingRun",
    "TrainingState",
    "TrainingStatus",
    # Pipeline Integration (ST-LAUNCH-012)
    "TrainingPipelineIntegration",
    "TrainingJob",
    "TrainingJobStatus",
    "Hyperparameters",
    "TrainingData",
    "AsyncJobScheduler",
    "FeedbackLoopDataFetcher",
    "GrafanaMetricsExporter",
    "TrainingPipelineError",
    "DataFetchError",
    "TrainingExecutionError",
    "ModelRegistrationError",
    "TrainingDataFetcher",
]
