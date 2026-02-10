"""API endpoints for position sizing recommendations.

Provides FastAPI routes for position sizing calculations with
portfolio state integration.
"""

from __future__ import annotations

import logging
from typing import Any

from portfolio_risk.position_sizing.integration import (
    PositionSizingCache,
    PositionSizingIntegration,
)
from portfolio_risk.position_sizing.types import (
    KellyInputs,
    SizingMethod,
    VolatilityInputs,
)

logger = logging.getLogger(__name__)


class PositionSizingAPI:
    """API handler for position sizing endpoints.

    Provides methods for calculating and retrieving position sizing
    recommendations with portfolio state integration.
    """

    def __init__(
        self,
        integration: PositionSizingIntegration,
        enable_caching: bool = True,
    ):
        """Initialize position sizing API.

        Args:
            integration: Position sizing integration instance
            enable_caching: Whether to enable result caching
        """
        self.integration = integration
        self.enable_caching = enable_caching
        self._cache = PositionSizingCache(integration) if enable_caching else None

    def calculate_position_size(
        self,
        token: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        method: str = "fixed_fractional",
        risk_percentage: float | None = None,
        use_portfolio_state: bool = True,
        kelly_win_probability: float | None = None,
        kelly_win_loss_ratio: float | None = None,
        atr_value: float | None = None,
        atr_multiplier: float = 2.0,
        volatility_percent: float | None = None,
    ) -> dict[str, Any]:
        """Calculate position size for a trade.

        Args:
            token: Trading pair token (e.g., "BTC", "ETH")
            direction: Trade direction ("long" or "short")
            entry_price: Entry price for the trade
            stop_loss_price: Stop loss price
            method: Sizing method ("fixed_fractional", "kelly", "volatility_based")
            risk_percentage: Risk percentage (optional)
            use_portfolio_state: Whether to factor in portfolio state
            kelly_win_probability: Win probability for Kelly method (0-1)
            kelly_win_loss_ratio: Win/loss ratio for Kelly method
            atr_value: ATR value for volatility-based method
            atr_multiplier: ATR multiplier for volatility-based method
            volatility_percent: Volatility percentage for volatility-based method

        Returns:
            Dictionary with sizing recommendation
        """
        # Parse sizing method
        sizing_method = self._parse_sizing_method(method)

        # Prepare method-specific inputs
        kelly_inputs = None
        volatility_inputs = None

        if sizing_method == SizingMethod.KELLY_CRITERION:
            if kelly_win_probability is None or kelly_win_loss_ratio is None:
                raise ValueError(
                    "kelly_win_probability and kelly_win_loss_ratio required "
                    "for Kelly Criterion method"
                )
            kelly_inputs = KellyInputs(
                win_probability=kelly_win_probability,
                win_loss_ratio=kelly_win_loss_ratio,
            )

        elif sizing_method == SizingMethod.VOLATILITY_BASED:
            if atr_value is None:
                raise ValueError("atr_value required for volatility-based method")
            volatility_inputs = VolatilityInputs(
                atr_value=atr_value,
                atr_multiplier=atr_multiplier,
                volatility_percent=volatility_percent,
            )

        # Calculate sizing
        sizing = self.integration.calculate_sizing(
            token=token,
            direction=direction,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            method=sizing_method,
            risk_percentage=risk_percentage,
            kelly_inputs=kelly_inputs,
            volatility_inputs=volatility_inputs,
            use_portfolio_state=use_portfolio_state,
        )

        return sizing.to_dict()

    def get_position_size_for_signal(
        self,
        signal: Any,  # Signal type
        entry_price: float,
        stop_loss_price: float,
        method: str = "fixed_fractional",
        risk_percentage: float | None = None,
        use_portfolio_state: bool = True,
        kelly_inputs: KellyInputs | None = None,
        volatility_inputs: VolatilityInputs | None = None,
    ) -> dict[str, Any]:
        """Get position sizing for a signal.

        Args:
            signal: Trading signal object
            entry_price: Entry price
            stop_loss_price: Stop loss price
            method: Sizing method
            risk_percentage: Risk percentage
            use_portfolio_state: Whether to use portfolio state
            kelly_inputs: Kelly Criterion inputs
            volatility_inputs: Volatility inputs

        Returns:
            Dictionary with sizing recommendation
        """
        sizing_method = self._parse_sizing_method(method)

        sizing = self.integration.calculate_sizing_for_signal(
            signal=signal,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            method=sizing_method,
            risk_percentage=risk_percentage,
            kelly_inputs=kelly_inputs,
            volatility_inputs=volatility_inputs,
            use_portfolio_state=use_portfolio_state,
        )

        return sizing.to_dict()

    def get_portfolio_exposure(self) -> dict[str, Any] | None:
        """Get current portfolio exposure summary.

        Returns:
            Portfolio exposure dictionary or None
        """
        exposure = self.integration.get_portfolio_exposure()
        if not exposure:
            return None

        return {
            "total_equity": round(exposure.total_equity, 2),
            "available_equity": round(exposure.available_equity, 2),
            "margin_used": round(exposure.margin_used, 2),
            "total_exposure_usd": round(exposure.total_exposure_usd, 2),
            "exposure_pct": round(exposure.exposure_pct, 2),
            "open_position_count": exposure.open_position_count,
            "positions_by_token": {
                k: round(v, 2) for k, v in exposure.positions_by_token.items()
            },
        }

    def should_recalculate(self) -> bool:
        """Check if sizing should be recalculated.

        Returns:
            True if portfolio balance changed significantly
        """
        return self.integration.should_recalculate()

    def invalidate_cache(self) -> None:
        """Invalidate all cached sizing results."""
        if self._cache:
            self._cache.invalidate_all()
            logger.info("Position sizing cache invalidated")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache statistics dictionary
        """
        if not self._cache:
            return {"caching_enabled": False}

        return {
            "caching_enabled": True,
            **self._cache.get_cache_stats(),
        }

    def _parse_sizing_method(self, method: str) -> SizingMethod:
        """Parse sizing method string to enum.

        Args:
            method: Method string

        Returns:
            SizingMethod enum value

        Raises:
            ValueError: If method is unknown
        """
        method_map = {
            "fixed_fractional": SizingMethod.FIXED_FRACTIONAL,
            "kelly": SizingMethod.KELLY_CRITERION,
            "kelly_criterion": SizingMethod.KELLY_CRITERION,
            "volatility": SizingMethod.VOLATILITY_BASED,
            "volatility_based": SizingMethod.VOLATILITY_BASED,
            "atr": SizingMethod.VOLATILITY_BASED,
        }

        normalized = method.lower().replace(" ", "_")

        if normalized not in method_map:
            raise ValueError(
                f"Unknown sizing method: {method}. "
                f"Valid methods: {list(method_map.keys())}"
            )

        return method_map[normalized]


# FastAPI route factory
def create_position_sizing_routes(
    integration: PositionSizingIntegration,
    prefix: str = "/api/v1",
) -> list[dict[str, Any]]:
    """Create FastAPI route definitions for position sizing API.

    Args:
        integration: Position sizing integration instance
        prefix: API route prefix

    Returns:
        List of route definitions
    """
    api = PositionSizingAPI(integration)

    routes = [
        {
            "path": f"{prefix}/position-size",
            "method": "POST",
            "handler": _create_calculate_handler(api),
            "response_model": dict,
            "summary": "Calculate position size for a trade",
            "description": (
                "Calculate position sizing recommendation based on portfolio state, "
                "risk parameters, and chosen sizing method."
            ),
        },
        {
            "path": f"{prefix}/position-size/signal/{{signal_id}}",
            "method": "POST",
            "handler": _create_signal_handler(api),
            "response_model": dict,
            "summary": "Calculate position size for a signal",
            "description": "Calculate position sizing for an existing signal.",
        },
        {
            "path": f"{prefix}/position-size/portfolio-exposure",
            "method": "GET",
            "handler": _create_exposure_handler(api),
            "response_model": dict | None,
            "summary": "Get current portfolio exposure",
            "description": "Get summary of current portfolio exposure and positions.",
        },
        {
            "path": f"{prefix}/position-size/should-recalculate",
            "method": "GET",
            "handler": _create_recalculate_check_handler(api),
            "response_model": dict,
            "summary": "Check if sizing should be recalculated",
            "description": (
                "Returns true if portfolio balance has changed >5% since last sizing."
            ),
        },
        {
            "path": f"{prefix}/position-size/cache",
            "method": "DELETE",
            "handler": _create_invalidate_cache_handler(api),
            "response_model": dict,
            "summary": "Invalidate sizing cache",
            "description": "Clear all cached sizing calculations.",
        },
        {
            "path": f"{prefix}/position-size/cache/stats",
            "method": "GET",
            "handler": _create_cache_stats_handler(api),
            "response_model": dict,
            "summary": "Get cache statistics",
            "description": "Get statistics about the sizing cache.",
        },
    ]

    return routes


def _create_calculate_handler(api: PositionSizingAPI):
    """Create handler for POST /position-size."""

    async def handler(request: dict[str, Any]) -> dict[str, Any]:
        """Handle position size calculation request.

        Request body:
            token: Trading pair token
            direction: "long" or "short"
            entry_price: Entry price
            stop_loss_price: Stop loss price
            method: Sizing method (default: "fixed_fractional")
            risk_percentage: Risk percentage (optional)
            use_portfolio_state: Whether to use portfolio state (default: true)
            kelly_win_probability: For Kelly method
            kelly_win_loss_ratio: For Kelly method
            atr_value: For volatility method
            atr_multiplier: For volatility method (default: 2.0)
            volatility_percent: For volatility method

        Returns:
            Sizing recommendation
        """
        try:
            sizing = api.calculate_position_size(
                token=request["token"],
                direction=request["direction"],
                entry_price=float(request["entry_price"]),
                stop_loss_price=float(request["stop_loss_price"]),
                method=request.get("method", "fixed_fractional"),
                risk_percentage=request.get("risk_percentage"),
                use_portfolio_state=request.get("use_portfolio_state", True),
                kelly_win_probability=request.get("kelly_win_probability"),
                kelly_win_loss_ratio=request.get("kelly_win_loss_ratio"),
                atr_value=request.get("atr_value"),
                atr_multiplier=request.get("atr_multiplier", 2.0),
                volatility_percent=request.get("volatility_percent"),
            )

            return {
                "success": True,
                "data": sizing,
            }

        except ValueError as e:
            logger.warning(f"Invalid position sizing request: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": "validation_error",
            }
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return {
                "success": False,
                "error": "Internal error calculating position size",
                "error_type": "internal_error",
            }

    return handler


def _create_signal_handler(api: PositionSizingAPI):
    """Create handler for POST /position-size/signal/{signal_id}."""

    async def handler(signal_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Handle signal-based position size calculation.

        Args:
            signal_id: Signal identifier
            request: Request body with signal data

        Returns:
            Sizing recommendation
        """
        try:
            # Reconstruct signal from request
            from signal_generation.models import Signal

            signal = Signal(
                signal_id=signal_id,
                token=request["token"],
                direction=request["direction"],  # type: ignore
                confidence=request.get("confidence", 0.5),
                base_score=request.get("base_score", 50.0),
                timeframe=request.get("timeframe", "1h"),
                timestamp=request.get("timestamp"),
                metadata=request.get("metadata", {}),
            )

            # Parse Kelly inputs if provided
            kelly_inputs = None
            if "kelly" in request:
                kelly_data = request["kelly"]
                kelly_inputs = KellyInputs(
                    win_probability=kelly_data["win_probability"],
                    win_loss_ratio=kelly_data["win_loss_ratio"],
                )

            # Parse volatility inputs if provided
            volatility_inputs = None
            if "volatility" in request:
                vol_data = request["volatility"]
                volatility_inputs = VolatilityInputs(
                    atr_value=vol_data["atr_value"],
                    atr_multiplier=vol_data.get("atr_multiplier", 2.0),
                    volatility_percent=vol_data.get("volatility_percent"),
                )

            sizing = api.get_position_size_for_signal(
                signal=signal,
                entry_price=float(request["entry_price"]),
                stop_loss_price=float(request["stop_loss_price"]),
                method=request.get("method", "fixed_fractional"),
                risk_percentage=request.get("risk_percentage"),
                use_portfolio_state=request.get("use_portfolio_state", True),
                kelly_inputs=kelly_inputs,
                volatility_inputs=volatility_inputs,
            )

            return {
                "success": True,
                "data": sizing,
            }

        except ValueError as e:
            logger.warning(f"Invalid signal sizing request: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": "validation_error",
            }
        except Exception as e:
            logger.error(f"Error calculating signal position size: {e}")
            return {
                "success": False,
                "error": "Internal error calculating position size",
                "error_type": "internal_error",
            }

    return handler


