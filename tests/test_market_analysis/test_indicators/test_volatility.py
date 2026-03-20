"""Tests for ATR and volatility band indicators (SIG-003).

Covers ATRResult dataclass, ATR calculator, True Range computation,
Wilder's RMA, volatility bands, trailing stop, signal conversion,
BaseIndicator integration, and ConfluenceScorer compatibility.
"""

from datetime import datetime

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.base import Signal, SignalDirection
from market_analysis.indicators.volatility import ATR, ATRResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ohlcv(
    timestamp: int = 0,
    o: float = 100.0,
    h: float = 102.0,
    l: float = 98.0,
    c: float = 100.0,
    v: float = 1000.0,
) -> OHLCVData:
    """Create a single OHLCVData point with sensible defaults."""
    return OHLCVData(
        timestamp=timestamp,
        open_price=o,
        high_price=h,
        low_price=l,
        close_price=c,
        volume=v,
    )


def _make_data(n: int, seed: int = 42) -> list[OHLCVData]:
    """Generate *n* OHLCV bars with a random walk."""
    rng = np.random.RandomState(seed)
    data: list[OHLCVData] = []
    price = 100.0
    for i in range(n):
        change = rng.normal(0, 1.5)
        price = max(price + change, 10.0)
        data.append(
            OHLCVData(
                timestamp=1_600_000_000_000 + i * 60_000,
                open_price=price - 0.5,
                high_price=price + 1.0,
                low_price=price - 1.0,
                close_price=price,
                volume=1000.0,
            )
        )
    return data


def _flat_data(n: int, price: float = 100.0) -> list[OHLCVData]:
    """Generate *n* flat-price OHLCV bars (zero volatility)."""
    return [
        _ohlcv(
            timestamp=1_600_000_000_000 + i * 60_000,
            o=price,
            h=price,
            l=price,
            c=price,
        )
        for i in range(n)
    ]


# ===========================================================================
# ATRResult
# ===========================================================================


class TestATRResult:
    """Tests for the ATRResult dataclass."""

    def test_creation_with_valid_data(self) -> None:
        """ATRResult stores arrays and exposes convenience properties."""
        n = 20
        atr = np.full(n, 1.5)
        upper = np.full(n, 103.0)
        lower = np.full(n, 97.0)
        trailing = np.full(n, 96.0)

        result = ATRResult(
            atr=atr, upper_band=upper, lower_band=lower, trailing_stop=trailing
        )

        assert result.current_atr == 1.5
        assert result.current_trailing_stop == 96.0
        assert result.current_upper_band == 103.0
        assert result.current_lower_band == 97.0

    def test_empty_arrays_return_none(self) -> None:
        """All current_* properties return None for empty arrays."""
        result = ATRResult(
            atr=np.array([]),
            upper_band=np.array([]),
            lower_band=np.array([]),
            trailing_stop=np.array([]),
        )

        assert result.current_atr is None
        assert result.current_trailing_stop is None
        assert result.current_upper_band is None
        assert result.current_lower_band is None

    def test_leading_nan_ignored(self) -> None:
        """Properties skip leading NaN values."""
        atr = np.array([np.nan, np.nan, 2.5, 3.0])
        result = ATRResult(
            atr=atr,
            upper_band=atr,
            lower_band=atr,
            trailing_stop=atr,
        )

        assert result.current_atr == 3.0

    def test_all_nan_returns_none(self) -> None:
        """Properties return None when every entry is NaN."""
        atr = np.full(10, np.nan)
        result = ATRResult(atr=atr, upper_band=atr, lower_band=atr, trailing_stop=atr)

        assert result.current_atr is None
        assert result.current_trailing_stop is None


# ===========================================================================
# ATR initialisation
# ===========================================================================


class TestATRInit:
    """Tests for ATR constructor validation."""

    def test_defaults(self) -> None:
        atr = ATR()
        assert atr.period == 14
        assert atr.multiplier == 2.0
        assert atr.name == "ATR"

    def test_custom_params(self) -> None:
        atr = ATR(period=10, multiplier=3.0, name="ATR_10")
        assert atr.period == 10
        assert atr.multiplier == 3.0
        assert atr.name == "ATR_10"

    def test_period_too_small(self) -> None:
        with pytest.raises(ValueError, match="period must be at least 2"):
            ATR(period=1)

    def test_period_zero(self) -> None:
        with pytest.raises(ValueError, match="period must be at least 2"):
            ATR(period=0)

    def test_period_negative(self) -> None:
        with pytest.raises(ValueError, match="period must be at least 2"):
            ATR(period=-5)

    def test_multiplier_zero(self) -> None:
        with pytest.raises(ValueError, match="multiplier must be positive"):
            ATR(multiplier=0.0)

    def test_multiplier_negative(self) -> None:
        with pytest.raises(ValueError, match="multiplier must be positive"):
            ATR(multiplier=-1.0)


