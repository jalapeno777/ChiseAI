"""Tests for ECE (Expected Calibration Error) calculation module.

Tests cover:
- Binning correctness (10 equal-width bins)
- ECE calculation against known values
- Per-signal-type breakdown
- Edge cases and error handling
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from confidence.ece import ECEBin, ECECalculator, ECEResult, SignalType, calculate_ece

if TYPE_CHECKING:
    pass


class TestECEBin:
    """Tests for ECEBin dataclass."""

    def test_bin_creation(self):
        """Test ECEBin creation and auto-calculated error."""
        bin_obj = ECEBin(
            bin_index=5,
            bin_start=0.5,
            bin_end=0.6,
            confidence=0.55,
            accuracy=0.6,
            sample_count=100,
        )

        assert bin_obj.bin_index == 5
        assert bin_obj.bin_start == 0.5
        assert bin_obj.bin_end == 0.6
        assert bin_obj.confidence == 0.55
        assert bin_obj.accuracy == 0.6
        assert bin_obj.sample_count == 100
        assert bin_obj.error == pytest.approx(0.05)  # |0.6 - 0.55|

    def test_bin_weight(self):
        """Test bin weight property."""
        bin_obj = ECEBin(
            bin_index=0,
            bin_start=0.0,
            bin_end=0.1,
            confidence=0.05,
            accuracy=0.1,
            sample_count=50,
        )

        assert bin_obj.weight == 50

    def test_bin_error_calculation(self):
        """Test error is correctly calculated as |accuracy - confidence|."""
        # Perfect calibration
        perfect = ECEBin(0, 0.0, 0.1, 0.8, 0.8, 10)
        assert perfect.error == 0.0

        # Over-confident
        over = ECEBin(0, 0.0, 0.1, 0.9, 0.7, 10)
        assert over.error == pytest.approx(0.2)

        # Under-confident
        under = ECEBin(0, 0.0, 0.1, 0.6, 0.8, 10)
        assert under.error == pytest.approx(0.2)


class TestECECalculator:
    """Tests for ECECalculator class."""

    def test_default_bins(self):
        """Test default 10-bin configuration."""
        calc = ECECalculator()
        assert calc.n_bins == 10

    def test_custom_bins(self):
        """Test custom bin count."""
        calc = ECECalculator(n_bins=5)
        assert calc.n_bins == 5

    def test_bin_edges(self):
        """Test bin edges are correctly calculated."""
        calc = ECECalculator(n_bins=10)
        expected_edges = np.linspace(0.0, 1.0, 11)
        np.testing.assert_array_almost_equal(calc._bin_edges, expected_edges)

    def test_perfect_calibration(self):
        """Test ECE with perfectly calibrated predictions.

        When confidence always equals accuracy (on average per bin),
        ECE should be 0.
        """
        calc = ECECalculator(n_bins=10)

        # Create predictions where confidence matches actual accuracy
        # Bin 8: 80-90% confidence, 85% accuracy
        predictions = []
        outcomes = []

        # Add samples for each bin with matching accuracy
        for bin_idx in range(10):
            conf_center = (bin_idx + 0.5) / 10  # 0.05, 0.15, ..., 0.95
            # Create 100 predictions in this bin range
            for _ in range(100):
                predictions.append(conf_center)
                # Outcome matches confidence on average
                outcomes.append(1 if np.random.random() < conf_center else 0)

        result = calc.calculate(predictions, outcomes)

        # ECE should be low (not exactly 0 due to randomness)
        assert result.ece < 0.1
        assert result.n_bins == 10
        assert result.total_samples == 1000

    def test_perfect_miscalibration(self):
        """Test ECE with completely miscalibrated predictions.

        When predictions are always wrong but confidence is high,
        ECE should be high.
        """
        calc = ECECalculator(n_bins=10)

        # Always predict 90% confidence, always wrong
        predictions = [0.9] * 100
        outcomes = [0] * 100

        result = calc.calculate(predictions, outcomes)

        # ECE should be close to 0.9 (high confidence, 0 accuracy)
        assert result.ece > 0.8

    def test_known_ece_value(self):
        """Test ECE calculation against a known value.

        Simple case: 2 bins, equal samples
        Bin 0 (0-0.5): 10 predictions at 0.4 confidence, 3 correct (30% accuracy)
        Bin 1 (0.5-1.0): 10 predictions at 0.8 confidence, 7 correct (70% accuracy)

        ECE = 0.5 * |0.3 - 0.4| + 0.5 * |0.7 - 0.8|
            = 0.5 * 0.1 + 0.5 * 0.1
            = 0.1
        """
        calc = ECECalculator(n_bins=2)

        predictions = [0.4] * 10 + [0.8] * 10
        outcomes = [1, 1, 1, 0, 0, 0, 0, 0, 0, 0] + [1, 1, 1, 1, 1, 1, 1, 0, 0, 0]

        result = calc.calculate(predictions, outcomes)

        # Check per-bin statistics
        assert result.bins[0].confidence == pytest.approx(0.4)
        assert result.bins[0].accuracy == pytest.approx(0.3)
        assert result.bins[1].confidence == pytest.approx(0.8)
        assert result.bins[1].accuracy == pytest.approx(0.7)

        # ECE should be 0.1
        assert result.ece == pytest.approx(0.1, abs=0.01)

    def test_empty_predictions(self):
        """Test handling of empty predictions."""
        calc = ECECalculator()
        result = calc.calculate([], [])

        assert result.ece == 0.0
        assert result.total_samples == 0
        assert len(result.bins) == 0

    def test_single_sample(self):
        """Test with single sample."""
        calc = ECECalculator()
        result = calc.calculate([0.75], [1])

        assert result.total_samples == 1
        assert result.ece >= 0  # Should be |1.0 - 0.75| = 0.25

    def test_mismatched_lengths(self):
        """Test error on mismatched prediction/outcome lengths."""
        calc = ECECalculator()

        with pytest.raises(ValueError, match="same length"):
            calc.calculate([0.5, 0.6], [1])

    def test_invalid_predictions_range(self):
        """Test error on predictions outside [0, 1]."""
        calc = ECECalculator()

        with pytest.raises(ValueError, match="range"):
            calc.calculate([1.5], [1])

        with pytest.raises(ValueError, match="range"):
            calc.calculate([-0.1], [1])

    def test_invalid_outcomes(self):
        """Test error on non-binary outcomes."""
        calc = ECECalculator()

        with pytest.raises(ValueError, match="binary"):
            calc.calculate([0.5], [2])

        with pytest.raises(ValueError, match="binary"):
            calc.calculate([0.5], [-1])

    def test_signal_type_in_result(self):
        """Test signal type is preserved in result."""
        calc = ECECalculator()
        result = calc.calculate(
            [0.8, 0.9],
            [1, 1],
            signal_type=SignalType.ENTRY,
            strategy_id="test_strategy",
        )

        assert result.signal_type == SignalType.ENTRY
        assert result.strategy_id == "test_strategy"

    def test_get_bin(self):
        """Test get_bin method."""
        calc = ECECalculator()
        result = calc.calculate([0.15, 0.85], [1, 0])

        bin_0 = result.get_bin(0)
        bin_1 = result.get_bin(1)
        bin_missing = result.get_bin(99)

        assert bin_0 is not None
        assert bin_0.bin_index == 0
        assert bin_1 is not None
        assert bin_1.bin_index == 1
        assert bin_missing is None

    def test_is_well_calibrated(self):
        """Test is_well_calibrated property."""
        calc = ECECalculator()

        # Low ECE - well calibrated (default threshold 0.1)
        result_low = ECEResult(ece=0.05, n_bins=10, total_samples=100, bins=[])
        assert result_low.is_well_calibrated is True

        # High ECE - poorly calibrated (default threshold 0.1)
        result_high = ECEResult(ece=0.2, n_bins=10, total_samples=100, bins=[])
        assert result_high.is_well_calibrated is False

        # At threshold boundary
        result_boundary = ECEResult(ece=0.1, n_bins=10, total_samples=100, bins=[])
        assert result_boundary.is_well_calibrated is True


class TestPerSignalType:
    """Tests for per-signal-type ECE calculation."""

    def test_calculate_per_signal_type(self):
        """Test ECE calculation broken down by signal type."""
        calc = ECECalculator()

        predictions_by_type = {
            SignalType.ENTRY: [0.8, 0.85, 0.9],
            SignalType.EXIT: [0.7, 0.75],
            SignalType.STOP_LOSS: [0.6],
            SignalType.TAKE_PROFIT: [0.9, 0.95],
        }

        outcomes_by_type = {
            SignalType.ENTRY: [1, 1, 0],
            SignalType.EXIT: [1, 0],
            SignalType.STOP_LOSS: [1],
            SignalType.TAKE_PROFIT: [1, 1],
        }

        results = calc.calculate_per_signal_type(
            predictions_by_type, outcomes_by_type, strategy_id="test"
        )

        assert len(results) == 4
        assert SignalType.ENTRY in results
        assert SignalType.EXIT in results
        assert SignalType.STOP_LOSS in results
        assert SignalType.TAKE_PROFIT in results

        # Check strategy_id is set
        for result in results.values():
            assert result.strategy_id == "test"

    def test_mismatched_signal_types(self):
        """Test error when signal types don't match."""
        calc = ECECalculator()

        predictions_by_type = {SignalType.ENTRY: [0.8]}
        outcomes_by_type = {SignalType.EXIT: [1]}

        with pytest.raises(ValueError, match="match"):
            calc.calculate_per_signal_type(predictions_by_type, outcomes_by_type)

    def test_signal_type_values(self):
        """Test SignalType enum values."""
        assert SignalType.ENTRY.value == "entry"
        assert SignalType.EXIT.value == "exit"
        assert SignalType.STOP_LOSS.value == "sl"
        assert SignalType.TAKE_PROFIT.value == "tp"


