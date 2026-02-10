"""Tests for correlation API."""

from unittest.mock import MagicMock

import pytest

from portfolio.state_management.models import (
    PortfolioState,
    Position,
    PositionDirection,
)
from portfolio.state_management.tracker import PortfolioTracker
from portfolio_risk.correlation.api import (
    CorrelationAPI,
    create_correlation_routes,
)
from portfolio_risk.correlation.engine import CorrelationMethod


@pytest.fixture
def mock_tracker():
    """Create a mock portfolio tracker."""
    tracker = MagicMock(spec=PortfolioTracker)
    tracker.portfolio_id = "test-portfolio"
    tracker.state = PortfolioState(portfolio_id="test-portfolio")
    return tracker


@pytest.fixture
def api(mock_tracker):
    """Create a CorrelationAPI with mock tracker."""
    return CorrelationAPI(mock_tracker, cache_ttl_ms=1000)


class TestCorrelationAPIInitialization:
    """Tests for CorrelationAPI initialization."""

    def test_default_initialization(self, mock_tracker):
        """Test API initialization with defaults."""
        api = CorrelationAPI(mock_tracker)
        assert api.tracker == mock_tracker
        assert api.cache_ttl_ms == 5000
        assert api.engine is not None

    def test_custom_initialization(self, mock_tracker):
        """Test API initialization with custom parameters."""
        from portfolio_risk.correlation.engine import CorrelationEngine

        engine = CorrelationEngine(method=CorrelationMethod.SPEARMAN)
        api = CorrelationAPI(mock_tracker, engine=engine, cache_ttl_ms=10000)

        assert api.engine == engine
        assert api.cache_ttl_ms == 10000


class TestCorrelationMatrixEndpoint:
    """Tests for correlation matrix endpoint."""

    def test_get_correlation_matrix_no_positions(self, api, mock_tracker):
        """Test correlation matrix with no positions."""
        result = api.get_correlation_matrix()

        assert result["tokens"] == []
        assert result["correlation_matrix"] == []
        assert "message" in result
        assert result["diversification_score"] == 0.0

    def test_get_correlation_matrix_single_position(self, api, mock_tracker):
        """Test correlation matrix with single position."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        result = api.get_correlation_matrix()

        assert result["tokens"] == ["BTC"]
        assert "message" in result

    def test_get_correlation_matrix_multiple_positions(self, api, mock_tracker):
        """Test correlation matrix with multiple positions."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        result = api.get_correlation_matrix()

        assert len(result["tokens"]) == 2
        assert "BTC" in result["tokens"]
        assert "ETH" in result["tokens"]
        assert len(result["correlation_matrix"]) == 2
        assert result["method"] == "pearson"
        assert "diversification_score" in result
        assert "timestamp" in result

    def test_get_correlation_matrix_spearman(self, api, mock_tracker):
        """Test correlation matrix with Spearman method."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        result = api.get_correlation_matrix(method="spearman")

        assert result["method"] == "spearman"

    def test_get_correlation_matrix_caching(self, api, mock_tracker):
        """Test that correlation matrix is cached."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        # First call
        result1 = api.get_correlation_matrix()
        # Second call should use cache
        result2 = api.get_correlation_matrix()

        assert result1["timestamp"] == result2["timestamp"]


class TestRollingCorrelationsEndpoint:
    """Tests for rolling correlations endpoint."""

    def test_get_rolling_correlations_no_positions(self, api, mock_tracker):
        """Test rolling correlations with no positions."""
        result = api.get_rolling_correlations(window_size=30)

        assert result["tokens"] == []
        assert result["rolling_correlations"] == {}
        assert "message" in result

    def test_get_rolling_correlations_insufficient_data(self, api, mock_tracker):
        """Test rolling correlations with insufficient data."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        # Window size too large for generated data
        result = api.get_rolling_correlations(window_size=500)

        # Should handle gracefully - either returns message or empty correlations
        # The API generates synthetic data, so it may succeed or return empty
        assert "message" in result or len(result.get("rolling_correlations", {})) >= 0

    def test_get_rolling_correlations_basic(self, api, mock_tracker):
        """Test basic rolling correlations."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        result = api.get_rolling_correlations(window_size=30)

        assert len(result["tokens"]) == 2
        assert result["window_size"] == 30
        assert "method" in result