# ===========================================================================
# ATR metadata / properties
# ===========================================================================


class TestATRMetadata:
    """Tests for BaseIndicator property implementations."""

    def test_description(self) -> None:
        atr = ATR(period=14, multiplier=2.0)
        assert "14" in atr.description
        assert "2" in atr.description

    def test_parameters(self) -> None:
        atr = ATR(period=7, multiplier=1.5)
        assert atr.parameters == {"period": 7, "multiplier": 1.5}

    def test_get_metadata(self) -> None:
        atr = ATR(period=10, multiplier=3.0, name="MyATR")
        meta = atr.get_metadata()
        assert meta["name"] == "MyATR"
        assert "period" in meta["parameters"]
        assert "multiplier" in meta["parameters"]


# ===========================================================================
# validate
# ===========================================================================


class TestATRValidate:
    """Tests for ATR.validate()."""

    def test_exact_minimum(self) -> None:
        atr = ATR(period=14)
        assert atr.validate(_flat_data(15)) is True  # period + 1

    def test_above_minimum(self) -> None:
        atr = ATR(period=14)
        assert atr.validate(_flat_data(50)) is True

    def test_below_minimum(self) -> None:
        atr = ATR(period=14)
        assert atr.validate(_flat_data(14)) is False

    def test_empty_data(self) -> None:
        atr = ATR(period=14)
        assert atr.validate([]) is False

    def test_small_period(self) -> None:
        atr = ATR(period=2)
        assert atr.validate(_flat_data(3)) is True
        assert atr.validate(_flat_data(2)) is False


# ===========================================================================
# compute
# ===========================================================================


