"""A/B testing framework core with configurable traffic splitting.

Implements deterministic champion/challenger assignment using user_id hashing,
configurable traffic split percentages, and full test lifecycle management
(create, start, pause, stop).

Traffic Splitting Algorithm:
    - Uses SHA-256 hash of f"{test_id}:{user_id}" for deterministic assignment
    - Same user always receives the same variant within a test
    - Configurable split percentage (0.01-0.99) controls challenger traffic
    - Assignment is independent across different tests
"""

from __future__ import annotations

import contextlib
import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ABTestStatus(str, Enum):
    """Lifecycle statuses for an A/B test."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


class WinnerSelectionStrategy(str, Enum):
    """Strategy for selecting a winner in an A/B test."""

    STATISTICAL_SIGNIFICANCE = "statistical_significance"
    BAYESIAN_PROBABILITY = "bayesian_probability"
    EARLY_STOPPING = "early_stopping"


@dataclass
class ABTestConfig:
    """Configuration for an A/B test.

    Attributes:
        test_id: Unique identifier for this A/B test.
        test_name: Human-readable name for the test.
        traffic_split: Fraction of traffic routed to challenger (0.01-0.99).
        confidence_level: Required confidence for winner selection (0-1).
        min_sample_size: Minimum observations before test can be evaluated (>=100).
        auto_rollback_enabled: Whether to auto-rollback on poor performance.
        rollback_threshold: Negative threshold for rollback trigger.
        winner_selection_strategy: Strategy for selecting the winner.
    """

    test_id: str
    test_name: str
    traffic_split: float = 0.5
    confidence_level: float = 0.95
    min_sample_size: int = 1000
    auto_rollback_enabled: bool = True
    rollback_threshold: float = -0.1
    winner_selection_strategy: WinnerSelectionStrategy = (
        WinnerSelectionStrategy.STATISTICAL_SIGNIFICANCE
    )

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if not 0.01 <= self.traffic_split <= 0.99:
            raise ValueError("Traffic split must be between 0.01 and 0.99")
        if not 0 <= self.confidence_level <= 1:
            raise ValueError("Confidence level must be between 0 and 1")
        if self.min_sample_size < 100:
            raise ValueError("Minimum sample size should be at least 100")
        if self.rollback_threshold >= 0:
            raise ValueError("Rollback threshold should be negative")


@dataclass
class ABTestResult:
    """Result of an A/B test.

    Attributes:
        test_id: Identifier of the test.
        status: Current status of the test.
        winner: Winning variant name, or None if not decided.
        statistical_result: Statistical analysis result, if available.
        champion_metrics: Metrics collected for the champion variant.
        challenger_metrics: Metrics collected for the challenger variant.
        duration_seconds: Total duration of the test.
        start_time: Timestamp when the test started.
        end_time: Timestamp when the test ended, or None if still running.
        decision_reason: Human-readable reason for the test outcome.
    """

    test_id: str
    status: ABTestStatus
    winner: str | None
    statistical_result: Any | None
    champion_metrics: dict
    challenger_metrics: dict
    duration_seconds: float
    start_time: float
    end_time: float | None
    decision_reason: str

    def to_dict(self) -> dict:
        """Convert the result to a dictionary."""
        return {
            "test_id": self.test_id,
            "status": self.status.value,
            "winner": self.winner,
            "statistical_result": self.statistical_result,
            "champion_metrics": self.champion_metrics,
            "challenger_metrics": self.challenger_metrics,
            "duration_seconds": self.duration_seconds,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "decision_reason": self.decision_reason,
        }


@dataclass
class _MetricEntry:
    """A single metric data point."""

    value: float
    metadata: dict = field(default_factory=dict)


class _MetricsCollector:
    """Collects metrics for A/B test variants.

    Stores metrics keyed by (variant, metric_name) pairs.
    Each metric entry has a value and optional metadata.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, dict[str, list[_MetricEntry]]] = {}
        self._lock = threading.Lock()

    def add_metric(self, variant: str, metric_name: str, value: Any) -> None:
        """Add a metric entry for a variant."""
        with self._lock:
            if variant not in self._metrics:
                self._metrics[variant] = {}
            if metric_name not in self._metrics[variant]:
                self._metrics[variant][metric_name] = []
            # Coerce to float if possible, store raw otherwise
            try:
                float_val = float(value)
            except (TypeError, ValueError):
                float_val = 0.0
            self._metrics[variant][metric_name].append(_MetricEntry(value=float_val))

    def add_metric_with_metadata(
        self, variant: str, metric_name: str, value: float, metadata: dict
    ) -> None:
        """Add a metric entry with metadata for a variant."""
        with self._lock:
            if variant not in self._metrics:
                self._metrics[variant] = {}
            if metric_name not in self._metrics[variant]:
                self._metrics[variant][metric_name] = []
            self._metrics[variant][metric_name].append(
                _MetricEntry(value=value, metadata=metadata)
            )

    def get_metrics(self, variant: str, metric_name: str) -> list[_MetricEntry]:
        """Get all metric entries for a variant and metric name."""
        with self._lock:
            return list(self._metrics.get(variant, {}).get(metric_name, []))


