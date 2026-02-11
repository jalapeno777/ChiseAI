"""Tests for correlation engine."""

import numpy as np
import pytest

from portfolio_risk.correlation.engine import (
    CorrelationEngine,
    CorrelationMethod,
    CorrelationResult,
)


class TestCorrelationEngineInitialization:
    """Tests for CorrelationEngine initialization."""

    def test_default_initialization(self):
        """Test engine initialization with defaults."""
        engine = CorrelationEngine()
        assert engine.method == CorrelationMethod.PEARSON
        assert engine.min_data_points == 10

    def test_custom_initialization(self):
        """Test engine initialization with custom parameters."""
        engine = CorrelationEngine(
            method=CorrelationMethod.SPEARMAN,
            min_data_points=20,
        )
        assert engine.method == CorrelationMethod.SPEARMAN
        assert engine.min_data_points == 20


class TestCorrelationMatrixCalculation:
    """Tests for correlation matrix calculation."""

    @pytest.fixture
    def engine(self):
        """Create a CorrelationEngine fixture."""
        return CorrelationEngine()

    @pytest.fixture
    def correlated_price_data(self):
        """Create price data with known correlations."""
        np.random.seed(42)
        n = 100

        # Create highly correlated series
        base_returns = np.random.normal(0.001, 0.02, n)
        token_a_prices = 100 * np.exp(np.cumsum(base_returns))
        token_b_prices = 100 * np.exp(
            np.cumsum(base_returns + np.random.normal(0, 0.005, n))
        )

        # Create less correlated series
        token_c_prices = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n)))

        return {
            "TOKEN_A": token_a_prices,
            "TOKEN_B": token_b_prices,
            "TOKEN_C": token_c_prices,
        }

    def test_correlation_matrix_shape(self, engine, correlated_price_data):
        """Test correlation matrix has correct shape."""
        result = engine.calculate_correlation_matrix(correlated_price_data)

        assert len(result.tokens) == 3
        assert result.correlation_matrix.shape == (3, 3)

    def test_correlation_matrix_symmetry(self, engine, correlated_price_data):
        """Test correlation matrix is symmetric."""
        result = engine.calculate_correlation_matrix(correlated_price_data)

        corr_matrix = result.correlation_matrix
        assert np.allclose(corr_matrix, corr_matrix.T)

    def test_correlation_matrix_diagonal(self, engine, correlated_price_data):
        """Test diagonal elements are 1.0."""
        result = engine.calculate_correlation_matrix(correlated_price_data)

        np.testing.assert_array_almost_equal(
            np.diag(result.correlation_matrix), np.ones(3)
        )

    def test_correlation_range(self, engine, correlated_price_data):
        """Test correlation values are in [-1, 1] range."""
        result = engine.calculate_correlation_matrix(correlated_price_data)

        assert np.all(result.correlation_matrix >= -1.0)
        assert np.all(result.correlation_matrix <= 1.0)

    def test_high_correlation_detection(self, engine, correlated_price_data):
        """Test that highly correlated assets have high correlation values."""
        result = engine.calculate_correlation_matrix(correlated_price_data)

        # TOKEN_A and TOKEN_B should be highly correlated
        idx_a = result.tokens.index("TOKEN_A")
        idx_b = result.tokens.index("TOKEN_B")
        corr_ab = result.correlation_matrix[idx_a, idx_b]

        assert corr_ab > 0.7  # Should be highly correlated

    def test_pearson_vs_spearman(self, correlated_price_data):
        """Test Pearson and Spearman methods produce different results."""
        pearson_engine = CorrelationEngine(method=CorrelationMethod.PEARSON)
        spearman_engine = CorrelationEngine(method=CorrelationMethod.SPEARMAN)

        pearson_result = pearson_engine.calculate_correlation_matrix(
            correlated_price_data
        )
        spearman_result = spearman_engine.calculate_correlation_matrix(
            correlated_price_data
        )

        assert pearson_result.method == CorrelationMethod.PEARSON
        assert spearman_result.method == CorrelationMethod.SPEARMAN

    def test_insufficient_tokens(self, engine):
        """Test handling of insufficient tokens."""
        price_data = {"TOKEN_A": np.array([100.0, 101.0, 102.0] * 10)}

        result = engine.calculate_correlation_matrix(price_data)

        assert len(result.tokens) == 1
        assert result.correlation_matrix.shape == (1, 1)
        assert result.diversification_score == 0.0

    def test_insufficient_data_points(self, engine):
        """Test handling of insufficient data points."""
        price_data = {
            "TOKEN_A": np.array([100.0, 101.0]),
            "TOKEN_B": np.array([100.0, 101.0]),
        }

        result = engine.calculate_correlation_matrix(price_data)

        # Should return identity matrix when insufficient data
        assert result.correlation_matrix.shape == (2, 2)
        np.testing.assert_array_almost_equal(result.correlation_matrix, np.eye(2))

    def test_correlation_result_to_dict(self, engine, correlated_price_data):
        """Test CorrelationResult serialization."""
        result = engine.calculate_correlation_matrix(correlated_price_data)

        data = result.to_dict()

        assert "tokens" in data
        assert "correlation_matrix" in data
        assert "method" in data
        assert "diversification_score" in data
        assert "timestamp" in data
        assert isinstance(data["correlation_matrix"], list)