class TestATRCompute:
    """Tests for ATR.compute() main logic."""

    def test_output_arrays_match_input_length(self) -> None:
        data = _make_data(30)
        result = ATR(period=14).compute(data)

        assert len(result.atr) == 30
        assert len(result.upper_band) == 30
        assert len(result.lower_band) == 30
        assert len(result.trailing_stop) == 30

    def test_insufficient_data_raises(self) -> None:
        data = _flat_data(10)
        with pytest.raises(ValueError, match="Need 15 data points"):
            ATR(period=14).compute(data)

    def test_exact_minimum_data_succeeds(self) -> None:
        data = _flat_data(15)
        result = ATR(period=14).compute(data)
        assert isinstance(result, ATRResult)

    def test_atr_is_non_negative(self) -> None:
        data = _make_data(50)
        result = ATR(period=14).compute(data)
        valid = result.atr[~np.isnan(result.atr)]
        assert np.all(valid >= 0)

    def test_atr_is_positive_with_volatility(self) -> None:
        data = _make_data(50, seed=99)
        result = ATR(period=14).compute(data)
        valid = result.atr[~np.isnan(result.atr)]
        assert np.all(valid > 0)

    def test_atr_zero_with_flat_prices(self) -> None:
        data = _flat_data(20)
        result = ATR(period=14).compute(data)
        valid = result.atr[~np.isnan(result.atr)]
        np.testing.assert_array_almost_equal(valid, 0.0, decimal=10)

    def test_leading_nan_count(self) -> None:
        """Exactly `period` leading NaN values in the ATR array."""
        period = 14
        data = _make_data(30)
        result = ATR(period=period).compute(data)
        assert np.all(np.isnan(result.atr[:period]))
        assert not np.isnan(result.atr[period])

    def test_upper_band_above_close(self) -> None:
        """Upper band = close + ATR * multiplier, so must be >= close."""
        data = _make_data(50)
        closes = np.array([d.close_price for d in data])
        result = ATR(period=14).compute(data)

        valid = ~np.isnan(result.upper_band)
        assert np.all(result.upper_band[valid] >= closes[valid])

    def test_lower_band_below_close(self) -> None:
        """Lower band = close - ATR * multiplier, so must be <= close."""
        data = _make_data(50)
        closes = np.array([d.close_price for d in data])
        result = ATR(period=14).compute(data)

        valid = ~np.isnan(result.lower_band)
        assert np.all(result.lower_band[valid] <= closes[valid])

    def test_band_width_symmetry(self) -> None:
        """upper_band - close == close - lower_band."""
        data = _make_data(50)
        closes = np.array([d.close_price for d in data])
        result = ATR(period=14).compute(data)

        valid = ~np.isnan(result.upper_band)
        np.testing.assert_array_almost_equal(
            result.upper_band[valid] - closes[valid],
            closes[valid] - result.lower_band[valid],
            decimal=10,
        )

    def test_trailing_stop_never_decreases(self) -> None:
        """Trailing stop should only ratchet upward."""
        data = _make_data(100, seed=7)
        result = ATR(period=14).compute(data)

        valid = result.trailing_stop[~np.isnan(result.trailing_stop)]
        if len(valid) > 1:
            diffs = np.diff(valid)
            assert np.all(diffs >= -1e-10), "Trailing stop decreased"

    def test_trailing_stop_below_close_in_uptrend(self) -> None:
        """Trailing stop is below close while price is above it (uptrend)."""
        # Create a steady uptrend where trailing stop should trail below close
        data = []
        price = 100.0
        for i in range(50):
            price += 0.5  # steady rise
            data.append(
                _ohlcv(
                    timestamp=1_600_000_000_000 + i * 60_000,
                    o=price - 0.2,
                    h=price + 0.3,
                    l=price - 0.3,
                    c=price,
                )
            )

        closes = np.array([d.close_price for d in data])
        result = ATR(period=14).compute(data)

        valid = ~np.isnan(result.trailing_stop)
        # In a steady uptrend, trailing stop should be below close
        assert np.all(result.trailing_stop[valid] <= closes[valid])

    def test_different_periods(self) -> None:
        """ATR with period=7 vs period=14 on same data."""
        data = _make_data(50)
        r7 = ATR(period=7).compute(data)
        r14 = ATR(period=14).compute(data)

        # Both should have valid values at the end
        assert r7.current_atr is not None
        assert r14.current_atr is not None

        # NaN count should differ
        nan7 = np.sum(np.isnan(r7.atr))
        nan14 = np.sum(np.isnan(r14.atr))
        assert nan7 < nan14

    def test_different_multipliers(self) -> None:
        """Larger multiplier → wider bands."""
        data = _make_data(50)
        r1 = ATR(period=14, multiplier=1.0).compute(data)
        r3 = ATR(period=14, multiplier=3.0).compute(data)

        valid = ~np.isnan(r1.upper_band) & ~np.isnan(r3.upper_band)
        # Wider multiplier means wider bands
        assert np.all(
            (r3.upper_band[valid] - r3.lower_band[valid])
            >= (r1.upper_band[valid] - r1.lower_band[valid]) - 1e-10
        )


# ===========================================================================
# True Range calculation (white-box)
# ===========================================================================


class TestTrueRange:
    """Verify True Range formula via compute output."""

    def test_tr_components(self) -> None:
        """TR = max(H-L, |H-prev_C|, |L-prev_C|) for a known case."""
        # Bar 0: close=100
        # Bar 1: H=110, L=95, C=105
        data = [
            _ohlcv(c=100.0, h=101.0, l=99.0),
            _ohlcv(c=105.0, h=110.0, l=95.0),
        ]
        # Need period+1 = 3 for period=2, so add one more bar
        data.append(_ohlcv(c=107.0, h=108.0, l=104.0))

        result = ATR(period=2).compute(data)
        # TR is computed from bar 1 onward (no previous close for bar 0).
        #   TR_impl[0] (bar 1) = max(110-95, |110-100|, |95-100|) = 15
        #   TR_impl[1] (bar 2) = max(108-104, |108-105|, |104-105|) = 4
        # RMA seed = mean(TR_impl[0:2]) = mean(15, 4) = 9.5
        # With period=2, only 2 TR values so seed IS the only valid ATR.
        # atr_padded[2] = atr_rma[1] = 9.5

        # The padded array has NaN at index 0, valid from index 2 (period=2)
        assert np.isnan(result.atr[0])
        assert np.isnan(result.atr[1])
        assert abs(result.atr[2] - 9.5) < 1e-10

    def test_gap_up(self) -> None:
        """TR should capture gap-up via |H - prev_close|."""
        data = [
            _ohlcv(c=100.0, h=101.0, l=99.0),
            _ohlcv(c=110.0, h=112.0, l=109.0),  # gap up
        ]
        data.append(_ohlcv(c=111.0, h=113.0, l=110.0))

        result = ATR(period=2).compute(data)
        # TR for bar 1: max(112-109, |112-100|, |109-100|) = max(3, 12, 9) = 12
        assert result.atr[2] is not None and result.atr[2] > 0


