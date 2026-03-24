"""Tests for MFI, StochRSI, and Williams %R extended momentum indicators."""

from datetime import datetime

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.base import Signal, SignalDirection
from market_analysis.indicators.momentum_extended import (
    MFI,
    MFIResult,
    StochRSI,
    StochRSIResult,
    WilliamsR,
    WilliamsRResult,
    _calculate_rma,
    _calculate_sma,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data with upward trend and volume."""
    data = []
    for i in range(50):
        data.append(
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i * 0.5,
                high_price=101.0 + i * 0.5,
                low_price=99.0 + i * 0.5,
                close_price=100.5 + i * 0.5,
                volume=1000.0 + i * 100,
            )
        )
    return data


@pytest.fixture
def oscillating_data():
    """Create OHLCV data that oscillates to trigger overbought/oversold."""
    data = []
    price = 100.0
    for i in range(100):
        # Oscillate price to create MFI extremes
        if i % 20 < 10:
            price += 1.0  # Rising
            vol = 2000.0  # High volume on up days
        else:
            price -= 1.0  # Falling
            vol = 500.0  # Low volume on down days
        data.append(
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=price - 0.5,
                high_price=price + 1.0,
                low_price=price - 1.0,
                close_price=price,
                volume=vol,
            )
        )
    return data


@pytest.fixture
def flat_data():
    """Create OHLCV data with flat prices (zero range)."""
    return [
        OHLCVData(
            timestamp=1000 + i * 60000,
            open_price=100.0,
            high_price=100.0,
            low_price=100.0,
            close_price=100.0,
            volume=1000.0,
        )
        for i in range(50)
    ]


@pytest.fixture
def short_data():
    """Create minimal OHLCV data (insufficient for most indicators)."""
    return [
        OHLCVData(
            timestamp=1000 + i * 60000,
            open_price=100.0,
            high_price=101.0,
            low_price=99.0,
            close_price=100.5,
            volume=1000.0,
        )
        for i in range(5)
    ]


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestCalculateRMA:
    """Tests for the _calculate_rma helper."""

    def test_basic_rma(self):
        """Test RMA produces correct initial value."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _calculate_rma(values, 3)
        assert result[2] == pytest.approx(2.0)  # mean of first 3

    def test_rma_smoothing(self):
        """Test RMA smoothing is exponential."""
        values = np.array([10.0] * 10)
        result = _calculate_rma(values, 5)
        # All values should be 10.0
        assert np.allclose(result[4:], 10.0)

    def test_rma_short_input(self):
        """Test RMA with insufficient data returns all NaN."""
        values = np.array([1.0, 2.0])
        result = _calculate_rma(values, 5)
        assert np.all(np.isnan(result))

    def test_rma_nan_positions(self):
        """Test RMA has NaN before period is complete."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _calculate_rma(values, 3)
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert not np.isnan(result[2])


class TestCalculateSMA:
    """Tests for the _calculate_sma helper."""

    def test_basic_sma(self):
        """Test SMA calculates correct average."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _calculate_sma(values, 3)
        assert result[2] == pytest.approx(2.0)
        assert result[3] == pytest.approx(3.0)
        assert result[4] == pytest.approx(4.0)

    def test_sma_with_nan(self):
        """Test SMA skips NaN values."""
        values = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
        result = _calculate_sma(values, 3)
        # Window [1, nan, 3] -> mean of valid [1, 3] = 2.0
        assert result[2] == pytest.approx(2.0)

    def test_sma_nan_positions(self):
        """Test SMA has NaN before period is complete."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _calculate_sma(values, 3)
        assert np.isnan(result[0])
        assert np.isnan(result[1])

    def test_sma_empty_window(self):
        """Test SMA with all-NaN window stays NaN."""
        values = np.array([np.nan, np.nan, np.nan, np.nan, np.nan])
        result = _calculate_sma(values, 3)
        assert np.all(np.isnan(result))


# ---------------------------------------------------------------------------
# MFI Tests
# ---------------------------------------------------------------------------


class TestMFI:
    """Tests for Money Flow Index indicator."""

    def test_creation_defaults(self):
        """Test MFI creation with default parameters."""
        mfi = MFI()
        assert mfi.name == "MFI"
        assert mfi.period == 14
        assert mfi.overbought_threshold == 80.0
        assert mfi.oversold_threshold == 20.0

    def test_creation_custom(self):
        """Test MFI creation with custom parameters."""
        mfi = MFI(
            period=10,
            overbought_threshold=90.0,
            oversold_threshold=10.0,
            name="CustomMFI",
        )
        assert mfi.name == "CustomMFI"
        assert mfi.period == 10
        assert mfi.overbought_threshold == 90.0
        assert mfi.oversold_threshold == 10.0

    def test_description(self):
        """Test description property."""
        mfi = MFI(period=14)
        assert mfi.description == "Money Flow Index (14)"

    def test_parameters(self):
        """Test parameters property."""
        mfi = MFI(period=10, overbought_threshold=85.0, oversold_threshold=15.0)
        params = mfi.parameters
        assert params["period"] == 10
        assert params["overbought_threshold"] == 85.0
        assert params["oversold_threshold"] == 15.0

    def test_validate_sufficient(self, sample_ohlcv_data):
        """Test validate returns True for sufficient data."""
        mfi = MFI(period=14)
        assert mfi.validate(sample_ohlcv_data) is True

    def test_validate_insufficient(self, short_data):
        """Test validate returns False for insufficient data."""
        mfi = MFI(period=14)
        assert mfi.validate(short_data) is False

    def test_validate_exact_minimum(self):
        """Test validate with exactly period+1 data points."""
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i,
                high_price=101.0 + i,
                low_price=99.0 + i,
                close_price=100.5 + i,
                volume=1000.0,
            )
            for i in range(15)  # period=14 needs 15 points
        ]
        mfi = MFI(period=14)
        assert mfi.validate(data) is True

    def test_validate_insufficient_by_one(self):
        """Test validate with one fewer than minimum."""
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i,
                high_price=101.0 + i,
                low_price=99.0 + i,
                close_price=100.5 + i,
                volume=1000.0,
            )
            for i in range(14)  # period=14 needs 15
        ]
        mfi = MFI(period=14)
        assert mfi.validate(data) is False

    def test_compute_basic(self, sample_ohlcv_data):
        """Test basic MFI computation."""
        mfi = MFI(period=14)
        result = mfi.compute(sample_ohlcv_data)
        assert isinstance(result, MFIResult)
        assert len(result.values) == len(sample_ohlcv_data)
        assert result.current is not None

    def test_compute_range(self, sample_ohlcv_data):
        """Test MFI values are in 0-100 range."""
        mfi = MFI(period=14)
        result = mfi.compute(sample_ohlcv_data)
        valid_values = result.values[~np.isnan(result.values)]
        assert np.all(valid_values >= 0.0)
        assert np.all(valid_values <= 100.0)

    def test_compute_insufficient_raises(self, short_data):
        """Test compute raises ValueError for insufficient data."""
        mfi = MFI(period=14)
        with pytest.raises(ValueError, match="Need 15 data points"):
            mfi.compute(short_data)

    def test_compute_nan_leading(self, sample_ohlcv_data):
        """Test leading values are NaN before sufficient data."""
        mfi = MFI(period=14)
        result = mfi.compute(sample_ohlcv_data)
        # First 14 values should be NaN
        assert np.all(np.isnan(result.values[:14]))

    def test_compute_all_positive_flow(self):
        """Test MFI with only positive money flow."""
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i,
                high_price=102.0 + i,
                low_price=99.0 + i,
                close_price=101.0 + i,
                volume=1000.0,
            )
            for i in range(30)
        ]
        mfi = MFI(period=14)
        result = mfi.compute(data)
        valid = result.values[~np.isnan(result.values)]
        assert np.all(valid == 100.0)

    def test_overbought_detection(self, oscillating_data):
        """Test overbought detection when MFI > threshold."""
        mfi = MFI(period=14)
        result = mfi.compute(oscillating_data)
        # With oscillating data, some values should be flagged
        assert isinstance(result.overbought, np.ndarray)
        assert len(result.overbought) == len(oscillating_data)

    def test_oversold_detection(self, oscillating_data):
        """Test oversold detection when MFI < threshold."""
        mfi = MFI(period=14)
        result = mfi.compute(oscillating_data)
        assert isinstance(result.oversold, np.ndarray)
        assert len(result.oversold) == len(oscillating_data)

    def test_get_metadata(self):
        """Test metadata retrieval."""
        mfi = MFI(period=10, name="TestMFI")
        meta = mfi.get_metadata()
        assert meta["name"] == "TestMFI"
        assert "description" in meta
        assert "parameters" in meta
        assert meta["parameters"]["period"] == 10

    def test_to_signal_hold(self, sample_ohlcv_data):
        """Test signal generation for neutral MFI."""
        mfi = MFI(period=14)
        result = mfi.compute(sample_ohlcv_data)
        signal = mfi.to_signal(result)
        assert isinstance(signal, Signal)
        assert 0.0 <= signal.confidence <= 1.0

    def test_to_signal_overbought(self):
        """Test signal generates SELL when overbought."""
        mfi = MFI(period=5, overbought_threshold=80.0)
        # Create data that will produce high MFI
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i * 2,
                high_price=101.0 + i * 2,
                low_price=99.0 + i * 2,
                close_price=100.5 + i * 2,
                volume=5000.0,  # High volume
            )
            for i in range(30)
        ]
        result = mfi.compute(data)
        signal = mfi.to_signal(result)
        if result.current is not None and result.current > 80.0:
            assert signal.direction == SignalDirection.SELL
            assert signal.metadata["mfi"] == pytest.approx(result.current)

    def test_to_signal_oversold(self):
        """Test signal generates BUY when oversold."""
        mfi = MFI(period=5, oversold_threshold=20.0)
        # Create data that will produce low MFI
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 - i * 2,
                high_price=101.0 - i * 2,
                low_price=99.0 - i * 2,
                close_price=100.5 - i * 2,
                volume=5000.0,
            )
            for i in range(30)
        ]
        result = mfi.compute(data)
        signal = mfi.to_signal(result)
        if result.current is not None and result.current < 20.0:
            assert signal.direction == SignalDirection.BUY
            assert signal.metadata["mfi"] == pytest.approx(result.current)

    def test_to_signal_none_current(self):
        """Test signal when result has no valid values."""
        mfi = MFI(period=14)
        result = MFIResult(
            values=np.array([np.nan, np.nan]),
            overbought=np.array([False, False]),
            oversold=np.array([False, False]),
        )
        signal = mfi.to_signal(result)
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.5


class TestMFIResult:
    """Tests for MFIResult dataclass."""

    def test_current_with_valid_values(self):
        """Test current property returns last valid value."""
        result = MFIResult(
            values=np.array([np.nan, np.nan, 50.0, 75.0]),
            overbought=np.array([False, False, False, False]),
            oversold=np.array([False, False, False, False]),
        )
        assert result.current == 75.0

    def test_current_with_all_nan(self):
        """Test current property returns None for all NaN."""
        result = MFIResult(
            values=np.array([np.nan, np.nan]),
            overbought=np.array([False, False]),
            oversold=np.array([False, False]),
        )
        assert result.current is None

    def test_current_empty(self):
        """Test current property with empty array."""
        result = MFIResult(
            values=np.array([]),
            overbought=np.array([]),
            oversold=np.array([]),
        )
        assert result.current is None


# ---------------------------------------------------------------------------
# StochRSI Tests
# ---------------------------------------------------------------------------


class TestStochRSI:
    """Tests for Stochastic RSI indicator."""

    def test_creation_defaults(self):
        """Test StochRSI creation with default parameters."""
        stoch = StochRSI()
        assert stoch.name == "StochRSI"
        assert stoch.rsi_period == 14
        assert stoch.stoch_period == 14
        assert stoch.k_period == 3
        assert stoch.d_period == 3
        assert stoch.overbought_threshold == 80.0
        assert stoch.oversold_threshold == 20.0

    def test_creation_custom(self):
        """Test StochRSI creation with custom parameters."""
        stoch = StochRSI(
            rsi_period=10,
            stoch_period=10,
            k_period=5,
            d_period=5,
            overbought_threshold=85.0,
            oversold_threshold=15.0,
            name="CustomStochRSI",
        )
        assert stoch.name == "CustomStochRSI"
        assert stoch.rsi_period == 10
        assert stoch.stoch_period == 10
        assert stoch.k_period == 5
        assert stoch.d_period == 5

    def test_description(self):
        """Test description property."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        assert "14,14,3,3" in stoch.description

    def test_parameters(self):
        """Test parameters property."""
        stoch = StochRSI(rsi_period=7, stoch_period=7, k_period=2, d_period=2)
        params = stoch.parameters
        assert params["rsi_period"] == 7
        assert params["stoch_period"] == 7
        assert params["k_period"] == 2
        assert params["d_period"] == 2

    def test_validate_sufficient(self, sample_ohlcv_data):
        """Test validate returns True for sufficient data."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3)
        # Need rsi_period + stoch_period + k_period = 31
        assert stoch.validate(sample_ohlcv_data) is True

    def test_validate_insufficient(self, short_data):
        """Test validate returns False for insufficient data."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3)
        assert stoch.validate(short_data) is False

    def test_compute_basic(self, oscillating_data):
        """Test basic StochRSI computation."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        result = stoch.compute(oscillating_data)
        assert isinstance(result, StochRSIResult)
        assert len(result.k) == len(oscillating_data)
        assert len(result.d) == len(oscillating_data)

    def test_compute_range(self, oscillating_data):
        """Test StochRSI %K values are in 0-100 range."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        result = stoch.compute(oscillating_data)
        valid_k = result.k[~np.isnan(result.k)]
        assert np.all(valid_k >= 0.0)
        assert np.all(valid_k <= 100.0)

    def test_compute_insufficient_raises(self, short_data):
        """Test compute raises ValueError for insufficient data."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3)
        with pytest.raises(ValueError, match="Need 31 data points"):
            stoch.compute(short_data)

    def test_compute_nan_leading(self, sample_ohlcv_data):
        """Test leading values are NaN before sufficient data."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        result = stoch.compute(sample_ohlcv_data)
        # Early values should be NaN
        assert np.all(np.isnan(result.k[:28]))

    def test_overbought_detection(self, oscillating_data):
        """Test overbought detection."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        result = stoch.compute(oscillating_data)
        assert isinstance(result.overbought, np.ndarray)
        assert len(result.overbought) == len(oscillating_data)

    def test_oversold_detection(self, oscillating_data):
        """Test oversold detection."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        result = stoch.compute(oscillating_data)
        assert isinstance(result.oversold, np.ndarray)
        assert len(result.oversold) == len(oscillating_data)

    def test_get_metadata(self):
        """Test metadata retrieval."""
        stoch = StochRSI(rsi_period=10, name="TestStochRSI")
        meta = stoch.get_metadata()
        assert meta["name"] == "TestStochRSI"
        assert "description" in meta
        assert "parameters" in meta

    def test_to_signal_hold(self, sample_ohlcv_data):
        """Test signal generation for neutral StochRSI."""
        stoch = StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        result = stoch.compute(sample_ohlcv_data)
        signal = stoch.to_signal(result)
        assert isinstance(signal, Signal)
        assert 0.0 <= signal.confidence <= 1.0

    def test_to_signal_overbought(self):
        """Test signal generates SELL when overbought."""
        stoch = StochRSI(
            rsi_period=5,
            stoch_period=5,
            k_period=3,
            d_period=3,
            overbought_threshold=80.0,
        )
        # Strong uptrend data
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i * 2,
                high_price=101.0 + i * 2,
                low_price=99.0 + i * 2,
                close_price=100.5 + i * 2,
                volume=1000.0,
            )
            for i in range(50)
        ]
        result = stoch.compute(data)
        signal = stoch.to_signal(result)
        assert isinstance(signal, Signal)
        if result.current_k is not None and result.current_k > 80.0:
            assert signal.direction == SignalDirection.SELL

    def test_to_signal_none_current(self):
        """Test signal when result has no valid %K values."""
        stoch = StochRSI()
        result = StochRSIResult(
            k=np.array([np.nan, np.nan]),
            d=np.array([np.nan, np.nan]),
            overbought=np.array([False, False]),
            oversold=np.array([False, False]),
        )
        signal = stoch.to_signal(result)
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.5

    def test_to_signal_hold_middle(self):
        """Test signal generates HOLD when %K is between thresholds."""
        stoch = StochRSI(
            rsi_period=5,
            stoch_period=5,
            k_period=3,
            d_period=3,
            overbought_threshold=80.0,
            oversold_threshold=20.0,
        )
        # Force a HOLD by constructing result with %K at 50.0
        result = StochRSIResult(
            k=np.array([30.0, 40.0, 50.0]),
            d=np.array([30.0, 40.0, 50.0]),
            overbought=np.array([False, False, False]),
            oversold=np.array([False, False, False]),
        )
        signal = stoch.to_signal(result)
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.5
        assert signal.metadata["stoch_rsi_k"] == 50.0

    def test_to_signal_oversold(self):
        """Test signal generates BUY when %K is oversold."""
        stoch = StochRSI(
            rsi_period=5,
            stoch_period=5,
            k_period=3,
            d_period=3,
            oversold_threshold=20.0,
        )
        result = StochRSIResult(
            k=np.array([30.0, 10.0, 5.0]),
            d=np.array([30.0, 10.0, 5.0]),
            overbought=np.array([False, False, False]),
            oversold=np.array([False, True, True]),
        )
        signal = stoch.to_signal(result)
        assert signal.direction == SignalDirection.BUY
        assert signal.metadata["stoch_rsi_k"] == 5.0

    def test_to_signal_overbought_direct(self):
        """Test signal generates SELL when %K is overbought (direct result)."""
        stoch = StochRSI(
            rsi_period=5,
            stoch_period=5,
            k_period=3,
            d_period=3,
            overbought_threshold=80.0,
        )
        result = StochRSIResult(
            k=np.array([70.0, 85.0, 95.0]),
            d=np.array([70.0, 85.0, 95.0]),
            overbought=np.array([False, True, True]),
            oversold=np.array([False, False, False]),
        )
        signal = stoch.to_signal(result)
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence > 0.5
        assert signal.metadata["stoch_rsi_k"] == 95.0

    def test_short_period_compute(self, oscillating_data):
        """Test StochRSI with short periods for faster calculation."""
        stoch = StochRSI(rsi_period=5, stoch_period=5, k_period=2, d_period=2)
        result = stoch.compute(oscillating_data)
        assert result.current_k is not None
        assert result.current_d is not None


