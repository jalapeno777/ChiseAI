"""Tests for MACD indicator safety (repainting guard)."""

import numpy as np
import pytest

from market_analysis.safety import RepaintingDetector, check_indicator


class TestMACDSafety:
    """Safety tests for MACD indicator."""

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing.

        MACD requires at least 35 bars (26 slow + 9 signal), so we use 50.
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
    def macd_indicator(self):
        """Create MACD indicator instance."""
        from market_analysis.indicators.macd import MACD

        return MACD()

    def test_macd_no_repainting(self, macd_indicator, sample_ohlcv_data):
        """Test that MACD indicator does not repaint.

        MACD should not change historical values when new data is added.
        """
        detector = RepaintingDetector(tolerance=0.0)
        result = detector.check_repainting(macd_indicator, sample_ohlcv_data)

        assert result.passed is True, f"MACD repainting detected: {result.violations}"

    def test_macd_lookahead_check(self, macd_indicator, sample_ohlcv_data):
        """Test MACD calculation passes lookahead check."""
        detector = RepaintingDetector(tolerance=0.0)
        result = detector.check_lookahead(
            sample_ohlcv_data,
            lambda data: macd_indicator.calculate(data),
            "MACD",
        )

        assert result.passed is True, f"MACD lookahead detected: {result.violations}"

    def test_macd_histogram_values_stable(self, macd_indicator, sample_ohlcv_data):
        """Test that MACD histogram values remain stable over time.

        The histogram values at historical bars should not change when
        new data is added.
        """
        n = len(sample_ohlcv_data)

        # Store histogram values at each calculation
        histogram_at_bars = []
        for i in range(35, n):  # Need 26+9 bars for MACD
            data_slice = sample_ohlcv_data[:i]
            result = macd_indicator.calculate(data_slice)
            # Get valid histogram values
            valid_hist = result.histogram[~np.isnan(result.histogram)]
            histogram_at_bars.append(
                valid_hist[:5].copy() if len(valid_hist) >= 5 else valid_hist.copy()
            )

        # Compare stability
        for bar_idx in range(len(histogram_at_bars) - 1):
            current = histogram_at_bars[bar_idx]
            next_hist = histogram_at_bars[bar_idx + 1]

            if len(current) >= 5 and len(next_hist) >= 5:
                min_len = min(len(current), len(next_hist))
                for i in range(min_len):
                    diff = abs(current[i] - next_hist[i])
                    assert diff < 1e-10, (
                        f"MACD histogram at bar {bar_idx} changed: "
                        f"{current[i]} -> {next_hist[i]}"
                    )

    def test_macd_check_indicator_convenience(self, macd_indicator, sample_ohlcv_data):
        """Test the check_indicator convenience function for MACD."""
        result = check_indicator(macd_indicator, sample_ohlcv_data)

        assert result.passed is True
        assert result.violation_count == 0
        assert "MACD" in result.guard_name