# ===========================================================================
# RMA (Wilder's smoothing) white-box
# ===========================================================================


class TestRMA:
    """Verify Wilder's RMA calculation."""

    def test_rma_seed_is_sma(self) -> None:
        """First valid RMA value equals the SMA of the first `period` values."""
        values = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
        period = 3
        rma = ATR._calculate_rma(values, period)

        expected_seed = np.mean(values[:period])  # (2+4+6)/3 = 4
        assert abs(rma[period - 1] - expected_seed) < 1e-10

    def test_rma_smoothing(self) -> None:
        """Verify subsequent RMA values use exponential smoothing."""
        values = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        period = 3
        alpha = 1.0 / period
        rma = ATR._calculate_rma(values, period)

        # Seed: mean(10, 20, 30) = 20
        # Index 3: alpha * 40 + (1-alpha) * 20 = (1/3)*40 + (2/3)*20 = 26.6667
        expected_3 = alpha * 40 + (1 - alpha) * 20
        assert abs(rma[3] - expected_3) < 1e-10

        # Index 4: alpha * 50 + (1-alpha) * 26.6667
        expected_4 = alpha * 50 + (1 - alpha) * expected_3
        assert abs(rma[4] - expected_4) < 1e-10

    def test_rma_leading_nan(self) -> None:
        """RMA output has NaN for indices before period-1."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        rma = ATR._calculate_rma(values, period=3)

        assert np.isnan(rma[0])
        assert np.isnan(rma[1])
        assert not np.isnan(rma[2])

    def test_rma_insufficient_data(self) -> None:
        """RMA returns all NaN when input is shorter than period."""
        values = np.array([1.0, 2.0])
        rma = ATR._calculate_rma(values, period=5)

        assert np.all(np.isnan(rma))

    def test_rma_constant_input(self) -> None:
        """RMA of constant values equals that constant."""
        values = np.full(10, 5.0)
        rma = ATR._calculate_rma(values, period=3)

        valid = rma[~np.isnan(rma)]
        np.testing.assert_array_almost_equal(valid, 5.0, decimal=10)


# ===========================================================================
# Trailing stop
# ===========================================================================


class TestTrailingStop:
    """Verify ATR-based trailing stop behaviour."""

    def test_trailing_stop_initialisation(self) -> None:
        """Stop starts at close[period] - ATR[period] * multiplier."""
        period = 2
        multiplier = 2.0
        data = [
            _ohlcv(c=100.0, h=101.0, l=99.0),
            _ohlcv(c=102.0, h=103.0, l=101.0),
            _ohlcv(c=104.0, h=105.0, l=103.0),
        ]

        result = ATR(period=period, multiplier=multiplier).compute(data)
        # TR is computed from bar 1 onward (no previous close for bar 0).
        #   TR_impl[0] (bar 1) = max(103-101, |103-100|, |101-100|) = 3
        #   TR_impl[1] (bar 2) = max(105-103, |105-102|, |103-102|) = 3
        # RMA seed = mean(3, 3) = 3.0
        # ATR[2] = 3.0 (seed is the only valid value with only 2 TR entries)
        # Stop init = close[2] - ATR[2] * multiplier = 104 - 3.0 * 2 = 98.0
        assert abs(result.trailing_stop[period] - 98.0) < 1e-10

    def test_trailing_stop_ratchets_up(self) -> None:
        """Stop increases when price moves up."""
        period = 2
        data = [
            _ohlcv(c=100.0, h=101.0, l=99.0),
            _ohlcv(c=100.0, h=101.0, l=99.0),  # flat
            _ohlcv(c=110.0, h=111.0, l=109.0),  # big move up
            _ohlcv(c=115.0, h=116.0, l=114.0),  # continued up
        ]

        result = ATR(period=period, multiplier=2.0).compute(data)
        # Stop should increase from index 2 to 3
        assert result.trailing_stop[3] >= result.trailing_stop[2] - 1e-10

    def test_trailing_stop_flat_on_pullback(self) -> None:
        """Stop stays flat when price pulls back below previous stop."""
        period = 2
        data = [
            _ohlcv(c=100.0, h=101.0, l=99.0),
            _ohlcv(c=100.0, h=101.0, l=99.0),  # flat
            _ohlcv(c=110.0, h=111.0, l=109.0),  # big up
            _ohlcv(c=95.0, h=96.0, l=94.0),  # sharp pullback
        ]

        result = ATR(period=period, multiplier=2.0).compute(data)
        # Stop at index 3 should NOT decrease
        assert result.trailing_stop[3] >= result.trailing_stop[2] - 1e-10

    def test_trailing_stop_nan_before_period(self) -> None:
        """Trailing stop is NaN for indices before period."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)

        assert np.all(np.isnan(result.trailing_stop[:14]))
        assert not np.isnan(result.trailing_stop[14])


