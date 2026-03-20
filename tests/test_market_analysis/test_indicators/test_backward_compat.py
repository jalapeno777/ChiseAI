"""Tests for backward compatibility with existing indicators."""

import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators import MACD, RSI, BollingerBands


class TestBackwardCompatibility:
    """Test that existing indicators still work after plugin refactor."""

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data."""
        return [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i * 0.1,
                high_price=101.0 + i * 0.1,
                low_price=99.0 + i * 0.1,
                close_price=100.5 + i * 0.1,
                volume=1000.0 + i * 100,
            )
            for i in range(50)
        ]

    def test_rsi_still_works(self, sample_data):
        """Test RSI indicator still functions."""
        rsi = RSI(period=14)
        result = rsi.calculate(sample_data)
        assert result.current is not None
        assert 0 <= result.current <= 100

    def test_macd_still_works(self, sample_data):
        """Test MACD indicator still functions."""
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        result = macd.calculate(sample_data)
        assert result.current_macd is not None

    def test_bollinger_still_works(self, sample_data):
        """Test Bollinger Bands still functions."""
        bb = BollingerBands(period=20, num_std_dev=2.0)
        result = bb.calculate(sample_data)
        assert result.current_middle is not None
