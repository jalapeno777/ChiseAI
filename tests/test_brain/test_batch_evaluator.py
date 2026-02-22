"""Tests for the brain batch evaluation framework."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from src.brain.batch_evaluator import (
    BatchEvaluator,
    EvaluationPersistence,
    EvaluationResult,
    EvaluationStatus,
    Leaderboard,
    LeaderboardConfig,
    run_batch_evaluation,
)


class TestEvaluationStatus:
    """Tests for EvaluationStatus enum."""

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert EvaluationStatus.PENDING.value == "pending"
        assert EvaluationStatus.COMPLETED.value == "completed"
        assert EvaluationStatus.FAILED.value == "failed"
        assert EvaluationStatus.TIMEOUT.value == "timeout"

    def test_enum_count(self) -> None:
        """Test that there are exactly 4 status values."""
        assert len(EvaluationStatus) == 4


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_create_successful_result(self) -> None:
        """Test creating a successful evaluation result."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=0.85,
            precision=0.80,
            recall=0.75,
            f1_score=0.775,
            win_rate=0.70,
            sharpe_ratio=1.5,
            max_drawdown=0.15,
            duration_seconds=120.5,
        )

        assert result.brain_version == "v1.0.0"
        assert result.status == EvaluationStatus.COMPLETED
        assert result.accuracy == 0.85
        assert result.precision == 0.80
        assert result.recall == 0.75
        assert result.f1_score == 0.775
        assert result.win_rate == 0.70
        assert result.sharpe_ratio == 1.5
        assert result.max_drawdown == 0.15
        assert result.duration_seconds == 120.5
        assert result.error_message is None
        assert result.is_successful() is True

    def test_create_failed_result(self) -> None:
        """Test creating a failed evaluation result."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.FAILED,
            error_message="Test error",
        )

        assert result.status == EvaluationStatus.FAILED
        assert result.error_message == "Test error"
        assert result.is_successful() is False

    def test_create_timeout_result(self) -> None:
        """Test creating a timeout evaluation result."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.TIMEOUT,
            error_message="Timeout occurred",
        )

        assert result.status == EvaluationStatus.TIMEOUT
        assert result.is_successful() is False

    def test_invalid_accuracy_raises(self) -> None:
        """Test that accuracy outside 0-1 range raises ValueError."""
        with pytest.raises(ValueError, match="accuracy must be between 0 and 1"):
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                accuracy=1.5,
            )

    def test_invalid_precision_raises(self) -> None:
        """Test that precision outside 0-1 range raises ValueError."""
        with pytest.raises(ValueError, match="precision must be between 0 and 1"):
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                precision=-0.1,
            )

    def test_invalid_recall_raises(self) -> None:
        """Test that recall outside 0-1 range raises ValueError."""
        with pytest.raises(ValueError, match="recall must be between 0 and 1"):
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                recall=1.1,
            )

    def test_invalid_f1_raises(self) -> None:
        """Test that f1_score outside 0-1 range raises ValueError."""
        with pytest.raises(ValueError, match="f1_score must be between 0 and 1"):
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                f1_score=-0.5,
            )

    def test_invalid_win_rate_raises(self) -> None:
        """Test that win_rate outside 0-1 range raises ValueError."""
        with pytest.raises(ValueError, match="win_rate must be between 0 and 1"):
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                win_rate=2.0,
            )

    def test_invalid_max_drawdown_raises(self) -> None:
        """Test that negative max_drawdown raises ValueError."""
        with pytest.raises(ValueError, match="max_drawdown must be non-negative"):
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                max_drawdown=-0.1,
            )

    def test_invalid_duration_raises(self) -> None:
        """Test that negative duration raises ValueError."""
        with pytest.raises(ValueError, match="duration_seconds must be non-negative"):
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                duration_seconds=-10.0,
            )

    def test_to_dict_serialization(self) -> None:
        """Test serialization to dictionary."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=0.85,
            duration_seconds=120.5,
        )

        data = result.to_dict()

        assert data["brain_version"] == "v1.0.0"
        assert data["status"] == "completed"
        assert data["accuracy"] == 0.85
        assert data["duration_seconds"] == 120.5
        assert "timestamp" in data

    def test_from_dict_deserialization(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "brain_version": "v1.0.0",
            "status": "completed",
            "accuracy": 0.85,
            "precision": 0.80,
            "recall": 0.75,
            "f1_score": 0.775,
            "win_rate": 0.70,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.15,
            "duration_seconds": 120.5,
            "error_message": None,
            "timestamp": "2024-01-15T10:30:00",
        }

        result = EvaluationResult.from_dict(data)

        assert result.brain_version == "v1.0.0"
        assert result.status == EvaluationStatus.COMPLETED
        assert result.accuracy == 0.85
        assert result.timestamp == datetime(2024, 1, 15, 10, 30, 0)

    def test_from_dict_with_enum_status(self) -> None:
        """Test deserialization when status is already an enum."""
        data = {
            "brain_version": "v1.0.0",
            "status": EvaluationStatus.FAILED,
            "error_message": "Test error",
        }

        result = EvaluationResult.from_dict(data)
        assert result.status == EvaluationStatus.FAILED


class TestLeaderboardConfig:
    """Tests for LeaderboardConfig."""

    def test_default_weights(self) -> None:
        """Test default weight configuration."""
        config = LeaderboardConfig()

        assert config.f1_weight == 0.25
        assert config.win_rate_weight == 0.25
        assert config.sharpe_weight == 0.30
        assert config.drawdown_weight == 0.20

    def test_custom_weights(self) -> None:
        """Test custom weight configuration."""
        config = LeaderboardConfig(
            f1_weight=0.4,
            win_rate_weight=0.3,
            sharpe_weight=0.2,
            drawdown_weight=0.1,
        )

        assert config.f1_weight == 0.4
        assert config.win_rate_weight == 0.3
        assert config.sharpe_weight == 0.2
        assert config.drawdown_weight == 0.1

    def test_invalid_weights_raises(self) -> None:
        """Test that weights not summing to 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            LeaderboardConfig(
                f1_weight=0.5,
                win_rate_weight=0.5,
                sharpe_weight=0.5,
                drawdown_weight=0.5,
            )