# ===========================================================================
# to_signal
# ===========================================================================


class TestATRToSignal:
    """Tests for ATR.to_signal() conversion."""

    def test_signal_hold_direction(self) -> None:
        """ATR signal direction is always HOLD (non-directional)."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert signal.direction == SignalDirection.HOLD

    def test_signal_confidence_range(self) -> None:
        """Confidence is always in [0, 1]."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert 0.0 <= signal.confidence <= 1.0

    def test_low_volatility_high_confidence(self) -> None:
        """Flat prices (ATR≈0) → confidence near 1.0."""
        data = _flat_data(20)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert signal.confidence >= 0.95

    def test_high_volatility_low_confidence(self) -> None:
        """High volatility → confidence near floor of 0.3."""
        # Create data with huge daily ranges
        data = []
        for i in range(30):
            data.append(
                _ohlcv(
                    timestamp=1_600_000_000_000 + i * 60_000,
                    o=100.0,
                    h=100.0 + 20.0,  # 20-point range
                    l=100.0 - 20.0,
                    c=100.0,
                )
            )

        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert signal.confidence <= 0.35

    def test_signal_metadata_has_atr(self) -> None:
        """Signal metadata contains current ATR value."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert "atr" in signal.metadata
        assert isinstance(signal.metadata["atr"], float)

    def test_signal_metadata_has_trailing_stop(self) -> None:
        """Signal metadata contains current trailing stop."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert "trailing_stop" in signal.metadata

    def test_signal_with_empty_result(self) -> None:
        """Signal with no valid ATR returns 0.5 confidence."""
        result = ATRResult(
            atr=np.array([np.nan]),
            upper_band=np.array([np.nan]),
            lower_band=np.array([np.nan]),
            trailing_stop=np.array([np.nan]),
        )
        signal = ATR().to_signal(result)

        assert signal.confidence == 0.5
        assert signal.direction == SignalDirection.HOLD
        assert signal.metadata["atr"] is None

    def test_signal_is_signal_instance(self) -> None:
        """to_signal returns a Signal dataclass instance."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert isinstance(signal, Signal)

    def test_signal_has_timestamp(self) -> None:
        """Signal includes a datetime timestamp."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        assert isinstance(signal.timestamp, datetime)


# ===========================================================================
# BaseIndicator interface compliance
# ===========================================================================


class TestBaseIndicatorCompliance:
    """Ensure ATR fully satisfies the BaseIndicator contract."""

    def test_is_base_indicator(self) -> None:
        atr = ATR()
        from market_analysis.indicators.base import BaseIndicator

        assert isinstance(atr, BaseIndicator)

    def test_name_property(self) -> None:
        assert ATR(name="CustomATR").name == "CustomATR"

    def test_compute_return_type(self) -> None:
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        assert isinstance(result, ATRResult)

    def test_validate_return_type(self) -> None:
        assert isinstance(ATR(period=14).validate(_make_data(30)), bool)


# ===========================================================================
# ConfluenceScorer integration
# ===========================================================================


