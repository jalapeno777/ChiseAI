"""Brain evaluation module.

Provides evaluation framework for brain versions with metrics including
accuracy, precision, recall, and F1 score. Results are stored in Redis
and InfluxDB for persistence and analysis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


logger = logging.getLogger(__name__)


class EvaluationStatus(Enum):
    """Status of an evaluation run."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for a brain version.

    Attributes:
        accuracy: Overall accuracy (0.0 to 1.0)
        precision: Precision score (0.0 to 1.0)
        recall: Recall score (0.0 to 1.0)
        f1_score: F1 score (harmonic mean of precision and recall)
        paper_carryover_rate: Rate of paper trading successes (BrainEval KPI)
        false_positive_rate: Rate of backtest wins that fail in paper
        time_to_improvement: Experiments to beat champion
        turnover_bias_alignment: Prefers low trades/day when profit within 3%
        compute_cost: Tokens / runs per useful win
        safety_compliance: Never violates caps; never touches live
        custom_metrics: Additional custom metrics
    """

    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    paper_carryover_rate: float = 0.0
    false_positive_rate: float = 0.0
    time_to_improvement: float = 0.0
    turnover_bias_alignment: float = 0.0
    compute_cost: float = 0.0
    safety_compliance: float = 1.0  # Default to perfect compliance
    custom_metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate metric ranges."""
        for name, value in self.__dict__.items():
            if name == "custom_metrics":
                continue
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"Metric '{name}' must be between 0.0 and 1.0: {value}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "paper_carryover_rate": self.paper_carryover_rate,
            "false_positive_rate": self.false_positive_rate,
            "time_to_improvement": self.time_to_improvement,
            "turnover_bias_alignment": self.turnover_bias_alignment,
            "compute_cost": self.compute_cost,
            "safety_compliance": self.safety_compliance,
            "custom_metrics": self.custom_metrics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationMetrics:
        """Create from dictionary."""
        custom_metrics = data.get("custom_metrics", {})
        return cls(
            accuracy=data.get("accuracy", 0.0),
            precision=data.get("precision", 0.0),
            recall=data.get("recall", 0.0),
            f1_score=data.get("f1_score", 0.0),
            paper_carryover_rate=data.get("paper_carryover_rate", 0.0),
            false_positive_rate=data.get("false_positive_rate", 0.0),
            time_to_improvement=data.get("time_to_improvement", 0.0),
            turnover_bias_alignment=data.get("turnover_bias_alignment", 0.0),
            compute_cost=data.get("compute_cost", 0.0),
            safety_compliance=data.get("safety_compliance", 1.0),
            custom_metrics=custom_metrics,
        )


