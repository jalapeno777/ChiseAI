"""Brain batch evaluation framework for parallel brain version testing.

This module provides the infrastructure for evaluating multiple brain versions
in parallel, ranking them by weighted objectives, and persisting results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EvaluationStatus(Enum):
    """Status of a brain evaluation."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class EvaluationResult:
    """Result of a single brain version evaluation.

    Attributes:
        brain_version: Unique identifier for the brain version
        status: Evaluation status (completed/failed/timeout/pending)
        accuracy: Classification accuracy (0-1)
        precision: Precision score (0-1)
        recall: Recall score (0-1)
        f1_score: F1 score (harmonic mean of precision and recall)
        win_rate: Trading win rate (0-1)
        sharpe_ratio: Risk-adjusted return metric
        max_drawdown: Maximum drawdown as decimal (e.g., 0.15 = 15%)
        duration_seconds: Time taken for evaluation
        error_message: Optional error message if evaluation failed
        timestamp: When the evaluation was completed
    """

    brain_version: str
    status: EvaluationStatus
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    duration_seconds: float = 0.0
    error_message: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Validate evaluation result values."""
        # Validate metric ranges
        for metric_name, metric_value in [
            ("accuracy", self.accuracy),
            ("precision", self.precision),
            ("recall", self.recall),
            ("f1_score", self.f1_score),
            ("win_rate", self.win_rate),
        ]:
            if not 0.0 <= metric_value <= 1.0:
                raise ValueError(
                    f"{metric_name} must be between 0 and 1, got {metric_value}"
                )

        if self.max_drawdown < 0.0:
            raise ValueError(
                f"max_drawdown must be non-negative, got {self.max_drawdown}"
            )

        if self.duration_seconds < 0.0:
            raise ValueError(
                f"duration_seconds must be non-negative, got {self.duration_seconds}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        result = asdict(self)
        result["status"] = self.status.value
        result["timestamp"] = self.timestamp.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationResult:
        """Create result from dictionary."""
        # Handle status conversion
        status_value = data.get("status", "pending")
        if isinstance(status_value, str):
            status = EvaluationStatus(status_value)
        else:
            status = status_value

        # Handle timestamp conversion
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = datetime.utcnow()

        return cls(
            brain_version=data["brain_version"],
            status=status,
            accuracy=data.get("accuracy", 0.0),
            precision=data.get("precision", 0.0),
            recall=data.get("recall", 0.0),
            f1_score=data.get("f1_score", 0.0),
            win_rate=data.get("win_rate", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            duration_seconds=data.get("duration_seconds", 0.0),
            error_message=data.get("error_message"),
            timestamp=timestamp,
        )

    def is_successful(self) -> bool:
        """Check if evaluation completed successfully."""
        return self.status == EvaluationStatus.COMPLETED


@dataclass
class LeaderboardConfig:
    """Configuration for leaderboard ranking weights.

    Attributes:
        f1_weight: Weight for F1 score (default: 0.25)
        win_rate_weight: Weight for win rate (default: 0.25)
        sharpe_weight: Weight for Sharpe ratio (default: 0.30)
        drawdown_weight: Weight for max drawdown penalty (default: 0.20)
    """

    f1_weight: float = 0.25
    win_rate_weight: float = 0.25
    sharpe_weight: float = 0.30
    drawdown_weight: float = 0.20

    def __post_init__(self) -> None:
        """Validate weights sum to approximately 1.0."""
        total = (
            self.f1_weight
            + self.win_rate_weight
            + self.sharpe_weight
            + self.drawdown_weight
        )
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


class Leaderboard:
    """Leaderboard for ranking brain evaluation results.

    Ranks results by a weighted composite score combining:
    - F1 score (classification quality)
    - Win rate (trading success)
    - Sharpe ratio (risk-adjusted returns)
    - Max drawdown (risk penalty)
    """

    def __init__(self, config: LeaderboardConfig | None = None) -> None:
        """Initialize leaderboard with optional custom config.

        Args:
            config: Leaderboard configuration with ranking weights.
                   Uses default weights if not provided.
        """
        self.config = config or LeaderboardConfig()
        self._results: list[EvaluationResult] = []

    def add_result(self, result: EvaluationResult) -> None:
        """Add an evaluation result to the leaderboard.

        Args:
            result: The evaluation result to add.
        """
        self._results.append(result)

    def add_results(self, results: list[EvaluationResult]) -> None:
        """Add multiple evaluation results to the leaderboard.

        Args:
            results: List of evaluation results to add.
        """
        self._results.extend(results)

    def _calculate_score(self, result: EvaluationResult) -> float:
        """Calculate composite score for a result.

        The score is a weighted combination of:
        - F1 score (higher is better)
        - Win rate (higher is better)
        - Sharpe ratio (higher is better, normalized)
        - Max drawdown (lower is better, so we use 1 - drawdown)

        Args:
            result: The evaluation result to score.

        Returns:
            Composite score between 0 and 1.
        """
        if not result.is_successful():
            return 0.0

        # Normalize Sharpe ratio (typical range -3 to 3, clip to 0-1)
        normalized_sharpe = max(0.0, min(1.0, (result.sharpe_ratio + 3) / 6))

        # Drawdown penalty (invert so lower drawdown = higher score)
        drawdown_score = max(0.0, 1.0 - result.max_drawdown)

        score = (
            self.config.f1_weight * result.f1_score
            + self.config.win_rate_weight * result.win_rate
            + self.config.sharpe_weight * normalized_sharpe
            + self.config.drawdown_weight * drawdown_score
        )

        return score

    def get_ranked_results(self) -> list[tuple[EvaluationResult, float]]:
        """Get all results ranked by composite score (highest first).

        Returns:
            List of tuples (result, score) sorted by score descending.
        """
        scored = [(r, self._calculate_score(r)) for r in self._results]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def get_top_n(self, n: int) -> list[tuple[EvaluationResult, float]]:
        """Get top N results by composite score.

        Args:
            n: Number of top results to return.

        Returns:
            List of top N (result, score) tuples.

        Raises:
            ValueError: If n is negative.
        """
        if n < 0:
            raise ValueError(f"n must be non-negative, got {n}")

        ranked = self.get_ranked_results()
        return ranked[:n]

    def compare(self, version_a: str, version_b: str) -> dict[str, Any]:
        """Compare two brain versions.

        Args:
            version_a: First brain version identifier.
            version_b: Second brain version identifier.

        Returns:
            Dictionary with comparison results including scores and winner.

        Raises:
            ValueError: If either version is not found in results.
        """
        result_a = next(
            (r for r in self._results if r.brain_version == version_a), None
        )
        result_b = next(
            (r for r in self._results if r.brain_version == version_b), None
        )

        if result_a is None:
            raise ValueError(f"Version '{version_a}' not found in results")
        if result_b is None:
            raise ValueError(f"Version '{version_b}' not found in results")

        score_a = self._calculate_score(result_a)
        score_b = self._calculate_score(result_b)

        if score_a > score_b:
            winner = version_a
        elif score_b > score_a:
            winner = version_b
        else:
            winner = "tie"

        return {
            "version_a": version_a,
            "version_b": version_b,
            "score_a": score_a,
            "score_b": score_b,
            "winner": winner,
            "score_difference": abs(score_a - score_b),
            "improvement_pct": (
                (max(score_a, score_b) / min(score_a, score_b) - 1) * 100
                if min(score_a, score_b) > 0
                else 0
            ),
        }

    def get_best(self) -> tuple[EvaluationResult, float] | None:
        """Get the best performing result.

        Returns:
            Tuple of (best_result, score) or None if no results.
        """
        ranked = self.get_ranked_results()
        return ranked[0] if ranked else None

    def clear(self) -> None:
        """Clear all results from the leaderboard."""
        self._results.clear()

    def __len__(self) -> int:
        """Return number of results in leaderboard."""
        return len(self._results)


class BatchEvaluator:
    """Evaluates multiple brain versions in parallel with timeout support.

    Supports evaluating 3-5 brain versions concurrently, with configurable
    timeouts per evaluation and graceful handling of partial failures.
    """

    def __init__(
        self,
        default_timeout_seconds: float = 300.0,
        max_concurrent: int = 5,
    ) -> None:
        """Initialize batch evaluator.

        Args:
            default_timeout_seconds: Default timeout for each evaluation.
            max_concurrent: Maximum number of concurrent evaluations.
        """
        self.default_timeout_seconds = default_timeout_seconds
        self.max_concurrent = max_concurrent
        self._evaluation_count = 0

    async def _evaluate_single(
        self,
        brain_version: str,
        timeout_seconds: float | None = None,
    ) -> EvaluationResult:
        """Evaluate a single brain version.

        This is a placeholder that simulates evaluation. In production,
        this would call the actual brain evaluation logic.

        Args:
            brain_version: The brain version to evaluate.
            timeout_seconds: Timeout for this specific evaluation.

        Returns:
            EvaluationResult with metrics or failure status.
        """
        timeout = timeout_seconds or self.default_timeout_seconds
        start_time = datetime.utcnow()

        try:
            # Simulate evaluation work with timeout
            await asyncio.wait_for(
                self._simulate_evaluation(brain_version),
                timeout=timeout,
            )

            duration = max(0.0, (datetime.utcnow() - start_time).total_seconds())

            # Generate deterministic metrics based on version string
            metrics = self._generate_metrics(brain_version)

            return EvaluationResult(
                brain_version=brain_version,
                status=EvaluationStatus.COMPLETED,
                accuracy=metrics["accuracy"],
                precision=metrics["precision"],
                recall=metrics["recall"],
                f1_score=metrics["f1_score"],
                win_rate=metrics["win_rate"],
                sharpe_ratio=metrics["sharpe_ratio"],
                max_drawdown=metrics["max_drawdown"],
                duration_seconds=duration,
            )

        except TimeoutError:
            duration = max(0.0, (datetime.utcnow() - start_time).total_seconds())
            logger.warning(f"Evaluation timeout for {brain_version}")
            return EvaluationResult(
                brain_version=brain_version,
                status=EvaluationStatus.TIMEOUT,
                duration_seconds=duration,
                error_message=f"Evaluation exceeded timeout of {timeout}s",
            )
        except Exception as e:
            duration = max(0.0, (datetime.utcnow() - start_time).total_seconds())
            logger.error(f"Evaluation failed for {brain_version}: {e}")
            return EvaluationResult(
                brain_version=brain_version,
                status=EvaluationStatus.FAILED,
                duration_seconds=duration,
                error_message=str(e),
            )

    async def _simulate_evaluation(self, brain_version: str) -> None:
        """Simulate evaluation work.

        In production, this would be replaced with actual evaluation logic.

        Args:
            brain_version: The brain version being evaluated.
        """
        # Simulate variable evaluation time (0.1-0.5 seconds)
        await asyncio.sleep(0.1 + (hash(brain_version) % 40) / 100)

    def _generate_metrics(self, brain_version: str) -> dict[str, float]:
        """Generate deterministic metrics for a brain version.

        Uses the version string hash to generate consistent metrics
        for testing purposes.

        Args:
            brain_version: The brain version identifier.

        Returns:
            Dictionary of metric names to values.
        """
        # Use hash for deterministic but varied metrics
        version_hash = hash(brain_version)

        # Generate metrics in valid ranges
        accuracy = 0.5 + (version_hash % 40) / 100  # 0.5 - 0.9
        precision = 0.45 + ((version_hash >> 4) % 45) / 100  # 0.45 - 0.9
        recall = 0.4 + ((version_hash >> 8) % 50) / 100  # 0.4 - 0.9

        # F1 is harmonic mean
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        win_rate = 0.45 + ((version_hash >> 12) % 40) / 100  # 0.45 - 0.85
        sharpe_ratio = -1.0 + ((version_hash >> 16) % 50) / 10  # -1.0 to 4.0
        max_drawdown = ((version_hash >> 20) % 30) / 100  # 0.0 to 0.3

        return {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "win_rate": round(win_rate, 4),
            "sharpe_ratio": round(sharpe_ratio, 4),
            "max_drawdown": round(max_drawdown, 4),
        }

    async def evaluate_batch(
        self,
        brain_versions: list[str],
        timeout_seconds: float | None = None,
    ) -> list[EvaluationResult]:
        """Evaluate multiple brain versions in parallel.

        Evaluates 3-5 brain versions concurrently with configurable timeout.
        Handles failures gracefully, returning partial results.

        Args:
            brain_versions: List of brain version identifiers to evaluate.
            timeout_seconds: Optional timeout override for all evaluations.

        Returns:
            List of EvaluationResult objects, one per input version.
            Failed evaluations have status FAILED or TIMEOUT.

        Raises:
            ValueError: If fewer than 1 or more than max_concurrent versions.
        """
        if not brain_versions:
            logger.warning("Empty brain_versions list provided")
            return []

        if len(brain_versions) > self.max_concurrent:
            raise ValueError(
                f"Cannot evaluate more than {self.max_concurrent} versions at once, "
                f"got {len(brain_versions)}"
            )

        logger.info(
            f"Starting batch evaluation of {len(brain_versions)} brain versions"
        )

        # Create tasks for parallel execution
        tasks = [
            self._evaluate_single(version, timeout_seconds)
            for version in brain_versions
        ]

        # Execute all evaluations concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, converting exceptions to failed results
        processed_results: list[EvaluationResult] = []
        for version, result in zip(brain_versions, results, strict=False):
            if isinstance(result, Exception):
                logger.error(f"Unexpected exception for {version}: {result}")
                processed_results.append(
                    EvaluationResult(
                        brain_version=version,
                        status=EvaluationStatus.FAILED,
                        error_message=f"Unexpected exception: {result}",
                    )
                )
            elif isinstance(result, EvaluationResult):
                processed_results.append(result)
            else:
                # Handle unexpected BaseException types
                processed_results.append(
                    EvaluationResult(
                        brain_version=version,
                        status=EvaluationStatus.FAILED,
                        error_message=f"Unexpected error: {result}",
                    )
                )

        self._evaluation_count += len(processed_results)

        # Log summary
        successful = sum(1 for r in processed_results if r.is_successful())
        failed = len(processed_results) - successful
        logger.info(
            f"Batch evaluation complete: {successful} successful, {failed} failed"
        )

        return processed_results

    def get_evaluation_count(self) -> int:
        """Get total number of evaluations performed."""
        return self._evaluation_count


class EvaluationPersistence:
    """Persistence layer for evaluation results.

    Supports saving and loading evaluation results to/from JSON files.
    """

    @staticmethod
    def save_results(
        results: list[EvaluationResult],
        filepath: Path | str,
    ) -> None:
        """Save evaluation results to JSON file.

        Args:
            results: List of evaluation results to save.
            filepath: Path to save the JSON file.

        Raises:
            IOError: If file cannot be written.
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "saved_at": datetime.utcnow().isoformat(),
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(results)} results to {filepath}")

    @staticmethod
    def load_results(filepath: Path | str) -> list[EvaluationResult]:
        """Load evaluation results from JSON file.

        Args:
            filepath: Path to the JSON file.

        Returns:
            List of evaluation results.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If JSON is malformed.
        """
        filepath = Path(filepath)

        with open(filepath) as f:
            data = json.load(f)

        results = [EvaluationResult.from_dict(r) for r in data.get("results", [])]
        logger.info(f"Loaded {len(results)} results from {filepath}")
        return results

    @staticmethod
    def append_results(
        results: list[EvaluationResult],
        filepath: Path | str,
    ) -> None:
        """Append evaluation results to existing JSON file.

        Args:
            results: List of evaluation results to append.
            filepath: Path to the JSON file.
        """
        filepath = Path(filepath)

        if filepath.exists():
            existing = EvaluationPersistence.load_results(filepath)
            combined = existing + results
        else:
            combined = results

        EvaluationPersistence.save_results(combined, filepath)


