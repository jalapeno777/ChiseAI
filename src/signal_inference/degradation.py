"""Graceful degradation for signal pipeline.

Implements degradation behavior for four failure modes:
1. Individual Signal Failure - degrade signal, continue pipeline
2. Redis Slow/Unavailable - circuit breaker with fallback
3. Bybit API Rate-Limited - backoff/retry with jitter
4. Network Partition - detection, queue, stale data fallback

For TASK-H1: Graceful Degradation Mode Implementation
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DegradationMode(Enum):
    """Mode of degradation affecting the signal pipeline."""

    SIGNAL_FAILURE = "signal_failure"
    REDIS_FAILURE = "redis_failure"
    RATE_LIMITED = "rate_limited"
    NETWORK_PARTITION = "network_partition"
    HEALTHY = "healthy"


class CircuitBreakerState(Enum):
    """State of a circuit breaker."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast, using fallback
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class DegradedSignal:
    """Signal that has entered degraded mode.

    Attributes:
        signal_id: Unique signal identifier
        token: Trading pair/token
        original_error: The error that caused degradation
        failure_mode: Type of failure that occurred
        occurred_at: When the failure occurred
        is_degraded: Whether signal is in degraded state
        continue_pipeline: Whether to continue processing other signals
        metadata: Additional degradation context
    """

    signal_id: str
    token: str
    original_error: Exception | str
    failure_mode: DegradationMode
    occurred_at: datetime
    is_degraded: bool = True
    continue_pipeline: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        error_str = (
            str(self.original_error)
            if isinstance(self.original_error, Exception)
            else self.original_error
        )
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "original_error": error_str,
            "failure_mode": self.failure_mode.value,
            "occurred_at": self.occurred_at.isoformat(),
            "is_degraded": self.is_degraded,
            "continue_pipeline": self.continue_pipeline,
            "metadata": self.metadata,
        }


@dataclass
class StalenessIndicator:
    """Indicator for stale data with age information."""

    is_stale: bool
    age_seconds: float
    max_age_seconds: float
    fetched_at: datetime
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_stale": self.is_stale,
            "age_seconds": self.age_seconds,
            "max_age_seconds": self.max_age_seconds,
            "fetched_at": self.fetched_at.isoformat(),
            "source": self.source,
        }


@dataclass
class PartitionDetectionResult:
    """Result of network partition detection check."""

    is_partitioned: bool
    is_timeout: bool
    is_healthy: bool
    consecutive_timeouts: int
    latency_ms: float | None = None
    message: str = ""