class TestStochRSIResult:
    """Tests for StochRSIResult dataclass."""

    def test_current_k_with_valid(self):
        """Test current_k returns last valid %K."""
        result = StochRSIResult(
            k=np.array([np.nan, 50.0, 80.0]),
            d=np.array([np.nan, 50.0, 70.0]),
            overbought=np.array([False, False, True]),
            oversold=np.array([False, False, False]),
        )
        assert result.current_k == 80.0

    def test_current_k_all_nan(self):
        """Test current_k returns None for all NaN."""
        result = StochRSIResult(
            k=np.array([np.nan, np.nan]),
            d=np.array([np.nan, np.nan]),
            overbought=np.array([False, False]),
            oversold=np.array([False, False]),
        )
        assert result.current_k is None

    def test_current_d_with_valid(self):
        """Test current_d returns last valid %D."""
        result = StochRSIResult(
            k=np.array([np.nan, 50.0, 80.0]),
            d=np.array([np.nan, 50.0, 70.0]),
            overbought=np.array([False, False, True]),
            oversold=np.array([False, False, False]),
        )
        assert result.current_d == 70.0

    def test_current_d_all_nan(self):
        """Test current_d returns None for all NaN."""
        result = StochRSIResult(
            k=np.array([np.nan, np.nan]),
            d=np.array([np.nan, np.nan]),
            overbought=np.array([False, False]),
            oversold=np.array([False, False]),
        )
        assert result.current_d is None


