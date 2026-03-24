"""Meta-learning controller for task distribution and episode generation.

Provides the MetaLearningController class for managing task distributions,
sampling episodes, and handling meta-train/meta-test splits for MAML-style
training.

Example:
    >>> from src.strong_system.meta_learning.controller import MetaLearningController
    >>> controller = MetaLearningController()
    >>>
    >>> # Add tasks
    >>> controller.add_task("task_1", {"data": X1, "labels": y1})
    >>> controller.add_task("task_2", {"data": X2, "labels": y2})
    >>>
    >>> # Split into meta-train and meta-test
    >>> controller.split_tasks(train_ratio=0.8)
    >>>
    >>> # Sample training episodes
    >>> episodes = controller.sample_episodes(
    ...     n_episodes=10,
    ...     k_shot=5,
    ...     split="train"
    ... )
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, TypeVar

import numpy as np

T = TypeVar("T")


@dataclass
class Task:
    """Represents a single task with data and metadata.

    A task consists of input data and corresponding labels/targets,
    along with optional metadata for task identification and organization.

    Attributes:
        task_id: Unique identifier for this task
        data: Input features/data (typically numpy array)
        labels: Target labels/values (typically numpy array)
        metadata: Optional dictionary with task-specific metadata

    Example:
        >>> task = Task(
        ...     task_id="classification_task_1",
        ...     data=np.array([[1.0, 2.0], [3.0, 4.0]]),
        ...     labels=np.array([0, 1]),
        ...     metadata={"domain": "vision", "difficulty": "easy"}
        ... )
    """

    task_id: str
    data: np.ndarray
    labels: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate task data consistency."""
        if len(self.data) != len(self.labels):
            raise ValueError(
                f"Data and labels must have same length. "
                f"Got {len(self.data)} data points and {len(self.labels)} labels"
            )

    @property
    def n_samples(self) -> int:
        """Return the number of samples in this task."""
        return len(self.data)

    @property
    def input_dim(self) -> int | tuple[int, ...]:
        """Return the input dimensionality."""
        if self.data.ndim == 1:
            return 1
        return self.data.shape[1:]

    @property
    def output_dim(self) -> int | tuple[int, ...]:
        """Return the output dimensionality."""
        if self.labels.ndim == 1:
            return 1
        return self.labels.shape[1:]

    def sample(
        self, n_samples: int, seed: int | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """Sample a subset of data from this task.

        Args:
            n_samples: Number of samples to draw
            seed: Optional random seed for reproducibility

        Returns:
            Tuple of (sampled_data, sampled_labels)

        Raises:
            ValueError: If n_samples > available samples

        Example:
            >>> task = Task("t1", np.array([[1.0], [2.0], [3.0]]), np.array([0, 1, 0]))
            >>> data, labels = task.sample(2, seed=42)
            >>> len(data)
            2
        """
        if n_samples > self.n_samples:
            raise ValueError(
                f"Cannot sample {n_samples} from task with only {self.n_samples} samples"
            )

        rng = np.random.RandomState(seed)
        indices = rng.choice(self.n_samples, size=n_samples, replace=False)
        return self.data[indices], self.labels[indices]

    def sample_support_query(
        self, k_shot: int, q_query: int, seed: int | None = None
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        """Sample support and query sets for few-shot learning.

        Args:
            k_shot: Number of support samples per class
            q_query: Number of query samples
            seed: Optional random seed

        Returns:
            Tuple of ((support_data, support_labels), (query_data, query_labels))

        Example:
            >>> task = Task("t1", np.random.randn(100, 10), np.random.randint(0, 5, 100))
            >>> (sx, sy), (qx, qy) = task.sample_support_query(k_shot=5, q_query=15)
            >>> sx.shape[0]
            25  # 5 classes × 5 samples
        """
        if k_shot + q_query > self.n_samples:
            raise ValueError(
                f"k_shot ({k_shot}) + q_query ({q_query}) exceeds "
                f"available samples ({self.n_samples})"
            )

        rng = np.random.RandomState(seed)
        indices = rng.choice(self.n_samples, size=k_shot + q_query, replace=False)

        support_indices = indices[:k_shot]
        query_indices = indices[k_shot : k_shot + q_query]

        support_data = self.data[support_indices]
        support_labels = self.labels[support_indices]
        query_data = self.data[query_indices]
        query_labels = self.labels[query_indices]

        return (support_data, support_labels), (query_data, query_labels)


@dataclass
class Episode:
    """Represents a single meta-learning episode.

    An episode consists of support and query sets for one or more tasks,
    used for meta-training or meta-testing.

    Attributes:
        task_id: ID of the task this episode is from
        support_data: Support set inputs (k-shot samples)
        support_labels: Support set labels
        query_data: Query set inputs
        query_labels: Query set labels
        metadata: Episode-specific metadata

    Example:
        >>> episode = Episode(
        ...     task_id="task_1",
        ...     support_data=np.array([[1.0], [2.0]]),
        ...     support_labels=np.array([0, 1]),
        ...     query_data=np.array([[3.0], [4.0]]),
        ...     query_labels=np.array([0, 1]),
        ... )
    """

    task_id: str
    support_data: np.ndarray
    support_labels: np.ndarray
    query_data: np.ndarray
    query_labels: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate episode data consistency."""
        if len(self.support_data) != len(self.support_labels):
            raise ValueError("Support data and labels must have same length")
        if len(self.query_data) != len(self.query_labels):
            raise ValueError("Query data and labels must have same length")

    @property
    def n_support(self) -> int:
        """Return number of support samples."""
        return len(self.support_data)

    @property
    def n_query(self) -> int:
        """Return number of query samples."""
        return len(self.query_data)

    @property
    def support_shape(self) -> tuple[int, ...]:
        """Return shape of support data."""
        return self.support_data.shape

    @property
    def query_shape(self) -> tuple[int, ...]:
        """Return shape of query data."""
        return self.query_data.shape


class TaskDistribution:
    """Manages a collection of tasks with sampling capabilities.

    Provides methods for adding tasks, sampling tasks uniformly or by weight,
    and organizing tasks into meta-train/meta-test splits.

    Attributes:
        tasks: Dictionary mapping task_id to Task objects
        task_weights: Optional weights for non-uniform sampling

    Example:
        >>> distribution = TaskDistribution()
        >>> distribution.add_task(Task("t1", np.array([[1.0]]), np.array([0])))
        >>> distribution.add_task(Task("t2", np.array([[2.0]]), np.array([1])))
        >>> task = distribution.sample_task()
        >>> print(task.task_id)
        t1  # or t2
    """

    def __init__(self) -> None:
        """Initialize empty task distribution."""
        self._tasks: dict[str, Task] = {}
        self._task_weights: dict[str, float] = {}
        self._train_tasks: set[str] = set()
        self._test_tasks: set[str] = set()

    def add_task(
        self, task: Task, weight: float = 1.0, split: str | None = None
    ) -> None:
        """Add a task to the distribution.

        Args:
            task: Task to add
            weight: Sampling weight (default 1.0 for uniform)
            split: Optional split assignment ('train' or 'test')

        Raises:
            ValueError: If task_id already exists

        Example:
            >>> distribution = TaskDistribution()
            >>> distribution.add_task(
            ...     Task("t1", np.array([[1.0]]), np.array([0])),
            ...     weight=2.0,
            ...     split="train"
            ... )
        """
        if task.task_id in self._tasks:
            raise ValueError(f"Task with id '{task.task_id}' already exists")

        self._tasks[task.task_id] = task
        self._task_weights[task.task_id] = weight

        if split == "train":
            self._train_tasks.add(task.task_id)
        elif split == "test":
            self._test_tasks.add(task.task_id)

    def get_task(self, task_id: str) -> Task:
        """Get a task by ID.

        Args:
            task_id: ID of the task to retrieve

        Returns:
            The Task object

        Raises:
            KeyError: If task_id not found
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task '{task_id}' not found")
        return self._tasks[task_id]

    def remove_task(self, task_id: str) -> None:
        """Remove a task from the distribution.

        Args:
            task_id: ID of task to remove

        Raises:
            KeyError: If task_id not found
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task '{task_id}' not found")

        del self._tasks[task_id]
        del self._task_weights[task_id]
        self._train_tasks.discard(task_id)
        self._test_tasks.discard(task_id)

    @property
    def n_tasks(self) -> int:
        """Return total number of tasks."""
        return len(self._tasks)

    @property
    def task_ids(self) -> list[str]:
        """Return list of all task IDs."""
        return list(self._tasks.keys())

    @property
    def train_task_ids(self) -> list[str]:
        """Return list of training task IDs."""
        return list(self._train_tasks)

    @property
    def test_task_ids(self) -> list[str]:
        """Return list of test task IDs."""
        return list(self._test_tasks)

    def sample_task(self, split: str | None = None, seed: int | None = None) -> Task:
        """Sample a task from the distribution.

        Args:
            split: Optional split to sample from ('train' or 'test')
            seed: Optional random seed

        Returns:
            Sampled Task object

        Raises:
            ValueError: If no tasks available
        """
        if self.n_tasks == 0:
            raise ValueError("No tasks in distribution")

        # Filter by split if specified
        if split == "train":
            candidates = list(self._train_tasks)
        elif split == "test":
            candidates = list(self._test_tasks)
        else:
            candidates = list(self._tasks.keys())

        if not candidates:
            raise ValueError(f"No tasks in split '{split}'")

        # Sample with weights
        weights = [self._task_weights[tid] for tid in candidates]

        rng = random.Random(seed)
        task_id = rng.choices(candidates, weights=weights, k=1)[0]
        return self._tasks[task_id]

    def sample_tasks(
        self,
        n_tasks: int,
        split: str | None = None,
        replace: bool = True,
        seed: int | None = None,
    ) -> list[Task]:
        """Sample multiple tasks from the distribution.

        Args:
            n_tasks: Number of tasks to sample
            split: Optional split to sample from
            replace: Whether to sample with replacement
            seed: Optional random seed

        Returns:
            List of sampled Task objects
        """
        if split == "train":
            candidates = list(self._train_tasks)
        elif split == "test":
            candidates = list(self._test_tasks)
        else:
            candidates = list(self._tasks.keys())

        if not candidates:
            raise ValueError(f"No tasks in split '{split}'")

        weights = [self._task_weights[tid] for tid in candidates]

        rng = random.Random(seed)
        if replace:
            sampled_ids = rng.choices(candidates, weights=weights, k=n_tasks)
        else:
            # Sample without replacement
            if n_tasks > len(candidates):
                raise ValueError(
                    f"Cannot sample {n_tasks} tasks without replacement "
                    f"from {len(candidates)} available"
                )
            sampled_ids = rng.sample(candidates, k=n_tasks)

        return [self._tasks[tid] for tid in sampled_ids]

    def split_tasks(self, train_ratio: float = 0.8, seed: int | None = None) -> None:
        """Split tasks into meta-train and meta-test sets.

        Args:
            train_ratio: Fraction of tasks for training (default 0.8)
            seed: Optional random seed for reproducibility

        Raises:
            ValueError: If train_ratio not in (0, 1)
        """
        if not 0 < train_ratio < 1:
            raise ValueError(f"train_ratio must be in (0, 1), got {train_ratio}")

        all_ids = list(self._tasks.keys())
        n_train = int(len(all_ids) * train_ratio)

        rng = random.Random(seed)
        shuffled = all_ids.copy()
        rng.shuffle(shuffled)

        self._train_tasks = set(shuffled[:n_train])
        self._test_tasks = set(shuffled[n_train:])

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the task distribution.

        Returns:
            Dictionary with distribution statistics
        """
        stats = {
            "n_total_tasks": self.n_tasks,
            "n_train_tasks": len(self._train_tasks),
            "n_test_tasks": len(self._test_tasks),
            "task_ids": self.task_ids,
        }

        if self._tasks:
            sample_sizes = [t.n_samples for t in self._tasks.values()]
            stats["avg_samples_per_task"] = sum(sample_sizes) / len(sample_sizes)
            stats["min_samples"] = min(sample_sizes)
            stats["max_samples"] = max(sample_sizes)

        return stats


class MetaLearningController:
    """Main controller for meta-learning operations.

    Coordinates task management, episode generation, and data splits
    for meta-learning algorithms like MAML.

    Attributes:
        task_distribution: TaskDistribution managing all tasks
        config: Configuration dictionary

    Example:
        >>> controller = MetaLearningController()
        >>>
        >>> # Add tasks
        >>> for i in range(10):
        ...     data = np.random.randn(100, 10)
        ...     labels = np.random.randint(0, 5, 100)
        ...     controller.add_task(f"task_{i}", data, labels)
        >>>
        >>> # Split and sample
        >>> controller.split_tasks(train_ratio=0.8)
        >>> episodes = controller.sample_episodes(n_episodes=5, k_shot=5, q_query=15)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the meta-learning controller.

        Args:
            config: Optional configuration dictionary
        """
        self.task_distribution = TaskDistribution()
        self.config = config or {}
        self._task_counter = 0

    def add_task(
        self,
        task_id: str | None,
        data: np.ndarray,
        labels: np.ndarray,
        metadata: dict[str, Any] | None = None,
        weight: float = 1.0,
        split: str | None = None,
    ) -> str:
        """Add a new task to the controller.

        Args:
            task_id: Optional task ID (auto-generated if None)
            data: Input data
            labels: Target labels
            metadata: Optional task metadata
            weight: Sampling weight
            split: Optional split assignment

        Returns:
            The task ID
        """
        if task_id is None:
            task_id = f"task_{self._task_counter}"
            self._task_counter += 1

        task = Task(task_id=task_id, data=data, labels=labels, metadata=metadata or {})

        self.task_distribution.add_task(task, weight=weight, split=split)
        return task_id

    def remove_task(self, task_id: str) -> None:
        """Remove a task from the controller."""
        self.task_distribution.remove_task(task_id)

    def get_task(self, task_id: str) -> Task:
        """Get a task by ID."""
        return self.task_distribution.get_task(task_id)

    def split_tasks(self, train_ratio: float = 0.8, seed: int | None = None) -> None:
        """Split tasks into meta-train and meta-test sets."""
        self.task_distribution.split_tasks(train_ratio=train_ratio, seed=seed)

    def sample_episode(
        self,
        k_shot: int = 5,
        q_query: int = 15,
        split: str | None = None,
        seed: int | None = None,
    ) -> Episode:
        """Sample a single meta-learning episode.

        Args:
            k_shot: Number of support samples
            q_query: Number of query samples
            split: Optional split to sample from
            seed: Optional random seed

        Returns:
            Episode object with support and query sets
        """
        task = self.task_distribution.sample_task(split=split, seed=seed)

        (support_data, support_labels), (query_data, query_labels) = (
            task.sample_support_query(k_shot=k_shot, q_query=q_query, seed=seed)
        )

        return Episode(
            task_id=task.task_id,
            support_data=support_data,
            support_labels=support_labels,
            query_data=query_data,
            query_labels=query_labels,
            metadata={"k_shot": k_shot, "q_query": q_query, "split": split},
        )

    def sample_episodes(
        self,
        n_episodes: int,
        k_shot: int = 5,
        q_query: int = 15,
        split: str | None = None,
        seed: int | None = None,
    ) -> list[Episode]:
        """Sample multiple meta-learning episodes.

        Args:
            n_episodes: Number of episodes to sample
            k_shot: Number of support samples per episode
            q_query: Number of query samples per episode
            split: Optional split to sample from
            seed: Optional random seed

        Returns:
            List of Episode objects
        """
        episodes = []
        for i in range(n_episodes):
            episode_seed = seed + i if seed is not None else None
            episode = self.sample_episode(
                k_shot=k_shot, q_query=q_query, split=split, seed=episode_seed
            )
            episodes.append(episode)
        return episodes

    def create_episode_batch(
        self,
        task_ids: list[str],
        k_shot: int = 5,
        q_query: int = 15,
        seed: int | None = None,
    ) -> list[Episode]:
        """Create episodes from specific tasks.

        Args:
            task_ids: List of task IDs to create episodes from
            k_shot: Number of support samples
            q_query: Number of query samples
            seed: Optional random seed

        Returns:
            List of Episode objects
        """
        episodes = []
        for i, task_id in enumerate(task_ids):
            task = self.task_distribution.get_task(task_id)
            episode_seed = seed + i if seed is not None else None

            (support_data, support_labels), (query_data, query_labels) = (
                task.sample_support_query(
                    k_shot=k_shot, q_query=q_query, seed=episode_seed
                )
            )

            episode = Episode(
                task_id=task.task_id,
                support_data=support_data,
                support_labels=support_labels,
                query_data=query_data,
                query_labels=query_labels,
            )
            episodes.append(episode)

        return episodes

    @property
    def n_tasks(self) -> int:
        """Return total number of tasks."""
        return self.task_distribution.n_tasks

    @property
    def task_ids(self) -> list[str]:
        """Return list of all task IDs."""
        return self.task_distribution.task_ids

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the controller state."""
        return self.task_distribution.get_statistics()
