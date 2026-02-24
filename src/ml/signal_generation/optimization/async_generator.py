"""Async signal generation for low-latency signal creation.

Provides async signal generation with optimized processing
to meet sub-second generation targets.
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

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GenerationStatus(Enum):
    """Status of signal generation."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class GenerationConfig:
    """Configuration for signal generation.

    Attributes:
        max_latency_ms: Maximum allowed generation latency
        batch_size: Batch size for bulk generation
        parallel_workers: Number of parallel workers
        cache_enabled: Whether to cache intermediate results
        prefetch_count: Number of items to prefetch
    """

    max_latency_ms: float = 500.0  # Sub-second target
    batch_size: int = 50
    parallel_workers: int = 4
    cache_enabled: bool = True
    prefetch_count: int = 10

    @classmethod
    def default(cls) -> "GenerationConfig":
        """Get default configuration."""
        return cls()

    @classmethod
    def high_throughput(cls) -> "GenerationConfig":
        """Get high throughput configuration."""
        return cls(
            max_latency_ms=1000.0,
            batch_size=100,
            parallel_workers=8,
        )

    @classmethod
    def low_latency(cls) -> "GenerationConfig":
        """Get low latency configuration."""
        return cls(
            max_latency_ms=250.0,
            batch_size=25,
            parallel_workers=2,
        )


