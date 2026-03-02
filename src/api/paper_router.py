"""Paper trading API router.

Provides FastAPI endpoints for paper trading:
- GET /paper/positions - Current paper positions
- GET /paper/orders - Paper order history
- GET /paper/pnl - PnL metrics

For HOTFIX-PAPER-API-001: Paper Trading API Endpoints
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from paper_trading.models import (
    ErrorResponse,
    OrdersResponse,
    OrderState,
    PnLResponse,
    PositionsResponse,
)
from paper_trading.tracker import PaperTradingTracker

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/paper", tags=["paper_trading"])

# Global tracker instance
_tracker: PaperTradingTracker | None = None


def get_tracker() -> PaperTradingTracker:
    """Get or create paper trading tracker instance.

    Returns:
        PaperTradingTracker instance
    """
    global _tracker
    if _tracker is None:
        _tracker = PaperTradingTracker(portfolio_id="default")
    return _tracker


def set_tracker(tracker: PaperTradingTracker) -> None:
    """Set the global tracker instance (useful for testing).

    Args:
        tracker: PaperTradingTracker instance
    """
    global _tracker
    _tracker = tracker


@router.get(
    "/positions",
    response_model=PositionsResponse,
    summary="Get current paper positions",
    description="Returns all current paper trading positions with unrealized PnL.",
    responses={
        200: {"description": "Successfully retrieved positions"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_positions(
    symbol: str | None = Query(None, description="Filter by symbol (e.g., BTC-USD)"),
) -> PositionsResponse:
    """Get current paper trading positions.

    Args:
        symbol: Optional symbol filter

    Returns:
        List of positions with metadata
    """
    tracker = get_tracker()

    try:
        if symbol:
            # Get specific position
            position = tracker.get_position(symbol)
            positions = [position] if position else []
        else:
            # Get all positions
            positions = tracker.get_all_positions()

        # Calculate totals
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_realized = sum(p.realized_pnl for p in positions)
        total_size = sum(p.size for p in positions)

        return PositionsResponse(
            success=True,
            data={
                "positions": [p.to_dict() for p in positions],
                "count": len(positions),
                "total_unrealized_pnl": total_unrealized,
                "total_realized_pnl": total_realized,
                "total_size": total_size,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    except Exception as e:
        logger.exception("Failed to get paper positions")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve positions: {e!s}",
        ) from e


@router.get(
    "/positions/{symbol}",
    response_model=PositionsResponse,
    summary="Get position for specific symbol",
    description="Returns paper trading position for a specific trading pair.",
    responses={
        200: {"description": "Successfully retrieved position"},
        404: {"description": "Position not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_position_by_symbol(symbol: str) -> PositionsResponse:
    """Get paper trading position for a specific symbol.

    Args:
        symbol: Trading pair symbol (e.g., BTC-USD)

    Returns:
        Position data

    Raises:
        HTTPException: If position not found
    """
    tracker = get_tracker()

    try:
        position = tracker.get_position(symbol)

        if position is None:
            raise HTTPException(
                status_code=404,
                detail=f"No position found for symbol '{symbol}'",
            )

        return PositionsResponse(
            success=True,
            data={
                "position": position.to_dict(),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get position for {symbol}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve position: {e!s}",
        ) from e


@router.get(
    "/orders",
    response_model=OrdersResponse,
    summary="Get paper order history",
    description="Returns paper trading orders with optional filtering by symbol and state.",
    responses={
        200: {"description": "Successfully retrieved orders"},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_orders(
    symbol: str | None = Query(None, description="Filter by symbol (e.g., BTC-USD)"),
    state: str | None = Query(
        None,
        description="Filter by state: pending, open, partial, filled, cancelled, rejected",
    ),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of orders to return (1-1000)"
    ),
) -> OrdersResponse:
    """Get paper trading orders.

    Args:
        symbol: Optional symbol filter
        state: Optional state filter
        limit: Maximum number of orders to return

    Returns:
        List of orders with metadata

    Raises:
        HTTPException: If invalid state parameter
    """
    tracker = get_tracker()

    try:
        # Parse state if provided
        order_state: OrderState | None = None
        if state:
            try:
                order_state = OrderState(state.lower())
            except ValueError as e:
                valid_states = [s.value for s in OrderState]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid state. Must be one of: {', '.join(valid_states)}",
                ) from e

        # Get orders
        orders = tracker.get_orders(
            symbol=symbol.upper() if symbol else None,
            state=order_state,
            limit=limit,
        )

        # Calculate statistics
        filled_orders = [o for o in orders if o.state == OrderState.FILLED]
        pending_orders = [
            o
            for o in orders
            if o.state in (OrderState.PENDING, OrderState.OPEN, OrderState.PARTIAL)
        ]
        cancelled_orders = [o for o in orders if o.state == OrderState.CANCELLED]

        total_quantity = sum(o.quantity for o in orders)
        total_filled = sum(o.filled_quantity for o in orders)

        return OrdersResponse(
            success=True,
            data={
                "orders": [o.to_dict() for o in orders],
                "count": len(orders),
                "by_state": {
                    "filled": len(filled_orders),
                    "pending": len(pending_orders),
                    "cancelled": len(cancelled_orders),
                    "other": len(orders)
                    - len(filled_orders)
                    - len(pending_orders)
                    - len(cancelled_orders),
                },
                "total_quantity": total_quantity,
                "total_filled": total_filled,
                "fill_rate": (
                    (total_filled / total_quantity * 100) if total_quantity > 0 else 0
                ),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get paper orders")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve orders: {e!s}",
        ) from e


@router.get(
    "/orders/{order_id}",
    response_model=OrdersResponse,
    summary="Get specific order by ID",
    description="Returns paper trading order details for a specific order ID.",
    responses={
        200: {"description": "Successfully retrieved order"},
        404: {"description": "Order not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_order_by_id(order_id: str) -> OrdersResponse:
    """Get paper trading order by ID.

    Args:
        order_id: Order identifier

    Returns:
        Order data

    Raises:
        HTTPException: If order not found
    """
    tracker = get_tracker()

    try:
        order = tracker.get_order(order_id)

        if order is None:
            raise HTTPException(
                status_code=404,
                detail=f"Order not found: '{order_id}'",
            )

        return OrdersResponse(
            success=True,
            data={
                "order": order.to_dict(),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get order {order_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve order: {e!s}",
        ) from e


@router.get(
    "/pnl",
    response_model=PnLResponse,
    summary="Get PnL metrics",
    description="Returns paper trading PnL metrics including realized, unrealized, and trade statistics.",
    responses={
        200: {"description": "Successfully retrieved PnL metrics"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_pnl(
    calculate: bool = Query(
        False, description="Recalculate PnL from current positions"
    ),
) -> PnLResponse:
    """Get paper trading PnL metrics.

    Args:
        calculate: Whether to recalculate PnL from current positions

    Returns:
        PnL metrics with trade statistics
    """
    tracker = get_tracker()

    try:
        if calculate:
            pnl = tracker.calculate_pnl()
            tracker.save_pnl(pnl)
        else:
            pnl = tracker.get_pnl()

        # Get additional context
        positions = tracker.get_all_positions()
        total_unrealized = sum(p.unrealized_pnl for p in positions)

        return PnLResponse(
            success=True,
            data={
                "pnl": pnl.to_dict(),
                "current_unrealized_from_positions": total_unrealized,
                "position_count": len(positions),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    except Exception as e:
        logger.exception("Failed to get PnL metrics")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve PnL metrics: {e!s}",
        ) from e


@router.get(
    "/portfolio",
    response_model=dict[str, Any],
    summary="Get portfolio summary",
    description="Returns complete paper trading portfolio summary including positions, orders, and PnL.",
    responses={
        200: {"description": "Successfully retrieved portfolio"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def get_portfolio() -> dict[str, Any]:
    """Get complete paper trading portfolio summary.

    Returns:
        Portfolio summary with positions, orders, and PnL
    """
    tracker = get_tracker()

    try:
        portfolio = tracker.get_portfolio()
        positions = tracker.get_all_positions()
        recent_orders = tracker.get_orders(limit=20)
        pnl = tracker.get_pnl()

        # Update portfolio with current data
        portfolio.positions = positions
        portfolio.recent_orders = recent_orders
        portfolio.pnl = pnl
        portfolio.open_positions_count = len(positions)
        portfolio.open_orders_count = len(
            [
                o
                for o in recent_orders
                if o.state in (OrderState.PENDING, OrderState.OPEN)
            ]
        )

        return {
            "success": True,
            "data": portfolio.to_dict(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.exception("Failed to get portfolio")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve portfolio: {e!s}",
        ) from e


@router.get(
    "/stats",
    response_model=dict[str, Any],
    summary="Get paper trading statistics",
    description="Returns paper trading system statistics and counts.",
)
async def get_stats() -> dict[str, Any]:
    """Get paper trading statistics.

    Returns:
        Statistics including position count, order count, etc.
    """
    tracker = get_tracker()

    try:
        stats = tracker.get_stats()
        positions = tracker.get_all_positions()
        orders = tracker.get_orders(limit=1000)

        return {
            "success": True,
            "data": {
                **stats,
                "open_positions": len(positions),
                "total_orders": len(orders),
                "filled_orders": len(
                    [o for o in orders if o.state == OrderState.FILLED]
                ),
                "pending_orders": len(
                    [
                        o
                        for o in orders
                        if o.state in (OrderState.PENDING, OrderState.OPEN)
                    ]
                ),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.exception("Failed to get stats")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve stats: {e!s}",
        ) from e


# Export router
__all__ = ["router", "get_tracker", "set_tracker"]
