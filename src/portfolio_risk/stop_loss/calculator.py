"""Main stop-loss calculator interface.

Provides a unified interface for calculating stop-losses with
support for multiple methods and automatic optimal selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from portfolio_risk.stop_loss.engine import (
    StopLossComparison,
    StopLossEngine,
    StopLossMethod,
    StopLossResult,
    TradeDirection,
)

if TYPE_CHECKING:
    from dashboard.key_levels import KeyLevelsResult
    from data_ingestion.ohlcv_fetcher import OHLCVData


@dataclass
class StopLossConfig:
    """Configuration for stop-loss calculation.

    Attributes:
        method: Preferred calculation method (default: automatic selection)
        atr_period: Period for ATR calculation (default: 14)
        atr_multiplier: Multiplier for ATR-based stops (default: 2.0)
        min_risk_reward: Minimum risk:reward ratio (default: 1.5)
        default_percentage: Default percentage for pct stops (default: 0.03)
        min_percentage: Minimum percentage (default: 0.02)
        max_percentage: Maximum percentage (default: 0.05)
        max_drawdown_pct: Maximum drawdown kill-switch (default: 0.15)
    """

    method: StopLossMethod | None = None
    atr_period: int = 14
    atr_multiplier: float = 2.0
    min_risk_reward: float = 1.5
    default_percentage: float = 0.03
    min_percentage: float = 0.02
    max_percentage: float = 0.05
    max_drawdown_pct: float = 0.15

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "method": self.method.value if self.method else "auto",
            "atr_period": self.atr_period,
            "atr_multiplier": self.atr_multiplier,
            "min_risk_reward": self.min_risk_reward,
            "default_percentage": self.default_percentage,
            "min_percentage": self.min_percentage,
            "max_percentage": self.max_percentage,
            "max_drawdown_pct": self.max_drawdown_pct,
        }


@dataclass
class StopLossCalculation:
    """Complete stop-loss calculation result.

    Attributes:
        entry_price: Entry price for the trade
        direction: Trade direction
        target_price: Target price (if provided)
        config: Configuration used for calculation
        comparison: Comparison of all methods
        selected_stop: The selected stop-loss result
        risk_amount: Absolute risk amount in price terms
        risk_pct: Risk as percentage of entry
    """

    entry_price: float
    direction: TradeDirection
    target_price: float | None
    config: StopLossConfig
    comparison: StopLossComparison
    selected_stop: StopLossResult
    risk_amount: float = field(init=False)
    risk_pct: float = field(init=False)

    def __post_init__(self) -> None:
        """Calculate derived risk metrics."""
        self.risk_amount = abs(self.entry_price - self.selected_stop.stop_price)
        self.risk_pct = self.risk_amount / self.entry_price if self.entry_price else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entry_price": round(self.entry_price, 2),
            "direction": self.direction.value,
            "target_price": round(self.target_price, 2) if self.target_price else None,
            "config": self.config.to_dict(),
            "comparison": self.comparison.to_dict(),
            "selected_stop": self.selected_stop.to_dict(),
            "risk_amount": round(self.risk_amount, 2),
            "risk_pct": round(self.risk_pct, 4),
        }


class StopLossCalculator:
    """Main calculator for stop-loss calculations.

    Provides a unified interface for calculating stop-losses with
    support for multiple methods and automatic optimal selection.

    Example:
        calculator = StopLossCalculator()

        # Simple calculation with automatic method selection
        result = calculator.calculate_stop_loss(
            entry_price=50000,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels
        )

        # Use specific method
        config = StopLossConfig(method=StopLossMethod.ATR)
        result = calculator.calculate_stop_loss(
            entry_price=50000,
            direction=TradeDirection.LONG,
            ohlcv_data=data,
            key_levels=key_levels,
            config=config
        )
    """

    def __init__(self, config: StopLossConfig | None = None):
        """Initialize stop-loss calculator.

        Args:
            config: Default configuration (optional)
        """
        self.default_config = config or StopLossConfig()
        self._engine = self._create_engine(self.default_config)

    def calculate_stop_loss(
        self,
        entry_price: float,
        direction: TradeDirection,
        ohlcv_data: list["OHLCVData"],
        key_levels: "KeyLevelsResult",
        target_price: float | None = None,
        config: StopLossConfig | None = None,
    ) -> StopLossCalculation:
        """Calculate stop-loss for a trade.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            ohlcv_data: OHLCV data for ATR calculation
            key_levels: KeyLevelsResult from KeyLevelsAnalyzer
            target_price: Optional target price for R:R calculation
            config: Optional configuration override

        Returns:
            StopLossCalculation with complete results
        """
        cfg = config or self.default_config

        # Create engine with config if different from default
        if config and config != self.default_config:
            engine = self._create_engine(config)
        else:
            engine = self._engine

        # If specific method requested, use it
        if cfg.method and cfg.method != StopLossMethod:
            result = self._calculate_specific_method(
                engine=engine,
                method=cfg.method,
                entry_price=entry_price,
                direction=direction,
                ohlcv_data=ohlcv_data,
                key_levels=key_levels,
                target_price=target_price,
            )

            # Create comparison with single result
            comparison = StopLossComparison(
                results=[result],
                optimal=result if result.is_valid else None,
                selection_rationale=f"Used requested method: {cfg.method.value}",
            )
        else:
            # Compare all methods and select optimal
            comparison = engine.compare_methods(
                entry_price=entry_price,
                direction=direction,
                ohlcv_data=ohlcv_data,
                key_levels=key_levels,
                target_price=target_price,
            )

        # Select the stop to use
        selected = comparison.optimal
        if selected is None:
            # No valid optimal, use the first result (best effort)
            selected = comparison.results[0] if comparison.results else None

        if selected is None:
            raise ValueError("Could not calculate any stop-loss")

        return StopLossCalculation(
            entry_price=entry_price,
            direction=direction,
            target_price=target_price,
            config=cfg,
            comparison=comparison,
            selected_stop=selected,
        )

    def calculate_atr_stop(
        self,
        entry_price: float,
        direction: TradeDirection,
        ohlcv_data: list["OHLCVData"],
        target_price: float | None = None,
        atr_multiplier: float | None = None,
    ) -> StopLossResult:
        """Calculate ATR-based stop-loss.

        Convenience method for direct ATR stop calculation.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            ohlcv_data: OHLCV data for ATR calculation
            target_price: Optional target price for R:R calculation
            atr_multiplier: Optional ATR multiplier override

        Returns:
            StopLossResult with calculated stop
        """
        if atr_multiplier is not None:
            engine = StopLossEngine(atr_multiplier=atr_multiplier)
        else:
            engine = self._engine

        return engine.atr_based_stop(
            entry_price=entry_price,
            direction=direction,
            ohlcv_data=ohlcv_data,
            target_price=target_price,
        )

    def calculate_technical_stop(
        self,
        entry_price: float,
        direction: TradeDirection,
        key_levels: "KeyLevelsResult",
        target_price: float | None = None,
    ) -> StopLossResult:
        """Calculate technical level-based stop-loss.

        Convenience method for direct technical stop calculation.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            key_levels: KeyLevelsResult from KeyLevelsAnalyzer
            target_price: Optional target price for R:R calculation

        Returns:
            StopLossResult with calculated stop
        """
        return self._engine.technical_level_stop(
            entry_price=entry_price,
            direction=direction,
            key_levels=key_levels,
            target_price=target_price,
        )

    def calculate_percentage_stop(
        self,
        entry_price: float,
        direction: TradeDirection,
        percentage: float | None = None,
        target_price: float | None = None,
    ) -> StopLossResult:
        """Calculate percentage-based stop-loss.

        Convenience method for direct percentage stop calculation.

        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (LONG or SHORT)
            percentage: Percentage distance (default: from config)
            target_price: Optional target price for R:R calculation

        Returns:
            StopLossResult with calculated stop
        """
        return self._engine.percentage_based_stop(
            entry_price=entry_price,
            direction=direction,
            percentage=percentage,
            target_price=target_price,
        )

    def _create_engine(self, config: StopLossConfig) -> StopLossEngine:
        """Create StopLossEngine from configuration.

        Args:
            config: StopLossConfig to use

        Returns:
            Configured StopLossEngine
        """
        return StopLossEngine(
            atr_period=config.atr_period,
            atr_multiplier=config.atr_multiplier,
            min_risk_reward=config.min_risk_reward,
            default_percentage=config.default_percentage,
            min_percentage=config.min_percentage,
            max_percentage=config.max_percentage,
            max_drawdown_pct=config.max_drawdown_pct,
        )

    def _calculate_specific_method(
        self,
        engine: StopLossEngine,
        method: StopLossMethod,
        entry_price: float,
        direction: TradeDirection,
        ohlcv_data: list["OHLCVData"],
        key_levels: "KeyLevelsResult",
        target_price: float | None,
    ) -> StopLossResult:
        """Calculate stop using specific method.

        Args:
            engine: StopLossEngine to use
            method: Method to use
            entry_price: Entry price
            direction: Trade direction
            ohlcv_data: OHLCV data
            key_levels: Key levels result
            target_price: Optional target price

        Returns:
            StopLossResult
        """
        if method == StopLossMethod.ATR:
            return engine.atr_based_stop(
                entry_price, direction, ohlcv_data, target_price
            )
        elif method == StopLossMethod.TECHNICAL_LEVEL:
            return engine.technical_level_stop(
                entry_price, direction, key_levels, target_price
            )
        elif method == StopLossMethod.PERCENTAGE:
            return engine.percentage_based_stop(
                entry_price, direction, None, target_price
            )
        else:
            raise ValueError(f"Unknown method: {method}")
