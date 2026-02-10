"""API endpoints for portfolio state querying.

Provides FastAPI routes for querying portfolio state, positions,
balances, and historical snapshots with <100ms latency target.
"""

from __future__ import annotations

import logging
from typing import Any

from portfolio.state_management.models import PortfolioState, Position
from portfolio.state_management.tracker import PortfolioTracker

logger = logging.getLogger(__name__)


class PortfolioAPI:
    """API handler for portfolio state queries.

    Provides methods for querying portfolio state with optimized
    performance targeting <100ms latency for dashboard responsiveness.

    Attributes:
        tracker: PortfolioTracker instance
        cache_ttl_ms: Cache time-to-live in milliseconds
    """

    def __init__(
        self,
        tracker: PortfolioTracker,
        cache_ttl_ms: int = 1000,  # 1 second cache
    ):
        """Initialize portfolio API.

        Args:
            tracker: PortfolioTracker instance
            cache_ttl_ms: Cache TTL in milliseconds
        """
        self.tracker = tracker
        self.cache_ttl_ms = cache_ttl_ms
        self._cache: dict[str, Any] = {}
        self._cache_timestamp: int = 0

    def _get_current_time_ms(self) -> int:
        """Get current time in milliseconds."""
        import time

        return int(time.time() * 1000)

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        current_time = self._get_current_time_ms()
        return (current_time - self._cache_timestamp) < self.cache_ttl_ms

    def _update_cache(self, data: dict[str, Any]) -> None:
        """Update cache with new data."""
        self._cache = data
        self._cache_timestamp = self._get_current_time_ms()

    def get_portfolio_summary(self) -> dict[str, Any]:
        """Get portfolio summary for dashboard.

        Returns:
            Portfolio summary dictionary
        """
        state = self.tracker.state

        return {
            "portfolio_id": state.portfolio_id,
            "total_equity": round(state.total_equity, 8),
            "available_equity": round(state.available_equity, 8),
            "margin_used": round(state.margin_used, 8),
            "unrealized_pnl": round(state.unrealized_pnl, 8),
            "realized_pnl": round(state.realized_pnl, 8),
            "open_positions": len(state.get_open_positions()),
            "total_positions": len(state.positions),
            "last_update": state.last_update,
        }

    def get_positions(
        self,
        token: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get positions with optional filtering.

        Args:
            token: Filter by token (optional)
            status: Filter by status (optional)

        Returns:
            List of position dictionaries
        """
        state = self.tracker.state
        positions = list(state.positions.values())

        # Apply filters
        if token:
            positions = [p for p in positions if p.token == token]
        if status:
            positions = [p for p in positions if p.status.value == status]

        return [p.to_dict() for p in positions]

    def get_position(self, position_id: str) -> dict[str, Any] | None:
        """Get a specific position by ID.

        Args:
            position_id: Position identifier

        Returns:
            Position dictionary or None if not found
        """
        state = self.tracker.state

        if position_id not in state.positions:
            return None

        return state.positions[position_id].to_dict()

    def get_balances(
        self, token: str | None = None
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Get balances with optional token filter.

        Args:
            token: Filter by token (optional)

        Returns:
            List of balances or single balance if token specified
        """
        state = self.tracker.state

        if token:
            if token in state.balances:
                return state.balances[token].to_dict()
            return {"token": token, "free": 0.0, "locked": 0.0, "total": 0.0}

        return [b.to_dict() for b in state.balances.values()]

    def get_pnl_summary(self) -> dict[str, Any]:
        """Get PnL summary across all positions.

        Returns:
            PnL summary dictionary
        """
        state = self.tracker.state
        open_positions = state.get_open_positions()

        # Calculate by token
        pnl_by_token: dict[str, float] = {}
        for pos in open_positions:
            if pos.token not in pnl_by_token:
                pnl_by_token[pos.token] = 0.0
            pnl_by_token[pos.token] += pos.unrealized_pnl

        # Calculate by direction
        long_pnl = sum(p.unrealized_pnl for p in open_positions if p.is_long)
        short_pnl = sum(p.unrealized_pnl for p in open_positions if p.is_short)

        return {
            "total_unrealized_pnl": round(state.unrealized_pnl, 8),
            "total_realized_pnl": round(state.realized_pnl, 8),
            "long_pnl": round(long_pnl, 8),
            "short_pnl": round(short_pnl, 8),
            "pnl_by_token": {k: round(v, 8) for k, v in pnl_by_token.items()},
            "open_position_count": len(open_positions),
        }

    async def get_historical_snapshots(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get historical portfolio snapshots.

        Args:
            start_time: Start timestamp (Unix ms)
            end_time: End timestamp (Unix ms)
            limit: Maximum number of snapshots

        Returns:
            List of snapshot dictionaries
        """
        snapshots = await self.tracker.get_snapshots(start_time, end_time, limit)
        return [s.to_dict() for s in snapshots]

    async def get_equity_curve(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get equity curve data for charting.

        Args:
            start_time: Start timestamp (Unix ms)
            end_time: End timestamp (Unix ms)

        Returns:
            List of equity data points
        """
        snapshots = await self.tracker.get_snapshots(start_time, end_time, limit=1000)

        # Sort by timestamp ascending for curve
        snapshots_sorted = sorted(snapshots, key=lambda s: s.timestamp)

        return [
            {
                "timestamp": s.timestamp,
                "total_equity": round(s.total_equity, 8),
                "available_equity": round(s.available_equity, 8),
                "margin_used": round(s.margin_used, 8),
                "unrealized_pnl": round(s.unrealized_pnl, 8),
            }
            for s in snapshots_sorted
        ]

    def get_full_state(self) -> dict[str, Any]:
        """Get complete portfolio state.

        Returns:
            Complete portfolio state dictionary
        """
        return self.tracker.state.to_dict()

    def health_check(self) -> dict[str, Any]:
        """Get API health status.

        Returns:
            Health status dictionary
        """
        import time

        # Measure response time
        start = time.time()
        _ = self.tracker.state.total_equity
        latency_ms = (time.time() - start) * 1000

        return {
            "status": "healthy",
            "portfolio_id": self.tracker.portfolio_id,
            "latency_ms": round(latency_ms, 3),
            "last_update": self.tracker.state.last_update,
            "open_positions": len(self.tracker.state.get_open_positions()),
        }


# FastAPI route factory for easy integration
def create_portfolio_routes(tracker: PortfolioTracker) -> list[dict[str, Any]]:
    """Create FastAPI route definitions for portfolio API.

    Args:
        tracker: PortfolioTracker instance

    Returns:
        List of route definitions
    """
    api = PortfolioAPI(tracker)

    routes = [
        {
            "path": "/portfolio/summary",
            "method": "GET",
            "handler": api.get_portfolio_summary,
            "response_model": dict,
        },
        {
            "path": "/portfolio/positions",
            "method": "GET",
            "handler": api.get_positions,
            "response_model": list,
        },
        {
            "path": "/portfolio/positions/{position_id}",
            "method": "GET",
            "handler": api.get_position,
            "response_model": dict | None,
        },
        {
            "path": "/portfolio/balances",
            "method": "GET",
            "handler": api.get_balances,
            "response_model": list | dict,
        },
        {
            "path": "/portfolio/pnl",
            "method": "GET",
            "handler": api.get_pnl_summary,
            "response_model": dict,
        },
        {
            "path": "/portfolio/snapshots",
            "method": "GET",
            "handler": api.get_historical_snapshots,
            "response_model": list,
        },
        {
            "path": "/portfolio/equity-curve",
            "method": "GET",
            "handler": api.get_equity_curve,
            "response_model": list,
        },
        {
            "path": "/portfolio/state",
            "method": "GET",
            "handler": api.get_full_state,
            "response_model": dict,
        },
        {
            "path": "/portfolio/health",
            "method": "GET",
            "handler": api.health_check,
            "response_model": dict,
        },
    ]

    return routes
