"""Tests for ECE API router.

Tests all endpoints with mock ECE tracker to ensure proper functionality
and error handling.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# Fixtures
@pytest.fixture
def mock_tracker():
    """Create a mock ECE history tracker."""
    tracker = MagicMock()
    tracker.close = AsyncMock()
    return tracker


@pytest.fixture
def sample_history_points():
    """Create sample ECE history points."""
    from confidence import ECEHistoryPoint, SignalType

    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return [
        ECEHistoryPoint(
            timestamp=base_time + timedelta(days=i),
            ece=0.05 + (i * 0.01),
            n_bins=10,
            total_samples=100 + (i * 10),
            signal_type=SignalType.ENTRY,
            strategy_id="test_strategy",
        )
        for i in range(5)
    ]


@pytest.fixture
def sample_trend():
    """Create a sample ECE trend."""
    from confidence import ECETrend, ECEHistoryPoint, SignalType

    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    points = [
        ECEHistoryPoint(
            timestamp=base_time + timedelta(days=i),
            ece=0.05 + (i * 0.01),
            n_bins=10,
            total_samples=100 + (i * 10),
            signal_type=SignalType.ENTRY,
            strategy_id="test_strategy",
        )
        for i in range(5)
    ]

    return ECETrend(
        strategy_id="test_strategy",
        signal_type=SignalType.ENTRY,
        points=points,
        trend_direction="degrading",
        trend_slope=0.01,
        current_ece=0.09,
        avg_ece=0.07,
        min_ece=0.05,
        max_ece=0.09,
    )


# Test list_strategies endpoint
class TestListStrategies:
    """Tests for GET /api/v1/ece/ endpoint."""

    @pytest.mark.asyncio
    async def test_list_strategies_success(self, mock_tracker):
        """Test successful retrieval of strategy list."""
        mock_tracker.get_all_strategies = AsyncMock(
            return_value=["strategy1", "strategy2", "strategy3"]
        )

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import list_strategies

            result = await list_strategies()

            assert result.strategies == ["strategy1", "strategy2", "strategy3"]
            assert result.count == 3
            mock_tracker.get_all_strategies.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_strategies_empty(self, mock_tracker):
        """Test retrieval when no strategies exist."""
        mock_tracker.get_all_strategies = AsyncMock(return_value=[])

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import list_strategies

            result = await list_strategies()

            assert result.strategies == []
            assert result.count == 0

    @pytest.mark.asyncio
    async def test_list_strategies_error(self, mock_tracker):
        """Test error handling when tracker fails."""
        mock_tracker.get_all_strategies = AsyncMock(
            side_effect=Exception("Database error")
        )

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import list_strategies
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await list_strategies()

            assert exc_info.value.status_code == 500
            assert "Failed to retrieve strategy list" in exc_info.value.detail


# Test get_latest_ece endpoint
class TestGetLatestECE:
    """Tests for GET /api/v1/ece/{strategy_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_latest_ece_success(self, mock_tracker):
        """Test successful retrieval of latest ECE."""
        from confidence import ECEHistoryPoint, SignalType

        mock_point = ECEHistoryPoint(
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
            ece=0.08,
            n_bins=10,
            total_samples=500,
            signal_type=SignalType.ENTRY,
            strategy_id="test_strategy",
        )
        mock_tracker.get_latest_ece = AsyncMock(return_value=mock_point)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_latest_ece

            result = await get_latest_ece("test_strategy", None)

            assert result.strategy_id == "test_strategy"
            assert result.ece == 0.08
            assert result.n_bins == 10
            assert result.total_samples == 500
            assert result.signal_type == "entry"
            assert result.is_well_calibrated is True  # ECE <= 0.1
            mock_tracker.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_ece_with_signal_type(self, mock_tracker):
        """Test retrieval with signal type filter."""
        from confidence import ECEHistoryPoint, SignalType

        mock_point = ECEHistoryPoint(
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
            ece=0.15,
            n_bins=10,
            total_samples=300,
            signal_type=SignalType.EXIT,
            strategy_id="test_strategy",
        )
        mock_tracker.get_latest_ece = AsyncMock(return_value=mock_point)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_latest_ece

            result = await get_latest_ece("test_strategy", "exit")

            assert result.signal_type == "exit"
            assert result.is_well_calibrated is False  # ECE > 0.1
            mock_tracker.get_latest_ece.assert_called_once_with(
                strategy_id="test_strategy",
                signal_type=SignalType.EXIT,
            )

    @pytest.mark.asyncio
    async def test_get_latest_ece_not_found(self, mock_tracker):
        """Test 404 when strategy has no ECE data."""
        mock_tracker.get_latest_ece = AsyncMock(return_value=None)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_latest_ece
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_latest_ece("unknown_strategy", None)

            assert exc_info.value.status_code == 404
            assert "No ECE data found" in exc_info.value.detail
            mock_tracker.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_ece_invalid_signal_type(self, mock_tracker):
        """Test 400 for invalid signal type."""
        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_latest_ece
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_latest_ece("test_strategy", "invalid_type")

            assert exc_info.value.status_code == 400
            assert "Invalid signal_type" in exc_info.value.detail
            mock_tracker.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_ece_tracker_error(self, mock_tracker):
        """Test 500 when tracker raises exception."""
        mock_tracker.get_latest_ece = AsyncMock(side_effect=Exception("DB error"))

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_latest_ece
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_latest_ece("test_strategy", None)

            assert exc_info.value.status_code == 500
            assert "Failed to retrieve ECE data" in exc_info.value.detail
            mock_tracker.close.assert_called_once()


# Test get_ece_history endpoint
class TestGetECEHistory:
    """Tests for GET /api/v1/ece/{strategy_id}/history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, mock_tracker, sample_history_points):
        """Test successful retrieval of ECE history."""
        mock_tracker.get_history = AsyncMock(return_value=sample_history_points)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_history

            result = await get_ece_history("test_strategy", days=30, signal_type=None)

            assert result.strategy_id == "test_strategy"
            assert result.days == 30
            assert result.count == 5
            assert len(result.points) == 5
            assert result.points[0].ece == 0.05
            mock_tracker.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_history_with_signal_type(
        self, mock_tracker, sample_history_points
    ):
        """Test history retrieval with signal type filter."""
        mock_tracker.get_history = AsyncMock(return_value=sample_history_points)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_history
            from confidence import SignalType

            result = await get_ece_history("test_strategy", days=7, signal_type="entry")

            assert result.signal_type == "entry"
            mock_tracker.get_history.assert_called_once_with(
                strategy_id="test_strategy",
                signal_type=SignalType.ENTRY,
                days=7,
            )

    @pytest.mark.asyncio
    async def test_get_history_empty(self, mock_tracker):
        """Test empty history response."""
        mock_tracker.get_history = AsyncMock(return_value=[])

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_history

            result = await get_ece_history("test_strategy", days=30, signal_type=None)

            assert result.count == 0
            assert result.points == []

    @pytest.mark.asyncio
    async def test_get_history_invalid_signal_type(self, mock_tracker):
        """Test 400 for invalid signal type."""
        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_history
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_ece_history("test_strategy", days=30, signal_type="bad_type")

            assert exc_info.value.status_code == 400


# Test get_ece_trend endpoint
class TestGetECETrend:
    """Tests for GET /api/v1/ece/{strategy_id}/trend endpoint."""

    @pytest.mark.asyncio
    async def test_get_trend_success(self, mock_tracker, sample_trend):
        """Test successful retrieval of trend analysis."""
        mock_tracker.get_trend = AsyncMock(return_value=sample_trend)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_trend

            result = await get_ece_trend("test_strategy", days=30, signal_type=None)

            assert result.strategy_id == "test_strategy"
            assert result.trend_direction == "degrading"
            assert result.trend_slope == 0.01
            assert result.current_ece == 0.09
            assert result.avg_ece == 0.07
            assert result.min_ece == 0.05
            assert result.max_ece == 0.09
            assert result.point_count == 5
            mock_tracker.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_trend_improving(self, mock_tracker):
        """Test trend with improving direction."""
        from confidence import ECETrend, ECEHistoryPoint, SignalType

        base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        points = [
            ECEHistoryPoint(
                timestamp=base_time + timedelta(days=i),
                ece=0.15 - (i * 0.02),
                n_bins=10,
                total_samples=100,
                signal_type=SignalType.ENTRY,
                strategy_id="test_strategy",
            )
            for i in range(5)
        ]

        trend = ECETrend(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
            points=points,
            trend_direction="improving",
            trend_slope=-0.02,
            current_ece=0.07,
            avg_ece=0.11,
            min_ece=0.07,
            max_ece=0.15,
        )
        mock_tracker.get_trend = AsyncMock(return_value=trend)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_trend

            result = await get_ece_trend("test_strategy", days=30, signal_type=None)

            assert result.trend_direction == "improving"
            assert result.trend_slope == -0.02

    @pytest.mark.asyncio
    async def test_get_trend_insufficient_data(self, mock_tracker):
        """Test 404 when insufficient data for trend."""
        mock_tracker.get_trend = AsyncMock(return_value=None)

        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_trend
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_ece_trend("test_strategy", days=30, signal_type=None)

            assert exc_info.value.status_code == 404
            assert "Insufficient ECE data" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_trend_invalid_signal_type(self, mock_tracker):
        """Test 400 for invalid signal type."""
        with patch("api.ece_router.get_ece_tracker", return_value=mock_tracker):
            from api.ece_router import get_ece_trend
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_ece_trend("test_strategy", days=30, signal_type="unknown")

            assert exc_info.value.status_code == 400


# Test signal type validation
class TestSignalTypeValidation:
    """Tests for signal type parameter validation."""

    @pytest.mark.parametrize("signal_type", ["entry", "exit", "sl", "tp"])
    def test_valid_signal_types(self, signal_type):
        """Test that all valid signal types are accepted."""
        from confidence import SignalType

        # Should not raise
        st = SignalType(signal_type)
        assert st.value == signal_type

    def test_invalid_signal_type(self):
        """Test that invalid signal types raise ValueError."""
        from confidence import SignalType

        with pytest.raises(ValueError):
            SignalType("invalid")


# Test response models
class TestResponseModels:
    """Tests for Pydantic response models."""

    def test_ece_response_well_calibrated(self):
        """Test ECE response with well-calibrated ECE."""
        from api.ece_router import ECEResponse

        response = ECEResponse(
            strategy_id="test",
            ece=0.05,
            n_bins=10,
            total_samples=100,
            is_well_calibrated=True,
        )
        assert response.ece == 0.05
        assert response.is_well_calibrated is True

    def test_ece_response_poorly_calibrated(self):
        """Test ECE response with poorly calibrated ECE."""
        from api.ece_router import ECEResponse

        response = ECEResponse(
            strategy_id="test",
            ece=0.15,
            n_bins=10,
            total_samples=100,
            is_well_calibrated=False,
        )
        assert response.ece == 0.15
        assert response.is_well_calibrated is False

    def test_history_response(self):
        """Test history response model."""
        from api.ece_router import ECEHistoryResponse, ECEHistoryPointResponse
        from datetime import datetime, UTC

        point = ECEHistoryPointResponse(
            timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            ece=0.08,
            n_bins=10,
            total_samples=100,
        )
        response = ECEHistoryResponse(
            strategy_id="test",
            days=30,
            points=[point],
            count=1,
        )
        assert response.count == 1
        assert len(response.points) == 1

    def test_trend_response(self):
        """Test trend response model."""
        from api.ece_router import ECETrendResponse

        response = ECETrendResponse(
            strategy_id="test",
            days=30,
            trend_direction="stable",
            trend_slope=0.0,
            current_ece=0.08,
            avg_ece=0.08,
            min_ece=0.05,
            max_ece=0.11,
            point_count=10,
        )
        assert response.trend_direction == "stable"
        assert response.point_count == 10

    def test_strategy_list_response(self):
        """Test strategy list response model."""
        from api.ece_router import StrategyListResponse

        response = StrategyListResponse(
            strategies=["s1", "s2", "s3"],
            count=3,
        )
        assert response.count == 3
        assert response.strategies == ["s1", "s2", "s3"]


# Test error response model
class TestErrorResponse:
    """Tests for error response model."""

    def test_error_response(self):
        """Test error response model."""
        from api.ece_router import ErrorResponse

        error = ErrorResponse(detail="Something went wrong")
        assert error.detail == "Something went wrong"
