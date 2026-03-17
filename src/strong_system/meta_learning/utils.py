"""Utility functions for meta-learning.

Provides task samplers, episode batchers, and meta-learning metrics.

Example:
    >>> from src.strong_system.meta_learning.utils import TaskSampler, compute_meta_metrics
    >>> sampler = TaskSampler(tasks)
    >>> episodes = sampler.sample_episodes(n_episodes=10, k_shot=5)
    >>> metrics = compute_meta_metrics(predictions, targets)
"""

from __future__ import annotations

import random
from typing import Any, Callable

import numpy as np


class TaskSampler:
    """Sampler for generating meta-learning episodes from tasks.

    Provides methods for sampling k-shot episodes with support and query sets
    from a collection of tasks.

    Attributes:
        tasks: List of tasks to sample from

    Example:
        >>> tasks = [task1, task2, task3]
        >>> sampler = TaskSampler(tasks)
        >>> episode = sampler.sample_episode(k_shot=5, q_query=15)
        >>> batch = sampler.sample_batch(n_episodes=10, k_shot=5)
    """

    def __init__(self, tasks: list) -> None:
        """Initialize task sampler.

        Args:
            tasks: List of Task objects
        """
        self.tasks = tasks

    def sample_episode(
        self,
        k_shot: int = 5,
        q_query: int = 15,
        task_idx: int | None = None,
        seed: int | None = None,
    ) -> Any:
        """Sample a single episode.

        Args:
            k_shot: Number of support samples
            q_query: Number of query samples
            task_idx: Specific task index (random if None)
            seed: Random seed

        Returns:
            Episode object
        """
        from .controller import Episode

        rng = np.random.RandomState(seed)

        # Select task
        if task_idx is None:
            task_idx = rng.randint(0, len(self.tasks))
        task = self.tasks[task_idx]

        # Sample support and query
        (support_data, support_labels), (query_data, query_labels) = (
            task.sample_support_query(k_shot=k_shot, q_query=q_query, seed=seed)
        )

        return Episode(
            task_id=task.task_id,
            support_data=support_data,
            support_labels=support_labels,
            query_data=query_data,
            query_labels=query_labels,
        )

    def sample_batch(
        self,
        n_episodes: int,
        k_shot: int = 5,
        q_query: int = 15,
        seed: int | None = None,
    ) -> list:
        """Sample a batch of episodes.

        Args:
            n_episodes: Number of episodes
            k_shot: Number of support samples per episode
            q_query: Number of query samples per episode
            seed: Random seed

        Returns:
            List of Episode objects
        """
        episodes = []
        for i in range(n_episodes):
            episode_seed = seed + i if seed is not None else None
            episode = self.sample_episode(
                k_shot=k_shot, q_query=q_query, seed=episode_seed
            )
            episodes.append(episode)
        return episodes

    def sample_task_episodes(
        self,
        task_idx: int,
        n_episodes: int,
        k_shot: int = 5,
        q_query: int = 15,
        seed: int | None = None,
    ) -> list:
        """Sample multiple episodes from a specific task.

        Args:
            task_idx: Task index
            n_episodes: Number of episodes
            k_shot: Number of support samples
            q_query: Number of query samples
            seed: Random seed

        Returns:
            List of Episode objects
        """
        episodes = []
        for i in range(n_episodes):
            episode_seed = seed + i if seed is not None else None
            episode = self.sample_episode(
                k_shot=k_shot, q_query=q_query, task_idx=task_idx, seed=episode_seed
            )
            episodes.append(episode)
        return episodes


class EpisodeBatcher:
    """Batch episodes for efficient training.

    Groups episodes into batches for meta-training, supporting
    different batching strategies.

    Attributes:
        episodes: List of episodes to batch
        batch_size: Number of episodes per batch

    Example:
        >>> batcher = EpisodeBatcher(episodes, batch_size=4)
        >>> for batch in batcher:
        ...     # Train on batch of 4 episodes
        ...     pass
    """

    def __init__(
        self,
        episodes: list,
        batch_size: int = 4,
        shuffle: bool = True,
        seed: int | None = None,
    ) -> None:
        """Initialize episode batcher.

        Args:
            episodes: List of episodes
            batch_size: Episodes per batch
            shuffle: Whether to shuffle episodes
            seed: Random seed
        """
        self.episodes = episodes.copy()
        self.batch_size = batch_size
        self.shuffle = shuffle

        if shuffle:
            rng = random.Random(seed)
            rng.shuffle(self.episodes)

    def __iter__(self):
        """Iterate over batches."""
        for i in range(0, len(self.episodes), self.batch_size):
            batch = self.episodes[i : i + self.batch_size]
            yield batch

    def __len__(self) -> int:
        """Return number of batches."""
        return (len(self.episodes) + self.batch_size - 1) // self.batch_size

    def get_batch(self, idx: int) -> list:
        """Get specific batch by index.

        Args:
            idx: Batch index

        Returns:
            List of episodes in batch
        """
        start = idx * self.batch_size
        end = start + self.batch_size
        return self.episodes[start:end]


