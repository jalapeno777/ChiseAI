"""Risk enforcer for live trading risk controls.

Enforces hard-coded risk limits from PRD:
- ≤1% per-trade risk
- ≤3x leverage
- ≤2% per-grid worst-case

For ST-EX-002: Bitget Live Trading Gating Implementation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of risk validation.

    Attributes:
        valid: Whether validation passed
        violations: List of risk violations (empty if valid)
        timestamp: When validation was performed
        trade_params: Copy of trade parameters that were validated
    """

    valid: bool
    violations: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    trade_params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure valid is False if violations exist."""
        if self.violations and self.valid:
            self.valid = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "violations": self.violations,
            "timestamp": self.timestamp.isoformat(),
            "trade_params": self.trade_params,
        }


class RiskEnforcer:
    """Enforces risk controls for live trading.

    Hard-coded limits from PRD:
    - Per-trade risk: ≤1% of portfolio value
    - Leverage cap: ≤3x
    - Per-grid worst-case: ≤2%

    This class validates trades before execution and ensures
    all risk parameters are within acceptable bounds.

    Usage:
        enforcer = RiskEnforcer(portfolio_value=10000.0)

        # Validate a trade
        result = enforcer.validate_trade({
            "size": 0.1,
            "leverage": 2.0,
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
        })

        if not result.valid:
            print(f"Risk violations: {result.violations}")
    """

    # Hard-coded limits from PRD
    MAX_PER_TRADE_RISK_PCT = 1.0  # ≤1% per-trade risk
    MAX_LEVERAGE = 3.0  # ≤3x leverage
    MAX_PER_GRID_WORST_CASE_PCT = 2.0  # ≤2% per-grid worst-case

    def __init__(self, portfolio_value: float = 10000.0) -> None:
        """Initialize risk enforcer.

        Args:
            portfolio_value: Current portfolio value in quote currency

        Raises:
            ValueError: If portfolio value is not positive
        """
        if portfolio_value <= 0:
            raise ValueError("Portfolio value must be positive")

        self._portfolio_value = portfolio_value
        self._daily_loss = 0.0
        self._daily_loss_reset_time = datetime.now(UTC)
        self._trade_count_today = 0
        self._validation_history: list[ValidationResult] = []

        logger.info(
            f"RiskEnforcer initialized: portfolio={portfolio_value:.2f}, "
            f"max_risk={self.MAX_PER_TRADE_RISK_PCT}%, "
            f"max_leverage={self.MAX_LEVERAGE}x"
        )

    @property
    def portfolio_value(self) -> float:
        """Get current portfolio value."""
        return self._portfolio_value

    @portfolio_value.setter
    def portfolio_value(self, value: float) -> None:
        """Update portfolio value.

        Args:
            value: New portfolio value

        Raises:
            ValueError: If value is not positive
        """
        if value <= 0:
            raise ValueError("Portfolio value must be positive")
        self._portfolio_value = value

    def enforce_position_limit(self, size: float, symbol: str = "") -> bool:
        """Enforce position size limit.

        Position size is limited to ensure per-trade risk ≤1%.

        Args:
            size: Position size in base currency
            symbol: Trading symbol (for logging)

        Returns:
            True if within limits, False if exceeded
        """
        # Calculate notional value (assuming price is ~portfolio_value for simplicity)
        # In practice, this would use current market price
        notional_value = size * self._portfolio_value / 10  # Rough estimate

        # Max position = portfolio * (max_risk / 100) * leverage
        max_notional = (
            self._portfolio_value
            * (self.MAX_PER_TRADE_RISK_PCT / 100)
            * self.MAX_LEVERAGE
        )

        if notional_value > max_notional:
            logger.warning(
                f"Position limit exceeded for {symbol}: "
                f"{notional_value:.2f} > {max_notional:.2f}"
            )
            return False

        return True

    def enforce_leverage_cap(self, leverage: float) -> bool:
        """Enforce leverage cap.

        Args:
            leverage: Requested leverage multiplier

        Returns:
            True if within cap, False if exceeded
        """
        if leverage > self.MAX_LEVERAGE:
            logger.warning(f"Leverage cap exceeded: {leverage}x > {self.MAX_LEVERAGE}x")
            return False

        if leverage <= 0:
            logger.warning(f"Invalid leverage: {leverage}")
            return False

        return True

    def check_daily_loss_cap(self, daily_loss_cap: float = 1000.0) -> bool:
        """Check if daily loss is within cap.

        Args:
            daily_loss_cap: Maximum allowed daily loss

        Returns:
            True if within cap, False if exceeded
        """
        self._reset_daily_if_needed()

        if abs(self._daily_loss) > daily_loss_cap:
            logger.critical(
                f"Daily loss cap exceeded: {abs(self._daily_loss):.2f} > {daily_loss_cap:.2f}"
            )
            return False

        return True

    def validate_trade(self, trade_params: dict[str, Any]) -> ValidationResult:
        """Validate trade against all risk controls.

        Args:
            trade_params: Trade parameters including:
                - size: Position size
                - leverage: Leverage multiplier
                - entry_price: Entry price
                - stop_loss: Stop loss price (optional)
                - symbol: Trading symbol
                - side: 'long' or 'short'

        Returns:
            ValidationResult with validity and any violations
        """
        violations = []

        # Extract parameters
        size = trade_params.get("size", 0.0)
        leverage = trade_params.get("leverage", 1.0)
        entry_price = trade_params.get("entry_price", 0.0)
        stop_loss = trade_params.get("stop_loss")
        symbol = trade_params.get("symbol", "")
        side = trade_params.get("side", "long")

        # Validate leverage
        if not self.enforce_leverage_cap(leverage):
            violations.append(
                f"Leverage {leverage}x exceeds maximum {self.MAX_LEVERAGE}x"
            )

        # Validate position size
        if not self.enforce_position_limit(size, symbol):
            violations.append(f"Position size {size} exceeds risk-adjusted limit")

        # Calculate per-trade risk if stop loss provided
        if stop_loss and entry_price > 0:
            risk_amount = self._calculate_trade_risk(size, entry_price, stop_loss, side)
            risk_pct = (risk_amount / self._portfolio_value) * 100

            if risk_pct > self.MAX_PER_TRADE_RISK_PCT:
                violations.append(
                    f"Per-trade risk {risk_pct:.2f}% exceeds "
                    f"maximum {self.MAX_PER_TRADE_RISK_PCT}%"
                )

        # Check notional value doesn't exceed portfolio * leverage
        if entry_price > 0:
            notional = size * entry_price * leverage
            max_notional = self._portfolio_value * self.MAX_LEVERAGE

            if notional > max_notional:
                violations.append(
                    f"Notional value {notional:.2f} exceeds maximum {max_notional:.2f}"
                )

        # Create validation result
        result = ValidationResult(
            valid=len(violations) == 0,
            violations=violations,
            trade_params=trade_params.copy(),
        )

        self._validation_history.append(result)

        if violations:
            logger.warning(f"Trade validation failed: {violations}")
        else:
            logger.debug(f"Trade validation passed for {symbol}")

        return result

    def _calculate_trade_risk(
        self,
        size: float,
        entry_price: float,
        stop_loss: float,
        side: str,
    ) -> float:
        """Calculate risk amount for a trade.

        Args:
            size: Position size
            entry_price: Entry price
            stop_loss: Stop loss price
            side: Position side ('long' or 'short')

        Returns:
            Risk amount in quote currency
        """
        if side == "long":
            price_diff = entry_price - stop_loss
        else:
            price_diff = stop_loss - entry_price

        # Risk = size * price difference
        risk = size * abs(price_diff)
        return risk

    def _reset_daily_if_needed(self) -> None:
        """Reset daily counters if it's a new day."""
        now = datetime.now(UTC)
        if (now - self._daily_loss_reset_time).days >= 1:
            self._daily_loss = 0.0
            self._trade_count_today = 0
            self._daily_loss_reset_time = now
            logger.info("Daily risk counters reset")

    def record_trade_result(self, pnl: float) -> None:
        """Record trade result for daily tracking.

        Args:
            pnl: Profit/loss from trade
        """
        self._reset_daily_if_needed()
        self._daily_loss += min(0, pnl)  # Only track losses
        self._trade_count_today += 1

    def get_risk_summary(self) -> dict[str, Any]:
        """Get current risk summary.

        Returns:
            Dictionary with risk metrics
        """
        self._reset_daily_if_needed()

        return {
            "portfolio_value": self._portfolio_value,
            "max_per_trade_risk_pct": self.MAX_PER_TRADE_RISK_PCT,
            "max_leverage": self.MAX_LEVERAGE,
            "max_per_grid_worst_case_pct": self.MAX_PER_GRID_WORST_CASE_PCT,
            "daily_loss": self._daily_loss,
            "trade_count_today": self._trade_count_today,
            "validation_count": len(self._validation_history),
            "rejection_count": sum(1 for r in self._validation_history if not r.valid),
        }

    def validate_grid_strategy(
        self,
        grid_levels: int,
        total_allocation_pct: float,
        per_level_risk_pct: float,
    ) -> ValidationResult:
        """Validate grid strategy risk parameters.

        Args:
            grid_levels: Number of grid levels
            total_allocation_pct: Total portfolio allocation percentage
            per_level_risk_pct: Risk per grid level percentage

        Returns:
            ValidationResult with validity and any violations
        """
        violations = []

        # Check total allocation
        if total_allocation_pct > 100.0:
            violations.append(f"Total allocation {total_allocation_pct}% exceeds 100%")

        # Check per-grid worst-case risk
        total_grid_risk = grid_levels * per_level_risk_pct
        if total_grid_risk > self.MAX_PER_GRID_WORST_CASE_PCT:
            violations.append(
                f"Total grid risk {total_grid_risk:.2f}% exceeds "
                f"maximum {self.MAX_PER_GRID_WORST_CASE_PCT}%"
            )

        # Check per-level risk
        if per_level_risk_pct > self.MAX_PER_TRADE_RISK_PCT:
            violations.append(
                f"Per-level risk {per_level_risk_pct}% exceeds "
                f"maximum {self.MAX_PER_TRADE_RISK_PCT}%"
            )

        return ValidationResult(
            valid=len(violations) == 0,
            violations=violations,
            trade_params={
                "grid_levels": grid_levels,
                "total_allocation_pct": total_allocation_pct,
                "per_level_risk_pct": per_level_risk_pct,
            },
        )
