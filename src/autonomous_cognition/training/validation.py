"""Validation split and metrics computation for autocog training.

This module provides validation functionality using the existing
TrainingDataLoader (70/15/15 split) from src.ml.training.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.ml.training.training_pipeline import (
    TrainingConfig,
    TrainingDataLoader,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationMetrics:
    """Computed validation metrics.

    Attributes:
        loss: Validation loss
        metric: Primary validation metric
        additional_metrics: Additional computed metrics
        num_samples: Number of validation samples
    """

    loss: float
    metric: float | None = None
    additional_metrics: dict[str, float] = field(default_factory=dict)
    num_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "loss": round(self.loss, 6),
            "metric": round(self.metric, 6) if self.metric is not None else None,
            "additional_metrics": {
                k: round(v, 6) for k, v in self.additional_metrics.items()
            },
            "num_samples": self.num_samples,
        }


@dataclass
class ValidationSplit:
    """Container for validation split data and utilities.

    Attributes:
        train_data: Training samples (70%)
        val_data: Validation samples (15%)
        test_data: Test samples (15%)
        config: Training configuration used
    """

    train_data: list[Any] = field(default_factory=list)
    val_data: list[Any] = field(default_factory=list)
    test_data: list[Any] = field(default_factory=list)
    config: TrainingConfig = field(default_factory=TrainingConfig)

    @property
    def total_count(self) -> int:
        """Get total sample count."""
        return len(self.train_data) + len(self.val_data) + len(self.test_data)

    @property
    def train_count(self) -> int:
        """Get training set size."""
        return len(self.train_data)

    @property
    def val_count(self) -> int:
        """Get validation set size."""
        return len(self.val_data)

    @property
    def test_count(self) -> int:
        """Get test set size."""
        return len(self.test_data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "train_count": self.train_count,
            "val_count": self.val_count,
            "test_count": self.test_count,
            "total_count": self.total_count,
            "split_ratio": f"{self.config.train_ratio}/{self.config.validation_ratio}/{self.config.test_ratio}",
        }


class ValidationSplitManager:
    """Manages validation splits and metrics computation.

    Uses the existing TrainingDataLoader from src.ml.training for
    the 70/15/15 split.

    Features:
    - Uses existing TrainingDataLoader (70/15/15 split)
    - Validation metrics computation
    - Test set evaluation
    - Custom metric functions

    Example:
        manager = ValidationSplitManager(
            config=TrainingConfig(
                train_ratio=0.70,
                validation_ratio=0.15,
                test_ratio=0.15,
            )
        )

        # Create split from data
        split = manager.create_split(samples)

        # Compute validation metrics
        metrics = manager.compute_metrics(
            params=model_params,
            val_data=split.val_data,
            metric_fn=compute_calibration_error,
        )
    """

    def __init__(
        self,
        config: TrainingConfig | None = None,
        data_loader: TrainingDataLoader | None = None,
    ):
        """Initialize validation split manager.

        Args:
            config: Training configuration for split ratios
            data_loader: Optional existing TrainingDataLoader
        """
        self.config = config or TrainingConfig()
        self._data_loader = data_loader or TrainingDataLoader(config=self.config)

    @property
    def data_loader(self) -> TrainingDataLoader:
        """Get the data loader."""
        return self._data_loader

    def create_split(
        self,
        samples: list[Any],
        seed: int | None = None,
    ) -> ValidationSplit:
        """Create a validation split from samples.

        Uses the same splitting logic as TrainingDataLoader.

        Args:
            samples: List of samples to split
            seed: Random seed override

        Returns:
            ValidationSplit with train/val/test data
        """
        if not samples:
            logger.warning("Empty samples provided to create_split")
            return ValidationSplit(config=self.config)

        # Use random seed for reproducibility
        rng = random.Random(seed if seed is not None else self.config.random_seed)
        shuffled = samples.copy()
        rng.shuffle(shuffled)

        # Calculate split indices
        n = len(shuffled)
        train_end = int(n * self.config.train_ratio)
        val_end = train_end + int(n * self.config.validation_ratio)

        # Split
        train_data = shuffled[:train_end]
        val_data = shuffled[train_end:val_end]
        test_data = shuffled[val_end:]

        split = ValidationSplit(
            train_data=train_data,
            val_data=val_data,
            test_data=test_data,
            config=self.config,
        )

        logger.info(
            f"Created validation split: "
            f"train={len(train_data)}, val={len(val_data)}, test={len(test_data)}"
        )

        return split

    def compute_metrics(
        self,
        params: dict[str, float],
        data: list[Any],
        metric_fn: Callable[[dict[str, float], Any], float],
        loss_fn: Callable[[dict[str, float], Any], float] | None = None,
    ) -> ValidationMetrics:
        """Compute validation metrics on a dataset.

        Args:
            params: Current model parameters
            data: Dataset to evaluate
            metric_fn: Function(params, sample) -> metric value
            loss_fn: Optional function(params, sample) -> loss value

        Returns:
            ValidationMetrics with computed values
        """
        if not data:
            logger.warning("Empty data provided to compute_metrics")
            return ValidationMetrics(loss=0.0, num_samples=0)

        total_loss = 0.0
        total_metric = 0.0
        num_samples = len(data)

        for sample in data:
            try:
                if loss_fn:
                    total_loss += loss_fn(params, sample)
                total_metric += metric_fn(params, sample)
            except Exception as e:
                logger.warning(f"Error computing metrics on sample: {e}")

        avg_loss = total_loss / num_samples if loss_fn else 0.0
        avg_metric = total_metric / num_samples if num_samples > 0 else 0.0

        return ValidationMetrics(
            loss=avg_loss,
            metric=avg_metric,
            num_samples=num_samples,
        )

    async def compute_metrics_async(
        self,
        params: dict[str, float],
        data: list[Any],
        metric_fn: Callable[[dict[str, float], Any], float],
        loss_fn: Callable[[dict[str, float], Any], float] | None = None,
    ) -> ValidationMetrics:
        """Async version of compute_metrics.

        Args:
            Same as compute_metrics

        Returns:
            ValidationMetrics with computed values
        """
        if not data:
            logger.warning("Empty data provided to compute_metrics_async")
            return ValidationMetrics(loss=0.0, num_samples=0)

        total_loss = 0.0
        total_metric = 0.0
        num_samples = len(data)

        for sample in data:
            try:
                if loss_fn:
                    total_loss += loss_fn(params, sample)
                total_metric += metric_fn(params, sample)
            except Exception as e:
                logger.warning(f"Error computing metrics on sample: {e}")

        avg_loss = total_loss / num_samples if loss_fn else 0.0
        avg_metric = total_metric / num_samples if num_samples > 0 else 0.0

        return ValidationMetrics(
            loss=avg_loss,
            metric=avg_metric,
            num_samples=num_samples,
        )

    def evaluate_on_test(
        self,
        params: dict[str, float],
        test_data: list[Any],
        metric_fn: Callable[[dict[str, float], Any], float],
        loss_fn: Callable[[dict[str, float], Any], float] | None = None,
    ) -> ValidationMetrics:
        """Evaluate model on test set.

        Args:
            params: Model parameters
            test_data: Test samples
            metric_fn: Metric function
            loss_fn: Optional loss function

        Returns:
            ValidationMetrics on test set
        """
        logger.info(f"Evaluating on test set ({len(test_data)} samples)")
        return self.compute_metrics(params, test_data, metric_fn, loss_fn)

    def get_split_info(self, split: ValidationSplit) -> dict[str, Any]:
        """Get information about a split.

        Args:
            split: ValidationSplit to describe

        Returns:
            Dictionary with split information
        """
        return {
            "total_samples": split.total_count,
            "train": {
                "count": split.train_count,
                "ratio": self.config.train_ratio,
                "percentage": self.config.train_ratio * 100,
            },
            "validation": {
                "count": split.val_count,
                "ratio": self.config.validation_ratio,
                "percentage": self.config.validation_ratio * 100,
            },
            "test": {
                "count": split.test_count,
                "ratio": self.config.test_ratio,
                "percentage": self.config.test_ratio * 100,
            },
            "random_seed": self.config.random_seed,
        }


def create_validation_split_manager(
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_seed: int = 42,
) -> ValidationSplitManager:
    """Factory function to create ValidationSplitManager.

    Args:
        train_ratio: Training set ratio
        validation_ratio: Validation set ratio
        test_ratio: Test set ratio
        random_seed: Random seed

    Returns:
        Configured ValidationSplitManager
    """
    config = TrainingConfig(
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        random_seed=random_seed,
    )

    return ValidationSplitManager(config=config)