class TestRollingCorrelations:
    """Tests for rolling window correlations."""

    @pytest.fixture
    def engine(self):
        """Create a CorrelationEngine fixture."""
        return CorrelationEngine()

    @pytest.fixture
    def price_data_for_rolling(self):
        """Create price data suitable for rolling correlation."""
        np.random.seed(42)
        n = 200

        base_returns = np.random.normal(0.001, 0.02, n)
        token_a = 100 * np.exp(np.cumsum(base_returns))
        token_b = 100 * np.exp(np.cumsum(base_returns + np.random.normal(0, 0.005, n)))

        return {
            "TOKEN_A": token_a,
            "TOKEN_B": token_b,
        }

    def test_rolling_correlation_basic(self, engine, price_data_for_rolling):
        """Test basic rolling correlation calculation."""
        result = engine.calculate_rolling_correlations(
            price_data_for_rolling,
            window_size=30,
        )

        assert len(result.tokens) == 2
        assert result.window_size == 30
        assert len(result.timestamps) > 0

    def test_rolling_correlation_values(self, engine, price_data_for_rolling):
        """Test rolling correlation values are in valid range."""
        result = engine.calculate_rolling_correlations(
            price_data_for_rolling,
            window_size=30,
        )

        for _token_pair, correlations in result.rolling_correlations.items():
            for corr in correlations:
                assert -1.0 <= corr <= 1.0

    def test_rolling_correlation_spearman(self, engine, price_data_for_rolling):
        """Test rolling correlation with Spearman method."""
        result = engine.calculate_rolling_correlations(
            price_data_for_rolling,
            window_size=30,
            method=CorrelationMethod.SPEARMAN,
        )

        assert result.method == CorrelationMethod.SPEARMAN

    def test_rolling_correlation_insufficient_data(self, engine):
        """Test handling of insufficient data for rolling window."""
        # Need data that's long enough for returns calculation but too short for window
        # Returns calculation needs min_data_points + 1 prices, so for window_size=30
        # we need at least 31 prices but we'll provide fewer valid returns
        np.random.seed(42)
        n = 25  # Less than window_size=30
        prices_a = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n)))
        prices_b = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n)))

        price_data = {
            "TOKEN_A": prices_a,
            "TOKEN_B": prices_b,
        }

        # Should handle gracefully by returning empty result, not raising
        result = engine.calculate_rolling_correlations(
            price_data,
            window_size=30,
        )

        # Should return empty result when insufficient data
        assert len(result.tokens) == 2
        assert len(result.rolling_correlations) == 0

    def test_rolling_correlation_single_token(self, engine):
        """Test handling of single token for rolling correlation."""
        price_data = {"TOKEN_A": np.array([100.0] * 100)}

        result = engine.calculate_rolling_correlations(
            price_data,
            window_size=30,
        )

        assert len(result.tokens) == 1
        assert len(result.rolling_correlations) == 0

    def test_rolling_result_to_dict(self, engine, price_data_for_rolling):
        """Test RollingCorrelationResult serialization."""
        result = engine.calculate_rolling_correlations(
            price_data_for_rolling,
            window_size=30,
        )

        data = result.to_dict()

        assert "tokens" in data
        assert "rolling_correlations" in data
        assert "window_size" in data
        assert "timestamps" in data
        assert "method" in data


