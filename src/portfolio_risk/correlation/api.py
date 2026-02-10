"""API endpoints for correlation analysis.

Provides FastAPI routes for querying correlation matrices,
rolling correlations, and diversification metrics.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from portfolio.state_management.tracker import PortfolioTracker

from .engine import (
    CorrelationEngine,
    CorrelationMethod,
    CorrelationResult,
)

logger = logging.getLogger(__name__)


class CorrelationAPI:
    """API handler for correlation analysis queries.

    Provides methods for retrieving correlation matrices,
    rolling correlations, and diversification metrics with
    optimized performance for dashboard consumption.

    Attributes:
        tracker: PortfolioTracker instance
        engine: CorrelationEngine instance
        cache_ttl_ms: Cache time-to-live in milliseconds
    """

    def __init__(
        self,
        tracker: PortfolioTracker,
        engine: CorrelationEngine | None = None,
        cache_ttl_ms: int = 5000,  # 5 second cache for correlation data
    ):
        """Initialize correlation API.

        Args:
            tracker: PortfolioTracker instance
            engine: CorrelationEngine instance (creates default if None)
            cache_ttl_ms: Cache TTL in milliseconds
        """
        self.tracker = tracker
        self.engine = engine or CorrelationEngine()
        self.cache_ttl_ms = cache_ttl_ms
        self._cache: dict[str, Any] = {}
        self._cache_timestamp: int = 0

    def _get_current_time_ms(self) -> int:
        """Get current time in milliseconds."""
        import time

        return int(time.time() * 1000)

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is still valid."""
        current_time = self._get_current_time_ms()
        return (
            cache_key in self._cache
            and (current_time - self._cache_timestamp) < self.cache_ttl_ms
        )

    def _update_cache(self, cache_key: str, data: Any) -> None:
        """Update cache with new data."""
        self._cache[cache_key] = data
        self._cache_timestamp = self._get_current_time_ms()

    def _get_position_price_data(
        self,
        lookback_periods: int = 100,
    ) -> dict[str, np.ndarray]:
        """Extract price data from portfolio positions.

        In a real implementation, this would fetch historical OHLCV data
        from the data ingestion system. For now, we use current prices
        as a placeholder and generate synthetic historical data.

        Args:
            lookback_periods: Number of historical periods to fetch

        Returns:
            Dictionary mapping token symbols to price arrays
        """
        # Get unique tokens from open positions
        tokens = set()
        for position in self.tracker.state.get_open_positions():
            tokens.add(position.token)

        price_data: dict[str, np.ndarray] = {}

        # In production, this would fetch from OHLCV fetcher
        # For now, generate synthetic data based on current prices
        np.random.seed(42)  # For reproducibility in tests

        for token in tokens:
            # Get current price from positions
            positions = self.tracker.state.get_positions_by_token(token)
            if positions:
                current_price = positions[0].current_price
                if current_price > 0:
                    # Generate synthetic historical prices with random walk
                    returns = np.random.normal(0.001, 0.02, lookback_periods)
                    prices = current_price * np.exp(np.cumsum(returns[::-1]))[::-1]
                    price_data[token] = prices

        return price_data

    def get_correlation_matrix(
        self,
        method: str = "pearson",
    ) -> dict[str, Any]:
        """Get correlation matrix for all portfolio positions.

        Args:
            method: Correlation method ("pearson" or "spearman")

        Returns:
            Dictionary with correlation matrix and metadata
        """
        cache_key = f"correlation_matrix_{method}"
        if self._is_cache_valid(cache_key):
            return dict(self._cache[cache_key])

        # Get price data from positions
        price_data = self._get_position_price_data()

        if len(price_data) < 2:
            result = {
                "tokens": list(price_data.keys()),
                "correlation_matrix": [],
                "method": method,
                "diversification_score": 0.0,
                "message": "Insufficient positions for correlation analysis",
                "timestamp": self._get_current_time_ms(),
            }
            self._update_cache(cache_key, result)
            return result

        # Calculate correlation matrix
        corr_method = CorrelationMethod(method.lower())
        corr_result = self.engine.calculate_correlation_matrix(price_data, corr_method)

        result = {
            "tokens": corr_result.tokens,
            "correlation_matrix": corr_result.correlation_matrix.tolist(),
            "method": corr_result.method.value,
            "diversification_score": round(corr_result.diversification_score, 4),
            "timestamp": corr_result.timestamp,
        }

        self._update_cache(cache_key, result)
        return result

    def get_rolling_correlations(
        self,
        window_size: int = 30,
        method: str = "pearson",
    ) -> dict[str, Any]:
        """Get rolling window correlations for trend analysis.

        Args:
            window_size: Rolling window size in periods
            method: Correlation method ("pearson" or "spearman")

        Returns:
            Dictionary with rolling correlation time series
        """
        cache_key = f"rolling_corr_{window_size}_{method}"
        if self._is_cache_valid(cache_key):
            return dict(self._cache[cache_key])

        # Get price data
        # Need more data for rolling windows
        price_data = self._get_position_price_data(lookback_periods=window_size + 100)

        if len(price_data) < 2:
            result = {
                "tokens": list(price_data.keys()),
                "rolling_correlations": {},
                "window_size": window_size,
                "method": method,
                "message": "Insufficient positions for rolling correlation",
                "timestamps": [],
            }
            self._update_cache(cache_key, result)
            return result

        # Calculate rolling correlations
        corr_method = CorrelationMethod(method.lower())
        try:
            rolling_result = self.engine.calculate_rolling_correlations(
                price_data, window_size, corr_method
            )
            result = rolling_result.to_dict()
        except ValueError as e:
            result = {
                "tokens": list(price_data.keys()),
                "rolling_correlations": {},
                "window_size": window_size,
                "method": method,
                "message": str(e),
                "timestamps": [],
            }

        self._update_cache(cache_key, result)
        return result

    def get_diversification_metrics(self) -> dict[str, Any]:
        """Get portfolio diversification metrics.

        Returns:
            Dictionary with diversification score and recommendations
        """
        cache_key = "diversification_metrics"
        if self._is_cache_valid(cache_key):
            return dict(self._cache[cache_key])

        # Get correlation matrix first
        corr_data = self.get_correlation_matrix()

        if not corr_data.get("correlation_matrix"):
            result = {
                "diversification_score": 0.0,
                "score_interpretation": "N/A",
                "recommendations": [],
                "high_correlation_pairs": [],
                "timestamp": self._get_current_time_ms(),
            }
            self._update_cache(cache_key, result)
            return result

        # Reconstruct CorrelationResult for analysis
        tokens = corr_data["tokens"]
        corr_matrix = np.array(corr_data["correlation_matrix"])
        corr_result = CorrelationResult(
            tokens=tokens,
            correlation_matrix=corr_matrix,
            method=CorrelationMethod(corr_data["method"]),
            window_size=0,
            timestamp=corr_data["timestamp"],
            diversification_score=corr_data["diversification_score"],
        )

        # Get high correlation pairs
        high_corr_pairs = self.engine.get_high_correlation_pairs(
            corr_result, threshold=0.7
        )

        # Get recommendations
        recommendations = self.engine.get_diversification_recommendations(corr_result)

        # Interpret score
        score = corr_data["diversification_score"]
        if score >= 70:
            interpretation = "Well diversified"
        elif score >= 40:
            interpretation = "Moderately diversified"
        else:
            interpretation = "Poorly diversified"

        result = {
            "diversification_score": score,
            "score_interpretation": interpretation,
            "recommendations": recommendations,
            "high_correlation_pairs": high_corr_pairs,
            "timestamp": corr_data["timestamp"],
        }

        self._update_cache(cache_key, result)
        return result

    def get_correlation_between_tokens(
        self,
        token1: str,
        token2: str,
    ) -> dict[str, Any]:
        """Get correlation between two specific tokens.

        Args:
            token1: First token symbol
            token2: Second token symbol

        Returns:
            Dictionary with correlation value
        """
        corr_data = self.get_correlation_matrix()

        if not corr_data.get("correlation_matrix"):
            return {
                "token1": token1,
                "token2": token2,
                "correlation": None,
                "message": "Correlation matrix not available",
            }

        tokens = corr_data["tokens"]
        if token1 not in tokens or token2 not in tokens:
            return {
                "token1": token1,
                "token2": token2,
                "correlation": None,
                "message": "One or both tokens not in portfolio",
            }

        corr_matrix = np.array(corr_data["correlation_matrix"])
        idx1 = tokens.index(token1)
        idx2 = tokens.index(token2)
        correlation = float(corr_matrix[idx1, idx2])

        return {
            "token1": token1,
            "token2": token2,
            "correlation": round(correlation, 4),
            "abs_correlation": round(abs(correlation), 4),
            "method": corr_data["method"],
            "timestamp": corr_data["timestamp"],
        }

    def get_position_correlations(self, position_id: str) -> dict[str, Any]:
        """Get correlations for a specific position with all others.

        Args:
            position_id: Position identifier

        Returns:
            Dictionary with correlations to other positions
        """
        # Get position
        if position_id not in self.tracker.state.positions:
            return {
                "position_id": position_id,
                "error": "Position not found",
                "correlations": [],
            }

        position = self.tracker.state.positions[position_id]
        token = position.token

        # Get correlation matrix
        corr_data = self.get_correlation_matrix()

        if not corr_data.get("correlation_matrix"):
            return {
                "position_id": position_id,
                "token": token,
                "correlations": [],
                "message": "Correlation matrix not available",
            }

        tokens = corr_data["tokens"]
        if token not in tokens:
            return {
                "position_id": position_id,
                "token": token,
                "correlations": [],
                "message": "Token not in correlation matrix",
            }

        # Get correlations for this token
        corr_matrix = np.array(corr_data["correlation_matrix"])
        token_idx = tokens.index(token)

        correlations = []
        for i, other_token in enumerate(tokens):
            if i != token_idx:
                correlations.append(
                    {
                        "token": other_token,
                        "correlation": round(float(corr_matrix[token_idx, i]), 4),
                        "abs_correlation": round(
                            float(abs(corr_matrix[token_idx, i])), 4
                        ),
                    }
                )

        # Sort by absolute correlation descending
        correlations.sort(key=lambda x: x["abs_correlation"], reverse=True)

        return {
            "position_id": position_id,
            "token": token,
            "correlations": correlations,
            "method": corr_data["method"],
            "timestamp": corr_data["timestamp"],
        }

    def health_check(self) -> dict[str, Any]:
        """Get API health status.

        Returns:
            Health status dictionary
        """
        import time

        start = time.time()

        # Quick check - can we get position count
        position_count = len(self.tracker.state.get_open_positions())

        latency_ms = (time.time() - start) * 1000

        return {
            "status": "healthy",
            "portfolio_id": self.tracker.portfolio_id,
            "latency_ms": round(latency_ms, 3),
            "open_positions": position_count,
            "cache_valid": self._is_cache_valid("correlation_matrix_pearson"),
        }


def create_correlation_routes(tracker: PortfolioTracker) -> list[dict[str, Any]]:
    """Create FastAPI route definitions for correlation API.

    Args:
        tracker: PortfolioTracker instance

    Returns:
        List of route definitions
    """
    api = CorrelationAPI(tracker)

    routes = [
        {
            "path": "/correlation/matrix",
            "method": "GET",
            "handler": api.get_correlation_matrix,
            "response_model": dict,
        },
        {
            "path": "/correlation/rolling",
            "method": "GET",
            "handler": api.get_rolling_correlations,
            "response_model": dict,
        },
        {
            "path": "/correlation/diversification",
            "method": "GET",
            "handler": api.get_diversification_metrics,
            "response_model": dict,
        },
        {
            "path": "/correlation/pair",
            "method": "GET",
            "handler": api.get_correlation_between_tokens,
            "response_model": dict,
        },
        {
            "path": "/correlation/position/{position_id}",
            "method": "GET",
            "handler": api.get_position_correlations,
            "response_model": dict,
        },
        {
            "path": "/correlation/health",
            "method": "GET",
            "handler": api.health_check,
            "response_model": dict,
        },
    ]

    return routes
