"""Retry Coordinator with budget management for ST-NS-039."""

import asyncio
from typing import Callable, TypeVar, Optional, Any, Dict
from datetime import datetime
from src.autonomous_control_plane.models.retry_policy import (
    RetryPolicy,
)

T = TypeVar("T")


class RetryBudgetExceeded(Exception):
    """Raised when retry budget is exceeded."""

    pass


class RetryAborted(Exception):
    """Raised when retry is aborted (e.g., circuit breaker open)."""

    pass


class RetryCoordinator:
    """Intelligent retry coordinator with budget management."""

    def __init__(self):
        self._budgets: Dict[str, Dict[str, Any]] = {}

    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        policy: RetryPolicy,
        service_name: str,
        circuit_breaker: Optional[Any] = None,
    ) -> T:
        """Execute an operation with retry logic."""

        # Check circuit breaker if provided
        if circuit_breaker and not circuit_breaker.can_execute():
            raise RetryAborted("Circuit breaker is open")

        # Check retry budget
        if not self._check_budget(service_name, policy.budget_limit_per_minute):
            raise RetryBudgetExceeded(f"Retry budget exceeded for {service_name}")

        last_exception = None

        for attempt in range(policy.max_attempts):
            try:
                result = operation()

                # Record success in circuit breaker
                if circuit_breaker:
                    circuit_breaker.record_success()

                return result

            except Exception as e:
                last_exception = e

                # Record failure in circuit breaker
                if circuit_breaker:
                    circuit_breaker.record_failure()
                    if not circuit_breaker.can_execute():
                        raise RetryAborted("Circuit breaker opened after failure")

                # Don't retry on last attempt
                if attempt == policy.max_attempts - 1:
                    break

                # Calculate and apply backoff
                delay = policy.calculate_delay(attempt)
                await asyncio.sleep(delay)

        # All retries exhausted
        raise last_exception

    def _check_budget(self, service_name: str, limit: int) -> bool:
        """Check if retry budget allows another attempt."""
        now = datetime.utcnow()
        minute_key = now.strftime("%Y-%m-%d-%H-%M")

        if service_name not in self._budgets:
            self._budgets[service_name] = {}

        current_count = self._budgets[service_name].get(minute_key, 0)

        if current_count >= limit:
            return False

        self._budgets[service_name][minute_key] = current_count + 1
        return True

    def get_retry_budget(self, service_name: str) -> Dict[str, Any]:
        """Get current retry budget status."""
        now = datetime.utcnow()
        minute_key = now.strftime("%Y-%m-%d-%H-%M")

        if service_name not in self._budgets:
            return {"used": 0, "limit": 100, "remaining": 100}

        used = self._budgets[service_name].get(minute_key, 0)
        limit = 100  # Default

        return {"used": used, "limit": limit, "remaining": max(0, limit - used)}

    def reset_budget(self, service_name: str) -> None:
        """Reset retry budget for a service."""
        if service_name in self._budgets:
            self._budgets[service_name] = {}