class SignalFailureDetector:
    """Detects and handles individual signal failures.

    When a signal fails, this detector:
    - Marks the signal as DEGRADED
    - Allows pipeline to continue with available signals
    - Provides detection hooks for signal failures
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_threshold_ms: float = 5000.0,
    ) -> None:
        """Initialize signal failure detector.

        Args:
            failure_threshold: Number of failures before degradation mode
            timeout_threshold_ms: Timeout threshold in milliseconds
        """
        self._failure_threshold = failure_threshold
        self._timeout_threshold_ms = timeout_threshold_ms
        self._degraded_signals: dict[str, DegradedSignal] = {}
        self._failure_history: list[DegradedSignal] = []
        self._recovery_times: dict[str, datetime] = {}

    def is_signal_degraded(self, signal_id: str) -> bool:
        """Check if a signal is currently degraded."""
        if signal_id not in self._degraded_signals:
            return False
        degraded = self._degraded_signals[signal_id]
        return degraded.is_degraded

    def get_failure_count(self, signal_id: str) -> int:
        """Get number of failures for a specific signal."""
        return sum(1 for s in self._failure_history if s.signal_id == signal_id)

    def is_degradation_mode_active(self) -> bool:
        """Check if degradation mode is currently active."""
        if not self._degraded_signals:
            return False
        return len(self._degraded_signals) >= self._failure_threshold

    def get_total_failures(self) -> int:
        """Get total number of recorded failures."""
        return len(self._failure_history)

    def record_failure(self, failed_signal: DegradedSignal) -> None:
        """Record a signal failure.

        Args:
            failed_signal: The failed signal details
        """
        failed_signal.is_degraded = True
        self._degraded_signals[failed_signal.signal_id] = failed_signal
        self._failure_history.append(failed_signal)
        logger.warning(
            f"Signal failure recorded: {failed_signal.signal_id} "
            f"[{failed_signal.failure_mode.value}] - {failed_signal.original_error}"
        )

    def record_recovery(self, signal_id: str) -> None:
        """Record recovery of a signal.

        Args:
            signal_id: Signal that recovered
        """
        if signal_id in self._degraded_signals:
            self._degraded_signals[signal_id].is_degraded = False
            self._recovery_times[signal_id] = datetime.now(UTC)
            logger.info(f"Signal recovered: {signal_id}")

    def mark_degraded(
        self,
        signal_id: str,
        token: str,
        error_message: str,
        continue_pipeline: bool = True,
    ) -> DegradedSignal:
        """Mark a signal as degraded with continuation option.

        Args:
            signal_id: Signal identifier
            token: Trading pair
            error_message: Error description
            continue_pipeline: Whether pipeline should continue

        Returns:
            DegradedSignal instance
        """
        degraded = DegradedSignal(
            signal_id=signal_id,
            token=token,
            original_error=error_message,
            failure_mode=DegradationMode.SIGNAL_FAILURE,
            occurred_at=datetime.now(UTC),
            continue_pipeline=continue_pipeline,
            metadata={"continue_pipeline": continue_pipeline},
        )
        self._degraded_signals[signal_id] = degraded
        self._failure_history.append(degraded)
        return degraded

    def get_available_signals(
        self,
        all_signals: list[str],
        failed_signals: list[str],
    ) -> list[str]:
        """Get signals that are available (not failed).

        Args:
            all_signals: All known signal IDs
            failed_signals: Signal IDs that failed

        Returns:
            List of available signal IDs
        """
        failed_set = set(failed_signals)
        return [s for s in all_signals if s not in failed_set]

    def get_degraded_signals(self) -> list[DegradedSignal]:
        """Get all signals currently in degraded state."""
        return [s for s in self._degraded_signals.values() if s.is_degraded]


class RedisCircuitBreaker:
    """Circuit breaker for Redis operations with fallback behavior.

    Implements the circuit breaker pattern:
    - CLOSED: Normal operation, failures increment counter
    - OPEN: Failures exceeded threshold, fast-fail with fallback
    - HALF_OPEN: Testing recovery with limited calls
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 60.0,
        recovery_timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3,
    ) -> None:
        """Initialize Redis circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            timeout_seconds: Operation timeout in seconds
            recovery_timeout_seconds: Time before attempting recovery
            half_open_max_calls: Max calls in half-open state
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._recent_latencies: list[float] = []
        self._latency_threshold_ms = 100.0  # Threshold for slow operation

    def is_open(self) -> bool:
        """Check if circuit is currently open."""
        return self.state == CircuitBreakerState.OPEN

    def record_failure(self, error: str | Exception) -> None:
        """Record a Redis operation failure.

        Args:
            error: The error that occurred
        """
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                f"Redis circuit breaker OPEN after {self._failure_count} failures"
            )

        error_str = str(error) if isinstance(error, Exception) else error
        logger.error(f"Redis failure recorded: {error_str}")

    def record_latency(self, latency_ms: float) -> None:
        """Record operation latency for slow operation detection.

        Args:
            latency_ms: Operation latency in milliseconds
        """
        self._recent_latencies.append(latency_ms)
        # Keep only recent latencies
        if len(self._recent_latencies) > 100:
            self._recent_latencies = self._recent_latencies[-100:]

        if latency_ms > self._latency_threshold_ms:
            logger.warning(
                f"Redis slow operation detected: {latency_ms}ms "
                f"(threshold: {self._latency_threshold_ms}ms)"
            )

    def get_recent_latencies(self) -> list[float]:
        """Get recent operation latencies."""
        return self._recent_latencies.copy()

    def record_success(self) -> None:
        """Record a successful Redis operation."""
        self._failure_count = 0
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            logger.info("Redis circuit breaker CLOSED - recovery successful")
        self._half_open_calls = 0

    def _should_attempt_recovery(self) -> bool:
        """Check if circuit should attempt recovery."""
        if self.state != CircuitBreakerState.OPEN:
            return False
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.recovery_timeout_seconds

    def _can_execute_in_half_open(self) -> bool:
        """Check if operation can execute in half-open state."""
        if self.state != CircuitBreakerState.HALF_OPEN:
            return False
        return self._half_open_calls < self.half_open_max_calls

    async def execute_with_fallback(
        self,
        operation_key: str,
        fallback: Callable[[], T],
        timeout_seconds: float | None = None,
    ) -> T:
        """Execute operation with circuit breaker and fallback.

        Args:
            operation_key: Key identifying the operation
            fallback: Fallback function to call on failure
            timeout_seconds: Optional timeout for operation

        Returns:
            Result from operation or fallback
        """
        timeout = timeout_seconds or self.timeout_seconds

        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_recovery():
                self.state = CircuitBreakerState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Redis circuit breaker HALF_OPEN - testing recovery")
            else:
                logger.warning(
                    f"Redis circuit breaker OPEN, using fallback for {operation_key}"
                )
                return fallback()

        if self.state == CircuitBreakerState.HALF_OPEN:
            if not self._can_execute_in_half_open():
                logger.warning("Redis half-open max calls reached, using fallback")
                return fallback()
            self._half_open_calls += 1

        # Execute operation with timeout
        try:
            start = time.time()
            result = await asyncio.wait_for(
                asyncio.shield(self._execute_redis_operation(operation_key)),
                timeout=timeout,
            )
            latency_ms = (time.time() - start) * 1000
            self.record_latency(latency_ms)
            self.record_success()
            return result
        except TimeoutError:
            self.record_failure(f"Operation timed out after {timeout}s")
            logger.warning(f"Redis operation timeout: {operation_key}")
            return fallback()
        except Exception as e:
            self.record_failure(str(e))
            return fallback()

    async def _execute_redis_operation(self, operation_key: str) -> Any:
        """Execute the actual Redis operation.

        This is a placeholder - real implementation would call Redis.
        """
        # Simulate Redis operation
        await asyncio.sleep(0.01)
        return {"data": "redis_result", "source": "redis"}


class RateLimitPolicy:
    """Rate limit policy with backoff and jitter.

    Handles Bybit API rate limiting with:
    - Backoff/retry with exponential increase
    - Jitter to prevent thundering herd
    - Graceful degradation when rate limited
    """

    def __init__(
        self,
        max_requests_per_minute: int = 60,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 60.0,
        jitter_factor: float = 0.3,
        adaptive_throttling: bool = False,
    ) -> None:
        """Initialize rate limit policy.

        Args:
            max_requests_per_minute: Maximum requests per minute
            backoff_base_seconds: Base backoff delay
            backoff_max_seconds: Maximum backoff delay
            jitter_factor: Jitter as fraction of delay (0.0-1.0)
            adaptive_throttling: Enable adaptive throttling based on errors
        """
        self.max_requests_per_minute = max_requests_per_minute
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.jitter_factor = jitter_factor
        self.adaptive_throttling = adaptive_throttling

        self._current_backoff = backoff_base_seconds
        self._request_history: list[float] = []
        self._rate_limit_count = 0
        self._last_rate_limit_time: float = 0.0
        self.throttle_threshold = max_requests_per_minute

    def should_throttle(self) -> bool:
        """Check if request should be throttled."""
        self._clean_old_requests()
        return len(self._request_history) >= self.max_requests_per_minute

    def is_near_limit(self) -> bool:
        """Check if approaching rate limit."""
        self._clean_old_requests()
        return len(self._request_history) >= int(self.max_requests_per_minute * 0.8)

    def record_request(self, cost: int = 1) -> None:
        """Record a request for rate limiting.

        Args:
            cost: Cost of the request (for cost-based limits)
        """
        current_time = time.time()
        self._request_history.append(current_time)
        self._adjust_throttle_threshold()

    def record_rate_limit_response(self) -> None:
        """Record a 429 rate limit response."""
        self._rate_limit_count += 1
        self._last_rate_limit_time = time.time()

        # Exponential backoff
        self._current_backoff = min(
            self._current_backoff * 2,
            self.backoff_max_seconds,
        )
        logger.warning(
            f"Rate limit response recorded, backoff increased to "
            f"{self._current_backoff:.1f}s"
        )

    def record_success(self) -> None:
        """Record a successful request, reset backoff."""
        self._current_backoff = self.backoff_base_seconds
        self._rate_limit_count = max(0, self._rate_limit_count - 1)

    def get_current_backoff(self) -> float:
        """Get current backoff with jitter applied.

        Returns:
            Backoff delay in seconds with jitter
        """
        jitter_range = self._current_backoff * self.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        return max(0.1, self._current_backoff + jitter)

    def get_degraded_result(
        self,
        cached_data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Get degraded result when rate limited.

        Args:
            cached_data: Cached data to use as fallback

        Returns:
            Degraded result with staleness indicator
        """
        if cached_data is None:
            return {
                "rate_limited": True,
                "error": "Rate limited, no cached data available",
                "timestamp": time.time(),
            }

        result = dict(cached_data)
        result["rate_limited"] = True
        result["cached"] = True
        result["backoff_seconds"] = self._current_backoff
        return result

    def _clean_old_requests(self) -> None:
        """Remove requests older than 1 minute from history."""
        current_time = time.time()
        cutoff = current_time - 60.0
        self._request_history = [t for t in self._request_history if t > cutoff]

    def _adjust_throttle_threshold(self) -> None:
        """Adjust throttle threshold based on error rate."""
        if not self.adaptive_throttling:
            return

        if self._rate_limit_count > 5:
            # Reduce threshold by 20% after repeated rate limits
            self.throttle_threshold = int(self.max_requests_per_minute * 0.8)
        elif self._rate_limit_count > 10:
            self.throttle_threshold = int(self.max_requests_per_minute * 0.5)

    def is_cost_limit_reached(self) -> bool:
        """Check if cost-based limit is reached."""
        if not hasattr(self, "_request_costs"):
            return False
        total_cost = sum(self._request_costs)
        return total_cost >= self.max_requests_per_minute * 10


