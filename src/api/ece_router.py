"""ECE API router for querying Expected Calibration Error data.

Provides FastAPI endpoints for retrieving ECE metrics per strategy,
historical ECE data, trend analysis, and strategy listings.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from confidence import ECEHistoryPoint, ECEHistoryTracker, ECETrend, SignalType

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/ece", tags=["ece"])


# Pydantic response models
class ECEBinResponse(BaseModel):
    """ECE bin data for API response."""

    bin_index: int = Field(..., description="Index of this bin (0-9)")
    bin_start: float = Field(..., description="Start of confidence range (0.0-0.9)")
    bin_end: float = Field(..., description="End of confidence range (0.1-1.0)")
    confidence: float = Field(
        ..., description="Average predicted confidence in this bin"
    )
    accuracy: float = Field(..., description="Actual accuracy in this bin")
    sample_count: int = Field(..., description="Number of samples in this bin")
    error: float = Field(..., description="Absolute difference |accuracy - confidence|")


class ECEResponse(BaseModel):
    """ECE calculation result for API response."""

    strategy_id: str = Field(..., description="Strategy identifier")
    ece: float = Field(..., description="Expected Calibration Error value (0.0-1.0)")
    n_bins: int = Field(..., description="Number of bins used")
    total_samples: int = Field(..., description="Total number of samples")
    bins: list[ECEBinResponse] = Field(
        default_factory=list, description="Per-bin details"
    )
    signal_type: str | None = Field(
        None, description="Signal type filter if applicable"
    )
    is_well_calibrated: bool = Field(
        ..., description="Whether ECE indicates good calibration"
    )
    timestamp: datetime | None = Field(None, description="When the ECE was calculated")


class ECEHistoryPointResponse(BaseModel):
    """Single ECE history point for API response."""

    timestamp: datetime = Field(..., description="When the ECE was calculated")
    ece: float = Field(..., description="ECE value")
    n_bins: int = Field(..., description="Number of bins used")
    total_samples: int = Field(..., description="Total samples in calculation")
    signal_type: str | None = Field(None, description="Signal type if applicable")
    strategy_id: str | None = Field(None, description="Strategy identifier")


class ECEHistoryResponse(BaseModel):
    """ECE history response."""

    strategy_id: str = Field(..., description="Strategy identifier")
    signal_type: str | None = Field(
        None, description="Signal type filter if applicable"
    )
    days: int = Field(..., description="Number of days in query")
    points: list[ECEHistoryPointResponse] = Field(
        default_factory=list, description="Historical ECE points"
    )
    count: int = Field(..., description="Total number of points returned")


class ECETrendResponse(BaseModel):
    """ECE trend analysis response."""

    strategy_id: str = Field(..., description="Strategy identifier")
    signal_type: str | None = Field(
        None, description="Signal type filter if applicable"
    )
    days: int = Field(..., description="Number of days analyzed")
    trend_direction: str = Field(..., description="improving, degrading, or stable")
    trend_slope: float = Field(
        ..., description="Slope of linear trend (ECE change per day)"
    )
    current_ece: float = Field(..., description="Most recent ECE value")
    avg_ece: float = Field(..., description="Average ECE over the period")
    min_ece: float = Field(..., description="Minimum ECE in the period")
    max_ece: float = Field(..., description="Maximum ECE in the period")
    point_count: int = Field(..., description="Number of data points in analysis")


class StrategyListResponse(BaseModel):
    """List of strategies with ECE data."""

    strategies: list[str] = Field(
        default_factory=list, description="List of strategy IDs"
    )
    count: int = Field(..., description="Total number of strategies")


class ErrorResponse(BaseModel):
    """Error response model."""

    detail: str = Field(..., description="Error message")


# Dependency to get ECE tracker
async def get_ece_tracker() -> ECEHistoryTracker:
    """Get ECE history tracker instance.

    Returns:
        Configured ECEHistoryTracker instance
    """
    # Create tracker with default settings
    # In production, this might use dependency injection or config
    return ECEHistoryTracker()


@router.get(
    "/",
    response_model=StrategyListResponse,
    summary="List all strategies with ECE data",
    description="Returns a list of all strategy IDs that have ECE history data.",
    responses={
        200: {"description": "Successfully retrieved strategy list"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def list_strategies(
    tracker: ECEHistoryTracker = Query(None),
) -> StrategyListResponse:
    """List all strategies with ECE data.

    Returns:
        List of strategy IDs with ECE history
    """
    if tracker is None:
        tracker = await get_ece_tracker()

    try:
        strategies = await tracker.get_all_strategies()
        return StrategyListResponse(
            strategies=strategies,
            count=len(strategies),
        )
    except Exception as e:
        logger.exception("Failed to list strategies with ECE data")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve strategy list: {e!s}",
        ) from e


@router.get(
    "/{strategy_id}",
    response_model=ECEResponse,
    summary="Get latest ECE for a strategy",
    description="Returns the most recent ECE calculation for the specified strategy.",
    responses={
        200: {"description": "Successfully retrieved ECE data"},
        404: {
            "description": "Strategy not found or no ECE data",
            "model": ErrorResponse,
        },
        400: {"description": "Invalid signal type", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_latest_ece(
    strategy_id: str,
    signal_type: str | None = Query(
        None,
        description="Filter by signal type: entry, exit, sl, or tp",
    ),
) -> ECEResponse:
    """Get the latest ECE for a strategy.

    Args:
        strategy_id: Strategy identifier
        signal_type: Optional signal type filter

    Returns:
        Latest ECE data for the strategy

    Raises:
        HTTPException: If strategy not found or invalid parameters
    """
    tracker = await get_ece_tracker()

    try:
        # Parse signal type if provided
        st: SignalType | None = None
        if signal_type:
            try:
                st = SignalType(signal_type.lower())
            except ValueError as e:
                valid_types = [t.value for t in SignalType]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid signal_type. Must be one of: {', '.join(valid_types)}",
                ) from e

        # Get latest ECE
        point = await tracker.get_latest_ece(strategy_id=strategy_id, signal_type=st)

        if point is None:
            raise HTTPException(
                status_code=404,
                detail=f"No ECE data found for strategy '{strategy_id}'"
                + (f" with signal_type '{signal_type}'" if signal_type else ""),
            )

        # Determine if well calibrated (ECE < 0.1 is default threshold)
        is_well_calibrated = point.ece <= 0.1

        return ECEResponse(
            strategy_id=strategy_id,
            ece=point.ece,
            n_bins=point.n_bins,
            total_samples=point.total_samples,
            bins=[],  # Latest ECE from history doesn't include bin details
            signal_type=point.signal_type.value if point.signal_type else None,
            is_well_calibrated=is_well_calibrated,
            timestamp=point.timestamp,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get latest ECE for strategy {strategy_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve ECE data: {e!s}",
        ) from e
    finally:
        await tracker.close()


@router.get(
    "/{strategy_id}/history",
    response_model=ECEHistoryResponse,
    summary="Get ECE history for a strategy",
    description="Returns historical ECE data for the specified strategy over a time period.",
    responses={
        200: {"description": "Successfully retrieved ECE history"},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_ece_history(
    strategy_id: str,
    days: int = Query(
        30, ge=1, le=365, description="Number of days to look back (1-365)"
    ),
    signal_type: str | None = Query(
        None,
        description="Filter by signal type: entry, exit, sl, or tp",
    ),
) -> ECEHistoryResponse:
    """Get ECE history for a strategy.

    Args:
        strategy_id: Strategy identifier
        days: Number of days to look back (default 30)
        signal_type: Optional signal type filter

    Returns:
        Historical ECE data for the strategy

    Raises:
        HTTPException: If invalid parameters or server error
    """
    tracker = await get_ece_tracker()

    try:
        # Parse signal type if provided
        st: SignalType | None = None
        if signal_type:
            try:
                st = SignalType(signal_type.lower())
            except ValueError as e:
                valid_types = [t.value for t in SignalType]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid signal_type. Must be one of: {', '.join(valid_types)}",
                ) from e

        # Get history
        points = await tracker.get_history(
            strategy_id=strategy_id,
            signal_type=st,
            days=days,
        )

        # Convert to response model
        history_points = [
            ECEHistoryPointResponse(
                timestamp=p.timestamp,
                ece=p.ece,
                n_bins=p.n_bins,
                total_samples=p.total_samples,
                signal_type=p.signal_type.value if p.signal_type else None,
                strategy_id=p.strategy_id,
            )
            for p in points
        ]

        return ECEHistoryResponse(
            strategy_id=strategy_id,
            signal_type=signal_type,
            days=days,
            points=history_points,
            count=len(history_points),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get ECE history for strategy {strategy_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve ECE history: {e!s}",
        ) from e
    finally:
        await tracker.close()


@router.get(
    "/{strategy_id}/trend",
    response_model=ECETrendResponse,
    summary="Get ECE trend analysis for a strategy",
    description="Returns trend analysis including direction, slope, and statistics.",
    responses={
        200: {"description": "Successfully retrieved trend analysis"},
        404: {
            "description": "Insufficient data for trend analysis",
            "model": ErrorResponse,
        },
        400: {"description": "Invalid parameters", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_ece_trend(
    strategy_id: str,
    days: int = Query(
        30, ge=1, le=365, description="Number of days to analyze (1-365)"
    ),
    signal_type: str | None = Query(
        None,
        description="Filter by signal type: entry, exit, sl, or tp",
    ),
) -> ECETrendResponse:
    """Get ECE trend analysis for a strategy.

    Args:
        strategy_id: Strategy identifier
        days: Number of days to analyze (default 30)
        signal_type: Optional signal type filter

    Returns:
        Trend analysis with direction, slope, and statistics

    Raises:
        HTTPException: If insufficient data or invalid parameters
    """
    tracker = await get_ece_tracker()

    try:
        # Parse signal type if provided
        st: SignalType | None = None
        if signal_type:
            try:
                st = SignalType(signal_type.lower())
            except ValueError as e:
                valid_types = [t.value for t in SignalType]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid signal_type. Must be one of: {', '.join(valid_types)}",
                ) from e

        # Get trend analysis
        trend = await tracker.get_trend(
            strategy_id=strategy_id,
            signal_type=st,
            days=days,
        )

        if trend is None:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient ECE data for trend analysis for strategy '{strategy_id}'. "
                "Need at least 2 data points.",
            )

        return ECETrendResponse(
            strategy_id=strategy_id,
            signal_type=signal_type,
            days=days,
            trend_direction=trend.trend_direction,
            trend_slope=trend.trend_slope,
            current_ece=trend.current_ece,
            avg_ece=trend.avg_ece,
            min_ece=trend.min_ece,
            max_ece=trend.max_ece,
            point_count=len(trend.points),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get ECE trend for strategy {strategy_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve ECE trend: {e!s}",
        ) from e
    finally:
        await tracker.close()


# Export router
__all__ = ["router"]
