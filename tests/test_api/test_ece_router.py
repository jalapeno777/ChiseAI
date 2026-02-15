"""Tests for ECE API router.

Tests cover:
- GET /api/v1/ece/{strategy_id} - Get latest ECE
- GET /api/v1/ece/{strategy_id}/history - Get ECE history
- GET /api/v1/ece/{strategy_id}/trend - Get trend analysis
- GET /api/v1/ece/ - List all strategies with ECE data
- Error handling
- Query parameter filtering
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.ece_router import router as ece_router
from confidence import ECEHistoryPoint, ECETrend, SignalType

if TYPE_CHECKING:
    pass


# Create test app
app = FastAPI()
app.include_router(ece_router)
client = TestClient(app)


@pytest.fixture
def mock_tracker():
    """Create a mock ECEHistoryTracker."""
    with patch("api.ece_router.get_ece_tracker") as mock_get_tracker:
        mock_tracker = AsyncMock()
        mock_get_tracker.return_value = mock_tracker
        yield mock_tracker


@pytest.fixture
def sample_history_point():
    """Create a sample ECE history point."""
    return ECEHistoryPoint(
        timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        ece=0.05,
        n_bins=10,
        total_samples=100,
        signal_type=SignalType.ENTRY,
        strategy_id="test_strategy",
    )


@pytest.fixture
def sample_trend():
    """Create a sample ECE trend."""
    points = [
        ECEHistoryPoint(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
            ece=0.1 - i * 0.005,
            n_bins=10,
            total_samples=100,
            signal_type=SignalType.ENTRY,
            strategy_id="test_strategy",
        )
        for i in range(10)
    ]
    return ECETrend(
        strategy_id="test_strategy",
        signal_type=SignalType.ENTRY,
        points=points,
        trend_direction="improving",
        trend_slope=-0.005,
        current_ece=0.055,
        avg_ece=0.0775,
        min_ece=0.055,
        max_ece=0.1,
    )


class TestGetLatestECE:
    """Tests for GET /api/v1/ece/{strategy_id}"""

    def test_get_latest_ece_success(self, mock_tracker, sample_history_point):
        """Test successful retrieval of latest ECE."""
        mock_tracker.get_latest_ece.return_value = sample_history_point

        response = client.get("/api/v1/ece/test_strategy")

        assert response.status_code == 200
        data = response.json()
        assert data["ece"] == 0.05
        assert data["n_bins"] == 10
        assert data["total_samples"] == 100
        assert data["signal_type"] == "entry"
        assert data["is_well_calibrated"] is True

        mock_tracker.get_latest_ece.assert_called_once_with(
            strategy_id="test_strategy",
            signal_type=None,
        )
        mock_tracker.close.assert_called_once()

    def test_get_latest_ece_with_signal_type(self, mock_tracker, sample_history_point):
        """Test retrieval with signal type filter."""
        mock_tracker.get_latest_ece.return_value = sample_history_point

        response = client.get("/api/v1/ece/test_strategy?signal_type=exit")

        assert response.status_code == 200
        mock_tracker.get_latest_ece.assert_called_once_with(
            strategy_id="test_strategy",
            signal_type=SignalType.EXIT,
        )

    def test_get_latest_ece_not_found(self, mock_tracker):
        """Test 404 when strategy has no ECE data."""
        mock_tracker.get_latest_ece.return_value = None

        response = client.get("/api/v1/ece/unknown_strategy")

        assert response.status_code == 404
        assert "No ECE data found" in response.json()["detail"]

    def test_get_latest_ece_invalid_signal_type(self, mock_tracker):
        """Test 400 for invalid signal type."""
        response = client.get("/api/v1/ece/test_strategy?signal_type=invalid")

        assert response.status_code == 400
        assert "Invalid signal_type" in response.json()["detail"]

    def test_get_latest_ece_internal_error(self, mock_tracker):
        """Test 500 on internal error."""
        mock_tracker.get_latest_ece.side_effect = Exception("Database error")

        response = client.get("/api/v1/ece/test_strategy")

        assert response.status_code == 500
        assert "Internal error" in response.json()["detail"]


class TestGetECEHistory:
    """Tests for GET /api/v1/ece/{strategy_id}/history"""

    def test_get_history_success(self, mock_tracker):
        """Test successful retrieval of ECE history."""
        history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
                ece=0.05 + i * 0.01,
                n_bins=10,
                total_samples=100,
                signal_type=SignalType.ENTRY,
                strategy_id="test_strategy",
            )
            for i in range(5)
        ]
        mock_tracker.get_history.return_value = history

        response = client.get("/api/v1/ece/test_strategy/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
        assert data[0]["ece"] == 0.05
        assert data[0]["signal_type"] == "entry"

    def test_get_history_with_days_param(self, mock_tracker):
        """Test history retrieval with days parameter."""
        mock_tracker.get_history.return_value = []

        response = client.get("/api/v1/ece/test_strategy/history?days=7")

        assert response.status_code == 404  # Empty history returns 404
        mock_tracker.get_history.assert_called_once_with(
            strategy_id="test_strategy",
            signal_type=None,
            days=7,
        )

    def test_get_history_days_validation(self, mock_tracker):
        """Test days parameter validation."""
        # Too few days
        response = client.get("/api/v1/ece/test_strategy/history?days=0")
        assert response.status_code == 422

        # Too many days
        response = client.get("/api/v1/ece/test_strategy/history?days=366")
        assert response.status_code == 422

    def test_get_history_with_signal_type_filter(self, mock_tracker):
        """Test history with signal type filter."""
        mock_tracker.get_history.return_value = []

        response = client.get("/api/v1/ece/test_strategy/history?signal_type=sl")

        mock_tracker.get_history.assert_called_once_with(
            strategy_id="test_strategy",
            signal_type=SignalType.STOP_LOSS,
            days=30,
        )

    def test_get_history_not_found(self, mock_tracker):
        """Test 404 when no history exists."""
        mock_tracker.get_history.return_value = []

        response = client.get("/api/v1/ece/unknown_strategy/history")

        assert response.status_code == 404
        assert "No ECE history found" in response.json()["detail"]


class TestGetECETrend:
    """Tests for GET /api/v1/ece/{strategy_id}/trend"""

    def test_get_trend_success(self, mock_tracker, sample_trend):
        """Test successful retrieval of ECE trend."""
        mock_tracker.get_trend.return_value = sample_trend

        response = client.get("/api/v1/ece/test_strategy/trend")

        assert response.status_code == 200
        data = response.json()
        assert data["strategy_id"] == "test_strategy"
        assert data["signal_type"] == "entry"
        assert data["trend_direction"] == "improving"
        assert data["trend_slope"] == -0.005
        assert data["current_ece"] == 0.055
        assert data["avg_ece"] == 0.0775
        assert data["min_ece"] == 0.055
        assert data["max_ece"] == 0.1
        assert data["data_points"] == 10

    def test_get_trend_with_days_param(self, mock_tracker, sample_trend):
        """Test trend with days parameter."""
        mock_tracker.get_trend.return_value = sample_trend

        response = client.get("/api/v1/ece/test_strategy/trend?days=60")

        assert response.status_code == 200
        mock_tracker.get_trend.assert_called_once_with(
            strategy_id="test_strategy",
            signal_type=None,
            days=60,
        )

    def test_get_trend_days_validation(self, mock_tracker):
        """Test days parameter validation for trend endpoint."""
        # Too few days
        response = client.get("/api/v1/ece/test_strategy/trend?days=6")
        assert response.status_code == 422

        # Too many days
        response = client.get("/api/v1/ece/test_strategy/trend?days=366")
        assert response.status_code == 422

    def test_get_trend_insufficient_data(self, mock_tracker):
        """Test 404 when insufficient data for trend."""
        mock_tracker.get_trend.return_value = None

        response = client.get("/api/v1/ece/test_strategy/trend")

        assert response.status_code == 404
        assert "Insufficient ECE data" in response.json()["detail"]


class TestListStrategies:
    """Tests for GET /api/v1/ece/"""

    def test_list_strategies_success(self, mock_tracker):
        """Test successful listing of strategies with ECE data."""
        mock_tracker.get_all_strategies.return_value = ["strategy_a", "strategy_b"]

        # Mock latest ECE for each strategy
        mock_tracker.get_latest_ece.side_effect = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 15, tzinfo=UTC),
                ece=0.05,
                n_bins=10,
                total_samples=100,
                signal_type=SignalType.ENTRY,
                strategy_id="strategy_a",
            ),
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 15, tzinfo=UTC),
                ece=0.08,
                n_bins=10,
                total_samples=80,
                signal_type=SignalType.EXIT,
                strategy_id="strategy_b",
            ),
        ]

        # Mock history for signal type collection
        mock_tracker.get_history.side_effect = [
            [  # strategy_a history
                ECEHistoryPoint(
                    timestamp=datetime(2024, 1, 15, tzinfo=UTC),
                    ece=0.05,
                    n_bins=10,
                    total_samples=100,
                    signal_type=SignalType.ENTRY,
                    strategy_id="strategy_a",
                ),
            ],
            [  # strategy_b history
                ECEHistoryPoint(
                    timestamp=datetime(2024, 1, 15, tzinfo=UTC),
                    ece=0.08,
                    n_bins=10,
                    total_samples=80,
                    signal_type=SignalType.EXIT,
                    strategy_id="strategy_b",
                ),
            ],
        ]

        response = client.get("/api/v1/ece/")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["strategies"]) == 2

        # Check first strategy
        strat_a = data["strategies"][0]
        assert strat_a["strategy_id"] == "strategy_a"
        assert strat_a["latest_ece"] == 0.05
        assert "entry" in strat_a["signal_types"]

    def test_list_strategies_empty(self, mock_tracker):
        """Test listing when no strategies exist."""
        mock_tracker.get_all_strategies.return_value = []

        response = client.get("/api/v1/ece/")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["strategies"] == []

    def test_list_strategies_internal_error(self, mock_tracker):
        """Test 500 on internal error."""
        mock_tracker.get_all_strategies.side_effect = Exception("Database error")

        response = client.get("/api/v1/ece/")

        assert response.status_code == 500
        assert "Internal error" in response.json()["detail"]


class TestSignalTypeFiltering:
    """Tests for signal type query parameter filtering."""

    def test_all_signal_types(self, mock_tracker, sample_history_point):
        """Test all valid signal types."""
        mock_tracker.get_latest_ece.return_value = sample_history_point

        signal_types = ["entry", "exit", "sl", "tp"]
        expected_enums = [
            SignalType.ENTRY,
            SignalType.EXIT,
            SignalType.STOP_LOSS,
            SignalType.TAKE_PROFIT,
        ]

        for st, expected in zip(signal_types, expected_enums):
            response = client.get(f"/api/v1/ece/test_strategy?signal_type={st}")
            assert response.status_code == 200

            # Verify correct enum was passed
            call_args = mock_tracker.get_latest_ece.call_args
            assert call_args.kwargs["signal_type"] == expected

    def test_case_sensitivity(self, mock_tracker, sample_history_point):
        """Test that signal type is case-insensitive."""
        mock_tracker.get_latest_ece.return_value = sample_history_point

        # Uppercase should also work
        response = client.get("/api/v1/ece/test_strategy?signal_type=ENTRY")
        assert response.status_code == 200


class TestErrorHandling:
    """Tests for error handling across endpoints."""

    def test_tracker_always_closed(self, mock_tracker):
        """Test that tracker is always closed even on error."""
        mock_tracker.get_latest_ece.side_effect = Exception("Error")

        client.get("/api/v1/ece/test_strategy")

        mock_tracker.close.assert_called_once()

    def test_tracker_closed_on_success(self, mock_tracker, sample_history_point):
        """Test that tracker is closed on successful response."""
        mock_tracker.get_latest_ece.return_value = sample_history_point

        client.get("/api/v1/ece/test_strategy")

        mock_tracker.close.assert_called_once()