def compute_accuracy(
    predictions: np.ndarray, labels: np.ndarray, task_type: str = "classification"
) -> float:
    """Compute accuracy for predictions.

    Args:
        predictions: Model predictions
        labels: True labels
        task_type: 'classification' or 'regression'

    Returns:
        Accuracy score
    """
    if task_type == "classification":
        if predictions.ndim > 1 and predictions.shape[1] > 1:
            # Multi-class
            pred_labels = np.argmax(predictions, axis=1)
        else:
            # Binary
            pred_labels = (predictions > 0.5).astype(int)
        return float(np.mean(pred_labels == labels))
    else:  # regression
        # R^2 score for regression
        ss_res = np.sum((labels - predictions) ** 2)
        ss_tot = np.sum((labels - np.mean(labels)) ** 2)
        if ss_tot == 0:
            return 1.0
        return float(1 - (ss_res / ss_tot))


def compute_precision_recall_f1(
    predictions: np.ndarray, labels: np.ndarray, average: str = "macro"
) -> dict[str, float]:
    """Compute precision, recall, and F1 score.

    Args:
        predictions: Model predictions (logits or probabilities)
        labels: True labels
        average: Averaging method ('macro', 'micro', 'weighted')

    Returns:
        Dictionary with precision, recall, f1 scores
    """
    # Get predicted classes
    if predictions.ndim > 1:
        pred_labels = np.argmax(predictions, axis=1)
    else:
        pred_labels = predictions.astype(int)

    labels = labels.astype(int)

    # Get unique classes
    classes = np.unique(np.concatenate([labels, pred_labels]))

    # Compute per-class metrics
    precisions = []
    recalls = []
    f1s = []
    supports = []

    for c in classes:
        true_positives = np.sum((pred_labels == c) & (labels == c))
        false_positives = np.sum((pred_labels == c) & (labels != c))
        false_negatives = np.sum((pred_labels != c) & (labels == c))

        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives) > 0
            else 0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives) > 0
            else 0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
        supports.append(np.sum(labels == c))

    # Average
    if average == "macro":
        return {
            "precision": float(np.mean(precisions)),
            "recall": float(np.mean(recalls)),
            "f1": float(np.mean(f1s)),
        }
    elif average == "weighted":
        total = sum(supports)
        return {
            "precision": float(np.average(precisions, weights=supports)),
            "recall": float(np.average(recalls, weights=supports)),
            "f1": float(np.average(f1s, weights=supports)),
        }
    else:  # micro
        # Micro-average is just accuracy for multi-class
        accuracy = compute_accuracy(predictions, labels)
        return {"precision": accuracy, "recall": accuracy, "f1": accuracy}


def compute_meta_metrics(
    predictions: np.ndarray, labels: np.ndarray, task_type: str = "classification"
) -> dict[str, float]:
    """Compute comprehensive meta-learning metrics.

    Args:
        predictions: Model predictions
        labels: True labels
        task_type: 'classification' or 'regression'

    Returns:
        Dictionary of metrics
    """
    metrics = {"accuracy": compute_accuracy(predictions, labels, task_type)}

    if task_type == "classification":
        # Add classification-specific metrics
        prf1 = compute_precision_recall_f1(predictions, labels)
        metrics.update(prf1)

        # Confusion matrix elements for binary
        if predictions.ndim == 1 or predictions.shape[1] == 1:
            pred_labels = (predictions > 0.5).astype(int)
            labels = labels.astype(int)

            tp = np.sum((pred_labels == 1) & (labels == 1))
            tn = np.sum((pred_labels == 0) & (labels == 0))
            fp = np.sum((pred_labels == 1) & (labels == 0))
            fn = np.sum((pred_labels == 0) & (labels == 1))

            metrics["true_positives"] = int(tp)
            metrics["true_negatives"] = int(tn)
            metrics["false_positives"] = int(fp)
            metrics["false_negatives"] = int(fn)

    return metrics


def compute_adaptation_gain(pre_adapt_loss: float, post_adapt_loss: float) -> float:
    """Compute adaptation gain (improvement from adaptation).

    Args:
        pre_adapt_loss: Loss before adaptation
        post_adapt_loss: Loss after adaptation

    Returns:
        Adaptation gain (positive is improvement)
    """
    if pre_adapt_loss == 0:
        return 0.0
    return (pre_adapt_loss - post_adapt_loss) / pre_adapt_loss