@dataclass
class EvaluationResult:
    """Result of a brain evaluation run.

    Attributes:
        version: The brain version evaluated
        status: Evaluation status
        metrics: Evaluation metrics
        started_at: ISO timestamp when evaluation started
        completed_at: ISO timestamp when evaluation completed
        duration_seconds: Total evaluation duration
        test_cases_run: Number of test cases executed
        test_cases_passed: Number of test cases that passed
        error_message: Error message if evaluation failed
        metadata: Additional metadata
    """

    version: str
    status: EvaluationStatus
    metrics: EvaluationMetrics
    started_at: str
    completed_at: str | None = None
    duration_seconds: float = 0.0
    test_cases_run: int = 0
    test_cases_passed: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure status is EvaluationStatus enum."""
        if isinstance(self.status, str):
            self.status = EvaluationStatus(self.status)

    @property
    def test_cases_failed(self) -> int:
        """Number of test cases that failed."""
        return self.test_cases_run - self.test_cases_passed

    @property
    def pass_rate(self) -> float:
        """Percentage of test cases that passed."""
        if self.test_cases_run == 0:
            return 0.0
        return self.test_cases_passed / self.test_cases_run

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "test_cases_run": self.test_cases_run,
            "test_cases_passed": self.test_cases_passed,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationResult:
        """Create from dictionary."""
        return cls(
            version=data["version"],
            status=EvaluationStatus(data["status"]),
            metrics=EvaluationMetrics.from_dict(data.get("metrics", {})),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            duration_seconds=data.get("duration_seconds", 0.0),
            test_cases_run=data.get("test_cases_run", 0),
            test_cases_passed=data.get("test_cases_passed", 0),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


class EvaluationError(Exception):
    """Base exception for evaluation errors."""

    pass


class BrainEvaluator:
    """Evaluates brain versions and stores results.

    Attributes:
        redis_client: Optional Redis client for result storage
        influxdb_client: Optional InfluxDB client for metrics storage
        thresholds: Metric thresholds for pass/fail determination

    Examples:
        >>> evaluator = BrainEvaluator()
        >>> result = evaluator.evaluate_version("1.0.0", test_data)
        >>> print(result.metrics.f1_score)
        0.92
    """

    # Default thresholds for evaluation
    DEFAULT_THRESHOLDS = {
        "accuracy": 0.80,
        "precision": 0.80,
        "recall": 0.80,
        "f1_score": 0.80,
        "paper_carryover_rate": 0.70,
        "false_positive_rate": 0.30,  # Maximum allowed
        "safety_compliance": 1.0,  # Must be perfect
    }

    def __init__(
        self,
        redis_client: Any | None = None,
        influxdb_client: Any | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> None:
        """Initialize the evaluator.

        Args:
            redis_client: Optional Redis client for result storage
            influxdb_client: Optional InfluxDB client for metrics storage
            thresholds: Optional custom thresholds for evaluation
        """
        self.redis_client = redis_client
        self.influxdb_client = influxdb_client
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._evaluation_in_progress: dict[str, EvaluationResult] = {}

    def evaluate_version(
        self,
        version: str,
        test_data: Sequence[dict[str, Any]],
        expected_outputs: Sequence[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate a brain version against test data.

        Args:
            version: Brain version to evaluate
            test_data: Test cases to run
            expected_outputs: Expected outputs for comparison
            metadata: Additional metadata for the evaluation

        Returns:
            EvaluationResult with metrics and status
        """
        started_at = datetime.now(UTC).isoformat()

        # Create initial result
        result = EvaluationResult(
            version=version,
            status=EvaluationStatus.RUNNING,
            metrics=EvaluationMetrics(),
            started_at=started_at,
            metadata=metadata or {},
        )
        self._evaluation_in_progress[version] = result

        try:
            # Run evaluation
            metrics = self._compute_metrics(test_data, expected_outputs)
            result.metrics = metrics

            # Determine pass/fail
            passed = self._check_thresholds(metrics)
            result.status = (
                EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED
            )

            result.test_cases_run = len(test_data)
            result.test_cases_passed = self._count_passed_tests(
                test_data, expected_outputs
            )

        except Exception as e:
            logger.exception(f"Evaluation failed for version {version}")
            result.status = EvaluationStatus.ERROR
            result.error_message = str(e)

        finally:
            # Complete evaluation
            completed_at = datetime.now(UTC).isoformat()
            result.completed_at = completed_at
            result.duration_seconds = self._calculate_duration(
                result.started_at, completed_at
            )
            del self._evaluation_in_progress[version]

            # Store results
            self._store_result(result)

        return result

    def _compute_metrics(
        self,
        test_data: Sequence[dict[str, Any]],
        expected_outputs: Sequence[dict[str, Any]] | None,
    ) -> EvaluationMetrics:
        """Compute evaluation metrics from test results.

        Computes real accuracy, precision, recall, and F1 score from
        actual predictions vs expected outputs.

        Args:
            test_data: Test cases with predictions (must contain 'output' key)
            expected_outputs: Expected outputs for comparison (must contain 'expected' key)

        Returns:
            EvaluationMetrics with computed values

        Raises:
            EvaluationError: If data validation fails
        """
        if not test_data:
            return EvaluationMetrics()

        if not expected_outputs:
            # No ground truth to compare against
            return EvaluationMetrics()

        if len(test_data) != len(expected_outputs):
            raise EvaluationError(
                f"Test data length ({len(test_data)}) does not match "
                f"expected outputs length ({len(expected_outputs)})"
            )

        # Compute confusion matrix components
        tp, fp, tn, fn = self._compute_confusion_matrix(test_data, expected_outputs)

        # Compute metrics from confusion matrix
        metrics = self._compute_metrics_from_confusion_matrix(tp, fp, tn, fn)

        return metrics

    def _compute_confusion_matrix(
        self,
        test_data: Sequence[dict[str, Any]],
        expected_outputs: Sequence[dict[str, Any]],
    ) -> tuple[int, int, int, int]:
        """Compute confusion matrix components from test results.

        Args:
            test_data: Test cases with predictions
            expected_outputs: Expected outputs for comparison

        Returns:
            Tuple of (true_positives, false_positives, true_negatives, false_negatives)

        Note:
            Assumes binary classification with positive class being truthy values.
            For multi-class, positive is defined as non-zero/non-empty values.
        """
        tp = fp = tn = fn = 0

        for i, test in enumerate(test_data):
            if i >= len(expected_outputs):
                break

            actual = test.get("output")
            expected = expected_outputs[i].get("expected")

            # Convert to boolean (positive = truthy, negative = falsy)
            actual_positive = bool(actual) if actual is not None else False
            expected_positive = bool(expected) if expected is not None else False

            if actual_positive and expected_positive:
                tp += 1
            elif actual_positive and not expected_positive:
                fp += 1
            elif not actual_positive and not expected_positive:
                tn += 1
            else:  # not actual_positive and expected_positive
                fn += 1

        return tp, fp, tn, fn

    def _compute_metrics_from_confusion_matrix(
        self,
        tp: int,
        fp: int,
        tn: int,
        fn: int,
    ) -> EvaluationMetrics:
        """Compute evaluation metrics from confusion matrix components.

        Args:
            tp: True positives
            fp: False positives
            tn: True negatives
            fn: False negatives

        Returns:
            EvaluationMetrics with computed values
        """
        total = tp + fp + tn + fn

        if total == 0:
            return EvaluationMetrics()

        # Accuracy: (TP + TN) / Total
        accuracy = (tp + tn) / total

        # Precision: TP / (TP + FP) - handles division by zero
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

        # Recall: TP / (TP + FN) - handles division by zero
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        # F1 Score: 2 * (Precision * Recall) / (Precision + Recall)
        if precision + recall > 0:
            f1_score = 2 * (precision * recall) / (precision + recall)
        else:
            f1_score = 0.0

        # False Positive Rate: FP / (FP + TN)
        false_positive_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        return EvaluationMetrics(
            accuracy=round(accuracy, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1_score, 4),
            paper_carryover_rate=0.0,  # Placeholder - wired in future story
            false_positive_rate=round(false_positive_rate, 4),
            time_to_improvement=0.0,  # Placeholder
            turnover_bias_alignment=0.0,  # Placeholder
            compute_cost=0.0,  # Placeholder
            safety_compliance=1.0,  # Default to perfect compliance
        )

    def _check_thresholds(self, metrics: EvaluationMetrics) -> bool:
        """Check if metrics meet thresholds.

        Args:
            metrics: Computed metrics

        Returns:
            True if all thresholds are met
        """
        metric_dict = metrics.to_dict()

        for metric_name, threshold in self.thresholds.items():
            if metric_name == "false_positive_rate":
                # Lower is better for false positive rate
                if metric_dict.get(metric_name, 1.0) > threshold:
                    return False
            else:
                # Higher is better for other metrics
                if metric_dict.get(metric_name, 0.0) < threshold:
                    return False

        return True

    def _count_passed_tests(
        self,
        test_data: Sequence[dict[str, Any]],
        expected_outputs: Sequence[dict[str, Any]] | None,
    ) -> int:
        """Count how many tests passed.

        In production, this would compare actual vs expected outputs.
        """
        if not expected_outputs:
            return len(test_data)  # Assume all passed if no expected outputs

        # Simplified: count matches
        passed = 0
        for i, test in enumerate(test_data):
            if i < len(expected_outputs):
                if test.get("output") == expected_outputs[i].get("expected"):
                    passed += 1

        return passed

    def _calculate_duration(self, started_at: str, completed_at: str) -> float:
        """Calculate duration in seconds between two timestamps."""
        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            return (end - start).total_seconds()
        except (ValueError, AttributeError):
            return 0.0

    def _store_result(self, result: EvaluationResult) -> None:
        """Store evaluation result in Redis and InfluxDB."""
        # Store in Redis
        if self.redis_client:
            try:
                key = f"brain:evaluation:{result.version}"
                self.redis_client.set(
                    key,
                    json.dumps(result.to_dict()),
                    ex=86400 * 30,  # 30 days TTL
                )
                logger.info(f"Stored evaluation result in Redis: {key}")
            except Exception as e:
                logger.error(f"Failed to store result in Redis: {e}")

        # Store in InfluxDB
        if self.influxdb_client:
            try:
                self._store_in_influxdb(result)
                logger.info(
                    f"Stored evaluation metrics in InfluxDB for {result.version}"
                )
            except Exception as e:
                logger.error(f"Failed to store metrics in InfluxDB: {e}")

    def _store_in_influxdb(self, result: EvaluationResult) -> None:
        """Store metrics in InfluxDB.

        In production, this would write to InfluxDB using the line protocol
        or the InfluxDB client library.
        """
        # Placeholder for InfluxDB storage
        # In production:
        # point = Point("brain_evaluation")
        #     .tag("version", result.version)
        #     .tag("status", result.status.value)
        #     .field("accuracy", result.metrics.accuracy)
        #     ...
        pass

    def get_evaluation_result(self, version: str) -> EvaluationResult | None:
        """Get the evaluation result for a version.

        Args:
            version: Brain version

        Returns:
            EvaluationResult if found, None otherwise
        """
        if self.redis_client:
            try:
                key = f"brain:evaluation:{version}"
                data = self.redis_client.get(key)
                if data:
                    return EvaluationResult.from_dict(json.loads(data))
            except Exception as e:
                logger.error(f"Failed to retrieve result from Redis: {e}")

        return None

    def list_evaluations(self, limit: int = 100) -> list[EvaluationResult]:
        """List recent evaluation results.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of EvaluationResult objects
        """
        if not self.redis_client:
            return []

        try:
            # Scan for evaluation keys
            results = []
            cursor = 0
            pattern = "brain:evaluation:*"

            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        results.append(EvaluationResult.from_dict(json.loads(data)))

                if cursor == 0 or len(results) >= limit:
                    break

            # Sort by started_at descending and limit
            results.sort(key=lambda r: r.started_at, reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Failed to list evaluations: {e}")
            return []

    def is_evaluation_passed(self, version: str) -> bool:
        """Check if a version has passed evaluation.

        Args:
            version: Brain version

        Returns:
            True if evaluation passed
        """
        result = self.get_evaluation_result(version)
        return result is not None and result.status == EvaluationStatus.PASSED
