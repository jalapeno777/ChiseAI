"""Paper trading risk enforcer.

Validates orders against risk limits and calculates position sizes
for paper trading simulations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

from execution.paper.models import RiskAssessment

logger = logging.getLogger(__name__)


@dataclass
class RiskEnforcerConfig:
    """Configuration for risk enforcer.

    Attributes:
        max_position_pct: Maximum position size as % of portfolio (0.0-1.0)
        max_total_exposure_pct: Maximum total exposure as % of portfolio
        max_concentration_pct: Maximum concentration in single asset
        max_daily_loss_pct: Maximum daily loss limit
        max_leverage: Maximum allowed leverage
        min_confidence: Minimum signal confidence required
        require_stop_loss: Whether stop-loss is required for orders
    """

    max_position_pct: float = 0.10  # 10% max per position
    max_total_exposure_pct: float = 0.80  # 80% max total exposure
    max_concentration_pct: float = 0.25  # 25% max in single asset
    max_daily_loss_pct: float = 0.02  # 2% daily loss limit
    max_leverage: float = 3.0
    min_confidence: float = 0.75
    require_stop_loss: bool = True


class PaperRiskEnforcer:
    """Enforces risk limits for paper trading.

    Validates orders against portfolio risk constraints:
    - Position size limits
    - Concentration limits
    - Leverage limits
    - Confidence thresholds
    """

    def __init__(self, config: RiskEnforcerConfig | None = None):
        """Initialize risk enforcer.

        Args:
            config: Risk enforcer configuration
        """
        self.config = config or RiskEnforcerConfig()

        logger.info(
            f"PaperRiskEnforcer initialized: max_position={self.config.max_position_pct:.0%}, "
            f"max_leverage={self.config.max_leverage:.1f}x"
        )

    async def validate_order(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: list[Any],
    ) -> RiskAssessment:
        """Validate a signal against risk constraints.

        Args:
            signal: Trading signal to validate
            portfolio_value: Current portfolio value
            current_positions: List of current open positions

        Returns:
            RiskAssessment with approval status and violations
        """
        violations: list[str] = []

        # Check signal confidence
        if signal.confidence < self.config.min_confidence:
            violations.append(
                f"Signal confidence {signal.confidence:.1%} below minimum "
                f"{self.config.min_confidence:.1%}"
            )

        # Check signal is actionable
        if not signal.is_actionable:
            violations.append("Signal is not actionable (below 75% threshold)")

        # Check stop-loss is present if required
        if self.config.require_stop_loss and signal.stop_loss is None:
            violations.append("Stop-loss required but not present")

        # Calculate position size
        position_size = self.calculate_position_size(signal, portfolio_value)

        # Check position size against limit
        position_value = position_size * (signal.stop_loss or 0)  # Approximate
        max_position_value = portfolio_value * self.config.max_position_pct

        if position_value > max_position_value:
            violations.append(
                f"Position value ${position_value:.2f} exceeds limit "
                f"${max_position_value:.2f}"
            )

        # Check concentration in symbol
        symbol_exposure = self._calculate_symbol_exposure(
            signal.token, current_positions
        )
        new_exposure = symbol_exposure + position_value
        max_concentration = portfolio_value * self.config.max_concentration_pct

        if new_exposure > max_concentration:
            violations.append(
                f"Concentration in {signal.token} would be ${new_exposure:.2f}, "
                f"exceeds limit ${max_concentration:.2f}"
            )

        # Check total exposure
        total_exposure = (
            sum(pos.notional_value for pos in current_positions) + position_value
        )
        max_exposure = portfolio_value * self.config.max_total_exposure_pct

        if total_exposure > max_exposure:
            violations.append(
                f"Total exposure ${total_exposure:.2f} exceeds limit ${max_exposure:.2f}"
            )

        # Calculate max loss if stop-loss is available
        max_loss = 0.0
        if signal.stop_loss and position_size > 0:
            # Approximate entry price from signal or use stop-loss as proxy
            entry_price = getattr(signal, "current_price", signal.stop_loss * 1.02)
            risk_per_unit = abs(entry_price - signal.stop_loss)
            max_loss = risk_per_unit * position_size

        approved = len(violations) == 0

        if approved:
            logger.info(f"Signal approved: {signal.token} {signal.direction.value}")
        else:
            logger.warning(f"Signal rejected: {', '.join(violations)}")

        return RiskAssessment(
            approved=approved,
            violations=violations,
            position_size=position_size,
            stop_loss_price=signal.stop_loss,
            max_loss_amount=max_loss,
            correlation_id=signal.signal_id,
        )

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
    ) -> float:
        """Calculate position size based on risk parameters.

        Uses a simple position sizing model based on:
        - Portfolio value
        - Maximum position percentage
        - Signal confidence (higher confidence = larger size)

        Args:
            signal: Trading signal
            portfolio_value: Current portfolio value

        Returns:
            Position size in base units
        """
        # Base position size from max position percentage
        max_position_value = portfolio_value * self.config.max_position_pct

        # Scale by confidence (75% = 1.0x, 100% = 1.33x)
        confidence_multiplier = signal.confidence / 0.75
        confidence_multiplier = min(confidence_multiplier, 1.33)  # Cap at 33% boost

        position_value = max_position_value * confidence_multiplier

        # Convert to quantity (need approximate entry price)
        # Use stop-loss as proxy if no current price available
        if hasattr(signal, "current_price") and signal.current_price:
            entry_price = signal.current_price
        elif signal.stop_loss:
            # Estimate entry price based on direction and stop-loss
            if signal.direction.value == "long":
                entry_price = signal.stop_loss * 1.02  # 2% above stop
            else:
                entry_price = signal.stop_loss * 0.98  # 2% below stop
        else:
            # Default - can't calculate without price info
            logger.warning("Cannot calculate position size without price info")
            return 0.0

        quantity = position_value / entry_price

        logger.debug(
            f"Position size: {quantity:.6f} @ ${entry_price:.2f} "
            f"(value=${position_value:.2f})"
        )

        return quantity

    def _calculate_symbol_exposure(
        self,
        symbol: str,
        positions: list[Any],
    ) -> float:
        """Calculate current exposure to a symbol.

        Args:
            symbol: Trading pair symbol
            positions: Current open positions

        Returns:
            Total exposure value
        """
        total = 0.0
        for pos in positions:
            if pos.symbol == symbol:
                total += pos.notional_value
        return total