def compute_meta_gradient_norm(meta_gradient: dict[str, np.ndarray]) -> float:
    """Compute L2 norm of meta-gradient.

    Args:
        meta_gradient: Dictionary of parameter gradients

    Returns:
        L2 norm
    """
    total_norm = 0.0
    for grad in meta_gradient.values():
        total_norm += np.sum(grad**2)
    return float(np.sqrt(total_norm))


def clip_gradient_norm(
    gradient: dict[str, np.ndarray], max_norm: float
) -> dict[str, np.ndarray]:
    """Clip gradient by norm.

    Args:
        gradient: Gradient dictionary
        max_norm: Maximum allowed norm

    Returns:
        Clipped gradient
    """
    norm = compute_meta_gradient_norm(gradient)
    if norm > max_norm:
        scale = max_norm / norm
        return {k: v * scale for k, v in gradient.items()}
    return gradient


def create_sinusoid_task(
    amplitude: float,
    phase: float,
    n_samples: int = 100,
    x_range: tuple[float, float] = (-5.0, 5.0),
    noise_std: float = 0.1,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a sinusoid regression task.

    Args:
        amplitude: Sine wave amplitude
        phase: Sine wave phase
        n_samples: Number of samples
        x_range: Range of x values
        noise_std: Standard deviation of noise
        seed: Random seed

    Returns:
        Tuple of (X, y) arrays

    Example:
        >>> X, y = create_sinusoid_task(amplitude=1.0, phase=0.0, n_samples=50)
        >>> X.shape
        (50, 1)
    """
    rng = np.random.RandomState(seed)

    X = rng.uniform(x_range[0], x_range[1], size=(n_samples, 1))
    y = amplitude * np.sin(X + phase)

    if noise_std > 0:
        y = y + rng.randn(n_samples, 1) * noise_std

    return X, y.flatten()


def create_classification_task(
    n_classes: int,
    n_samples: int = 100,
    n_features: int = 10,
    class_sep: float = 1.0,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a synthetic classification task.

    Args:
        n_classes: Number of classes
        n_samples: Number of samples
        n_features: Number of features
        class_sep: Class separation (higher = easier)
        seed: Random seed

    Returns:
        Tuple of (X, y) arrays

    Example:
        >>> X, y = create_classification_task(n_classes=5, n_samples=100)
        >>> X.shape
        (100, 10)
    """
    rng = np.random.RandomState(seed)

    samples_per_class = n_samples // n_classes
    X_list = []
    y_list = []

    for i in range(n_classes):
        # Create cluster for each class
        center = rng.randn(n_features) * class_sep
        X_class = rng.randn(samples_per_class, n_features) + center
        y_class = np.full(samples_per_class, i)

        X_list.append(X_class)
        y_list.append(y_class)

    X = np.vstack(X_list)
    y = np.concatenate(y_list)

    # Shuffle
    indices = rng.permutation(len(X))
    X = X[indices]
    y = y[indices]

    return X, y


def split_episodes(
    episodes: list, train_ratio: float = 0.8, seed: int | None = None
) -> tuple[list, list]:
    """Split episodes into train and validation sets.

    Args:
        episodes: List of episodes
        train_ratio: Fraction for training
        seed: Random seed

    Returns:
        Tuple of (train_episodes, val_episodes)
    """
    rng = random.Random(seed)
    shuffled = episodes.copy()
    rng.shuffle(shuffled)

    n_train = int(len(shuffled) * train_ratio)
    return shuffled[:n_train], shuffled[n_train:]


def compute_confidence_interval(
    values: list[float] | np.ndarray, confidence: float = 0.95
) -> tuple[float, float]:
    """Compute confidence interval for a set of values.

    Args:
        values: List or array of values
        confidence: Confidence level (default 0.95)

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    values = np.array(values)
    mean = np.mean(values)
    std = np.std(values)

    # Approximate 95% CI using normal distribution
    z = 1.96 if confidence == 0.95 else 2.58 if confidence == 0.99 else 1.645
    margin = z * std / np.sqrt(len(values))

    return mean - margin, mean + margin


def aggregate_episode_metrics(
    episode_metrics: list[dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Aggregate metrics across episodes.

    Args:
        episode_metrics: List of metric dictionaries

    Returns:
        Dictionary with mean, std, min, max for each metric
    """
    if not episode_metrics:
        return {}

    # Get all metric keys
    keys = episode_metrics[0].keys()

    aggregated = {}
    for key in keys:
        values = [m[key] for m in episode_metrics if key in m]
        if values:
            aggregated[key] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "median": float(np.median(values)),
            }

    return aggregated