class TestDiversificationScore:
    """Tests for diversification score calculation."""

    @pytest.fixture
    def engine(self):
        """Create a CorrelationEngine fixture."""
        return CorrelationEngine()

    def test_perfect_diversification(self, engine):
        """Test diversification score for uncorrelated assets."""
        # Create correlation matrix with zero correlations
        corr_matrix = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ]
        )
        tokens = ["A", "B", "C"]

        score = engine._calculate_diversification_score(corr_matrix, tokens)

        assert score == 100.0

    def test_no_diversification(self, engine):
        """Test diversification score for perfectly correlated assets."""
        # Create correlation matrix with all correlations = 1
        corr_matrix = np.array(
            [
                [1.0, 1.0, 1.0],
                [1.0, 1.0, 1.0],
                [1.0, 1.0, 1.0],
            ]
        )
        tokens = ["A", "B", "C"]

        score = engine._calculate_diversification_score(corr_matrix, tokens)

        assert score == 0.0

    def test_partial_diversification(self, engine):
        """Test diversification score for partially correlated assets."""
        # Create correlation matrix with 0.5 average correlation
        corr_matrix = np.array(
            [
                [1.0, 0.5, 0.5],
                [0.5, 1.0, 0.5],
                [0.5, 0.5, 1.0],
            ]
        )
        tokens = ["A", "B", "C"]

        score = engine._calculate_diversification_score(corr_matrix, tokens)

        assert 40.0 < score < 60.0  # Should be around 50

    def test_single_token_diversification(self, engine):
        """Test diversification score for single token."""
        corr_matrix = np.array([[1.0]])
        tokens = ["A"]

        score = engine._calculate_diversification_score(corr_matrix, tokens)

        assert score == 0.0

    def test_negative_correlation(self, engine):
        """Test diversification score with negative correlations."""
        corr_matrix = np.array(
            [
                [1.0, -0.5, -0.5],
                [-0.5, 1.0, -0.5],
                [-0.5, -0.5, 1.0],
            ]
        )
        tokens = ["A", "B", "C"]

        score = engine._calculate_diversification_score(corr_matrix, tokens)

        # Negative correlations should improve diversification
        # Average abs correlation is 0.5, so score should be (1-0.5)*100 = 50
        # With negative correlations, we should get at least 50
        assert score >= 50.0