class TestCalculatePerBin:
    """Tests for per-bin calculation."""

    def test_calculate_per_bin(self):
        """Test per-bin accuracy and confidence calculation."""
        calc = ECECalculator(n_bins=5)

        # 20 samples in each bin
        predictions = []
        for bin_idx in range(5):
            conf = (bin_idx * 0.2) + 0.1  # 0.1, 0.3, 0.5, 0.7, 0.9
            predictions.extend([conf] * 20)

        # 50% accuracy for all
        outcomes = [1, 0] * 50

        bins = calc.calculate_per_bin(predictions, outcomes)

        assert len(bins) == 5
        for i, bin_obj in enumerate(bins):
            assert bin_obj.bin_index == i
            assert bin_obj.sample_count == 20
            assert bin_obj.accuracy == pytest.approx(0.5)


class TestConvenienceFunction:
    """Tests for calculate_ece convenience function."""

    def test_calculate_ece(self):
        """Test convenience function returns correct ECE value."""
        predictions = [0.8] * 10
        outcomes = [1] * 7 + [0] * 3  # 70% accuracy

        ece = calculate_ece(predictions, outcomes, n_bins=10)

        # Should be |0.8 - 0.7| = 0.1 (approximately)
        assert ece == pytest.approx(0.1, abs=0.05)

    def test_calculate_ece_default_bins(self):
        """Test convenience function with default bins."""
        predictions = [0.5, 0.6, 0.7]
        outcomes = [1, 0, 1]

        ece = calculate_ece(predictions, outcomes)

        assert isinstance(ece, float)
        assert 0 <= ece <= 1


