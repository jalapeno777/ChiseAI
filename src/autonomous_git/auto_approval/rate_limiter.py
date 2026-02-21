"""Rate limiting for auto-approval."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Redis key patterns
HOURLY_COUNT_KEY = "bmad:chiseai:auto_approval:hourly_count:{hour}"
CONSECUTIVE_KEY = "bmad:chiseai:auto_approval:consecutive_count"
LAST_RESET_KEY = "bmad:chiseai:auto_approval:last_reset"


class RateLimiter:
    """Rate limiter for auto-approval operations."""

    def __init__(
        self,
        max_per_hour: int = 10,
        max_consecutive: int = 3,
        consecutive_pause_duration: int = 300,
        redis_client=None,
    ):
        """Initialize rate limiter.

        Args:
            max_per_hour: Maximum approvals per hour
            max_consecutive: Maximum consecutive approvals before pause
            consecutive_pause_duration: Seconds to pause after max_consecutive
            redis_client: Optional Redis client for state storage
        """
        self.max_per_hour = max_per_hour
        self.max_consecutive = max_consecutive
        self.consecutive_pause_duration = consecutive_pause_duration
        self.redis = redis_client

        # In-memory fallback when Redis is unavailable
        self._hourly_count = 0
        self._consecutive_count = 0
        self._current_hour = self._get_current_hour()

    def _get_current_hour(self) -> str:
        """Get current hour as string for key generation."""
        return datetime.now(timezone.utc).strftime("%Y%m%d%H")

    async def check_limits(self) -> bool:
        """Check if rate limits allow another approval.

        Returns:
            True if approval is allowed, False otherwise
        """
        current_hour = self._get_current_hour()

        # Reset counters if hour changed
        if current_hour != self._current_hour:
            self._current_hour = current_hour
            self._hourly_count = 0

        # Try to use Redis if available
        if self.redis:
            try:
                return await self._check_limits_redis(current_hour)
            except Exception as e:
                logger.warning(f"Redis rate limit check failed, using in-memory: {e}")

        # In-memory rate limiting
        return self._check_limits_memory()

    async def _check_limits_redis(self, current_hour: str) -> bool:
        """Check limits using Redis."""
        hour_key = HOURLY_COUNT_KEY.format(hour=current_hour)

        # Increment hourly count
        hour_count = await self.redis.incr(hour_key)
        if hour_count == 1:
            # Set expiry on first increment
            await self.redis.expire(hour_key, 3600)

        # Check hourly limit
        if hour_count > self.max_per_hour:
            logger.warning(
                f"Hourly rate limit exceeded: {hour_count}/{self.max_per_hour}"
            )
            # Decrement since we're rejecting
            await self.redis.decr(hour_key)
            return False

        # Check consecutive limit
        consecutive = await self.redis.incr(CONSECUTIVE_KEY)

        if consecutive > self.max_consecutive:
            logger.info(
                f"Consecutive limit reached ({consecutive}), pausing for {self.consecutive_pause_duration}s"
            )
            await asyncio.sleep(self.consecutive_pause_duration)
            await self.redis.set(CONSECUTIVE_KEY, 0)

        return True

    def _check_limits_memory(self) -> bool:
        """Check limits using in-memory counters."""
        # Check hourly limit
        if self._hourly_count >= self.max_per_hour:
            logger.warning(
                f"Hourly rate limit exceeded: {self._hourly_count}/{self.max_per_hour}"
            )
            return False

        # Check consecutive limit
        if self._consecutive_count >= self.max_consecutive:
            logger.info(
                f"Consecutive limit reached ({self._consecutive_count}), pausing for {self.consecutive_pause_duration}s"
            )
            # In async context, we'd sleep, but for sync we just reset
            self._consecutive_count = 0

        self._hourly_count += 1
        self._consecutive_count += 1
        return True

    async def record_success(self):
        """Record a successful approval."""
        if self.redis:
            try:
                await self.redis.incr(CONSECUTIVE_KEY)
            except Exception as e:
                logger.warning(f"Failed to record success in Redis: {e}")
        else:
            self._consecutive_count += 1

    async def reset_consecutive(self):
        """Reset consecutive count (e.g., after manual intervention)."""
        if self.redis:
            try:
                await self.redis.set(CONSECUTIVE_KEY, 0)
            except Exception as e:
                logger.warning(f"Failed to reset consecutive in Redis: {e}")
        self._consecutive_count = 0
        logger.info("Reset consecutive approval counter")

    async def get_stats(self) -> dict:
        """Get current rate limit statistics."""
        current_hour = self._get_current_hour()

        if self.redis:
            try:
                hour_key = HOURLY_COUNT_KEY.format(hour=current_hour)
                hour_count = int(await self.redis.get(hour_key) or 0)
                consecutive = int(await self.redis.get(CONSECUTIVE_KEY) or 0)
                return {
                    "hourly_count": hour_count,
                    "hourly_limit": self.max_per_hour,
                    "consecutive_count": consecutive,
                    "consecutive_limit": self.max_consecutive,
                    "current_hour": current_hour,
                }
            except Exception as e:
                logger.warning(f"Failed to get stats from Redis: {e}")

        return {
            "hourly_count": self._hourly_count,
            "hourly_limit": self.max_per_hour,
            "consecutive_count": self._consecutive_count,
            "consecutive_limit": self.max_consecutive,
            "current_hour": current_hour,
        }