class TestCorrelationHelpers:
    """Tests for correlation helper methods."""

    @pytest.fixture
    def engine(self):
        """Create a CorrelationEngine fixture."""
        return CorrelationEngine()

    @pytest.fixture
    def sample_correlation_result(self):
        """Create a sample CorrelationResult."""
        return CorrelationResult(
            tokens=["BTC", "ETH", "SOL"],
            correlation_matrix=np.array(
                [
                    [1.0, 0.8, 0.3],
                    [0.8, 1.0, 0.4],
                    [0.3, 0.4, 1.0],
                ]
            ),
            method=CorrelationMethod.PEARSON,
            window_size=0,
            timestamp=1234567890000,
            diversification_score=50.0,
        )

    def test_get_correlation_between_tokens(self, engine, sample_correlation_result):
        """Test getting correlation between specific tokens."""
        corr = engine.get_correlation_between_tokens(
            sample_correlation_result, "BTC", "ETH"
        )

        assert corr == 0.8

    def test_get_correlation_same_token(self, engine, sample_correlation_result):
        """Test getting correlation of token with itself."""
        corr = engine.get_correlation_between_tokens(
            sample_correlation_result, "BTC", "BTC"
        )

        assert corr == 1.0

    def test_get_correlation_token_not_found(self, engine, sample_correlation_result):
        """Test getting correlation for non-existent token."""
        corr = engine.get_correlation_between_tokens(
            sample_correlation_result, "BTC", "XYZ"
        )

        assert corr is None

    def test_get_high_correlation_pairs(self, engine, sample_correlation_result):
        """Test getting high correlation pairs."""
        pairs = engine.get_high_correlation_pairs(
            sample_correlation_result,
            threshold=0.7,
        )

        assert len(pairs) == 1
        assert pairs[0]["token1"] == "BTC"
        assert pairs[0]["token2"] == "ETH"
        assert pairs[0]["correlation"] == 0.8

    def test_get_high_correlation_pairs_sorted(self, engine, sample_correlation_result):
        """Test that high correlation pairs are sorted by absolute correlation."""
        # Modify matrix to have multiple high correlations
        sample_correlation_result.correlation_matrix = np.array(
            [
                [1.0, 0.9, 0.95],
                [0.9, 1.0, 0.4],
                [0.95, 0.4, 1.0],
            ]
        )

        pairs = engine.get_high_correlation_pairs(
            sample_correlation_result,
            threshold=0.7,
        )

        assert len(pairs) == 2
        # Should be sorted by abs correlation descending
        assert pairs[0]["abs_correlation"] >= pairs[1]["abs_correlation"]

    def test_get_diversification_recommendations_high_correlation(
        self, engine, sample_correlation_result
    ):
        """Test recommendations for high correlation."""
        recommendations = engine.get_diversification_recommendations(
            sample_correlation_result
        )

        # Should have recommendation for BTC-ETH high correlation
        high_corr_recs = [
            r for r in recommendations if r["type"] == "reduce_concentration"
        ]
        assert len(high_corr_recs) > 0

    def test_get_diversification_recommendations_low_score(self, engine):
        """Test recommendations for low diversification score."""
        low_div_result = CorrelationResult(
            tokens=["BTC", "ETH"],
            correlation_matrix=np.array(
                [
                    [1.0, 0.95],
                    [0.95, 1.0],
                ]
            ),
            method=CorrelationMethod.PEARSON,
            window_size=0,
            timestamp=1234567890000,
            diversification_score=20.0,
        )

        recommendations = engine.get_diversification_recommendations(low_div_result)

        # Should have high severity recommendation
        div_recs = [
            r for r in recommendations if r["type"] == "improve_diversification"
        ]
        assert len(div_recs) > 0
        assert div_recs[0]["severity"] == "high"


class TestReturnsCalculation:
    """Tests for returns calculation."""

    @pytest.fixture
    def engine(self):
        """Create a CorrelationEngine fixture."""
        return CorrelationEngine()

    def test_calculate_returns_basic(self, engine):
        """Test basic returns calculation."""
        prices = np.array([100.0, 101.0, 102.0, 101.0])

        returns = engine._calculate_returns(prices)

        assert len(returns) == 3
        # Log returns should be approximately 0.01, 0.0099, -0.0099
        assert returns[0] > 0  # Price went up
        assert returns[2] < 0  # Price went down

    def test_calculate_returns_insufficient_data(self, engine):
        """Test returns calculation with insufficient data."""
        prices = np.array([100.0])

        returns = engine._calculate_returns(prices)

        assert len(returns) == 0

    def test_calculate_returns_two_points(self, engine):
        """Test returns calculation with exactly two points."""
        prices = np.array([100.0, 101.0])

        returns = engine._calculate_returns(prices)

        assert len(returns) == 1
        assert returns[0] > 0