class TestTenBinConfiguration:
    """Tests specific to 10-bin configuration (AC requirement)."""

    def test_ten_bins_correct_ranges(self):
        """Test that 10 bins have correct ranges: 0-10%, 10-20%, etc."""
        calc = ECECalculator(n_bins=10)

        # Check bin edges
        expected_edges = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        np.testing.assert_array_almost_equal(calc._bin_edges, expected_edges)

    def test_predictions_in_correct_bins(self):
        """Test predictions are assigned to correct bins."""
        calc = ECECalculator(n_bins=10)

        # One prediction in each bin
        predictions = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
        outcomes = [1] * 10

        result = calc.calculate(predictions, outcomes)

        assert len(result.bins) == 10
        for i, bin_obj in enumerate(result.bins):
            assert bin_obj.bin_index == i
            assert bin_obj.sample_count == 1
            assert bin_obj.bin_start == pytest.approx(i * 0.1)
            assert bin_obj.bin_end == pytest.approx((i + 1) * 0.1)

    def test_boundary_predictions(self):
        """Test predictions at bin boundaries."""
        calc = ECECalculator(n_bins=10)

        # Predictions at exact boundaries
        predictions = [0.1, 0.2, 0.3, 0.5, 0.9]
        outcomes = [1] * 5

        result = calc.calculate(predictions, outcomes)

        # All should be assigned to bins
        total_samples = sum(b.sample_count for b in result.bins)
        assert total_samples == 5


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_all_same_confidence(self):
        """Test when all predictions have same confidence."""
        calc = ECECalculator()

        predictions = [0.75] * 100
        outcomes = [1] * 60 + [0] * 40  # 60% accuracy

        result = calc.calculate(predictions, outcomes)

        # All in one bin
        non_empty_bins = [b for b in result.bins if b.sample_count > 0]
        assert len(non_empty_bins) == 1
        assert non_empty_bins[0].confidence == 0.75
        assert non_empty_bins[0].accuracy == 0.6
        assert result.ece == pytest.approx(0.15)  # |0.75 - 0.6|

    def test_all_correct(self):
        """Test when all predictions are correct."""
        calc = ECECalculator()

        predictions = [0.6, 0.7, 0.8, 0.9]
        outcomes = [1, 1, 1, 1]

        result = calc.calculate(predictions, outcomes)

        # Accuracy is 1.0 for all bins
        for bin_obj in result.bins:
            if bin_obj.sample_count > 0:
                assert bin_obj.accuracy == 1.0

    def test_all_incorrect(self):
        """Test when all predictions are incorrect."""
        calc = ECECalculator()

        predictions = [0.6, 0.7, 0.8, 0.9]
        outcomes = [0, 0, 0, 0]

        result = calc.calculate(predictions, outcomes)

        # Accuracy is 0.0 for all bins
        for bin_obj in result.bins:
            if bin_obj.sample_count > 0:
                assert bin_obj.accuracy == 0.0

    def test_extreme_confidence_values(self):
        """Test with 0% and 100% confidence."""
        calc = ECECalculator()

        # Mix of 0% and 100% confidence
        predictions = [0.0] * 50 + [1.0] * 50
        outcomes = [0] * 40 + [1] * 10 + [1] * 45 + [0] * 5

        result = calc.calculate(predictions, outcomes)

        # Should have reasonable ECE
        assert 0 <= result.ece <= 1

    def test_very_small_sample(self):
        """Test with very small sample size."""
        calc = ECECalculator()

        result = calc.calculate([0.5], [1])

        assert result.total_samples == 1
        assert result.ece >= 0


