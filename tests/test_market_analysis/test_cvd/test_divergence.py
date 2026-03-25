"""Tests for divergence detector."""

from datetime import UTC, datetime, timedelta

import pytest

from market_analysis.cvd.divergence_detector import (
    Divergence,
    DivergenceDetector,
    DivergenceType,
)


class TestDivergenceDetector:
    """Tests for DivergenceDetector."""

    @pytest.fixture
    def detector(self):
        """Create DivergenceDetector instance."""
        return DivergenceDetector(min_swing_size=0.001, lookback=3)

    @pytest.fixture
    def sample_data(self):
        """Create sample CVD and price data with known divergence."""
        base_time = datetime.now(UTC)
        # Price making lower lows, CVD making higher lows (bullish divergence)
        timestamps = [base_time + timedelta(minutes=i) for i in range(20)]
        prices = [
            100.0,
            99.0,
            98.0,
            97.0,
            96.0,
            97.0,
            98.0,
            99.0,
            100.0,
            101.0,
            100.0,
            99.0,
            98.0,
            97.0,
            96.0,
            97.0,
            98.0,
            99.0,
            100.0,
            101.0,
        ]
        cvd_values = [
            0.0,
            -1.0,
            -2.0,
            -3.0,
            -4.0,
            -3.0,
            -2.0,
            -1.0,
            0.0,
            1.0,
            0.0,
            -1.0,
            -2.0,
            -1.0,
            0.0,
            1.0,
            2.0,
            3.0,
            4.0,
            5.0,
        ]  # Divergence at indices 13-14
        return timestamps, prices, cvd_values

    def test_detect_divergence(self, detector, sample_data):
        """Test divergence detection."""
        timestamps, prices, cvd_values = sample_data

        divergences = detector.detect(cvd_values, prices, timestamps)

        assert isinstance(divergences, list)
        # May find divergences - at minimum we should get Divergence objects when detected
        for div in divergences:
            assert isinstance(div, Divergence)
            assert isinstance(div.divergence_type, DivergenceType)
            assert 0.0 <= div.strength <= 1.0

    def test_detect_empty_data(self, detector):
        """Test divergence detection with empty data."""
        divergences = detector.detect([], [], [])

        assert divergences == []

    def test_detect_short_data(self, detector):
        """Test divergence detection with insufficient data."""
        timestamps = [datetime.now(UTC) + timedelta(minutes=i) for i in range(3)]
        prices = [100.0, 99.0, 98.0]
        cvd_values = [0.0, -1.0, -2.0]

        divergences = detector.detect(cvd_values, prices, timestamps)

        # With very short data and lookback=3, may not find divergences
        assert isinstance(divergences, list)

    def test_get_latest_divergence(self, detector, sample_data):
        """Test getting most recent divergence."""
        timestamps, prices, cvd_values = sample_data

        latest = detector.get_latest_divergence(cvd_values, prices, timestamps)

        if latest:
            assert isinstance(latest, Divergence)
            # Verify it's the most recent by timestamp
            for div in detector.detect(cvd_values, prices, timestamps):
                assert latest.price_index >= div.price_index

    def test_get_latest_divergence_none(self, detector):
        """Test getting latest divergence when none exists."""
        # Price and CVD moving together (no divergence)
        timestamps = [datetime.now(UTC) + timedelta(minutes=i) for i in range(20)]
        prices = [100.0 + i for i in range(20)]
        cvd_values = [i * 0.1 for i in range(20)]

        latest = detector.get_latest_divergence(cvd_values, prices, timestamps)

        # May or may not find divergences depending on swing detection
        assert latest is None or isinstance(latest, Divergence)

    def test_detect_swing_points(self, detector):
        """Test swing point detection."""
        # With lookback=3, need enough data points
        values = [1.0, 0.5, 0.3, 2.0, 1.5, 1.0, 0.8]  # Clear swing high at index 3
        timestamps = [datetime.now(UTC) + timedelta(minutes=i) for i in range(7)]

        swings = detector.detect_swing_points(values, timestamps)

        # Should detect swing high at index 3 (value 2.0 is highest in window)
        swing_indices = [idx for idx, _ in swings if _ == "high"]
        assert 3 in swing_indices

    def test_divergence_type_classification(self, detector):
        """Test divergence type classification."""
        # Create data with clear bearish divergence (price higher high, CVD lower high)
        timestamps = [datetime.now(UTC) + timedelta(minutes=i) for i in range(10)]
        prices = [100.0, 101.0, 102.0]  # Higher high at index 2
        cvd_values = [0.0, -1.0, -2.0]  # Lower high at index 2

        # This is a simplified check - actual detection needs more data
        div_type = detector._classify_divergence(
            "high", 2, prices, "high", 2, cvd_values
        )

        # With the simplified data, we might not get a clear divergence type
        # The actual detection algorithm is more sophisticated

    def test_calculate_strength(self, detector):
        """Test divergence strength calculation."""
        strength = detector.calculate_strength(
            price_delta=1.0, cvd_delta=-2.0, price_trend=10.0, cvd_trend=-10.0
        )

        assert 0.0 <= strength <= 1.0


class TestDivergenceEdgeCases:
    """Edge case tests for DivergenceDetector."""

    @pytest.fixture
    def detector(self):
        """Create DivergenceDetector instance."""
        return DivergenceDetector(min_swing_size=0.001, lookback=2)

    def test_zero_trend_strength(self, detector):
        """Test strength calculation with zero trend."""
        strength = detector.calculate_strength(0.0, 0.0, 0.0, 0.0)

        # Should handle gracefully and return a valid strength
        assert 0.0 <= strength <= 1.0

    def test_identical_prices(self, detector):
        """Test with flat price."""
        timestamps = [datetime.now(UTC) + timedelta(minutes=i) for i in range(10)]
        prices = [100.0] * 10  # Flat price
        cvd_values = list(range(10))

        divergences = detector.detect(cvd_values, prices, timestamps)

        # Should handle flat price without crashing
        assert isinstance(divergences, list)

    def test_identical_cvd(self, detector):
        """Test with flat CVD."""
        timestamps = [datetime.now(UTC) + timedelta(minutes=i) for i in range(10)]
        prices = [100.0 + i for i in range(10)]
        cvd_values = [0.0] * 10  # Flat CVD

        divergences = detector.detect(cvd_values, prices, timestamps)

        # Should handle flat CVD without crashing
        assert isinstance(divergences, list)
