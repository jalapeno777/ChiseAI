"""Load testing utilities and shared components."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class LoadTestMetrics:
    """Metrics collected during load testing."""

    test_name: str
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None

    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Latency metrics (in milliseconds)
    latencies: list[float] = field(default_factory=list)

    # Throughput metrics
    requests_per_second: float = 0.0

    # Error tracking
    errors: list[dict[str, Any]] = field(default_factory=list)

    def record_request(
        self, latency_ms: float, success: bool, error: str | None = None
    ) -> None:
        """Record a request result."""
        self.total_requests += 1
        self.latencies.append(latency_ms)

        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if error:
                self.errors.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": error,
                    }
                )

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    @property
    def p50_latency_ms(self) -> float:
        """Calculate 50th percentile (median) latency."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.5)
        return sorted_latencies[idx]

    @property
    def p95_latency_ms(self) -> float:
        """Calculate 95th percentile latency."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx]

    @property
    def p99_latency_ms(self) -> float:
        """Calculate 99th percentile latency."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx]

    @property
    def min_latency_ms(self) -> float:
        """Calculate minimum latency."""
        if not self.latencies:
            return 0.0
        return min(self.latencies)

    @property
    def max_latency_ms(self) -> float:
        """Calculate maximum latency."""
        if not self.latencies:
            return 0.0
        return max(self.latencies)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    def finalize(self) -> None:
        """Finalize metrics calculation."""
        self.end_time = datetime.now(UTC)
        duration_seconds = (self.end_time - self.start_time).total_seconds()
        if duration_seconds > 0:
            self.requests_per_second = self.total_requests / duration_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "test_name": self.test_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.success_rate,
            "requests_per_second": self.requests_per_second,
            "latency_ms": {
                "avg": self.avg_latency_ms,
                "p50": self.p50_latency_ms,
                "p95": self.p95_latency_ms,
                "p99": self.p99_latency_ms,
                "min": self.min_latency_ms,
                "max": self.max_latency_ms,
            },
            "error_count": len(self.errors),
            "errors": self.errors[:10],  # Include first 10 errors
        }


class CircuitBreakerSimulator:
    """Simulates circuit breaker behavior for load testing."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        """Initialize circuit breaker simulator.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Max calls allowed in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        """Get current circuit state."""
        return self._state

    async def call(self, func: callable, *args, **kwargs) -> Any:
        """Execute a function with circuit breaker protection.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        async with self._lock:
            # Check if we should transition from open to half-open
            if self._state == "open":
                if self._last_failure_time and (
                    time.time() - self._last_failure_time >= self.recovery_timeout
                ):
                    self._state = "half_open"
                    self._half_open_calls = 0
                    logger.info("Circuit breaker entering half-open state")
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is open")

            # Check half-open call limit
            if self._state == "half_open":
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        "Circuit breaker is half-open (limit reached)"
                    )
                self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self._state == "half_open":
                # Success in half-open state closes the circuit
                self._state = "closed"
                self._failure_count = 0
                self._half_open_calls = 0
                logger.info("Circuit breaker closed after successful recovery")
            else:
                # Success in closed state resets failure count
                self._failure_count = 0

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == "half_open":
                # Failure in half-open state opens the circuit again
                self._state = "open"
                self._half_open_calls = 0
                logger.warning("Circuit breaker opened after recovery failure")
            elif self._failure_count >= self.failure_threshold:
                # Too many failures opens the circuit
                self._state = "open"
                logger.warning(
                    f"Circuit breaker opened after {self._failure_count} failures"
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert circuit breaker state to dictionary."""
        return {
            "state": self._state,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self._last_failure_time,
            "half_open_calls": self._half_open_calls,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


class MetricsCollector:
    """Collects and aggregates metrics from multiple sources."""

    def __init__(self):
        """Initialize metrics collector."""
        self._metrics: dict[str, LoadTestMetrics] = {}

    def register(self, name: str, metrics: LoadTestMetrics) -> None:
        """Register a metrics instance."""
        self._metrics[name] = metrics

    def get(self, name: str) -> LoadTestMetrics | None:
        """Get metrics by name."""
        return self._metrics.get(name)

    def get_all(self) -> dict[str, LoadTestMetrics]:
        """Get all registered metrics."""
        return self._metrics.copy()

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive report."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "tests": {
                name: metrics.to_dict() for name, metrics in self._metrics.items()
            },
            "summary": {
                "total_tests": len(self._metrics),
                "total_requests": sum(m.total_requests for m in self._metrics.values()),
                "total_successful": sum(
                    m.successful_requests for m in self._metrics.values()
                ),
                "total_failed": sum(m.failed_requests for m in self._metrics.values()),
                "overall_success_rate": (
                    sum(m.successful_requests for m in self._metrics.values())
                    / max(1, sum(m.total_requests for m in self._metrics.values()))
                ),
            },
        }

    def export_to_json(self, filepath: str) -> None:
        """Export report to JSON file."""
        report = self.generate_report()
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Metrics exported to {filepath}")


