"""Pre-execution validation for autonomous cognition actions.

This module provides the ActionValidator class which validates actions
before execution against safety constraints, rate limits, and budgets.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autonomous_cognition.action_executor import Action

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of action validation.

    Attributes:
        valid: Whether the action passed validation
        error: Error message if validation failed
        warnings: List of warning messages
        validation_time_ms: Time taken for validation in milliseconds
        constraints_checked: List of constraints that were validated
    """

    valid: bool
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    validation_time_ms: float = 0.0
    constraints_checked: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        max_requests_per_minute: Maximum requests allowed per minute
        max_requests_per_hour: Maximum requests allowed per hour
        burst_size: Maximum burst size for token bucket
    """

    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 1000
    burst_size: int = 10


@dataclass
class BudgetConfig:
    """Configuration for budget constraints.

    Attributes:
        max_daily_actions: Maximum actions per day
        max_concurrent_actions: Maximum concurrent actions
        action_costs: Mapping of action types to cost values
    """

    max_daily_actions: int = 10000
    max_concurrent_actions: int = 100
    action_costs: dict[str, float] = field(default_factory=dict)


@dataclass
class SafetyConstraint:
    """Safety constraint definition.

    Attributes:
        name: Name of the constraint
        check: Function that performs the check
        error_message: Message to return if check fails
    """

    name: str
    check: callable
    error_message: str


class ActionValidator:
    """Validates actions before execution.

    This validator checks actions against:
    - Input validation schemas
    - Safety constraints
    - Rate limits
    - Budget constraints

    Example:
        >>> validator = ActionValidator()
        >>> result = validator.validate(action, action_id)
        >>> if result.valid:
        ...     print("Action is valid")
        >>> else:
        ...     print(f"Validation failed: {result.error}")
    """

    def __init__(
        self,
        rate_limits: RateLimitConfig | None = None,
        budget: BudgetConfig | None = None,
        custom_constraints: list[SafetyConstraint] | None = None,
    ):
        """Initialize the action validator.

        Args:
            rate_limits: Rate limiting configuration
            budget: Budget constraint configuration
            custom_constraints: Additional safety constraints
        """
        self._rate_limits = rate_limits or RateLimitConfig()
        self._budget = budget or BudgetConfig()
        self._custom_constraints = custom_constraints or []

        # Rate tracking
        self._request_times: list[float] = []
        self._hourly_requests: dict[str, list[float]] = {}
        self._daily_count: int = 0
        self._daily_reset_time: float = time.time()
        self._concurrent_count: int = 0

        # Token bucket for burst handling
        self._tokens: float = float(self._rate_limits.burst_size)
        self._last_token_update: float = time.time()

    async def validate(self, action: Action, action_id: str) -> ValidationResult:
        """Validate an action before execution.

        Args:
            action: The action to validate
            action_id: Unique identifier for this execution

        Returns:
            ValidationResult indicating if action is valid
        """
        start_time = time.time()
        result = ValidationResult(valid=True)
        constraints_checked: list[str] = []

        try:
            # Check 1: Input schema validation
            schema_result = self._validate_schema(action)
            constraints_checked.append("schema")
            if not schema_result.valid:
                result.valid = False
                result.error = schema_result.error
                result.validation_time_ms = (time.time() - start_time) * 1000
                result.constraints_checked = constraints_checked
                return result

            # Check 2: Safety constraints
            safety_result = self._validate_safety_constraints(action)
            constraints_checked.append("safety")
            if not safety_result.valid:
                result.valid = False
                result.error = safety_result.error
                result.validation_time_ms = (time.time() - start_time) * 1000
                result.constraints_checked = constraints_checked
                return result

            # Check 3: Rate limits
            rate_result = self._validate_rate_limits(action)
            constraints_checked.append("rate_limit")
            if not rate_result.valid:
                result.valid = False
                result.error = rate_result.error
                result.validation_time_ms = (time.time() - start_time) * 1000
                result.constraints_checked = constraints_checked
                return result

            # Check 4: Budget constraints
            budget_result = self._validate_budget(action)
            constraints_checked.append("budget")
            if not budget_result.valid:
                result.valid = False
                result.error = budget_result.error
                result.validation_time_ms = (time.time() - start_time) * 1000
                result.constraints_checked = constraints_checked
                return result

            # Check 5: Custom constraints
            for constraint in self._custom_constraints:
                constraints_checked.append(f"custom:{constraint.name}")
                if not constraint.check(action):
                    result.valid = False
                    result.error = constraint.error_message
                    result.validation_time_ms = (time.time() - start_time) * 1000
                    result.constraints_checked = constraints_checked
                    return result

            # Add any warnings
            for warning in schema_result.warnings:
                result.add_warning(warning)
            for warning in safety_result.warnings:
                result.add_warning(warning)

            result.validation_time_ms = (time.time() - start_time) * 1000
            result.constraints_checked = constraints_checked

            logger.debug("Action %s passed all validation checks", action_id)
            return result

        except Exception as e:
            logger.exception("Validation error for action %s: %s", action_id, e)
            result.valid = False
            result.error = f"Validation error: {str(e)}"
            result.validation_time_ms = (time.time() - start_time) * 1000
            result.constraints_checked = constraints_checked
            return result

    def _validate_schema(self, action: Action) -> ValidationResult:
        """Validate action against input schema.

        Args:
            action: The action to validate

        Returns:
            ValidationResult for schema validation
        """
        result = ValidationResult(valid=True)

        # Validate required fields
        if not action.name or not action.name.strip():
            result.valid = False
            result.error = "Action name is required"
            return result

        if not action.action_type or not action.action_type.strip():
            result.valid = False
            result.error = "Action type is required"
            return result

        if action.payload is None:
            result.valid = False
            result.error = "Action payload cannot be None"
            return result

        # Validate payload is a dict
        if not isinstance(action.payload, dict):
            result.valid = False
            result.error = "Action payload must be a dictionary"
            return result

        # Warn about empty payload
        if len(action.payload) == 0:
            result.add_warning("Action payload is empty")

        # Validate timeout
        if action.timeout_seconds <= 0:
            result.valid = False
            result.error = "Timeout must be positive"
            return result

        if action.timeout_seconds > 300:  # 5 minutes max
            result.add_warning(
                f"Timeout {action.timeout_seconds}s exceeds recommended 300s"
            )

        # Validate retries
        if action.max_retries < 0:
            result.valid = False
            result.error = "Max retries must be non-negative"
            return result

        if action.max_retries > 5:
            result.add_warning(
                f"Max retries {action.max_retries} exceeds recommended 5"
            )

        return result

    def _validate_safety_constraints(self, action: Action) -> ValidationResult:
        """Validate action against safety constraints.

        Args:
            action: The action to validate

        Returns:
            ValidationResult for safety validation
        """
        result = ValidationResult(valid=True)

        # Constraint 1: Action type whitelist check
        dangerous_types = {"delete", "drop", "remove", "purge"}
        if any(dt in action.action_type.lower() for dt in dangerous_types):
            result.add_warning(
                f"Action type '{action.action_type}' contains dangerous keywords"
            )

        # Constraint 2: Payload size check
        payload_size = len(str(action.payload))
        if payload_size > 1000000:  # 1MB
            result.valid = False
            result.error = f"Payload size {payload_size} bytes exceeds maximum 1MB"
            return result

        if payload_size > 100000:  # 100KB
            result.add_warning(
                f"Payload size {payload_size} bytes exceeds recommended 100KB"
            )

        # Constraint 3: Metadata validation
        if action.metadata:
            if len(str(action.metadata)) > 10000:  # 10KB
                result.add_warning("Metadata size exceeds recommended 10KB")

        return result

    def _validate_rate_limits(self, action: Action) -> ValidationResult:
        """Validate action against rate limits.

        Args:
            action: The action to validate

        Returns:
            ValidationResult for rate limit validation
        """
        result = ValidationResult(valid=True)
        now = time.time()

        # Update token bucket
        time_since_last = now - self._last_token_update
        tokens_to_add = time_since_last * (
            self._rate_limits.max_requests_per_minute / 60
        )
        self._tokens = min(
            self._tokens + tokens_to_add,
            float(self._rate_limits.burst_size),
        )
        self._last_token_update = now

        # Check burst limit (token bucket)
        if self._tokens < 1:
            result.valid = False
            result.error = "Rate limit exceeded: burst capacity exhausted"
            return result

        # Consume token
        self._tokens -= 1

        # Clean old requests (older than 1 minute)
        cutoff = now - 60
        self._request_times = [t for t in self._request_times if t > cutoff]

        # Check per-minute limit
        if len(self._request_times) >= self._rate_limits.max_requests_per_minute:
            result.valid = False
            result.error = f"Rate limit exceeded: {self._rate_limits.max_requests_per_minute} requests per minute"
            return result

        # Track this request
        self._request_times.append(now)

        # Check per-hour limit per action type
        action_type = action.action_type
        if action_type not in self._hourly_requests:
            self._hourly_requests[action_type] = []

        hour_cutoff = now - 3600
        self._hourly_requests[action_type] = [
            t for t in self._hourly_requests[action_type] if t > hour_cutoff
        ]

        if (
            len(self._hourly_requests[action_type])
            >= self._rate_limits.max_requests_per_hour
        ):
            result.valid = False
            result.error = (
                f"Rate limit exceeded: {self._rate_limits.max_requests_per_hour} "
                f"requests per hour for action type '{action_type}'"
            )
            return result

        self._hourly_requests[action_type].append(now)

        return result

    def _validate_budget(self, action: Action) -> ValidationResult:
        """Validate action against budget constraints.

        Args:
            action: The action to validate

        Returns:
            ValidationResult for budget validation
        """
        result = ValidationResult(valid=True)
        now = time.time()

        # Reset daily count if needed
        if now - self._daily_reset_time >= 86400:  # 24 hours
            self._daily_count = 0
            self._daily_reset_time = now

        # Check daily limit
        if self._daily_count >= self._budget.max_daily_actions:
            result.valid = False
            result.error = (
                f"Daily action budget exceeded: {self._budget.max_daily_actions}"
            )
            return result

        # Check concurrent limit
        if self._concurrent_count >= self._budget.max_concurrent_actions:
            result.valid = False
            result.error = f"Concurrent action limit exceeded: {self._budget.max_concurrent_actions}"
            return result

        # Check action-specific cost
        action_cost = self._budget.action_costs.get(action.action_type, 1.0)
        if action_cost <= 0:
            result.valid = False
            result.error = f"Invalid action cost for type '{action.action_type}'"
            return result

        # Increment counters
        self._daily_count += 1
        self._concurrent_count += 1

        return result

    def release_concurrent_slot(self) -> None:
        """Release a concurrent action slot.

        Should be called after action completes.
        """
        self._concurrent_count = max(0, self._concurrent_count - 1)

    def get_rate_limit_status(self) -> dict[str, Any]:
        """Get current rate limit status.

        Returns:
            Dictionary with rate limit metrics
        """
        now = time.time()

        # Clean old requests
        cutoff = now - 60
        self._request_times = [t for t in self._request_times if t > cutoff]

        return {
            "requests_last_minute": len(self._request_times),
            "max_requests_per_minute": self._rate_limits.max_requests_per_minute,
            "available_tokens": self._tokens,
            "burst_size": self._rate_limits.burst_size,
            "concurrent_count": self._concurrent_count,
            "max_concurrent": self._budget.max_concurrent_actions,
            "daily_count": self._daily_count,
            "max_daily": self._budget.max_daily_actions,
        }

    def reset_rate_limits(self) -> None:
        """Reset all rate limit counters.

        Useful for testing or manual recovery.
        """
        self._request_times = []
        self._hourly_requests = {}
        self._daily_count = 0
        self._concurrent_count = 0
        self._tokens = float(self._rate_limits.burst_size)
        self._last_token_update = time.time()
        logger.info("Rate limits reset")
