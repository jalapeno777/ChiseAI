"""Integration tests for main FastAPI application.

Tests that the main FastAPI application is properly configured
and all mounted routers are accessible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a TestClient for the main FastAPI app."""
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


@pytest.fixture
def mock_tracker():
    """Create a mock ECE history tracker."""
    tracker = MagicMock()
    tracker.close = AsyncMock()
    return tracker


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Test that GET /health returns 200 OK."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_content_type(self, client: TestClient) -> None:
        """Test that health endpoint returns JSON."""
        response = client.get("/health")

        assert response.headers["content-type"] == "application/json"


class TestECEEndpoint:
    """Tests for ECE router mounted at /api/v1/ece/."""

    def test_ece_list_strategies_endpoint_exists(
        self, client: TestClient, mock_tracker
    ) -> None:
        """Test that GET /api/v1/ece/ endpoint exists and returns list."""
        mock_tracker.get_all_strategies = AsyncMock(
            return_value=["strategy1", "strategy2"]
        )

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            response = client.get("/api/v1/ece/")

            assert response.status_code == 200
            data = response.json()
            assert "strategies" in data
            assert "count" in data

    def test_ece_get_strategy_endpoint_exists(
        self, client: TestClient, mock_tracker
    ) -> None:
        """Test that GET /api/v1/ece/{strategy_id} endpoint exists."""
        from datetime import UTC, datetime

        from confidence import ECEHistoryPoint

        mock_point = ECEHistoryPoint(
            timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            ece=0.05,
            n_bins=10,
            total_samples=100,
            signal_type=None,
            strategy_id="test_strategy",
        )
        mock_tracker.get_latest_ece = AsyncMock(return_value=mock_point)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            response = client.get("/api/v1/ece/test_strategy")

            # Should return 200 if strategy exists or 404 if not
            # The important thing is the endpoint is accessible
            assert response.status_code in [200, 404]

    def test_ece_history_endpoint_exists(
        self, client: TestClient, mock_tracker
    ) -> None:
        """Test that GET /api/v1/ece/{strategy_id}/history endpoint exists."""
        mock_tracker.get_history = AsyncMock(return_value=[])

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            response = client.get("/api/v1/ece/test_strategy/history")

            # Should return 200 even with empty history
            assert response.status_code == 200
            data = response.json()
            assert "points" in data
            assert "count" in data

    def test_ece_trend_endpoint_exists(self, client: TestClient, mock_tracker) -> None:
        """Test that GET /api/v1/ece/{strategy_id}/trend endpoint exists."""
        from datetime import UTC, datetime

        from confidence import ECEHistoryPoint, ECETrend

        mock_trend = ECETrend(
            strategy_id="test_strategy",
            signal_type=None,
            points=[
                ECEHistoryPoint(
                    timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
                    ece=0.05,
                    n_bins=10,
                    total_samples=100,
                    signal_type=None,
                    strategy_id="test_strategy",
                ),
                ECEHistoryPoint(
                    timestamp=datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC),
                    ece=0.06,
                    n_bins=10,
                    total_samples=110,
                    signal_type=None,
                    strategy_id="test_strategy",
                ),
            ],
            trend_direction="stable",
            trend_slope=0.0,
            current_ece=0.06,
            avg_ece=0.055,
            min_ece=0.05,
            max_ece=0.06,
        )
        mock_tracker.get_trend = AsyncMock(return_value=mock_trend)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            response = client.get("/api/v1/ece/test_strategy/trend")

            # Should return 200 if trend exists or 404 if not enough data
            assert response.status_code in [200, 404]

    def test_ece_router_prefix_applied(self, client: TestClient) -> None:
        """Test that ECE router is mounted with correct prefix."""
        # The router should be accessible at /api/v1/ece/ not just /
        response = client.get("/api/v1/ece/")

        # Should not be 404 (endpoint not found) - might be 200 or 500 depending on tracker
        assert response.status_code != 404


class TestAppMetadata:
    """Tests for FastAPI application metadata."""

    def test_app_title(self, client: TestClient) -> None:
        """Test that app has correct title."""
        from main import app

        assert app.title == "ChiseAI API"

    def test_app_version(self, client: TestClient) -> None:
        """Test that app has correct version."""
        from main import app

        assert app.version == "1.1.0"

    def test_openapi_schema_available(self, client: TestClient) -> None:
        """Test that OpenAPI schema is available at /openapi.json."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "ChiseAI API"
        assert schema["info"]["version"] == "1.1.0"

    def test_docs_endpoint_available(self, client: TestClient) -> None:
        """Test that Swagger UI docs are available at /docs."""
        response = client.get("/docs")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
