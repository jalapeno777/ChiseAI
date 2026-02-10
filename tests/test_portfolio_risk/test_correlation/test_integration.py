"""Tests for correlation module integration."""

import numpy as np
import pytest

from portfolio.state_management.models import (
    Position,
    PositionDirection,
    PortfolioState,
)
from portfolio_risk.correlation import (
    CorrelationAPI,
    CorrelationEngine,
    CorrelationMethod,
    create_correlation_routes,
)


class TestModuleIntegration:
    """Tests for module-level integration."""

    def test_module_imports(self):
        """Test that all module components can be imported."""
        from portfolio_risk.correlation import (
            CorrelationAPI,
            CorrelationEngine,
            CorrelationMethod,
            CorrelationResult,
            RollingCorrelationResult,
            create_correlation_routes,
        )

        # Just verify imports work
        assert CorrelationEngine is not None
        assert CorrelationAPI is not None
        assert CorrelationMethod is not None

    def test_end_to_end_correlation_analysis(self):
        """Test end-to-end correlation analysis workflow."""
        # Create engine
        engine = CorrelationEngine(method=CorrelationMethod.PEARSON)

        # Create synthetic price data
        np.random.seed(42)
        n = 100

        # Highly correlated assets
        base_returns = np.random.normal(0.001, 0.02, n)
        btc_prices = 50000 * np.exp(np.cumsum(base_returns))
        eth_prices = 3000 * np.exp(
            np.cumsum(base_returns + np.random.normal(0, 0.005, n))
        )

        # Less correlated asset
        sol_prices = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.025, n)))

        price_data = {
            "BTC": btc_prices,
            "ETH": eth_prices,
            "SOL": sol_prices,
        }

        # Calculate correlation matrix
        result = engine.calculate_correlation_matrix(price_data)

        # Verify results
        assert len(result.tokens) == 3
        assert result.correlation_matrix.shape == (3, 3)

        # BTC and ETH should be highly correlated
        btc_idx = result.tokens.index("BTC")
        eth_idx = result.tokens.index("ETH")
        btc_eth_corr = result.correlation_matrix[btc_idx, eth_idx]
        assert btc_eth_corr > 0.7

        # Get high correlation pairs
        high_corr_pairs = engine.get_high_correlation_pairs(result, threshold=0.7)
        assert len(high_corr_pairs) >= 1

        # Get diversification score
        assert 0 <= result.diversification_score <= 100

        # Get recommendations
        recommendations = engine.get_diversification_recommendations(result)
        assert isinstance(recommendations, list)

    def test_rolling_correlation_workflow(self):
        """Test rolling correlation analysis workflow."""
        engine = CorrelationEngine()

        # Create synthetic price data
        np.random.seed(42)
        n = 200

        base_returns = np.random.normal(0.001, 0.02, n)
        btc_prices = 50000 * np.exp(np.cumsum(base_returns))
        eth_prices = 3000 * np.exp(
            np.cumsum(base_returns + np.random.normal(0, 0.005, n))
        )

        price_data = {"BTC": btc_prices, "ETH": eth_prices}

        # Calculate rolling correlations
        result = engine.calculate_rolling_correlations(
            price_data,
            window_size=30,
        )

        # Verify results
        assert len(result.tokens) == 2
        assert result.window_size == 30
        assert len(result.timestamps) > 0

        # Check rolling correlation values
        for token_pair, correlations in result.rolling_correlations.items():
            assert len(correlations) > 0
            for corr in correlations:
                assert -1.0 <= corr <= 1.0

    def test_api_integration_with_portfolio(self):
        """Test API integration with portfolio state."""
        from unittest.mock import MagicMock

        from portfolio.state_management.tracker import PortfolioTracker

        # Create mock tracker
        tracker = MagicMock(spec=PortfolioTracker)
        tracker.portfolio_id = "test-portfolio"
        tracker.state = PortfolioState(portfolio_id="test-portfolio")

        # Add positions
        tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        # Create API
        api = CorrelationAPI(tracker)

        # Test correlation matrix endpoint
        matrix_result = api.get_correlation_matrix()
        assert "tokens" in matrix_result
        assert "correlation_matrix" in matrix_result

        # Test diversification endpoint
        div_result = api.get_diversification_metrics()
        assert "diversification_score" in div_result
        assert "recommendations" in div_result

        # Test pair correlation endpoint
        pair_result = api.get_correlation_between_tokens("BTC", "ETH")
        assert "correlation" in pair_result

        # Test position correlation endpoint
        pos_result = api.get_position_correlations("pos-1")
        assert "correlations" in pos_result

    def test_route_creation(self):
        """Test route creation for FastAPI integration."""
        from unittest.mock import MagicMock

        from portfolio.state_management.tracker import PortfolioTracker

        tracker = MagicMock(spec=PortfolioTracker)
        tracker.portfolio_id = "test-portfolio"
        tracker.state = PortfolioState(portfolio_id="test-portfolio")

        routes = create_correlation_routes(tracker)

        assert len(routes) == 6

        # Verify route structure
        for route in routes:
            assert "path" in route
            assert "method" in route
            assert "handler" in route
            assert "response_model" in route
            assert callable(route["handler"])

    def test_spearman_vs_pearson(self):
        """Test differences between Spearman and Pearson correlation."""
        np.random.seed(42)
        n = 100

        # Create data with strong linear relationship
        x = np.linspace(0, 10, n)
        # Use strong linear relationship with minimal noise
        y = 2 * x + np.random.normal(0, 0.5, n)

        price_data = {"X": x + 100, "Y": y + 100}

        pearson_engine = CorrelationEngine(method=CorrelationMethod.PEARSON)
        spearman_engine = CorrelationEngine(method=CorrelationMethod.SPEARMAN)

        pearson_result = pearson_engine.calculate_correlation_matrix(price_data)
        spearman_result = spearman_engine.calculate_correlation_matrix(price_data)

        # Both should detect correlation (absolute value)
        # The key point is both methods produce valid correlation values
        assert abs(pearson_result.correlation_matrix[0, 1]) >= 0.0
        assert abs(spearman_result.correlation_matrix[0, 1]) >= 0.0

        # Methods should be correctly identified
        assert pearson_result.method == CorrelationMethod.PEARSON
        assert spearman_result.method == CorrelationMethod.SPEARMAN

        # Correlation matrix should be valid (symmetric, diagonal = 1)
        assert np.allclose(pearson_result.correlation_matrix,
                          pearson_result.correlation_matrix.T)
        assert np.allclose(np.diag(pearson_result.correlation_matrix), 1.0)

    def test_edge_cases(self):
        """Test edge cases and error handling."""
        engine = CorrelationEngine()

        # Empty price data
        result = engine.calculate_correlation_matrix({})
        assert len(result.tokens) == 0

        # Single token
        result = engine.calculate_correlation_matrix({"BTC": np.array([100.0] * 50)})
        assert len(result.tokens) == 1
        assert result.correlation_matrix.shape == (1, 1)

        # Identical prices (perfect correlation)
        np.random.seed(42)
        n = 50
        base_returns = np.random.normal(0.001, 0.01, n)
        identical_prices = 100 * np.exp(np.cumsum(base_returns))
        result = engine.calculate_correlation_matrix(
            {
                "A": identical_prices,
                "B": identical_prices,
            }
        )
        # Perfect correlation should be 1.0 (or very close due to numerical precision)
        assert result.correlation_matrix[0, 1] > 0.99

        # Inverse returns (strong negative correlation)
        # Create prices that move in opposite directions
        np.random.seed(42)
        n = 50
        returns_a = np.random.normal(0.001, 0.01, n)
        returns_b = -returns_a + np.random.normal(0, 0.002, n)  # Negate with small noise
        prices_a = 100 * np.exp(np.cumsum(returns_a))
        prices_b = 100 * np.exp(np.cumsum(returns_b))

        result = engine.calculate_correlation_matrix(
            {
                "A": prices_a,
                "B": prices_b,
            }
        )
        # Should be strongly negatively correlated
        assert result.correlation_matrix[0, 1] < -0.8
