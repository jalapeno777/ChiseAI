"""Retry budget management with Redis backing.

Provides per-service and per-endpoint retry budget tracking and enforcement using
Redis for distributed state management.

Features:
- Per-service budget tracking
- Per-endpoint budget tracking with wildcard support
- Hierarchical budget inheritance (endpoint → service → global)
- Budget burst allowance with cooldown
- Cross-service budget pools
- Budget exhaustion strategies
- Budget analytics and forecasting

For ST-NS-039: Retry Coordinator with Budget Management
For ST-SAFETY-002: Retry Budget Implementation
"""

from __future__ import annotations

import fnmatch
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis

from autonomous_control_plane.models.retry_policy import (
    BudgetBurstConfig,
    BudgetExhaustionStrategy,
    BudgetPool,
    EndpointRetryBudget,
    RetryBudget,
)

logger = logging.getLogger(__name__)


class BudgetAnalytics:
    """Analytics and forecasting for retry budgets.

    Tracks budget consumption patterns and provides forecasting
    for time-to-exhaustion predictions.
    """

    def __init__(self, redis_client: Redis | None = None):
        """Initialize analytics.

        Args:
            redis_client: Redis client for storing analytics data
        """
        self._redis = redis_client
        self._local_metrics: dict[str, dict[str, Any]] = {}

    def record_consumption(
        self,
        budget_key: str,
        amount: int = 1,
        success: bool = True,
    ) -> None:
        """Record budget consumption event.

        Args:
            budget_key: Budget identifier
            amount: Amount consumed
            success: Whether the retry succeeded
        """
        timestamp = time.time()

        if budget_key not in self._local_metrics:
            self._local_metrics[budget_key] = {
                "consumption_history": [],
                "success_count": 0,
                "failure_count": 0,
                "total_retries": 0,
            }

        metrics = self._local_metrics[budget_key]
        metrics["consumption_history"].append(
            {
                "timestamp": timestamp,
                "amount": amount,
                "success": success,
            }
        )
        metrics["total_retries"] += amount
        if success:
            metrics["success_count"] += 1
        else:
            metrics["failure_count"] += 1

        # Trim history to last 1000 entries
        if len(metrics["consumption_history"]) > 1000:
            metrics["consumption_history"] = metrics["consumption_history"][-1000:]

        # Store in Redis if available
        if self._redis:
            try:
                key = f"retry_budget_analytics:{budget_key}"
                self._redis.hincrby(key, "total_retries", amount)
                self._redis.hincrby(
                    key, "success_count" if success else "failure_count", 1
                )
                self._redis.expire(key, 86400)  # 24 hour TTL
            except Exception as e:
                logger.error(f"Failed to record analytics to Redis: {e}")

    def get_consumption_rate(self, budget_key: str, window_seconds: int = 60) -> float:
        """Calculate consumption rate over a time window.

        Args:
            budget_key: Budget identifier
            window_seconds: Time window in seconds

        Returns:
            Consumption rate (retries per second)
        """
        if budget_key not in self._local_metrics:
            return 0.0

        cutoff_time = time.time() - window_seconds
        history = self._local_metrics[budget_key].get("consumption_history", [])

        recent_consumption = sum(1 for h in history if h["timestamp"] >= cutoff_time)

        return recent_consumption / window_seconds if window_seconds > 0 else 0.0

    def predict_time_to_exhaustion(
        self,
        budget_key: str,
        remaining_budget: int,
    ) -> float | None:
        """Predict time until budget exhaustion.

        Args:
            budget_key: Budget identifier
            remaining_budget: Remaining budget amount

        Returns:
            Predicted seconds until exhaustion, or None if can't predict
        """
        rate = self.get_consumption_rate(budget_key, window_seconds=60)
        if rate <= 0:
            return None
        return remaining_budget / rate

    def get_efficiency_metrics(self, budget_key: str) -> dict[str, float]:
        """Get budget efficiency metrics.

        Returns:
            Dictionary with efficiency metrics
        """
        if budget_key not in self._local_metrics:
            return {
                "retries_per_success": 0.0,
                "success_rate": 0.0,
                "avg_consumption_rate": 0.0,
            }

        metrics = self._local_metrics[budget_key]
        total = metrics["total_retries"]
        successes = metrics["success_count"]
        metrics["failure_count"]

        return {
            "retries_per_success": total / max(successes, 1),
            "success_rate": successes / max(total, 1),
            "avg_consumption_rate": self.get_consumption_rate(budget_key),
        }

    def export_to_influxdb(self, influx_client: Any, bucket: str = "chiseai") -> None:
        """Export analytics metrics to InfluxDB.

        Args:
            influx_client: InfluxDB client
            bucket: InfluxDB bucket name
        """
        if not influx_client:
            return

        try:
            from influxdb_client.client.write_api import SYNCHRONOUS

            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            timestamp = int(time.time() * 1e9)

            for budget_key, metrics in self._local_metrics.items():
                efficiency = self.get_efficiency_metrics(budget_key)
                consumption_rate = self.get_consumption_rate(budget_key)

                point = {
                    "measurement": "retry_budget_analytics",
                    "tags": {"budget_key": budget_key},
                    "fields": {
                        "consumption_rate": consumption_rate,
                        "retries_per_success": efficiency["retries_per_success"],
                        "success_rate": efficiency["success_rate"],
                        "total_retries": metrics["total_retries"],
                    },
                    "time": timestamp,
                }
                write_api.write(bucket=bucket, record=point)

        except Exception as e:
            logger.error(f"Failed to export analytics to InfluxDB: {e}")


