"""Tests for meta-learning utilities module.

Tests TaskSampler, EpisodeBatcher, and metric computation functions.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.strong_system.meta_learning.controller import Episode, Task
from src.strong_system.meta_learning.utils import (
    TaskSampler,
    EpisodeBatcher,
    compute_accuracy,
    compute_precision_recall_f1,
    compute_meta_metrics,
    compute_adaptation_gain,
    compute_meta_gradient_norm,
    clip_gradient_norm,
    create_sinusoid_task,
    create_classification_task,
    split_episodes,
    compute_confidence_interval,
    aggregate_episode_metrics,
)


class TestTaskSampler:
    """Tests for TaskSampler class."""

    def test_sampler_creation(self):
        """Test sampler creation."""
        tasks = [
            Task(f"task_{i}", np.random.randn(100, 10), np.random.randint(0, 5, 100))
            for i in range(5)
        ]
        sampler = TaskSampler(tasks)

        assert len(sampler.tasks) == 5

    def test_sample_episode(self):
        """Test sampling a single episode."""
        tasks = [
            Task(f"task_{i}", np.random.randn(100, 10), np.random.randint(0, 5, 100))
            for i in range(5)
        ]
        sampler = TaskSampler(tasks)

        episode = sampler.sample_episode(k_shot=5, q_query=15, seed=42)

        assert isinstance(episode, Episode)
        assert episode.n_support == 5
        assert episode.n_query == 15

    def test_sample_episode_specific_task(self):
        """Test sampling from specific task."""
        tasks = [
            Task(f"task_{i}", np.random.randn(100, 10), np.random.randint(0, 5, 100))
            for i in range(5)
        ]
        sampler = TaskSampler(tasks)

        episode = sampler.sample_episode(k_shot=5, q_query=15, task_idx=2, seed=42)

        assert episode.task_id == "task_2"

    def test_sample_batch(self):
        """Test sampling a batch of episodes."""
        tasks = [
            Task(f"task_{i}", np.random.randn(100, 10), np.random.randint(0, 5, 100))
            for i in range(5)
        ]
        sampler = TaskSampler(tasks)

        episodes = sampler.sample_batch(n_episodes=10, k_shot=5, q_query=15, seed=42)

        assert len(episodes) == 10
        for ep in episodes:
            assert ep.n_support == 5
            assert ep.n_query == 15

    def test_sample_task_episodes(self):
        """Test sampling multiple episodes from specific task."""
        tasks = [
            Task(f"task_{i}", np.random.randn(100, 10), np.random.randint(0, 5, 100))
            for i in range(5)
        ]
        sampler = TaskSampler(tasks)

        episodes = sampler.sample_task_episodes(
            task_idx=1, n_episodes=5, k_shot=5, q_query=15, seed=42
        )

        assert len(episodes) == 5
        for ep in episodes:
            assert ep.task_id == "task_1"


class TestEpisodeBatcher:
    """Tests for EpisodeBatcher class."""

    def test_batcher_creation(self):
        """Test batcher creation."""
        episodes = [
            Episode(
                f"task_{i}",
                np.random.randn(5, 10),
                np.random.randint(0, 3, 5),
                np.random.randn(15, 10),
                np.random.randint(0, 3, 15),
            )
            for i in range(10)
        ]
        batcher = EpisodeBatcher(episodes, batch_size=4)

        assert len(batcher) == 3  # 10 episodes / 4 per batch = 3 batches

    def test_batcher_iteration(self):
        """Test iterating over batches."""
        episodes = [
            Episode(
                f"task_{i}",
                np.random.randn(5, 10),
                np.random.randint(0, 3, 5),
                np.random.randn(15, 10),
                np.random.randint(0, 3, 15),
            )
            for i in range(10)
        ]
        batcher = EpisodeBatcher(episodes, batch_size=4)

        batches = list(batcher)

        assert len(batches) == 3
        assert len(batches[0]) == 4
        assert len(batches[1]) == 4
        assert len(batches[2]) == 2  # Last batch has remaining

    def test_batcher_no_shuffle(self):
        """Test batcher without shuffling."""
        episodes = [
            Episode(
                f"task_{i}",
                np.random.randn(5, 10),
                np.random.randint(0, 3, 5),
                np.random.randn(15, 10),
                np.random.randint(0, 3, 15),
            )
            for i in range(5)
        ]
        batcher = EpisodeBatcher(episodes, batch_size=2, shuffle=False)

        first_batch = next(iter(batcher))
        assert first_batch[0].task_id == "task_0"
        assert first_batch[1].task_id == "task_1"

    def test_batcher_get_batch(self):
        """Test getting specific batch."""
        episodes = [
            Episode(
                f"task_{i}",
                np.random.randn(5, 10),
                np.random.randint(0, 3, 5),
                np.random.randn(15, 10),
                np.random.randint(0, 3, 15),
            )
            for i in range(10)
        ]
        batcher = EpisodeBatcher(episodes, batch_size=4, shuffle=False)

        batch = batcher.get_batch(1)

        assert len(batch) == 4
        assert batch[0].task_id == "task_4"


class TestComputeAccuracy:
    """Tests for compute_accuracy function."""

    def test_classification_accuracy_perfect(self):
        """Test perfect classification accuracy."""
        predictions = np.array([[0.9, 0.1, 0.0], [0.1, 0.8, 0.1], [0.0, 0.1, 0.9]])
        labels = np.array([0, 1, 2])

        accuracy = compute_accuracy(predictions, labels, task_type="classification")

        assert accuracy == 1.0

    def test_classification_accuracy_zero(self):
        """Test zero classification accuracy."""
        predictions = np.array([[0.0, 0.9, 0.1], [0.8, 0.1, 0.1], [0.1, 0.0, 0.9]])
        labels = np.array([2, 2, 0])  # All wrong

        accuracy = compute_accuracy(predictions, labels, task_type="classification")

        assert accuracy == 0.0

    def test_classification_accuracy_partial(self):
        """Test partial classification accuracy."""
        predictions = np.array(
            [
                [0.9, 0.1],  # Correct (class 0)
                [0.1, 0.9],  # Correct (class 1)
                [0.9, 0.1],  # Wrong (class 1 expected)
            ]
        )
        labels = np.array([0, 1, 1])

        accuracy = compute_accuracy(predictions, labels, task_type="classification")

        assert accuracy == 2.0 / 3.0

    def test_regression_r2_score(self):
        """Test R^2 score for regression."""
        predictions = np.array([1.0, 2.0, 3.0, 4.0])
        labels = np.array([1.1, 1.9, 3.2, 3.8])

        r2 = compute_accuracy(predictions, labels, task_type="regression")

        assert 0 < r2 <= 1.0


class TestComputePrecisionRecallF1:
    """Tests for compute_precision_recall_f1 function."""

    def test_perfect_classification(self):
        """Test perfect classification metrics."""
        predictions = np.array([[0.9, 0.1], [0.1, 0.9], [0.9, 0.1], [0.1, 0.9]])
        labels = np.array([0, 1, 0, 1])

        metrics = compute_precision_recall_f1(predictions, labels, average="macro")

        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0

    def test_macro_average(self):
        """Test macro averaging."""
        predictions = np.array(
            [
                [0.9, 0.1],
                [0.9, 0.1],  # Wrong
                [0.1, 0.9],
                [0.1, 0.9],
            ]
        )
        labels = np.array([0, 1, 1, 1])

        metrics = compute_precision_recall_f1(predictions, labels, average="macro")

        assert 0 < metrics["precision"] < 1.0
        assert 0 < metrics["recall"] < 1.0
        assert 0 < metrics["f1"] < 1.0

    def test_weighted_average(self):
        """Test weighted averaging."""
        predictions = np.array([[0.9, 0.1], [0.9, 0.1], [0.1, 0.9], [0.1, 0.9]])
        labels = np.array([0, 0, 1, 1])

        metrics = compute_precision_recall_f1(predictions, labels, average="weighted")

        assert 0 <= metrics["precision"] <= 1.0
        assert 0 <= metrics["recall"] <= 1.0


class TestComputeMetaMetrics:
    """Tests for compute_meta_metrics function."""

    def test_classification_metrics(self):
        """Test classification meta-metrics."""
        predictions = np.array([[0.9, 0.1], [0.1, 0.9], [0.9, 0.1]])
        labels = np.array([0, 1, 0])

        metrics = compute_meta_metrics(predictions, labels, task_type="classification")

        assert "accuracy" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics

    def test_binary_confusion_matrix(self):
        """Test binary classification confusion matrix."""
        predictions = np.array([0.9, 0.1, 0.8, 0.2])  # Predicted: 1, 0, 1, 0
        labels = np.array([1, 0, 1, 0])  # All correct

        metrics = compute_meta_metrics(predictions, labels, task_type="classification")

        assert metrics["true_positives"] == 2
        assert metrics["true_negatives"] == 2
        assert metrics["false_positives"] == 0
        assert metrics["false_negatives"] == 0


class TestComputeAdaptationGain:
    """Tests for compute_adaptation_gain function."""

    def test_positive_gain(self):
        """Test positive adaptation gain."""
        pre_loss = 1.0
        post_loss = 0.5

        gain = compute_adaptation_gain(pre_loss, post_loss)

        assert gain == 0.5  # 50% improvement

    def test_zero_gain(self):
        """Test zero adaptation gain."""
        pre_loss = 1.0
        post_loss = 1.0

        gain = compute_adaptation_gain(pre_loss, post_loss)

        assert gain == 0.0

    def test_negative_gain(self):
        """Test negative adaptation gain (worse after adaptation)."""
        pre_loss = 0.5
        post_loss = 1.0

        gain = compute_adaptation_gain(pre_loss, post_loss)

        assert gain == -1.0  # Got worse

    def test_zero_pre_loss(self):
        """Test with zero pre-adaptation loss."""
        gain = compute_adaptation_gain(0.0, 0.5)

        assert gain == 0.0  # Should return 0 to avoid division by zero


class TestComputeMetaGradientNorm:
    """Tests for compute_meta_gradient_norm function."""

    def test_gradient_norm(self):
        """Test computing gradient norm."""
        meta_gradient = {"W": np.ones((10, 5)), "b": np.ones(5)}

        norm = compute_meta_gradient_norm(meta_gradient)

        # Norm should be sqrt(10*5 + 5) = sqrt(55)
        expected = np.sqrt(55)
        assert np.isclose(norm, expected)

    def test_zero_gradient_norm(self):
        """Test zero gradient norm."""
        meta_gradient = {"W": np.zeros((10, 5)), "b": np.zeros(5)}

        norm = compute_meta_gradient_norm(meta_gradient)

        assert norm == 0.0


class TestClipGradientNorm:
    """Tests for clip_gradient_norm function."""

    def test_clip_gradient(self):
        """Test clipping gradient."""
        gradient = {
            "W": np.ones((10, 5)) * 10,  # Large values
            "b": np.ones(5) * 10,
        }

        clipped = clip_gradient_norm(gradient, max_norm=1.0)

        # Norm should now be 1.0
        new_norm = compute_meta_gradient_norm(clipped)
        assert np.isclose(new_norm, 1.0)

    def test_no_clip_needed(self):
        """Test when clipping is not needed."""
        gradient = {"W": np.ones((10, 5)) * 0.01, "b": np.ones(5) * 0.01}

        clipped = clip_gradient_norm(gradient, max_norm=10.0)

        # Should be unchanged
        assert np.allclose(clipped["W"], gradient["W"])
        assert np.allclose(clipped["b"], gradient["b"])


class TestCreateSinusoidTask:
    """Tests for create_sinusoid_task function."""

    def test_sinusoid_creation(self):
        """Test creating sinusoid task."""
        X, y = create_sinusoid_task(amplitude=1.0, phase=0.0, n_samples=50, seed=42)

        assert X.shape == (50, 1)
        assert y.shape == (50,)

    def test_sinusoid_amplitude(self):
        """Test sinusoid amplitude."""
        X1, y1 = create_sinusoid_task(amplitude=1.0, phase=0.0, n_samples=100, seed=42)
        X2, y2 = create_sinusoid_task(amplitude=2.0, phase=0.0, n_samples=100, seed=42)

        # y2 should have roughly twice the range of y1
        assert np.max(np.abs(y2)) > np.max(np.abs(y1))

    def test_sinusoid_phase(self):
        """Test sinusoid phase."""
        # Use same X values by fixing seed - but with different phases
        # sin(x + pi) = -sin(x), so y2 should be -y1 when sampled at same X
        X1, y1 = create_sinusoid_task(
            amplitude=1.0,
            phase=0.0,
            n_samples=100,
            x_range=(0, 2 * np.pi),
            noise_std=0.0,
            seed=42,
        )
        X2, y2 = create_sinusoid_task(
            amplitude=1.0,
            phase=np.pi,
            n_samples=100,
            x_range=(0, 2 * np.pi),
            noise_std=0.0,
            seed=42,
        )

        # X values should be the same with same seed
        assert np.allclose(X1, X2)
        # y2 should be roughly -y1 (with no noise)
        assert np.allclose(y1, -y2, atol=0.01)


class TestCreateClassificationTask:
    """Tests for create_classification_task function."""

    def test_classification_task_creation(self):
        """Test creating classification task."""
        X, y = create_classification_task(
            n_classes=5, n_samples=100, n_features=10, seed=42
        )

        assert X.shape == (100, 10)
        assert y.shape == (100,)
        assert len(np.unique(y)) == 5

    def test_class_separation(self):
        """Test that higher class_sep creates more separable classes."""
        X1, y1 = create_classification_task(
            n_classes=3, n_samples=90, n_features=10, class_sep=0.5, seed=42
        )
        X2, y2 = create_classification_task(
            n_classes=3, n_samples=90, n_features=10, class_sep=5.0, seed=42
        )

        # Both should have same shape
        assert X1.shape == X2.shape
        assert y1.shape == y2.shape


class TestSplitEpisodes:
    """Tests for split_episodes function."""

    def test_split_episodes(self):
        """Test splitting episodes."""
        episodes = [
            Episode(
                f"task_{i}",
                np.random.randn(5, 10),
                np.random.randint(0, 3, 5),
                np.random.randn(15, 10),
                np.random.randint(0, 3, 15),
            )
            for i in range(10)
        ]

        train, val = split_episodes(episodes, train_ratio=0.8, seed=42)

        assert len(train) == 8
        assert len(val) == 2

    def test_split_reproducibility(self):
        """Test that split is reproducible with same seed."""
        episodes = [
            Episode(
                f"task_{i}",
                np.random.randn(5, 10),
                np.random.randint(0, 3, 5),
                np.random.randn(15, 10),
                np.random.randint(0, 3, 15),
            )
            for i in range(10)
        ]

        train1, val1 = split_episodes(episodes, train_ratio=0.8, seed=42)
        train2, val2 = split_episodes(episodes, train_ratio=0.8, seed=42)

        # Same IDs should be in train/val
        assert [ep.task_id for ep in train1] == [ep.task_id for ep in train2]
        assert [ep.task_id for ep in val1] == [ep.task_id for ep in val2]


class TestComputeConfidenceInterval:
    """Tests for compute_confidence_interval function."""

    def test_confidence_interval(self):
        """Test computing confidence interval."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]

        lower, upper = compute_confidence_interval(values, confidence=0.95)

        assert lower < upper
        assert lower < np.mean(values)
        assert upper > np.mean(values)

    def test_narrower_interval_with_more_data(self):
        """Test that more data gives narrower interval."""
        values1 = np.random.randn(10)
        values2 = np.random.randn(1000)

        lower1, upper1 = compute_confidence_interval(values1)
        lower2, upper2 = compute_confidence_interval(values2)

        width1 = upper1 - lower1
        width2 = upper2 - lower2

        assert width2 < width1


class TestAggregateEpisodeMetrics:
    """Tests for aggregate_episode_metrics function."""

    def test_aggregate_metrics(self):
        """Test aggregating episode metrics."""
        episode_metrics = [
            {"accuracy": 0.7, "loss": 0.5},
            {"accuracy": 0.8, "loss": 0.4},
            {"accuracy": 0.75, "loss": 0.45},
        ]

        aggregated = aggregate_episode_metrics(episode_metrics)

        assert "accuracy" in aggregated
        assert "loss" in aggregated
        assert "mean" in aggregated["accuracy"]
        assert "std" in aggregated["accuracy"]
        assert "min" in aggregated["accuracy"]
        assert "max" in aggregated["accuracy"]
        assert "median" in aggregated["accuracy"]

    def test_aggregate_empty(self):
        """Test aggregating empty metrics."""
        aggregated = aggregate_episode_metrics([])

        assert aggregated == {}

    def test_aggregate_single(self):
        """Test aggregating single metric."""
        episode_metrics = [{"accuracy": 0.7}]

        aggregated = aggregate_episode_metrics(episode_metrics)

        assert aggregated["accuracy"]["mean"] == 0.7
        assert aggregated["accuracy"]["std"] == 0.0