class ABTestFramework:
    """Manages A/B tests with deterministic traffic splitting.

    Provides the full lifecycle for champion/challenger A/B tests:
    creation, traffic assignment, starting, pausing, and stopping.
    All traffic assignments are deterministic based on user_id hashing
    to ensure consistent user experience.
    """

    def __init__(self) -> None:
        """Initialize the framework with empty registries."""
        self._tests: dict[str, ABTestConfig] = {}
        self._test_results: dict[str, ABTestResult] = {}
        self._active_tests: dict[str, dict[str, Any]] = {}
        self._monitoring: bool = False
        self._winner_callbacks: list[Callable] = []
        self._rollback_callbacks: list[Callable] = []
        self.metrics_collector = _MetricsCollector()
        self._lock = threading.Lock()

    def create_test(self, config: ABTestConfig) -> str:
        """Create and register a new A/B test.

        Args:
            config: Validated ABTestConfig with all test parameters.

        Returns:
            The test_id of the created test.

        Raises:
            ValueError: If a test with the same test_id already exists.
        """
        with self._lock:
            if config.test_id in self._tests:
                raise ValueError(f"Test {config.test_id} already exists")
            self._tests[config.test_id] = config
            self._test_results[config.test_id] = ABTestResult(
                test_id=config.test_id,
                status=ABTestStatus.DRAFT,
                winner=None,
                statistical_result=None,
                champion_metrics={},
                challenger_metrics={},
                duration_seconds=0,
                start_time=0,
                end_time=None,
                decision_reason="",
            )
        return config.test_id

    def start_test(self, test_id: str) -> bool:
        """Start an A/B test.

        Args:
            test_id: Identifier of the test to start.

        Returns:
            True if the test was started, False if already running.

        Raises:
            ValueError: If the test does not exist.
        """
        with self._lock:
            if test_id not in self._tests:
                raise ValueError(f"Test {test_id} does not exist")
            if test_id in self._active_tests:
                return False
            self._active_tests[test_id] = {"started_at": time.time()}
            self._test_results[test_id].status = ABTestStatus.RUNNING
            self._test_results[test_id].start_time = time.time()
            self._monitoring = True
        return True

    def pause_test(self, test_id: str) -> bool:
        """Pause an active A/B test.

        Args:
            test_id: Identifier of the test to pause.

        Returns:
            True if paused, False if not currently active.
        """
        with self._lock:
            if test_id not in self._active_tests:
                return False
            del self._active_tests[test_id]
            self._test_results[test_id].status = ABTestStatus.PAUSED
        return True

    def stop_test(
        self, test_id: str, winner: str | None = None, reason: str | None = None
    ) -> ABTestResult:
        """Stop an A/B test and record the result.

        Args:
            test_id: Identifier of the test to stop.
            winner: The winning variant, if known.
            reason: Human-readable reason for stopping.

        Returns:
            The final ABTestResult.

        Raises:
            ValueError: If the test does not exist.
        """
        with self._lock:
            if test_id not in self._tests:
                raise ValueError(f"Test {test_id} does not exist")

            result = self._test_results[test_id]
            result.status = ABTestStatus.COMPLETED
            result.winner = winner
            result.end_time = time.time()
            result.duration_seconds = result.end_time - result.start_time
            result.decision_reason = reason or ""

            # Compute champion metrics
            champion_conversions = self.metrics_collector.get_metrics(
                "champion", "conversions"
            )
            champion_visitors = self.metrics_collector.get_metrics(
                "champion", "visitors"
            )
            if champion_visitors and champion_conversions:
                result.champion_metrics["conversion_rate"] = len(
                    champion_conversions
                ) / len(champion_visitors)
            else:
                result.champion_metrics["conversion_rate"] = 0.0

            # Compute challenger metrics
            challenger_conversions = self.metrics_collector.get_metrics(
                "challenger", "conversions"
            )
            challenger_visitors = self.metrics_collector.get_metrics(
                "challenger", "visitors"
            )
            if challenger_visitors and challenger_conversions:
                result.challenger_metrics["conversion_rate"] = len(
                    challenger_conversions
                ) / len(challenger_visitors)
            else:
                result.challenger_metrics["conversion_rate"] = 0.0

            if test_id in self._active_tests:
                del self._active_tests[test_id]

        return result

    def assign_variant(self, test_id: str, user_id: str) -> str:
        """Assign a variant to a user for a given test.

        Uses SHA-256 hash of the composite key for deterministic assignment.

        Args:
            test_id: Identifier of the A/B test.
            user_id: Identifier of the user.

        Returns:
            'champion' or 'challenger'. Returns 'champion' if test not running.
        """
        with self._lock:
            if test_id not in self._active_tests:
                return "champion"

        config = self._tests[test_id]
        composite_key = f"{test_id}:{user_id}"
        hash_digest = hashlib.sha256(composite_key.encode("utf-8")).hexdigest()
        bucket = int(hash_digest, 16) % 100

        if bucket < int(config.traffic_split * 100):
            return "challenger"
        return "champion"

    def record_visitor(self, test_id: str, variant: str, user_id: str) -> None:
        """Record a visitor for a variant.

        Args:
            test_id: Identifier of the test.
            variant: 'champion' or 'challenger'.
            user_id: Identifier of the visitor.
        """
        self.metrics_collector.add_metric_with_metadata(
            variant,
            "visitors",
            1.0,
            {"visitor_id": f"{test_id}:{user_id}"},
        )

    def record_conversion(
        self, test_id: str, variant: str, user_id: str, value: float
    ) -> None:
        """Record a conversion for a variant.

        Args:
            test_id: Identifier of the test.
            variant: 'champion' or 'challenger'.
            user_id: Identifier of the user.
            value: Conversion value.
        """
        self.metrics_collector.add_metric_with_metadata(
            variant,
            "conversions",
            value,
            {"visitor_id": f"{test_id}:{user_id}"},
        )

    def record_performance(
        self,
        test_id: str,
        variant: str,
        request_id: str,
        latency: float,
        success: bool,
    ) -> None:
        """Record performance metrics for a request.

        Args:
            test_id: Identifier of the test.
            variant: 'champion' or 'challenger'.
            request_id: Identifier of the request.
            latency: Request latency in seconds.
            success: Whether the request was successful.
        """
        self.metrics_collector.add_metric(variant, "latency", latency)
        self.metrics_collector.add_metric(variant, "requests", 1.0)

    def get_test_status(self, test_id: str) -> ABTestResult | None:
        """Get the current status of a test.

        Args:
            test_id: Identifier of the test.

        Returns:
            The ABTestResult, or None if the test does not exist.
        """
        return self._test_results.get(test_id)

    def get_all_test_statuses(self) -> dict[str, ABTestResult]:
        """Get statuses of all tests.

        Returns:
            Dictionary mapping test_id to ABTestResult.
        """
        return dict(self._test_results)

    def add_winner_callback(self, callback: Callable) -> None:
        """Register a callback to be called when a winner is selected.

        Args:
            callback: Function that takes an ABTestResult.
        """
        self._winner_callbacks.append(callback)

    def add_rollback_callback(self, callback: Callable) -> None:
        """Register a callback to be called on rollback.

        Args:
            callback: Function that takes an ABTestResult.
        """
        self._rollback_callbacks.append(callback)

    def _notify_winner_callbacks(self, result: ABTestResult) -> None:
        """Notify all winner callbacks, catching individual errors."""
        for cb in self._winner_callbacks:
            with contextlib.suppress(Exception):
                cb(result)

    def _notify_rollback_callbacks(self, result: ABTestResult) -> None:
        """Notify all rollback callbacks, catching individual errors."""
        for cb in self._rollback_callbacks:
            with contextlib.suppress(Exception):
                cb(result)

    def _check_test_completion(self, test_id: str) -> None:
        """Check if a test should auto-complete based on metrics.

        Handles errors gracefully to avoid crashing the monitoring loop.
        """
        try:
            champion_rate = self.metrics_collector.get_metrics(
                "champion", "conversion_rate"
            )
            challenger_rate = self.metrics_collector.get_metrics(
                "challenger", "conversion_rate"
            )
            # Placeholder: actual completion logic would analyze metrics
            # For now, just ensure no crash on invalid data
            _ = champion_rate
            _ = challenger_rate
        except Exception:
            pass

    def shutdown(self) -> None:
        """Shut down the framework and stop monitoring."""
        self._monitoring = False
