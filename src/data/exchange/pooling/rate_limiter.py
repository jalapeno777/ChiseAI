"""Rate limiting logic for exchange APIs.

Implements token bucket and sliding window rate limiters
with pre-emptive limiting to avoid 429 responses.

For ST-NS-026: Connection Pooling for Exchange APIs
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        requests_per_minute: Maximum requests per minute
        burst_size: Maximum burst of requests
        retry_after_header: Header name for retry-after
    """

    requests_per_minute: int = 60
    burst_size: int = 5
    retry_after_header: str = "Retry-After"


@dataclass
class RateLimitState:
    """Current rate limiter state.

    Attributes:
        tokens: Current token bucket level
        last_update: Last token update timestamp
        wait_count: Number of times waited for token
        total_wait_ms: Total time spent waiting
    """

    tokens: float = 0.0
    last_update: float = field(default_factory=time.monotonic)
    wait_count: int = 0
    total_wait_ms: float = 0.0


class TokenBucketRateLimiter:
    """Token bucket rate limiter.

    Implements the token bucket algorithm for smooth rate limiting
    with burst capability. Pre-emptively limits to avoid 429s.

    Example:
        limiter = TokenBucketRateLimiter(requests_per_minute=120, burst_size=10)

        # Acquire token (waits if necessary)
        wait_time = await limiter.acquire()

        # Make request
        response = await http_client.get(url)
    """

    def __init__(
        self,
        requests_per_minute: int,
        burst_size: int | None = None,
        config: RateLimitConfig | None = None,
    ) -> None:
        """Initialize token bucket rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
            burst_size: Maximum burst (defaults to 10% of rate)
            config: Optional full configuration
        """
        if config:
            self.requests_per_minute = config.requests_per_minute
            self.burst_size = config.burst_size
        else:
            self.requests_per_minute = requests_per_minute
            self.burst_size = burst_size or max(1, requests_per_minute // 10)

        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

        # Metrics
        self.wait_count = 0
        self.total_wait_ms = 0.0
        self.total_acquired = 0

        # Calculate token refill rate (tokens per second)
        self.refill_rate = self.requests_per_minute / 60.0

    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Time waited in milliseconds
        """
        start_time = time.monotonic()

        async with self.lock:
            # Refill tokens based on elapsed time
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst_size, self.tokens + (elapsed * self.refill_rate)
            )
            self.last_update = now

            # Wait if insufficient tokens
            while self.tokens < tokens:
                self.wait_count += 1

                # Calculate wait time for next token
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.refill_rate

                # Release lock while waiting
                self.lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self.lock.acquire()

                # Refill after wait
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size, self.tokens + (elapsed * self.refill_rate)
                )
                self.last_update = now

            # Deduct tokens
            self.tokens -= tokens
            self.total_acquired += tokens

        elapsed_ms = (time.monotonic() - start_time) * 1000
        self.total_wait_ms += elapsed_ms
        return elapsed_ms

    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False otherwise
        """
        # Synchronous check (no waiting)
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.burst_size, self.tokens + (elapsed * self.refill_rate))
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            self.total_acquired += tokens
            return True
        return False

    def get_metrics(self) -> dict[str, Any]:
        """Get rate limiter metrics.

        Returns:
            Dictionary of metrics
        """
        return {
            "requests_per_minute": self.requests_per_minute,
            "burst_size": self.burst_size,
            "current_tokens": round(self.tokens, 2),
            "refill_rate": round(self.refill_rate, 4),
            "wait_count": self.wait_count,
            "total_wait_ms": round(self.total_wait_ms, 2),
            "total_acquired": self.total_acquired,
        }

    def reset(self) -> None:
        """Reset the rate limiter state."""
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self.wait_count = 0
        self.total_wait_ms = 0.0
        self.total_acquired = 0


