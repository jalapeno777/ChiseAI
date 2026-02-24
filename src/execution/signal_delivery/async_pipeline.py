"""Async signal delivery pipeline for low-latency transmission.

Provides async processing pipeline for delivering trading signals
with sub-second latency targets.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from execution.signal_delivery.cache import SignalMetadataCache
    from execution.signal_delivery.latency_monitor import LatencyMonitor

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DeliveryStatus(Enum):
    """Status of signal delivery."""

    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


@dataclass
class DeliveryConfig:
    """Configuration for signal delivery.

    Attributes:
        max_latency_ms: Maximum allowed latency in milliseconds
        retry_count: Number of retries on failure
        retry_delay_ms: Delay between retries in milliseconds
        batch_size: Maximum batch size for bulk delivery
        timeout_ms: Timeout for individual deliveries
        enable_caching: Whether to cache signal metadata
        enable_monitoring: Whether to track latency metrics
    """

    max_latency_ms: float = 1000.0  # 1 second target
    retry_count: int = 3
    retry_delay_ms: float = 100.0
    batch_size: int = 100
    timeout_ms: float = 5000.0
    enable_caching: bool = True
    enable_monitoring: bool = True

    @classmethod
    def default(cls) -> DeliveryConfig:
        """Get default configuration."""
        return cls()

    @classmethod
    def high_throughput(cls) -> DeliveryConfig:
        """Get high throughput configuration."""
        return cls(
            max_latency_ms=2000.0,
            batch_size=500,
            retry_count=2,
        )

    @classmethod
    def low_latency(cls) -> DeliveryConfig:
        """Get low latency configuration."""
        return cls(
            max_latency_ms=500.0,
            batch_size=50,
            retry_count=1,
        )


@dataclass
class DeliveryResult(Generic[T]):
    """Result of signal delivery attempt.

    Attributes:
        signal_id: Signal identifier
        status: Delivery status
        latency_ms: Delivery latency in milliseconds
        result: Delivery result payload
        error: Error message if failed
        retries: Number of retries attempted
        timestamp: Delivery timestamp
    """

    signal_id: str
    status: DeliveryStatus
    latency_ms: float = 0.0
    result: T | None = None
    error: str | None = None
    retries: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_success(self) -> bool:
        """Check if delivery was successful."""
        return self.status == DeliveryStatus.DELIVERED

    def is_slow(self, threshold_ms: float = 1000.0) -> bool:
        """Check if delivery exceeded latency threshold.

        Args:
            threshold_ms: Latency threshold in milliseconds

        Returns:
            True if delivery was slow
        """
        return self.latency_ms > threshold_ms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "is_success": self.is_success,
            "error": self.error,
            "retries": self.retries,
            "timestamp": self.timestamp.isoformat(),
        }


class AsyncSignalPipeline:
    """Async pipeline for signal delivery with low-latency guarantees.

    Provides async processing, batching, and retry logic for
    delivering trading signals to execution targets.

    Example:
        pipeline = AsyncSignalPipeline(redis_client)
        result = await pipeline.deliver(signal)
        if result.is_success and not result.is_slow():
            print(f"Delivered in {result.latency_ms}ms")
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        config: DeliveryConfig | None = None,
        metadata_cache: SignalMetadataCache | None = None,
        latency_monitor: LatencyMonitor | None = None,
    ):
        """Initialize signal delivery pipeline.

        Args:
            redis_client: Async Redis client for state management
            config: Delivery configuration
            metadata_cache: Optional signal metadata cache
            latency_monitor: Optional latency monitor
        """
        self.redis = redis_client
        self.config = config or DeliveryConfig.default()
        self.metadata_cache = metadata_cache
        self.latency_monitor = latency_monitor

        # Internal state
        self._pending_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._processing = False
        self._stats = {
            "total_delivered": 0,
            "total_failed": 0,
            "total_retries": 0,
            "total_latency_ms": 0.0,
        }

    async def deliver(
        self,
        signal: Any,
        target: str = "default",
    ) -> DeliveryResult:
        """Deliver a single signal.

        Args:
            signal: Signal to deliver
            target: Delivery target identifier

        Returns:
            DeliveryResult with delivery status
        """
        start_time = datetime.now(UTC)
        signal_id = getattr(signal, "signal_id", str(id(signal)))

        # Check cache first
        if self.metadata_cache and self.config.enable_caching:
            cached = await self.metadata_cache.get(signal_id)
            if cached and cached.delivered:
                # Already delivered, skip
                return DeliveryResult(
                    signal_id=signal_id,
                    status=DeliveryStatus.DELIVERED,
                    latency_ms=0.0,
                    result={"cached": True},
                )

        # Attempt delivery with retries
        last_error: str | None = None
        for attempt in range(self.config.retry_count + 1):
            try:
                result = await self._deliver_single(signal, target)

                latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

                # Cache metadata
                if self.metadata_cache and self.config.enable_caching:
                    await self.metadata_cache.set(
                        signal_id,
                        {
                            "delivered": True,
                            "latency_ms": latency_ms,
                            "target": target,
                        },
                    )

                # Record latency
                if self.latency_monitor and self.config.enable_monitoring:
                    from execution.signal_delivery.latency_monitor import LatencyMetric

                    self.latency_monitor.record(
                        LatencyMetric(
                            signal_id=signal_id,
                            stage="delivery",
                            latency_ms=latency_ms,
                        )
                    )

                # Update stats
                self._stats["total_delivered"] += 1
                self._stats["total_latency_ms"] += latency_ms

                return DeliveryResult(
                    signal_id=signal_id,
                    status=DeliveryStatus.DELIVERED,
                    latency_ms=latency_ms,
                    result=result,
                    retries=attempt,
                )

            except TimeoutError:
                last_error = "Delivery timeout"
                logger.warning(
                    f"Signal {signal_id} delivery timeout, attempt {attempt + 1}"
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Signal {signal_id} delivery failed: {e}, attempt {attempt + 1}"
                )

            # Retry delay
            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay_ms / 1000)
                self._stats["total_retries"] += 1

        # All retries failed
        self._stats["total_failed"] += 1

        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return DeliveryResult(
            signal_id=signal_id,
            status=DeliveryStatus.FAILED,
            latency_ms=latency_ms,
            error=last_error,
            retries=self.config.retry_count,
        )

    async def deliver_batch(
        self,
        signals: list[Any],
        target: str = "default",
    ) -> list[DeliveryResult]:
        """Deliver multiple signals in batch.

        Args:
            signals: List of signals to deliver
            target: Delivery target identifier

        Returns:
            List of DeliveryResult for each signal
        """
        # Process in batches for efficiency
        results: list[DeliveryResult] = []

        for i in range(0, len(signals), self.config.batch_size):
            batch = signals[i : i + self.config.batch_size]

            # Deliver batch concurrently
            tasks = [self.deliver(signal, target) for signal in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    signal_id = getattr(batch[j], "signal_id", str(id(batch[j])))
                    results.append(
                        DeliveryResult(
                            signal_id=signal_id,
                            status=DeliveryStatus.FAILED,
                            error=str(result),
                        )
                    )
                else:
                    results.append(result)

        return results

    async def _deliver_single(
        self,
        signal: Any,
        target: str,
    ) -> dict[str, Any]:
        """Internal method for single signal delivery.

        Args:
            signal: Signal to deliver
            target: Delivery target

        Returns:
            Delivery result payload

        Raises:
            asyncio.TimeoutError: If delivery times out
            Exception: If delivery fails
        """
        # Simulate delivery with timeout
        async with asyncio.timeout(self.config.timeout_ms / 1000):
            # In real implementation, this would call the actual delivery mechanism
            # (e.g., exchange API, message queue, etc.)

            # For now, simulate delivery latency
            await asyncio.sleep(0.01)  # 10ms simulated delivery

            return {
                "delivered": True,
                "target": target,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def get_stats(self) -> dict[str, Any]:
        """Get delivery statistics.

        Returns:
            Dictionary with delivery stats
        """
        avg_latency = (
            self._stats["total_latency_ms"] / self._stats["total_delivered"]
            if self._stats["total_delivered"] > 0
            else 0.0
        )

        return {
            "total_delivered": self._stats["total_delivered"],
            "total_failed": self._stats["total_failed"],
            "total_retries": self._stats["total_retries"],
            "avg_latency_ms": round(avg_latency, 2),
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check.

        Returns:
            Health check result
        """
        try:
            # Check Redis connectivity
            await self.redis.ping()

            stats = self.get_stats()

            # Determine health based on failure rate
            total = stats["total_delivered"] + stats["total_failed"]
            failure_rate = stats["total_failed"] / total if total > 0 else 0.0

            if failure_rate > 0.1:  # >10% failure rate
                status = "degraded"
            elif failure_rate > 0.3:  # >30% failure rate
                status = "unhealthy"
            else:
                status = "healthy"

            return {
                "status": status,
                "stats": stats,
                "config": {
                    "max_latency_ms": self.config.max_latency_ms,
                    "retry_count": self.config.retry_count,
                    "batch_size": self.config.batch_size,
                },
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
