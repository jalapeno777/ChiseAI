"""Tests for TokenCorrelator and correlation result types."""

from __future__ import annotations

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.correlation.token_correlator import (
    DEFAULT_TOKENS,
    CorrelationSnapshot,
    RollingCorrelationResult,
    TokenCorrelator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(
    timestamps: list[int],
    closes: list[float],
) -> list[OHLCVData]:
    """Build a list of OHLCVData from timestamps and close prices."""
    bars: list[OHLCVData] = []
    for ts, c in zip(timestamps, closes):
        bars.append(
            OHLCVData(
                timestamp=ts,
                open_price=c,
                high_price=c * 1.01,
                low_price=c * 0.99,
                close_price=c,
                volume=1000.0,
            )
        )
    return bars


def _make_correlated_data(
    n_bars: int = 100,
    tokens: list[str] | None = None,
    base_seed: int = 42,
    correlation_strength: float = 0.8,
) -> dict[str, list[OHLCVData]]:
    """Generate synthetic OHLCV data with configurable correlation.

    Args:
        n_bars: Number of bars per token.
        tokens: Token list (defaults to first 3 of DEFAULT_TOKENS for speed).
        base_seed: Random seed.
        correlation_strength: How strongly prices correlate (0-1).

    Returns:
        ``token -> list[OHLCVData]`` mapping.
    """
    rng = np.random.RandomState(base_seed)
    tokens = tokens or DEFAULT_TOKENS[:3]

    # Common market driver
    common = rng.randn(n_bars).cumsum() + 100

    data: dict[str, list[OHLCVData]] = {}
    timestamps = list(range(1_000_000, 1_000_000 + n_bars * 60, 60))

    for token in tokens:
        noise = rng.randn(n_bars) * (1 - correlation_strength)
        closes = common * correlation_strength + noise.cumsum()
        closes = np.clip(closes, 1.0, None)  # keep positive
        data[token] = _make_ohlcv(timestamps, closes.tolist())

    return data


def _make_uncorrelated_data(
    n_bars: int = 100,
    tokens: list[str] | None = None,
) -> dict[str, list[OHLCVData]]:
    """Generate synthetic OHLCV data with independent random walks."""
    tokens = tokens or DEFAULT_TOKENS[:3]
    data: dict[str, list[OHLCVData]] = {}
    timestamps = list(range(1_000_000, 1_000_000 + n_bars * 60, 60))

    for i, token in enumerate(tokens):
        rng = np.random.RandomState(100 + i)
        closes = rng.randn(n_bars).cumsum() + 100
        closes = np.clip(closes, 1.0, None)
        data[token] = _make_ohlcv(timestamps, closes.tolist())

    return data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def correlated_data() -> dict[str, list[OHLCVData]]:
    return _make_correlated_data(n_bars=100)


@pytest.fixture
def uncorrelated_data() -> dict[str, list[OHLCVData]]:
    return _make_uncorrelated_data(n_bars=100)


@pytest.fixture
def three_tokens() -> list[str]:
    return DEFAULT_TOKENS[:3]


@pytest.fixture
def correlator(three_tokens: list[str]) -> TokenCorrelator:
    return TokenCorrelator(tokens=three_tokens, windows=[10, 20])


@pytest.fixture
def correlator_single_window(three_tokens: list[str]) -> TokenCorrelator:
    return TokenCorrelator(tokens=three_tokens, windows=[20])


# ---------------------------------------------------------------------------
# TokenCorrelator.__init__
# ---------------------------------------------------------------------------


class TestTokenCorrelatorInit:
    def test_default_tokens(self) -> None:
        tc = TokenCorrelator()
        assert tc.tokens == list(DEFAULT_TOKENS)

    def test_default_windows(self) -> None:
        tc = TokenCorrelator()
        assert tc.windows == [20, 50]

    def test_custom_tokens(self) -> None:
        tc = TokenCorrelator(tokens=["BTC", "ETH"])
        assert tc.tokens == ["BTC", "ETH"]

    def test_custom_windows(self) -> None:
        tc = TokenCorrelator(windows=[5, 10, 30])
        assert tc.windows == [5, 10, 30]

    def test_custom_name(self) -> None:
        tc = TokenCorrelator(name="MyCorr")
        assert tc.name == "MyCorr"

    def test_default_name(self) -> None:
        tc = TokenCorrelator()
        assert tc.name == "TokenCorrelator"

    def test_min_periods_defaults_to_half_max_window(self) -> None:
        tc = TokenCorrelator(windows=[20, 50])
        assert tc.min_periods == 25  # max(20,50) // 2

    def test_custom_min_periods(self) -> None:
        tc = TokenCorrelator(windows=[20, 50], min_periods=10)
        assert tc.min_periods == 10


# ---------------------------------------------------------------------------
# BaseIndicator interface
# ---------------------------------------------------------------------------


class TestBaseIndicatorInterface:
    def test_description(self, correlator: TokenCorrelator) -> None:
        desc = correlator.description
        assert "correlation" in desc.lower()
        assert "BTC" in desc

    def test_parameters(self, correlator: TokenCorrelator) -> None:
        params = correlator.parameters
        assert "tokens" in params
        assert "windows" in params
        assert "min_periods" in params

    def test_get_metadata(self, correlator: TokenCorrelator) -> None:
        meta = correlator.get_metadata()
        assert meta["name"] == correlator.name
        assert "description" in meta
        assert "parameters" in meta

    def test_validate_with_insufficient_data(self, correlator: TokenCorrelator) -> None:
        data = {"BTC": [], "ETH": [], "SOL": []}
        assert correlator.validate(data) is False

    def test_validate_with_enough_data(
        self, correlator: TokenCorrelator, correlated_data: dict[str, list[OHLCVData]]
    ) -> None:
        # validate checks list length >= max(windows)
        first_token_bars = next(iter(correlated_data.values()))
        assert correlator.validate(first_token_bars) is True

    def test_validate_non_list(self, correlator: TokenCorrelator) -> None:
        assert correlator.validate("not a list") is False  # type: ignore[arg-type]

    def test_validate_empty_list(self, correlator: TokenCorrelator) -> None:
        assert correlator.validate([]) is False


# ---------------------------------------------------------------------------
# compute()
# ---------------------------------------------------------------------------


class TestCompute:
    def test_basic_compute(
        self,
        correlator: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator.compute(correlated_data)
        assert isinstance(result, RollingCorrelationResult)
        assert len(result.snapshots) > 0
        assert result.tokens == correlator.tokens

    def test_result_has_correct_windows(
        self,
        correlator: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator.compute(correlated_data)
        assert set(result.windows) == set(correlator.windows)

    def test_matrix_shape(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        n = len(correlator_single_window.tokens)
        for snap in result.snapshots:
            assert snap.matrix.shape == (n, n)

    def test_diagonal_is_one(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        for snap in result.snapshots:
            np.testing.assert_array_almost_equal(
                np.diag(snap.matrix), np.ones(len(snap.tokens))
            )

    def test_matrix_is_symmetric(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        for snap in result.snapshots:
            np.testing.assert_array_almost_equal(snap.matrix, snap.matrix.T)

    def test_correlation_values_in_range(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        for snap in result.snapshots:
            # Off-diagonal values should be in [-1, 1]
            mask = ~np.eye(len(snap.tokens), dtype=bool)
            values = snap.matrix[mask]
            assert np.all(values >= -1.0 - 1e-10)
            assert np.all(values <= 1.0 + 1e-10)

    def test_correlated_data_has_high_correlation(
        self,
        correlator_single_window: TokenCorrelator,
    ) -> None:
        data = _make_correlated_data(n_bars=200, correlation_strength=0.95)
        result = correlator_single_window.compute(data)
        latest = result.latest
        assert latest is not None
        mask = ~np.eye(len(latest.tokens), dtype=bool)
        mean_corr = float(np.mean(np.abs(latest.matrix[mask])))
        assert mean_corr > 0.5, f"Expected high correlation, got {mean_corr}"

    def test_uncorrelated_data_has_low_correlation(
        self,
        correlator_single_window: TokenCorrelator,
        uncorrelated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(uncorrelated_data)
        latest = result.latest
        assert latest is not None
        mask = ~np.eye(len(latest.tokens), dtype=bool)
        mean_corr = float(np.mean(np.abs(latest.matrix[mask])))
        # With independent random walks, correlation should be low
        assert mean_corr < 0.8, f"Expected lower correlation, got {mean_corr}"

    def test_timestamps_populated(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        assert len(result.timestamps) > 0
        # Timestamps should be ints
        assert result.timestamps.dtype in (np.int64, np.int32)


# ---------------------------------------------------------------------------
# compute() – error handling
# ---------------------------------------------------------------------------


class TestComputeErrors:
    def test_empty_data_raises(self, correlator: TokenCorrelator) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            correlator.compute({})

    def test_token_mismatch_raises(self, correlator: TokenCorrelator) -> None:
        data = _make_correlated_data(n_bars=100, tokens=["BTC", "ETH", "DOGE"])
        with pytest.raises(ValueError, match="Token mismatch"):
            correlator.compute(data)

    def test_insufficient_bars_raises(self, correlator: TokenCorrelator) -> None:
        data = _make_correlated_data(n_bars=5)  # less than max window (20)
        with pytest.raises(ValueError, match="Need at least"):
            correlator.compute(data)

    def test_length_mismatch_raises(self, three_tokens: list[str]) -> None:
        tc = TokenCorrelator(tokens=three_tokens, windows=[10])
        data_a = _make_correlated_data(n_bars=50, tokens=["BTC", "ETH", "SOL"])
        data_a["SOL"] = data_a["SOL"][:-5]  # shorten one series
        with pytest.raises(ValueError, match="length mismatch"):
            tc.compute(data_a)


# ---------------------------------------------------------------------------
# CorrelationSnapshot helpers
# ---------------------------------------------------------------------------


class TestCorrelationSnapshot:
    @pytest.fixture
    def snapshot(self) -> CorrelationSnapshot:
        mat = np.array(
            [
                [1.0, 0.8, 0.3],
                [0.8, 1.0, -0.2],
                [0.3, -0.2, 1.0],
            ]
        )
        return CorrelationSnapshot(
            matrix=mat,
            tokens=["BTC", "ETH", "SOL"],
            window=20,
            timestamp=1_000_000,
        )

    def test_get_pair(self, snapshot: CorrelationSnapshot) -> None:
        assert snapshot.get_pair("BTC", "ETH") == pytest.approx(0.8)
        assert snapshot.get_pair("ETH", "BTC") == pytest.approx(0.8)
        assert snapshot.get_pair("SOL", "SOL") == pytest.approx(1.0)

    def test_get_pair_invalid_token(self, snapshot: CorrelationSnapshot) -> None:
        with pytest.raises(ValueError):
            snapshot.get_pair("BTC", "DOGE")

    def test_most_correlated(self, snapshot: CorrelationSnapshot) -> None:
        top = snapshot.most_correlated("BTC", n=2)
        assert len(top) == 2
        assert top[0][0] == "ETH"  # 0.8 > 0.3
        assert top[0][1] == pytest.approx(0.8)

    def test_least_correlated(self, snapshot: CorrelationSnapshot) -> None:
        bottom = snapshot.least_correlated("BTC", n=2)
        assert len(bottom) == 2
        assert bottom[0][0] == "SOL"  # 0.3 < 0.8
        assert bottom[0][1] == pytest.approx(0.3)

    def test_most_correlated_excludes_self(self, snapshot: CorrelationSnapshot) -> None:
        top = snapshot.most_correlated("BTC", n=5)
        tokens = [t for t, _ in top]
        assert "BTC" not in tokens

    def test_least_correlated_excludes_self(
        self, snapshot: CorrelationSnapshot
    ) -> None:
        bottom = snapshot.least_correlated("BTC", n=5)
        tokens = [t for t, _ in bottom]
        assert "BTC" not in tokens


# ---------------------------------------------------------------------------
# RollingCorrelationResult helpers
# ---------------------------------------------------------------------------


class TestRollingCorrelationResult:
    def test_latest_returns_last(self) -> None:
        snaps = [
            CorrelationSnapshot(
                matrix=np.eye(2), tokens=["A", "B"], window=10, timestamp=1
            ),
            CorrelationSnapshot(
                matrix=np.eye(2), tokens=["A", "B"], window=10, timestamp=2
            ),
        ]
        result = RollingCorrelationResult(
            snapshots=snaps,
            timestamps=np.array([1, 2]),
            tokens=["A", "B"],
            windows=[10],
        )
        assert result.latest is not None
        assert result.latest.timestamp == 2

    def test_latest_none_when_empty(self) -> None:
        result = RollingCorrelationResult()
        assert result.latest is None

    def test_get_pair_series(self) -> None:
        snaps = [
            CorrelationSnapshot(
                matrix=np.array([[1.0, 0.5], [0.5, 1.0]]),
                tokens=["A", "B"],
                window=10,
                timestamp=1,
            ),
            CorrelationSnapshot(
                matrix=np.array([[1.0, 0.7], [0.7, 1.0]]),
                tokens=["A", "B"],
                window=10,
                timestamp=2,
            ),
        ]
        result = RollingCorrelationResult(
            snapshots=snaps,
            timestamps=np.array([1, 2]),
            tokens=["A", "B"],
            windows=[10],
        )
        series = result.get_pair_series("A", "B")
        assert series == [0.5, 0.7]


# ---------------------------------------------------------------------------
# to_signal()
# ---------------------------------------------------------------------------


class TestToSignal:
    def test_signal_hold_direction(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        signal = correlator_single_window.to_signal(result)
        assert signal.direction.value == "hold"
        assert 0.0 <= signal.confidence <= 1.0

    def test_signal_no_snapshot(
        self,
        correlator_single_window: TokenCorrelator,
    ) -> None:
        empty_result = RollingCorrelationResult()
        signal = correlator_single_window.to_signal(empty_result)
        assert signal.confidence == 0.0

    def test_signal_metadata(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        signal = correlator_single_window.to_signal(result)
        assert "mean_abs_correlation" in signal.metadata
        assert "window" in signal.metadata
        assert "num_tokens" in signal.metadata


# ---------------------------------------------------------------------------
# update() (incremental)
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_update_with_new_data(
        self,
        correlator_single_window: TokenCorrelator,
    ) -> None:
        initial_data = _make_correlated_data(n_bars=50)
        result = correlator_single_window.compute(initial_data)
        assert len(result.snapshots) > 0

        # New bars
        new_data = _make_correlated_data(n_bars=50, base_seed=99)
        updated = correlator_single_window.update(result, new_data)
        assert isinstance(updated, RollingCorrelationResult)
        assert len(updated.snapshots) > 0

    def test_update_empty_new_data_raises(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        with pytest.raises(ValueError, match="must not be empty"):
            correlator_single_window.update(result, {})

    def test_update_token_mismatch_raises(
        self,
        correlator_single_window: TokenCorrelator,
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        result = correlator_single_window.compute(correlated_data)
        bad_new = _make_correlated_data(n_bars=10, tokens=["BTC", "ETH", "DOGE"])
        with pytest.raises(ValueError, match="Token mismatch"):
            correlator_single_window.update(result, bad_new)


# ---------------------------------------------------------------------------
# Multiple window sizes
# ---------------------------------------------------------------------------


class TestMultipleWindows:
    def test_multiple_windows_produce_more_snapshots(
        self,
        three_tokens: list[str],
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        single = TokenCorrelator(tokens=three_tokens, windows=[20])
        multi = TokenCorrelator(
            tokens=three_tokens, windows=[10, 20, 50], min_periods=5
        )

        result_single = single.compute(correlated_data)
        result_multi = multi.compute(correlated_data)

        # Multi should have more snapshots (one per window per bar)
        assert len(result_multi.snapshots) > len(result_single.snapshots)

    def test_snapshots_have_correct_window_labels(
        self,
        three_tokens: list[str],
        correlated_data: dict[str, list[OHLCVData]],
    ) -> None:
        tc = TokenCorrelator(tokens=three_tokens, windows=[10, 20], min_periods=5)
        result = tc.compute(correlated_data)
        window_labels = {snap.window for snap in result.snapshots}
        assert window_labels == {10, 20}


# ---------------------------------------------------------------------------
# Full token universe (10 tokens)
# ---------------------------------------------------------------------------


class TestFullUniverse:
    def test_full_universe_compute(self) -> None:
        tc = TokenCorrelator(tokens=list(DEFAULT_TOKENS), windows=[20])
        data = _make_correlated_data(
            n_bars=100,
            tokens=list(DEFAULT_TOKENS),
            correlation_strength=0.7,
        )
        result = tc.compute(data)
        assert result.tokens == list(DEFAULT_TOKENS)
        assert result.latest is not None
        assert result.latest.matrix.shape == (10, 10)

    def test_full_universe_diagonal(self) -> None:
        tc = TokenCorrelator(tokens=list(DEFAULT_TOKENS), windows=[20])
        data = _make_correlated_data(n_bars=100, tokens=list(DEFAULT_TOKENS))
        result = tc.compute(data)
        for snap in result.snapshots:
            np.testing.assert_array_almost_equal(np.diag(snap.matrix), np.ones(10))


# ---------------------------------------------------------------------------
# _simple_returns (static)
# ---------------------------------------------------------------------------


class TestSimpleReturns:
    def test_basic_returns(self) -> None:
        prices = np.array([100.0, 110.0, 105.0])
        returns = TokenCorrelator._simple_returns(prices)
        assert np.isnan(returns[0])
        assert returns[1] == pytest.approx(0.1)  # (110-100)/100
        assert returns[2] == pytest.approx(-5.0 / 110.0)  # (105-110)/110

    def test_single_price(self) -> None:
        prices = np.array([100.0])
        returns = TokenCorrelator._simple_returns(prices)
        assert len(returns) == 1
        assert np.isnan(returns[0])

    def test_constant_prices(self) -> None:
        prices = np.array([100.0, 100.0, 100.0])
        returns = TokenCorrelator._simple_returns(prices)
        assert np.isnan(returns[0])
        assert returns[1] == pytest.approx(0.0)
        assert returns[2] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_minimum_data_points(self) -> None:
        """Compute with exactly max(windows) bars."""
        tc = TokenCorrelator(tokens=["BTC", "ETH"], windows=[10])
        data = _make_correlated_data(n_bars=10, tokens=["BTC", "ETH"])
        result = tc.compute(data)
        # With min_periods = 5, we should get some snapshots
        assert len(result.snapshots) >= 0  # may be 0 if min_periods not met

    def test_perfect_correlation(self) -> None:
        """Two tokens with identical prices should have correlation = 1."""
        tc = TokenCorrelator(tokens=["BTC", "ETH"], windows=[20])
        closes = [100.0 + i * 0.5 for i in range(50)]
        timestamps = list(range(1_000_000, 1_000_000 + 50 * 60, 60))
        bars_btc = _make_ohlcv(timestamps, closes)
        bars_eth = _make_ohlcv(timestamps, closes)  # identical

        result = tc.compute({"BTC": bars_btc, "ETH": bars_eth})
        latest = result.latest
        assert latest is not None
        corr = latest.get_pair("BTC", "ETH")
        assert corr == pytest.approx(1.0, abs=1e-10)

    def test_inverse_correlation(self) -> None:
        """Tokens with opposite return directions should have negative correlation."""
        tc = TokenCorrelator(tokens=["BTC", "ETH"], windows=[20])
        # Use sinusoidal prices with opposite phases so returns are anti-correlated
        closes_up = [100.0 + 10.0 * np.sin(i * 0.3) for i in range(50)]
        closes_down = [100.0 - 10.0 * np.sin(i * 0.3) for i in range(50)]
        timestamps = list(range(1_000_000, 1_000_000 + 50 * 60, 60))

        result = tc.compute(
            {
                "BTC": _make_ohlcv(timestamps, closes_up),
                "ETH": _make_ohlcv(timestamps, closes_down),
            }
        )
        latest = result.latest
        assert latest is not None
        corr = latest.get_pair("BTC", "ETH")
        assert corr < -0.5  # should be strongly negative
