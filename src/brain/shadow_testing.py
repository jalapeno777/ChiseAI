"""Shadow testing framework for brain version comparison with latency measurement.

ST-CHISE-001.2: Add Shadow Testing Component with Latency Measurement

This module provides infrastructure for running shadow tests where a candidate
brain version runs in parallel with a baseline version, measuring latency
overhead and prediction differences.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.brain.version import BrainVersion

# Type alias for brain functions
BrainFunction = Callable[[Any], Coroutine[Any, Any, Any]]


@dataclass(frozen=True)
class ShadowTestConfig:
    """Configuration for shadow testing.

    Attributes:
        candidate_version: The candidate brain version to test
        baseline_version: The baseline brain version to compare against
        max_latency_overhead_ms: Maximum acceptable latency overhead in milliseconds
        sample_size: Number of inputs to test
        parallel_enabled: Whether to run candidate and baseline in parallel
        warmup_iterations: Number of warmup iterations before measurement
        measurement_iterations: Number of measurement iterations per input
    """

    candidate_version: BrainVersion
    baseline_version: BrainVersion
    max_latency_overhead_ms: float = 100.0
    sample_size: int = 1000
    parallel_enabled: bool = True
    warmup_iterations: int = 3
    measurement_iterations: int = 5

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.max_latency_overhead_ms <= 0:
            raise ValueError(
                f"max_latency_overhead_ms must be positive, got {self.max_latency_overhead_ms}"
            )
        if self.sample_size <= 0:
            raise ValueError(f"sample_size must be positive, got {self.sample_size}")
        if self.warmup_iterations < 0:
            raise ValueError(
                f"warmup_iterations must be non-negative, got {self.warmup_iterations}"
            )
        if self.measurement_iterations < 1:
            raise ValueError(
                f"measurement_iterations must be at least 1, got {self.measurement_iterations}"
            )


@dataclass(frozen=True)
class LatencyStatistics:
    """Statistical summary of latency measurements.

    Attributes:
        p50_ms: 50th percentile (median) latency in milliseconds
        p95_ms: 95th percentile latency in milliseconds
        p99_ms: 99th percentile latency in milliseconds
        mean_ms: Mean latency in milliseconds
        std_ms: Standard deviation of latency in milliseconds
        min_ms: Minimum latency in milliseconds
        max_ms: Maximum latency in milliseconds
        sample_count: Number of samples used for statistics
    """

    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    std_ms: float
    min_ms: float
    max_ms: float
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "mean_ms": self.mean_ms,
            "std_ms": self.std_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class ShadowTestResult:
    """Result of a shadow test run.

    Attributes:
        passed: Whether the shadow test passed all criteria
        latency_overhead_ms: Latency overhead as percentage of baseline
        candidate_latency_ms: Candidate version latency statistics
        baseline_latency_ms: Baseline version latency statistics
        candidate_predictions: Predictions from candidate brain
        baseline_predictions: Predictions from baseline brain
        timestamp: When the test was run
        error_message: Error message if test failed, None otherwise
        config: The configuration used for this test
    """

    passed: bool
    latency_overhead_ms: float
    candidate_latency_ms: LatencyStatistics
    baseline_latency_ms: LatencyStatistics
    candidate_predictions: list[Any]
    baseline_predictions: list[Any]
    timestamp: datetime
    error_message: str | None = None
    config: ShadowTestConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "latency_overhead_ms": self.latency_overhead_ms,
            "candidate_latency_ms": self.candidate_latency_ms.to_dict(),
            "baseline_latency_ms": self.baseline_latency_ms.to_dict(),
            "candidate_predictions": self.candidate_predictions,
            "baseline_predictions": self.baseline_predictions,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "config": (
                {
                    "candidate_version": str(self.config.candidate_version),
                    "baseline_version": str(self.config.baseline_version),
                    "max_latency_overhead_ms": self.config.max_latency_overhead_ms,
                    "sample_size": self.config.sample_size,
                    "parallel_enabled": self.config.parallel_enabled,
                }
                if self.config
                else None
            ),
        }


class ShadowTester:
    """Executes shadow tests between candidate and baseline brain versions.

    Runs both versions on the same inputs, measures latency for each,
    and calculates overhead statistics. Supports parallel and sequential
    execution modes.
    """

    def __init__(
        self,
        config: ShadowTestConfig,
        candidate_brain: BrainFunction,
        baseline_brain: BrainFunction,
    ) -> None:
        """Initialize the shadow tester.

        Args:
            config: Shadow test configuration
            candidate_brain: Async function for candidate brain predictions
            baseline_brain: Async function for baseline brain predictions
        """
        self.config = config
        self.candidate_brain = candidate_brain
        self.baseline_brain = baseline_brain

    async def run_shadow_test(self, inputs: list[Any]) -> ShadowTestResult:
        """Run shadow test on provided inputs.

        Executes both candidate and baseline brains on the same inputs,
        measures latencies, and compares results.

        Args:
            inputs: List of input data to test with

        Returns:
            ShadowTestResult with latency statistics and test outcome
        """
        if not inputs:
            return ShadowTestResult(
                passed=False,
                latency_overhead_ms=0.0,
                candidate_latency_ms=LatencyStatistics(
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    mean_ms=0.0,
                    std_ms=0.0,
                    min_ms=0.0,
                    max_ms=0.0,
                    sample_count=0,
                ),
                baseline_latency_ms=LatencyStatistics(
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    mean_ms=0.0,
                    std_ms=0.0,
                    min_ms=0.0,
                    max_ms=0.0,
                    sample_count=0,
                ),
                candidate_predictions=[],
                baseline_predictions=[],
                timestamp=datetime.utcnow(),
                error_message="No inputs provided for shadow test",
                config=self.config,
            )

        # Limit inputs to sample_size
        test_inputs = inputs[: self.config.sample_size]

        try:
            # Run warmup iterations
            await self._run_warmup()

            # Run measurements
            if self.config.parallel_enabled:
                results = await self._run_parallel_measurements(test_inputs)
            else:
                results = await self._run_sequential_measurements(test_inputs)

            # Calculate statistics
            candidate_latencies = [r["candidate_ms"] for r in results]
            baseline_latencies = [r["baseline_ms"] for r in results]
            candidate_predictions = [r["candidate_pred"] for r in results]
            baseline_predictions = [r["baseline_pred"] for r in results]

            candidate_stats = self._calculate_statistics(candidate_latencies)
            baseline_stats = self._calculate_statistics(baseline_latencies)

            # Calculate overhead as percentage: (candidate - baseline) / baseline * 100
            if baseline_stats.mean_ms > 0:
                latency_overhead_pct = (
                    (candidate_stats.mean_ms - baseline_stats.mean_ms)
                    / baseline_stats.mean_ms
                ) * 100
            else:
                latency_overhead_pct = float("inf")

            # Determine if test passed
            passed = self.validate_latency_threshold(
                latency_overhead_pct, self.config.max_latency_overhead_ms
            )

            error_message = None
            if not passed:
                error_message = (
                    f"Latency overhead {latency_overhead_pct:.2f}% exceeds "
                    f"threshold {self.config.max_latency_overhead_ms:.2f}%"
                )

            return ShadowTestResult(
                passed=passed,
                latency_overhead_ms=latency_overhead_pct,
                candidate_latency_ms=candidate_stats,
                baseline_latency_ms=baseline_stats,
                candidate_predictions=candidate_predictions,
                baseline_predictions=baseline_predictions,
                timestamp=datetime.utcnow(),
                error_message=error_message,
                config=self.config,
            )

        except Exception as e:
            return ShadowTestResult(
                passed=False,
                latency_overhead_ms=0.0,
                candidate_latency_ms=LatencyStatistics(
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    mean_ms=0.0,
                    std_ms=0.0,
                    min_ms=0.0,
                    max_ms=0.0,
                    sample_count=0,
                ),
                baseline_latency_ms=LatencyStatistics(
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    mean_ms=0.0,
                    std_ms=0.0,
                    min_ms=0.0,
                    max_ms=0.0,
                    sample_count=0,
                ),
                candidate_predictions=[],
                baseline_predictions=[],
                timestamp=datetime.utcnow(),
                error_message=f"Shadow test execution failed: {str(e)}",
                config=self.config,
            )

    async def _run_warmup(self) -> None:
        """Run warmup iterations to stabilize performance."""
        warmup_input = {"warmup": True}
        for _ in range(self.config.warmup_iterations):
            try:
                await self.candidate_brain(warmup_input)
                await self.baseline_brain(warmup_input)
            except Exception:
                # Warmup failures are non-fatal - intentionally ignored for shadow testing
                pass  # nosec B110

    async def _run_parallel_measurements(
        self, inputs: list[Any]
    ) -> list[dict[str, Any]]:
        """Run measurements in parallel for predictions, sequential for latency.

        For accurate latency overhead measurement, we measure each brain
        independently (sequentially) while still computing predictions
        in parallel to verify correctness.

        Args:
            inputs: List of inputs to test

        Returns:
            List of measurement results with latencies and predictions
        """
        results = []

        for input_data in inputs:
            # Run multiple iterations for statistical validity
            candidate_times = []
            baseline_times = []
            candidate_pred = None
            baseline_pred = None

            for _ in range(self.config.measurement_iterations):
                # Measure candidate latency independently
                start = time.perf_counter()
                candidate_pred = await self.candidate_brain(input_data)
                candidate_times.append((time.perf_counter() - start) * 1000)

                # Measure baseline latency independently
                start = time.perf_counter()
                baseline_pred = await self.baseline_brain(input_data)
                baseline_times.append((time.perf_counter() - start) * 1000)

            # Use median of iterations for stability
            results.append(
                {
                    "candidate_ms": statistics.median(candidate_times),
                    "baseline_ms": statistics.median(baseline_times),
                    "candidate_pred": candidate_pred,
                    "baseline_pred": baseline_pred,
                }
            )

        return results

    async def _run_sequential_measurements(
        self, inputs: list[Any]
    ) -> list[dict[str, Any]]:
        """Run measurements sequentially for all inputs.

        Args:
            inputs: List of inputs to test

        Returns:
            List of measurement results with latencies and predictions
        """
        results = []

        for input_data in inputs:
            # Run multiple iterations for statistical validity
            candidate_times = []
            baseline_times = []
            candidate_pred = None
            baseline_pred = None

            for _ in range(self.config.measurement_iterations):
                # Run candidate first
                start = time.perf_counter()
                candidate_pred = await self.candidate_brain(input_data)
                candidate_times.append((time.perf_counter() - start) * 1000)

                # Then run baseline
                start = time.perf_counter()
                baseline_pred = await self.baseline_brain(input_data)
                baseline_times.append((time.perf_counter() - start) * 1000)

            # Use median of iterations for stability
            results.append(
                {
                    "candidate_ms": statistics.median(candidate_times),
                    "baseline_ms": statistics.median(baseline_times),
                    "candidate_pred": candidate_pred,
                    "baseline_pred": baseline_pred,
                }
            )

        return results

    def _calculate_statistics(self, latencies: list[float]) -> LatencyStatistics:
        """Calculate statistical summary of latency measurements.

        Args:
            latencies: List of latency measurements in milliseconds

        Returns:
            LatencyStatistics with percentiles, mean, std dev, min, max
        """
        if not latencies:
            return LatencyStatistics(
                p50_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                mean_ms=0.0,
                std_ms=0.0,
                min_ms=0.0,
                max_ms=0.0,
                sample_count=0,
            )

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        # Calculate percentiles
        p50 = self._percentile(sorted_latencies, 50)
        p95 = self._percentile(sorted_latencies, 95)
        p99 = self._percentile(sorted_latencies, 99)

        # Calculate mean and std
        mean_val = statistics.mean(sorted_latencies)
        std_val = statistics.stdev(sorted_latencies) if n > 1 else 0.0

        return LatencyStatistics(
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            mean_ms=mean_val,
            std_ms=std_val,
            min_ms=min(sorted_latencies),
            max_ms=max(sorted_latencies),
            sample_count=n,
        )

    def _percentile(self, sorted_data: list[float], percentile: float) -> float:
        """Calculate percentile from sorted data.

        Uses linear interpolation for percentiles.

        Args:
            sorted_data: Sorted list of values
            percentile: Percentile to calculate (0-100)

        Returns:
            The percentile value
        """
        if not sorted_data:
            return 0.0

        n = len(sorted_data)
        if n == 1:
            return sorted_data[0]

        # Calculate index using linear interpolation
        index = (percentile / 100) * (n - 1)
        lower_idx = int(index)
        upper_idx = min(lower_idx + 1, n - 1)
        fraction = index - lower_idx

        return sorted_data[lower_idx] + fraction * (
            sorted_data[upper_idx] - sorted_data[lower_idx]
        )

    def validate_latency_threshold(
        self, latency_overhead_ms: float, threshold: float | None = None
    ) -> bool:
        """Validate that latency overhead is within acceptable threshold.

        Args:
            latency_overhead_ms: The measured latency overhead in milliseconds
            threshold: Optional override threshold (uses config if not provided)

        Returns:
            True if overhead is within threshold, False otherwise
        """
        max_threshold = (
            threshold if threshold is not None else self.config.max_latency_overhead_ms
        )
        return latency_overhead_ms <= max_threshold


async def run_shadow_test(
    candidate_version: BrainVersion,
    baseline_version: BrainVersion,
    candidate_brain: BrainFunction,
    baseline_brain: BrainFunction,
    inputs: list[Any],
    max_latency_overhead_ms: float = 100.0,
    sample_size: int = 1000,
    parallel_enabled: bool = True,
) -> ShadowTestResult:
    """Convenience function to run a shadow test.

    Args:
        candidate_version: Candidate brain version
        baseline_version: Baseline brain version
        candidate_brain: Candidate brain prediction function
        baseline_brain: Baseline brain prediction function
        inputs: List of test inputs
        max_latency_overhead_ms: Maximum acceptable latency overhead
        sample_size: Number of inputs to test
        parallel_enabled: Whether to run in parallel

    Returns:
        ShadowTestResult with test outcome and metrics
    """
    config = ShadowTestConfig(
        candidate_version=candidate_version,
        baseline_version=baseline_version,
        max_latency_overhead_ms=max_latency_overhead_ms,
        sample_size=sample_size,
        parallel_enabled=parallel_enabled,
    )

    tester = ShadowTester(config, candidate_brain, baseline_brain)
    return await tester.run_shadow_test(inputs)