class RetryWithBackoff:
    """Retry mechanism with exponential backoff and jitter."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter_factor: float = 0.2,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        """Initialize retry mechanism.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay between retries
            max_delay: Maximum delay between retries
            jitter_factor: Jitter as fraction of delay
            retryable_exceptions: Exception types to retry on
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self.retryable_exceptions = retryable_exceptions

    async def execute(
        self,
        operation: Callable[[], T],
    ) -> T:
        """Execute operation with retry logic.

        Args:
            operation: Async operation to execute

        Returns:
            Result from operation

        Raises:
            Last exception if all retries fail
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_attempts):
            try:
                return await operation()
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.max_attempts - 1:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    jitter = delay * self.jitter_factor * random.random()
                    actual_delay = delay + jitter
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{self.max_attempts} failed: {e}. "
                        f"Retrying in {actual_delay:.2f}s"
                    )
                    await asyncio.sleep(actual_delay)
                else:
                    logger.error(f"All {self.max_attempts} retry attempts failed")

        if last_exception:
            raise last_exception
        raise RuntimeError("Retry logic exhausted without exception")


class NetworkPartitionDetector:
    """Detects network partitions and provides fallback behavior.

    Detects partitions via:
    - Operation timeouts
    - Consecutive timeout patterns
    - High latency spikes

    Fallback behavior:
    - Queue operations for retry
    - Use stale data with staleness indicator
    """

    def __init__(
        self,
        timeout_threshold_seconds: float = 5.0,
        consecutive_timeout_threshold: int = 3,
        max_staleness_seconds: float = 300.0,
    ) -> None:
        """Initialize network partition detector.

        Args:
            timeout_threshold_seconds: Timeout threshold in seconds
            consecutive_timeout_threshold: Consecutive timeouts to detect partition
            max_staleness_seconds: Maximum staleness for fallback data
        """
        self.timeout_threshold_seconds = timeout_threshold_seconds
        self.consecutive_timeout_threshold = consecutive_timeout_threshold
        self.max_staleness_seconds = max_staleness_seconds

        self._is_partitioned = False
        self._partition_detected_at: datetime | None = None
        self._consecutive_timeouts = 0
        self._operation_queue: list[dict[str, Any]] = []
        self._latency_history: list[float] = []

    def is_partition_detected(self) -> bool:
        """Check if network partition is currently detected."""
        return self._is_partitioned

    def is_healthy(self) -> bool:
        """Check if network is currently healthy."""
        return not self._is_partitioned and self._consecutive_timeouts < 2

    def record_timeout(self) -> None:
        """Record an operation timeout."""
        self._consecutive_timeouts += 1

        if self._consecutive_timeouts >= self.consecutive_timeout_threshold:
            self._is_partitioned = True
            self._partition_detected_at = datetime.now(UTC)
            logger.error(
                f"Network partition detected after "
                f"{self._consecutive_timeouts} consecutive timeouts"
            )

    def record_success(self) -> None:
        """Record a successful operation."""
        self._consecutive_timeouts = 0
        if self._is_partitioned:
            self._is_partitioned = False
            self._partition_detected_at = None
            logger.info("Network partition resolved")

    def check_operation_latency(
        self,
        latency_ms: float,
    ) -> PartitionDetectionResult:
        """Check if operation latency indicates partition.

        Args:
            latency_ms: Operation latency in milliseconds

        Returns:
            Partition detection result
        """
        latency_seconds = latency_ms / 1000.0
        is_timeout = latency_seconds >= self.timeout_threshold_seconds

        self._latency_history.append(latency_ms)
        if len(self._latency_history) > 100:
            self._latency_history = self._latency_history[-100:]

        if is_timeout:
            self.record_timeout()
        else:
            self._consecutive_timeouts = 0

        return PartitionDetectionResult(
            is_partitioned=self._is_partitioned,
            is_timeout=is_timeout,
            is_healthy=not self._is_partitioned,
            consecutive_timeouts=self._consecutive_timeouts,
            latency_ms=latency_ms,
            message=(
                "Network partition detected"
                if self._is_partitioned
                else "Operation healthy"
            ),
        )

    def queue_for_retry(
        self,
        operation_id: str,
        operation_params: dict[str, Any],
    ) -> None:
        """Queue an operation for retry after partition.

        Args:
            operation_id: Unique operation identifier
            operation_params: Parameters for the operation
        """
        self._operation_queue.append(
            {
                "operation_id": operation_id,
                "params": operation_params,
                "queued_at": datetime.now(UTC).isoformat(),
                "attempt": 0,
            }
        )
        logger.info(f"Operation queued for retry: {operation_id}")

    def get_pending_retries(self) -> list[dict[str, Any]]:
        """Get operations pending retry.

        Returns:
            List of queued operations
        """
        return self._operation_queue.copy()

    def get_with_stale_fallback(
        self,
        fresh_compute: Callable[[], T] | None,
        stale_data: dict[str, Any],
    ) -> dict[str, Any] | T:
        """Get data with stale fallback when partition is detected.

        Args:
            fresh_compute: Function to compute fresh data
            stale_data: Stale data to use as fallback

        Returns:
            Fresh compute result or stale data with indicator
        """
        if not self._is_partitioned:
            if fresh_compute:
                return fresh_compute()
            return stale_data

        result = self.add_staleness_indicator(stale_data)
        logger.warning(
            f"Using stale data (age: {result['staleness_indicator']['age_seconds']:.1f}s) "
            f"due to network partition"
        )
        return result

    def add_staleness_indicator(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Add staleness indicator to data.

        Args:
            data: Data to add indicator to

        Returns:
            Data with staleness indicator
        """
        fetched_at = data.get("_fetched_at", time.time())
        age_seconds = time.time() - fetched_at

        is_stale = age_seconds > self.max_staleness_seconds

        indicator = {
            "staleness_indicator": {
                "is_stale": is_stale,
                "age_seconds": age_seconds,
                "max_age_seconds": self.max_staleness_seconds,
                "fetched_at": datetime.fromtimestamp(fetched_at, tz=UTC).isoformat(),
                "source": "stale_cache",
            }
        }

        return {**data, **indicator}


