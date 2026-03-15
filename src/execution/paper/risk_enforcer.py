"""Paper trading risk enforcer.

Validates orders against safety constraints before execution in paper trading mode.
Integrates with kill-switch executor for drawdown protection.

For PAPER-LOOP-001: Paper Trading Risk Enforcer
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from signal_generation.models import Signal

from .risk_models import (
    PaperPosition,
    RiskAssessment,
    RiskCheck,
    RiskSeverity,
    RiskViolation,
)

if TYPE_CHECKING:
    from execution.kill_switch.executor import KillSwitchExecutor

logger = logging.getLogger(__name__)


class PaperRiskEnforcer:
    """Risk enforcer for paper trading.

    Validates orders against safety constraints before execution,
    including position size limits, leverage limits, portfolio exposure,
    confidence thresholds, and drawdown protection.

    Attributes:
        config: Risk check configuration
        kill_switch: Optional kill-switch executor for drawdown protection
        _violation_log: History of risk violations for audit
    """

    def __init__(
        self,
        config: RiskCheck | None = None,
        kill_switch_executor: KillSwitchExecutor | None = None,
    ):
        """Initialize paper risk enforcer.

        Args:
            config: Risk check configuration (uses defaults if None)
            kill_switch_executor: Optional kill-switch executor for drawdown protection
        """
        self.config = config or RiskCheck()
        self.kill_switch = kill_switch_executor
        self._violation_log: list[dict[str, Any]] = []

        logger.info(
            f"PaperRiskEnforcer initialized: "
            f"max_position_pct={self.config.max_position_pct:.1%}, "
            f"max_leverage={self.config.max_leverage:.1f}x, "
            f"min_confidence={self.config.min_confidence:.1%}"
        )

    async def validate_order(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: list[PaperPosition],
        current_drawdown_pct: float = 0.0,
        entry_price: float | None = None,
    ) -> RiskAssessment:
        """Validate if order can be executed.

        Performs comprehensive risk checks:
        1. Confidence check (blocks if < 75%)
        2. Drawdown check (triggers kill-switch if >= 15%)
        3. Position size check (blocks if > 10% portfolio)
        4. Portfolio exposure check (warns if > 80%)

        Args:
            signal: Trading signal to validate
            portfolio_value: Current portfolio value in USD
            current_positions: List of current open positions
            current_drawdown_pct: Current drawdown percentage (0.0-1.0)
            entry_price: Entry price (uses signal metadata if None)

        Returns:
            RiskAssessment with approval status and violations
        """
        violations: list[RiskViolation] = []

        # 1. Check drawdown first - may trigger kill-switch
        drawdown_triggered = await self.check_drawdown(current_drawdown_pct)
        if drawdown_triggered:
            violation = RiskViolation(
                rule="drawdown",
                severity=RiskSeverity.BLOCK.value,
                message=f"Kill-switch triggered: drawdown {current_drawdown_pct:.2%} >= {self.config.max_drawdown_pct:.2%}",
                current_value=current_drawdown_pct,
                limit_value=self.config.max_drawdown_pct,
                metadata={"kill_switch_triggered": True},
            )
            violations.append(violation)
            self._log_violation(violation, signal)

            return RiskAssessment(
                approved=False,
                violations=violations,
                position_size=0.0,
                margin_required=0.0,
                metadata={
                    "signal_id": signal.signal_id,
                    "token": signal.token,
                    "reason": "kill_switch_triggered",
                },
            )

        # 2. Confidence check
        if signal.confidence < self.config.min_confidence:
            violation = RiskViolation(
                rule="confidence",
                severity=RiskSeverity.BLOCK.value,
                message=f"Signal confidence {signal.confidence:.2%} below minimum {self.config.min_confidence:.2%}",
                current_value=signal.confidence,
                limit_value=self.config.min_confidence,
            )
            violations.append(violation)
            self._log_violation(violation, signal)

        # 3. Calculate position size (pass entry_price to ensure correct calculation)
        price = entry_price or signal.metadata.get("entry_price", 0.0)
        position_size = self.calculate_position_size(signal, portfolio_value, price)
        if price <= 0:
            # Try to get from signal stop loss and risk reward ratio
            if signal.stop_loss and signal.risk_reward_ratio > 0:
                # Rough estimate: entry = stop_loss * (1 + 1/rr) for long
                price = signal.stop_loss * (1 + 1 / signal.risk_reward_ratio)

        position_value = position_size * price if price > 0 else 0.0

        # 4. Position size check (max 10% of portfolio per token)
        max_position_value = portfolio_value * self.config.max_position_pct
        if position_value > max_position_value:
            violation = RiskViolation(
                rule="position_size",
                severity=RiskSeverity.BLOCK.value,
                message=f"Position value ${position_value:,.2f} exceeds max {self.config.max_position_pct:.1%} of portfolio (${max_position_value:,.2f})",
                current_value=position_value,
                limit_value=max_position_value,
                metadata={
                    "position_size": position_size,
                    "entry_price": price,
                    "token": signal.token,
                },
            )
            violations.append(violation)
            self._log_violation(violation, signal)

        # 5. Portfolio exposure check (warn at 80%)
        total_exposure = sum(pos.value for pos in current_positions)
        # Exclude current token's existing position (we're replacing it)
        # Handle both 'symbol' (from position_tracker.PaperPosition) and 'token' (from risk_models.PaperPosition)
        existing_token_exposure = sum(
            pos.value
            for pos in current_positions
            if getattr(pos, "symbol", getattr(pos, "token", None)) == signal.token
        )
        adjusted_exposure = total_exposure - existing_token_exposure
        new_exposure = adjusted_exposure + position_value
        max_exposure = portfolio_value * self.config.max_portfolio_exposure_pct

        if new_exposure > max_exposure:
            violation = RiskViolation(
                rule="exposure",
                severity=RiskSeverity.WARNING.value,
                message=f"Portfolio exposure would be ${new_exposure:,.2f} ({new_exposure / portfolio_value:.1%}), exceeds {self.config.max_portfolio_exposure_pct:.1%} limit",
                current_value=new_exposure / portfolio_value,
                limit_value=self.config.max_portfolio_exposure_pct,
                metadata={
                    "current_exposure": total_exposure,
                    "new_exposure": new_exposure,
                    "portfolio_value": portfolio_value,
                },
            )
            violations.append(violation)
            self._log_violation(violation, signal)

        # 6. Leverage check
        leverage = signal.metadata.get("leverage", 1.0)
        if leverage > self.config.max_leverage:
            violation = RiskViolation(
                rule="leverage",
                severity=RiskSeverity.BLOCK.value,
                message=f"Leverage {leverage:.1f}x exceeds maximum {self.config.max_leverage:.1f}x",
                current_value=leverage,
                limit_value=self.config.max_leverage,
            )
            violations.append(violation)
            self._log_violation(violation, signal)

        # Determine approval
        has_blocking = any(v.severity == RiskSeverity.BLOCK.value for v in violations)
        approved = not has_blocking

        # Calculate margin required
        margin_required = position_value / leverage if leverage > 0 else position_value

        assessment = RiskAssessment(
            approved=approved,
            violations=violations,
            position_size=position_size if approved else 0.0,
            margin_required=margin_required if approved else 0.0,
            metadata={
                "signal_id": signal.signal_id,
                "token": signal.token,
                "confidence": signal.confidence,
                "portfolio_value": portfolio_value,
                "current_drawdown_pct": current_drawdown_pct,
                "position_value": position_value,
                "total_positions": len(current_positions),
            },
        )

        # Log assessment
        if approved:
            logger.info(
                f"Order approved: {signal.token} size={position_size:.6f} "
                f"value=${position_value:,.2f}"
            )
        else:
            logger.warning(
                f"Order rejected: {signal.token} - "
                f"{len([v for v in violations if v.severity == RiskSeverity.BLOCK.value])} blocking violations"
            )

        return assessment

    async def check_drawdown(self, current_drawdown_pct: float) -> bool:
        """Check if drawdown triggers kill-switch.

        Args:
            current_drawdown_pct: Current drawdown percentage (0.0-1.0)

        Returns:
            True if kill-switch was triggered, False otherwise
        """
        if current_drawdown_pct >= self.config.max_drawdown_pct:
            logger.critical(
                f"Drawdown threshold reached: {current_drawdown_pct:.2%} >= "
                f"{self.config.max_drawdown_pct:.2%}"
            )

            if self.kill_switch:
                try:
                    result = await self.kill_switch.execute_kill_switch(
                        reason="drawdown_threshold",
                        triggered_by="paper_risk_enforcer",
                        environment="paper",
                    )
                    logger.critical(
                        f"Kill-switch executed: success={result.success}, "
                        f"positions_closed={result.positions_closed}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"Failed to execute kill-switch: {e}")
                    # Still return True to indicate threshold was reached
                    return True
            else:
                logger.warning(
                    "Kill-switch threshold reached but no executor configured"
                )
                return True

        return False

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        entry_price: float | None = None,
    ) -> float:
        """Calculate safe position size based on risk rules.

        Uses fixed fractional sizing capped at max position percentage.
        Respects the 10% max position per token rule.
        Rounds to exchange precision (3 decimals for most crypto pairs).

        Args:
            signal: Trading signal
            portfolio_value: Current portfolio value
            entry_price: Entry price (uses signal metadata if None)

        Returns:
            Recommended position size in units (rounded to 3 decimal places)
        """
        # Default risk per trade (1% of portfolio)
        default_risk_pct = 0.01
        risk_amount = portfolio_value * default_risk_pct

        # Get entry price from parameter or signal metadata
        effective_entry_price: float = entry_price or 0.0
        if effective_entry_price <= 0:
            effective_entry_price = signal.metadata.get("entry_price", 0.0)
        stop_loss: float | None = signal.stop_loss
        position_size: float = 0.0

        if effective_entry_price > 0 and stop_loss is not None and stop_loss > 0:
            # Calculate position size based on risk amount and stop distance
            stop_distance = abs(effective_entry_price - stop_loss)
            if stop_distance > 0:
                position_size = risk_amount / stop_distance
            else:
                # Fallback: use fixed fractional
                position_size = (
                    portfolio_value * default_risk_pct
                ) / effective_entry_price
        else:
            # Fallback: fixed fractional sizing (1% of portfolio)
            if effective_entry_price > 0:
                position_size = (
                    portfolio_value * default_risk_pct
                ) / effective_entry_price
            else:
                # No price info, use notional value approach
                position_size = portfolio_value * default_risk_pct

        # Cap at max position percentage (10% of portfolio)
        max_position_value = portfolio_value * self.config.max_position_pct
        if effective_entry_price > 0:
            max_size = max_position_value / effective_entry_price
            position_size = min(position_size, max_size)

        # FIX: Round to 3 decimal places for exchange precision (e.g., BTCUSDT qtyStep=0.001)
        # This prevents "Qty invalid" errors from Bybit
        position_size = round(position_size, 3)

        return position_size

    def _log_violation(
        self,
        violation: RiskViolation,
        signal: Signal,
    ) -> None:
        """Log a risk violation for audit.

        Args:
            violation: The violation to log
            signal: The signal that triggered the violation
        """
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "signal_id": signal.signal_id,
            "token": signal.token,
            "violation": violation.to_dict(),
        }
        self._violation_log.append(log_entry)

        # Also log to Python logger
        if violation.severity == RiskSeverity.BLOCK.value:
            logger.warning(f"[RISK BLOCK] {violation.rule}: {violation.message}")
        else:
            logger.info(f"[RISK WARNING] {violation.rule}: {violation.message}")

    def get_violation_log(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent violation log entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of violation log entries
        """
        return self._violation_log[-limit:]

    def clear_violation_log(self) -> None:
        """Clear the violation log."""
        self._violation_log.clear()
        logger.info("Violation log cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get enforcer statistics.

        Returns:
            Dictionary with statistics
        """
        block_count = sum(
            1
            for entry in self._violation_log
            if entry["violation"]["severity"] == RiskSeverity.BLOCK.value
        )
        warning_count = sum(
            1
            for entry in self._violation_log
            if entry["violation"]["severity"] == RiskSeverity.WARNING.value
        )

        return {
            "config": {
                "max_position_pct": self.config.max_position_pct,
                "max_leverage": self.config.max_leverage,
                "max_portfolio_exposure_pct": self.config.max_portfolio_exposure_pct,
                "min_confidence": self.config.min_confidence,
                "max_drawdown_pct": self.config.max_drawdown_pct,
            },
            "violation_stats": {
                "total_violations": len(self._violation_log),
                "block_count": block_count,
                "warning_count": warning_count,
            },
            "kill_switch_configured": self.kill_switch is not None,
        }