class SlidingWindowRateLimiter:
    """Sliding window rate limiter.

    Tracks actual request timestamps in a sliding window
    for more precise rate limiting.

    Example:
        limiter = SlidingWindowRateLimiter(
            max_requests=120,
            window_seconds=60
        )

        # Check if request allowed
        if await limiter.allow_request():
            # Make request
            pass
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
    ) -> None:
        """Initialize sliding window rate limiter.

        Args:
            max_requests: Maximum requests in window
            window_seconds: Window size in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque[float] = deque()
        self.lock = asyncio.Lock()

        # Metrics
        self.rejected_count = 0
        self.total_requests = 0

    async def allow_request(self) -> bool:
        """Check if a request is allowed.

        Returns:
            True if request is allowed
        """
        async with self.lock:
            now = time.monotonic()

            # Remove old requests outside window
            cutoff = now - self.window_seconds
            while self.requests and self.requests[0] < cutoff:
                self.requests.popleft()

            # Check if under limit
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                self.total_requests += 1
                return True
            else:
                self.rejected_count += 1
                return False

    async def get_wait_time(self) -> float:
        """Get estimated wait time for next available slot.

        Returns:
            Estimated wait time in seconds
        """
        async with self.lock:
            if len(self.requests) < self.max_requests:
                return 0.0

            # Time until oldest request expires
            now = time.monotonic()
            oldest = self.requests[0]
            return max(0.0, (oldest + self.window_seconds) - now)

    def get_metrics(self) -> dict[str, Any]:
        """Get rate limiter metrics.

        Returns:
            Dictionary of metrics
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Count requests in current window
        current_requests = sum(1 for t in self.requests if t >= cutoff)

        return {
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "current_requests": current_requests,
            "rejected_count": self.rejected_count,
            "total_requests": self.total_requests,
            "utilization": (
                (current_requests / self.max_requests * 100)
                if self.max_requests > 0
                else 0
            ),
        }

    def reset(self) -> None:
        """Reset the rate limiter state."""
        self.requests.clear()
        self.rejected_count = 0
        self.total_requests = 0


class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts based on API responses.

    Monitors for rate limit responses (429) and automatically
    adjusts the rate limit down, then gradually increases it back.

    Example:
        limiter = AdaptiveRateLimiter(
            initial_rpm=120,
            min_rpm=30,
            max_rpm=120
        )

        wait_time = await limiter.acquire()
        try:
            response = await api_call()
        except RateLimitError:
            limiter.report_rate_limit()
    """

    def __init__(
        self,
        initial_rpm: int,
        min_rpm: int = 10,
        max_rpm: int = 120,
        backoff_factor: float = 0.8,
        recovery_factor: float = 1.05,
        recovery_interval: int = 60,
    ) -> None:
        """Initialize adaptive rate limiter.

        Args:
            initial_rpm: Starting requests per minute
            min_rpm: Minimum allowed RPM
            max_rpm: Maximum allowed RPM
            backoff_factor: Factor to reduce on 429 (0.8 = 20% reduction)
            recovery_factor: Factor to increase on success
            recovery_interval: Seconds between recovery attempts
        """
        self.min_rpm = min_rpm
        self.max_rpm = max_rpm
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.recovery_interval = recovery_interval

        self.current_rpm = initial_rpm
        self.last_rate_limit = 0.0
        self.last_recovery = time.monotonic()

        # Use token bucket as base
        self._limiter = TokenBucketRateLimiter(
            requests_per_minute=self.current_rpm,
            burst_size=max(1, self.current_rpm // 10),
        )

    async def acquire(self) -> float:
        """Acquire permission to make a request.

        Returns:
            Time waited in milliseconds
        """
        # Try recovery if enough time passed
        await self._try_recovery()

        return await self._limiter.acquire()

    async def _try_recovery(self) -> None:
        """Attempt to recover rate limit after cooldown."""
        now = time.monotonic()

        if now - self.last_recovery < self.recovery_interval:
            return

        if now - self.last_rate_limit < self.recovery_interval:
            return

        # Increase rate limit
        new_rpm = min(self.max_rpm, int(self.current_rpm * self.recovery_factor))
        if new_rpm > self.current_rpm:
            logger.info(f"Recovering rate limit: {self.current_rpm} -> {new_rpm} RPM")
            self.current_rpm = new_rpm
            self._limiter = TokenBucketRateLimiter(
                requests_per_minute=self.current_rpm,
                burst_size=max(1, self.current_rpm // 10),
            )

        self.last_recovery = now

    def report_rate_limit(self, retry_after: int | None = None) -> None:
        """Report a rate limit hit to reduce limits.

        Args:
            retry_after: Optional retry-after header value
        """
        self.last_rate_limit = time.monotonic()

        # Calculate new rate
        if retry_after:
            # Adjust based on server's suggestion
            new_rpm = max(self.min_rpm, int(60 / retry_after))
        else:
            new_rpm = max(self.min_rpm, int(self.current_rpm * self.backoff_factor))

        if new_rpm < self.current_rpm:
            logger.warning(
                f"Rate limit hit, reducing: {self.current_rpm} -> {new_rpm} RPM"
            )
            self.current_rpm = new_rpm
            self._limiter = TokenBucketRateLimiter(
                requests_per_minute=self.current_rpm,
                burst_size=max(1, self.current_rpm // 10),
            )

    def get_metrics(self) -> dict[str, Any]:
        """Get rate limiter metrics.

        Returns:
            Dictionary of metrics
        """
        base_metrics = self._limiter.get_metrics()
        base_metrics.update(
            {
                "current_rpm": self.current_rpm,
                "min_rpm": self.min_rpm,
                "max_rpm": self.max_rpm,
                "last_rate_limit": self.last_rate_limit,
                "adaptive_enabled": True,
            }
        )
        return base_metrics

    def reset(self) -> None:
        """Reset the rate limiter."""
        self._limiter.reset()


class CompositeRateLimiter:
    """Combines multiple rate limiters.

    Useful when an API has multiple limits (e.g., per-endpoint
    and global limits).

    Example:
        global_limiter = TokenBucketRateLimiter(requests_per_minute=120)
        endpoint_limiter = TokenBucketRateLimiter(requests_per_minute=60)

        limiter = CompositeRateLimiter([global_limiter, endpoint_limiter])
        wait_time = await limiter.acquire()
    """

    def __init__(self, limiters: list[TokenBucketRateLimiter]) -> None:
        """Initialize composite rate limiter.

        Args:
            limiters: List of rate limiters to combine
        """
        self.limiters = limiters

    async def acquire(self) -> float:
        """Acquire from all limiters.

        Returns:
            Total time waited in milliseconds
        """
        total_wait = 0.0
        for limiter in self.limiters:
            total_wait += await limiter.acquire()
        return total_wait

    def try_acquire(self) -> bool:
        """Try to acquire from all limiters.

        Returns:
            True if all limiters granted tokens
        """
        # First check all can acquire
        for limiter in self.limiters:
            if not limiter.try_acquire():
                # Release any acquired tokens
                return False
        return True

    def get_metrics(self) -> dict[str, Any]:
        """Get combined metrics.

        Returns:
            Dictionary with all limiter metrics
        """
        return {
            f"limiter_{i}": limiter.get_metrics()
            for i, limiter in enumerate(self.limiters)
        }

    def reset(self) -> None:
        """Reset all limiters."""
        for limiter in self.limiters:
            limiter.reset()
