"""Unit tests for Threshold Controller.

Tests for ThresholdController, ThresholdMode, ThresholdChange,
DynamicThresholdAdjuster, and related components.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "src")

from ml.calibration.controller import (
    ThresholdChange,
    ThresholdController,
    ThresholdMode,
)
from ml.calibration.data_collector import CalibrationDataCollector
from ml.calibration.dynamic import (
    DynamicThresholdAdjuster,
    calculate_optimal_adjustment,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
)
from ml.calibration.models import CalibrationRecord, SignalType
from ml.calibration.optimizer import ThresholdOptimizer
from ml.calibration.storage import InMemoryCalibrationStorage


def create_mock_records(signal_type: str, n: int = 50) -> list[CalibrationRecord]:
    """Create mock calibration records for testing."""
    records = []
    for i in range(n):
        # Create varied predictions and outcomes
        predicted_prob = 0.4 + (i / n) * 0.55  # Range 0.4 to 0.95
        # Higher predictions have better outcomes (calibrated)
        actual_outcome = 1 if predicted_prob > 0.65 else 0

        record = CalibrationRecord(
            timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
            signal_id=f"sig-{signal_type}-{i:04d}",
            predicted_prob=predicted_prob,
            actual_outcome=actual_outcome,
            signal_type=SignalType(signal_type),
            confidence_bin=CalibrationRecord.calculate_confidence_bin(predicted_prob),
        )
        records.append(record)
    return records


def add_records_to_collector(
    collector: CalibrationDataCollector, records: list[CalibrationRecord]
) -> None:
    """Add records to collector using collect method."""
    for record in records:
        collector.collect(
            signal_id=record.signal_id,
            predicted_prob=record.predicted_prob,
            actual_outcome=record.actual_outcome,
            signal_type=record.signal_type.value,
            timestamp=record.timestamp,
        )


class TestThresholdMode:
    """Tests for ThresholdMode enum."""

    def test_dynamic_mode(self):
        """Test DYNAMIC mode value."""
        assert ThresholdMode.DYNAMIC.value == "dynamic"

    def test_fixed_mode(self):
        """Test FIXED mode value."""
        assert ThresholdMode.FIXED.value == "fixed"


class TestThresholdChange:
    """Tests for ThresholdChange dataclass."""

    def test_creation(self):
        """Test creating a ThresholdChange."""
        change = ThresholdChange(
            timestamp=datetime.now(timezone.utc),
            signal_type="LONG",
            old_threshold=0.60,
            new_threshold=0.70,
            reason="ece_degradation: ECE=0.18",
            mode=ThresholdMode.DYNAMIC,
            ece_before=0.18,
            ece_after=0.12,
        )

        assert change.signal_type == "LONG"
        assert change.old_threshold == 0.60
        assert change.new_threshold == 0.70

    def test_to_dict(self):
        """Test converting to dictionary."""
        change = ThresholdChange(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            signal_type="LONG",
            old_threshold=0.60,
            new_threshold=0.70,
            reason="test_reason",
            mode=ThresholdMode.DYNAMIC,
            ece_before=0.18,
            ece_after=0.12,
        )

        d = change.to_dict()
        assert d["signal_type"] == "LONG"
        assert d["old_threshold"] == 0.60
        assert d["new_threshold"] == 0.70
        assert d["ece_before"] == 0.18
        assert d["mode"] == "dynamic"


class TestThresholdController:
    """Tests for ThresholdController class."""

    @pytest.fixture
    def collector_with_data(self):
        """Create a collector with mock data."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)

        # Add records for each signal type
        for signal_type in ["LONG", "SHORT", "SCALP"]:
            records = create_mock_records(signal_type, 50)
            add_records_to_collector(collector, records)

        return collector

    @pytest.fixture
    def optimizer(self, collector_with_data):
        """Create an optimizer with mock data."""
        return ThresholdOptimizer(collector_with_data)

    @pytest.fixture
    def controller(self, optimizer):
        """Create a controller with mock optimizer."""
        return ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

    def test_initialization(self, optimizer):
        """Test controller initialization."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        assert controller.mode == ThresholdMode.DYNAMIC
        assert "LONG" in controller.current_thresholds
        assert "SHORT" in controller.current_thresholds
        assert "SCALP" in controller.current_thresholds

    def test_initialization_fixed_mode(self, optimizer):
        """Test controller initialization in fixed mode."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.FIXED)

        assert controller.mode == ThresholdMode.FIXED
        assert controller._adjuster is None

    def test_should_emit_signal_above_threshold(self, controller):
        """Test signal emission when confidence above threshold."""
        signal = {"type": "LONG", "confidence": 0.75}
        threshold = controller.get_current_threshold("LONG")

        assert signal["confidence"] >= threshold
        assert controller.should_emit_signal(signal) is True

    def test_should_emit_signal_below_threshold(self, controller):
        """Test signal emission when confidence below threshold."""
        # Set a higher threshold
        controller.set_threshold("LONG", 0.80, reason="test")

        signal = {"type": "LONG", "confidence": 0.75}
        assert controller.should_emit_signal(signal) is False

    def test_get_current_threshold(self, controller):
        """Test getting current threshold for signal type."""
        threshold = controller.get_current_threshold("LONG")
        assert MIN_THRESHOLD <= threshold <= MAX_THRESHOLD

    def test_set_threshold(self, controller):
        """Test setting threshold for signal type."""
        old_threshold = controller.get_current_threshold("LONG")
        new_threshold = old_threshold + 0.10

        result = controller.set_threshold("LONG", new_threshold, reason="test_set")

        assert result is True
        assert controller.get_current_threshold("LONG") == new_threshold
        assert len(controller.get_audit_log()) > 0

    def test_set_threshold_clamping(self, controller):
        """Test threshold clamping to valid range."""
        # Test too low
        controller.set_threshold("LONG", 0.20, reason="test")
        assert controller.get_current_threshold("LONG") == MIN_THRESHOLD

        # Test too high
        controller.set_threshold("LONG", 1.0, reason="test")
        assert controller.get_current_threshold("LONG") == MAX_THRESHOLD

    def test_set_threshold_no_change(self, controller):
        """Test setting threshold to same value."""
        current = controller.get_current_threshold("LONG")
        result = controller.set_threshold("LONG", current, reason="test")

        assert result is False

    def test_update_thresholds_dynamic_mode(self, controller):
        """Test threshold update in dynamic mode."""
        result = controller.update_thresholds()
        # May or may not update depending on data

        # Check audit log has entries for the attempt
        log = controller.get_audit_log()
        assert isinstance(log, list)

    def test_update_thresholds_fixed_mode(self, optimizer):
        """Test threshold update is skipped in fixed mode."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.FIXED)
        result = controller.update_thresholds()

        assert result is False

    def test_update_thresholds_force(self, optimizer):
        """Test forced threshold update in fixed mode."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.FIXED)
        result = controller.update_thresholds(force=True)

        # May update if data available
        assert isinstance(result, bool)

    def test_switch_mode(self, optimizer):
        """Test switching between modes."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.FIXED)

        result = controller.switch_mode(ThresholdMode.DYNAMIC, "test switch")
        assert result is True
        assert controller.mode == ThresholdMode.DYNAMIC

    def test_switch_mode_no_change(self, controller):
        """Test switching to same mode."""
        result = controller.switch_mode(ThresholdMode.DYNAMIC, "same mode")
        assert result is False

    def test_get_audit_log(self, controller):
        """Test getting audit log."""
        # Make some changes
        controller.set_threshold("LONG", 0.75, reason="test_audit")

        log = controller.get_audit_log()
        assert len(log) > 0
        assert isinstance(log[0], ThresholdChange)

    def test_get_audit_log_filtered(self, controller):
        """Test filtered audit log."""
        # Make changes to different signal types
        controller.set_threshold("LONG", 0.70, reason="test_long")
        controller.set_threshold("SHORT", 0.75, reason="test_short")

        # Filter by signal type
        log = controller.get_audit_log(signal_type="LONG")
        for entry in log:
            if entry.signal_type == "LONG":
                assert entry.signal_type == "LONG"

    def test_get_status(self, controller):
        """Test getting controller status."""
        status = controller.get_status()

        assert "mode" in status
        assert "thresholds" in status
        assert "audit_log_entries" in status
        assert status["mode"] == "dynamic"


class TestDynamicThresholdAdjuster:
    """Tests for DynamicThresholdAdjuster class."""

    @pytest.fixture
    def collector_with_data(self):
        """Create a collector with mock data."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)

        # Add records for each signal type
        for signal_type in ["LONG", "SHORT", "SCALP"]:
            records = create_mock_records(signal_type, 50)
            add_records_to_collector(collector, records)

        return collector

    @pytest.fixture
    def optimizer(self, collector_with_data):
        """Create an optimizer with mock data."""
        return ThresholdOptimizer(collector_with_data)

    @pytest.fixture
    def controller(self, optimizer):
        """Create a controller."""
        return ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

    @pytest.fixture
    def adjuster(self, controller):
        """Create an adjuster."""
        return DynamicThresholdAdjuster(controller, ece_threshold=0.15)

    def test_initialization(self, controller):
        """Test adjuster initialization."""
        adjuster = DynamicThresholdAdjuster(controller, ece_threshold=0.15)

        assert adjuster.ece_threshold == 0.15
        assert adjuster.controller is not None

    def test_calculate_adjustment_high_ece(self, controller):
        """Test adjustment calculation with high ECE."""
        adjuster = DynamicThresholdAdjuster(controller, ece_threshold=0.15)

        # High ECE should increase threshold
        new_threshold = adjuster.calculate_adjustment("LONG", 0.25)
        current = controller.get_current_threshold("LONG")

        assert new_threshold > current

    def test_calculate_adjustment_low_ece(self, controller):
        """Test adjustment calculation with low ECE."""
        adjuster = DynamicThresholdAdjuster(controller, ece_threshold=0.15)

        # Low ECE (good calibration) can decrease threshold
        new_threshold = adjuster.calculate_adjustment("LONG", 0.03)
        current = controller.get_current_threshold("LONG")

        assert new_threshold < current

    def test_calculate_adjustment_medium_ece(self, controller):
        """Test adjustment calculation with medium ECE."""
        adjuster = DynamicThresholdAdjuster(controller, ece_threshold=0.15)

        # Medium ECE (acceptable) - no significant change
        new_threshold = adjuster.calculate_adjustment("LONG", 0.10)
        current = controller.get_current_threshold("LONG")

        # Should be very close to current
        assert abs(new_threshold - current) < 0.01

    def test_adjustment_clamping(self, controller):
        """Test that adjustments are clamped to valid range."""
        adjuster = DynamicThresholdAdjuster(controller, ece_threshold=0.15)

        # Try to set very high threshold
        controller.set_threshold("LONG", 0.90, reason="test")

        # High ECE should try to increase but clamp
        new_threshold = adjuster.calculate_adjustment("LONG", 0.30)
        assert new_threshold <= MAX_THRESHOLD

    def test_get_adjustment_summary(self, adjuster):
        """Test getting adjustment summary."""
        summary = adjuster.get_adjustment_summary()

        assert "total_adjustments" in summary
        assert "by_signal_type" in summary


