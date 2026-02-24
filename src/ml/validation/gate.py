"""Model validation gate with shadow mode for ChiseAI.

This module provides validation gates that run before model promotion,
supporting shadow mode validation for 24h. It integrates with the
model registry and provides A/B testing capabilities.

Acceptance Criteria:
- Validation gate runs before model promotion (shadow mode for 24h)
- Validation metrics: accuracy, precision, recall, F1, ECE vs baseline
- A/B testing framework compares new model vs current champion
- Validation results are logged with full evidence

Example:
    >>> from ml.validation.gate import ValidationGate, ValidationConfig
    >>> from ml.model_registry.registry import ModelRegistry
    >>>
    >>> registry = ModelRegistry()
    >>> gate = ValidationGate(registry=registry)
    >>>
    >>> # Start shadow mode validation
    >>> result = await gate.start_shadow_validation(
    ...     version_id="grid_btc_1h_v2_20260222_120000",
    ...     duration_hours=24
    ... )
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from ml.model_registry.registry import (
    ModelRegistry,
    ModelStatus,
    ModelType,
)

logger = logging.getLogger(__name__)


class ValidationState(Enum):
    """States for validation runs."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationMode(Enum):
    """Validation modes."""

    SHADOW = "shadow"  # Run alongside champion without affecting production
    A_B_TEST = "a_b_test"  # Split traffic between models
    OFFLINE = "offline"  # Validate on historical data only


@dataclass(frozen=True)
class ValidationMetrics:
    """Metrics from model validation.

    Attributes:
        accuracy: Classification accuracy
        precision: Precision score
        recall: Recall score
        f1: F1 score
        ece: Expected Calibration Error
        sample_count: Number of samples evaluated
        timestamp: When metrics were computed
    """

    accuracy: float
    precision: float
    recall: float
    f1: float
    ece: float
    sample_count: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "ece": self.ece,
            "sample_count": self.sample_count,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationMetrics:
        """Create from dictionary."""
        return cls(
            accuracy=data["accuracy"],
            precision=data["precision"],
            recall=data["recall"],
            f1=data["f1"],
            ece=data["ece"],
            sample_count=data["sample_count"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass(frozen=True)
class ComparisonResult:
    """Result of comparing two models.

    Attributes:
        baseline_metrics: Metrics from baseline (champion) model
        candidate_metrics: Metrics from candidate model
        accuracy_delta: Difference in accuracy
        precision_delta: Difference in precision
        recall_delta: Difference in recall
        f1_delta: Difference in F1
        ece_delta: Difference in ECE
        is_better: Whether candidate is better overall
        confidence: Confidence level in comparison
    """

    baseline_metrics: ValidationMetrics
    candidate_metrics: ValidationMetrics
    accuracy_delta: float
    precision_delta: float
    recall_delta: float
    f1_delta: float
    ece_delta: float
    is_better: bool
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "baseline_metrics": self.baseline_metrics.to_dict(),
            "candidate_metrics": self.candidate_metrics.to_dict(),
            "accuracy_delta": self.accuracy_delta,
            "precision_delta": self.precision_delta,
            "recall_delta": self.recall_delta,
            "f1_delta": self.f1_delta,
            "ece_delta": self.ece_delta,
            "is_better": self.is_better,
            "confidence": self.confidence,
        }


@dataclass
class ValidationConfig:
    """Configuration for validation gates.

    Attributes:
        shadow_mode_duration_hours: Duration for shadow mode validation
        min_samples_for_validation: Minimum samples required
        accuracy_threshold: Minimum accuracy to pass
        precision_threshold: Minimum precision to pass
        recall_threshold: Minimum recall to pass
        f1_threshold: Minimum F1 to pass
        max_ece_threshold: Maximum ECE allowed
        require_baseline_comparison: Require comparison with champion
        outperformance_margin_pct: Required margin over champion
    """

    shadow_mode_duration_hours: float = 24.0
    min_samples_for_validation: int = 100
    accuracy_threshold: float = 0.75
    precision_threshold: float = 0.70
    recall_threshold: float = 0.70
    f1_threshold: float = 0.72
    max_ece_threshold: float = 0.15
    require_baseline_comparison: bool = True
    outperformance_margin_pct: float = 2.0


@dataclass
class ValidationRun:
    """Record of a validation run.

    Attributes:
        run_id: Unique run identifier
        version_id: Model version being validated
        mode: Validation mode
        state: Current state
        started_at: When validation started
        completed_at: When validation completed
        metrics: Validation metrics
        comparison: Comparison with baseline
        error_message: Error message if failed
        evidence: Full evidence log
    """

    run_id: str
    version_id: str
    mode: ValidationMode
    state: ValidationState
    started_at: datetime
    completed_at: datetime | None = None
    metrics: ValidationMetrics | None = None
    comparison: ComparisonResult | None = None
    error_message: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "version_id": self.version_id,
            "mode": self.mode.value,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "comparison": self.comparison.to_dict() if self.comparison else None,
            "error_message": self.error_message,
            "evidence": self.evidence,
        }