# Global metrics collector instance
metrics_collector = MetricsCollector()


class LatencyBenchmark:
    """Benchmark tool for measuring latency percentiles.

    Provides percentile-based latency measurements for performance testing.
    """

    def __init__(self, name: str):
        """Initialize latency benchmark.

        Args:
            name: Benchmark name
        """
        self.name = name
        self.latencies_ms: list[float] = []

    def record(self, latency_ms: float) -> None:
        """Record a latency measurement."""
        self.latencies_ms.append(latency_ms)

    def get_percentile(self, percentile: float) -> float:
        """Get latency at specified percentile.

        Args:
            percentile: Percentile (0.0 to 1.0)

        Returns:
            Latency in milliseconds at the specified percentile
        """
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * percentile)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p50(self) -> float:
        """50th percentile (median) latency."""
        return self.get_percentile(0.5)

    @property
    def p95(self) -> float:
        """95th percentile latency."""
        return self.get_percentile(0.95)

    @property
    def p99(self) -> float:
        """99th percentile latency."""
        return self.get_percentile(0.99)

    @property
    def avg(self) -> float:
        """Average latency."""
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

    def assert_requirement(
        self, max_latency_ms: float, percentile: float = 0.95
    ) -> None:
        """Assert that latency requirement is met.

        Args:
            max_latency_ms: Maximum allowed latency
            percentile: Percentile to check (default 0.95 for P95)

        Raises:
            AssertionError: If requirement is not met
        """
        actual = self.get_percentile(percentile)
        if actual > max_latency_ms:
            raise AssertionError(
                f"{self.name}: Latency at P{int(percentile * 100)} "
                f"({actual:.1f}ms) exceeds requirement ({max_latency_ms}ms)"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert benchmark results to dictionary."""
        return {
            "name": self.name,
            "count": len(self.latencies_ms),
            "avg_ms": self.avg,
            "p50_ms": self.p50,
            "p95_ms": self.p95,
            "p99_ms": self.p99,
            "min_ms": min(self.latencies_ms) if self.latencies_ms else 0,
            "max_ms": max(self.latencies_ms) if self.latencies_ms else 0,
        }


class SustainedLoadTest:
    """Helper for running sustained load tests over time.

    Manages the execution of load tests for specified durations
    and collects metrics throughout.
    """

    def __init__(
        self,
        name: str,
        target_rate_per_second: float,
        duration_seconds: float,
    ):
        """Initialize sustained load test.

        Args:
            name: Test name
            target_rate_per_second: Target operations per second
            duration_seconds: Test duration in seconds
        """
        self.name = name
        self.target_rate_per_second = target_rate_per_second
        self.duration_seconds = duration_seconds
        self.metrics = LoadTestMetrics(test_name=name)

    async def run(
        self,
        operation: callable,
        *args,
        **kwargs,
    ) -> LoadTestMetrics:
        """Run the sustained load test.

        Args:
            operation: Async function to call
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            LoadTestMetrics with collected results
        """
        start_time = time.perf_counter()
        end_time = start_time + self.duration_seconds

        # Calculate interval between requests to achieve target rate
        interval = 1.0 / self.target_rate_per_second

        tasks = []
        next_request_time = start_time

        while time.perf_counter() < end_time:
            # Wait until next request time
            now = time.perf_counter()
            if now < next_request_time:
                await asyncio.sleep(next_request_time - now)

            # Launch request
            task = asyncio.create_task(self._execute_operation(operation, args, kwargs))
            tasks.append(task)

            next_request_time += interval

            # Process completed tasks periodically to avoid memory buildup
            if len(tasks) >= 100:
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.1,
                )
                for task in done:
                    await task
                tasks = list(pending)

        # Wait for all remaining tasks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.metrics.finalize()
        return self.metrics

    async def _execute_operation(
        self,
        operation: callable,
        args: tuple,
        kwargs: dict,
    ) -> None:
        """Execute a single operation and record metrics."""
        start = time.perf_counter()
        try:
            await operation(*args, **kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            self.metrics.record_request(latency_ms=latency_ms, success=True)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self.metrics.record_request(
                latency_ms=latency_ms, success=False, error=str(e)
            )