class TestConfluenceScorerIntegration:
    """Verify ATR signals are compatible with the ConfluenceScorer pipeline.

    The ConfluenceScorer consumes ``AggregatedSignals`` where each signal
    carries ``indicator_type``, ``confidence``, ``raw_value``, etc.  ATR's
    ``to_signal()`` output must provide data that can be mapped into this
    pipeline without modification.
    """

    def test_signal_has_confidence_for_aggregation(self) -> None:
        """ATR signal confidence can feed into the confluence pipeline."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        # ConfluenceScorer expects 0-1 confidence
        assert 0.0 <= signal.confidence <= 1.0

    def test_signal_metadata_carries_raw_value(self) -> None:
        """ATR signal metadata carries raw_value compatible fields."""
        data = _make_data(30)
        result = ATR(period=14).compute(data)
        signal = ATR().to_signal(result)

        # The signal aggregator expects a raw_value per signal
        assert "atr" in signal.metadata
        assert signal.metadata["atr"] is not None

    def test_atr_result_provides_confluence_inputs(self) -> None:
        """ATRResult fields map cleanly to confluence signal fields."""
        data = _make_data(30)
        atr = ATR(period=14)
        result = atr.compute(data)

        # These fields should be available for aggregation
        assert result.current_atr is not None
        assert result.current_trailing_stop is not None

        # Can construct a confluence-compatible dict
        confluence_signal = {
            "indicator_type": atr.name,
            "confidence": atr.to_signal(result).confidence,
            "raw_value": result.current_atr,
            "trailing_stop": result.current_trailing_stop,
        }
        assert confluence_signal["indicator_type"] == "ATR"
        assert isinstance(confluence_signal["confidence"], float)
        assert isinstance(confluence_signal["raw_value"], float)

    def test_multiple_timeframes_compatible(self) -> None:
        """ATR can produce signals for multiple timeframes independently."""
        data_1h = _make_data(30, seed=1)
        data_4h = _make_data(30, seed=2)

        atr_1h = ATR(period=14, name="ATR_1h")
        atr_4h = ATR(period=14, name="ATR_4h")

        sig_1h = atr_1h.to_signal(atr_1h.compute(data_1h))
        sig_4h = atr_4h.to_signal(atr_4h.compute(data_4h))

        # Both produce valid signals for confluence aggregation
        assert 0.0 <= sig_1h.confidence <= 1.0
        assert 0.0 <= sig_4h.confidence <= 1.0
        assert sig_1h.direction == SignalDirection.HOLD
        assert sig_4h.direction == SignalDirection.HOLD


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Miscellaneous edge cases and robustness."""

    def test_very_large_dataset(self) -> None:
        """ATR handles 1000+ bars without error."""
        data = _make_data(1000)
        result = ATR(period=14).compute(data)

        assert len(result.atr) == 1000
        assert result.current_atr is not None

    def test_period_equals_data_minus_one(self) -> None:
        """Minimum valid data (period + 1)."""
        period = 14
        data = _make_data(period + 1)
        result = ATR(period=period).compute(data)

        # Only last value should be valid
        assert np.isnan(result.atr[period - 1])
        assert not np.isnan(result.atr[period])

    def test_single_candle_range(self) -> None:
        """All bars have identical OHLC (TR = 0)."""
        data = _flat_data(20, price=50.0)
        result = ATR(period=14).compute(data)

        valid = result.atr[~np.isnan(result.atr)]
        np.testing.assert_array_almost_equal(valid, 0.0, decimal=10)

    def test_alternating_high_low_volatility(self) -> None:
        """ATR responds to changing volatility regimes."""
        data = []
        price = 100.0
        for i in range(40):
            if i < 20:
                # Low volatility
                h, l = price + 0.5, price - 0.5
            else:
                # High volatility
                h, l = price + 5.0, price - 5.0
            data.append(
                _ohlcv(
                    timestamp=1_600_000_000_000 + i * 60_000,
                    o=price,
                    h=h,
                    l=l,
                    c=price,
                )
            )

        result = ATR(period=14).compute(data)

        # ATR in high-vol regime should exceed low-vol regime
        low_vol_atr = result.atr[19]  # End of low-vol period
        high_vol_atr = result.atr[-1]  # End of high-vol period

        assert not np.isnan(low_vol_atr)
        assert not np.isnan(high_vol_atr)
        assert high_vol_atr > low_vol_atr