class RetryBudgetManager:
    """Manages per-service and per-endpoint retry budgets with Redis backing.

    Tracks retry attempts per service and endpoint with minute-bucketed accounting.
    Uses Redis for distributed state in multi-instance deployments.

    Features:
    - Per-service budget tracking
    - Per-endpoint budget tracking with wildcard patterns
    - Hierarchical budget inheritance (endpoint → service → global)
    - Budget burst allowance with cooldown
    - Cross-service budget pools
    - Budget exhaustion strategies

    Redis Key Patterns:
        retry_budget:{service_name}:{YYYY-MM-DD-HH-MM} - Service budgets
        retry_budget:{service_name}:{endpoint}:{YYYY-MM-DD-HH-MM} - Endpoint budgets
        retry_budget_pool:{pool_id} - Budget pool state
        retry_budget_burst:{budget_key} - Burst usage tracking
        retry_budget_analytics:{budget_key} - Analytics data

    Example:
        manager = RetryBudgetManager(redis_client)

        # Check and consume budget for service
        if manager.check_and_consume("redis_service", limit=100):
            # Proceed with retry
            pass
        else:
            # Budget exceeded
            raise BudgetExceededError()

        # Check and consume budget for endpoint
        if manager.check_and_consume_endpoint(
            "api_service", "api/v1/orders/123", limit=50
        ):
            # Proceed with retry
            pass
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        default_limit: int = 100,
        ttl_seconds: int = 120,
        global_limit: int | None = None,
    ):
        """Initialize budget manager.

        Args:
            redis_client: Redis client for distributed state
            default_limit: Default retry limit per minute
            ttl_seconds: TTL for Redis keys (2x window for safety)
            global_limit: Optional global budget limit across all services
        """
        self._redis = redis_client
        self._default_limit = default_limit
        self._ttl_seconds = ttl_seconds
        self._global_limit = global_limit
        self._local_budgets: dict[str, RetryBudget] = {}
        self._local_endpoint_budgets: dict[str, EndpointRetryBudget] = {}
        self._budget_pools: dict[str, BudgetPool] = {}
        self._endpoint_patterns: dict[str, list[str]] = {}  # service -> patterns
        self._analytics = BudgetAnalytics(redis_client)

    def _get_budget_key(
        self,
        service_name: str,
        endpoint: str | None = None,
        dt: datetime | None = None,
    ) -> str:
        """Generate Redis key for budget.

        Args:
            service_name: Service identifier
            endpoint: Optional endpoint pattern
            dt: Datetime for key (default: now)

        Returns:
            Redis key string
        """
        if dt is None:
            dt = datetime.now(UTC)
        time_bucket = dt.strftime("%Y-%m-%d-%H-%M")

        if endpoint:
            return f"retry_budget:{service_name}:{endpoint}:{time_bucket}"
        return f"retry_budget:{service_name}:{time_bucket}"

    def _get_current_window(self) -> datetime:
        """Get current minute window."""
        return datetime.now(UTC).replace(second=0, microsecond=0)

    def register_endpoint_pattern(
        self,
        service_name: str,
        endpoint_pattern: str,
        limit: int | None = None,
        exhaustion_strategy: BudgetExhaustionStrategy = BudgetExhaustionStrategy.FAIL_FAST,
    ) -> None:
        """Register an endpoint pattern for budget tracking.

        Args:
            service_name: Service identifier
            endpoint_pattern: Endpoint pattern (e.g., "api/v1/orders/*")
            limit: Budget limit for this endpoint (uses default if None)
            exhaustion_strategy: Strategy when budget is exhausted
        """
        if service_name not in self._endpoint_patterns:
            self._endpoint_patterns[service_name] = []

        if endpoint_pattern not in self._endpoint_patterns[service_name]:
            self._endpoint_patterns[service_name].append(endpoint_pattern)

        # Create local budget entry
        full_key = f"{service_name}:{endpoint_pattern}"
        self._local_endpoint_budgets[full_key] = EndpointRetryBudget(
            service_name=service_name,
            endpoint_pattern=endpoint_pattern,
            limit=limit or self._default_limit,
            exhaustion_strategy=exhaustion_strategy,
            parent_service=service_name,
            window_start=self._get_current_window(),
        )

        logger.info(
            f"Registered endpoint pattern '{endpoint_pattern}' for service '{service_name}'"
        )

    def _match_endpoint_pattern(
        self,
        service_name: str,
        endpoint: str,
    ) -> str | None:
        """Find matching endpoint pattern for an endpoint.

        Args:
            service_name: Service identifier
            endpoint: Actual endpoint path

        Returns:
            Matching pattern or None
        """
        patterns = self._endpoint_patterns.get(service_name, [])

        for pattern in patterns:
            if fnmatch.fnmatch(endpoint, pattern):
                return pattern

        return None

    def check_and_consume(
        self,
        service_name: str,
        limit: int | None = None,
        burst_config: BudgetBurstConfig | None = None,
    ) -> tuple[bool, int]:
        """Check budget and consume if available.

        Args:
            service_name: Service to check
            limit: Budget limit (uses default if None)
            burst_config: Optional burst configuration

        Returns:
            Tuple of (allowed: bool, remaining: int)
        """
        limit = limit or self._default_limit

        # Check global limit first
        if self._global_limit is not None:
            global_allowed, global_remaining = self._check_global_budget()
            if not global_allowed:
                logger.warning("Global retry budget exceeded")
                return False, 0

        if self._redis:
            return self._check_and_consume_redis(
                service_name, limit, burst_config=burst_config
            )
        else:
            return self._check_and_consume_local(
                service_name, limit, burst_config=burst_config
            )

    def check_and_consume_endpoint(
        self,
        service_name: str,
        endpoint: str,
        limit: int | None = None,
        burst_config: BudgetBurstConfig | None = None,
        check_hierarchy: bool = True,
    ) -> tuple[bool, int, BudgetExhaustionStrategy]:
        """Check endpoint budget and consume if available.

        Supports hierarchical budget inheritance - checks endpoint budget first,
        then falls back to service budget if endpoint budget exceeded.

        Args:
            service_name: Service identifier
            endpoint: Endpoint path
            limit: Budget limit (uses default if None)
            burst_config: Optional burst configuration
            check_hierarchy: Whether to check parent service budget

        Returns:
            Tuple of (allowed: bool, remaining: int, strategy: BudgetExhaustionStrategy)
        """
        # Find matching pattern
        pattern = self._match_endpoint_pattern(service_name, endpoint)

        if pattern:
            # Check endpoint-specific budget
            allowed, remaining = self._check_and_consume_endpoint_budget(
                service_name, pattern, limit, burst_config
            )

            if allowed:
                # Record analytics
                full_key = f"{service_name}:{pattern}"
                self._analytics.record_consumption(full_key, success=True)

                endpoint_budget = self._local_endpoint_budgets.get(full_key)
                strategy = (
                    endpoint_budget.exhaustion_strategy
                    if endpoint_budget
                    else BudgetExhaustionStrategy.FAIL_FAST
                )
                return True, remaining, strategy

            # Endpoint budget exceeded - check hierarchy
            if check_hierarchy:
                service_allowed, service_remaining = self.check_and_consume(
                    service_name, limit, burst_config
                )
                if service_allowed:
                    return True, service_remaining, BudgetExhaustionStrategy.FAIL_FAST

            # Both exceeded - return endpoint strategy
            full_key = f"{service_name}:{pattern}"
            endpoint_budget = self._local_endpoint_budgets.get(full_key)
            strategy = (
                endpoint_budget.exhaustion_strategy
                if endpoint_budget
                else BudgetExhaustionStrategy.FAIL_FAST
            )
            return False, 0, strategy

        # No pattern match - fall back to service budget
        allowed, remaining = self.check_and_consume(service_name, limit, burst_config)
        return allowed, remaining, BudgetExhaustionStrategy.FAIL_FAST

    def _check_and_consume_endpoint_budget(
        self,
        service_name: str,
        endpoint_pattern: str,
        limit: int | None,
        burst_config: BudgetBurstConfig | None,
    ) -> tuple[bool, int]:
        """Check and consume budget for a specific endpoint pattern."""
        limit = limit or self._default_limit
        full_key = f"{service_name}:{endpoint_pattern}"

        if self._redis:
            return self._check_and_consume_redis(
                full_key, limit, is_endpoint=True, burst_config=burst_config
            )
        else:
            return self._check_and_consume_local(
                full_key, limit, is_endpoint=True, burst_config=burst_config
            )

    def _check_global_budget(self) -> tuple[bool, int]:
        """Check global budget across all services."""
        if self._global_limit is None:
            return True, float("inf")  # type: ignore

        if self._redis:
            key = f"retry_budget:global:{self._get_current_window().strftime('%Y-%m-%d-%H-%M')}"
            try:
                current = self._redis.incr(key)
                if current == 1:
                    self._redis.expire(key, self._ttl_seconds)
                return current <= self._global_limit, max(
                    0, self._global_limit - current
                )
            except Exception as e:
                logger.error(f"Redis error checking global budget: {e}")
                return True, self._global_limit
        else:
            # Simple local global budget tracking
            key = "global"
            if key not in self._local_budgets:
                self._local_budgets[key] = RetryBudget(
                    service_name=key,
                    limit=self._global_limit,
                    window_start=self._get_current_window(),
                )

            budget = self._local_budgets[key]
            if budget.window_start < self._get_current_window():
                budget = RetryBudget(
                    service_name=key,
                    limit=self._global_limit,
                    window_start=self._get_current_window(),
                )
                self._local_budgets[key] = budget

            allowed = budget.record_attempt()
            return allowed, max(0, self._global_limit - budget.current_count)

    def _check_and_consume_redis(
        self,
        budget_key: str,
        limit: int,
        is_endpoint: bool = False,
        burst_config: BudgetBurstConfig | None = None,
    ) -> tuple[bool, int]:
        """Check and consume budget using Redis atomic operations."""
        assert (
            self._redis is not None
        ), "_check_and_consume_redis should only be called when redis is set"

        key = self._get_budget_key(budget_key)

        try:
            # Check burst allowance
            effective_limit = limit
            burst_used = 0

            if burst_config:
                burst_limit = burst_config.calculate_burst_limit(limit)
                burst_key = f"retry_budget_burst:{budget_key}"
                burst_count = int(self._redis.get(burst_key) or 0)

                if burst_count < burst_config.max_bursts_per_window:
                    effective_limit = burst_limit
                    burst_used = 1

            # Use Redis INCR for atomic increment
            current = self._redis.incr(key)

            # Set TTL on first increment
            if current == 1:
                self._redis.expire(key, self._ttl_seconds)

            # Track burst usage
            if burst_used and current > limit:
                self._redis.incr(burst_key)
                self._redis.expire(burst_key, burst_config.cooldown_seconds)

            allowed = current <= effective_limit
            remaining = max(0, effective_limit - current)

            if not allowed:
                logger.warning(
                    f"Retry budget exceeded for {budget_key}: {current}/{effective_limit}"
                )

            return allowed, remaining

        except Exception as e:
            logger.error(f"Redis error checking budget for {budget_key}: {e}")
            # Fail open if Redis unavailable (don't block retries)
            return True, limit

    def _check_and_consume_local(
        self,
        budget_key: str,
        limit: int,
        is_endpoint: bool = False,
        burst_config: BudgetBurstConfig | None = None,
    ) -> tuple[bool, int]:
        """Check and consume budget using local tracking."""
        now = self._get_current_window()

        # Get or create budget
        if is_endpoint:
            budgets_dict = self._local_endpoint_budgets
            if budget_key not in budgets_dict:
                # Parse service and endpoint from key
                parts = budget_key.split(":", 1)
                if len(parts) == 2:
                    budgets_dict[budget_key] = EndpointRetryBudget(
                        service_name=parts[0],
                        endpoint_pattern=parts[1],
                        limit=limit,
                        window_start=now,
                    )
                else:
                    # Fallback to regular budget
                    is_endpoint = False
                    budgets_dict = self._local_budgets
                    if budget_key not in budgets_dict:
                        budgets_dict[budget_key] = RetryBudget(
                            service_name=budget_key,
                            limit=limit,
                            window_start=now,
                        )
        else:
            budgets_dict = self._local_budgets
            if budget_key not in budgets_dict:
                budgets_dict[budget_key] = RetryBudget(
                    service_name=budget_key,
                    limit=limit,
                    window_start=now,
                )

        budget = budgets_dict[budget_key]

        # Reset if window changed
        if budget.window_start < now:
            if is_endpoint:
                budget = EndpointRetryBudget(
                    service_name=budget.service_name,
                    endpoint_pattern=budget.endpoint_pattern,
                    limit=limit,
                    window_start=now,
                )
            else:
                budget = RetryBudget(
                    service_name=budget_key,
                    limit=limit,
                    window_start=now,
                )
            budgets_dict[budget_key] = budget

        # Check burst allowance
        effective_limit = limit
        if burst_config:
            burst_limit = burst_config.calculate_burst_limit(limit)
            # Simple local burst tracking - burst allows going beyond base limit
            if not hasattr(self, "_burst_counts"):
                self._burst_counts: dict[str, int] = {}
            burst_key = f"{budget_key}:burst_count"
            burst_count = self._burst_counts.get(burst_key, 0)
            # Allow burst if we haven't exceeded max bursts
            if burst_count < burst_config.max_bursts_per_window:
                effective_limit = burst_limit

        # Check and consume - temporarily set budget limit to effective_limit
        original_limit = budget.limit
        budget.limit = effective_limit
        allowed = budget.record_attempt()
        budget.limit = original_limit

        # Track burst usage when we first exceed the base limit
        if burst_config and budget.current_count == limit + 1:
            burst_key = f"{budget_key}:burst_count"
            self._burst_counts[burst_key] = self._burst_counts.get(burst_key, 0) + 1

        remaining = max(0, effective_limit - budget.current_count)

        if not allowed:
            logger.warning(
                f"Retry budget exceeded for {budget_key}: "
                f"{budget.current_count}/{effective_limit}"
            )

        return allowed, remaining

    def create_budget_pool(
        self,
        pool_id: str,
        name: str,
        services: list[str],
        total_budget: int = 1000,
        priority_allocation: dict[str, int] | None = None,
        emergency_reserve: int = 100,
    ) -> BudgetPool:
        """Create a budget pool for cross-service sharing.

        Args:
            pool_id: Unique pool identifier
            name: Human-readable pool name
            services: List of services in the pool
            total_budget: Total budget for the pool
            priority_allocation: Priority-based allocation percentages
            emergency_reserve: Emergency reserve amount

        Returns:
            Created BudgetPool
        """
        pool = BudgetPool(
            pool_id=pool_id,
            name=name,
            services=services,
            total_budget=total_budget,
            priority_allocation=priority_allocation or {},
            emergency_reserve=emergency_reserve,
        )

        self._budget_pools[pool_id] = pool

        # Store in Redis if available
        if self._redis:
            try:
                key = f"retry_budget_pool:{pool_id}"
                self._redis.hset(
                    key,
                    mapping={
                        "name": name,
                        "services": ",".join(services),
                        "total_budget": total_budget,
                        "used_budget": 0,
                        "emergency_reserve": emergency_reserve,
                        "emergency_unlocked": "false",
                    },
                )
                self._redis.expire(key, 86400)  # 24 hour TTL
            except Exception as e:
                logger.error(f"Failed to store pool in Redis: {e}")

        logger.info(f"Created budget pool '{name}' with {total_budget} budget")
        return pool

    def consume_from_pool(
        self,
        pool_id: str,
        service_name: str,
        amount: int = 1,
    ) -> bool:
        """Consume budget from a pool.

        Args:
            pool_id: Pool identifier
            service_name: Service consuming the budget
            amount: Amount to consume

        Returns:
            True if budget was available, False otherwise
        """
        pool = self._budget_pools.get(pool_id)
        if not pool:
            logger.warning(f"Budget pool '{pool_id}' not found")
            return False

        if service_name not in pool.services:
            logger.warning(f"Service '{service_name}' not in pool '{pool_id}'")
            return False

        # Check priority allocation
        service_allocation = pool.get_service_allocation(service_name)
        service_usage = self._get_pool_service_usage(pool_id, service_name)

        if service_allocation > 0 and service_usage + amount > service_allocation:
            logger.warning(
                f"Service '{service_name}' would exceed allocation in pool '{pool_id}'"
            )
            return False

        if pool.consume_budget(amount):
            self._update_pool_service_usage(pool_id, service_name, amount)

            # Update Redis if available
            if self._redis:
                try:
                    key = f"retry_budget_pool:{pool_id}"
                    self._redis.hincrby(key, "used_budget", amount)
                except Exception as e:
                    logger.error(f"Failed to update pool in Redis: {e}")

            return True

        return False

    def _get_pool_service_usage(self, pool_id: str, service_name: str) -> int:
        """Get current usage for a service in a pool."""
        # Local tracking only for now
        return 0

    def _update_pool_service_usage(
        self,
        pool_id: str,
        service_name: str,
        amount: int,
    ) -> None:
        """Update usage for a service in a pool."""
        # Local tracking only for now
        pass

    def unlock_emergency_reserve(self, pool_id: str) -> bool:
        """Unlock emergency reserve for a pool.

        Args:
            pool_id: Pool identifier

        Returns:
            True if unlocked successfully
        """
        pool = self._budget_pools.get(pool_id)
        if not pool:
            return False

        pool.unlock_emergency_reserve()

        if self._redis:
            try:
                key = f"retry_budget_pool:{pool_id}"
                self._redis.hset(key, "emergency_unlocked", "true")
            except Exception as e:
                logger.error(f"Failed to update pool in Redis: {e}")

        logger.info(f"Unlocked emergency reserve for pool '{pool_id}'")
        return True

    def get_budget_status(
        self,
        service_name: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get current budget status for a service.

        Args:
            service_name: Service to check
            limit: Budget limit (uses default if None)

        Returns:
            Budget status dictionary
        """
        limit = limit or self._default_limit

        if self._redis:
            return self._get_budget_status_redis(service_name, limit)
        else:
            return self._get_budget_status_local(service_name, limit)

    def get_endpoint_budget_status(
        self,
        service_name: str,
        endpoint_pattern: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get current budget status for an endpoint.

        Args:
            service_name: Service identifier
            endpoint_pattern: Endpoint pattern
            limit: Budget limit (uses default if None)

        Returns:
            Budget status dictionary
        """
        limit = limit or self._default_limit
        full_key = f"{service_name}:{endpoint_pattern}"

        if self._redis:
            return self._get_budget_status_redis(full_key, limit, is_endpoint=True)
        else:
            return self._get_budget_status_local(full_key, limit, is_endpoint=True)

    def _get_budget_status_redis(
        self,
        budget_key: str,
        limit: int,
        is_endpoint: bool = False,
    ) -> dict[str, Any]:
        """Get budget status from Redis."""
        assert (
            self._redis is not None
        ), "_get_budget_status_redis should only be called when redis is set"
        key = self._get_budget_key(budget_key)

        try:
            current = int(self._redis.get(key) or 0)
            ttl = self._redis.ttl(key)

            # Get analytics
            analytics_key = f"retry_budget_analytics:{budget_key}"
            analytics_data = self._redis.hgetall(analytics_key) or {}

            result = {
                "budget_key": budget_key,
                "current_count": current,
                "limit": limit,
                "remaining": max(0, limit - current),
                "is_exceeded": current >= limit,
                "window_ttl_seconds": ttl if ttl > 0 else self._ttl_seconds,
                "analytics": {
                    "total_retries": int(analytics_data.get(b"total_retries", 0)),
                    "success_count": int(analytics_data.get(b"success_count", 0)),
                    "failure_count": int(analytics_data.get(b"failure_count", 0)),
                },
            }

            if is_endpoint:
                result["is_endpoint"] = True

            return result
        except Exception as e:
            logger.error(f"Redis error getting budget for {budget_key}: {e}")
            return {
                "budget_key": budget_key,
                "current_count": 0,
                "limit": limit,
                "remaining": limit,
                "is_exceeded": False,
                "error": str(e),
            }

    def _get_budget_status_local(
        self,
        budget_key: str,
        limit: int,
        is_endpoint: bool = False,
    ) -> dict[str, Any]:
        """Get budget status from local tracking."""
        now = self._get_current_window()

        budgets_dict = (
            self._local_endpoint_budgets if is_endpoint else self._local_budgets
        )

        if budget_key in budgets_dict:
            budget = budgets_dict[budget_key]
            if budget.window_start == now:
                result = {
                    "budget_key": budget_key,
                    "current_count": budget.current_count,
                    "limit": limit,
                    "remaining": max(0, limit - budget.current_count),
                    "is_exceeded": budget.is_exceeded,
                    "window_start": budget.window_start.isoformat(),
                }

                if is_endpoint and isinstance(budget, EndpointRetryBudget):
                    result["is_endpoint"] = True
                    result["endpoint_pattern"] = budget.endpoint_pattern
                    result["exhaustion_strategy"] = budget.exhaustion_strategy.name

                return result

        # No budget recorded for current window
        result = {
            "budget_key": budget_key,
            "current_count": 0,
            "limit": limit,
            "remaining": limit,
            "is_exceeded": False,
        }

        if is_endpoint:
            result["is_endpoint"] = True

        return result

    def get_pool_status(self, pool_id: str) -> dict[str, Any] | None:
        """Get status of a budget pool.

        Args:
            pool_id: Pool identifier

        Returns:
            Pool status dictionary or None if not found
        """
        pool = self._budget_pools.get(pool_id)
        if pool:
            return pool.to_dict()

        # Try Redis
        if self._redis:
            try:
                key = f"retry_budget_pool:{pool_id}"
                data = self._redis.hgetall(key)
                if data:
                    return {
                        "pool_id": pool_id,
                        "name": data.get(b"name", b"").decode(),
                        "services": data.get(b"services", b"").decode().split(","),
                        "total_budget": int(data.get(b"total_budget", 0)),
                        "used_budget": int(data.get(b"used_budget", 0)),
                        "emergency_reserve": int(data.get(b"emergency_reserve", 0)),
                        "emergency_unlocked": data.get(b"emergency_unlocked", b"false")
                        == b"true",
                    }
            except Exception as e:
                logger.error(f"Redis error getting pool status: {e}")

        return None

    def reset_budget(
        self, service_name: str, endpoint_pattern: str | None = None
    ) -> None:
        """Reset budget for a service or endpoint.

        Args:
            service_name: Service to reset
            endpoint_pattern: Optional endpoint pattern to reset
        """
        if endpoint_pattern:
            budget_key = f"{service_name}:{endpoint_pattern}"
        else:
            budget_key = service_name

        if self._redis:
            key = self._get_budget_key(budget_key)
            try:
                self._redis.delete(key)
                logger.info(f"Reset retry budget for {budget_key}")
            except Exception as e:
                logger.error(f"Redis error resetting budget for {budget_key}: {e}")
        else:
            if budget_key in self._local_budgets:
                del self._local_budgets[budget_key]
            if budget_key in self._local_endpoint_budgets:
                del self._local_endpoint_budgets[budget_key]
            logger.info(f"Reset retry budget for {budget_key}")

    def get_all_budgets(self) -> list[dict[str, Any]]:
        """Get all active budgets.

        Returns:
            List of budget status dictionaries
        """
        budgets = []

        if self._redis:
            try:
                # Scan for retry budget keys
                pattern = "retry_budget:*"
                cursor = 0

                while True:
                    cursor, keys = self._redis.scan(cursor, match=pattern, count=100)

                    for key in keys:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        parts = key_str.split(":")
                        if len(parts) >= 3:
                            # Could be service or endpoint budget
                            if len(parts) >= 4:  # retry_budget:service:endpoint:time
                                service_name = parts[1]
                                status = self.get_budget_status(service_name)
                                budgets.append(status)
                            else:  # retry_budget:service:time
                                service_name = parts[1]
                                status = self.get_budget_status(service_name)
                                if status not in budgets:
                                    budgets.append(status)

                    if cursor == 0:
                        break

            except Exception as e:
                logger.error(f"Redis error getting all budgets: {e}")
        else:
            for service_name in self._local_budgets:
                status = self.get_budget_status(service_name)
                budgets.append(status)

            for full_key in self._local_endpoint_budgets:
                status = self._get_budget_status_local(
                    full_key, self._default_limit, is_endpoint=True
                )
                budgets.append(status)

        return budgets

    def get_all_pools(self) -> list[dict[str, Any]]:
        """Get all budget pools.

        Returns:
            List of pool status dictionaries
        """
        pools = []

        for pool_id in self._budget_pools:
            status = self.get_pool_status(pool_id)
            if status:
                pools.append(status)

        return pools

    def get_analytics(self) -> BudgetAnalytics:
        """Get the analytics collector.

        Returns:
            BudgetAnalytics instance
        """
        return self._analytics

    def export_analytics_to_influxdb(
        self,
        influx_client: Any,
        bucket: str = "chiseai",
    ) -> None:
        """Export analytics to InfluxDB.

        Args:
            influx_client: InfluxDB client
            bucket: InfluxDB bucket name
        """
        self._analytics.export_to_influxdb(influx_client, bucket)

    def cleanup_old_budgets(self) -> int:
        """Clean up expired budget entries.

        Returns:
            Number of budgets cleaned up
        """
        if not self._redis:
            # Local budgets auto-expire via window check
            return 0

        try:
            # Redis handles expiration via TTL
            # This method is a placeholder for explicit cleanup if needed
            return 0
        except Exception as e:
            logger.error(f"Error cleaning up budgets: {e}")
            return 0
