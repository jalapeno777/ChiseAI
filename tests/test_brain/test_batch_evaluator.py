"""Tests for brain batch evaluator (ST-CHISE-002).

Tests cover:
- Batch evaluation of 3-5 brain versions
- Evaluation metrics computation
- Leaderboard ranking
- Result persistence
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.brain.batch_evaluator import (
    BatchEvaluator,
    BatchEvaluationConfig,
    EvaluationMetrics,
    EvaluationResult,
    EvaluationStatus,
    Leaderboard,
)


class TestEvaluationMetrics:
    """Test EvaluationMetrics dataclass."""

    def test_default_values(self):
        """Test default metric values."""
        metrics = EvaluationMetrics()
        assert metrics.accuracy == 0.0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0
        assert metrics.win_rate == 0.0

    def test_custom_values(self):
        """Test setting custom metric values."""
        metrics = EvaluationMetrics(
            accuracy=0.85,
            precision=0.80,
            recall=0.75,
            f1_score=0.77,
            win_rate=0.65,
        )
        assert metrics.accuracy == 0.85
        assert metrics.precision == 0.80
        assert metrics.recall == 0.75
        assert metrics.f1_score == 0.77
        assert metrics.win_rate == 0.65

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = EvaluationMetrics(accuracy=0.85, precision=0.80)
        data = metrics.to_dict()
        assert data["accuracy"] == 0.85
        assert data["precision"] == 0.80
        assert "custom" in data

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "accuracy": 0.85,
            "precision": 0.80,
            "recall": 0.75,
            "f1_score": 0.77,
            "win_rate": 0.65,
            "profit_factor": 1.5,
            "sharpe_ratio": 1.2,
            "max_drawdown": 0.10,
            "total_signals": 100,
            "correct_predictions": 85,
            "false_positives": 10,
            "false_negatives": 5,
            "true_positives": 80,
            "true_negatives": 5,
            "avg_latency_ms": 50.0,
            "p95_latency_ms": 100.0,
            "p99_latency_ms": 150.0,
            "custom": {"custom_metric": 0.9},
        }
        metrics = EvaluationMetrics.from_dict(data)
        assert metrics.accuracy == 0.85
        assert metrics.custom == {"custom_metric": 0.9}

    def test_calculate_f1(self):
        """Test F1 score calculation."""
        # Perfect precision and recall
        metrics = EvaluationMetrics(precision=1.0, recall=1.0)
        assert metrics.calculate_f1() == 1.0

        # Zero precision and recall
        metrics = EvaluationMetrics(precision=0.0, recall=0.0)
        assert metrics.calculate_f1() == 0.0

        # Normal case
        metrics = EvaluationMetrics(precision=0.8, recall=0.6)
        expected_f1 = 2 * (0.8 * 0.6) / (0.8 + 0.6)
        assert abs(metrics.calculate_f1() - expected_f1) < 0.001


class TestEvaluationResult:
    """Test EvaluationResult dataclass."""

    def test_default_creation(self):
        """Test default result creation."""
        result = EvaluationResult(
            brain_version="v1.0.0",
            brain_name="Test Brain",
            status=EvaluationStatus.PENDING,
            metrics=EvaluationMetrics(),
            started_at=datetime.utcnow(),
        )
        assert result.brain_version == "v1.0.0"
        assert result.brain_name == "Test Brain"
        assert result.status == EvaluationStatus.PENDING
        assert result.evaluation_id  # Auto-generated

    def test_to_dict(self):
        """Test conversion to dictionary."""
        started_at = datetime.utcnow()
        result = EvaluationResult(
            brain_version="v1.0.0",
            brain_name="Test Brain",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(accuracy=0.85),
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_seconds=30.0,
        )
        data = result.to_dict()
        assert data["brain_version"] == "v1.0.0"
        assert data["status"] == "completed"
        assert data["metrics"]["accuracy"] == 0.85

    def test_from_dict(self):
        """Test creation from dictionary."""
        started_at = datetime.utcnow()
        data = {
            "evaluation_id": "test-123",
            "brain_version": "v1.0.0",
            "brain_name": "Test Brain",
            "status": "completed",
            "metrics": {"accuracy": 0.85, "precision": 0.80, "custom": {}},
            "started_at": started_at.isoformat(),
            "completed_at": None,
            "duration_seconds": 30.0,
            "error_message": None,
            "test_suite": "standard",
        }
        result = EvaluationResult.from_dict(data)
        assert result.brain_version == "v1.0.0"
        assert result.status == EvaluationStatus.COMPLETED


class TestLeaderboard:
    """Test Leaderboard functionality."""

    def test_empty_leaderboard(self):
        """Test empty leaderboard."""
        lb = Leaderboard()
        assert lb.results == []
        assert lb.get_winner() is None
        assert lb.get_top(3) == []

    def test_add_result(self):
        """Test adding a result."""
        lb = Leaderboard()
        result = EvaluationResult(
            brain_version="v1.0.0",
            brain_name="Brain A",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(f1_score=0.8),
            started_at=datetime.utcnow(),
        )
        lb.add_result(result)
        assert len(lb.results) == 1
        assert lb.get_winner() == result

    def test_sorting_by_f1(self):
        """Test sorting by F1 score."""
        lb = Leaderboard(sort_by="f1_score", ascending=False)

        results = [
            EvaluationResult(
                brain_version=f"v{i}.0.0",
                brain_name=f"Brain {i}",
                status=EvaluationStatus.COMPLETED,
                metrics=EvaluationMetrics(f1_score=0.5 + i * 0.1),
                started_at=datetime.utcnow(),
            )
            for i in range(3)
        ]

        lb.add_results(results)
        assert lb.results[0].brain_version == "v2.0.0"  # Highest F1
        assert lb.results[2].brain_version == "v0.0.0"  # Lowest F1

    def test_get_ranking(self):
        """Test getting ranked results."""
        lb = Leaderboard()

        for i in range(3):
            lb.add_result(
                EvaluationResult(
                    brain_version=f"v{i}.0.0",
                    brain_name=f"Brain {i}",
                    status=EvaluationStatus.COMPLETED,
                    metrics=EvaluationMetrics(f1_score=0.5 + i * 0.1),
                    started_at=datetime.utcnow(),
                )
            )

        ranking = lb.get_ranking()
        assert len(ranking) == 3
        assert ranking[0][0] == 1  # First rank
        assert ranking[0][1].brain_version == "v2.0.0"

    def test_compare_versions(self):
        """Test comparing two versions."""
        lb = Leaderboard()

        result_a = EvaluationResult(
            brain_version="v1.0.0",
            brain_name="Brain A",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(accuracy=0.8, f1_score=0.75),
            started_at=datetime.utcnow(),
        )
        result_b = EvaluationResult(
            brain_version="v2.0.0",
            brain_name="Brain B",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(accuracy=0.9, f1_score=0.85),
            started_at=datetime.utcnow(),
        )

        lb.add_results([result_a, result_b])

        comparison = lb.compare_versions("v1.0.0", "v2.0.0")
        assert comparison["winner"] == "v2.0.0"
        assert (
            abs(comparison["metrics_diff"]["accuracy"]["difference"] - (-0.1)) < 0.001
        )

    def test_to_markdown(self):
        """Test markdown generation."""
        lb = Leaderboard()
        lb.add_result(
            EvaluationResult(
                brain_version="v1.0.0",
                brain_name="Brain A",
                status=EvaluationStatus.COMPLETED,
                metrics=EvaluationMetrics(
                    accuracy=0.8,
                    precision=0.75,
                    recall=0.7,
                    f1_score=0.72,
                    win_rate=0.65,
                ),
                started_at=datetime.utcnow(),
            )
        )

        md = lb.to_markdown()
        assert "# Brain Evaluation Leaderboard" in md
        assert "v1.0.0" in md
        assert "0.800" in md


class TestBatchEvaluator:
    """Test BatchEvaluator functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def evaluator(self, temp_dir):
        """Create batch evaluator with temp directory."""
        config = BatchEvaluationConfig(
            results_dir=temp_dir,
            save_results=True,
        )
        return BatchEvaluator(config)

    @pytest.mark.asyncio
    async def test_evaluate_single_brain(self, evaluator):
        """Test evaluating a single brain."""

        async def mock_evaluator():
            return EvaluationMetrics(accuracy=0.85)

        result = await evaluator.evaluate_brain(
            brain_version="v1.0.0",
            brain_name="Test Brain",
            evaluator_func=mock_evaluator,
        )

        assert result.brain_version == "v1.0.0"
        assert result.status == EvaluationStatus.COMPLETED
        assert result.metrics.accuracy == 0.85

    @pytest.mark.asyncio
    async def test_evaluate_batch(self, evaluator):
        """Test batch evaluation of 3 versions."""

        async def mock_evaluator_v1():
            return EvaluationMetrics(accuracy=0.85, f1_score=0.80)

        async def mock_evaluator_v2():
            return EvaluationMetrics(accuracy=0.90, f1_score=0.85)

        async def mock_evaluator_v3():
            return EvaluationMetrics(accuracy=0.80, f1_score=0.75)

        brain_configs = [
            ("v1.0.0", "Brain A", mock_evaluator_v1),
            ("v2.0.0", "Brain B", mock_evaluator_v2),
            ("v3.0.0", "Brain C", mock_evaluator_v3),
        ]

        results = await evaluator.evaluate_batch(brain_configs)

        assert len(results) == 3
        assert all(r.status == EvaluationStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_batch_size_validation(self, evaluator):
        """Test batch size validation (3-5 versions)."""
        # Too few
        with pytest.raises(ValueError, match="at least 3"):
            await evaluator.evaluate_batch(
                [
                    ("v1.0.0", "Brain A", lambda: None),
                ]
            )

        # Too many
        with pytest.raises(ValueError, match="maximum 5"):
            await evaluator.evaluate_batch(
                [(f"v{i}.0.0", f"Brain {i}", lambda: None) for i in range(6)]
            )

    @pytest.mark.asyncio
    async def test_evaluation_timeout(self, evaluator):
        """Test evaluation timeout handling."""
        evaluator.config.timeout_seconds = 0.1

        async def slow_evaluator():
            await asyncio.sleep(1.0)  # Will timeout
            return EvaluationMetrics()

        result = await evaluator.evaluate_brain(
            brain_version="v1.0.0",
            brain_name="Slow Brain",
            evaluator_func=slow_evaluator,
        )

        assert result.status == EvaluationStatus.TIMEOUT
        assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_evaluation_error(self, evaluator):
        """Test evaluation error handling."""

        async def failing_evaluator():
            raise ValueError("Test error")

        result = await evaluator.evaluate_brain(
            brain_version="v1.0.0",
            brain_name="Failing Brain",
            evaluator_func=failing_evaluator,
        )

        assert result.status == EvaluationStatus.FAILED
        assert "Test error" in result.error_message

    @pytest.mark.asyncio
    async def test_result_persistence(self, evaluator, temp_dir):
        """Test that results are saved to disk."""

        async def mock_evaluator():
            return EvaluationMetrics(accuracy=0.85)

        result = await evaluator.evaluate_brain(
            brain_version="v1.0.0",
            brain_name="Test Brain",
            evaluator_func=mock_evaluator,
        )

        # Check file was created
        saved_files = list(temp_dir.glob("*.json"))
        assert len(saved_files) == 1

        # Check content
        with open(saved_files[0]) as f:
            data = json.load(f)
            assert data["brain_version"] == "v1.0.0"

    @pytest.mark.asyncio
    async def test_load_result(self, evaluator):
        """Test loading saved result."""

        async def mock_evaluator():
            return EvaluationMetrics(accuracy=0.85)

        result = await evaluator.evaluate_brain(
            brain_version="v1.0.0",
            brain_name="Test Brain",
            evaluator_func=mock_evaluator,
        )

        loaded = evaluator.load_result(result.evaluation_id)
        assert loaded is not None
        assert loaded.brain_version == "v1.0.0"

    @pytest.mark.asyncio
    async def test_create_leaderboard(self, evaluator):
        """Test creating leaderboard from results."""
        brain_configs = [
            ("v1.0.0", "Brain A", lambda: EvaluationMetrics(f1_score=0.80)),
            ("v2.0.0", "Brain B", lambda: EvaluationMetrics(f1_score=0.85)),
            ("v3.0.0", "Brain C", lambda: EvaluationMetrics(f1_score=0.75)),
        ]

        # Need to make these async
        async_configs = []
        for v, n, f in brain_configs:

            async def make_async(f=f):
                return f()

            async_configs.append((v, n, make_async))

        await evaluator.evaluate_batch(async_configs)
        leaderboard = evaluator.create_leaderboard()

        assert len(leaderboard.results) == 3
        assert leaderboard.get_winner().brain_version == "v2.0.0"


class TestBatchEvaluationConfig:
    """Test BatchEvaluationConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = BatchEvaluationConfig()
        assert config.max_concurrent == 3
        assert config.timeout_seconds == 1800.0
        assert config.test_suite == "standard"
        assert config.save_results is True

    def test_custom_config(self):
        """Test custom configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = BatchEvaluationConfig(
                max_concurrent=5,
                timeout_seconds=3600.0,
                test_suite="comprehensive",
                save_results=False,
                results_dir=Path(tmpdir),
            )
            assert config.max_concurrent == 5
            assert config.timeout_seconds == 3600.0
            assert config.test_suite == "comprehensive"
            assert config.save_results is False
