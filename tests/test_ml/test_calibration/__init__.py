"""Tests for calibration module initialization and imports."""

from __future__ import annotations

import sys

sys.path.insert(0, "src")


def test_module_imports():
    """Test that all module components can be imported."""
    from ml.calibration import (
        CollectionWindow,
        ExportFormat,
        SignalType,
    )

    # Verify all imports are the expected types
    assert isinstance(SignalType.LONG, SignalType)
    assert isinstance(CollectionWindow.ONE_DAY, CollectionWindow)
    assert isinstance(ExportFormat.CSV, ExportFormat)


def test_calibration_record_creation():
    """Test creating a CalibrationRecord through the public API."""
    from datetime import UTC, datetime

    from ml.calibration import CalibrationRecord, SignalType

    record = CalibrationRecord(
        timestamp=datetime.now(UTC),
        signal_id="test-sig-001",
        predicted_prob=0.75,
        actual_outcome=1,
        signal_type=SignalType.LONG,
        confidence_bin=7,
    )

    assert record.signal_id == "test-sig-001"
    assert record.predicted_prob == 0.75
    assert record.signal_type == SignalType.LONG


def test_calibration_config_creation():
    """Test creating a CalibrationConfig through the public API."""
    from ml.calibration import CalibrationConfig, CollectionWindow

    config = CalibrationConfig(
        n_bins=10,
        retention_days=90,
        default_window=CollectionWindow.ONE_DAY,
    )

    assert config.n_bins == 10
    assert config.retention_days == 90
    assert config.default_window == CollectionWindow.ONE_DAY


def test_data_collector_creation():
    """Test creating a CalibrationDataCollector through the public API."""
    from ml.calibration import CalibrationConfig, CalibrationDataCollector

    config = CalibrationConfig()
    collector = CalibrationDataCollector(config=config)

    assert collector.config == config
    assert collector._storage is None  # Will be created on first use
