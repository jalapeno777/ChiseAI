"""Position sizing integration with portfolio state and signals.

Provides automatic position sizing recommendations that factor in current
portfolio exposure, with recalculation triggers when portfolio balance
changes significantly (>5%).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC
from typing import TYPE_CHECKING, Any

# Import calculator at runtime (avoid circular import with __init__.py)
from portfolio_risk.position_sizing.calculator import PositionSizeCalculator
from portfolio_risk.position_sizing.types import (
    KellyInputs,
    PositionSizeResult,
    SizingConfig,
    SizingMethod,
    VolatilityInputs,
)

if TYPE_CHECKING:
    from portfolio.state_management.models import PortfolioState
    from portfolio.state_management.tracker import PortfolioTracker
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


@dataclass
class SizingRecommendation:
    """Complete position sizing recommendation for a signal.

    Attributes:
        signal_id: Signal identifier
        token: Trading pair token
        direction: Trade direction (long/short)
        entry_price: Entry price for the trade
        stop_loss_price: Stop loss price
        position_size: Suggested position size in base currency
        notional_value: Position value in USD
        risk_amount_usd: Risk amount in USD
        risk_percent: Risk as percentage of portfolio
        sizing_method: Method used for sizing calculation
        leverage_used: Leverage applied
        max_position_check: Whether position passes max position limits
        portfolio_exposure_pct: Current portfolio exposure percentage
        available_equity: Available equity for new positions
        total_equity: Total portfolio equity
        capped_by_limit: Whether sizing was capped by limits
        metadata: Additional calculation metadata
    """

    signal_id: str
    token: str
    direction: str
    entry_price: float
    stop_loss_price: float
    position_size: float
    notional_value: float
    risk_amount_usd: float
    risk_percent: float
    sizing_method: SizingMethod
    leverage_used: float
    max_position_check: bool
    portfolio_exposure_pct: float
    available_equity: float
    total_equity: float
    capped_by_limit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 2),
            "stop_loss_price": round(self.stop_loss_price, 2),
            "position_size": round(self.position_size, 6),
            "notional_value": round(self.notional_value, 2),
            "risk_amount_usd": round(self.risk_amount_usd, 2),
            "risk_percent": round(self.risk_percent, 2),
            "sizing_method": self.sizing_method.name if self.sizing_method else None,
            "leverage_used": round(self.leverage_used, 2),
            "max_position_check": self.max_position_check,
            "portfolio_exposure_pct": round(self.portfolio_exposure_pct, 2),
            "available_equity": round(self.available_equity, 2),
            "total_equity": round(self.total_equity, 2),
            "capped_by_limit": self.capped_by_limit,
            "metadata": self.metadata,
        }


@dataclass
class PortfolioExposure:
    """Current portfolio exposure summary.

    Attributes:
        total_equity: Total portfolio equity
        available_equity: Available equity for new positions
        margin_used: Total margin used
        total_exposure_usd: Total notional exposure across all positions
        exposure_pct: Portfolio exposure as percentage of equity
        open_position_count: Number of open positions
        positions_by_token: Exposure breakdown by token
    """

    total_equity: float
    available_equity: float
    margin_used: float
    total_exposure_usd: float
    exposure_pct: float
    open_position_count: int
    positions_by_token: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_portfolio_state(cls, state: PortfolioState) -> PortfolioExposure:
        """Create exposure summary from portfolio state.

        Args:
            state: Current portfolio state

        Returns:
            PortfolioExposure summary
        """
        total_exposure = sum(
            pos.notional_value for pos in state.positions.values() if pos.is_open
        )

        positions_by_token: dict[str, float] = {}
        for pos in state.positions.values():
            if pos.is_open:
                positions_by_token[pos.token] = (
                    positions_by_token.get(pos.token, 0.0) + pos.notional_value
                )

        exposure_pct = (
            (total_exposure / state.total_equity * 100)
            if state.total_equity > 0
            else 0.0
        )

        return cls(
            total_equity=state.total_equity,
            available_equity=state.available_equity,
            margin_used=state.margin_used,
            total_exposure_usd=total_exposure,
            exposure_pct=exposure_pct,
            open_position_count=len(state.get_open_positions()),
            positions_by_token=positions_by_token,
        )


class PositionSizingIntegration:
    """Integrates position sizing with portfolio state.

    Provides automatic position sizing recommendations that factor in:
    - Current portfolio exposure
    - Available equity
    - Existing positions
    - Risk limits and constraints

    Automatically recalculates sizing when portfolio balance changes >5%.
    """

    # Threshold for portfolio balance change that triggers recalculation
    BALANCE_CHANGE_THRESHOLD_PCT = 5.0

    def __init__(
        self,
        portfolio_tracker: PortfolioTracker | None = None,
        config: SizingConfig | None = None,
        default_method: SizingMethod = SizingMethod.FIXED_FRACTIONAL,
    ):
        """Initialize position sizing integration.

        Args:
            portfolio_tracker: Portfolio tracker for state access
            config: Sizing configuration
            default_method: Default sizing method to use
        """
        self.portfolio_tracker = portfolio_tracker
        self.config = config or SizingConfig()
        self.default_method = default_method
        self._calculator = PositionSizeCalculator(self.config)

        # Cache for last portfolio equity to detect significant changes
        self._last_portfolio_equity: float = 0.0
        self._last_sizing_time: float = 0.0

        # Initialize equity from tracker if available
        if portfolio_tracker:
            self._last_portfolio_equity = portfolio_tracker.state.total_equity

    def set_portfolio_tracker(self, tracker: PortfolioTracker) -> None:
        """Set or update the portfolio tracker.

        Args:
            tracker: Portfolio tracker instance
        """
        self.portfolio_tracker = tracker
        if tracker:
            self._last_portfolio_equity = tracker.state.total_equity

    def get_portfolio_exposure(self) -> PortfolioExposure | None:
        """Get current portfolio exposure summary.

        Returns:
            PortfolioExposure or None if no tracker available
        """
        if not self.portfolio_tracker:
            return None

        return PortfolioExposure.from_portfolio_state(self.portfolio_tracker.state)

    def should_recalculate(self) -> bool:
        """Check if sizing should be recalculated due to portfolio changes.

        Returns:
            True if portfolio balance changed >5% since last sizing
        """
        if not self.portfolio_tracker:
            return False

        current_equity = self.portfolio_tracker.state.total_equity

        if self._last_portfolio_equity == 0:
            # First calculation
            self._last_portfolio_equity = current_equity
            return True

        change_pct = (
            abs(current_equity - self._last_portfolio_equity)
            / self._last_portfolio_equity
            * 100
        )

        return change_pct > self.BALANCE_CHANGE_THRESHOLD_PCT

    def calculate_sizing_for_signal(
        self,
        signal: Signal,
        entry_price: float,
        stop_loss_price: float,
        method: SizingMethod | None = None,
        risk_percentage: float | None = None,
        kelly_inputs: KellyInputs | None = None,
        volatility_inputs: VolatilityInputs | None = None,
        use_portfolio_state: bool = True,
    ) -> SizingRecommendation:
        """Calculate position sizing recommendation for a signal.

        Automatically factors in current portfolio exposure if portfolio
        tracker is available.

        Args:
            signal: Trading signal
            entry_price: Entry price for the trade
            stop_loss_price: Stop loss price
            method: Sizing method (uses default if None)
            risk_percentage: Risk percentage (uses config default if None)
            kelly_inputs: Kelly Criterion inputs (for Kelly method)
            volatility_inputs: Volatility inputs (for volatility method)
            use_portfolio_state: Whether to factor in portfolio state

        Returns:
            SizingRecommendation with complete sizing details
        """
        method = method or self.default_method

        # Get portfolio state if available
        portfolio_exposure = None
        account_balance = 10_000.0  # Default fallback

        if use_portfolio_state and self.portfolio_tracker:
            portfolio_exposure = self.get_portfolio_exposure()
            if portfolio_exposure:
                account_balance = portfolio_exposure.total_equity

        # Adjust risk based on portfolio exposure
        adjusted_risk_pct = self._adjust_risk_for_exposure(
            risk_percentage or self.config.default_risk_pct,
            portfolio_exposure,
        )

        # Calculate position size
        direction = (
            signal.direction.value
            if hasattr(signal.direction, "value")
            else str(signal.direction)
        )

        result = self._calculator.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            method=method,
            risk_percentage=adjusted_risk_pct,
            kelly_inputs=kelly_inputs,
            volatility_inputs=volatility_inputs,
            direction=direction,
        )

        # Validate against position limits
        existing_positions = (
            self._get_existing_position_results() if use_portfolio_state else None
        )
        is_valid, validation_reason = self._calculator.validate_position_limits(
            result,
            account_balance=account_balance,
            existing_positions=existing_positions,
        )

        # Update last sizing tracking
        self._last_portfolio_equity = account_balance
        self._last_sizing_time = time.time()

        # Build recommendation
        exposure_pct = portfolio_exposure.exposure_pct if portfolio_exposure else 0.0
        available_equity = (
            portfolio_exposure.available_equity
            if portfolio_exposure
            else account_balance
        )

        return SizingRecommendation(
            signal_id=signal.signal_id,
            token=signal.token,
            direction=direction,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            position_size=result.position_size,
            notional_value=result.notional_value,
            risk_amount_usd=result.risk_amount,
            risk_percent=result.risk_percentage,
            sizing_method=result.method_used,
            leverage_used=result.leverage_used,
            max_position_check=is_valid,
            portfolio_exposure_pct=exposure_pct,
            available_equity=available_equity,
            total_equity=account_balance,
            capped_by_limit=result.capped_by_limit,
            metadata={
                "validation_reason": validation_reason,
                "requested_risk_pct": risk_percentage,
                "adjusted_risk_pct": adjusted_risk_pct,
                "sizing_result_metadata": result.metadata,
            },
        )

    def calculate_sizing(
        self,
        token: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        method: SizingMethod | None = None,
        risk_percentage: float | None = None,
        kelly_inputs: KellyInputs | None = None,
        volatility_inputs: VolatilityInputs | None = None,
        use_portfolio_state: bool = True,
    ) -> SizingRecommendation:
        """Calculate position sizing without a signal object.

        Args:
            token: Trading pair token
            direction: Trade direction (long/short)
            entry_price: Entry price
            stop_loss_price: Stop loss price
            method: Sizing method
            risk_percentage: Risk percentage
            kelly_inputs: Kelly Criterion inputs
            volatility_inputs: Volatility inputs
            use_portfolio_state: Whether to use portfolio state

        Returns:
            SizingRecommendation
        """
        from datetime import datetime

        from signal_generation.models import Signal, SignalDirection, SignalStatus

        # Create a minimal signal for the calculation
        signal = Signal(
            signal_id=f"manual_{token}_{int(time.time())}",
            token=token,
            direction=SignalDirection(direction.lower()),
            confidence=0.5,
            base_score=50.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
        )

        return self.calculate_sizing_for_signal(
            signal=signal,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            method=method,
            risk_percentage=risk_percentage,
            kelly_inputs=kelly_inputs,
            volatility_inputs=volatility_inputs,
            use_portfolio_state=use_portfolio_state,
        )

    def _adjust_risk_for_exposure(
        self,
        base_risk_pct: float,
        exposure: PortfolioExposure | None,
    ) -> float:
        """Adjust risk percentage based on current portfolio exposure.

        Reduces risk when portfolio is heavily exposed.

        Args:
            base_risk_pct: Base risk percentage
            exposure: Current portfolio exposure

        Returns:
            Adjusted risk percentage
        """
        if not exposure or exposure.total_equity == 0:
            return base_risk_pct

        # Reduce risk as exposure increases
        exposure_pct = exposure.exposure_pct

        if exposure_pct > 80:
            # High exposure (>80%): reduce risk by 50%
            return base_risk_pct * 0.5
        elif exposure_pct > 50:
            # Medium exposure (50-80%): reduce risk by 25%
            return base_risk_pct * 0.75
        elif exposure_pct > 30:
            # Moderate exposure (30-50%): reduce risk by 10%
            return base_risk_pct * 0.9

        return base_risk_pct

    def _get_existing_position_results(self) -> list[PositionSizeResult]:
        """Get existing positions as PositionSizeResult objects for validation.

        Returns:
            List of PositionSizeResult for existing positions
        """
        if not self.portfolio_tracker:
            return []

        results = []
        for pos in self.portfolio_tracker.state.get_open_positions():
            # Estimate risk amount based on position size and typical stop distance
            # In practice, this would use actual stop loss data from positions
            notional = pos.notional_value
            # Assume 2% stop distance for risk estimation
            estimated_risk_pct = 2.0
            risk_amount = notional * (estimated_risk_pct / 100)

            result = PositionSizeResult(
                position_size=pos.quantity,
                notional_value=notional,
                risk_amount=risk_amount,
                risk_percentage=(
                    (risk_amount / self.portfolio_tracker.state.total_equity * 100)
                    if self.portfolio_tracker.state.total_equity > 0
                    else 0.0
                ),
                method_used=SizingMethod.FIXED_FRACTIONAL,
                leverage_used=pos.leverage,
            )
            results.append(result)

        return results


class PositionSizingCache:
    """Cache for position sizing recommendations with invalidation logic.

    Caches sizing recommendations and invalidates them when:
    - Portfolio balance changes >5%
    - Signal parameters change
    - Explicit invalidation is requested
    """

    def __init__(self, integration: PositionSizingIntegration):
        """Initialize cache.

        Args:
            integration: Position sizing integration instance
        """
        self.integration = integration
        self._cache: dict[str, SizingRecommendation] = {}
        self._cache_timestamp: dict[str, float] = {}
        self._cache_portfolio_equity: dict[str, float] = {}

    def get_cached_sizing(
        self,
        cache_key: str,
        signal: Signal,
        entry_price: float,
        stop_loss_price: float,
        **kwargs,
    ) -> SizingRecommendation | None:
        """Get cached sizing if still valid.

        Args:
            cache_key: Unique cache key
            signal: Trading signal
            entry_price: Entry price
            stop_loss_price: Stop loss price
            **kwargs: Additional parameters for sizing calculation

        Returns:
            Cached SizingRecommendation or None if invalid/expired
        """
        if cache_key not in self._cache:
            return None

        cached = self._cache[cache_key]
        cached_equity = self._cache_portfolio_equity.get(cache_key, 0)

        # Check if portfolio equity changed significantly
        if self.integration.portfolio_tracker:
            current_equity = self.integration.portfolio_tracker.state.total_equity
            if cached_equity > 0:
                change_pct = abs(current_equity - cached_equity) / cached_equity * 100
                if change_pct > PositionSizingIntegration.BALANCE_CHANGE_THRESHOLD_PCT:
                    # Invalidate cache due to portfolio change
                    self.invalidate(cache_key)
                    return None

        return cached

    def cache_sizing(
        self,
        cache_key: str,
        sizing: SizingRecommendation,
    ) -> None:
        """Cache a sizing recommendation.

        Args:
            cache_key: Unique cache key
            sizing: Sizing recommendation to cache
        """
        self._cache[cache_key] = sizing
        self._cache_timestamp[cache_key] = time.time()

        if self.integration.portfolio_tracker:
            self._cache_portfolio_equity[cache_key] = (
                self.integration.portfolio_tracker.state.total_equity
            )

    def invalidate(self, cache_key: str) -> None:
        """Invalidate a cached sizing.

        Args:
            cache_key: Cache key to invalidate
        """
        self._cache.pop(cache_key, None)
        self._cache_timestamp.pop(cache_key, None)
        self._cache_portfolio_equity.pop(cache_key, None)

    def invalidate_all(self) -> None:
        """Invalidate all cached sizings."""
        self._cache.clear()
        self._cache_timestamp.clear()
        self._cache_portfolio_equity.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "cached_items": len(self._cache),
            "cache_keys": list(self._cache.keys()),
        }
