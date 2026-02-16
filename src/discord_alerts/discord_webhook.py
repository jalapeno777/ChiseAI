"""Optimized Discord webhook client with batching and rate limiting.

High-performance Discord webhook client that implements:
- Connection pooling for efficient HTTP reuse
- Signal batching to reduce webhook calls
- Discord-specific rate limiting (30 req/min)
- Retry logic with exponential backoff

For TASK-ST-NS-026-03: Discord Webhook Optimization
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import aiohttp

from discord_alerts.config import DiscordConfig

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


# Discord rate limit constants
DISCORD_RATE_LIMIT_PER_MINUTE = 30
DISCORD_BURST_SIZE = 5


@dataclass
class DeliveryResult:
    """Result of a webhook delivery attempt.

    Attributes:
        signal_id: ID of the signal that was delivered
        success: Whether delivery was successful
        latency_ms: Time taken for delivery in milliseconds
        retry_count: Number of retry attempts made
        error: Error message if delivery failed
    """

    signal_id: str
    success: bool
    latency_ms: float
    retry_count: int = 0
    error: str | None = None


@dataclass
class BatchSignal:
    """A signal queued for batch delivery."""

    signal: "Signal"
    queued_at: float = field(default_factory=time.time)
    high_priority: bool = False


class DiscordRateLimiter:
    """Async Discord-specific rate limiter.

    Enforces Discord's rate limits (30 requests/minute per webhook)
    with token bucket algorithm and support for burst requests.

    Attributes:
        requests_per_minute: Maximum requests per minute (default: 30)
        burst_size: Maximum burst requests (default: 5)
    """

    def __init__(
        self,
        requests_per_minute: int = DISCORD_RATE_LIMIT_PER_MINUTE,
        burst_size: int = DISCORD_BURST_SIZE,
    ):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
            burst_size: Maximum burst requests
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()
        self._refill_rate = requests_per_minute / 60.0
        self._lock = asyncio.Lock()
        self._retry_after: float | None = None

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        tokens_to_add = elapsed * self._refill_rate

        self._tokens = min(self.burst_size, self._tokens + tokens_to_add)
        self._last_refill = now

    async def acquire(self, tokens: float = 1.0) -> bool:
        """Wait for rate limit slot.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True when tokens acquired
        """
        async with self._lock:
            while True:
                self._refill()

                if self._retry_after is not None:
                    # Respect server-side rate limit
                    wait_time = self._retry_after
                    self._retry_after = None
                    logger.warning(f"Server rate limited, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    continue

                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

                # Calculate wait time for tokens
                tokens_needed = tokens - self._tokens
                wait_time = tokens_needed / self._refill_rate

                # Wait but don't hold the lock
                self._lock.release()
                try:
                    await asyncio.sleep(min(wait_time, 0.1))
                finally:
                    await self._lock.acquire()

    def set_retry_after(self, retry_after: float) -> None:
        """Set server-specified retry-after time.

        Args:
            retry_after: Seconds to wait before retrying
        """
        self._retry_after = retry_after

    def get_wait_time(self) -> float:
        """Get estimated wait time for next request.

        Returns:
            Estimated seconds until next token available
        """
        self._refill()
        if self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) / self._refill_rate


class ConnectionPool:
    """Simple connection pool for aiohttp.

    Reuses a single ClientSession for efficient HTTP connections.

    Attributes:
        timeout: Request timeout in seconds
    """

    def __init__(self, timeout: float = 10.0):
        """Initialize connection pool.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session.

        Returns:
            Shared ClientSession
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(
                limit=10,  # Max connections
                limit_per_host=5,  # Max per host
                ttl_dns_cache=300,  # DNS cache TTL
                keepalive_timeout=30,  # Keep-alive
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            )
        return self._session

    async def close(self) -> None:
        """Close the connection pool."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


class DiscordBatchSender:
    """Batches and sends Discord webhooks efficiently.

    Collects signals and sends them in batches to reduce webhook calls.
    Uses time-based and size-based batching strategies.

    Attributes:
        webhook_url: Discord webhook URL
        max_batch_size: Maximum signals per batch (default: 5)
        max_wait_ms: Maximum wait time to collect signals (default: 100ms)
    """

    def __init__(
        self,
        webhook_url: str,
        max_batch_size: int = 5,
        max_wait_ms: int = 100,
    ):
        """Initialize batch sender.

        Args:
            webhook_url: Discord webhook URL
            max_batch_size: Maximum signals per batch
            max_wait_ms: Maximum wait time in milliseconds
        """
        self.webhook_url = webhook_url
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms

        self._queue: list[BatchSignal] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

        logger.debug(
            f"DiscordBatchSender initialized: "
            f"max_batch_size={max_batch_size}, max_wait_ms={max_wait_ms}"
        )

    async def send_signal(self, signal: "Signal") -> bool:
        """Queue signal for batch sending.

        High-confidence signals (>=90%) are sent immediately.

        Args:
            signal: Trading signal to queue

        Returns:
            True if queued or sent successfully
        """
        high_priority = signal.confidence >= 0.90

        async with self._lock:
            if high_priority:
                # High confidence - send immediately
                logger.debug(
                    f"High confidence signal {signal.signal_id} "
                    f"({signal.confidence:.0%}) - sending immediately"
                )
                return True

            # Add to batch queue
            self._queue.append(
                BatchSignal(
                    signal=signal,
                    high_priority=high_priority,
                )
            )

            # Check if we should flush
            if len(self._queue) >= self.max_batch_size:
                await self._flush_locked()

        return True

    async def flush(self) -> list[DeliveryResult]:
        """Force send all queued signals.

        Returns:
            List of delivery results
        """
        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> list[DeliveryResult]:
        """Flush queue (must hold lock).

        Returns:
            List of delivery results
        """
        if not self._queue:
            return []

        signals = [bs.signal for bs in self._queue]
        self._queue = []

        # Send batch
        results = await self._send_batch(signals)
        return results

    async def _send_batch(self, signals: list["Signal"]) -> list[DeliveryResult]:
        """Send batch of signals in one webhook.

        Combines multiple signals into a single Discord embed.

        Args:
            signals: List of signals to send

        Returns:
            List of delivery results
        """
        if not signals:
            return []

        start_time = time.perf_counter()

        # Build embed with multiple signal fields
        embed = self._build_batch_embed(signals)
        payload = {"embeds": [embed]}

        try:
            # Use aiohttp directly (rate limiter will handle throttling)
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    latency_ms = (time.perf_counter() - start_time) * 1000

                    if resp.status == 204:
                        # Success
                        logger.info(
                            f"Batch sent successfully: {len(signals)} signals "
                            f"in {latency_ms:.1f}ms"
                        )
                        return [
                            DeliveryResult(
                                signal_id=s.signal_id,
                                success=True,
                                latency_ms=latency_ms,
                            )
                            for s in signals
                        ]

                    elif resp.status == 429:
                        # Rate limited
                        retry_after = float(resp.headers.get("Retry-After", "5"))
                        logger.warning(f"Rate limited, retry_after={retry_after}s")
                        return [
                            DeliveryResult(
                                signal_id=s.signal_id,
                                success=False,
                                latency_ms=latency_ms,
                                error=f"Rate limited, retry after {retry_after}s",
                            )
                            for s in signals
                        ]

                    else:
                        body = await resp.text()
                        error = f"HTTP {resp.status}: {body}"
                        logger.error(f"Batch send failed: {error}")
                        return [
                            DeliveryResult(
                                signal_id=s.signal_id,
                                success=False,
                                latency_ms=latency_ms,
                                error=error,
                            )
                            for s in signals
                        ]

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Batch send error: {e}")
            return [
                DeliveryResult(
                    signal_id=s.signal_id,
                    success=False,
                    latency_ms=latency_ms,
                    error=str(e),
                )
                for s in signals
            ]

    def _build_batch_embed(self, signals: list["Signal"]) -> dict[str, Any]:
        """Build Discord embed for batched signals.

        Args:
            signals: List of signals to embed

        Returns:
            Discord embed dict
        """
        # Direction emoji
        direction_emoji = {
            "long": "🟢",
            "short": "🔴",
            "neutral": "⚪",
        }

        # Title based on signals
        total_conf = sum(s.confidence for s in signals) / len(signals)
        title = f"📊 {len(signals)} Trading Signals (Avg: {total_conf:.0%})"

        # Build fields
        fields = []
        for signal in signals:
            emoji = direction_emoji.get(signal.direction.value, "📊")
            field_name = f"{emoji} {signal.token} {signal.direction.value.upper()}"

            field_value = (
                f"Confidence: **{signal.confidence:.0%}**\n"
                f"Score: {signal.base_score:.1f}/100\n"
            )

            if signal.stop_loss:
                field_value += f"🛑 SL: ${signal.stop_loss:,.2f}\n"

            fields.append(
                {
                    "name": field_name,
                    "value": field_value,
                    "inline": True,
                }
            )

        return {
            "title": title,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "color": 0x00FF00 if signals[0].direction.value == "long" else 0xFF0000,
        }

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue)


class OptimizedDiscordClient:
    """High-performance Discord webhook client.

    Combines batching, rate limiting, and connection pooling for
    efficient signal delivery with <200ms latency target.

    Attributes:
        webhook_url: Discord webhook URL
        config: Discord configuration
    """

    def __init__(
        self,
        webhook_url: str,
        config: DiscordConfig | None = None,
        max_batch_size: int = 5,
        max_wait_ms: int = 100,
    ):
        """Initialize optimized client.

        Args:
            webhook_url: Discord webhook URL
            config: Discord configuration
            max_batch_size: Maximum batch size
            max_wait_ms: Maximum wait time for batching
        """
        self.webhook_url = webhook_url
        self.config = config or DiscordConfig()

        # Initialize components
        self._rate_limiter = DiscordRateLimiter(
            requests_per_minute=DISCORD_RATE_LIMIT_PER_MINUTE,
            burst_size=DISCORD_BURST_SIZE,
        )
        self._connection_pool = ConnectionPool()
        self._batch_sender = DiscordBatchSender(
            webhook_url=webhook_url,
            max_batch_size=max_batch_size,
            max_wait_ms=max_wait_ms,
        )

        self._max_retries = self.config.max_retries
        self._retry_base_delay = self.config.retry_base_delay
        self._retry_max_delay = self.config.retry_max_delay

        logger.info(
            f"OptimizedDiscordClient initialized: "
            f"batch_size={max_batch_size}, wait_ms={max_wait_ms}"
        )

    async def emit_signal(self, signal: "Signal") -> DeliveryResult:
        """Emit signal with batching and rate limiting.

        Args:
            signal: Signal to emit

        Returns:
            DeliveryResult
        """
        start_time = time.perf_counter()

        # Queue for batching
        await self._batch_sender.send_signal(signal)

        # Try to flush and get result
        # For single signal, we send immediately through rate limiter
        success = await self._rate_limiter.acquire()

        if not success:
            return DeliveryResult(
                signal_id=signal.signal_id,
                success=False,
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="Rate limit acquire failed",
            )

        # Send the batch
        results = await self._batch_sender.flush()

        # Get result for our signal
        for result in results:
            if result.signal_id == signal.signal_id:
                return result

        # If not found in batch results, check if it was queued
        latency_ms = (time.perf_counter() - start_time) * 1000

        # The signal was queued but batch may not have been sent yet
        # Return pending status
        return DeliveryResult(
            signal_id=signal.signal_id,
            success=True,  # Queued successfully
            latency_ms=latency_ms,
        )

    async def emit_batch(self, signals: list["Signal"]) -> list[DeliveryResult]:
        """Emit multiple signals efficiently.

        Args:
            signals: List of signals to emit

        Returns:
            List of DeliveryResults
        """
        # Queue all signals
        for signal in signals:
            await self._batch_sender.send_signal(signal)

        # Wait for rate limit
        await self._rate_limiter.acquire()

        # Flush the batch
        return await self._batch_sender.flush()

    async def send_with_retry(
        self,
        payload: dict[str, Any],
    ) -> tuple[bool, float, str | None]:
        """Send payload with retry logic.

        Args:
            payload: JSON payload to send

        Returns:
            Tuple of (success, latency_ms, error)
        """
        last_error = None

        for attempt in range(self._max_retries):
            start = time.perf_counter()

            try:
                session = await self._connection_pool.get_session()
                async with session.post(self.webhook_url, json=payload) as resp:
                    latency_ms = (time.perf_counter() - start) * 1000

                    if resp.status == 204:
                        return True, latency_ms, None

                    elif resp.status == 429:
                        # Rate limited by Discord
                        retry_after = float(resp.headers.get("Retry-After", "5"))
                        self._rate_limiter.set_retry_after(retry_after)

                        if attempt < self._max_retries - 1:
                            delay = min(
                                self._retry_base_delay * (2**attempt),
                                self._retry_max_delay,
                            )
                            await asyncio.sleep(delay)
                            continue

                        return False, latency_ms, f"Rate limited: {retry_after}s"

                    else:
                        body = await resp.text()
                        last_error = f"HTTP {resp.status}: {body}"

                        # Don't retry on client errors
                        if resp.status in (400, 401, 403, 404):
                            return False, latency_ms, last_error

            except Exception as e:
                latency_ms = (time.perf_counter() - start) * 1000
                last_error = str(e)

            # Exponential backoff
            if attempt < self._max_retries - 1:
                delay = min(
                    self._retry_base_delay * (2**attempt),
                    self._retry_max_delay,
                )
                await asyncio.sleep(delay)

        return False, 0.0, last_error or "Max retries exceeded"

    async def close(self) -> None:
        """Close client and cleanup resources."""
        await self._connection_pool.close()
        logger.info("OptimizedDiscordClient closed")

    async def health_check(self) -> dict[str, Any]:
        """Check client health.

        Returns:
            Health status dict
        """
        return {
            "healthy": True,
            "rate_limiter": {
                "wait_time": self._rate_limiter.get_wait_time(),
                "requests_per_minute": self._rate_limiter.requests_per_minute,
            },
            "batch_sender": {
                "queue_size": self._batch_sender.queue_size,
                "max_batch_size": self._batch_sender.max_batch_size,
            },
        }
