"""Integration tests for calibration data collector."""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from ml.calibration import CalibrationDataCollector


class TestCalibrationIntegration:
    """Integration tests for the calibration module."""

    def test_basic_integration(self):
        """Test basic integration - collect and retrieve."""
        collector = CalibrationDataCollector()

        # Collect a record
        result = collector.collect(
            signal_id="test-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type="LONG",
        )

        assert result.success is True
        assert result.record is not None
        assert result.record.signal_id == "test-sig-001"

    def test_collect_multiple_signal_types(self):
        """Test collecting different signal types."""
        collector = CalibrationDataCollector()

        signals = [
            ("long-sig-001", 0.75, 1, "LONG"),
            ("short-sig-001", 0.65, 0, "SHORT"),
            ("scalp-sig-001", 0.85, 1, "SCALP"),
        ]

        for sig_id, prob, outcome, sig_type in signals:
            result = collector.collect(
                signal_id=sig_id,
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type=sig_type,
            )
            assert result.success is True, f"Failed to collect {sig_id}"

    def test_confidence_bin_calculation(self):
        """Test that confidence bins are calculated correctly."""
        collector = CalibrationDataCollector()

        test_cases = [
            (0.05, 0),
            (0.15, 1),
            (0.55, 5),
            (0.75, 7),
            (0.95, 9),
            (1.0, 9),
        ]

        for prob, expected_bin in test_cases:
            result = collector.collect(
                signal_id=f"test-{prob}",
                predicted_prob=prob,
                actual_outcome=1,
                signal_type="LONG",
            )
            assert result.success is True
            assert result.record.confidence_bin == expected_bin, (
                f"Expected bin {expected_bin} for prob {prob}, "
                f"got {result.record.confidence_bin}"
            )

    def test_validation_errors(self):
        """Test that validation catches invalid inputs."""
        collector = CalibrationDataCollector()

        # Invalid probability
        result = collector.collect(
            signal_id="test", predicted_prob=1.5, actual_outcome=1, signal_type="LONG"
        )
        assert result.success is False

        # Invalid outcome
        result = collector.collect(
            signal_id="test", predicted_prob=0.5, actual_outcome=2, signal_type="LONG"
        )
        assert result.success is False

        # Invalid signal type
        result = collector.collect(
            signal_id="test",
            predicted_prob=0.5,
            actual_outcome=1,
            signal_type="INVALID",
        )
        assert result.success is False

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        collector = CalibrationDataCollector()

        # Clear any existing stats
        collector.clear_statistics()

        # Collect some valid records
        for i in range(3):
            collector.collect(
                signal_id=f"valid-{i}",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type="LONG",
            )

        # Collect an invalid record
        collector.collect(
            signal_id="invalid",
            predicted_prob=1.5,  # Invalid
            actual_outcome=1,
            signal_type="LONG",
        )

        stats = collector.get_statistics()
        assert stats["total_collected"] == 3
        assert stats["total_failed"] == 1
        assert stats["success_rate"] == 0.75
