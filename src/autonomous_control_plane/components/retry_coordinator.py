"""Retry coordinator with budget management and circuit breaker integration.

Provides centralized retry logic with:
- Exponential backoff with jitter
- Per-service retry budgets
- Circuit breaker integration
- Dead letter queue for failed operations
- Metrics export

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from src.autonomous_control_plane.components.dead_letter_queue import DeadLetterQueue
from src.autonomous_control_plane.components.retry_budget_manager import (
    RetryBudgetManager,
)
from src.autonomous_control_plane.models.retry_policy import (
    BudgetExceededError,
    MaxRetriesExceededError,
    RetryAborted,
    RetryOperation,
    RetryPolicy,
    RetryStatus,
)
from src.common.circuit_breaker import CircuitBreakerOpen, CircuitBreakerRegistry

if TYPE_CHECKING:
    from influxdb_client import InfluxDBClient
    from redis import Redis
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryMetricsCollector:
    """Collects and exports retry metrics.

    Exports metrics to InfluxDB for monitoring and alerting.

    Metrics:
        - retry_attempts_total: Total retry attempts by service
        - retry_success_total: Successful retries
        - retry_failure_total: Failed retries by reason
        - retry_budget_exceeded_total: Budget exceeded events
        - retry_dead_letter_total: Items added to DLQ
        - retry_backoff_ms: Backoff delay histogram
    """

    def __init__(
        self,
        influx_client: InfluxDBClient | None = None,
        bucket: str = "chiseai",
    ):
        """Initialize metrics collector.

        Args:
            influx_client: InfluxDB client for metrics export
            bucket: InfluxDB bucket name
        """
        self._influx = influx_client
        self._bucket = bucket
        self._local_metrics: dict[str, Any] = {
            "attempts": {},
            "successes": {},
            "failures": {},
            "budget_exceeded": {},
            "dlq": {},
            "backoff_ms": [],
        }

    def record_attempt(
        self,
        service_name: str,
        attempt_number: int,
        backoff_ms: float,
    ) -> None:
        """Record a retry attempt.

        Args:
            service_name: Service being retried
            attempt_number: Current attempt number
            backoff_ms: Backoff delay in milliseconds
        """
        # Update local metrics
        key = f"{service_name}:{attempt_number}"
        self._local_metrics["attempts"][key] = (
            self._local_metrics["attempts"].get(key, 0) + 1
        )
        self._local_metrics["backoff_ms"].append(backoff_ms)

        # Export to InfluxDB if available
        if self._influx:
            self._write_to_influx(
                measurement="retry_attempts",
                tags={
                    "service": service_name,
                    "attempt_number": str(attempt_number),
                },
                fields={"count": 1, "backoff_ms": backoff_ms},
            )

    def record_success(self, service_name: str) -> None:
        """Record a successful retry.

        Args:
            service_name: Service that succeeded
        """
        self._local_metrics["successes"][service_name] = (
            self._local_metrics["successes"].get(service_name, 0) + 1
        )

        if self._influx:
            self._write_to_influx(
                measurement="retry_success",
                tags={"service": service_name},
                fields={"count": 1},
            )

    def record_failure(
        self,
        service_name: str,
        reason: str,
    ) -> None:
        """Record a failed retry.

        Args:
            service_name: Service that failed
            reason: Failure reason (max_retries, budget_exceeded, circuit_open)
        """
        key = f"{service_name}:{reason}"
        self._local_metrics["failures"][key] = (
            self._local_metrics["failures"].get(key, 0) + 1
        )

        if self._influx:
            self._write_to_influx(
                measurement="retry_failure",
                tags={
                    "service": service_name,
                    "reason": reason,
                },
                fields={"count": 1},
            )

    def record_budget_exceeded(self, service_name: str) -> None:
        """Record a budget exceeded event.

        Args:
            service_name: Service that exceeded budget
        """
        self._local_metrics["budget_exceeded"][service_name] = (
            self._local_metrics["budget_exceeded"].get(service_name, 0) + 1
        )

        if self._influx:
            self._write_to_influx(
                measurement="retry_budget_exceeded",
                tags={"service": service_name},
                fields={"count": 1},
            )

    def record_dlq(self, service_name: str) -> None:
        """Record an item added to dead letter queue.

        Args:
            service_name: Service for DLQ item
        """
        self._local_metrics["dlq"][service_name] = (
            self._local_metrics["dlq"].get(service_name, 0) + 1
        )

        if self._influx:
            self._write_to_influx(
                measurement="retry_dead_letter",
                tags={"service": service_name},
                fields={"count": 1},
            )

    def _write_to_influx(
        self,
        measurement: str,
        tags: dict[str, str],
        fields: dict[str, Any],
    ) -> None:
        """Write data point to InfluxDB."""
        if not self._influx:
            return

        try:
            from influxdb_client.client.write_api import SYNCHRONOUS

            write_api = self._influx.write_api(write_options=SYNCHRONOUS)

            point = {
                "measurement": measurement,
                "tags": tags,
                "fields": fields,
                "time": int(time.time() * 1e9),  # Nanoseconds
            }

            write_api.write(bucket=self._bucket, record=point)

        except Exception as e:
            logger.error(f"Failed to write metrics to InfluxDB: {e}")

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics summary.

        Returns:
            Metrics dictionary
        """
        total_attempts = sum(self._local_metrics["attempts"].values())
        total_successes = sum(self._local_metrics["successes"].values())
        total_failures = sum(self._local_metrics["failures"].values())
        total_budget_exceeded = sum(self._local_metrics["budget_exceeded"].values())
        total_dlq = sum(self._local_metrics["dlq"].values())

        backoff_times = self._local_metrics["backoff_ms"]
        avg_backoff = sum(backoff_times) / len(backoff_times) if backoff_times else 0

        return {
            "total_attempts": total_attempts,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "total_budget_exceeded": total_budget_exceeded,
            "total_dlq": total_dlq,
            "success_rate": (
                total_successes / total_attempts if total_attempts > 0 else 0
            ),
            "avg_backoff_ms": avg_backoff,
            "by_service": {
                "attempts": self._local_metrics["attempts"],
                "successes": self._local_metrics["successes"],
                "failures": self._local_metrics["failures"],
            },
        }