class StaleDataIndicator:
    """Marks data with staleness information."""

    def __init__(
        self,
        max_age_seconds: float = 300.0,
    ) -> None:
        """Initialize stale data indicator.

        Args:
            max_age_seconds: Maximum age before data is considered stale
        """
        self.max_age_seconds = max_age_seconds

    def mark_if_stale(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Mark data as stale if older than threshold.

        Args:
            data: Data to check and mark

        Returns:
            Data with staleness indicator added
        """
        fetched_at = data.get("_fetched_at", time.time())
        age_seconds = time.time() - fetched_at

        is_stale = age_seconds > self.max_age_seconds

        result = {
            **data,
            "staleness_indicator": {
                "is_stale": is_stale,
                "age_seconds": age_seconds,
                "max_age_seconds": self.max_age_seconds,
                "fetched_at": datetime.fromtimestamp(fetched_at, tz=UTC).isoformat(),
            },
        }

        if is_stale:
            logger.warning(
                f"Data marked as stale (age: {age_seconds:.1f}s, "
                f"max: {self.max_age_seconds}s)"
            )

        return result

    def calculate_staleness(self, timestamp: float) -> float:
        """Calculate staleness in seconds.

        Args:
            timestamp: Data timestamp

        Returns:
            Staleness in seconds
        """
        return time.time() - timestamp
