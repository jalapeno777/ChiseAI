"""
Brain Evaluation Framework - Batch Evaluation Module

Implements batch evaluation of 3-5 brain versions simultaneously
with comprehensive metrics and leaderboard ranking.

ST-CHISE-002: Brain Evaluation Framework - Batching + BrainEval
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Generic, TypeVar


class EvaluationStatus(Enum):
    """Status of an evaluation run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class EvaluationMetrics:
    """Comprehensive evaluation metrics for a brain version."""

    # Classification metrics
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0

    # Trading-specific metrics
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0

    # Signal metrics
    total_signals: int = 0
    correct_predictions: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_positives: int = 0
    true_negatives: int = 0

    # Timing metrics
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Custom metrics
    custom: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationMetrics:
        """Create metrics from dictionary."""
        custom = data.pop("custom", {})
        return cls(custom=custom, **data)

    def calculate_f1(self) -> float:
        """Calculate F1 score from precision and recall."""
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)


@dataclass
class EvaluationResult:
    """Result of evaluating a single brain version."""

    brain_version: str
    brain_name: str
    status: EvaluationStatus
    metrics: EvaluationMetrics
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    error_message: str | None = None
    test_suite: str = "standard"
    evaluation_id: str = ""

    def __post_init__(self):
        """Post-initialization validation."""
        if not self.evaluation_id:
            self.evaluation_id = f"{self.brain_version}_{int(time.time())}"

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "evaluation_id": self.evaluation_id,
            "brain_version": self.brain_version,
            "brain_name": self.brain_name,
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "test_suite": self.test_suite,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationResult:
        """Create result from dictionary."""
        return cls(
            evaluation_id=data["evaluation_id"],
            brain_version=data["brain_version"],
            brain_name=data["brain_name"],
            status=EvaluationStatus(data["status"]),
            metrics=EvaluationMetrics.from_dict(data["metrics"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data["completed_at"]
            else None,
            duration_seconds=data["duration_seconds"],
            error_message=data.get("error_message"),
            test_suite=data.get("test_suite", "standard"),
        )


@dataclass
class BatchEvaluationConfig:
    """Configuration for batch evaluation."""

    max_concurrent: int = 3
    timeout_seconds: float = 1800.0  # 30 minutes
    test_suite: str = "standard"
    save_results: bool = True
    results_dir: Path = field(
        default_factory=lambda: Path("_bmad-output/brain-evaluations")
    )

    def __post_init__(self):
        """Ensure results directory exists."""
        if self.save_results:
            self.results_dir.mkdir(parents=True, exist_ok=True)


T = TypeVar("T")


class Leaderboard:
    """Sortable leaderboard for comparing evaluation results."""

    def __init__(self, sort_by: str = "f1_score", ascending: bool = False):
        """
        Initialize leaderboard.

        Args:
            sort_by: Metric to sort by (accuracy, precision, recall, f1_score, win_rate, etc.)
            ascending: Sort in ascending order (lower is better)
        """
        self.results: list[EvaluationResult] = []
        self.sort_by = sort_by
        self.ascending = ascending

    def add_result(self, result: EvaluationResult) -> None:
        """Add an evaluation result to the leaderboard."""
        self.results.append(result)
        self._sort()

    def add_results(self, results: list[EvaluationResult]) -> None:
        """Add multiple evaluation results."""
        self.results.extend(results)
        self._sort()

    def _sort(self) -> None:
        """Sort results by the configured metric."""

        def get_sort_key(result: EvaluationResult) -> float:
            metrics = result.metrics
            if hasattr(metrics, self.sort_by):
                return getattr(metrics, self.sort_by)
            return metrics.custom.get(self.sort_by, 0.0)

        self.results.sort(key=get_sort_key, reverse=not self.ascending)

    def get_ranking(self) -> list[tuple[int, EvaluationResult]]:
        """Get ranked results with positions."""
        return [(i + 1, r) for i, r in enumerate(self.results)]

    def get_top(self, n: int = 3) -> list[EvaluationResult]:
        """Get top N results."""
        return self.results[:n]

    def get_winner(self) -> EvaluationResult | None:
        """Get the best performing result."""
        return self.results[0] if self.results else None

    def compare_versions(self, version_a: str, version_b: str) -> dict[str, Any]:
        """Compare two brain versions across all metrics."""
        result_a = next((r for r in self.results if r.brain_version == version_a), None)
        result_b = next((r for r in self.results if r.brain_version == version_b), None)

        if not result_a or not result_b:
            raise ValueError(
                f"One or both versions not found: {version_a}, {version_b}"
            )

        metrics_a = result_a.metrics
        metrics_b = result_b.metrics

        comparison = {
            "version_a": version_a,
            "version_b": version_b,
            "winner": None,
            "metrics_diff": {},
        }

        # Compare standard metrics
        for metric_name in ["accuracy", "precision", "recall", "f1_score", "win_rate"]:
            val_a = getattr(metrics_a, metric_name)
            val_b = getattr(metrics_b, metric_name)
            diff = val_a - val_b
            comparison["metrics_diff"][metric_name] = {
                "version_a": val_a,
                "version_b": val_b,
                "difference": diff,
                "winner": version_a if diff > 0 else (version_b if diff < 0 else "tie"),
            }

        # Determine overall winner by F1 score
        if metrics_a.f1_score > metrics_b.f1_score:
            comparison["winner"] = version_a
        elif metrics_b.f1_score > metrics_a.f1_score:
            comparison["winner"] = version_b
        else:
            comparison["winner"] = "tie"

        return comparison

    def to_markdown(self) -> str:
        """Generate markdown table of rankings."""
        lines = [
            "# Brain Evaluation Leaderboard",
            "",
            f"Sorted by: **{self.sort_by}** ({'ascending' if self.ascending else 'descending'})",
            "",
            "| Rank | Version | Name | Accuracy | Precision | Recall | F1 Score | Win Rate | Status |",
            "|------|---------|------|----------|-----------|--------|----------|----------|--------|",
        ]

        for rank, result in self.get_ranking():
            m = result.metrics
            status_emoji = "✅" if result.status == EvaluationStatus.COMPLETED else "❌"
            lines.append(
                f"| {rank} | {result.brain_version} | {result.brain_name} | "
                f"{m.accuracy:.3f} | {m.precision:.3f} | {m.recall:.3f} | "
                f"{m.f1_score:.3f} | {m.win_rate:.3f} | {status_emoji} |"
            )

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert leaderboard to dictionary."""
        return {
            "sort_by": self.sort_by,
            "ascending": self.ascending,
            "results": [r.to_dict() for r in self.results],
        }


class BatchEvaluator:
    """
    Evaluates 3-5 brain versions simultaneously with comprehensive metrics.

    Supports parallel execution, timeout handling, and result persistence.
    """

    def __init__(self, config: BatchEvaluationConfig | None = None):
        """
        Initialize batch evaluator.

        Args:
            config: Configuration for batch evaluation
        """
        self.config = config or BatchEvaluationConfig()
        self._evaluation_tasks: dict[str, asyncio.Task] = {}
        self._results: list[EvaluationResult] = []

    async def evaluate_brain(
        self,
        brain_version: str,
        brain_name: str,
        evaluator_func: Callable[[], Coroutine[Any, Any, EvaluationMetrics]],
    ) -> EvaluationResult:
        """
        Evaluate a single brain version.

        Args:
            brain_version: Version identifier (e.g., "v1.2.3")
            brain_name: Human-readable name
            evaluator_func: Async function that returns EvaluationMetrics

        Returns:
            EvaluationResult with full metrics
        """
        started_at = datetime.utcnow()

        result = EvaluationResult(
            brain_version=brain_version,
            brain_name=brain_name,
            status=EvaluationStatus.RUNNING,
            metrics=EvaluationMetrics(),
            started_at=started_at,
            test_suite=self.config.test_suite,
        )

        try:
            # Run evaluation with timeout
            metrics = await asyncio.wait_for(
                evaluator_func(),
                timeout=self.config.timeout_seconds,
            )

            result.metrics = metrics
            result.status = EvaluationStatus.COMPLETED
            result.completed_at = datetime.utcnow()
            result.duration_seconds = (result.completed_at - started_at).total_seconds()

        except asyncio.TimeoutError:
            result.status = EvaluationStatus.TIMEOUT
            result.error_message = (
                f"Evaluation timed out after {self.config.timeout_seconds}s"
            )
            result.completed_at = datetime.utcnow()

        except Exception as e:
            result.status = EvaluationStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.utcnow()

        # Save result if configured
        if self.config.save_results:
            self._save_result(result)

        return result

    async def evaluate_batch(
        self,
        brain_configs: list,
    ) -> list[EvaluationResult]:
        """
        Evaluate multiple brain versions in parallel (3-5 versions).

        Args:
            brain_configs: List of (version, name, evaluator_func) tuples

        Returns:
            List of EvaluationResult for each brain version
        """
        if len(brain_configs) < 3:
            raise ValueError("Batch evaluation requires at least 3 brain versions")
        if len(brain_configs) > 5:
            raise ValueError("Batch evaluation supports maximum 5 brain versions")

        # Create semaphore to limit concurrent evaluations
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def _evaluate_with_semaphore(
            version: str,
            name: str,
            func: Callable[[], Coroutine[Any, Any, EvaluationMetrics]],
        ) -> EvaluationResult:
            async with semaphore:
                return await self.evaluate_brain(version, name, func)

        # Run all evaluations concurrently
        tasks = [
            _evaluate_with_semaphore(version, name, func)
            for version, name, func in brain_configs
        ]

        self._results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        processed_results: list[EvaluationResult] = []
        for i, result in enumerate(self._results):
            if isinstance(result, Exception):
                version, name, _ = brain_configs[i]
                error_result = EvaluationResult(
                    brain_version=version,
                    brain_name=name,
                    status=EvaluationStatus.FAILED,
                    metrics=EvaluationMetrics(),
                    started_at=datetime.utcnow(),
                    error_message=str(result),
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)

        self._results = processed_results
        return self._results

    def create_leaderboard(
        self,
        sort_by: str = "f1_score",
        ascending: bool = False,
    ) -> Leaderboard:
        """
        Create a leaderboard from evaluation results.

        Args:
            sort_by: Metric to sort by
            ascending: Sort in ascending order

        Returns:
            Leaderboard with ranked results
        """
        leaderboard = Leaderboard(sort_by=sort_by, ascending=ascending)
        leaderboard.add_results(self._results)
        return leaderboard

    def _save_result(self, result: EvaluationResult) -> None:
        """Save evaluation result to disk."""
        filename = f"{result.evaluation_id}.json"
        filepath = self.config.results_dir / filename

        with open(filepath, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load_result(self, evaluation_id: str) -> EvaluationResult | None:
        """Load evaluation result from disk."""
        filepath = self.config.results_dir / f"{evaluation_id}.json"

        if not filepath.exists():
            return None

        with open(filepath) as f:
            data = json.load(f)
            return EvaluationResult.from_dict(data)

    def list_saved_results(self) -> list[str]:
        """List all saved evaluation IDs."""
        if not self.config.results_dir.exists():
            return []

        return [f.stem for f in self.config.results_dir.glob("*.json")]


# CLI entry point
async def run_brain_eval(
    brain_versions: list[str],
    brain_names: list[str] | None = None,
    test_suite: str = "standard",
    timeout: float = 1800.0,
) -> Leaderboard:
    """
    CLI entry point for brain evaluation.

    Args:
        brain_versions: List of brain version identifiers
        brain_names: Optional list of human-readable names
        test_suite: Test suite to run
        timeout: Timeout per evaluation in seconds

    Returns:
        Leaderboard with results
    """
    if brain_names is None:
        brain_names = brain_versions

    if len(brain_versions) != len(brain_names):
        raise ValueError("brain_versions and brain_names must have same length")

    config = BatchEvaluationConfig(
        test_suite=test_suite,
        timeout_seconds=timeout,
    )

    evaluator = BatchEvaluator(config)

    # Create mock evaluator functions (replace with actual evaluation logic)
    async def mock_evaluator(version: str) -> EvaluationMetrics:
        # Simulate evaluation time
        await asyncio.sleep(1)
        return EvaluationMetrics(
            accuracy=0.75 + hash(version) % 100 / 1000,
            precision=0.70 + hash(version) % 100 / 1000,
            recall=0.72 + hash(version) % 100 / 1000,
            f1_score=0.71 + hash(version) % 100 / 1000,
            win_rate=0.65 + hash(version) % 100 / 1000,
        )

    brain_configs = [
        (version, name, lambda v=version: mock_evaluator(v))
        for version, name in zip(brain_versions, brain_names)
    ]

    results = await evaluator.evaluate_batch(brain_configs)
    leaderboard = evaluator.create_leaderboard()

    return leaderboard


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) < 4:
        print(
            "Usage: python batch_evaluator.py <version1> <version2> <version3> [version4] [version5]"
        )
        sys.exit(1)

    versions = sys.argv[1:]
    leaderboard = asyncio.run(run_brain_eval(versions))
    print(leaderboard.to_markdown())