class RetryCoordinator:
    """Centralized retry coordinator with budget and circuit breaker integration.

    Coordinates retry operations with:
    - Configurable backoff strategies and jitter
    - Per-service retry budgets
    - Circuit breaker state checking
    - Dead letter queue for failures
    - Metrics collection

    Example:
        coordinator = RetryCoordinator(
            redis_client=redis,
            db_engine=db_engine,
        )

        # Execute with retry
        result = await coordinator.execute_with_retry(
            service_name="api_client",
            operation_name="fetch_data",
            func=lambda: api.get_data(),
            policy=RetryPolicy(max_attempts=3),
        )

        # Get metrics
        metrics = coordinator.get_metrics()
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        db_engine: Engine | None = None,
        influx_client: InfluxDBClient | None = None,
        default_policy: RetryPolicy | None = None,
    ):
        """Initialize retry coordinator.

        Args:
            redis_client: Redis client for budget tracking
            db_engine: Database engine for DLQ
            influx_client: InfluxDB client for metrics
            default_policy: Default retry policy
        """
        self._budget_manager = RetryBudgetManager(
            redis_client=redis_client,
            default_limit=100,
        )
        self._dlq = DeadLetterQueue(db_engine=db_engine)
        self._metrics = RetryMetricsCollector(influx_client=influx_client)
        self._default_policy = default_policy or RetryPolicy()
        self._circuit_breaker_registry = CircuitBreakerRegistry()

    async def execute_with_retry(
        self,
        service_name: str,
        operation_name: str,
        func: Callable[[], Awaitable[T]],
        policy: RetryPolicy | None = None,
        operation_id: str | None = None,
    ) -> T:
        """Execute a function with retry logic.

        Args:
            service_name: Service identifier for budget/circuit tracking
            operation_name: Human-readable operation name
            func: Async function to execute
            policy: Retry policy (uses default if None)
            operation_id: Optional operation identifier

        Returns:
            Function result

        Raises:
            RetryAborted: If circuit breaker is open
            BudgetExceededError: If retry budget exceeded
            MaxRetriesExceededError: If max retries exceeded
            Exception: Original exception from function
        """
        policy = policy or self._default_policy
        operation_id = operation_id or str(uuid.uuid4())

        operation = RetryOperation(
            id=operation_id,
            service_name=service_name,
            operation_name=operation_name,
            func=func,
            policy=policy,
        )

        last_exception: Exception | None = None

        for attempt in range(1, policy.max_attempts + 1):
            operation.attempt_count = attempt
            operation.last_attempt_at = datetime_now()
            operation.status = RetryStatus.IN_PROGRESS

            # Check circuit breaker before each attempt
            if policy.circuit_breaker_name:
                try:
                    self._check_circuit_breaker(policy.circuit_breaker_name)
                except CircuitBreakerOpen as e:
                    operation.status = RetryStatus.CIRCUIT_OPEN
                    self._metrics.record_failure(service_name, "circuit_open")
                    raise RetryAborted(f"Circuit breaker open: {e}") from e

            try:
                # Attempt execution
                result = await func()

                # Success
                operation.status = RetryStatus.SUCCESS
                self._metrics.record_success(service_name)
                logger.info(
                    f"Operation {operation_name} succeeded on attempt {attempt}"
                )
                return result

            except policy.non_retryable_exceptions as e:
                # Non-retryable exception - fail immediately
                operation.status = RetryStatus.FAILED
                self._metrics.record_failure(service_name, "non_retryable")
                logger.error(
                    f"Operation {operation_name} failed with non-retryable error: {e}"
                )
                raise

            except policy.retryable_exceptions as e:
                last_exception = e
                operation.last_error = str(e)

                # Check if this was the last attempt
                if attempt >= policy.max_attempts:
                    break

                # Check retry budget
                allowed, remaining = self._budget_manager.check_and_consume(
                    service_name, policy.budget_limit_per_minute
                )

                if not allowed:
                    operation.status = RetryStatus.BUDGET_EXCEEDED
                    self._metrics.record_budget_exceeded(service_name)

                    # Add to DLQ
                    self._add_to_dlq(operation, str(e))

                    raise BudgetExceededError(
                        f"Retry budget exceeded for {service_name}"
                    ) from e

                # Calculate backoff
                backoff_ms = policy.calculate_delay(attempt)
                backoff_seconds = backoff_ms / 1000.0

                self._metrics.record_attempt(service_name, attempt, backoff_ms)

                logger.warning(
                    f"Operation {operation_name} attempt {attempt} failed: {e}. "
                    f"Retrying in {backoff_seconds:.2f}s... "
                    f"(budget remaining: {remaining})"
                )

                # Wait before retry
                await asyncio.sleep(backoff_seconds)

        # Max retries exceeded
        operation.status = RetryStatus.FAILED
        self._metrics.record_failure(service_name, "max_retries")

        # Add to DLQ
        error_msg = str(last_exception) if last_exception else "Max retries exceeded"
        self._add_to_dlq(operation, error_msg)

        raise MaxRetriesExceededError(
            f"Operation {operation_name} failed after {policy.max_attempts} attempts"
        ) from last_exception

    def _check_circuit_breaker(self, name: str) -> None:
        """Check if circuit breaker allows execution.

        Args:
            name: Circuit breaker name

        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        cb = self._circuit_breaker_registry.get(name)
        if cb and not cb.can_execute():
            raise CircuitBreakerOpen(f"Circuit '{name}' is {cb.state.name}")

    def _add_to_dlq(self, operation: RetryOperation, error_message: str) -> None:
        """Add failed operation to dead letter queue.

        Args:
            operation: Failed operation
            error_message: Error that caused failure
        """
        self._dlq.enqueue(
            service_name=operation.service_name,
            operation=operation.operation_name,
            payload={
                "operation_id": operation.id,
                "policy": operation.policy.to_dict(),
                "attempt_count": operation.attempt_count,
            },
            error_message=error_message,
            retry_count=operation.attempt_count,
        )
        self._metrics.record_dlq(operation.service_name)

    def get_budget_status(self, service_name: str) -> dict[str, Any]:
        """Get retry budget status for a service.

        Args:
            service_name: Service to check

        Returns:
            Budget status dictionary
        """
        return self._budget_manager.get_budget_status(service_name)

    def get_all_budgets(self) -> list[dict[str, Any]]:
        """Get all service budgets.

        Returns:
            List of budget status dictionaries
        """
        return self._budget_manager.get_all_budgets()

    def reset_budget(self, service_name: str) -> None:
        """Reset retry budget for a service.

        Args:
            service_name: Service to reset
        """
        self._budget_manager.reset_budget(service_name)

    def get_dlq_items(
        self,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get items from dead letter queue.

        Args:
            service_name: Filter by service
            limit: Maximum items to return

        Returns:
            List of DLQ items as dictionaries
        """
        items = self._dlq.list_pending(service_name=service_name, limit=limit)
        return [item.to_dict() for item in items]

    def retry_dlq_item(self, item_id: str) -> bool:
        """Mark a DLQ item as retried.

        Args:
            item_id: Item identifier

        Returns:
            True if item was updated
        """
        return self._dlq.mark_retried(item_id, success=False)

    def delete_dlq_item(self, item_id: str) -> bool:
        """Delete a DLQ item.

        Args:
            item_id: Item identifier

        Returns:
            True if item was deleted
        """
        return self._dlq.delete(item_id)

    def get_metrics(self) -> dict[str, Any]:
        """Get retry metrics.

        Returns:
            Metrics dictionary
        """
        return self._metrics.get_metrics()

    def get_circuit_breaker_states(self) -> dict[str, dict[str, Any]]:
        """Get all circuit breaker states.

        Returns:
            Dictionary of circuit breaker states
        """
        return self._circuit_breaker_registry.get_all_states()


def datetime_now() -> Any:
    """Get current datetime."""
    from datetime import datetime

    return datetime.utcnow()