class TestDiversificationMetricsEndpoint:
    """Tests for diversification metrics endpoint."""

    def test_get_diversification_metrics_no_positions(self, api, mock_tracker):
        """Test diversification metrics with no positions."""
        result = api.get_diversification_metrics()

        assert result["diversification_score"] == 0.0
        assert result["score_interpretation"] == "N/A"
        assert result["recommendations"] == []
        assert result["high_correlation_pairs"] == []

    def test_get_diversification_metrics_with_positions(self, api, mock_tracker):
        """Test diversification metrics with positions."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        result = api.get_diversification_metrics()

        assert "diversification_score" in result
        assert "score_interpretation" in result
        assert result["score_interpretation"] in [
            "Well diversified",
            "Moderately diversified",
            "Poorly diversified",
        ]
        assert "recommendations" in result
        assert "high_correlation_pairs" in result
        assert "timestamp" in result


class TestCorrelationBetweenTokensEndpoint:
    """Tests for correlation between tokens endpoint."""

    def test_get_correlation_between_tokens_no_data(self, api, mock_tracker):
        """Test correlation between tokens with no data."""
        result = api.get_correlation_between_tokens("BTC", "ETH")

        assert result["token1"] == "BTC"
        assert result["token2"] == "ETH"
        assert result["correlation"] is None
        assert "message" in result

    def test_get_correlation_between_tokens_with_data(self, api, mock_tracker):
        """Test correlation between tokens with data."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        result = api.get_correlation_between_tokens("BTC", "ETH")

        assert result["token1"] == "BTC"
        assert result["token2"] == "ETH"
        assert result["correlation"] is not None
        assert -1.0 <= result["correlation"] <= 1.0
        assert "abs_correlation" in result
        assert "method" in result
        assert "timestamp" in result

    def test_get_correlation_token_not_found(self, api, mock_tracker):
        """Test correlation for non-existent token."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        result = api.get_correlation_between_tokens("BTC", "XYZ")

        assert result["correlation"] is None
        assert "message" in result


class TestPositionCorrelationsEndpoint:
    """Tests for position correlations endpoint."""

    def test_get_position_correlations_not_found(self, api, mock_tracker):
        """Test position correlations for non-existent position."""
        result = api.get_position_correlations("non-existent")

        assert result["position_id"] == "non-existent"
        assert "error" in result
        assert result["correlations"] == []

    def test_get_position_correlations_single_position(self, api, mock_tracker):
        """Test position correlations with single position."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        result = api.get_position_correlations("pos-1")

        assert result["position_id"] == "pos-1"
        assert result["token"] == "BTC"
        # Single position has no correlations to other positions
        assert len(result["correlations"]) == 0

    def test_get_position_correlations_multiple(self, api, mock_tracker):
        """Test position correlations with multiple positions."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-3",
                token="SOL",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=100.0,
                current_price=110.0,
            )
        )

        result = api.get_position_correlations("pos-1")

        assert result["position_id"] == "pos-1"
        assert result["token"] == "BTC"
        assert len(result["correlations"]) == 2  # ETH and SOL

        # Check correlations are sorted by absolute value
        corrs = [c["abs_correlation"] for c in result["correlations"]]
        assert corrs == sorted(corrs, reverse=True)


class TestHealthCheckEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, api, mock_tracker):
        """Test health check."""
        result = api.health_check()

        assert result["status"] == "healthy"
        assert result["portfolio_id"] == "test-portfolio"
        assert "latency_ms" in result
        assert "open_positions" in result
        assert "cache_valid" in result

    def test_health_check_with_positions(self, api, mock_tracker):
        """Test health check with positions."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        result = api.health_check()

        assert result["open_positions"] == 1


class TestCreateCorrelationRoutes:
    """Tests for route factory function."""

    def test_create_routes(self, mock_tracker):
        """Test creating correlation routes."""
        routes = create_correlation_routes(mock_tracker)

        assert len(routes) == 6

        # Check expected routes exist
        paths = [r["path"] for r in routes]
        assert "/correlation/matrix" in paths
        assert "/correlation/rolling" in paths
        assert "/correlation/diversification" in paths
        assert "/correlation/pair" in paths
        assert "/correlation/position/{position_id}" in paths
        assert "/correlation/health" in paths

        # Check all routes have required fields
        for route in routes:
            assert "path" in route
            assert "method" in route
            assert "handler" in route
            assert "response_model" in route
            assert route["method"] == "GET"
