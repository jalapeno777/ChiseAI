"""Calibration Data Collector Module for ChiseAI.

This module provides the infrastructure for collecting prediction vs outcome
pairs for calibration analysis. It gathers model prediction probabilities and
compares them with actual trade outcomes to measure calibration accuracy.

Components:
- models: Data models and schemas for calibration records
- storage: Redis time-series storage backend
- data_collector: Main collector class for gathering calibration data
- exporter: Parquet/CSV export functionality for ECE analysis
- dynamic: Dynamic threshold adjustment with guardrails
- telemetry_exporter: InfluxDB metrics export for Grafana
- health_monitor: Calibration health monitoring and alerts

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

# Data Collector
from ml.calibration.data_collector import (
    CalibrationDataCollector,
    CollectionResult,
)

# Dynamic Threshold Adjuster
from ml.calibration.dynamic import (
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_VELOCITY_LIMIT,
    ECE_DEGRADATION_THRESHOLD,
    ECE_IMPROVEMENT_THRESHOLD,
    MAX_ADJUSTMENT_PER_STEP,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    AdjustmentGuardrails,
    DynamicThresholdAdjuster,
    ThresholdAdjustment,
    calculate_optimal_adjustment,
)

# Exporter
from ml.calibration.exporter import (
    CalibrationExporter,
    ExportFormat,
)

# Health Monitor
from ml.calibration.health_monitor import (
    ECE_ALERT_THRESHOLD,
    ECE_CRITICAL_THRESHOLD,
    AdjustmentFrequencyMetrics,
    CalibrationAlert,
    CalibrationHealthMonitor,
    CalibrationStatus,
)

# Models
from ml.calibration.models import (
    CalibrationConfig,
    CalibrationRecord,
    CollectionWindow,
    SignalType,
)

# Storage
from ml.calibration.storage import (
    CalibrationStorage,
    InMemoryCalibrationStorage,
    RedisCalibrationStorage,
)

# Telemetry Exporter
from ml.calibration.telemetry_exporter import (
    CalibrationHealthMetrics,
    CalibrationTelemetryConfig,
    CalibrationTelemetryExporter,
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
    # Dynamic Threshold Adjuster
    "DynamicThresholdAdjuster",
    "ThresholdAdjustment",
    "AdjustmentGuardrails",
    "calculate_optimal_adjustment",
    "MIN_THRESHOLD",
    "MAX_THRESHOLD",
    "MAX_ADJUSTMENT_PER_STEP",
    "ECE_DEGRADATION_THRESHOLD",
    "ECE_IMPROVEMENT_THRESHOLD",
    "DEFAULT_VELOCITY_LIMIT",
    "DEFAULT_COOLDOWN_MINUTES",
    # Telemetry Exporter
    "CalibrationTelemetryExporter",
    "CalibrationTelemetryConfig",
    "CalibrationHealthMetrics",
    # Health Monitor
    "CalibrationHealthMonitor",
    "CalibrationAlert",
    "AdjustmentFrequencyMetrics",
    "CalibrationStatus",
    "ECE_ALERT_THRESHOLD",
    "ECE_CRITICAL_THRESHOLD",
]