class TestIntegrationScenarios:
    """Integration-style tests with realistic scenarios."""

    def test_realistic_trading_scenario(self):
        """Test with realistic trading signal data."""
        calc = ECECalculator()

        np.random.seed(42)

        # Simulate 1000 trading signals with various confidence levels
        predictions = []
        outcomes = []

        # High confidence signals (80-95%) - should be right ~85% of time
        for conf in np.random.uniform(0.8, 0.95, 300):
            predictions.append(conf)
            outcomes.append(1 if np.random.random() < 0.85 else 0)

        # Medium confidence signals (50-75%) - should be right ~60% of time
        for conf in np.random.uniform(0.5, 0.75, 500):
            predictions.append(conf)
            outcomes.append(1 if np.random.random() < 0.6 else 0)

        # Low confidence signals (30-45%) - should be right ~35% of time
        for conf in np.random.uniform(0.3, 0.45, 200):
            predictions.append(conf)
            outcomes.append(1 if np.random.random() < 0.35 else 0)

        result = calc.calculate(predictions, outcomes)

        assert result.total_samples == 1000
        assert result.n_bins == 10
        # ECE should be reasonable (not perfect, not terrible)
        assert 0 <= result.ece <= 0.3

    def test_per_signal_type_breakdown(self):
        """Test ECE breakdown by signal type for a strategy."""
        calc = ECECalculator()

        np.random.seed(42)

        # Generate data for each signal type with different calibration
        predictions_by_type = {
            SignalType.ENTRY: np.random.uniform(0.7, 0.95, 200).tolist(),
            SignalType.EXIT: np.random.uniform(0.5, 0.8, 150).tolist(),
            SignalType.STOP_LOSS: np.random.uniform(0.6, 0.9, 100).tolist(),
            SignalType.TAKE_PROFIT: np.random.uniform(0.65, 0.92, 120).tolist(),
        }

        outcomes_by_type = {
            SignalType.ENTRY: [
                1 if np.random.random() < 0.8 else 0 for _ in range(200)
            ],
            SignalType.EXIT: [
                1 if np.random.random() < 0.65 else 0 for _ in range(150)
            ],
            SignalType.STOP_LOSS: [
                1 if np.random.random() < 0.75 else 0 for _ in range(100)
            ],
            SignalType.TAKE_PROFIT: [
                1 if np.random.random() < 0.78 else 0 for _ in range(120)
            ],
        }

        results = calc.calculate_per_signal_type(
            predictions_by_type, outcomes_by_type, strategy_id="grid_btc_1h"
        )

        # Verify all signal types have results
        for signal_type in SignalType:
            assert signal_type in results
            result = results[signal_type]
            assert result.strategy_id == "grid_btc_1h"
            assert result.signal_type == signal_type
            assert result.total_samples > 0
            assert 0 <= result.ece <= 1

    def test_strategy_comparison(self):
        """Test comparing ECE across different strategies."""
        calc = ECECalculator()

        # Strategy 1: Well calibrated
        pred1 = [0.7] * 70 + [0.3] * 30  # 70% at 70% conf, 30% at 30% conf
        out1 = [1] * 49 + [0] * 21 + [1] * 9 + [0] * 21  # Matches confidence
        result1 = calc.calculate(pred1, out1, strategy_id="strategy_1")

        # Strategy 2: Poorly calibrated (overconfident)
        pred2 = [0.9] * 100  # 90% confidence
        out2 = [1] * 50 + [0] * 50  # Only 50% accuracy
        result2 = calc.calculate(pred2, out2, strategy_id="strategy_2")

        # Strategy 1 should have lower ECE
        assert result1.ece < result2.ece
        assert result1.is_well_calibrated is True  # 0.05 < 0.1 default threshold
        assert result2.is_well_calibrated is False  # 0.4 > 0.1 default threshold
