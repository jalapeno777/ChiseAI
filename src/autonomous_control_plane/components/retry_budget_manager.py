"""Retry budget management with Redis backing.

Provides per-service retry budget tracking and enforcement using
Redis for distributed state management.

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis

from src.autonomous_control_plane.models.retry_policy import RetryBudget

logger = logging.getLogger(__name__)


class RetryBudgetManager:
    """Manages per-service retry budgets with Redis backing.

    Tracks retry attempts per service with minute-bucketed accounting.
    Uses Redis for distributed state in multi-instance deployments.

    Redis Key Pattern:
        retry_budget:{service_name}:{YYYY-MM-DD-HH-MM}

    Example:
        manager = RetryBudgetManager(redis_client)

        # Check and consume budget
        if manager.check_budget("redis_service", limit=100):
            # Proceed with retry
            pass
        else:
            # Budget exceeded
            raise BudgetExceededError()
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        default_limit: int = 100,
        ttl_seconds: int = 120,
    ):
        """Initialize budget manager.

        Args:
            redis_client: Redis client for distributed state
            default_limit: Default retry limit per minute
            ttl_seconds: TTL for Redis keys (2x window for safety)
        """
        self._redis = redis_client
        self._default_limit = default_limit
        self._ttl_seconds = ttl_seconds
        self._local_budgets: dict[str, RetryBudget] = {}

    def _get_budget_key(self, service_name: str, dt: datetime | None = None) -> str:
        """Generate Redis key for service budget.

        Args:
            service_name: Service identifier
            dt: Datetime for key (default: now)

        Returns:
            Redis key string
        """
        if dt is None:
            dt = datetime.utcnow()
        time_bucket = dt.strftime("%Y-%m-%d-%H-%M")
        return f"retry_budget:{service_name}:{time_bucket}"

    def _get_current_window(self) -> datetime:
        """Get current minute window."""
        return datetime.utcnow().replace(second=0, microsecond=0)

    def check_and_consume(
        self,
        service_name: str,
        limit: int | None = None,
    ) -> tuple[bool, int]:
        """Check budget and consume if available.

        Args:
            service_name: Service to check
            limit: Budget limit (uses default if None)

        Returns:
            Tuple of (allowed: bool, remaining: int)
        """
        limit = limit or self._default_limit

        if self._redis:
            return self._check_and_consume_redis(service_name, limit)
        else:
            return self._check_and_consume_local(service_name, limit)

    def _check_and_consume_redis(
        self,
        service_name: str,
        limit: int,
    ) -> tuple[bool, int]:
        """Check and consume budget using Redis atomic operations."""
        key = self._get_budget_key(service_name)

        try:
            # Use Redis INCR for atomic increment
            # Returns current value after increment
            current = self._redis.incr(key)

            # Set TTL on first increment
            if current == 1:
                self._redis.expire(key, self._ttl_seconds)

            allowed = current <= limit
            remaining = max(0, limit - current)

            if not allowed:
                logger.warning(
                    f"Retry budget exceeded for {service_name}: {current}/{limit}"
                )

            return allowed, remaining

        except Exception as e:
            logger.error(f"Redis error checking budget for {service_name}: {e}")
            # Fail open if Redis unavailable (don't block retries)
            return True, limit

    def _check_and_consume_local(
        self,
        service_name: str,
        limit: int,
    ) -> tuple[bool, int]:
        """Check and consume budget using local tracking."""
        now = self._get_current_window()

        # Get or create budget for service
        if service_name not in self._local_budgets:
            self._local_budgets[service_name] = RetryBudget(
                service_name=service_name,
                limit=limit,
                window_start=now,
            )

        budget = self._local_budgets[service_name]

        # Reset if window changed
        if budget.window_start < now:
            budget = RetryBudget(
                service_name=service_name,
                limit=limit,
                window_start=now,
            )
            self._local_budgets[service_name] = budget

        # Check and consume
        allowed = budget.record_attempt()
        remaining = max(0, limit - budget.current_count)

        if not allowed:
            logger.warning(
                f"Retry budget exceeded for {service_name}: "
                f"{budget.current_count}/{limit}"
            )

        return allowed, remaining

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

    def _get_budget_status_redis(
        self,
        service_name: str,
        limit: int,
    ) -> dict[str, Any]:
        """Get budget status from Redis."""
        key = self._get_budget_key(service_name)

        try:
            current = int(self._redis.get(key) or 0)
            ttl = self._redis.ttl(key)

            return {
                "service_name": service_name,
                "current_count": current,
                "limit": limit,
                "remaining": max(0, limit - current),
                "is_exceeded": current >= limit,
                "window_ttl_seconds": ttl if ttl > 0 else self._ttl_seconds,
            }
        except Exception as e:
            logger.error(f"Redis error getting budget for {service_name}: {e}")
            return {
                "service_name": service_name,
                "current_count": 0,
                "limit": limit,
                "remaining": limit,
                "is_exceeded": False,
                "error": str(e),
            }

    def _get_budget_status_local(
        self,
        service_name: str,
        limit: int,
    ) -> dict[str, Any]:
        """Get budget status from local tracking."""
        now = self._get_current_window()

        if service_name in self._local_budgets:
            budget = self._local_budgets[service_name]
            if budget.window_start == now:
                return {
                    "service_name": service_name,
                    "current_count": budget.current_count,
                    "limit": limit,
                    "remaining": max(0, limit - budget.current_count),
                    "is_exceeded": budget.is_exceeded,
                    "window_start": budget.window_start.isoformat(),
                }

        # No budget recorded for current window
        return {
            "service_name": service_name,
            "current_count": 0,
            "limit": limit,
            "remaining": limit,
            "is_exceeded": False,
        }

    def reset_budget(self, service_name: str) -> None:
        """Reset budget for a service.

        Args:
            service_name: Service to reset
        """
        if self._redis:
            key = self._get_budget_key(service_name)
            try:
                self._redis.delete(key)
                logger.info(f"Reset retry budget for {service_name}")
            except Exception as e:
                logger.error(f"Redis error resetting budget for {service_name}: {e}")
        else:
            if service_name in self._local_budgets:
                del self._local_budgets[service_name]
            logger.info(f"Reset retry budget for {service_name}")

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
                        if len(parts) >= 2:
                            service_name = parts[1]
                            status = self.get_budget_status(service_name)
                            budgets.append(status)

                    if cursor == 0:
                        break

            except Exception as e:
                logger.error(f"Redis error getting all budgets: {e}")
        else:
            for service_name in self._local_budgets:
                status = self.get_budget_status(service_name)
                budgets.append(status)

        return budgets

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
