"""Async signal processing pipeline with concurrency control.

Provides async signal processing capabilities to handle signal generation,
validation, and delivery concurrently. Reduces end-to-end latency by
processing multiple signals in parallel.

Key Features:
- Async signal processing (non-blocking)
- Concurrent signal handling (10+ parallel)
- Priority queue for high-confidence signals
- Graceful error handling and retries
- Metrics collection (latency, throughput)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.dedup import SignalDeduper
    from signal_generation.models import Signal
    from signal_generation.signal_emitter import SignalEmitter

# TTL for stored signals (7 days)
SIGNAL_STORAGE_TTL_SECONDS = 7 * 24 * 60 * 60  # 604800

# Redis key patterns for signal storage
SIGNAL_KEY_PATTERN = "paper:signal:{timestamp}:{token}:{signal_id}"
PROCESSED_SIGNALS_KEY = "paper:signals:processed"
SIGNAL_SCAN_PREFIX = "paper:signal:*"

logger = logging.getLogger(__name__)


class ProcessingStage(Enum):
    """Processing stages for a signal."""

    DEDUP = "dedup"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"
    STORAGE = "storage"
    DELIVERY = "delivery"
    LOGGING = "logging"
    COMPLETED = "completed"
    FAILED = "failed"


class SignalPriority(Enum):
    """Priority levels for signal processing."""

    HIGH = 0  # Confidence >= 90%
    MEDIUM = 1  # Confidence >= 75%
    LOW = 2  # Confidence < 75%


@dataclass
class ProcessingMetrics:
    """Metrics for signal processing.

    Attributes:
        signal_id: Unique signal identifier
        stage_latencies: Latency per processing stage (ms)
        total_latency_ms: Total processing time (ms)
        stage_errors: Errors per stage
        retry_count: Number of retries performed
        processed_at: Processing completion timestamp
    """

    signal_id: str
    stage_latencies: dict[str, float] = field(default_factory=dict)
    total_latency_ms: float = 0.0
    stage_errors: dict[str, str] = field(default_factory=dict)
    retry_count: int = 0
    processed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "signal_id": self.signal_id,
            "stage_latencies": self.stage_latencies,
            "total_latency_ms": round(self.total_latency_ms, 3),
            "stage_errors": self.stage_errors,
            "retry_count": self.retry_count,
            "processed_at": (
                self.processed_at.isoformat() if self.processed_at else None
            ),
        }


@dataclass
class SignalResult:
    """Result of signal processing.

    Attributes:
        signal: The processed signal
        success: Whether processing was successful
        stage: Final processing stage reached
        error: Error message if failed
        metrics: Processing metrics
        delivery_results: Results from delivery attempts
    """

    signal: Signal | None
    success: bool
    stage: ProcessingStage
    error: str | None = None
    metrics: ProcessingMetrics | None = None
    delivery_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "signal_id": self.signal.signal_id if self.signal else None,
            "success": self.success,
            "stage": self.stage.value,
            "error": self.error,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "delivery_results": self.delivery_results,
        }


@dataclass
class ValidationResult:
    """Result of signal validation.

    Attributes:
        valid: Whether signal is valid
        errors: List of validation errors
        warnings: List of validation warnings
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class EnrichedSignal:
    """Signal with additional context.

    Attributes:
        signal: Original signal
        current_price: Current market price
        orderbook_depth: Orderbook depth data
        risk_params: Risk parameters
        market_context: Additional market context
    """

    signal: Signal
    current_price: float | None = None
    orderbook_depth: dict[str, Any] | None = None
    risk_params: dict[str, Any] | None = None
    market_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal": self.signal.to_dict() if self.signal else None,
            "current_price": self.current_price,
            "orderbook_depth": self.orderbook_depth,
            "risk_params": self.risk_params,
            "market_context": self.market_context,
        }


