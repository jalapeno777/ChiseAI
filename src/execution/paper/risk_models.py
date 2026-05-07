"""Risk models and data structures for paper trading.

Defines the core dataclasses for risk checks, violations, and assessments
used by the paper trading risk enforcer.

For PAPER-LOOP-001: Paper Trading Risk Enforcer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskSeverity(Enum):
    """Severity level for risk violations."""

    WARNING = "warning"  # Violation logged but order allowed
    BLOCK = "block"  # Order rejected


@dataclass
class RiskCheck:
    """Risk check configuration.

    Attributes:
        max_position_pct: Maximum position size as % of portfolio per token (default: 10%)
        max_leverage: Maximum allowed leverage (default: 3x)
        max_portfolio_exposure_pct: Maximum total portfolio exposure (default: 80%)
        min_confidence: Minimum confidence for actionable signals (default: 75%)
        max_drawdown_pct: Maximum drawdown before kill-switch (default: 15%)
    """

    max_position_pct: float = 0.10  # 10% per token
    max_leverage: float = 3.0
    max_portfolio_exposure_pct: float = 0.80  # 80%
    min_confidence: float = 0.70  # 70%
    max_drawdown_pct: float = 0.15  # 15%

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0 < self.max_position_pct <= 1:
            raise ValueError("max_position_pct must be between 0 and 1")
        if not self.max_leverage > 0:
            raise ValueError("max_leverage must be positive")
        if not 0 < self.max_portfolio_exposure_pct <= 1:
            raise ValueError("max_portfolio_exposure_pct must be between 0 and 1")
        if not 0 < self.min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        if not 0 < self.max_drawdown_pct <= 1:
            raise ValueError("max_drawdown_pct must be between 0 and 1")


@dataclass
class RiskViolation:
    """Risk violation report.

    Attributes:
        rule: Name of the violated rule
        severity: Severity level (warning or block)
        message: Human-readable violation message
        current_value: Current value that violated the rule
        limit_value: Limit value that was exceeded
        metadata: Additional context about the violation
    """

    rule: str
    severity: str  # warning, block
    message: str
    current_value: float
    limit_value: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary for serialization."""
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "current_value": round(self.current_value, 4),
            "limit_value": round(self.limit_value, 4),
            "metadata": self.metadata,
        }


@dataclass
class RiskAssessment:
    """Result of risk check.

    Attributes:
        approved: Whether the order is approved for execution
        violations: List of risk violations found
        position_size: Recommended position size
        margin_required: Margin required for the position
        metadata: Additional assessment metadata
    """

    approved: bool
    violations: list[RiskViolation] = field(default_factory=list)
    position_size: float = 0.0
    margin_required: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate assessment state."""
        # If there are blocking violations, approval must be False
        has_block = any(v.severity == RiskSeverity.BLOCK.value for v in self.violations)
        if has_block and self.approved:
            raise ValueError("Cannot approve order with blocking violations")

    @property
    def has_violations(self) -> bool:
        """Check if any violations exist."""
        return len(self.violations) > 0

    @property
    def has_blocking_violations(self) -> bool:
        """Check if any blocking violations exist."""
        return any(v.severity == RiskSeverity.BLOCK.value for v in self.violations)

    @property
    def has_warning_violations(self) -> bool:
        """Check if any warning violations exist."""
        return any(v.severity == RiskSeverity.WARNING.value for v in self.violations)

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment to dictionary for serialization."""
        return {
            "approved": self.approved,
            "violations": [v.to_dict() for v in self.violations],
            "position_size": round(self.position_size, 8),
            "margin_required": round(self.margin_required, 2),
            "metadata": self.metadata,
        }


@dataclass
class PaperPosition:
    """Paper trading position representation.

    Attributes:
        position_id: Unique position identifier
        token: Trading pair/token (e.g., "BTC/USDT")
        direction: Position direction ("long" or "short")
        quantity: Position quantity
        entry_price: Average entry price
        current_price: Current market price
        leverage: Leverage used
        value: Current position value in USD
    """

    position_id: str
    token: str
    direction: str  # "long" or "short"
    quantity: float
    entry_price: float
    current_price: float
    leverage: float = 1.0

    @property
    def value(self) -> float:
        """Calculate current position value in USD."""
        return abs(self.quantity) * self.current_price

    @property
    def notional_value(self) -> float:
        """Calculate notional value (with leverage)."""
        return self.value * self.leverage

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized PnL."""
        if self.direction == "long":
            return (self.current_price - self.entry_price) * self.quantity
        else:  # short
            return (self.entry_price - self.current_price) * abs(self.quantity)

    def to_dict(self) -> dict[str, Any]:
        """Convert position to dictionary for serialization."""
        return {
            "position_id": self.position_id,
            "token": self.token,
            "direction": self.direction,
            "quantity": round(self.quantity, 8),
            "entry_price": round(self.entry_price, 2),
            "current_price": round(self.current_price, 2),
            "leverage": round(self.leverage, 2),
            "value": round(self.value, 2),
            "notional_value": round(self.notional_value, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
        }
