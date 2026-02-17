"""Calibration Data Collector Module for ChiseAI.

This module provides the infrastructure for collecting prediction vs outcome
pairs for calibration analysis. It gathers model prediction probabilities and
compares them with actual trade outcomes to measure calibration accuracy.

Components:
- models: Data models and schemas for calibration records
- storage: Redis time-series storage backend
- data_collector: Main collector class for gathering calibration data
- exporter: Parquet/CSV export functionality for ECE analysis

Usage:
    from ml.calibration import CalibrationDataCollector, CalibrationRecord

    # Collect calibration data
    collector = CalibrationDataCollector()
    collector.collect(
        signal_id="test-sig-001",
        predicted_prob=0.75,
        actual_outcome=1,
        signal_type="LONG"
    )

    # Get records for analysis
    records = collector.get_records(window="24h")

    # Export for ECE analysis
    collector.export_to_parquet("calibration_data.parquet")
"""

from __future__ import annotations

# Models
from ml.calibration.models import (
    CalibrationRecord,
    CalibrationConfig,
    SignalType,
    CollectionWindow,
)

# Storage
from ml.calibration.storage import (
    CalibrationStorage,
    RedisCalibrationStorage,
    InMemoryCalibrationStorage,
)

# Data Collector
from ml.calibration.data_collector import (
    CalibrationDataCollector,
    CollectionResult,
)

# Exporter
from ml.calibration.exporter import (
    CalibrationExporter,
    ExportFormat,
)

__all__ = [
    # Models
    "CalibrationRecord",
    "CalibrationConfig",
    "SignalType",
    "CollectionWindow",
    # Storage
    "CalibrationStorage",
    "RedisCalibrationStorage",
    "InMemoryCalibrationStorage",
    # Data Collector
    "CalibrationDataCollector",
    "CollectionResult",
    # Exporter
    "CalibrationExporter",
    "ExportFormat",
]