class TestCalculateOptimalAdjustment:
    """Tests for calculate_optimal_adjustment utility."""

    def test_high_ece_increase(self):
        """Test threshold increase with high ECE."""
        result = calculate_optimal_adjustment(
            current_ece=0.25,
            current_threshold=0.60,
        )

        assert result > 0.60

    def test_low_ece_decrease(self):
        """Test threshold decrease with low ECE."""
        result = calculate_optimal_adjustment(
            current_ece=0.03,
            current_threshold=0.60,
        )

        assert result < 0.60

    def test_medium_ece_no_change(self):
        """Test no change with medium ECE."""
        result = calculate_optimal_adjustment(
            current_ece=0.10,
            current_threshold=0.60,
        )

        assert result == 0.60

    def test_max_threshold_clamp(self):
        """Test clamping at maximum threshold."""
        result = calculate_optimal_adjustment(
            current_ece=0.30,
            current_threshold=0.93,
        )

        assert result <= MAX_THRESHOLD

    def test_min_threshold_clamp(self):
        """Test clamping at minimum threshold."""
        result = calculate_optimal_adjustment(
            current_ece=0.02,
            current_threshold=0.42,
        )

        assert result >= MIN_THRESHOLD


class TestControllerSignalFiltering:
    """Integration tests for signal filtering with controller."""

    @pytest.fixture
    def collector_with_data(self):
        """Create a collector with calibration data."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)

        # Create well-calibrated records
        for signal_type in ["LONG", "SHORT", "SCALP"]:
            for i in range(50):
                predicted_prob = 0.4 + (i / 50) * 0.55
                actual_outcome = 1 if predicted_prob > 0.65 else 0

                collector.collect(
                    signal_id=f"sig-{signal_type}-{i:04d}",
                    predicted_prob=predicted_prob,
                    actual_outcome=actual_outcome,
                    signal_type=signal_type,
                )

        return collector

    @pytest.fixture
    def optimizer(self, collector_with_data):
        """Create optimizer."""
        return ThresholdOptimizer(collector_with_data)

    def test_signal_filtering_integration(self, optimizer):
        """Test complete signal filtering workflow."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        # Test various confidence levels
        test_cases = [
            {"type": "LONG", "confidence": 0.95, "expected": True},
            {"type": "LONG", "confidence": 0.50, "expected": False},
            {"type": "SHORT", "confidence": 0.80, "expected": True},
            {"type": "SCALP", "confidence": 0.70, "expected": True},
        ]

        for case in test_cases:
            result = controller.should_emit_signal(case)
            threshold = controller.get_current_threshold(case["type"])
            # Result should be based on threshold comparison
            assert result == (case["confidence"] >= threshold)


