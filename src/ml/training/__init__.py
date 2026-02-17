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

# Schema components
from ml.training.schema import TrainingSample, TrainingDataset

# Feature components
from ml.training.features import (
    FeatureSpec,
    FeatureType,
    FeatureValidator,
    FEATURE_SPECS,
    FEATURE_GROUPS,
    TrendState,
)

# Storage format components
from ml.training.storage_format import (
    StorageFormatManager,
    DatasetMetadata,
    ParquetHandler,
    CSVHandler,
    JSONHandler,
)

# Version components
from ml.training.version import (
    SchemaVersion,
    SchemaVersionManager,
    CURRENT_SCHEMA_VERSION,
    VERSION_HISTORY,
)

# Extraction and pipeline components
from ml.training.extractor import (
    FeatureExtractor,
    ExtractedFeatures,
    TechnicalIndicators,
    MarketContext,
)
from ml.training.pipeline import (
    TrainingPipeline,
    PipelineConfig,
    PipelineStats,
)

# Exporter components
from ml.training.exporter import (
    DatasetExporter,
    DatasetInfo,
    DatasetStatistics,
    ExportFormat,
    ModelType,
    export_from_samples,
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
]