@dataclass
class DeliveryResult:
    """Result of signal delivery.

    Attributes:
        success: Whether delivery was successful
        channel: Delivery channel (discord, dashboard, etc.)
        error: Error message if failed
        latency_ms: Delivery latency
    """

    success: bool
    channel: str
    error: str | None = None
    latency_ms: float = 0.0


class AsyncSignalProcessor:
    """Async signal processing with concurrency control.

    Processes signals asynchronously through validation, enrichment,
    storage, and delivery stages. Uses semaphores to limit concurrent
    operations and maintains priority ordering for high-confidence signals.

    Attributes:
        max_concurrent: Maximum number of concurrent signal processes
        max_retries: Maximum retry attempts for failed operations
        retry_delay: Delay between retries (seconds)
        emitters: List of signal emitters for delivery
    """

    # Stage latency targets (ms)
    TARGET_VALIDATION_MS = 50
    TARGET_ENRICHMENT_MS = 100
    TARGET_STORAGE_MS = 30
    TARGET_DELIVERY_MS = 200
    TARGET_LOGGING_MS = 10
    TARGET_TOTAL_MS = 500  # Total pipeline target

    def __init__(
        self,
        max_concurrent: int = 10,
        max_retries: int = 3,
        retry_delay: float = 0.1,
        emitters: list[SignalEmitter] | None = None,
        deduper: SignalDeduper | None = None,
        actionable_threshold: float = 0.75,
        redis_client: Any | None = None,
    ):
        """Initialize async signal processor.

        Args:
            max_concurrent: Maximum concurrent signal processes
            max_retries: Maximum retry attempts for failed operations
            retry_delay: Delay between retries (seconds)
            emitters: List of signal emitters for delivery
            deduper: Signal deduplicator for duplicate detection
            actionable_threshold: Minimum confidence for actionable signals (default 0.75)
            redis_client: Optional Redis client for durable signal storage.
                          If None, one is created lazily from redis_config.
        """
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.emitters = emitters or []
        self._deduper = deduper
        self._actionable_threshold = actionable_threshold
        self._redis_client: Any | None = redis_client
        self._redis_client_initialized = redis_client is not None

        # Concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Priority queue for high-confidence signals
        self._priority_queue: asyncio.PriorityQueue[tuple[int, Signal]] = (
            asyncio.PriorityQueue()
        )

        # Processing statistics
        self._stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "total_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
        }

        logger.info(
            f"AsyncSignalProcessor initialized: "
            f"max_concurrent={max_concurrent}, max_retries={max_retries}"
        )

    async def _get_redis_client(self) -> Any | None:
        """Lazily initialize and return the Redis client.

        Returns:
            Redis client instance, or None if Redis is unavailable.
        """
        if self._redis_client_initialized:
            return self._redis_client

        try:
            from execution.paper.redis_config import get_redis_client

            self._redis_client = get_redis_client(decode_responses=True)
            self._redis_client_initialized = True
            logger.info("Redis client initialized for signal storage")
            return self._redis_client
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client for signal storage: {e}")
            self._redis_client_initialized = True  # Avoid repeated attempts
            return None

    def _get_priority(self, signal: Signal) -> int:
        """Get processing priority for a signal.

        Args:
            signal: Signal to prioritize

        Returns:
            Priority value (lower = higher priority)
        """
        if signal.confidence >= 0.90:
            return SignalPriority.HIGH.value
        elif signal.confidence >= self._actionable_threshold:
            return SignalPriority.MEDIUM.value
        else:
            return SignalPriority.LOW.value

    async def process_signal(
        self,
        signal: Signal,
        skip_delivery: bool = False,
    ) -> SignalResult:
        """Process a single signal through the entire pipeline.

        Args:
            signal: Signal to process
            skip_delivery: If True, skip delivery stage

        Returns:
            SignalResult with processing status and metrics
        """
        async with self._semaphore:
            start_time = time.perf_counter()
            metrics = ProcessingMetrics(signal_id=signal.signal_id)
            stage_errors: dict[str, str] = {}
            enriched_signal: EnrichedSignal | None = None
            delivery_results: list[dict[str, Any]] = []

            try:
                # Stage 0: Deduplication (target: 5ms)
                if self._deduper is not None:
                    stage_start = time.perf_counter()
                    dedup_result = self._deduper.is_duplicate(signal)
                    metrics.stage_latencies["dedup"] = (
                        time.perf_counter() - stage_start
                    ) * 1000

                    if dedup_result.is_duplicate:
                        logger.debug(
                            f"Signal {signal.signal_id} deduplicated "
                            f"(window={dedup_result.window_end - dedup_result.window_start:.1f}s)"
                        )
                        return SignalResult(
                            signal=signal,
                            success=True,
                            stage=ProcessingStage.DEDUP,
                            metrics=metrics,
                        )

                # Stage 1: Validation (target: 50ms)
                stage_start = time.perf_counter()
                validation_result = await self.validate_signal(signal)
                metrics.stage_latencies["validation"] = (
                    time.perf_counter() - stage_start
                ) * 1000

                if not validation_result.valid:
                    stage_errors["validation"] = "; ".join(validation_result.errors)
                    logger.warning(
                        f"Signal {signal.signal_id} failed validation: "
                        f"{validation_result.errors}"
                    )
                    return SignalResult(
                        signal=signal,
                        success=False,
                        stage=ProcessingStage.VALIDATION,
                        error="; ".join(validation_result.errors),
                        metrics=metrics,
                    )

                # Stage 2: Enrichment (target: 100ms)
                stage_start = time.perf_counter()
                enriched_signal = await self.enrich_signal(signal)
                metrics.stage_latencies["enrichment"] = (
                    time.perf_counter() - stage_start
                ) * 1000

                # Stage 3: Storage (target: 30ms)
                stage_start = time.perf_counter()
                storage_success = await self._store_signal(enriched_signal)
                metrics.stage_latencies["storage"] = (
                    time.perf_counter() - stage_start
                ) * 1000

                if not storage_success:
                    stage_errors["storage"] = "Failed to store signal"
                    logger.warning(f"Signal {signal.signal_id} storage failed")

                # Stage 4: Delivery (target: 200ms)
                if not skip_delivery:
                    stage_start = time.perf_counter()
                    delivery_results = await self.deliver_signal(enriched_signal)
                    metrics.stage_latencies["delivery"] = (
                        time.perf_counter() - stage_start
                    ) * 1000

                    # Check if any delivery succeeded
                    any_delivery_success = any(
                        r.get("success", False) for r in delivery_results
                    )

                    if not any_delivery_success and delivery_results:
                        stage_errors["delivery"] = "All delivery channels failed"

                # Stage 5: Logging (target: 10ms)
                stage_start = time.perf_counter()
                await self._log_processing_complete(signal, metrics)
                metrics.stage_latencies["logging"] = (
                    time.perf_counter() - stage_start
                ) * 1000

                # Calculate total latency
                metrics.total_latency_ms = (time.perf_counter() - start_time) * 1000
                metrics.stage_errors = stage_errors
                metrics.processed_at = datetime.now(UTC)

                # Update statistics
                self._update_stats(metrics.total_latency_ms, success=True)

                # Check latency target
                if metrics.total_latency_ms > self.TARGET_TOTAL_MS:
                    logger.warning(
                        f"Signal {signal.signal_id} exceeded latency target: "
                        f"{metrics.total_latency_ms:.1f}ms > {self.TARGET_TOTAL_MS}ms"
                    )

                return SignalResult(
                    signal=signal,
                    success=True,
                    stage=ProcessingStage.COMPLETED,
                    metrics=metrics,
                    delivery_results=delivery_results,
                )

            except Exception as e:
                metrics.total_latency_ms = (time.perf_counter() - start_time) * 1000
                metrics.stage_errors = stage_errors
                metrics.processed_at = datetime.now(UTC)

                self._update_stats(metrics.total_latency_ms, success=False)

                logger.error(f"Signal {signal.signal_id} processing failed: {e}")
                return SignalResult(
                    signal=signal,
                    success=False,
                    stage=ProcessingStage.FAILED,
                    error=str(e),
                    metrics=metrics,
                )

    async def process_batch(
        self,
        signals: list[Signal],
        skip_delivery: bool = False,
    ) -> list[SignalResult]:
        """Process multiple signals concurrently.

        Args:
            signals: List of signals to process
            skip_delivery: If True, skip delivery stage for all signals

        Returns:
            List of SignalResults in same order as input
        """
        if not signals:
            return []

        logger.info(f"Processing batch of {len(signals)} signals")
        start_time = time.perf_counter()

        # Create tasks for concurrent processing
        tasks = [
            self.process_signal(signal, skip_delivery=skip_delivery)
            for signal in signals
        ]

        # Process all signals concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        processed_results: list[SignalResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    SignalResult(
                        signal=signals[i],
                        success=False,
                        stage=ProcessingStage.FAILED,
                        error=f"Exception during processing: {result}",
                    )
                )
            else:
                processed_results.append(result)

        elapsed = time.perf_counter() - start_time
        throughput = len(signals) / elapsed if elapsed > 0 else 0
        avg_latency = elapsed / len(signals) * 1000 if signals else 0

        success_count = sum(1 for r in processed_results if r.success)

        logger.info(
            f"Batch processing complete: {success_count}/{len(signals)} successful, "
            f"throughput={throughput:.1f} signals/sec, "
            f"avg_latency={avg_latency:.1f}ms"
        )

        return processed_results

    async def validate_signal(self, signal: Signal) -> ValidationResult:
        """Validate a signal asynchronously.

        Performs async validation checks including:
        - Confidence threshold check
        - Required field validation
        - Data freshness validation

        Args:
            signal: Signal to validate

        Returns:
            ValidationResult with validation status
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Simulate async validation work
        await asyncio.sleep(0.001)  # Minimal async yield

        # Check confidence threshold (75% minimum for actionable)
        if signal.confidence < 0.0 or signal.confidence > 1.0:
            errors.append(f"Invalid confidence value: {signal.confidence}")

        # Check required fields
        if not signal.token:
            errors.append("Missing token")

        if not signal.signal_id:
            errors.append("Missing signal_id")

        # Check timestamp is recent (within last hour)
        from datetime import timedelta

        if signal.timestamp:
            age = datetime.now(UTC) - signal.timestamp
            if age > timedelta(hours=1):
                warnings.append(
                    f"Signal is stale: {age.total_seconds() / 60:.0f} minutes old"
                )

        # Validate direction
        valid_directions = ["long", "short", "neutral"]
        if signal.direction.value.lower() not in valid_directions:
            errors.append(f"Invalid direction: {signal.direction.value}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    async def enrich_signal(self, signal: Signal) -> EnrichedSignal:
        """Enrich a signal with additional context asynchronously.

        Adds context including:
        - Current market price
        - Orderbook depth
        - Risk parameters
        - Market context

        Args:
            signal: Signal to enrich

        Returns:
            EnrichedSignal with additional context
        """
        # Simulate async enrichment work
        await asyncio.sleep(0.001)  # Minimal async yield

        enriched = EnrichedSignal(signal=signal)

        # Add risk parameters based on signal confidence
        if signal.confidence >= 0.90:
            enriched.risk_params = {
                "position_size_pct": 0.05,  # 5% for high confidence
                "max_leverage": 3.0,
                "risk_level": "high_confidence",
            }
        elif signal.confidence >= 0.75:
            enriched.risk_params = {
                "position_size_pct": 0.03,  # 3% for medium confidence
                "max_leverage": 2.0,
                "risk_level": "medium_confidence",
            }
        else:
            enriched.risk_params = {
                "position_size_pct": 0.01,  # 1% for low confidence
                "max_leverage": 1.0,
                "risk_level": "low_confidence",
            }

        # Add market context
        enriched.market_context = {
            "enriched_at": datetime.now(UTC).isoformat(),
            "processor_version": "1.0.0",
            "confidence_tier": (
                "high"
                if signal.confidence >= 0.90
                else "medium" if signal.confidence >= 0.75 else "low"
            ),
        }

        return enriched

    async def deliver_signal(
        self,
        signal: EnrichedSignal,
    ) -> list[dict[str, Any]]:
        """Deliver a signal to all configured emitters asynchronously.

        Args:
            signal: Enriched signal to deliver

        Returns:
            List of delivery results from each emitter
        """
        if not self.emitters:
            return []

        results: list[dict[str, Any]] = []

        # Deliver to all emitters concurrently
        delivery_tasks = []
        for emitter in self.emitters:
            delivery_tasks.append(self._deliver_to_emitter(emitter, signal))

        delivery_results = await asyncio.gather(*delivery_tasks, return_exceptions=True)

        for emitter, result in zip(self.emitters, delivery_results, strict=False):
            if isinstance(result, Exception):
                results.append(
                    {
                        "success": False,
                        "channel": emitter.name,
                        "error": str(result),
                        "latency_ms": 0.0,
                    }
                )
            else:
                results.append(result)

        return results

    async def _deliver_to_emitter(
        self,
        emitter: SignalEmitter,
        enriched_signal: EnrichedSignal,
    ) -> dict[str, Any]:
        """Deliver signal to a single emitter with retry logic.

        Args:
            emitter: Signal emitter to use
            enriched_signal: Signal to deliver

        Returns:
            Delivery result dictionary
        """

        for attempt in range(self.max_retries):
            try:
                start_time = time.perf_counter()

                # Call emitter's emit method
                result = await emitter.emit(enriched_signal.signal)

                latency_ms = (time.perf_counter() - start_time) * 1000

                return {
                    "success": result.success,
                    "channel": result.channel,
                    "error": result.error,
                    "latency_ms": latency_ms,
                }

            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Delivery to {emitter.name} failed (attempt {attempt + 1}), "
                        f"retrying: {e}"
                    )
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    err_msg = (
                        f"Delivery to {emitter.name} failed after "
                        f"{self.max_retries} attempts: {e}"
                    )
                    logger.error(err_msg)
                    return {
                        "success": False,
                        "channel": emitter.name,
                        "error": str(e),
                        "latency_ms": 0.0,
                    }

        # Should not reach here
        return {
            "success": False,
            "channel": emitter.name,
            "error": "Unexpected end of retry loop",
            "latency_ms": 0.0,
        }

    async def _store_signal(self, enriched_signal: EnrichedSignal) -> bool:
        """Store signal to Redis durably.

        Persists signal data as a Redis hash with a 7-day TTL. The key
        follows the pattern ``paper:signal:{timestamp}:{token}:{signal_id}``.
        Writes are idempotent — re-storing the same signal is safe.

        Args:
            enriched_signal: Enriched signal to store

        Returns:
            True if storage succeeded, False otherwise
        """
        client = await self._get_redis_client()
        if client is None:
            logger.warning(
                f"Signal {enriched_signal.signal.signal_id} not stored: "
                "Redis unavailable"
            )
            return False

        signal = enriched_signal.signal
        timestamp_str = (
            signal.timestamp.strftime("%Y%m%dT%H%M%S")
            if signal.timestamp
            else datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        )
        token_safe = signal.token.replace("/", "_")
        redis_key = SIGNAL_KEY_PATTERN.format(
            timestamp=timestamp_str,
            token=token_safe,
            signal_id=signal.signal_id,
        )

        try:
            signal_data = enriched_signal.to_dict()
            # Redis hashes require string values
            flat_data: dict[str, str] = {}
            for k, v in signal_data.items():
                if isinstance(v, dict):
                    flat_data[k] = json.dumps(v, default=str)
                else:
                    flat_data[k] = str(v) if v is not None else ""

            await client.hset(redis_key, mapping=flat_data)
            await client.expire(redis_key, SIGNAL_STORAGE_TTL_SECONDS)
            logger.debug(f"Signal {signal.signal_id} stored to Redis key {redis_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to store signal {signal.signal_id} to Redis: {e}")
            return False

    async def recover_pending_signals(self) -> list[dict[str, Any]]:
        """Scan Redis for stored signals not yet in the processed set.

        On startup or after a restart, this recovers signals that were
        persisted but never fully processed (e.g., crash before delivery).

        Returns:
            List of signal data dicts recovered from Redis.
        """
        client = await self._get_redis_client()
        if client is None:
            logger.warning("Cannot recover signals: Redis unavailable")
            return []

        recovered: list[dict[str, Any]] = []
        try:
            cursor = 0
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor, match="paper:signal:*", count=100
                )
                for key in keys:
                    # Check if already processed (idempotency guard)
                    is_processed = await client.sismember(PROCESSED_SIGNALS_KEY, key)
                    if is_processed:
                        continue

                    signal_data = await client.hgetall(key)
                    if signal_data:
                        # Reconstruct nested JSON fields
                        for field_name in (
                            "signal",
                            "orderbook_depth",
                            "risk_params",
                            "market_context",
                        ):
                            raw = signal_data.get(field_name)
                            if raw and isinstance(raw, str):
                                with contextlib.suppress(
                                    json.JSONDecodeError, TypeError
                                ):
                                    signal_data[field_name] = json.loads(raw)
                        recovered.append(signal_data)
                        logger.info(f"Recovered pending signal from {key}")

                if cursor == 0:
                    break

            if recovered:
                logger.info(f"Recovered {len(recovered)} pending signal(s) from Redis")
            else:
                logger.debug("No pending signals to recover from Redis")

        except Exception as e:
            logger.error(f"Error recovering pending signals: {e}")

        return recovered

    async def _log_processing_complete(
        self,
        signal: Signal,
        metrics: ProcessingMetrics,
    ) -> None:
        """Log processing completion asynchronously.

        Args:
            signal: Processed signal
            metrics: Processing metrics
        """
        # Simulate async logging work
        await asyncio.sleep(0.0001)  # Minimal async yield

        logger.debug(
            f"Signal {signal.signal_id} processing complete: "
            f"{metrics.total_latency_ms:.1f}ms total"
        )

    def _update_stats(self, latency_ms: float, success: bool) -> None:
        """Update processing statistics.

        Args:
            latency_ms: Processing latency
            success: Whether processing succeeded
        """
        self._stats["processed"] += 1
        if success:
            self._stats["successful"] += 1
        else:
            self._stats["failed"] += 1

        self._stats["total_latency_ms"] += latency_ms
        self._stats["avg_latency_ms"] = (
            self._stats["total_latency_ms"] / self._stats["processed"]
        )

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics.

        Returns:
            Dictionary with processing statistics
        """
        return {
            "processed": self._stats["processed"],
            "successful": self._stats["successful"],
            "failed": self._stats["failed"],
            "success_rate": (
                self._stats["successful"] / self._stats["processed"]
                if self._stats["processed"] > 0
                else 0.0
            ),
            "avg_latency_ms": round(self._stats["avg_latency_ms"], 3),
            "max_concurrent": self.max_concurrent,
        }

    def reset_stats(self) -> None:
        """Reset processing statistics."""
        self._stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "total_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
        }
        logger.info("AsyncSignalProcessor statistics reset")

    async def process_priority_queue(self) -> list[SignalResult]:
        """Process all signals in the priority queue.

        Returns:
            List of SignalResults
        """
        signals: list[Signal] = []

        # Drain the priority queue
        while not self._priority_queue.empty():
            try:
                _, signal = self._priority_queue.get_nowait()
                signals.append(signal)
            except asyncio.QueueEmpty:
                break

        if signals:
            logger.info(f"Processing {len(signals)} signals from priority queue")
            return await self.process_batch(signals)

        return []

    async def add_to_priority_queue(self, signal: Signal) -> None:
        """Add a signal to the priority queue.

        Args:
            signal: Signal to add
        """
        priority = self._get_priority(signal)
        await self._priority_queue.put((priority, signal))
        logger.debug(
            f"Signal {signal.signal_id} added to priority queue (p={priority})"
        )


