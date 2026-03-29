"""Safety gates for experiment execution.

This module provides the ExperimentSafetyGates class which enforces safety
constraints on experiment execution, including:
- Max experiments per cycle limits
- Experiment timeout enforcement
- Result validation
- Risk level checking
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Default timeout for experiment execution (5 minutes)
DEFAULT_EXPERIMENT_TIMEOUT_SECONDS = 300

# Risk level ordering for comparison
RISK_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Max allowed risk level by default
DEFAULT_MAX_RISK_LEVEL = "medium"


@dataclass
class SafetyGateResult:
    """Result of a safety gate check.

    Attributes:
        passed: Whether the gate check passed
        message: Human-readable message explaining the result
        errors: List of specific errors if validation failed
    """

    passed: bool
    message: str = ""
    errors: list[str] | None = None

    def __bool__(self) -> bool:
        return self.passed


@dataclass
class ValidationError:
    """Detailed validation error.

    Attributes:
        field: The field that failed validation
        message: Description of the validation failure
        value: The invalid value (for context)
    """

    field: str
    message: str
    value: Any = None


class ExperimentSafetyGates:
    """Enforces safety constraints on experiment execution.

    This class provides:
    - Max experiments per cycle enforcement (respects config)
    - Experiment timeout enforcement
    - Result sanity validation
    - Risk level checking against configurable max

    All methods return SafetyGateResult objects with passed/failed status
    and detailed error information.
    """

    def __init__(
        self,
        max_experiments_per_cycle: int = 3,
        default_timeout_seconds: int = DEFAULT_EXPERIMENT_TIMEOUT_SECONDS,
        max_risk_level: str = DEFAULT_MAX_RISK_LEVEL,
    ):
        """Initialize the experiment safety gates.

        Args:
            max_experiments_per_cycle: Maximum number of experiments to run per cycle
            default_timeout_seconds: Default timeout for experiment execution
            max_risk_level: Maximum allowed risk level (low, medium, high, critical)
        """
        self._max_experiments = max_experiments_per_cycle
        self._default_timeout = default_timeout_seconds
        self._max_risk_level = max_risk_level

        logger.info(
            "ExperimentSafetyGates initialized: max_experiments=%d, timeout=%ds, max_risk=%s",
            max_experiments_per_cycle,
            default_timeout_seconds,
            max_risk_level,
        )

    @property
    def max_experiments_per_cycle(self) -> int:
        """Get the configured max experiments per cycle."""
        return self._max_experiments

    @property
    def default_timeout_seconds(self) -> int:
        """Get the default experiment timeout in seconds."""
        return self._default_timeout

    @property
    def max_risk_level(self) -> str:
        """Get the maximum allowed risk level."""
        return self._max_risk_level

    def check_max_experiments(self, count: int) -> SafetyGateResult:
        """Check if the number of experiments is within the allowed limit.

        Args:
            count: Number of experiments being proposed

        Returns:
            SafetyGateResult with passed=True if within limit, False otherwise
        """
        if count <= 0:
            return SafetyGateResult(
                passed=True,
                message="No experiments to run (count=0)",
            )

        if count > self._max_experiments:
            error_msg = (
                f"Experiment count {count} exceeds maximum allowed "
                f"{self._max_experiments}"
            )
            logger.warning("Max experiments gate failed: %s", error_msg)
            return SafetyGateResult(
                passed=False,
                message=error_msg,
                errors=[error_msg],
            )

        logger.debug(
            "Max experiments check passed: %d <= %d",
            count,
            self._max_experiments,
        )
        return SafetyGateResult(
            passed=True,
            message=f"Experiment count {count} is within limit ({self._max_experiments})",
        )

    def check_timeout(
        self,
        start_time: float | None,
        timeout_seconds: int | None = None,
    ) -> SafetyGateResult:
        """Check if an experiment has exceeded its timeout.

        Args:
            start_time: Unix timestamp when the experiment started (from time.time())
            timeout_seconds: Maximum allowed duration in seconds (uses default if None)

        Returns:
            SafetyGateResult with passed=True if not timed out, False if timed out
        """
        if start_time is None:
            logger.warning(
                "check_timeout called with start_time=None, allowing (no timing)"
            )
            return SafetyGateResult(
                passed=True,
                message="No start time provided, timeout check skipped",
            )

        timeout = (
            timeout_seconds if timeout_seconds is not None else self._default_timeout
        )
        elapsed = time.time() - start_time

        if elapsed > timeout:
            error_msg = (
                f"Experiment timed out: elapsed={elapsed:.1f}s, limit={timeout}s"
            )
            logger.warning("Timeout gate failed: %s", error_msg)
            return SafetyGateResult(
                passed=False,
                message=error_msg,
                errors=[error_msg],
            )

        logger.debug(
            "Timeout check passed: elapsed=%.1fs, limit=%ds",
            elapsed,
            timeout,
        )
        return SafetyGateResult(
            passed=True,
            message=f"Experiment within timeout (elapsed={elapsed:.1f}s, limit={timeout}s)",
        )

    def validate_result(
        self,
        result: dict[str, Any] | None,
    ) -> tuple[bool, list[ValidationError]]:
        """Validate that an experiment result passes basic sanity checks.

        Required fields in result:
        - sharpe: float >= 0 (risk-adjusted return metric)
        - sortino: float >= 0 (downside risk metric)
        - drawdown: float >= 0 and <= 1 (max drawdown as fraction)
        - ece: float >= 0 and <= 1 (expected calibration error)

        Optional fields:
        - passed: bool (explicit pass/fail flag)
        - hypothesis_id: str (for error reporting)

        Args:
            result: The experiment result dictionary to validate

        Returns:
            Tuple of (is_valid, list_of_errors). If is_valid is True, errors is empty.
        """
        errors: list[ValidationError] = []

        if result is None:
            errors.append(
                ValidationError(
                    field="result",
                    message="Experiment result is None",
                    value=result,
                )
            )
            return False, errors

        if not isinstance(result, dict):
            errors.append(
                ValidationError(
                    field="result",
                    message="Experiment result is not a dictionary",
                    value=type(result).__name__,
                )
            )
            return False, errors

        hypothesis_id = result.get("hypothesis_id", "unknown")

        # Validate sharpe (required, must be >= 0)
        sharpe = result.get("sharpe")
        if sharpe is None:
            errors.append(
                ValidationError(
                    field="sharpe",
                    message="Missing required field 'sharpe'",
                    value=sharpe,
                )
            )
        elif not isinstance(sharpe, int | float):
            errors.append(
                ValidationError(
                    field="sharpe",
                    message="Field 'sharpe' must be numeric",
                    value=type(sharpe).__name__,
                )
            )
        elif sharpe < 0:
            errors.append(
                ValidationError(
                    field="sharpe",
                    message=f"Field 'sharpe' must be >= 0, got {sharpe}",
                    value=sharpe,
                )
            )

        # Validate sortino (required, must be >= 0)
        sortino = result.get("sortino")
        if sortino is None:
            errors.append(
                ValidationError(
                    field="sortino",
                    message="Missing required field 'sortino'",
                    value=sortino,
                )
            )
        elif not isinstance(sortino, int | float):
            errors.append(
                ValidationError(
                    field="sortino",
                    message="Field 'sortino' must be numeric",
                    value=type(sortino).__name__,
                )
            )
        elif sortino < 0:
            errors.append(
                ValidationError(
                    field="sortino",
                    message=f"Field 'sortino' must be >= 0, got {sortino}",
                    value=sortino,
                )
            )

        # Validate drawdown (required, must be 0 <= x <= 1)
        drawdown = result.get("drawdown")
        if drawdown is None:
            errors.append(
                ValidationError(
                    field="drawdown",
                    message="Missing required field 'drawdown'",
                    value=drawdown,
                )
            )
        elif not isinstance(drawdown, int | float):
            errors.append(
                ValidationError(
                    field="drawdown",
                    message="Field 'drawdown' must be numeric",
                    value=type(drawdown).__name__,
                )
            )
        elif drawdown < 0 or drawdown > 1:
            errors.append(
                ValidationError(
                    field="drawdown",
                    message=f"Field 'drawdown' must be 0 <= x <= 1, got {drawdown}",
                    value=drawdown,
                )
            )

        # Validate ece (required, must be 0 <= x <= 1)
        ece = result.get("ece")
        if ece is None:
            errors.append(
                ValidationError(
                    field="ece",
                    message="Missing required field 'ece'",
                    value=ece,
                )
            )
        elif not isinstance(ece, int | float):
            errors.append(
                ValidationError(
                    field="ece",
                    message="Field 'ece' must be numeric",
                    value=type(ece).__name__,
                )
            )
        elif ece < 0 or ece > 1:
            errors.append(
                ValidationError(
                    field="ece",
                    message=f"Field 'ece' must be 0 <= x <= 1, got {ece}",
                    value=ece,
                )
            )

        # If there's an explicit 'passed' field, log a warning but don't fail
        # (the actual pass/fail determination should be based on metrics)
        if "passed" in result and isinstance(result["passed"], bool):
            logger.debug(
                "Result validation for %s: passed flag is %s (metrics-based check)",
                hypothesis_id,
                result["passed"],
            )

        is_valid = len(errors) == 0

        if not is_valid:
            error_messages = [e.message for e in errors]
            logger.warning(
                "Result validation failed for %s: %s",
                hypothesis_id,
                error_messages,
            )
        else:
            logger.debug(
                "Result validation passed for %s",
                hypothesis_id,
            )

        return is_valid, errors

    def check_risk_level(
        self,
        risk_level: str | None,
        max_allowed: str | None = None,
    ) -> SafetyGateResult:
        """Check if a risk level is within acceptable bounds.

        Args:
            risk_level: The risk level to check (low, medium, high, critical)
            max_allowed: Maximum allowed risk level (uses configured max if None)

        Returns:
            SafetyGateResult with passed=True if risk level is acceptable
        """
        if risk_level is None:
            error_msg = "Risk level is None"
            logger.warning("Risk level check failed: %s", error_msg)
            return SafetyGateResult(
                passed=False,
                message=error_msg,
                errors=[error_msg],
            )

        max_risk = max_allowed if max_allowed is not None else self._max_risk_level

        # Validate risk levels exist in our ordering
        if risk_level not in RISK_LEVEL_ORDER:
            error_msg = f"Unknown risk level: {risk_level}"
            logger.warning("Risk level check failed: %s", error_msg)
            return SafetyGateResult(
                passed=False,
                message=error_msg,
                errors=[error_msg],
            )

        if max_risk not in RISK_LEVEL_ORDER:
            error_msg = f"Unknown max risk level configured: {max_risk}"
            logger.error("Risk level check failed: %s", error_msg)
            return SafetyGateResult(
                passed=False,
                message=error_msg,
                errors=[error_msg],
            )

        risk_value = RISK_LEVEL_ORDER[risk_level]
        max_value = RISK_LEVEL_ORDER[max_risk]

        if risk_value > max_value:
            error_msg = (
                f"Risk level '{risk_level}' exceeds maximum allowed '{max_risk}'"
            )
            logger.warning("Risk level check failed: %s", error_msg)
            return SafetyGateResult(
                passed=False,
                message=error_msg,
                errors=[error_msg],
            )

        logger.debug(
            "Risk level check passed: %s <= %s",
            risk_level,
            max_risk,
        )
        return SafetyGateResult(
            passed=True,
            message=f"Risk level '{risk_level}' is within limit ('{max_risk}')",
        )

    def run_all_gates(
        self,
        experiment_count: int,
        start_time: float | None,
        result: dict[str, Any] | None,
        risk_level: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, SafetyGateResult]:
        """Run all safety gates and return a summary.

        This is a convenience method to run all applicable safety gates
        and get a dictionary of results keyed by gate name.

        Args:
            experiment_count: Number of experiments being run
            start_time: Unix timestamp when experiment started
            result: The experiment result to validate
            risk_level: The risk level of the experiment
            timeout_seconds: Custom timeout (uses default if None)

        Returns:
            Dictionary mapping gate names to their SafetyGateResult objects
        """
        return {
            "max_experiments": self.check_max_experiments(experiment_count),
            "timeout": self.check_timeout(start_time, timeout_seconds),
            "result_validation": SafetyGateResult(
                *(
                    self.validate_result(result)[:2]
                    if result
                    else (False, ["Result is None"])
                )
            ),
            "risk_level": self.check_risk_level(risk_level),
        }

    def all_gates_passed(
        self,
        experiment_count: int,
        start_time: float | None,
        result: dict[str, Any] | None,
        risk_level: str | None = None,
        timeout_seconds: int | None = None,
    ) -> bool:
        """Check if all safety gates passed.

        Convenience method that returns True only if ALL gates pass.

        Args:
            experiment_count: Number of experiments being run
            start_time: Unix timestamp when experiment started
            result: The experiment result to validate
            risk_level: The risk level of the experiment
            timeout_seconds: Custom timeout (uses default if None)

        Returns:
            True if all gates passed, False otherwise
        """
        gates = self.run_all_gates(
            experiment_count=experiment_count,
            start_time=start_time,
            result=result,
            risk_level=risk_level,
            timeout_seconds=timeout_seconds,
        )
        return all(gate.passed for gate in gates.values())