@dataclass
class GenerationResult(Generic[T]):
    """Result of signal generation.

    Attributes:
        signal_id: Generated signal identifier
        status: Generation status
        latency_ms: Generation latency in milliseconds
        signal: Generated signal payload
        error: Error message if failed
        timestamp: Generation timestamp
    """

    signal_id: str
    status: GenerationStatus
    latency_ms: float = 0.0
    signal: T | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_success(self) -> bool:
        """Check if generation was successful."""
        return self.status == GenerationStatus.COMPLETED

    @property
    def is_slow(self, threshold_ms: float = 500.0) -> bool:
        """Check if generation was slow.

        Args:
            threshold_ms: Latency threshold

        Returns:
            True if generation was slow
        """
        return self.latency_ms > threshold_ms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_id": self.signal_id,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "is_success": self.is_success,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class AsyncSignalGenerator:
    """Async signal generator with optimized processing.

    Provides async signal generation with parallel processing,
    caching, and latency tracking.

    Example:
        generator = AsyncSignalGenerator(redis_client)
        result = await generator.generate(market_data)
        if result.is_success:
            print(f"Generated in {result.latency_ms}ms")
    """

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        config: GenerationConfig | None = None,
    ):
        """Initialize async signal generator.

        Args:
            redis_client: Optional Redis client for caching
            config: Generation configuration
        """
        self.redis = redis_client
        self.config = config or GenerationConfig.default()

        # Internal state
        self._stats = {
            "total_generated": 0,
            "total_failed": 0,
            "total_latency_ms": 0.0,
            "cache_hits": 0,
        }

        # Worker pool
        self._workers: list[asyncio.Task] = []
        self._queue: asyncio.Queue[Any] = asyncio.Queue()

    async def generate(
        self,
        data: Any,
        signal_id: str | None = None,
    ) -> GenerationResult:
        """Generate a signal from input data.

        Args:
            data: Input data for signal generation
            signal_id: Optional signal identifier

        Returns:
            GenerationResult with generated signal
        """
        start_time = datetime.now(UTC)
        signal_id = signal_id or f"sig-{datetime.now(UTC).timestamp()}"

        try:
            # Check cache first
            if self.redis and self.config.cache_enabled:
                cached = await self._check_cache(signal_id)
                if cached:
                    self._stats["cache_hits"] += 1
                    return GenerationResult(
                        signal_id=signal_id,
                        status=GenerationStatus.COMPLETED,
                        latency_ms=0.0,
                        signal=cached,
                    )

            # Generate signal
            signal = await self._generate_internal(data)

            latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            # Cache result
            if self.redis and self.config.cache_enabled:
                await self._cache_result(signal_id, signal)

            # Update stats
            self._stats["total_generated"] += 1
            self._stats["total_latency_ms"] += latency_ms

            return GenerationResult(
                signal_id=signal_id,
                status=GenerationStatus.COMPLETED,
                latency_ms=latency_ms,
                signal=signal,
            )

        except asyncio.TimeoutError:
            self._stats["total_failed"] += 1
            latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return GenerationResult(
                signal_id=signal_id,
                status=GenerationStatus.TIMEOUT,
                latency_ms=latency_ms,
                error="Generation timeout",
            )

        except Exception as e:
            self._stats["total_failed"] += 1
            latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            logger.error(f"Signal generation failed: {e}")
            return GenerationResult(
                signal_id=signal_id,
                status=GenerationStatus.FAILED,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def generate_batch(
        self,
        data_list: list[Any],
        signal_ids: list[str] | None = None,
    ) -> list[GenerationResult]:
        """Generate multiple signals in batch.

        Args:
            data_list: List of input data
            signal_ids: Optional list of signal identifiers

        Returns:
            List of GenerationResult for each signal
        """
        if signal_ids is None:
            signal_ids = [None] * len(data_list)

        # Generate in parallel batches
        results: list[GenerationResult] = []

        for i in range(0, len(data_list), self.config.batch_size):
            batch_data = data_list[i : i + self.config.batch_size]
            batch_ids = signal_ids[i : i + self.config.batch_size]

            # Process batch concurrently
            tasks = [
                self.generate(data, sig_id)
                for data, sig_id in zip(batch_data, batch_ids)
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    results.append(
                        GenerationResult(
                            signal_id=batch_ids[j] or f"batch-{i + j}",
                            status=GenerationStatus.FAILED,
                            error=str(result),
                        )
                    )
                else:
                    results.append(result)

        return results

    async def _generate_internal(self, data: Any) -> dict[str, Any]:
        """Internal signal generation logic.

        Args:
            data: Input data

        Returns:
            Generated signal dictionary
        """
        async with asyncio.timeout(self.config.max_latency_ms / 1000):
            # Simulate signal generation
            # In real implementation, this would call ML models, etc.
            await asyncio.sleep(0.05)  # 50ms simulated generation

            return {
                "signal_id": f"sig-{datetime.now(UTC).timestamp()}",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": data if isinstance(data, dict) else {"value": str(data)},
            }

    async def _check_cache(self, signal_id: str) -> dict[str, Any] | None:
        """Check cache for existing signal.

        Args:
            signal_id: Signal identifier

        Returns:
            Cached signal or None
        """
        if not self.redis:
            return None

        try:
            import json

            cached = await self.redis.get(f"chiseai:signal:gen:{signal_id}")
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache check error: {e}")

        return None

    async def _cache_result(
        self,
        signal_id: str,
        signal: dict[str, Any],
    ) -> None:
        """Cache generated signal.

        Args:
            signal_id: Signal identifier
            signal: Signal to cache
        """
        if not self.redis:
            return

        try:
            import json

            await self.redis.setex(
                f"chiseai:signal:gen:{signal_id}",
                3600,  # 1 hour TTL
                json.dumps(signal),
            )
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get generation statistics.

        Returns:
            Dictionary with stats
        """
        avg_latency = (
            self._stats["total_latency_ms"] / self._stats["total_generated"]
            if self._stats["total_generated"] > 0
            else 0.0
        )

        return {
            "total_generated": self._stats["total_generated"],
            "total_failed": self._stats["total_failed"],
            "cache_hits": self._stats["cache_hits"],
            "avg_latency_ms": round(avg_latency, 2),
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check.

        Returns:
            Health check result
        """
        stats = self.get_stats()
        total = stats["total_generated"] + stats["total_failed"]
        failure_rate = stats["total_failed"] / total if total > 0 else 0.0

        if failure_rate > 0.1:
            status = "degraded"
        elif failure_rate > 0.3:
            status = "unhealthy"
        else:
            status = "healthy"

        return {
            "status": status,
            "stats": stats,
            "config": {
                "max_latency_ms": self.config.max_latency_ms,
                "batch_size": self.config.batch_size,
                "parallel_workers": self.config.parallel_workers,
            },
        }
