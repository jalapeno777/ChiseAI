"""ECE API router for querying Expected Calibration Error data.

Provides REST endpoints for retrieving ECE metrics per strategy,
historical trends, and signal-type breakdowns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from confidence import ECEHistoryPoint, ECEHistoryTracker, ECETrend, SignalType

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)

# Response models


class ECEBinResponse(BaseModel):
    """Response model for ECE bin data."""

    bin_index: int = Field(..., description="Bin index (0-9)")
    bin_start: float = Field(..., description="Start of confidence range")
    bin_end: float = Field(..., description="End of confidence range")
    confidence: float = Field(..., description="Average predicted confidence")
    accuracy: float = Field(..., description="Actual accuracy")
    sample_count: int = Field(..., description="Number of samples")
    error: float = Field(..., description="Absolute difference |accuracy - confidence|")


class ECEResultResponse(BaseModel):
    """Response model for ECE result."""

    ece: float = Field(..., description="Expected Calibration Error value")
    n_bins: int = Field(..., description="Number of bins used")
    total_samples: int = Field(..., description="Total number of samples")
    signal_type: str | None = Field(None, description="Signal type if applicable")
    is_well_calibrated: bool = Field(
        ..., description="Whether ECE indicates good calibration"
    )


class ECEHistoryPointResponse(BaseModel):
    """Response model for ECE history point."""

    timestamp: str = Field(..., description="ISO timestamp")
    ece: float = Field(..., description="ECE value")
    n_bins: int = Field(..., description="Number of bins")
    total_samples: int = Field(..., description="Total samples")
    signal_type: str | None = Field(None, description="Signal type")


class ECETrendResponse(BaseModel):
    """Response model for ECE trend analysis."""

    strategy_id: str | None = Field(None, description="Strategy identifier")
    signal_type: str | None = Field(None, description="Signal type")
    trend_direction: str = Field(..., description="improving, degrading, or stable")
    trend_slope: float = Field(..., description="Slope of linear trend")
    current_ece: float = Field(..., description="Most recent ECE value")
    avg_ece: float = Field(..., description="Average ECE over period")
    min_ece: float = Field(..., description="Minimum ECE")
    max_ece: float = Field(..., description="Maximum ECE")
    data_points: int = Field(..., description="Number of data points")


class StrategyECEInfo(BaseModel):
    """Response model for strategy ECE summary."""

    strategy_id: str = Field(..., description="Strategy identifier")
    latest_ece: float | None = Field(None, description="Latest ECE value")
    signal_types: list[str] = Field(
        default_factory=list, description="Available signal types"
    )
    data_points: int = Field(0, description="Total data points in history")


class ECEListResponse(BaseModel):
    """Response model for listing strategies with ECE data."""

    strategies: list[StrategyECEInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total number of strategies")


# Create router
router = APIRouter(prefix="/api/v1/ece", tags=["ece"])

# Dependency to get tracker (can be overridden in tests)


async def get_ece_tracker() -> ECEHistoryTracker:
    """Get ECE history tracker instance."""
    return ECEHistoryTracker()


# Helper functions


def _signal_type_from_string(value: str | None) -> SignalType | None:
    """Convert string to SignalType enum."""
    if value is None:
        return None
    try:
        return SignalType(value.lower())
    except ValueError:
        valid_types = [t.value for t in SignalType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid signal_type. Must be one of: {', '.join(valid_types)}",
        )


def _history_point_to_response(point: ECEHistoryPoint) -> ECEHistoryPointResponse:
    """Convert ECEHistoryPoint to response model."""
    return ECEHistoryPointResponse(
        timestamp=point.timestamp.isoformat(),
        ece=point.ece,
        n_bins=point.n_bins,
        total_samples=point.total_samples,
        signal_type=point.signal_type.value if point.signal_type else None,
    )


def _trend_to_response(trend: ECETrend) -> ECETrendResponse:
    """Convert ECETrend to response model."""
    return ECETrendResponse(
        strategy_id=trend.strategy_id,
        signal_type=trend.signal_type.value if trend.signal_type else None,
        trend_direction=trend.trend_direction,
        trend_slope=trend.trend_slope,
        current_ece=trend.current_ece,
        avg_ece=trend.avg_ece,
        min_ece=trend.min_ece,
        max_ece=trend.max_ece,
        data_points=len(trend.points),
    )


# API Endpoints


@router.get("/{strategy_id}", response_model=ECEResultResponse)
async def get_latest_ece(
    strategy_id: str,
    signal_type: str | None = Query(
        None, description="Filter by signal type (entry, exit, sl, tp)"
    ),
) -> ECEResultResponse:
    """Get the latest ECE for a specific strategy.

    Args:
        strategy_id: Unique strategy identifier
        signal_type: Optional filter by signal type

    Returns:
        Latest ECE result for the strategy

    Raises:
        HTTPException: 404 if strategy not found or no ECE data
    """
    tracker = await get_ece_tracker()

    try:
        st = _signal_type_from_string(signal_type)
        latest = await tracker.get_latest_ece(strategy_id=strategy_id, signal_type=st)

        if latest is None:
            raise HTTPException(
                status_code=404,
                detail=f"No ECE data found for strategy '{strategy_id}'",
            )

        return ECEResultResponse(
            ece=latest.ece,
            n_bins=latest.n_bins,
            total_samples=latest.total_samples,
            signal_type=latest.signal_type.value if latest.signal_type else None,
            is_well_calibrated=latest.ece <= 0.1,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving ECE for strategy {strategy_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error retrieving ECE: {e!s}",
        ) from e
    finally:
        await tracker.close()


@router.get("/{strategy_id}/history", response_model=list[ECEHistoryPointResponse])
async def get_ece_history(
    strategy_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    signal_type: str | None = Query(
        None, description="Filter by signal type (entry, exit, sl, tp)"
    ),
) -> list[ECEHistoryPointResponse]:
    """Get ECE history for a specific strategy.

    Args:
        strategy_id: Unique strategy identifier
        days: Number of days to look back (1-365, default 30)
        signal_type: Optional filter by signal type

    Returns:
        List of ECE history points

    Raises:
        HTTPException: 404 if strategy not found or no history
    """
    tracker = await get_ece_tracker()

    try:
        st = _signal_type_from_string(signal_type)
        history = await tracker.get_history(
            strategy_id=strategy_id,
            signal_type=st,
            days=days,
        )

        if not history:
            raise HTTPException(
                status_code=404,
                detail=f"No ECE history found for strategy '{strategy_id}'",
            )

        return [_history_point_to_response(point) for point in history]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving ECE history for strategy {strategy_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error retrieving history: {e!s}",
        ) from e
    finally:
        await tracker.close()


@router.get("/{strategy_id}/trend", response_model=ECETrendResponse)
async def get_ece_trend(
    strategy_id: str,
    days: int = Query(
        30, ge=7, le=365, description="Number of days for trend analysis"
    ),
    signal_type: str | None = Query(
        None, description="Filter by signal type (entry, exit, sl, tp)"
    ),
) -> ECETrendResponse:
    """Get ECE trend analysis for a specific strategy.

    Args:
        strategy_id: Unique strategy identifier
        days: Number of days for trend analysis (7-365, default 30)
        signal_type: Optional filter by signal type

    Returns:
        Trend analysis including direction, slope, and statistics

    Raises:
        HTTPException: 404 if insufficient data for trend analysis
    """
    tracker = await get_ece_tracker()

    try:
        st = _signal_type_from_string(signal_type)
        trend = await tracker.get_trend(
            strategy_id=strategy_id,
            signal_type=st,
            days=days,
        )

        if trend is None:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient ECE data for trend analysis of strategy '{strategy_id}'. "
                "Need at least 2 data points.",
            )

        return _trend_to_response(trend)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving ECE trend for strategy {strategy_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error retrieving trend: {e!s}",
        ) from e
    finally:
        await tracker.close()


@router.get("/", response_model=ECEListResponse)
async def list_strategies_with_ece() -> ECEListResponse:
    """List all strategies that have ECE data.

    Returns:
        List of strategies with ECE summary information
    """
    tracker = await get_ece_tracker()

    try:
        strategy_ids = await tracker.get_all_strategies()

        strategies: list[StrategyECEInfo] = []
        for sid in strategy_ids:
            # Get latest ECE for summary
            latest = await tracker.get_latest_ece(strategy_id=sid)
            history = await tracker.get_history(strategy_id=sid, days=365)

            # Collect signal types
            signal_types = set()
            for point in history:
                if point.signal_type:
                    signal_types.add(point.signal_type.value)

            strategies.append(
                StrategyECEInfo(
                    strategy_id=sid,
                    latest_ece=latest.ece if latest else None,
                    signal_types=sorted(signal_types),
                    data_points=len(history),
                )
            )

        return ECEListResponse(strategies=strategies, total=len(strategies))

    except Exception as e:
        logger.exception("Error listing strategies with ECE data")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error listing strategies: {e!s}",
        ) from e
    finally:
        await tracker.close()