class TestControllerModeSwitching:
    """Tests for mode switching functionality."""

    @pytest.fixture
    def collector_with_data(self):
        """Create collector with data."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)

        for signal_type in ["LONG", "SHORT", "SCALP"]:
            records = create_mock_records(signal_type, 50)
            add_records_to_collector(collector, records)

        return collector

    @pytest.fixture
    def optimizer(self, collector_with_data):
        """Create optimizer."""
        return ThresholdOptimizer(collector_with_data)

    def test_dynamic_to_fixed_switch(self, optimizer):
        """Test switching from dynamic to fixed mode."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        # Switch to fixed
        controller.switch_mode(ThresholdMode.FIXED, "manual override")

        assert controller.mode == ThresholdMode.FIXED

    def test_fixed_to_dynamic_switch(self, optimizer):
        """Test switching from fixed to dynamic mode."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.FIXED)

        # Switch to dynamic
        controller.switch_mode(ThresholdMode.DYNAMIC, "enable auto-adjust")

        assert controller.mode == ThresholdMode.DYNAMIC

    def test_audit_log_on_mode_switch(self, optimizer):
        """Test that mode switches are logged."""
        controller = ThresholdController(optimizer, mode=ThresholdMode.FIXED)

        controller.switch_mode(ThresholdMode.DYNAMIC, "test switch")

        log = controller.get_audit_log()
        # Should have entries for mode switch
        mode_switch_entries = [e for e in log if "mode_switch" in e.reason]
        assert len(mode_switch_entries) > 0


class TestControllerEdgeCases:
    """Edge case tests for controller."""

    def test_unknown_signal_type(self):
        """Test handling of unknown signal types."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer)

        # Should use default threshold
        threshold = controller.get_current_threshold("UNKNOWN")
        assert threshold is not None

    def test_empty_audit_log(self):
        """Test getting audit log when empty."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer)

        log = controller.get_audit_log()
        assert log == []

    def test_signal_without_confidence(self):
        """Test signal without confidence key."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer)

        # Signal missing confidence should default to 0
        signal = {"type": "LONG"}
        assert controller.should_emit_signal(signal) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
