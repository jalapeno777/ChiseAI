"""Tests for RSI indicator safety (repainting guard)."""

import numpy as np
import pytest

from market_analysis.safety import RepaintingDetector, check_indicator


class TestRSISafety:
    """Safety tests for RSI indicator."""

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing."""
        from data_ingestion.ohlcv_fetcher import OHLCVData

        base_ts = 1609459200000
        data = []
        price = 100.0

        for i in range(50):
            # Alternating up/down pattern
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
    def rsi_indicator(self):
        """Create RSI indicator instance."""
        from market_analysis.indicators.rsi import RSI

        return RSI(period=14)

    def test_rsi_no_repainting(self, rsi_indicator, sample_ohlcv_data):
        """Test that RSI indicator does not repaint.

        This test verifies that when RSI is calculated at bar N,
        and then recalculated at bar N+1, the values at bars 0 to N-1
        do not change. This is the core repainting test.
        """
        detector = RepaintingDetector(tolerance=0.0)
        result = detector.check_repainting(rsi_indicator, sample_ohlcv_data)

        assert result.passed is True, f"RSI repainting detected: {result.violations}"

    def test_rsi_lookahead_check(self, rsi_indicator, sample_ohlcv_data):
        """Test RSI calculation passes lookahead check."""
        detector = RepaintingDetector(tolerance=0.0)
        result = detector.check_lookahead(
            sample_ohlcv_data,
            lambda data: rsi_indicator.calculate(data),
            "RSI",
        )

        assert result.passed is True, f"RSI lookahead detected: {result.violations}"

    def test_rsi_historical_values_stable(self, rsi_indicator, sample_ohlcv_data):
        """Test that RSI historical values remain stable over time.

        This test calculates RSI multiple times as new bars are added,
        and verifies that historical values never change.
        """

        n = len(sample_ohlcv_data)

        # Calculate RSI at each bar and store first 14 values
        rsi_values_at_bars = []
        for i in range(15, n):
            data_slice = sample_ohlcv_data[:i]
            result = rsi_indicator.calculate(data_slice)
            # Get RSI values from period onwards (first valid RSI at index 14)
            valid_rsi = result.values[14:]
            rsi_values_at_bars.append(
                valid_rsi[:5].copy() if len(valid_rsi) >= 5 else valid_rsi.copy()
            )

        # Verify that for each bar, the first 5 valid RSI values don't change
        # when we add more data
        for bar_idx in range(len(rsi_values_at_bars) - 1):
            current_values = rsi_values_at_bars[bar_idx]
            next_values = rsi_values_at_bars[bar_idx + 1]

            if len(current_values) >= 5 and len(next_values) >= 5:
                # Only compare up to the length of the shorter array
                min_len = min(len(current_values), len(next_values))
                for i in range(min_len):
                    if not (np.isnan(current_values[i]) and np.isnan(next_values[i])):
                        diff = abs(current_values[i] - next_values[i])
                        assert diff < 1e-10, (
                            f"RSI value at bar {bar_idx} changed when data added: "
                            f"{current_values[i]} -> {next_values[i]}"
                        )

    def test_rsi_check_indicator_convenience(self, rsi_indicator, sample_ohlcv_data):
        """Test the check_indicator convenience function for RSI."""
        result = check_indicator(rsi_indicator, sample_ohlcv_data)

        assert result.passed is True
        assert result.violation_count == 0
        assert "RSI" in result.guard_name