# ---------------------------------------------------------------------------
# Williams %R Tests
# ---------------------------------------------------------------------------


class TestWilliamsR:
    """Tests for Williams %R indicator."""

    def test_creation_defaults(self):
        """Test WilliamsR creation with default parameters."""
        wr = WilliamsR()
        assert wr.name == "WilliamsR"
        assert wr.period == 14
        assert wr.overbought_threshold == -20.0
        assert wr.oversold_threshold == -80.0

    def test_creation_custom(self):
        """Test WilliamsR creation with custom parameters."""
        wr = WilliamsR(
            period=10,
            overbought_threshold=-10.0,
            oversold_threshold=-90.0,
            name="CustomWR",
        )
        assert wr.name == "CustomWR"
        assert wr.period == 10
        assert wr.overbought_threshold == -10.0
        assert wr.oversold_threshold == -90.0

    def test_description(self):
        """Test description property."""
        wr = WilliamsR(period=14)
        assert wr.description == "Williams %R (14)"

    def test_parameters(self):
        """Test parameters property."""
        wr = WilliamsR(period=20, overbought_threshold=-15.0, oversold_threshold=-85.0)
        params = wr.parameters
        assert params["period"] == 20
        assert params["overbought_threshold"] == -15.0
        assert params["oversold_threshold"] == -85.0

    def test_validate_sufficient(self, sample_ohlcv_data):
        """Test validate returns True for sufficient data."""
        wr = WilliamsR(period=14)
        assert wr.validate(sample_ohlcv_data) is True

    def test_validate_insufficient(self, short_data):
        """Test validate returns False for insufficient data."""
        wr = WilliamsR(period=14)
        assert wr.validate(short_data) is False

    def test_validate_exact_minimum(self):
        """Test validate with exactly period data points."""
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0 + i,
                high_price=101.0 + i,
                low_price=99.0 + i,
                close_price=100.5 + i,
                volume=1000.0,
            )
            for i in range(14)  # period=14 needs 14 points
        ]
        wr = WilliamsR(period=14)
        assert wr.validate(data) is True

    def test_compute_basic(self, sample_ohlcv_data):
        """Test basic Williams %R computation."""
        wr = WilliamsR(period=14)
        result = wr.compute(sample_ohlcv_data)
        assert isinstance(result, WilliamsRResult)
        assert len(result.values) == len(sample_ohlcv_data)
        assert result.current is not None

    def test_compute_range(self, sample_ohlcv_data):
        """Test Williams %R values are in -100 to 0 range."""
        wr = WilliamsR(period=14)
        result = wr.compute(sample_ohlcv_data)
        valid_values = result.values[~np.isnan(result.values)]
        assert np.all(valid_values >= -100.0)
        assert np.all(valid_values <= 0.0)

    def test_compute_insufficient_raises(self, short_data):
        """Test compute raises ValueError for insufficient data."""
        wr = WilliamsR(period=14)
        with pytest.raises(ValueError, match="Need 14 data points"):
            wr.compute(short_data)

    def test_compute_nan_leading(self, sample_ohlcv_data):
        """Test leading values are NaN before sufficient data."""
        wr = WilliamsR(period=14)
        result = wr.compute(sample_ohlcv_data)
        assert np.all(np.isnan(result.values[:13]))

    def test_compute_flat_data(self, flat_data):
        """Test Williams %R with flat prices (zero range)."""
        wr = WilliamsR(period=14)
        result = wr.compute(flat_data)
        # All values should be NaN since highest_high == lowest_low
        assert np.all(np.isnan(result.values))

    def test_overbought_detection(self, sample_ohlcv_data):
        """Test overbought detection."""
        wr = WilliamsR(period=14)
        result = wr.compute(sample_ohlcv_data)
        assert isinstance(result.overbought, np.ndarray)
        assert len(result.overbought) == len(sample_ohlcv_data)

    def test_oversold_detection(self, sample_ohlcv_data):
        """Test oversold detection."""
        wr = WilliamsR(period=14)
        result = wr.compute(sample_ohlcv_data)
        assert isinstance(result.oversold, np.ndarray)
        assert len(result.oversold) == len(sample_ohlcv_data)

    def test_compute_close_at_high(self):
        """Test Williams %R when close equals highest high."""
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0,
                high_price=110.0 + i,
                low_price=90.0,
                close_price=110.0 + i,  # Close at high
                volume=1000.0,
            )
            for i in range(20)
        ]
        wr = WilliamsR(period=10)
        result = wr.compute(data)
        valid = result.values[~np.isnan(result.values)]
        # Close at high means Williams %R = 0
        assert np.allclose(valid, 0.0, atol=1e-10)

    def test_compute_close_at_low(self):
        """Test Williams %R when close equals lowest low of the window."""
        # Build data where each bar's close is at the window's lowest low
        data = []
        for i in range(20):
            # Set lowest low to be the current close, and highest high higher
            data.append(
                OHLCVData(
                    timestamp=1000 + i * 60000,
                    open_price=100.0,
                    high_price=200.0,  # Same high across all bars
                    low_price=50.0,  # Same low across all bars
                    close_price=50.0,  # Close at the lowest low
                    volume=1000.0,
                )
            )
        wr = WilliamsR(period=10)
        result = wr.compute(data)
        valid = result.values[~np.isnan(result.values)]
        # Close at the lowest low of the window → Williams %R = -100
        assert np.allclose(valid, -100.0, atol=1e-10)

    def test_get_metadata(self):
        """Test metadata retrieval."""
        wr = WilliamsR(period=10, name="TestWR")
        meta = wr.get_metadata()
        assert meta["name"] == "TestWR"
        assert "description" in meta
        assert "parameters" in meta
        assert meta["parameters"]["period"] == 10

    def test_to_signal_hold(self, sample_ohlcv_data):
        """Test signal generation for neutral Williams %R."""
        wr = WilliamsR(period=14)
        result = wr.compute(sample_ohlcv_data)
        signal = wr.to_signal(result)
        assert isinstance(signal, Signal)
        assert 0.0 <= signal.confidence <= 1.0

    def test_to_signal_overbought(self):
        """Test signal generates SELL when overbought (close to 0)."""
        wr = WilliamsR(period=5, overbought_threshold=-20.0)
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0,
                high_price=100.0 + i * 2,
                low_price=95.0,
                close_price=100.0 + i * 2,  # Close near high
                volume=1000.0,
            )
            for i in range(20)
        ]
        result = wr.compute(data)
        signal = wr.to_signal(result)
        assert isinstance(signal, Signal)
        if result.current is not None and result.current > -20.0:
            assert signal.direction == SignalDirection.SELL
            assert signal.metadata["williams_r"] == pytest.approx(result.current)

    def test_to_signal_oversold(self):
        """Test signal generates BUY when oversold (close to -100)."""
        wr = WilliamsR(period=5, oversold_threshold=-80.0)
        data = [
            OHLCVData(
                timestamp=1000 + i * 60000,
                open_price=100.0,
                high_price=105.0,
                low_price=100.0 - i * 2,
                close_price=100.0 - i * 2,  # Close near low
                volume=1000.0,
            )
            for i in range(20)
        ]
        result = wr.compute(data)
        signal = wr.to_signal(result)
        assert isinstance(signal, Signal)
        if result.current is not None and result.current < -80.0:
            assert signal.direction == SignalDirection.BUY
            assert signal.metadata["williams_r"] == pytest.approx(result.current)

    def test_to_signal_none_current(self):
        """Test signal when result has no valid values."""
        wr = WilliamsR(period=14)
        result = WilliamsRResult(
            values=np.array([np.nan, np.nan]),
            overbought=np.array([False, False]),
            oversold=np.array([False, False]),
        )
        signal = wr.to_signal(result)
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.5

    def test_to_signal_hold_middle(self):
        """Test signal generates HOLD when Williams %R is between thresholds."""
        wr = WilliamsR(period=14, overbought_threshold=-20.0, oversold_threshold=-80.0)
        result = WilliamsRResult(
            values=np.array([-30.0, -40.0, -50.0]),
            overbought=np.array([False, False, False]),
            oversold=np.array([False, False, False]),
        )
        signal = wr.to_signal(result)
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.5
        assert signal.metadata["williams_r"] == -50.0