class TestLeaderboard:
    """Tests for Leaderboard."""

    @pytest.fixture
    def sample_results(self) -> list[EvaluationResult]:
        """Create sample evaluation results for testing."""
        return [
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                accuracy=0.80,
                precision=0.75,
                recall=0.70,
                f1_score=0.725,
                win_rate=0.65,
                sharpe_ratio=1.2,
                max_drawdown=0.20,
            ),
            EvaluationResult(
                brain_version="v1.1.0",
                status=EvaluationStatus.COMPLETED,
                accuracy=0.85,
                precision=0.80,
                recall=0.75,
                f1_score=0.775,
                win_rate=0.70,
                sharpe_ratio=1.5,
                max_drawdown=0.15,
            ),
            EvaluationResult(
                brain_version="v1.2.0",
                status=EvaluationStatus.COMPLETED,
                accuracy=0.90,
                precision=0.85,
                recall=0.80,
                f1_score=0.825,
                win_rate=0.75,
                sharpe_ratio=2.0,
                max_drawdown=0.10,
            ),
        ]

    @pytest.fixture
    def leaderboard(self) -> Leaderboard:
        """Create a fresh leaderboard instance."""
        return Leaderboard()

    def test_add_single_result(self, leaderboard: Leaderboard) -> None:
        """Test adding a single result."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.COMPLETED,
        )

        leaderboard.add_result(result)

        assert len(leaderboard) == 1

    def test_add_multiple_results(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test adding multiple results at once."""
        leaderboard.add_results(sample_results)

        assert len(leaderboard) == 3

    def test_get_ranked_results(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test getting ranked results."""
        leaderboard.add_results(sample_results)

        ranked = leaderboard.get_ranked_results()

        assert len(ranked) == 3
        # v1.2.0 should be best (highest metrics, lowest drawdown)
        assert ranked[0][0].brain_version == "v1.2.0"
        # Scores should be descending
        assert ranked[0][1] >= ranked[1][1] >= ranked[2][1]

    def test_get_top_n(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test getting top N results."""
        leaderboard.add_results(sample_results)

        top_2 = leaderboard.get_top_n(2)

        assert len(top_2) == 2
        assert top_2[0][0].brain_version == "v1.2.0"
        assert top_2[1][0].brain_version == "v1.1.0"

    def test_get_top_n_zero(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test getting top 0 results."""
        leaderboard.add_results(sample_results)

        top_0 = leaderboard.get_top_n(0)

        assert len(top_0) == 0

    def test_get_top_n_negative_raises(self, leaderboard: Leaderboard) -> None:
        """Test that negative n raises ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            leaderboard.get_top_n(-1)

    def test_compare_versions(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test comparing two versions."""
        leaderboard.add_results(sample_results)

        comparison = leaderboard.compare("v1.0.0", "v1.2.0")

        assert comparison["version_a"] == "v1.0.0"
        assert comparison["version_b"] == "v1.2.0"
        assert comparison["winner"] == "v1.2.0"
        assert comparison["score_a"] < comparison["score_b"]
        assert "score_difference" in comparison
        assert "improvement_pct" in comparison

    def test_compare_same_version(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test comparing a version with itself."""
        leaderboard.add_results(sample_results)

        comparison = leaderboard.compare("v1.0.0", "v1.0.0")

        assert comparison["winner"] == "tie"
        assert comparison["score_difference"] == 0.0

    def test_compare_missing_version_raises(self, leaderboard: Leaderboard) -> None:
        """Test that comparing missing version raises ValueError."""
        with pytest.raises(ValueError, match="not found in results"):
            leaderboard.compare("v1.0.0", "v2.0.0")

    def test_get_best(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test getting the best result."""
        leaderboard.add_results(sample_results)

        best = leaderboard.get_best()

        assert best is not None
        assert best[0].brain_version == "v1.2.0"

    def test_get_best_empty(self, leaderboard: Leaderboard) -> None:
        """Test getting best from empty leaderboard."""
        best = leaderboard.get_best()

        assert best is None

    def test_clear(
        self, leaderboard: Leaderboard, sample_results: list[EvaluationResult]
    ) -> None:
        """Test clearing the leaderboard."""
        leaderboard.add_results(sample_results)
        assert len(leaderboard) == 3

        leaderboard.clear()

        assert len(leaderboard) == 0

    def test_failed_results_get_zero_score(self, leaderboard: Leaderboard) -> None:
        """Test that failed results get zero score."""
        failed_result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.FAILED,
            error_message="Test failure",
        )

        leaderboard.add_result(failed_result)
        ranked = leaderboard.get_ranked_results()

        assert ranked[0][1] == 0.0

    def test_custom_config(self, sample_results: list[EvaluationResult]) -> None:
        """Test leaderboard with custom config."""
        config = LeaderboardConfig(
            f1_weight=0.5,
            win_rate_weight=0.2,
            sharpe_weight=0.2,
            drawdown_weight=0.1,
        )
        leaderboard = Leaderboard(config=config)
        leaderboard.add_results(sample_results)

        ranked = leaderboard.get_ranked_results()

        # Should still rank correctly
        assert len(ranked) == 3


class TestBatchEvaluator:
    """Tests for BatchEvaluator."""

    @pytest.fixture
    def evaluator(self) -> BatchEvaluator:
        """Create a fresh batch evaluator."""
        return BatchEvaluator()

    @pytest.mark.asyncio
    async def test_evaluate_single_version(self, evaluator: BatchEvaluator) -> None:
        """Test evaluating a single version."""
        results = await evaluator.evaluate_batch(["v1.0.0"])

        assert len(results) == 1
        assert results[0].brain_version == "v1.0.0"
        assert results[0].is_successful()

    @pytest.mark.asyncio
    async def test_evaluate_multiple_versions(self, evaluator: BatchEvaluator) -> None:
        """Test evaluating multiple versions in parallel."""
        versions = ["v1.0.0", "v1.1.0", "v1.2.0"]

        results = await evaluator.evaluate_batch(versions)

        assert len(results) == 3
        result_versions = [r.brain_version for r in results]
        assert all(v in result_versions for v in versions)

    @pytest.mark.asyncio
    async def test_evaluate_empty_list(self, evaluator: BatchEvaluator) -> None:
        """Test evaluating empty list returns empty results."""
        results = await evaluator.evaluate_batch([])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_evaluate_too_many_versions_raises(
        self, evaluator: BatchEvaluator
    ) -> None:
        """Test that evaluating more than max_concurrent raises ValueError."""
        versions = ["v1.0.0", "v1.1.0", "v1.2.0", "v1.3.0", "v1.4.0", "v1.5.0"]

        with pytest.raises(ValueError, match="Cannot evaluate more than"):
            await evaluator.evaluate_batch(versions)

    @pytest.mark.asyncio
    async def test_evaluate_with_timeout(self, evaluator: BatchEvaluator) -> None:
        """Test evaluation with timeout."""
        results = await evaluator.evaluate_batch(["v1.0.0"], timeout_seconds=60.0)

        assert len(results) == 1
        assert results[0].is_successful()

    @pytest.mark.asyncio
    async def test_evaluate_with_very_short_timeout(
        self, evaluator: BatchEvaluator
    ) -> None:
        """Test evaluation with very short timeout causes timeout."""
        # Use a very short timeout to force timeout
        results = await evaluator.evaluate_batch(["v1.0.0"], timeout_seconds=0.001)

        assert len(results) == 1
        assert results[0].status == EvaluationStatus.TIMEOUT

    def test_get_evaluation_count(self, evaluator: BatchEvaluator) -> None:
        """Test evaluation count tracking."""
        assert evaluator.get_evaluation_count() == 0

        asyncio.run(evaluator.evaluate_batch(["v1.0.0"]))

        assert evaluator.get_evaluation_count() == 1


class TestEvaluationPersistence:
    """Tests for EvaluationPersistence."""

    @pytest.fixture
    def sample_results(self) -> list[EvaluationResult]:
        """Create sample evaluation results."""
        return [
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                accuracy=0.85,
                f1_score=0.80,
                win_rate=0.75,
                sharpe_ratio=1.5,
                max_drawdown=0.15,
                duration_seconds=120.5,
            ),
            EvaluationResult(
                brain_version="v1.1.0",
                status=EvaluationStatus.FAILED,
                error_message="Test error",
            ),
        ]

    def test_save_and_load_results(
        self, sample_results: list[EvaluationResult]
    ) -> None:
        """Test saving and loading results."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = Path(f.name)

        try:
            EvaluationPersistence.save_results(sample_results, filepath)
            loaded = EvaluationPersistence.load_results(filepath)

            assert len(loaded) == 2
            assert loaded[0].brain_version == "v1.0.0"
            assert loaded[0].status == EvaluationStatus.COMPLETED
            assert loaded[1].brain_version == "v1.1.0"
            assert loaded[1].status == EvaluationStatus.FAILED
        finally:
            filepath.unlink()

    def test_save_creates_directory(
        self, sample_results: list[EvaluationResult]
    ) -> None:
        """Test that save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "subdir" / "results.json"

            EvaluationPersistence.save_results(sample_results, filepath)

            assert filepath.exists()

    def test_load_nonexistent_file_raises(self) -> None:
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            EvaluationPersistence.load_results("/nonexistent/path/results.json")

    def test_append_results(self, sample_results: list[EvaluationResult]) -> None:
        """Test appending results to existing file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = Path(f.name)

        try:
            # Save initial results
            EvaluationPersistence.save_results(sample_results[:1], filepath)

            # Append more results
            EvaluationPersistence.append_results(sample_results[1:], filepath)

            # Load and verify
            loaded = EvaluationPersistence.load_results(filepath)
            assert len(loaded) == 2
        finally:
            filepath.unlink()

    def test_append_to_new_file(self, sample_results: list[EvaluationResult]) -> None:
        """Test appending when file doesn't exist creates new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "new_results.json"

            EvaluationPersistence.append_results(sample_results, filepath)

            loaded = EvaluationPersistence.load_results(filepath)
            assert len(loaded) == 2


class TestRunBatchEvaluation:
    """Tests for the convenience function run_batch_evaluation."""

    def test_run_batch_evaluation(self) -> None:
        """Test the convenience function."""
        results = run_batch_evaluation(["v1.0.0", "v1.1.0"])

        assert len(results) == 2
        assert all(r.is_successful() for r in results)

    def test_run_batch_evaluation_with_output(self) -> None:
        """Test the convenience function with output file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = Path(f.name)

        try:
            results = run_batch_evaluation(["v1.0.0"], output_path=filepath)

            assert len(results) == 1
            assert filepath.exists()

            # Verify file contents
            with open(filepath) as f:
                data = json.load(f)
                assert data["count"] == 1
                assert len(data["results"]) == 1
        finally:
            filepath.unlink()


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_results_leaderboard(self) -> None:
        """Test leaderboard with empty results."""
        leaderboard = Leaderboard()

        ranked = leaderboard.get_ranked_results()
        top_n = leaderboard.get_top_n(5)

        assert len(ranked) == 0
        assert len(top_n) == 0

    def test_single_result_leaderboard(self) -> None:
        """Test leaderboard with single result."""
        leaderboard = Leaderboard()
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=0.85,
        )

        leaderboard.add_result(result)
        ranked = leaderboard.get_ranked_results()

        assert len(ranked) == 1
        assert ranked[0][0].brain_version == "v1.0.0"

    @pytest.mark.asyncio
    async def test_all_failures_batch(self) -> None:
        """Test batch where all evaluations fail."""
        evaluator = BatchEvaluator()

        # Use very short timeout to force all timeouts
        results = await evaluator.evaluate_batch(
            ["v1.0.0", "v1.1.0"],
            timeout_seconds=0.0001,
        )

        assert len(results) == 2
        assert all(r.status == EvaluationStatus.TIMEOUT for r in results)

    def test_mixed_success_failure_leaderboard(self) -> None:
        """Test leaderboard with mix of success and failure."""
        leaderboard = Leaderboard()
        results = [
            EvaluationResult(
                brain_version="v1.0.0",
                status=EvaluationStatus.COMPLETED,
                accuracy=0.85,
                f1_score=0.80,
                win_rate=0.75,
                sharpe_ratio=1.5,
                max_drawdown=0.15,
            ),
            EvaluationResult(
                brain_version="v1.1.0",
                status=EvaluationStatus.FAILED,
                error_message="Failed",
            ),
        ]

        leaderboard.add_results(results)
        ranked = leaderboard.get_ranked_results()

        # Successful result should be first
        assert ranked[0][0].brain_version == "v1.0.0"
        assert ranked[0][1] > 0
        # Failed result should have 0 score
        assert ranked[1][0].brain_version == "v1.1.0"
        assert ranked[1][1] == 0.0

    def test_result_with_zero_metrics(self) -> None:
        """Test result with all zero metrics."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=0.0,
            precision=0.0,
            recall=0.0,
            f1_score=0.0,
            win_rate=0.0,
            sharpe_ratio=-3.0,  # Minimum normalized to 0
            max_drawdown=1.0,  # Maximum (100% drawdown)
        )

        assert result.accuracy == 0.0
        assert result.f1_score == 0.0

    def test_result_with_max_metrics(self) -> None:
        """Test result with maximum valid metrics."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=1.0,
            precision=1.0,
            recall=1.0,
            f1_score=1.0,
            win_rate=1.0,
            sharpe_ratio=3.0,  # Maximum normalized to 1
            max_drawdown=0.0,  # No drawdown
        )

        assert result.accuracy == 1.0
        assert result.f1_score == 1.0