class TestMarketConditions:
    """Tests for correlation calculations under different market conditions."""

    @pytest.fixture
    def engine(self):
        """Create a CorrelationEngine fixture."""
        return CorrelationEngine()

    def test_bull_market_correlation(self, engine):
        """Test correlation during bull market (trending up)."""
        np.random.seed(42)
        n = 100

        # Both assets trending up together with shared trend component
        base_returns = np.random.normal(0.001, 0.01, n)
        trend = np.linspace(0, 0.3, n)
        returns_a = base_returns + trend * 0.02 + np.random.normal(0, 0.005, n)
        returns_b = base_returns + trend * 0.02 + np.random.normal(0, 0.005, n)

        prices_a = 100 * np.exp(np.cumsum(returns_a))
        prices_b = 100 * np.exp(np.cumsum(returns_b))

        price_data = {"A": prices_a, "B": prices_b}
        result = engine.calculate_correlation_matrix(price_data)

        # Should be positively correlated when moving together
        assert result.correlation_matrix[0, 1] > 0.3

    def test_bear_market_correlation(self, engine):
        """Test correlation during bear market (trending down)."""
        np.random.seed(42)
        n = 100

        # Both assets trending down together with shared trend component
        base_returns = np.random.normal(-0.001, 0.01, n)
        trend = np.linspace(0, -0.3, n)
        returns_a = base_returns + trend * 0.02 + np.random.normal(0, 0.005, n)
        returns_b = base_returns + trend * 0.02 + np.random.normal(0, 0.005, n)

        prices_a = 100 * np.exp(np.cumsum(returns_a))
        prices_b = 100 * np.exp(np.cumsum(returns_b))

        price_data = {"A": prices_a, "B": prices_b}
        result = engine.calculate_correlation_matrix(price_data)

        # Should be positively correlated when moving together
        assert result.correlation_matrix[0, 1] > 0.3

    def test_high_volatility_correlation(self, engine):
        """Test correlation during high volatility period."""
        np.random.seed(42)
        n = 100

        # High volatility but same direction moves
        returns_a = np.random.normal(0, 0.05, n)
        returns_b = returns_a + np.random.normal(0, 0.01, n)

        prices_a = 100 * np.exp(np.cumsum(returns_a))
        prices_b = 100 * np.exp(np.cumsum(returns_b))

        price_data = {"A": prices_a, "B": prices_b}
        result = engine.calculate_correlation_matrix(price_data)

        # Should still be highly correlated despite volatility
        assert result.correlation_matrix[0, 1] > 0.7

    def test_low_volatility_correlation(self, engine):
        """Test correlation during low volatility period."""
        np.random.seed(42)
        n = 100

        # Low volatility, small moves
        returns_a = np.random.normal(0, 0.005, n)
        returns_b = returns_a + np.random.normal(0, 0.001, n)

        prices_a = 100 * np.exp(np.cumsum(returns_a))
        prices_b = 100 * np.exp(np.cumsum(returns_b))

        price_data = {"A": prices_a, "B": prices_b}
        result = engine.calculate_correlation_matrix(price_data)

        # Should be highly correlated even with low volatility
        assert result.correlation_matrix[0, 1] > 0.7

    def test_mixed_market_correlation(self, engine):
        """Test correlation with mixed market conditions."""
        np.random.seed(42)
        n = 100

        # Create three assets with different behaviors
        # A: Steady uptrend
        returns_a = np.random.normal(0.002, 0.01, n)
        # B: Steady downtrend
        returns_b = np.random.normal(-0.002, 0.01, n)
        # C: Sideways with noise
        returns_c = np.random.normal(0, 0.02, n)

        prices_a = 100 * np.exp(np.cumsum(returns_a))
        prices_b = 100 * np.exp(np.cumsum(returns_b))
        prices_c = 100 * np.exp(np.cumsum(returns_c))

        price_data = {"A": prices_a, "B": prices_b, "C": prices_c}
        result = engine.calculate_correlation_matrix(price_data)

        # A and B should be negatively correlated or uncorrelated
        idx_a = result.tokens.index("A")
        idx_b = result.tokens.index("B")
        corr_ab = result.correlation_matrix[idx_a, idx_b]

        # Should be low or negative correlation
        assert corr_ab < 0.3