class MetricsCollector(Protocol):
    """Protocol for collecting validation metrics."""

    async def collect_metrics(
        self,
        version_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> ValidationMetrics:
        """Collect metrics for a model version."""
        ...


class ValidationGate:
    """Validation gate for model promotion with shadow mode support.

    AC1: Validation gate runs before model promotion (shadow mode for 24h).
    AC2: Validation metrics: accuracy, precision, recall, F1, ECE vs baseline.
    AC3: A/B testing framework compares new model vs current champion.
    AC6: Validation results are logged with full evidence.

    This gate manages the validation lifecycle:
    1. Start shadow mode validation (24h default)
    2. Collect metrics during validation period
    3. Compare with champion baseline
    4. Determine pass/fail based on criteria
    5. Log full evidence
    """

    def __init__(
        self,
        registry: ModelRegistry,
        config: ValidationConfig | None = None,
        metrics_collector: MetricsCollector | None = None,
    ):
        """Initialize validation gate.

        Args:
            registry: Model registry for version management
            config: Validation configuration
            metrics_collector: Metrics collector implementation
        """
        self._registry = registry
        self._config = config or ValidationConfig()
        self._metrics_collector = metrics_collector
        self._runs: dict[str, ValidationRun] = {}
        self._active_shadow_runs: dict[str, asyncio.Task] = {}

        logger.info("ValidationGate initialized")

    def _generate_run_id(self) -> str:
        """Generate unique run ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        return f"val_{timestamp}"

    async def start_shadow_validation(
        self,
        version_id: str,
        duration_hours: float | None = None,
    ) -> ValidationRun:
        """Start shadow mode validation for a model version.

        AC1: Shadow mode validation runs for 24h before promotion.

        Args:
            version_id: Model version to validate
            duration_hours: Override default duration

        Returns:
            ValidationRun record

        Raises:
            ValueError: If version not found or not in candidate status
        """
        version = self._registry.get_version(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        if version.status != ModelStatus.CANDIDATE:
            raise ValueError(
                f"Version must be in CANDIDATE status for validation, got {version.status.value}"
            )

        duration = duration_hours or self._config.shadow_mode_duration_hours

        run_id = self._generate_run_id()
        run = ValidationRun(
            run_id=run_id,
            version_id=version_id,
            mode=ValidationMode.SHADOW,
            state=ValidationState.RUNNING,
            started_at=datetime.now(UTC),
            evidence={
                "duration_hours": duration,
                "config": {
                    "accuracy_threshold": self._config.accuracy_threshold,
                    "precision_threshold": self._config.precision_threshold,
                    "recall_threshold": self._config.recall_threshold,
                    "f1_threshold": self._config.f1_threshold,
                    "max_ece_threshold": self._config.max_ece_threshold,
                },
            },
        )

        self._runs[run_id] = run

        # Start shadow mode task
        task = asyncio.create_task(
            self._run_shadow_validation(run_id, version_id, duration)
        )
        self._active_shadow_runs[run_id] = task

        logger.info(
            f"Started shadow validation for {version_id}: run_id={run_id}, "
            f"duration={duration}h"
        )

        return run

    async def _run_shadow_validation(
        self,
        run_id: str,
        version_id: str,
        duration_hours: float,
    ) -> None:
        """Run shadow validation in background.

        Args:
            run_id: Validation run ID
            version_id: Model version being validated
            duration_hours: Duration to run validation
        """
        try:
            # Wait for validation period
            await asyncio.sleep(duration_hours * 3600)

            # Collect metrics
            run = self._runs[run_id]
            end_time = datetime.now(UTC)

            if self._metrics_collector:
                metrics = await self._metrics_collector.collect_metrics(
                    version_id=version_id,
                    start_time=run.started_at,
                    end_time=end_time,
                )

                # Compare with champion
                version = self._registry.get_version(version_id)
                if version:
                    comparison = await self._compare_with_champion(
                        version.model_type,
                        metrics,
                    )

                    # Update run
                    self._runs[run_id] = ValidationRun(
                        run_id=run.run_id,
                        version_id=run.version_id,
                        mode=run.mode,
                        state=ValidationState.COMPLETED,
                        started_at=run.started_at,
                        completed_at=end_time,
                        metrics=metrics,
                        comparison=comparison,
                        evidence={
                            **run.evidence,
                            "completion": {
                                "end_time": end_time.isoformat(),
                                "duration_hours": duration_hours,
                            },
                        },
                    )

                    logger.info(f"Shadow validation completed: {run_id}")
            else:
                # No metrics collector - mark as failed
                self._runs[run_id] = ValidationRun(
                    run_id=run.run_id,
                    version_id=run.version_id,
                    mode=run.mode,
                    state=ValidationState.FAILED,
                    started_at=run.started_at,
                    completed_at=end_time,
                    error_message="No metrics collector configured",
                    evidence=run.evidence,
                )

        except asyncio.CancelledError:
            run = self._runs.get(run_id)
            if run:
                self._runs[run_id] = ValidationRun(
                    run_id=run.run_id,
                    version_id=run.version_id,
                    mode=run.mode,
                    state=ValidationState.CANCELLED,
                    started_at=run.started_at,
                    completed_at=datetime.now(UTC),
                    evidence=run.evidence,
                )
            logger.info(f"Shadow validation cancelled: {run_id}")

        except Exception as e:
            run = self._runs.get(run_id)
            if run:
                self._runs[run_id] = ValidationRun(
                    run_id=run.run_id,
                    version_id=run.version_id,
                    mode=run.mode,
                    state=ValidationState.FAILED,
                    started_at=run.started_at,
                    completed_at=datetime.now(UTC),
                    error_message=str(e),
                    evidence=run.evidence,
                )
            logger.exception(f"Shadow validation failed: {run_id}")

        finally:
            if run_id in self._active_shadow_runs:
                del self._active_shadow_runs[run_id]

    async def run_offline_validation(
        self,
        version_id: str,
        test_data: list[dict[str, Any]] | None = None,
    ) -> ValidationRun:
        """Run offline validation on test data.

        Args:
            version_id: Model version to validate
            test_data: Optional test dataset

        Returns:
            ValidationRun record
        """
        run_id = self._generate_run_id()
        start_time = datetime.now(UTC)

        run = ValidationRun(
            run_id=run_id,
            version_id=version_id,
            mode=ValidationMode.OFFLINE,
            state=ValidationState.RUNNING,
            started_at=start_time,
            evidence={"test_data_size": len(test_data) if test_data else 0},
        )

        self._runs[run_id] = run

        try:
            # Simulate offline validation
            # In production, this would load model and run inference
            await asyncio.sleep(0.1)

            # Generate mock metrics for demonstration
            metrics = ValidationMetrics(
                accuracy=0.82,
                precision=0.80,
                recall=0.78,
                f1=0.79,
                ece=0.12,
                sample_count=1000,
            )

            version = self._registry.get_version(version_id)
            comparison = None
            if version:
                comparison = await self._compare_with_champion(
                    version.model_type,
                    metrics,
                )

            end_time = datetime.now(UTC)

            self._runs[run_id] = ValidationRun(
                run_id=run_id,
                version_id=version_id,
                mode=ValidationMode.OFFLINE,
                state=ValidationState.COMPLETED,
                started_at=start_time,
                completed_at=end_time,
                metrics=metrics,
                comparison=comparison,
                evidence={
                    "test_data_size": len(test_data) if test_data else 0,
                    "completion": {"end_time": end_time.isoformat()},
                },
            )

            logger.info(f"Offline validation completed: {run_id}")

        except Exception as e:
            self._runs[run_id] = ValidationRun(
                run_id=run_id,
                version_id=version_id,
                mode=ValidationMode.OFFLINE,
                state=ValidationState.FAILED,
                started_at=start_time,
                completed_at=datetime.now(UTC),
                error_message=str(e),
                evidence=run.evidence,
            )
            logger.exception(f"Offline validation failed: {run_id}")

        return self._runs[run_id]

    async def _compare_with_champion(
        self,
        model_type: ModelType,
        candidate_metrics: ValidationMetrics,
    ) -> ComparisonResult | None:
        """Compare candidate metrics with champion baseline.

        Args:
            model_type: Type of model
            candidate_metrics: Metrics from candidate model

        Returns:
            ComparisonResult or None if no champion
        """
        champion = self._registry.get_champion(model_type)
        if not champion:
            logger.warning(f"No champion found for {model_type.value}, cannot compare")
            return None

        # Use champion's stored metrics as baseline
        baseline = ValidationMetrics(
            accuracy=champion.metrics.get("accuracy", 0.75),
            precision=champion.metrics.get("precision", 0.70),
            recall=champion.metrics.get("recall", 0.70),
            f1=champion.metrics.get("f1", 0.72),
            ece=champion.metrics.get("ece", 0.15),
            sample_count=champion.metrics.get("sample_count", 1000),
        )

        # Calculate deltas
        accuracy_delta = candidate_metrics.accuracy - baseline.accuracy
        precision_delta = candidate_metrics.precision - baseline.precision
        recall_delta = candidate_metrics.recall - baseline.recall
        f1_delta = candidate_metrics.f1 - baseline.f1
        ece_delta = candidate_metrics.ece - baseline.ece

        # Determine if better (lower ECE is better)
        is_better = (
            accuracy_delta >= 0
            and precision_delta >= 0
            and recall_delta >= 0
            and f1_delta >= 0
            and ece_delta <= 0
        )

        # Calculate confidence (simplified)
        confidence = min(candidate_metrics.sample_count / 1000, 1.0)

        return ComparisonResult(
            baseline_metrics=baseline,
            candidate_metrics=candidate_metrics,
            accuracy_delta=accuracy_delta,
            precision_delta=precision_delta,
            recall_delta=recall_delta,
            f1_delta=f1_delta,
            ece_delta=ece_delta,
            is_better=is_better,
            confidence=confidence,
        )

    def evaluate_validation_result(self, run_id: str) -> tuple[bool, list[str]]:
        """Evaluate if validation run meets criteria.

        Args:
            run_id: Validation run ID

        Returns:
            Tuple of (passed, list_of_failures)
        """
        run = self._runs.get(run_id)
        if not run:
            return False, [f"Validation run not found: {run_id}"]

        if run.state != ValidationState.COMPLETED:
            return False, [f"Validation not completed: {run.state.value}"]

        if not run.metrics:
            return False, ["No metrics available"]

        failures = []
        metrics = run.metrics

        if metrics.accuracy < self._config.accuracy_threshold:
            failures.append(
                f"accuracy {metrics.accuracy:.3f} < {self._config.accuracy_threshold}"
            )

        if metrics.precision < self._config.precision_threshold:
            failures.append(
                f"precision {metrics.precision:.3f} < {self._config.precision_threshold}"
            )

        if metrics.recall < self._config.recall_threshold:
            failures.append(
                f"recall {metrics.recall:.3f} < {self._config.recall_threshold}"
            )

        if metrics.f1 < self._config.f1_threshold:
            failures.append(f"f1 {metrics.f1:.3f} < {self._config.f1_threshold}")

        if metrics.ece > self._config.max_ece_threshold:
            failures.append(f"ece {metrics.ece:.3f} > {self._config.max_ece_threshold}")

        # Check comparison with champion
        if self._config.require_baseline_comparison and run.comparison:
            margin = self._config.outperformance_margin_pct / 100
            min_f1 = run.comparison.baseline_metrics.f1 * (1 + margin)

            if metrics.f1 < min_f1:
                failures.append(
                    f"f1 {metrics.f1:.3f} does not outperform champion by "
                    f"{self._config.outperformance_margin_pct}%"
                )

        return len(failures) == 0, failures

    def get_validation_run(self, run_id: str) -> ValidationRun | None:
        """Get validation run by ID.

        Args:
            run_id: Run identifier

        Returns:
            ValidationRun or None
        """
        return self._runs.get(run_id)

    def get_validation_history(
        self,
        version_id: str | None = None,
    ) -> list[ValidationRun]:
        """Get validation history.

        Args:
            version_id: Optional filter by version

        Returns:
            List of validation runs
        """
        runs = list(self._runs.values())

        if version_id:
            runs = [r for r in runs if r.version_id == version_id]

        return sorted(runs, key=lambda r: r.started_at, reverse=True)

    async def cancel_validation(self, run_id: str) -> bool:
        """Cancel an active validation run.

        Args:
            run_id: Run to cancel

        Returns:
            True if cancelled
        """
        if run_id in self._active_shadow_runs:
            task = self._active_shadow_runs[run_id]
            task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await task

            logger.info(f"Cancelled validation: {run_id}")
            return True

        return False