class SignalPipeline:
    """Async signal processing pipeline.

    Main pipeline that orchestrates signal generation, processing,
    and delivery using async operations for maximum throughput.

    Attributes:
        processor: AsyncSignalProcessor for signal processing
        generator: SignalGenerator for signal generation
        running: Whether the pipeline is currently running
    """

    def __init__(
        self,
        processor: AsyncSignalProcessor | None = None,
        generator: Any | None = None,
    ):
        """Initialize signal pipeline.

        Args:
            processor: AsyncSignalProcessor instance (created if None)
            generator: SignalGenerator instance (created if None)
        """
        self.processor = processor or AsyncSignalProcessor()
        self._generator = generator
        self._running = False
        self._shutdown_event = asyncio.Event()

        logger.info("SignalPipeline initialized")

    def _get_generator(self) -> Any:
        """Get or create SignalGenerator."""
        if self._generator is None:
            from signal_generation.signal_generator import SignalGenerator

            self._generator = SignalGenerator()
        return self._generator

    @property
    def is_running(self) -> bool:
        """Check if pipeline is running."""
        return self._running

    async def run(self, signal_source: Any | None = None) -> None:
        """Run the main pipeline loop.

        Continuously processes signals from the signal source until
        shutdown is requested.

        Args:
            signal_source: Source of signals (optional, for future use)
        """
        self._running = True
        self._shutdown_event.clear()

        logger.info("SignalPipeline started")

        try:
            while self._running and not self._shutdown_event.is_set():
                # Process priority queue
                results = await self.processor.process_priority_queue()

                if results:
                    success_count = sum(1 for r in results if r.success)
                    logger.info(
                        f"Pipeline iteration: {success_count}/{len(results)} "
                        "signals processed"
                    )

                # Small yield to prevent tight loop
                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.info("SignalPipeline cancelled")
        except Exception as e:
            logger.error(f"SignalPipeline error: {e}")
        finally:
            self._running = False
            logger.info("SignalPipeline stopped")

    async def handle_new_signal(self, raw_data: dict[str, Any]) -> SignalResult:
        """Process a new signal from market data.

        Args:
            raw_data: Raw signal data from market analysis

        Returns:
            SignalResult with processing status
        """
        from signal_generation.models import Signal, SignalDirection, SignalStatus

        start_time = time.perf_counter()

        try:
            # Create signal from raw data
            signal = Signal(
                token=raw_data.get("token", "UNKNOWN"),
                direction=SignalDirection(raw_data.get("direction", "neutral")),
                confidence=raw_data.get("confidence", 0.0),
                base_score=raw_data.get("base_score", 0.0),
                timestamp=datetime.now(UTC),
                status=SignalStatus.LOGGED_ONLY,
                timeframe=raw_data.get("timeframe", "1h"),
                metadata=raw_data.get("metadata", {}),
            )

            # Process the signal
            result = await self.processor.process_signal(signal)

            total_latency = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"New signal handled: {signal.token} [{signal.direction.value}] "
                f"in {total_latency:.1f}ms"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to handle new signal: {e}")
            return SignalResult(
                signal=None,
                success=False,
                stage=ProcessingStage.FAILED,
                error=str(e),
            )

    async def shutdown(self) -> None:
        """Shutdown the pipeline gracefully."""
        logger.info("SignalPipeline shutdown requested")
        self._running = False
        self._shutdown_event.set()

        # Wait for current processing to complete
        await asyncio.sleep(0.1)

        logger.info("SignalPipeline shutdown complete")

    def get_pipeline_stats(self) -> dict[str, Any]:
        """Get combined pipeline statistics.

        Returns:
            Dictionary with pipeline and processor statistics
        """
        return {
            "running": self._running,
            "processor_stats": self.processor.get_stats(),
        }
