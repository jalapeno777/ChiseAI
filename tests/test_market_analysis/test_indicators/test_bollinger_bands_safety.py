"""Tests for Bollinger Bands indicator safety (repainting guard)."""

import numpy as np
import pytest

from market_analysis.safety import RepaintingDetector, check_indicator


class TestBollingerBandsSafety:
    """Safety tests for Bollinger Bands indicator."""

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing.

        Bollinger Bands requires at least 20 bars (period), so we use 50.
        """
        from data_ingestion.ohlcv_fetcher import OHLCVData

        base_ts = 1609459200000
        data = []
        price = 100.0

        for i in range(50):
            price += 2.0 if i % 2 == 0 else -1.0
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 1.0,
                    high_price=price + 1.0,
                    low_price=price - 2.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        return data

    @pytest.fixture
    def bb_indicator(self):
        """Create Bollinger Bands indicator instance."""
        from market_analysis.indicators.bollinger_bands import BollingerBands

        return BollingerBands()

    def test_bollinger_bands_no_repainting(self, bb_indicator, sample_ohlcv_data):
        """Test that Bollinger Bands indicator does not repaint.

        Bollinger Bands values at historical bars should not change
        when new data is added.
        """
        detector = RepaintingDetector(tolerance=0.0)
        result = detector.check_repainting(bb_indicator, sample_ohlcv_data)

        assert (
            result.passed is True
        ), f"Bollinger Bands repainting detected: {result.violations}"

    def test_bollinger_bands_lookahead_check(self, bb_indicator, sample_ohlcv_data):
        """Test Bollinger Bands calculation passes lookahead check."""
        detector = RepaintingDetector(tolerance=0.0)
        result = detector.check_lookahead(
            sample_ohlcv_data,
            lambda data: bb_indicator.calculate(data),
            "BollingerBands",
        )

        assert (
            result.passed is True
        ), f"Bollinger Bands lookahead detected: {result.violations}"

    def test_bollinger_bands_percent_b_stable(self, bb_indicator, sample_ohlcv_data):
        """Test that %B values remain stable over time.

        The %B metric should not change for historical bars when
        new data is added.
        """
        n = len(sample_ohlcv_data)

        percent_b_at_bars = []
        for i in range(25, n):  # Need 20+ bars for BB
            data_slice = sample_ohlcv_data[:i]
            result = bb_indicator.calculate(data_slice)
            # Get valid percent_b values
            valid_pb = result.percent_b[~np.isnan(result.percent_b)]
            percent_b_at_bars.append(
                valid_pb[:5].copy() if len(valid_pb) >= 5 else valid_pb.copy()
            )

        # Compare stability
        for bar_idx in range(len(percent_b_at_bars) - 1):
            current = percent_b_at_bars[bar_idx]
            next_pb = percent_b_at_bars[bar_idx + 1]

            if len(current) >= 5 and len(next_pb) >= 5:
                min_len = min(len(current), len(next_pb))
                for i in range(min_len):
                    diff = abs(current[i] - next_pb[i])
                    assert diff < 1e-10, (
                        f"Bollinger Bands %B at bar {bar_idx} changed: "
                        f"{current[i]} -> {next_pb[i]}"
                    )

    def test_bollinger_bands_check_indicator_convenience(
        self, bb_indicator, sample_ohlcv_data
    ):
        """Test the check_indicator convenience function for Bollinger Bands."""
        result = check_indicator(bb_indicator, sample_ohlcv_data)

        assert result.passed is True
        assert result.violation_count == 0
        assert "BollingerBands" in result.guard_name