def _create_exposure_handler(api: PositionSizingAPI):
    """Create handler for GET /position-size/portfolio-exposure."""

    async def handler() -> dict[str, Any]:
        """Get portfolio exposure summary."""
        exposure = api.get_portfolio_exposure()

        if exposure is None:
            return {
                "success": False,
                "error": "Portfolio tracker not available",
                "error_type": "not_available",
            }

        return {
            "success": True,
            "data": exposure,
        }

    return handler


def _create_recalculate_check_handler(api: PositionSizingAPI):
    """Create handler for GET /position-size/should-recalculate."""

    async def handler() -> dict[str, Any]:
        """Check if sizing should be recalculated."""
        should_recalc = api.should_recalculate()

        return {
            "success": True,
            "data": {
                "should_recalculate": should_recalc,
                "threshold_pct": PositionSizingIntegration.BALANCE_CHANGE_THRESHOLD_PCT,
            },
        }

    return handler


def _create_invalidate_cache_handler(api: PositionSizingAPI):
    """Create handler for DELETE /position-size/cache."""

    async def handler() -> dict[str, Any]:
        """Invalidate sizing cache."""
        api.invalidate_cache()

        return {
            "success": True,
            "message": "Cache invalidated successfully",
        }

    return handler


def _create_cache_stats_handler(api: PositionSizingAPI):
    """Create handler for GET /position-size/cache/stats."""

    async def handler() -> dict[str, Any]:
        """Get cache statistics."""
        stats = api.get_cache_stats()

        return {
            "success": True,
            "data": stats,
        }

    return handler