def run_batch_evaluation(
    brain_versions: list[str],
    timeout_seconds: float | None = None,
    output_path: Path | None = None,
) -> list[EvaluationResult]:
    """Convenience function to run batch evaluation synchronously.

    Args:
        brain_versions: List of brain version identifiers.
        timeout_seconds: Optional timeout for evaluations.
        output_path: Optional path to save results.

    Returns:
        List of evaluation results.
    """
    evaluator = BatchEvaluator()
    results = asyncio.run(evaluator.evaluate_batch(brain_versions, timeout_seconds))

    if output_path:
        EvaluationPersistence.save_results(results, output_path)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch evaluate brain versions")
    parser.add_argument(
        "versions",
        nargs="+",
        help="Brain version identifiers to evaluate",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Timeout per evaluation in seconds (default: 300)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--leaderboard",
        "-l",
        action="store_true",
        help="Show leaderboard ranking",
    )

    args = parser.parse_args()

    # Run evaluation
    results = run_batch_evaluation(
        args.versions,
        timeout_seconds=args.timeout,
        output_path=Path(args.output) if args.output else None,
    )

    # Print results
    print(f"\n{'=' * 60}")
    print(f"Evaluation Results ({len(results)} versions)")
    print(f"{'=' * 60}")

    for result in results:
        status_icon = "✓" if result.is_successful() else "✗"
        print(f"\n{status_icon} {result.brain_version}")
        print(f"   Status: {result.status.value}")
        if result.is_successful():
            print(f"   F1: {result.f1_score:.4f} | Win Rate: {result.win_rate:.4f}")
            print(
                f"   Sharpe: {result.sharpe_ratio:.4f} | Drawdown: {result.max_drawdown:.4f}"
            )
        elif result.error_message:
            print(f"   Error: {result.error_message}")

    # Show leaderboard if requested
    if args.leaderboard:
        leaderboard = Leaderboard()
        leaderboard.add_results(results)

        print(f"\n{'=' * 60}")
        print("Leaderboard (Top Performers)")
        print(f"{'=' * 60}")

        for i, (result, score) in enumerate(leaderboard.get_top_n(5), 1):
            print(f"{i}. {result.brain_version} (Score: {score:.4f})")
            if result.is_successful():
                print(
                    f"   F1: {result.f1_score:.4f} | Win: {result.win_rate:.4f} | "
                    f"Sharpe: {result.sharpe_ratio:.4f}"
                )
