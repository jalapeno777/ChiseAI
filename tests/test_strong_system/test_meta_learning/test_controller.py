"""Tests for meta-learning controller module.

Tests Task, Episode, TaskDistribution, and MetaLearningController classes.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.strong_system.meta_learning.controller import (
    Episode,
    MetaLearningController,
    Task,
    TaskDistribution,
)


class TestTask:
    """Tests for Task class."""

    def test_task_creation(self):
        """Test basic task creation."""
        data = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        labels = np.array([0, 1, 0])

        task = Task(task_id="test_task", data=data, labels=labels)

        assert task.task_id == "test_task"
        assert task.n_samples == 3
        assert task.input_dim == (2,)
        assert task.output_dim == 1

    def test_task_with_metadata(self):
        """Test task creation with metadata."""
        data = np.random.randn(10, 5)
        labels = np.random.randint(0, 3, 10)
        metadata = {"domain": "vision", "difficulty": "easy"}

        task = Task(
            task_id="task_with_meta", data=data, labels=labels, metadata=metadata
        )

        assert task.metadata["domain"] == "vision"
        assert task.metadata["difficulty"] == "easy"

    def test_task_validation_mismatched_lengths(self):
        """Test that mismatched data/labels raises error."""
        data = np.array([[1.0], [2.0]])
        labels = np.array([0])  # Only 1 label

        with pytest.raises(ValueError, match="same length"):
            Task(task_id="bad_task", data=data, labels=labels)

    def test_task_sample(self):
        """Test sampling from task."""
        data = np.random.randn(100, 10)
        labels = np.random.randint(0, 5, 100)
        task = Task(task_id="sample_task", data=data, labels=labels)

        sampled_data, sampled_labels = task.sample(n_samples=20, seed=42)

        assert len(sampled_data) == 20
        assert len(sampled_labels) == 20
        assert sampled_data.shape[1] == 10

    def test_task_sample_too_many(self):
        """Test sampling more than available raises error."""
        data = np.random.randn(10, 5)
        labels = np.random.randint(0, 3, 10)
        task = Task(task_id="small_task", data=data, labels=labels)

        with pytest.raises(ValueError, match="Cannot sample"):
            task.sample(n_samples=20)

    def test_task_sample_support_query(self):
        """Test support/query sampling."""
        data = np.random.randn(100, 10)
        labels = np.random.randint(0, 5, 100)
        task = Task(task_id="sq_task", data=data, labels=labels)

        (support_data, support_labels), (query_data, query_labels) = (
            task.sample_support_query(k_shot=5, q_query=15, seed=42)
        )

        assert len(support_data) == 5
        assert len(support_labels) == 5
        assert len(query_data) == 15
        assert len(query_labels) == 15

    def test_task_sample_support_query_too_many(self):
        """Test support/query with too many samples raises error."""
        data = np.random.randn(20, 5)
        labels = np.random.randint(0, 3, 20)
        task = Task(task_id="small_sq_task", data=data, labels=labels)

        with pytest.raises(ValueError, match="exceeds"):
            task.sample_support_query(k_shot=10, q_query=15)


class TestEpisode:
    """Tests for Episode class."""

    def test_episode_creation(self):
        """Test basic episode creation."""
        support_data = np.random.randn(10, 5)
        support_labels = np.random.randint(0, 3, 10)
        query_data = np.random.randn(20, 5)
        query_labels = np.random.randint(0, 3, 20)

        episode = Episode(
            task_id="task_1",
            support_data=support_data,
            support_labels=support_labels,
            query_data=query_data,
            query_labels=query_labels,
        )

        assert episode.task_id == "task_1"
        assert episode.n_support == 10
        assert episode.n_query == 20

    def test_episode_with_metadata(self):
        """Test episode creation with metadata."""
        episode = Episode(
            task_id="task_1",
            support_data=np.random.randn(5, 3),
            support_labels=np.random.randint(0, 2, 5),
            query_data=np.random.randn(10, 3),
            query_labels=np.random.randint(0, 2, 10),
            metadata={"k_shot": 5, "q_query": 10},
        )

        assert episode.metadata["k_shot"] == 5

    def test_episode_validation_mismatched_support(self):
        """Test mismatched support data/labels raises error."""
        with pytest.raises(ValueError, match="Support data and labels"):
            Episode(
                task_id="bad_episode",
                support_data=np.random.randn(5, 3),
                support_labels=np.random.randint(0, 2, 3),  # Wrong length
                query_data=np.random.randn(10, 3),
                query_labels=np.random.randint(0, 2, 10),
            )

    def test_episode_validation_mismatched_query(self):
        """Test mismatched query data/labels raises error."""
        with pytest.raises(ValueError, match="Query data and labels"):
            Episode(
                task_id="bad_episode",
                support_data=np.random.randn(5, 3),
                support_labels=np.random.randint(0, 2, 5),
                query_data=np.random.randn(10, 3),
                query_labels=np.random.randint(0, 2, 5),  # Wrong length
            )


class TestTaskDistribution:
    """Tests for TaskDistribution class."""

    def test_distribution_creation(self):
        """Test empty distribution creation."""
        distribution = TaskDistribution()
        assert distribution.n_tasks == 0

    def test_add_task(self):
        """Test adding tasks to distribution."""
        distribution = TaskDistribution()
        task = Task(
            task_id="task_1",
            data=np.random.randn(50, 10),
            labels=np.random.randint(0, 3, 50),
        )

        distribution.add_task(task)

        assert distribution.n_tasks == 1
        assert "task_1" in distribution.task_ids

    def test_add_task_duplicate_id(self):
        """Test adding duplicate task raises error."""
        distribution = TaskDistribution()
        task = Task(
            task_id="task_1",
            data=np.random.randn(50, 10),
            labels=np.random.randint(0, 3, 50),
        )

        distribution.add_task(task)

        with pytest.raises(ValueError, match="already exists"):
            distribution.add_task(task)

    def test_get_task(self):
        """Test getting task by ID."""
        distribution = TaskDistribution()
        task = Task(
            task_id="task_1",
            data=np.random.randn(50, 10),
            labels=np.random.randint(0, 3, 50),
        )
        distribution.add_task(task)

        retrieved = distribution.get_task("task_1")
        assert retrieved.task_id == "task_1"

    def test_get_task_not_found(self):
        """Test getting non-existent task raises error."""
        distribution = TaskDistribution()

        with pytest.raises(KeyError, match="not found"):
            distribution.get_task("nonexistent")

    def test_remove_task(self):
        """Test removing task from distribution."""
        distribution = TaskDistribution()
        task = Task(
            task_id="task_1",
            data=np.random.randn(50, 10),
            labels=np.random.randint(0, 3, 50),
        )
        distribution.add_task(task)

        distribution.remove_task("task_1")

        assert distribution.n_tasks == 0

    def test_sample_task(self):
        """Test sampling a task."""
        distribution = TaskDistribution()
        for i in range(5):
            task = Task(
                task_id=f"task_{i}",
                data=np.random.randn(50, 10),
                labels=np.random.randint(0, 3, 50),
            )
            distribution.add_task(task)

        sampled = distribution.sample_task(seed=42)
        assert sampled.task_id in distribution.task_ids

    def test_sample_task_empty(self):
        """Test sampling from empty distribution raises error."""
        distribution = TaskDistribution()

        with pytest.raises(ValueError, match="No tasks"):
            distribution.sample_task()

    def test_sample_tasks(self):
        """Test sampling multiple tasks."""
        distribution = TaskDistribution()
        for i in range(10):
            task = Task(
                task_id=f"task_{i}",
                data=np.random.randn(50, 10),
                labels=np.random.randint(0, 3, 50),
            )
            distribution.add_task(task)

        sampled = distribution.sample_tasks(n_tasks=5, seed=42)
        assert len(sampled) == 5

    def test_split_tasks(self):
        """Test splitting tasks into train/test."""
        distribution = TaskDistribution()
        for i in range(10):
            task = Task(
                task_id=f"task_{i}",
                data=np.random.randn(50, 10),
                labels=np.random.randint(0, 3, 50),
            )
            distribution.add_task(task)

        distribution.split_tasks(train_ratio=0.8, seed=42)

        assert len(distribution.train_task_ids) == 8
        assert len(distribution.test_task_ids) == 2

    def test_split_tasks_invalid_ratio(self):
        """Test invalid split ratio raises error."""
        distribution = TaskDistribution()

        with pytest.raises(ValueError, match="train_ratio"):
            distribution.split_tasks(train_ratio=1.5)

    def test_get_statistics(self):
        """Test getting distribution statistics."""
        distribution = TaskDistribution()
        for i in range(5):
            task = Task(
                task_id=f"task_{i}",
                data=np.random.randn(50 + i * 10, 10),
                labels=np.random.randint(0, 3, 50 + i * 10),
            )
            distribution.add_task(task)

        stats = distribution.get_statistics()

        assert stats["n_total_tasks"] == 5
        assert "avg_samples_per_task" in stats


class TestMetaLearningController:
    """Tests for MetaLearningController class."""

    def test_controller_creation(self):
        """Test controller creation."""
        controller = MetaLearningController()
        assert controller.n_tasks == 0

    def test_add_task(self):
        """Test adding task via controller."""
        controller = MetaLearningController()
        data = np.random.randn(100, 10)
        labels = np.random.randint(0, 3, 100)

        task_id = controller.add_task(task_id="my_task", data=data, labels=labels)

        assert task_id == "my_task"
        assert controller.n_tasks == 1

    def test_add_task_auto_id(self):
        """Test adding task with auto-generated ID."""
        controller = MetaLearningController()
        data = np.random.randn(100, 10)
        labels = np.random.randint(0, 3, 100)

        task_id = controller.add_task(task_id=None, data=data, labels=labels)

        assert task_id.startswith("task_")
        assert controller.n_tasks == 1

    def test_get_task(self):
        """Test getting task from controller."""
        controller = MetaLearningController()
        data = np.random.randn(100, 10)
        labels = np.random.randint(0, 3, 100)
        controller.add_task(task_id="test_task", data=data, labels=labels)

        task = controller.get_task("test_task")
        assert task.task_id == "test_task"

    def test_split_tasks(self):
        """Test splitting tasks via controller."""
        controller = MetaLearningController()
        for i in range(10):
            controller.add_task(
                task_id=f"task_{i}",
                data=np.random.randn(100, 10),
                labels=np.random.randint(0, 3, 100),
            )

        controller.split_tasks(train_ratio=0.8, seed=42)

        stats = controller.get_statistics()
        assert stats["n_train_tasks"] == 8
        assert stats["n_test_tasks"] == 2

    def test_sample_episode(self):
        """Test sampling a single episode."""
        controller = MetaLearningController()
        for i in range(5):
            controller.add_task(
                task_id=f"task_{i}",
                data=np.random.randn(100, 10),
                labels=np.random.randint(0, 3, 100),
            )

        episode = controller.sample_episode(k_shot=5, q_query=15, seed=42)

        assert episode.n_support == 5
        assert episode.n_query == 15
        assert episode.task_id in controller.task_ids

    def test_sample_episodes(self):
        """Test sampling multiple episodes."""
        controller = MetaLearningController()
        for i in range(5):
            controller.add_task(
                task_id=f"task_{i}",
                data=np.random.randn(100, 10),
                labels=np.random.randint(0, 3, 100),
            )

        episodes = controller.sample_episodes(
            n_episodes=10, k_shot=5, q_query=15, seed=42
        )

        assert len(episodes) == 10
        for ep in episodes:
            assert ep.n_support == 5
            assert ep.n_query == 15

    def test_create_episode_batch(self):
        """Test creating episode batch from specific tasks."""
        controller = MetaLearningController()
        for i in range(5):
            controller.add_task(
                task_id=f"task_{i}",
                data=np.random.randn(100, 10),
                labels=np.random.randint(0, 3, 100),
            )

        episodes = controller.create_episode_batch(
            task_ids=["task_0", "task_1", "task_2"], k_shot=5, q_query=15
        )

        assert len(episodes) == 3
        assert episodes[0].task_id == "task_0"
        assert episodes[1].task_id == "task_1"
        assert episodes[2].task_id == "task_2"

    def test_remove_task(self):
        """Test removing task from controller."""
        controller = MetaLearningController()
        controller.add_task(
            task_id="removable_task",
            data=np.random.randn(100, 10),
            labels=np.random.randint(0, 3, 100),
        )

        controller.remove_task("removable_task")

        assert controller.n_tasks == 0

    def test_get_statistics(self):
        """Test getting controller statistics."""
        controller = MetaLearningController()
        for i in range(5):
            controller.add_task(
                task_id=f"task_{i}",
                data=np.random.randn(100, 10),
                labels=np.random.randint(0, 3, 100),
            )

        stats = controller.get_statistics()

        assert stats["n_total_tasks"] == 5
        assert "avg_samples_per_task" in stats