class TestWilliamsRResult:
    """Tests for WilliamsRResult dataclass."""

    def test_current_with_valid_values(self):
        """Test current property returns last valid value."""
        result = WilliamsRResult(
            values=np.array([np.nan, np.nan, -50.0, -30.0]),
            overbought=np.array([False, False, False, True]),
            oversold=np.array([False, False, False, False]),
        )
        assert result.current == -30.0

    def test_current_with_all_nan(self):
        """Test current property returns None for all NaN."""
        result = WilliamsRResult(
            values=np.array([np.nan, np.nan]),
            overbought=np.array([False, False]),
            oversold=np.array([False, False]),
        )
        assert result.current is None

    def test_current_empty(self):
        """Test current property with empty array."""
        result = WilliamsRResult(
            values=np.array([]),
            overbought=np.array([]),
            oversold=np.array([]),
        )
        assert result.current is None


# ---------------------------------------------------------------------------
# Integration: BaseIndicator interface compliance
# ---------------------------------------------------------------------------


class TestBaseIndicatorCompliance:
    """Verify all three indicators comply with BaseIndicator interface."""

    @pytest.fixture(params=["mfi", "stoch_rsi", "williams_r"])
    def indicator_and_data(self, request, oscillating_data):
        """Parametrized fixture for all three indicators."""
        if request.param == "mfi":
            return MFI(period=14), oscillating_data
        elif request.param == "stoch_rsi":
            return (
                StochRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3),
                oscillating_data,
            )
        else:
            return WilliamsR(period=14), oscillating_data

    def test_is_base_indicator(self, indicator_and_data):
        """Test all indicators inherit from BaseIndicator."""
        indicator, _ = indicator_and_data
        from market_analysis.indicators.base import BaseIndicator

        assert isinstance(indicator, BaseIndicator)

    def test_name_property(self, indicator_and_data):
        """Test name property exists and is string."""
        indicator, _ = indicator_and_data
        assert isinstance(indicator.name, str)
        assert len(indicator.name) > 0

    def test_description_property(self, indicator_and_data):
        """Test description property exists and is string."""
        indicator, _ = indicator_and_data
        assert isinstance(indicator.description, str)
        assert len(indicator.description) > 0

    def test_parameters_property(self, indicator_and_data):
        """Test parameters property exists and is dict."""
        indicator, _ = indicator_and_data
        assert isinstance(indicator.parameters, dict)
        assert len(indicator.parameters) > 0

    def test_validate_method(self, indicator_and_data):
        """Test validate method returns bool."""
        indicator, data = indicator_and_data
        result = indicator.validate(data)
        assert isinstance(result, bool)

    def test_compute_method(self, indicator_and_data):
        """Test compute method returns appropriate result."""
        indicator, data = indicator_and_data
        result = indicator.compute(data)
        assert result is not None

    def test_get_metadata_method(self, indicator_and_data):
        """Test get_metadata returns dict with required keys."""
        indicator, _ = indicator_and_data
        meta = indicator.get_metadata()
        assert isinstance(meta, dict)
        assert "name" in meta
        assert "description" in meta
        assert "parameters" in meta

    def test_to_signal_method(self, indicator_and_data):
        """Test to_signal returns Signal."""
        indicator, data = indicator_and_data
        result = indicator.compute(data)
        signal = indicator.to_signal(result)
        assert isinstance(signal, Signal)
        assert isinstance(signal.direction, SignalDirection)
        assert 0.0 <= signal.confidence <= 1.0
        assert isinstance(signal.timestamp, datetime)
        assert isinstance(signal.metadata, dict)
