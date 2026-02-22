"""Calibration Data Collector Module for ChiseAI.

This module provides the infrastructure for collecting prediction vs outcome
pairs for calibration analysis. It gathers model prediction probabilities and
compares them with actual trade outcomes to measure calibration accuracy.

Components:
- models: Data models and schemas for calibration records
- storage: Redis time-series storage backend
- data_collector: Main collector class for gathering calibration data
- exporter: Parquet/CSV export functionality for ECE analysis
- dynamic: Dynamic threshold adjustment with guardrails (hourly granularity)
- dynamic_threshold: Dynamic threshold engine with daily granularity (ST-LAUNCH-010)
- threshold_guardrails: Safety guardrails and manual override (ST-LAUNCH-010)
- telemetry_exporter: InfluxDB metrics export for Grafana
- health_monitor: Calibration health monitoring and alerts

Usage:
    from ml.calibration import CalibrationDataCollector, CalibrationRecord
    from ml.calibration import DynamicThresholdEngine, ThresholdGuardrails

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

    # Dynamic threshold adjustment with daily granularity
    engine = DynamicThresholdEngine(ece_provider=ece_provider)
    result = await engine.evaluate_and_adjust(
        strategy_id="grid_btc_1h",
        signal_type=SignalType.ENTRY,
        current_threshold=0.65
    )

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

# Dynamic Threshold Engine (ST-LAUNCH-010)
from ml.calibration.dynamic_threshold import (
    COOLDOWN_HOURS,
    ECE_ADJUSTMENT_THRESHOLD,
    MAX_DAILY_CHANGE_PERCENT,
    OSCILLATION_DIRECTION_CHANGES,
    OSCILLATION_FREEZE_HOURS,
    OSCILLATION_WINDOW_DAYS,
    AdjustmentHistory,
    DynamicThresholdConfig,
    DynamicThresholdEngine,
    ECEProvider,
    ThresholdAdjustmentRecord,
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

# Threshold Guardrails (ST-LAUNCH-010)
from ml.calibration.threshold_guardrails import (
    AuditEventType,
    AuditLogEntry,
    GuardrailConfig,
    ManualOverride,
    OverrideReason,
    ThresholdGuardrails,
    ThresholdStorage,
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
    # Dynamic Threshold Adjuster (original)
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
    # Dynamic Threshold Engine (ST-LAUNCH-010)
    "DynamicThresholdEngine",
    "DynamicThresholdConfig",
    "ThresholdAdjustmentRecord",
    "AdjustmentHistory",
    "ECEProvider",
    "MAX_DAILY_CHANGE_PERCENT",
    "ECE_ADJUSTMENT_THRESHOLD",
    "COOLDOWN_HOURS",
    "OSCILLATION_WINDOW_DAYS",
    "OSCILLATION_FREEZE_HOURS",
    "OSCILLATION_DIRECTION_CHANGES",
    # Threshold Guardrails (ST-LAUNCH-010)
    "ThresholdGuardrails",
    "ManualOverride",
    "OverrideReason",
    "AuditLogEntry",
    "AuditEventType",
    "GuardrailConfig",
    "ThresholdStorage",
]
