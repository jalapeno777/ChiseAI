"""Brain shadow testing module.

Provides shadow testing capabilities to run new brain versions in parallel
with the live brain, comparing outputs and tracking latency overhead.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from collections.abc import Sequence


logger = logging.getLogger(__name__)


class ShadowTestStatus(Enum):
    """Status of a shadow test run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class LatencyMetrics:
    """Latency metrics for shadow testing.

    Attributes:
        live_latency_ms: Latency of the live brain in milliseconds
        shadow_latency_ms: Latency of the shadow brain in milliseconds
        overhead_ms: Additional latency introduced by shadow testing
        overhead_percentage: Overhead as percentage of live latency
    """

    live_latency_ms: float = 0.0
    shadow_latency_ms: float = 0.0
    overhead_ms: float = 0.0
    overhead_percentage: float = 0.0

    def __post_init__(self) -> None:
        """Calculate overhead metrics."""
        self.overhead_ms = max(0.0, self.shadow_latency_ms - self.live_latency_ms)
        if self.live_latency_ms > 0:
            self.overhead_percentage = (self.overhead_ms / self.live_latency_ms) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "live_latency_ms": self.live_latency_ms,
            "shadow_latency_ms": self.shadow_latency_ms,
            "overhead_ms": self.overhead_ms,
            "overhead_percentage": self.overhead_percentage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LatencyMetrics:
        """Create from dictionary."""
        return cls(
            live_latency_ms=data.get("live_latency_ms", 0.0),
            shadow_latency_ms=data.get("shadow_latency_ms", 0.0),
            overhead_ms=data.get("overhead_ms", 0.0),
            overhead_percentage=data.get("overhead_percentage", 0.0),
        )


@dataclass
class OutputComparison:
    """Comparison between live and shadow brain outputs.

    Attributes:
        input_id: Identifier for the input that was processed
        live_output: Output from the live brain
        shadow_output: Output from the shadow brain
        match: Whether outputs match (within tolerance)
        similarity_score: Similarity score between outputs (0.0 to 1.0)
        differences: List of specific differences found
    """

    input_id: str
    live_output: Any
    shadow_output: Any
    match: bool = False
    similarity_score: float = 0.0
    differences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "input_id": self.input_id,
            "live_output": self.live_output,
            "shadow_output": self.shadow_output,
            "match": self.match,
            "similarity_score": self.similarity_score,
            "differences": self.differences,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutputComparison:
        """Create from dictionary."""
        return cls(
            input_id=data["input_id"],
            live_output=data.get("live_output"),
            shadow_output=data.get("shadow_output"),
            match=data.get("match", False),
            similarity_score=data.get("similarity_score", 0.0),
            differences=data.get("differences", []),
        )


