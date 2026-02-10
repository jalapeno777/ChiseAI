"""Rate limiter for Discord alerts.

Implements token bucket algorithm for per-channel rate limiting
with configurable limits and retry-after support.

For ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting.

    Attributes:
        tokens: Current number of available tokens
        last_refill: Timestamp of last token refill
        max_tokens: Maximum tokens in bucket
        refill_rate: Tokens added per second
    """

    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)
    max_tokens: float = 10.0
    refill_rate: float = 10.0 / 60.0  # 10 per minute default

    def refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate

        self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
        self.last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens from bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient
        """
        self.refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def time_until_available(self, tokens: float = 1.0) -> float:
        """Calculate time until enough tokens are available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds until tokens available (0 if available now)
        """
        self.refill()

        if self.tokens >= tokens:
            return 0.0

        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate


class RateLimiter:
    """Rate limiter for Discord alerts using token bucket algorithm.

    Supports per-channel rate limiting with configurable limits.
    Thread-safe for concurrent access.

    Attributes:
        max_per_minute: Maximum alerts per channel per minute
        block_when_limited: Whether to block or fail when rate limited
    """

    DEFAULT_MAX_PER_MINUTE = 10

    def __init__(
        self,
        max_per_minute: int = DEFAULT_MAX_PER_MINUTE,
        block_when_limited: bool = False,
    ):
        """Initialize rate limiter.

        Args:
            max_per_minute: Maximum alerts per channel per minute
            block_when_limited: Whether to block until available
        """
        self.max_per_minute = max_per_minute
        self.block_when_limited = block_when_limited

        # Per-channel buckets
        self._buckets: dict[str, RateLimitBucket] = {}
        self._lock = threading.RLock()

        logger.debug(f"RateLimiter initialized: {max_per_minute}/min per channel")

    def _get_bucket(self, channel: str) -> RateLimitBucket:
        """Get or create bucket for channel.

        Args:
            channel: Channel identifier

        Returns:
            RateLimitBucket for channel
        """
        with self._lock:
            if channel not in self._buckets:
                self._buckets[channel] = RateLimitBucket(
                    max_tokens=float(self.max_per_minute),
                    refill_rate=self.max_per_minute / 60.0,
                    tokens=float(self.max_per_minute),  # Start full
                )
            return self._buckets[channel]

    def check_limit(self, channel: str) -> dict[str, Any]:
        """Check current rate limit status for channel.

        Args:
            channel: Channel identifier

        Returns:
            Dictionary with limit status
        """
        bucket = self._get_bucket(channel)
        bucket.refill()

        return {
            "allowed": bucket.tokens >= 1.0,
            "remaining": int(bucket.tokens),
            "limit": self.max_per_minute,
            "reset_after": int(
                (self.max_per_minute - bucket.tokens) / bucket.refill_rate
            ),
        }

    def acquire(
        self,
        channel: str,
        tokens: float = 1.0,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Acquire rate limit token for channel.

        Args:
            channel: Channel identifier
            tokens: Number of tokens to acquire
            timeout: Max time to wait if blocking (None = no timeout)

        Returns:
            Dictionary with result:
                - success: Whether acquisition succeeded
                - retry_after: Seconds to wait before retry (if rate limited)
                - remaining: Remaining tokens after acquisition
        """
        bucket = self._get_bucket(channel)

        start_time = time.time()

        while True:
            with self._lock:
                if bucket.consume(tokens):
                    return {
                        "success": True,
                        "retry_after": 0,
                        "remaining": int(bucket.tokens),
                    }

                # Calculate retry after
                retry_after = bucket.time_until_available(tokens)

            # Not enough tokens
            if not self.block_when_limited:
                return {
                    "success": False,
                    "retry_after": retry_after,
                    "remaining": 0,
                }

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return {
                        "success": False,
                        "retry_after": retry_after,
                        "remaining": 0,
                        "error": "Timeout waiting for rate limit",
                    }

            # Wait and retry
            wait_time = min(retry_after, 0.1)  # Max 100ms between checks
            time.sleep(wait_time)

    def try_acquire(self, channel: str, tokens: float = 1.0) -> bool:
        """Try to acquire token without blocking.

        Args:
            channel: Channel identifier
            tokens: Number of tokens to acquire

        Returns:
            True if acquired, False if rate limited
        """
        result = self.acquire(channel, tokens, timeout=0)
        return result["success"]

    def get_retry_after(self, channel: str) -> float:
        """Get seconds until next token available.

        Args:
            channel: Channel identifier

        Returns:
            Seconds until token available (0 if available now)
        """
        bucket = self._get_bucket(channel)
        return bucket.time_until_available(1.0)

    def reset_channel(self, channel: str) -> None:
        """Reset rate limit for a channel.

        Args:
            channel: Channel identifier
        """
        with self._lock:
            if channel in self._buckets:
                del self._buckets[channel]
                logger.debug(f"Reset rate limit for channel: {channel}")

    def reset_all(self) -> None:
        """Reset all rate limits."""
        with self._lock:
            self._buckets.clear()
            logger.debug("Reset all rate limits")

    def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            stats = {
                "max_per_minute": self.max_per_minute,
                "block_when_limited": self.block_when_limited,
                "channels_tracked": len(self._buckets),
                "channel_stats": {},
            }

            for channel, bucket in self._buckets.items():
                bucket.refill()
                stats["channel_stats"][channel] = {
                    "remaining": int(bucket.tokens),
                    "max": self.max_per_minute,
                    "utilization": (
                        (self.max_per_minute - bucket.tokens) / self.max_per_minute
                        if self.max_per_minute > 0
                        else 0
                    ),
                }

            return stats
