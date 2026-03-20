"""Retry coordinator with budget management and circuit breaker integration.

Provides centralized retry logic with:
- Exponential backoff with jitter
- Per-service and per-endpoint retry budgets
- Budget burst allowance
- Cross-service budget pools
- Circuit breaker integration
- Dead letter queue for failed operations
- Budget exhaustion strategies (FAIL_FAST, DEGRADED, QUEUE)
- Metrics export

For ST-NS-039: Retry Coordinator with Budget Management
For ST-SAFETY-002: Retry Budget Implementation
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from autonomous_control_plane.components.dead_letter_queue import DeadLetterQueue
from autonomous_control_plane.components.retry_budget_manager import (
    BudgetAnalytics,
    RetryBudgetManager,
)
from src.autonomous_control_plane.models.retry_policy import (
    BudgetExceededError,
    BudgetExhaustionStrategy,
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
        - retry_endpoint_attempts: Per-endpoint retry attempts
        - retry_pool_usage: Budget pool usage
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
            "endpoint_attempts": {},
            "pool_usage": {},
        }

    def record_attempt(
        self,
        service_name: str,
        attempt_number: int,
        backoff_ms: float,
        endpoint: str | None = None,
    ) -> None:
        """Record a retry attempt.

        Args:
            service_name: Service being retried
            attempt_number: Current attempt number
            backoff_ms: Backoff delay in milliseconds
            endpoint: Optional endpoint path
        """
        # Update local metrics
        key = f"{service_name}:{attempt_number}"
        self._local_metrics["attempts"][key] = (
            self._local_metrics["attempts"].get(key, 0) + 1
        )
        self._local_metrics["backoff_ms"].append(backoff_ms)

        # Track endpoint-specific metrics
        if endpoint:
            endpoint_key = f"{service_name}:{endpoint}"
            self._local_metrics["endpoint_attempts"][endpoint_key] = (
                self._local_metrics["endpoint_attempts"].get(endpoint_key, 0) + 1
            )

        # Export to InfluxDB if available
        if self._influx:
            tags = {
                "service": service_name,
                "attempt_number": str(attempt_number),
            }
            if endpoint:
                tags["endpoint"] = endpoint

            self._write_to_influx(
                measurement="retry_attempts",
                tags=tags,
                fields={"count": 1, "backoff_ms": backoff_ms},
            )

    def record_success(self, service_name: str, endpoint: str | None = None) -> None:
        """Record a successful retry.

        Args:
            service_name: Service that succeeded
            endpoint: Optional endpoint path
        """
        self._local_metrics["successes"][service_name] = (
            self._local_metrics["successes"].get(service_name, 0) + 1
        )

        if self._influx:
            tags = {"service": service_name}
            if endpoint:
                tags["endpoint"] = endpoint

            self._write_to_influx(
                measurement="retry_success",
                tags=tags,
                fields={"count": 1},
            )

    def record_failure(
        self,
        service_name: str,
        reason: str,
        endpoint: str | None = None,
    ) -> None:
        """Record a failed retry.

        Args:
            service_name: Service that failed
            reason: Failure reason (max_retries, budget_exceeded, circuit_open)
            endpoint: Optional endpoint path
        """
        key = f"{service_name}:{reason}"
        self._local_metrics["failures"][key] = (
            self._local_metrics["failures"].get(key, 0) + 1
        )

        if self._influx:
            tags = {
                "service": service_name,
                "reason": reason,
            }
            if endpoint:
                tags["endpoint"] = endpoint

            self._write_to_influx(
                measurement="retry_failure",
                tags=tags,
                fields={"count": 1},
            )

    def record_budget_exceeded(
        self,
        service_name: str,
        endpoint: str | None = None,
        strategy: str = "FAIL_FAST",
    ) -> None:
        """Record a budget exceeded event.

        Args:
            service_name: Service that exceeded budget
            endpoint: Optional endpoint path
            strategy: Exhaustion strategy used
        """
        self._local_metrics["budget_exceeded"][service_name] = (
            self._local_metrics["budget_exceeded"].get(service_name, 0) + 1
        )

        if self._influx:
            tags = {
                "service": service_name,
                "strategy": strategy,
            }
            if endpoint:
                tags["endpoint"] = endpoint

            self._write_to_influx(
                measurement="retry_budget_exceeded",
                tags=tags,
                fields={"count": 1},
            )

    def record_dlq(self, service_name: str, endpoint: str | None = None) -> None:
        """Record an item added to dead letter queue.

        Args:
            service_name: Service for DLQ item
            endpoint: Optional endpoint path
        """
        self._local_metrics["dlq"][service_name] = (
            self._local_metrics["dlq"].get(service_name, 0) + 1
        )

        if self._influx:
            tags = {"service": service_name}
            if endpoint:
                tags["endpoint"] = endpoint

            self._write_to_influx(
                measurement="retry_dead_letter",
                tags=tags,
                fields={"count": 1},
            )

    def record_pool_usage(self, pool_id: str, usage: int) -> None:
        """Record budget pool usage.

        Args:
            pool_id: Pool identifier
            usage: Current usage amount
        """
        self._local_metrics["pool_usage"][pool_id] = usage

        if self._influx:
            self._write_to_influx(
                measurement="retry_pool_usage",
                tags={"pool_id": pool_id},
                fields={"usage": usage},
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
            "by_endpoint": self._local_metrics["endpoint_attempts"],
            "pool_usage": self._local_metrics["pool_usage"],
        }


class RetryCoordinator:
    """Centralized retry coordinator with budget and circuit breaker integration.

    Coordinates retry operations with:
    - Configurable backoff strategies and jitter
    - Per-service and per-endpoint retry budgets
    - Budget burst allowance with cooldown
    - Cross-service budget pools
    - Circuit breaker state checking
    - Dead letter queue for failures
    - Budget exhaustion strategies (FAIL_FAST, DEGRADED, QUEUE)
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

        # Execute with endpoint-specific budget
        result = await coordinator.execute_with_retry(
            service_name="api_client",
            operation_name="fetch_order",
            endpoint="api/v1/orders/123",
            func=lambda: api.get_order(123),
            policy=RetryPolicy(
                max_attempts=3,
                exhaustion_strategy=BudgetExhaustionStrategy.DEGRADED,
            ),
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
        global_budget_limit: int | None = None,
    ):
        """Initialize retry coordinator.

        Args:
            redis_client: Redis client for budget tracking
            db_engine: Database engine for DLQ
            influx_client: InfluxDB client for metrics
            default_policy: Default retry policy
            global_budget_limit: Optional global budget limit
        """
        self._budget_manager = RetryBudgetManager(
            redis_client=redis_client,
            default_limit=100,
            global_limit=global_budget_limit,
        )
        self._dlq = DeadLetterQueue(db_engine=db_engine)
        self._metrics = RetryMetricsCollector(influx_client=influx_client)
        self._default_policy = default_policy or RetryPolicy()
        self._circuit_breaker_registry = CircuitBreakerRegistry()
        self._queued_operations: list[RetryOperation] = []
        self._degraded_services: dict[str, float] = {}  # service -> throttle rate

    def register_endpoint_pattern(
        self,
        service_name: str,
        endpoint_pattern: str,
        limit: int | None = None,
        exhaustion_strategy: BudgetExhaustionStrategy | None = None,
    ) -> None:
        """Register an endpoint pattern for budget tracking.

        Args:
            service_name: Service identifier
            endpoint_pattern: Endpoint pattern (e.g., "api/v1/orders/*")
            limit: Budget limit for this endpoint
            exhaustion_strategy: Strategy when budget is exhausted
        """
        strategy = exhaustion_strategy or BudgetExhaustionStrategy.FAIL_FAST
        self._budget_manager.register_endpoint_pattern(
            service_name, endpoint_pattern, limit, strategy
        )

    def create_budget_pool(
        self,
        pool_id: str,
        name: str,
        services: list[str],
        total_budget: int = 1000,
        priority_allocation: dict[str, int] | None = None,
        emergency_reserve: int = 100,
    ) -> None:
        """Create a budget pool for cross-service sharing.

        Args:
            pool_id: Unique pool identifier
            name: Human-readable pool name
            services: List of services in the pool
            total_budget: Total budget for the pool
            priority_allocation: Priority-based allocation percentages
            emergency_reserve: Emergency reserve amount
        """
        self._budget_manager.create_budget_pool(
            pool_id=pool_id,
            name=name,
            services=services,
            total_budget=total_budget,
            priority_allocation=priority_allocation,
            emergency_reserve=emergency_reserve,
        )

    async def execute_with_retry(
        self,
        service_name: str,
        operation_name: str,
        func: Callable[[], Awaitable[T]],
        policy: RetryPolicy | None = None,
        operation_id: str | None = None,
        endpoint: str | None = None,
    ) -> T:
        """Execute a function with retry logic.

        Args:
            service_name: Service identifier for budget/circuit tracking
            operation_name: Human-readable operation name
            func: Async function to execute
            policy: Retry policy (uses default if None)
            operation_id: Optional operation identifier
            endpoint: Optional endpoint path for per-endpoint budgets

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
                    self._metrics.record_failure(service_name, "circuit_open", endpoint)
                    raise RetryAborted(f"Circuit breaker open: {e}") from e

            # Check for degraded mode throttling
            if service_name in self._degraded_services:
                throttle_rate = self._degraded_services[service_name]
                import random

                if random.random() > throttle_rate:
                    logger.warning(
                        f"Throttling request for {service_name} in degraded mode"
                    )
                    await asyncio.sleep(0.1)
                    continue

            try:
                # Attempt execution
                result = await func()

                # Success
                operation.status = RetryStatus.SUCCESS
                self._metrics.record_success(service_name, endpoint)
                logger.info(
                    f"Operation {operation_name} succeeded on attempt {attempt}"
                )
                return result

            except policy.non_retryable_exceptions as e:
                # Non-retryable exception - fail immediately
                operation.status = RetryStatus.FAILED
                self._metrics.record_failure(service_name, "non_retryable", endpoint)
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
                if endpoint and policy.endpoint_pattern:
                    # Use endpoint-specific budget check
                    allowed, remaining, strategy = (
                        self._budget_manager.check_and_consume_endpoint(
                            service_name,
                            endpoint,
                            policy.budget_limit_per_minute,
                            policy.burst_config,
                        )
                    )
                else:
                    # Use service-level budget check
                    allowed, remaining = self._budget_manager.check_and_consume(
                        service_name,
                        policy.budget_limit_per_minute,
                        policy.burst_config,
                    )
                    strategy = policy.exhaustion_strategy

                if not allowed:
                    operation.status = RetryStatus.BUDGET_EXCEEDED
                    self._metrics.record_budget_exceeded(
                        service_name, endpoint, strategy.name
                    )

                    # Handle based on exhaustion strategy
                    if strategy == BudgetExhaustionStrategy.FAIL_FAST:
                        # Add to DLQ and fail
                        self._add_to_dlq(operation, str(e))
                        raise BudgetExceededError(
                            f"Retry budget exceeded for {service_name}"
                        ) from e
                    elif strategy == BudgetExhaustionStrategy.DEGRADED:
                        # Enter degraded mode (throttle)
                        logger.warning(f"Entering degraded mode for {service_name}")
                        self._degraded_services[service_name] = 0.5  # 50% throttle
                        # Continue with retry but throttled
                    elif strategy == BudgetExhaustionStrategy.QUEUE:
                        # Queue for later processing
                        logger.info(f"Queuing operation {operation_name} for later")
                        self._queued_operations.append(operation)
                        raise BudgetExceededError(
                            f"Operation queued due to budget exhaustion"
                        ) from e

                # Check pool budget if configured
                if policy.pool_id:
                    pool_consumed = self._budget_manager.consume_from_pool(
                        policy.pool_id, service_name, amount=1
                    )
                    if not pool_consumed:
                        logger.warning(
                            f"Pool {policy.pool_id} budget exhausted for {service_name}"
                        )

                # Calculate backoff
                backoff_ms = policy.calculate_delay(attempt)
                backoff_seconds = backoff_ms / 1000.0

                self._metrics.record_attempt(
                    service_name, attempt, backoff_ms, endpoint
                )

                logger.warning(
                    f"Operation {operation_name} attempt {attempt} failed: {e}. "
                    f"Retrying in {backoff_seconds:.2f}s... "
                    f"(budget remaining: {remaining})"
                )

                # Wait before retry
                await asyncio.sleep(backoff_seconds)

        # Max retries exceeded
        operation.status = RetryStatus.FAILED
        self._metrics.record_failure(service_name, "max_retries", endpoint)

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

    def get_endpoint_budget_status(
        self,
        service_name: str,
        endpoint_pattern: str,
    ) -> dict[str, Any]:
        """Get retry budget status for an endpoint.

        Args:
            service_name: Service identifier
            endpoint_pattern: Endpoint pattern

        Returns:
            Budget status dictionary
        """
        return self._budget_manager.get_endpoint_budget_status(
            service_name, endpoint_pattern
        )

    def get_all_budgets(self) -> list[dict[str, Any]]:
        """Get all service budgets.

        Returns:
            List of budget status dictionaries
        """
        return self._budget_manager.get_all_budgets()

    def get_all_endpoint_budgets(self) -> list[dict[str, Any]]:
        """Get all endpoint budgets.

        Returns:
            List of endpoint budget status dictionaries
        """
        return [
            self._budget_manager.get_endpoint_budget_status(
                budget.service_name, budget.endpoint_pattern
            )
            for budget in self._budget_manager._local_endpoint_budgets.values()
        ]

    def reset_budget(
        self,
        service_name: str,
        endpoint_pattern: str | None = None,
    ) -> None:
        """Reset retry budget for a service or endpoint.

        Args:
            service_name: Service to reset
            endpoint_pattern: Optional endpoint pattern
        """
        self._budget_manager.reset_budget(service_name, endpoint_pattern)

        # Also exit degraded mode if active
        if service_name in self._degraded_services:
            del self._degraded_services[service_name]
            logger.info(f"Exited degraded mode for {service_name}")

    def get_pool_status(self, pool_id: str) -> dict[str, Any] | None:
        """Get status of a budget pool.

        Args:
            pool_id: Pool identifier

        Returns:
            Pool status dictionary or None
        """
        return self._budget_manager.get_pool_status(pool_id)

    def get_all_pools(self) -> list[dict[str, Any]]:
        """Get all budget pools.

        Returns:
            List of pool status dictionaries
        """
        return self._budget_manager.get_all_pools()

    def unlock_emergency_reserve(self, pool_id: str) -> bool:
        """Unlock emergency reserve for a pool.

        Args:
            pool_id: Pool identifier

        Returns:
            True if unlocked successfully
        """
        return self._budget_manager.unlock_emergency_reserve(pool_id)

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

    def get_queued_operations(self) -> list[dict[str, Any]]:
        """Get queued operations (for QUEUE exhaustion strategy).

        Returns:
            List of queued operations
        """
        return [op.to_dict() for op in self._queued_operations]

    def clear_queued_operations(self) -> int:
        """Clear all queued operations.

        Returns:
            Number of operations cleared
        """
        count = len(self._queued_operations)
        self._queued_operations.clear()
        return count

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

    def get_analytics(self) -> BudgetAnalytics:
        """Get budget analytics.

        Returns:
            BudgetAnalytics instance
        """
        return self._budget_manager.get_analytics()

    def export_analytics_to_influxdb(
        self,
        bucket: str = "chiseai",
    ) -> None:
        """Export analytics to InfluxDB.

        Args:
            bucket: InfluxDB bucket name
        """
        # This would need the influx_client to be passed or stored
        # For now, just log that it would be exported
        logger.info("Analytics export requested")


def datetime_now() -> Any:
    """Get current datetime."""
    from datetime import UTC, datetime

    return datetime.now(UTC)
