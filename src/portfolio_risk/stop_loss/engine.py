"""Stop-loss calculation engine.

Provides multiple stop-loss calculation methods:
- ATR-based stops (volatility-adjusted)
- Technical level stops (support/resistance)
- Percentage-based stops (configurable)

Includes risk:reward validation and optimal stop selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from portfolio_risk.stop_loss.atr_indicator import ATR

if TYPE_CHECKING:
    from dashboard.key_levels import KeyLevel, KeyLevelsResult
    from data_ingestion.ohlcv_fetcher import OHLCVData

from data_ingestion.ohlcv_fetcher import OHLCVData


class StopLossMethod(Enum):
    """Available stop-loss calculation methods."""

    ATR = "atr"
    TECHNICAL_LEVEL = "technical_level"
    PERCENTAGE = "percentage"


class TradeDirection(Enum):
    """Direction of the trade."""

    LONG = "long"
    SHORT = "short"


@dataclass
class StopLossResult:
    """Result of a stop-loss calculation.

    Attributes:
        stop_price: The calculated stop-loss price
        method: Method used for calculation
        distance_pct: Distance from entry price as percentage
        risk_reward_ratio: Calculated risk:reward ratio
        is_valid: Whether the stop meets minimum criteria
        rationale: Human-readable explanation
        metadata: Additional calculation details
    """

    stop_price: float
    method: StopLossMethod
    distance_pct: float
    risk_reward_ratio: float
    is_valid: bool
    rationale: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "stop_price": round(self.stop_price, 2),
            "method": self.method.value,
            "distance_pct": round(self.distance_pct, 4),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "is_valid": self.is_valid,
            "rationale": self.rationale,
            "metadata": self.metadata,
        }


@dataclass
class StopLossComparison:
    """Comparison of multiple stop-loss methods.

    Attributes:
        results: List of all calculated stop-loss results
        optimal: The selected optimal stop-loss result
        selection_rationale: Why this stop was selected
    """

    results: list[StopLossResult]
    optimal: StopLossResult | None
    selection_rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "results": [r.to_dict() for r in self.results],
            "optimal": self.optimal.to_dict() if self.optimal else None,
            "selection_rationale": self.selection_rationale,
        }


class StopLossEngine:
    """Engine for calculating stop-losses using multiple methods.

    Supports three calculation methods:
    1. ATR-based: Uses 2× ATR(14) from entry price
    2. Technical level: Uses nearest support (long) / resistance (short)
    3. Percentage-based: Uses configurable percentage (default 2-5%)

    All methods validate against minimum risk:reward ratio (default 1:1.5).

    Example:
        engine = StopLossEngine()

        # Calculate ATR-based stop
        result = engine.atr_based_stop(
            entry_price=50000,
            direction=TradeDirection.LONG,
            ohlcv_data=data
        )

        # Compare all methods
        comparison = engine.compare_methods(
            entry_price=50000,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels_result
        )
    """

    # Default configuration
    DEFAULT_ATR_PERIOD = 14
    DEFAULT_ATR_MULTIPLIER = 2.0
    DEFAULT_MIN_RISK_REWARD = 1.5
    DEFAULT_DEFAULT_PERCENTAGE = 0.03  # 3%
    DEFAULT_MIN_PERCENTAGE = 0.02  # 2%
    DEFAULT_MAX_PERCENTAGE = 0.05  # 5%
    DEFAULT_MAX_DRAWDOWN_PCT = 0.15  # 15% kill-switch

    # Level weights for technical stops (from MEMORY_CONTEXT)
    LEVEL_WEIGHTS = {
        "swing": 1.0,
        "pivot": 0.8,
        "round_number": 0.5,
    }

    def __init__(
        self,
        atr_period: int = DEFAULT_ATR_PERIOD,
        atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
        min_risk_reward: float = DEFAULT_MIN_RISK_REWARD,
        default_percentage: float = DEFAULT_DEFAULT_PERCENTAGE,
        min_percentage: float = DEFAULT_MIN_PERCENTAGE,
        max_percentage: float = DEFAULT_MAX_PERCENTAGE,
        max_drawdown_pct: float = DEFAULT_MAX_DRAWDOWN_PCT,
    ):
        """Initialize stop-loss engine.

        Args:
            atr_period: Period for ATR calculation (default: 14)
            atr_multiplier: Multiplier for ATR-based stops (default: 2.0)
            min_risk_reward: Minimum risk:reward ratio (default: 1.5)
            default_percentage: Default percentage for pct-based stops (default: 0.03)
            min_percentage: Minimum percentage for pct-based stops (default: 0.02)
            max_percentage: Maximum percentage for pct-based stops (default: 0.05)
            max_drawdown_pct: Maximum drawdown before kill-switch (default: 0.15)
        """
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.min_risk_reward = min_risk_reward
        self.default_percentage = default_percentage
        self.min_percentage = min_percentage
        self.max_percentage = max_percentage
        self.max_drawdown_pct = max_drawdown_pct

        self._atr_calculator = ATR(period=atr_period)

    def _validate_stop_direction(
        self,
        entry_price: float,
        stop_price: float,
        direction: TradeDirection,
    ) -> None:
        """Validate that stop price is on the correct side of entry for trade direction.

        For LONG positions: stop_loss_price must be < entry_price
        For SHORT positions: stop_loss_price must be > entry_price

        Args:
            entry_price: Entry price for the trade
            stop_price: Calculated stop-loss price
            direction: Trade direction (LONG or SHORT)

        Raises:
            ValueError: If stop price is on the wrong side of entry
        """
        if direction == TradeDirection.LONG:
            if stop_price >= entry_price:
                raise ValueError(
                    f"Invalid stop-loss for LONG position: "
                    f"stop_price ({stop_price:.2f}) must be below "
                    f"entry_price ({entry_price:.2f})"
                )
        else:  # SHORT
            if stop_price <= entry_price:
                raise ValueError(
                    f"Invalid stop-loss for SHORT position: "
                    f"stop_price ({stop_price:.2f}) must be above "
                    f"entry_price ({entry_price:.2f})"
                )

    def _validate_stop_price_positive(
        self,
        stop_price: float,
        stop_distance: float,
    ) -> None:
        """Validate that stop price is positive and stop distance is non-negative.

        Args:
            stop_price: Calculated stop-loss price
            stop_distance: Distance from entry to stop

        Raises:
            ValueError: If stop_price <= 0 or stop_distance < 0
        """
        if stop_price <= 0:
            raise ValueError(
                f"Invalid stop-loss price: {stop_price:.2f} (must be positive)"
            )
        if stop_distance < 0:
            raise ValueError(
                f"Invalid stop distance: {stop_distance:.2f} (must be non-negative)"
            )

    def atr_based_stop(
        self,
        entry_price: float,
        direction: TradeDirection,
        ohlcv_data: list[OHLCVData],
        target_price: float | None = None,
    ) -> StopLossResult:
        """Calculate ATR-based stop-loss.

        Uses 2× ATR(14) from entry price as stop distance.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            ohlcv_data: OHLCV data for ATR calculation
            target_price: Optional target price for R:R calculation

        Returns:
            StopLossResult with calculated stop price
        """
        try:
            atr_result = self._atr_calculator.calculate(ohlcv_data)
        except ValueError as e:
            return StopLossResult(
                stop_price=0.0,
                method=StopLossMethod.ATR,
                distance_pct=0.0,
                risk_reward_ratio=0.0,
                is_valid=False,
                rationale=f"ATR calculation failed: {e}",
                metadata={"error": str(e)},
            )

        # Calculate stop distance
        stop_distance = atr_result.current * self.atr_multiplier

        # Calculate stop price based on direction
        if direction == TradeDirection.LONG:
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance

        # CRITICAL-001 & CRITICAL-003: Validate stop price
        self._validate_stop_price_positive(stop_price, stop_distance)
        self._validate_stop_direction(entry_price, stop_price, direction)

        # Calculate distance percentage
        distance_pct = stop_distance / entry_price

        # Calculate risk:reward ratio
        risk_reward = self._calculate_risk_reward(entry_price, stop_price, target_price)

        # Validate against constraints
        is_valid = self._validate_stop(
            distance_pct=distance_pct,
            risk_reward=risk_reward,
        )

        rationale = (
            f"ATR({self.atr_period})={atr_result.current:.2f} × "
            f"{self.atr_multiplier} = {stop_distance:.2f}"
        )

        if not is_valid:
            if risk_reward < self.min_risk_reward:
                rationale += (
                    f". Fails R:R requirement ({risk_reward:.2f} < "
                    f"{self.min_risk_reward})"
                )
            if distance_pct > self.max_drawdown_pct:
                rationale += (
                    f". Exceeds max drawdown ({distance_pct:.2%} > "
                    f"{self.max_drawdown_pct:.2%})"
                )

        return StopLossResult(
            stop_price=stop_price,
            method=StopLossMethod.ATR,
            distance_pct=distance_pct,
            risk_reward_ratio=risk_reward,
            is_valid=is_valid,
            rationale=rationale,
            metadata={
                "atr_value": atr_result.current,
                "atr_period": self.atr_period,
                "atr_multiplier": self.atr_multiplier,
            },
        )

    def technical_level_stop(
        self,
        entry_price: float,
        direction: TradeDirection,
        key_levels: KeyLevelsResult,
        target_price: float | None = None,
    ) -> StopLossResult:
        """Calculate technical level-based stop-loss.

        Uses nearest support (for longs) or resistance (for shorts).
        Considers level strength and confluence scores.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            key_levels: KeyLevelsResult from KeyLevelsAnalyzer
            target_price: Optional target price for R:R calculation

        Returns:
            StopLossResult with calculated stop price
        """
        # Select appropriate level based on direction
        if direction == TradeDirection.LONG:
            level = key_levels.nearest_support
            level_type = "support"
        else:
            level = key_levels.nearest_resistance
            level_type = "resistance"

        if level is None:
            return StopLossResult(
                stop_price=0.0,
                method=StopLossMethod.TECHNICAL_LEVEL,
                distance_pct=0.0,
                risk_reward_ratio=0.0,
                is_valid=False,
                rationale=f"No {level_type} level found",
                metadata={"level_type": level_type},
            )

        # CRITICAL-002: Validate that level is on correct side of entry
        # For LONG: support must be below entry (price < entry)
        # For SHORT: resistance must be above entry (price > entry)
        if direction == TradeDirection.LONG:
            if level.price >= entry_price:
                raise ValueError(
                    f"Invalid support level for LONG position: "
                    f"level price ({level.price:.2f}) must be below "
                    f"entry price ({entry_price:.2f})"
                )
        else:  # SHORT
            if level.price <= entry_price:
                raise ValueError(
                    f"Invalid resistance level for SHORT position: "
                    f"level price ({level.price:.2f}) must be above "
                    f"entry price ({entry_price:.2f})"
                )

        # For longs, stop is below support (give some buffer)
        # For shorts, stop is above resistance (give some buffer)
        buffer_pct = 0.005  # 0.5% buffer beyond level

        if direction == TradeDirection.LONG:
            stop_price = level.price * (1 - buffer_pct)
        else:
            stop_price = level.price * (1 + buffer_pct)

        # Calculate distance percentage
        stop_distance = abs(entry_price - stop_price)
        distance_pct = stop_distance / entry_price

        # CRITICAL-003: Validate stop price is positive
        self._validate_stop_price_positive(stop_price, stop_distance)

        # Calculate risk:reward ratio
        risk_reward = self._calculate_risk_reward(entry_price, stop_price, target_price)

        # Validate against constraints
        is_valid = self._validate_stop(
            distance_pct=distance_pct,
            risk_reward=risk_reward,
        )

        # Determine level weight category
        weight_category = self._get_level_weight_category(level)
        level_weight = self.LEVEL_WEIGHTS.get(weight_category, 0.5)

        rationale = (
            f"{level_type.capitalize()} level at {level.price:.2f} "
            f"(strength={level.strength:.1f}, "
            f"confluence={level.confluence_score:.1f}, "
            f"weight={level_weight})"
        )

        if not is_valid:
            if risk_reward < self.min_risk_reward:
                rationale += (
                    f". Fails R:R requirement ({risk_reward:.2f} < "
                    f"{self.min_risk_reward})"
                )
            if distance_pct > self.max_drawdown_pct:
                rationale += (
                    f". Exceeds max drawdown ({distance_pct:.2%} > "
                    f"{self.max_drawdown_pct:.2%})"
                )

        return StopLossResult(
            stop_price=stop_price,
            method=StopLossMethod.TECHNICAL_LEVEL,
            distance_pct=distance_pct,
            risk_reward_ratio=risk_reward,
            is_valid=is_valid,
            rationale=rationale,
            metadata={
                "level_price": level.price,
                "level_strength": level.strength,
                "level_confluence": level.confluence_score,
                "level_type": level_type,
                "level_weight": level_weight,
                "buffer_pct": buffer_pct,
            },
        )

    def percentage_based_stop(
        self,
        entry_price: float,
        direction: TradeDirection,
        percentage: float | None = None,
        target_price: float | None = None,
    ) -> StopLossResult:
        """Calculate percentage-based stop-loss.

        Uses configurable percentage from entry price.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            percentage: Percentage distance (default: 3%, clamped to 2-5%)
            target_price: Optional target price for R:R calculation

        Returns:
            StopLossResult with calculated stop price
        """
        # Use default if not provided, clamp to valid range
        if percentage is None:
            pct = self.default_percentage
        else:
            pct = max(self.min_percentage, min(self.max_percentage, percentage))

        # Calculate stop distance
        stop_distance = entry_price * pct

        # Calculate stop price based on direction
        if direction == TradeDirection.LONG:
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance

        # CRITICAL-001 & CRITICAL-003: Validate stop price
        self._validate_stop_price_positive(stop_price, stop_distance)
        self._validate_stop_direction(entry_price, stop_price, direction)

        # Calculate risk:reward ratio
        risk_reward = self._calculate_risk_reward(entry_price, stop_price, target_price)

        # Validate against constraints
        is_valid = self._validate_stop(
            distance_pct=pct,
            risk_reward=risk_reward,
        )

        rationale = f"{pct:.2%} from entry"
        if percentage is not None and pct != percentage:
            rationale += f" (clamped from {percentage:.2%})"

        if not is_valid:
            if risk_reward < self.min_risk_reward:
                rationale += (
                    f". Fails R:R requirement ({risk_reward:.2f} < "
                    f"{self.min_risk_reward})"
                )
            if pct > self.max_drawdown_pct:
                rationale += (
                    f". Exceeds max drawdown ({pct:.2%} > {self.max_drawdown_pct:.2%})"
                )

        return StopLossResult(
            stop_price=stop_price,
            method=StopLossMethod.PERCENTAGE,
            distance_pct=pct,
            risk_reward_ratio=risk_reward,
            is_valid=is_valid,
            rationale=rationale,
            metadata={
                "requested_percentage": percentage,
                "applied_percentage": pct,
                "min_percentage": self.min_percentage,
                "max_percentage": self.max_percentage,
            },
        )

    def compare_methods(
        self,
        entry_price: float,
        direction: TradeDirection,
        ohlcv_data: list[OHLCVData],
        key_levels: KeyLevelsResult,
        target_price: float | None = None,
        percentage: float | None = None,
    ) -> StopLossComparison:
        """Compare all stop-loss methods and select optimal.

        Calculates stops using all three methods and selects the
        optimal one based on risk:reward ratio and validity.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            ohlcv_data: OHLCV data for ATR calculation
            key_levels: KeyLevelsResult for technical levels
            target_price: Optional target price for R:R calculation
            percentage: Optional percentage for pct-based stop

        Returns:
            StopLossComparison with all results and optimal selection
        """
        # Calculate all three methods
        atr_result = self.atr_based_stop(
            entry_price, direction, ohlcv_data, target_price
        )

        tech_result = self.technical_level_stop(
            entry_price, direction, key_levels, target_price
        )

        pct_result = self.percentage_based_stop(
            entry_price, direction, percentage, target_price
        )

        results = [atr_result, tech_result, pct_result]

        # Select optimal stop
        optimal, rationale = self._select_optimal(results)

        return StopLossComparison(
            results=results,
            optimal=optimal,
            selection_rationale=rationale,
        )

    def _calculate_risk_reward(
        self,
        entry_price: float,
        stop_price: float,
        target_price: float | None,
    ) -> float:
        """Calculate risk:reward ratio.

        Args:
            entry_price: Entry price
            stop_price: Stop-loss price
            target_price: Target price (optional)

        Returns:
            Risk:reward ratio (0.0 if no target provided)
        """
        if target_price is None:
            return 0.0

        risk = abs(entry_price - stop_price)
        reward = abs(target_price - entry_price)

        if risk == 0:
            return 0.0

        return reward / risk

    def _validate_stop(
        self,
        distance_pct: float,
        risk_reward: float,
    ) -> bool:
        """Validate stop-loss against constraints.

        Args:
            distance_pct: Stop distance as percentage
            risk_reward: Risk:reward ratio

        Returns:
            True if stop is valid, False otherwise
        """
        # Check max drawdown (kill-switch)
        if distance_pct > self.max_drawdown_pct:
            return False

        # Check minimum risk:reward ratio (only if target provided)
        return not (risk_reward > 0 and risk_reward < self.min_risk_reward)

    def _get_level_weight_category(self, level: KeyLevel) -> str:
        """Determine weight category for a key level.

        Args:
            level: KeyLevel to categorize

        Returns:
            Weight category string
        """
        description_lower = level.description.lower()

        if "swing" in description_lower:
            return "swing"
        elif "pivot" in description_lower or "previous" in description_lower:
            return "pivot"
        elif "round" in description_lower:
            return "round_number"
        else:
            return "other"

    def _select_optimal(
        self,
        results: list[StopLossResult],
    ) -> tuple[StopLossResult | None, str]:
        """Select optimal stop from multiple results.

        Selection criteria:
        1. Must be valid (passes R:R and drawdown constraints)
        2. Highest risk:reward ratio among valid stops
        3. If tied, prefer technical level > ATR > percentage

        Args:
            results: List of stop-loss results

        Returns:
            Tuple of (optimal result or None, selection rationale)
        """
        valid_results = [r for r in results if r.is_valid]

        if not valid_results:
            # No valid stops, return the one with best R:R
            best = max(results, key=lambda r: r.risk_reward_ratio)
            return (
                None,
                f"No valid stops. Best R:R was {best.risk_reward_ratio:.2f} "
                f"using {best.method.value}",
            )

        # Sort by risk:reward ratio (descending), then by method preference
        method_preference = {
            StopLossMethod.TECHNICAL_LEVEL: 0,
            StopLossMethod.ATR: 1,
            StopLossMethod.PERCENTAGE: 2,
        }

        valid_results.sort(
            key=lambda r: (-r.risk_reward_ratio, method_preference.get(r.method, 3))
        )

        optimal = valid_results[0]

        rationale = (
            f"Selected {optimal.method.value} stop with "
            f"R:R={optimal.risk_reward_ratio:.2f} "
            f"({len(valid_results)} valid options)"
        )

        return optimal, rationale
