"""DSL Safety Constraints - Hard limits for strategy safety.

This module enforces safety constraints that must cause validation errors
when violated. These are the "guardrails" that prevent dangerous strategies
from being submitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.backtesting.dsl.validator import ValidationError


@dataclass(frozen=True)
class SafetyConstraint:
    """Definition of a safety constraint.

    Attributes:
        name: Constraint identifier
        description: Human-readable description
        max_value: Maximum allowed value (for numeric constraints)
        min_value: Minimum allowed value (for numeric constraints)
        required: Whether the constraint is required (not just recommended)
    """

    name: str
    description: str
    max_value: float | None = None
    min_value: float | None = None
    required: bool = True


# Define safety constraints per DSL spec
SAFETY_CONSTRAINTS = {
    "max_leverage": SafetyConstraint(
        name="max_leverage",
        description="Maximum leverage allowed",
        max_value=3.0,
        min_value=1.0,
        required=True,
    ),
    "max_position_percent": SafetyConstraint(
        name="max_position_percent",
        description="Maximum position size as percentage of portfolio",
        max_value=100.0,
        min_value=0.0,
        required=True,
    ),
    "min_confluence_score": SafetyConstraint(
        name="min_confluence_score",
        description="Minimum confluence score for signal validation",
        min_value=0.5,
        max_value=1.0,
        required=True,
    ),
    "max_daily_loss_percent": SafetyConstraint(
        name="max_daily_loss_percent",
        description="Maximum daily loss percentage",
        max_value=5.0,
        min_value=0.0,
        required=False,  # Warning only
    ),
    "stop_loss_required": SafetyConstraint(
        name="stop_loss_required",
        description="Stop-loss must be enabled",
        required=False,  # Warning only
    ),
}


class SafetyChecker:
    """Enforces safety constraints on DSL configurations.

    This class checks that strategies comply with hard safety limits
    defined in the DSL specification.
    """

    def __init__(self) -> None:
        """Initialize safety checker."""
        self.errors: list[ValidationError] = []

    def check(self, config: dict[str, Any]) -> list[ValidationError]:
        """Check all safety constraints.

        Args:
            config: DSL configuration dictionary

        Returns:
            List of validation errors for violated constraints
        """
        self.errors = []

        self._check_max_leverage(config)
        self._check_max_position_percent(config)
        self._check_min_confluence_score(config)
        self._check_timeframes(config)
        self._check_stop_loss(config)
        self._check_daily_loss_cap(config)

        return self.errors.copy()

    def _add_error(
        self, field_path: str, message: str, value: Any, constraint: str
    ) -> None:
        """Add a safety error."""
        self.errors.append(
            ValidationError(
                field_path=field_path,
                message=message,
                value=value,
                constraint=constraint,
            )
        )

    def _check_max_leverage(self, config: dict[str, Any]) -> None:
        """Check max leverage constraint (must be <= 3.0)."""
        risk_rules = config.get("risk_rules", {})
        position_limits = risk_rules.get("position_limits", {})
        max_leverage = position_limits.get("max_leverage", 1.0)

        constraint = SAFETY_CONSTRAINTS["max_leverage"]

        if constraint.max_value is not None and max_leverage > constraint.max_value:
            self._add_error(
                "risk_rules.position_limits.max_leverage",
                f"SAFETY VIOLATION: max_leverage ({max_leverage}x) exceeds hard limit of {constraint.max_value}x",
                max_leverage,
                f"must be <= {constraint.max_value}x",
            )

    def _check_max_position_percent(self, config: dict[str, Any]) -> None:
        """Check max position percent constraint (must be <= 100%)."""
        risk_rules = config.get("risk_rules", {})
        position_limits = risk_rules.get("position_limits", {})
        max_position_percent = position_limits.get("max_position_percent", 10.0)

        constraint = SAFETY_CONSTRAINTS["max_position_percent"]

        if (
            constraint.max_value is not None
            and max_position_percent > constraint.max_value
        ):
            self._add_error(
                "risk_rules.position_limits.max_position_percent",
                f"SAFETY VIOLATION: max_position_percent ({max_position_percent}%) exceeds hard limit of {constraint.max_value}%",
                max_position_percent,
                f"must be <= {constraint.max_value}%",
            )

    def _check_min_confluence_score(self, config: dict[str, Any]) -> None:
        """Check min confluence score constraint (must be 0.5-1.0)."""
        signals = config.get("signals", {})
        confluence = signals.get("confluence", {})

        if not confluence.get("enabled", False):
            return

        min_score = confluence.get("min_score", 0.5)
        constraint = SAFETY_CONSTRAINTS["min_confluence_score"]

        if constraint.min_value is not None and min_score < constraint.min_value:
            self._add_error(
                "signals.confluence.min_score",
                f"SAFETY VIOLATION: min_score ({min_score}) below minimum of {constraint.min_value}",
                min_score,
                f"must be >= {constraint.min_value}",
            )

        if constraint.max_value is not None and min_score > constraint.max_value:
            self._add_error(
                "signals.confluence.min_score",
                f"SAFETY VIOLATION: min_score ({min_score}) above maximum of {constraint.max_value}",
                min_score,
                f"must be <= {constraint.max_value}",
            )

    def _check_timeframes(self, config: dict[str, Any]) -> None:
        """Check that timeframes are in supported list."""
        metadata = config.get("metadata", {})
        timeframes = metadata.get("timeframes", [])

        supported = {"1m", "5m", "15m", "1h", "4h", "1d"}

        for i, tf in enumerate(timeframes):
            if tf not in supported:
                self._add_error(
                    f"metadata.timeframes[{i}]",
                    f"SAFETY VIOLATION: Unsupported timeframe: {tf}",
                    tf,
                    f"must be one of: {supported}",
                )

    def _check_stop_loss(self, config: dict[str, Any]) -> None:
        """Check that stop-loss is enabled (warning only)."""
        exits = config.get("exits", {})
        stop_loss = exits.get("stop_loss", {})

        if not stop_loss.get("enabled", True):
            # This is a warning-level check, but we include it for completeness
            # The validator will handle this as a warning
            pass

    def _check_daily_loss_cap(self, config: dict[str, Any]) -> None:
        """Check daily loss cap (warning if > 5%)."""
        risk_rules = config.get("risk_rules", {})
        daily_limits = risk_rules.get("daily_limits", {})
        max_daily_loss = daily_limits.get("max_daily_loss_percent", 2.0)

        constraint = SAFETY_CONSTRAINTS["max_daily_loss_percent"]

        if constraint.max_value is not None and max_daily_loss > constraint.max_value:
            # This is a warning-level constraint per the spec
            # We don't add an error here, but the validator will add a warning
            pass

    def get_constraint(self, name: str) -> SafetyConstraint | None:
        """Get a safety constraint by name.

        Args:
            name: Constraint name

        Returns:
            SafetyConstraint or None if not found
        """
        return SAFETY_CONSTRAINTS.get(name)

    def get_all_constraints(self) -> dict[str, SafetyConstraint]:
        """Get all safety constraints.

        Returns:
            Dictionary of all safety constraints
        """
        return SAFETY_CONSTRAINTS.copy()


def check_safety(config: dict[str, Any]) -> list[ValidationError]:
    """Quick safety check function.

    Args:
        config: DSL configuration dictionary

    Returns:
        List of safety violations (empty if safe)
    """
    checker = SafetyChecker()
    return checker.check(config)


def is_safe(config: dict[str, Any]) -> bool:
    """Quick check if configuration is safe.

    Args:
        config: DSL configuration dictionary

    Returns:
        True if no safety violations
    """
    return len(check_safety(config)) == 0