@dataclass
class ShadowTestResult:
    """Result of a shadow test run.

    Attributes:
        shadow_version: The shadow brain version being tested
        live_version: The live brain version (baseline)
        status: Test status
        started_at: ISO timestamp when test started
        completed_at: ISO timestamp when test completed
        total_requests: Total number of requests processed
        comparisons: List of output comparisons
        latency: Latency metrics
        match_rate: Percentage of outputs that match
        avg_similarity: Average similarity score
        error_message: Error message if test failed
        metadata: Additional metadata
    """

    shadow_version: str
    live_version: str
    status: ShadowTestStatus
    started_at: str
    completed_at: str | None = None
    total_requests: int = 0
    comparisons: list[OutputComparison] = field(default_factory=list)
    latency: LatencyMetrics = field(default_factory=LatencyMetrics)
    match_rate: float = 0.0
    avg_similarity: float = 0.0
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure status is ShadowTestStatus enum."""
        if isinstance(self.status, str):
            self.status = ShadowTestStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "shadow_version": self.shadow_version,
            "live_version": self.live_version,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_requests": self.total_requests,
            "comparisons": [c.to_dict() for c in self.comparisons],
            "latency": self.latency.to_dict(),
            "match_rate": self.match_rate,
            "avg_similarity": self.avg_similarity,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShadowTestResult:
        """Create from dictionary."""
        return cls(
            shadow_version=data["shadow_version"],
            live_version=data["live_version"],
            status=ShadowTestStatus(data["status"]),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            total_requests=data.get("total_requests", 0),
            comparisons=[
                OutputComparison.from_dict(c) for c in data.get("comparisons", [])
            ],
            latency=LatencyMetrics.from_dict(data.get("latency", {})),
            match_rate=data.get("match_rate", 0.0),
            avg_similarity=data.get("avg_similarity", 0.0),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


class ShadowTestError(Exception):
    """Base exception for shadow testing errors."""

    pass


class ShadowTester:
    """Runs shadow tests comparing live and shadow brain versions.

    Shadow testing runs the new (shadow) brain version in parallel with the
    live brain, comparing outputs and measuring latency overhead.

    Attributes:
        redis_client: Optional Redis client for result storage
        max_overhead_ms: Maximum acceptable latency overhead (default: 100ms)
        similarity_threshold: Minimum similarity score for outputs to match

    Examples:
        >>> tester = ShadowTester(max_overhead_ms=100)
        >>> result = tester.run_shadow_test(
        ...     shadow_version="1.1.0",
        ...     live_version="1.0.0",
        ...     test_inputs=[...]
        ... )
        >>> print(result.latency.overhead_ms)
        45.2
    """

    DEFAULT_MAX_OVERHEAD_MS = 100.0  # AC: <100ms latency overhead
    DEFAULT_SIMILARITY_THRESHOLD = 0.95
    DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        redis_client: Any | None = None,
        max_overhead_ms: float = DEFAULT_MAX_OVERHEAD_MS,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the shadow tester.

        Args:
            redis_client: Optional Redis client for result storage
            max_overhead_ms: Maximum acceptable latency overhead in milliseconds
            similarity_threshold: Minimum similarity score for outputs to match
            timeout_seconds: Maximum test duration before timeout
        """
        self.redis_client = redis_client
        self.max_overhead_ms = max_overhead_ms
        self.similarity_threshold = similarity_threshold
        self.timeout_seconds = timeout_seconds
        self._test_in_progress: dict[str, ShadowTestResult] = {}

    def run_shadow_test(
        self,
        shadow_version: str,
        live_version: str,
        test_inputs: Sequence[dict[str, Any]],
        live_brain_fn: Callable[[dict[str, Any]], Any] | None = None,
        shadow_brain_fn: Callable[[dict[str, Any]], Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ShadowTestResult:
        """Run a shadow test comparing live and shadow brain versions.

        Args:
            shadow_version: The shadow brain version to test
            live_version: The live brain version (baseline)
            test_inputs: Input data to process
            live_brain_fn: Function to call live brain (for testing)
            shadow_brain_fn: Function to call shadow brain (for testing)
            metadata: Additional metadata for the test

        Returns:
            ShadowTestResult with comparisons and latency metrics
        """
        started_at = datetime.now(timezone.utc).isoformat()

        result = ShadowTestResult(
            shadow_version=shadow_version,
            live_version=live_version,
            status=ShadowTestStatus.RUNNING,
            started_at=started_at,
            metadata=metadata or {},
        )
        self._test_in_progress[shadow_version] = result

        try:
            comparisons = []
            total_live_latency = 0.0
            total_shadow_latency = 0.0

            for i, test_input in enumerate(test_inputs):
                # Check timeout
                elapsed = (
                    time.time()
                    - datetime.fromisoformat(
                        started_at.replace("Z", "+00:00")
                    ).timestamp()
                )
                if elapsed > self.timeout_seconds:
                    result.status = ShadowTestStatus.TIMEOUT
                    result.error_message = (
                        f"Test timed out after {self.timeout_seconds}s"
                    )
                    break

                # Run live brain and measure latency
                live_start = time.perf_counter()
                live_output = self._call_brain(live_brain_fn, test_input, f"live_{i}")
                live_latency = (time.perf_counter() - live_start) * 1000

                # Run shadow brain and measure latency
                shadow_start = time.perf_counter()
                shadow_output = self._call_brain(
                    shadow_brain_fn, test_input, f"shadow_{i}"
                )
                shadow_latency = (time.perf_counter() - shadow_start) * 1000

                # Compare outputs
                comparison = self._compare_outputs(
                    input_id=f"input_{i}",
                    live_output=live_output,
                    shadow_output=shadow_output,
                )
                comparisons.append(comparison)

                total_live_latency += live_latency
                total_shadow_latency += shadow_latency

            # Calculate metrics
            if comparisons:
                result.total_requests = len(comparisons)
                result.comparisons = comparisons
                result.match_rate = sum(1 for c in comparisons if c.match) / len(
                    comparisons
                )
                result.avg_similarity = sum(
                    c.similarity_score for c in comparisons
                ) / len(comparisons)

                # Calculate latency metrics
                avg_live_latency = total_live_latency / len(comparisons)
                avg_shadow_latency = total_shadow_latency / len(comparisons)
                result.latency = LatencyMetrics(
                    live_latency_ms=avg_live_latency,
                    shadow_latency_ms=avg_shadow_latency,
                )

            if result.status != ShadowTestStatus.TIMEOUT:
                result.status = ShadowTestStatus.COMPLETED

        except Exception as e:
            logger.exception(f"Shadow test failed for version {shadow_version}")
            result.status = ShadowTestStatus.ERROR
            result.error_message = str(e)

        finally:
            # Complete test
            result.completed_at = datetime.now(timezone.utc).isoformat()
            if shadow_version in self._test_in_progress:
                del self._test_in_progress[shadow_version]

            # Store results
            self._store_result(result)

        return result

    def _call_brain(
        self,
        brain_fn: Callable[[dict[str, Any]], Any] | None,
        input_data: dict[str, Any],
        default_output: str,
    ) -> Any:
        """Call a brain function or return default.

        In production, this would call the actual brain inference.
        For testing, it can use provided mock functions.
        """
        if brain_fn:
            return brain_fn(input_data)

        # Simulate brain processing with small delay
        time.sleep(0.001)  # 1ms simulated processing
        return {"prediction": default_output, "confidence": 0.95}

    def _compare_outputs(
        self,
        input_id: str,
        live_output: Any,
        shadow_output: Any,
    ) -> OutputComparison:
        """Compare live and shadow outputs.

        Args:
            input_id: Identifier for the input
            live_output: Output from live brain
            shadow_output: Output from shadow brain

        Returns:
            OutputComparison with match status and differences
        """
        differences = []
        similarity = 1.0

        # Simple comparison for demonstration
        # In production, this would use domain-specific comparison logic
        if live_output != shadow_output:
            differences.append(f"Outputs differ: {live_output} vs {shadow_output}")
            similarity = 0.8  # Placeholder similarity

        match = similarity >= self.similarity_threshold

        return OutputComparison(
            input_id=input_id,
            live_output=live_output,
            shadow_output=shadow_output,
            match=match,
            similarity_score=similarity,
            differences=differences,
        )

    def _store_result(self, result: ShadowTestResult) -> None:
        """Store shadow test result in Redis."""
        if self.redis_client:
            try:
                key = f"brain:shadow_test:{result.shadow_version}"
                self.redis_client.set(
                    key,
                    json.dumps(result.to_dict()),
                    ex=86400 * 30,  # 30 days TTL
                )
                logger.info(f"Stored shadow test result in Redis: {key}")
            except Exception as e:
                logger.error(f"Failed to store shadow test result: {e}")

    def get_shadow_test_result(self, version: str) -> ShadowTestResult | None:
        """Get the shadow test result for a version.

        Args:
            version: Shadow brain version

        Returns:
            ShadowTestResult if found, None otherwise
        """
        if self.redis_client:
            try:
                key = f"brain:shadow_test:{version}"
                data = self.redis_client.get(key)
                if data:
                    return ShadowTestResult.from_dict(json.loads(data))
            except Exception as e:
                logger.error(f"Failed to retrieve shadow test result: {e}")

        return None

    def is_latency_acceptable(self, version: str) -> bool:
        """Check if a version meets latency requirements.

        Args:
            version: Brain version

        Returns:
            True if latency overhead is within acceptable limits
        """
        result = self.get_shadow_test_result(version)
        if result is None:
            return False

        return result.latency.overhead_ms <= self.max_overhead_ms

    def is_output_compatible(self, version: str) -> bool:
        """Check if a version produces compatible outputs.

        Args:
            version: Brain version

        Returns:
            True if outputs are compatible with live version
        """
        result = self.get_shadow_test_result(version)
        if result is None:
            return False

        return result.match_rate >= 0.95  # 95% match rate threshold

    def list_shadow_tests(self, limit: int = 100) -> list[ShadowTestResult]:
        """List recent shadow test results.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of ShadowTestResult objects
        """
        if not self.redis_client:
            return []

        try:
            results = []
            cursor = 0
            pattern = "brain:shadow_test:*"

            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        results.append(ShadowTestResult.from_dict(json.loads(data)))

                if cursor == 0 or len(results) >= limit:
                    break

            # Sort by started_at descending and limit
            results.sort(key=lambda r: r.started_at, reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Failed to list shadow tests: {e}")
            return []
