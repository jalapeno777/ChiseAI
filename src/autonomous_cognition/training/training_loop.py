"""Training loop for autocog model calibration.

This module provides an epoch-based training loop with early stopping,
loss tracking, and progress logging for calibration models.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EarlyStoppingMode(Enum):
    """Early stopping criterion."""

    PATIENCE = "patience"  # Stop after N epochs without improvement
    METRIC = "metric"  # Stop when metric crosses threshold


@dataclass
class EpochMetrics:
    """Metrics from a single epoch.

    Attributes:
        epoch: Epoch number
        train_loss: Training loss
        val_loss: Validation loss
        train_metric: Training metric value
        val_metric: Validation metric value
        learning_rate: Learning rate at epoch end
        duration_seconds: Time taken for epoch
    """

    epoch: int
    train_loss: float = 0.0
    val_loss: float = 0.0
    train_metric: float | None = None
    val_metric: float | None = None
    learning_rate: float = 0.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "epoch": self.epoch,
            "train_loss": round(self.train_loss, 6),
            "val_loss": round(self.val_loss, 6),
            "train_metric": (
                round(self.train_metric, 6) if self.train_metric is not None else None
            ),
            "val_metric": (
                round(self.val_metric, 6) if self.val_metric is not None else None
            ),
            "learning_rate": round(self.learning_rate, 8),
            "duration_seconds": round(self.duration_seconds, 3),
        }


@dataclass
class TrainingLoopState:
    """Current state of the training loop.

    Attributes:
        current_epoch: Current epoch number
        best_epoch: Epoch with best validation metric
        best_val_loss: Best validation loss
        best_val_metric: Best validation metric
        epochs_without_improvement: Number of epochs without improvement
        is_training: Whether training is in progress
        should_stop: Whether early stopping triggered
    """

    current_epoch: int = 0
    best_epoch: int = 0
    best_val_loss: float = float("inf")
    best_val_metric: float = float("-inf")
    epochs_without_improvement: int = 0
    is_training: bool = False
    should_stop: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current_epoch": self.current_epoch,
            "best_epoch": self.best_epoch,
            "best_val_loss": round(self.best_val_loss, 6),
            "best_val_metric": (
                round(self.best_val_metric, 6)
                if self.best_val_metric != float("-inf")
                else None
            ),
            "epochs_without_improvement": self.epochs_without_improvement,
            "is_training": self.is_training,
            "should_stop": self.should_stop,
        }


class TrainingLoop:
    """Epoch-based training loop with early stopping.

    Features:
    - Configurable maximum epochs
    - Early stopping (patience-based or metric-based)
    - Training/validation loss tracking
    - Progress logging
    - Learning rate scheduling integration
    - Gradient accumulation support

    Example:
        def train_step(params, batch):
            # Compute loss and gradients
            return loss, {"param": params}

        def val_step(params, val_data):
            # Compute validation metrics
            return val_loss, val_metric

        loop = TrainingLoop(
            max_epochs=100,
            early_stopping_patience=10,
            early_stopping_mode=EarlyStoppingMode.PATIENCE,
        )

        state = await loop.run(
            initial_params=params,
            train_step=train_step,
            val_step=val_step,
            train_data=train_batches,
            val_data=val_batches,
        )
    """

    def __init__(
        self,
        max_epochs: int = 100,
        early_stopping_patience: int = 10,
        early_stopping_mode: EarlyStoppingMode = EarlyStoppingMode.PATIENCE,
        early_stopping_threshold: float = 0.0,
        early_stopping_metric_direction: str = "minimize",
        min_epochs: int = 1,
        log_interval: int = 1,
        checkpoint_callback: Callable[[int, EpochMetrics], Any] | None = None,
        lr_scheduler_fn: Callable[[int], float] | None = None,
    ):
        """Initialize training loop.

        Args:
            max_epochs: Maximum number of epochs
            early_stopping_patience: Epochs to wait before early stopping
            early_stopping_mode: Criterion for early stopping
            early_stopping_threshold: Threshold for METRIC mode
            early_stopping_metric_direction: 'minimize' or 'maximize'
            min_epochs: Minimum epochs before early stopping can trigger
            log_interval: Log every N epochs
            checkpoint_callback: Called after each epoch with epoch metrics
            lr_scheduler_fn: Function to adjust learning rate by epoch
        """
        if max_epochs <= 0:
            raise ValueError(f"max_epochs must be positive, got {max_epochs}")

        if early_stopping_patience <= 0:
            raise ValueError(
                f"early_stopping_patience must be positive, got {early_stopping_patience}"
            )

        if min_epochs < 1:
            raise ValueError(f"min_epochs must be at least 1, got {min_epochs}")

        self.max_epochs = max_epochs
        self.early_stopping_patience = early_stopping_patience
        self.early_stopping_mode = early_stopping_mode
        self.early_stopping_threshold = early_stopping_threshold
        self.early_stopping_metric_direction = early_stopping_metric_direction.lower()
        self.min_epochs = min_epochs
        self.log_interval = log_interval
        self.checkpoint_callback = checkpoint_callback
        self.lr_scheduler_fn = lr_scheduler_fn

        self._state = TrainingLoopState()
        self._history: list[EpochMetrics] = []

    @property
    def state(self) -> TrainingLoopState:
        """Get current training state."""
        return self._state

    @property
    def history(self) -> list[EpochMetrics]:
        """Get training history."""
        return self._history.copy()

    @property
    def best_params(self) -> dict[str, float] | None:
        """Get best parameters from checkpoint callback."""
        return None  # Set by run() method if checkpoint_callback provides

    def _is_improvement(self, metric: float) -> bool:
        """Check if metric is an improvement.

        Args:
            metric: Current metric value

        Returns:
            True if metric improved
        """
        if self.early_stopping_metric_direction == "minimize":
            return metric < self._state.best_val_metric
        else:
            return metric > self._state.best_val_metric

    def _check_early_stopping(self, epoch_metrics: EpochMetrics) -> bool:
        """Check if early stopping criteria met.

        Args:
            epoch_metrics: Metrics from current epoch

        Returns:
            True if should stop
        """
        if epoch_metrics.epoch < self.min_epochs:
            return False

        if self.early_stopping_mode == EarlyStoppingMode.PATIENCE:
            if epoch_metrics.val_loss < self._state.best_val_loss:
                return False
            return (
                epoch_metrics.epoch - self._state.best_epoch
                >= self.early_stopping_patience
            )

        else:  # METRIC mode
            if self.early_stopping_metric_direction == "minimize":
                current_metric = epoch_metrics.val_loss
                threshold_met = current_metric <= self.early_stopping_threshold
            else:
                current_metric = epoch_metrics.val_metric or 0.0
                threshold_met = current_metric >= self.early_stopping_threshold

            if threshold_met:
                logger.info(
                    f"Early stopping threshold met: {current_metric:.6f} "
                    f"{self.early_stopping_metric_direction} "
                    f"{self.early_stopping_threshold:.6f}"
                )
                return True

            return False

    def _update_best(self, epoch_metrics: EpochMetrics) -> None:
        """Update best metrics.

        Args:
            epoch_metrics: Metrics from current epoch
        """
        improved = False

        if epoch_metrics.val_loss < self._state.best_val_loss:
            self._state.best_val_loss = epoch_metrics.val_loss
            self._state.best_epoch = epoch_metrics.epoch
            self._state.epochs_without_improvement = 0
            improved = True
        else:
            self._state.epochs_without_improvement += 1

        # Also track metric if available
        if epoch_metrics.val_metric is not None:
            if self._is_improvement(epoch_metrics.val_metric):
                self._state.best_val_metric = epoch_metrics.val_metric
                if not improved:
                    improved = True
                    self._state.best_epoch = epoch_metrics.epoch
                    self._state.epochs_without_improvement = 0

        if improved:
            logger.debug(
                f"New best: val_loss={epoch_metrics.val_loss:.6f}, "
                f"val_metric={epoch_metrics.val_metric}, "
                f"epoch={epoch_metrics.epoch}"
            )

    async def run(
        self,
        initial_params: dict[str, float],
        train_step: Callable[[dict[str, float], Any], tuple[float, dict[str, Any]]],
        val_step: Callable[[dict[str, float], Any], tuple[float, float | None]],
        train_data: Any,
        val_data: Any,
        current_lr: float = 0.01,
    ) -> TrainingLoopState:
        """Run the training loop.

        Args:
            initial_params: Initial parameter values
            train_step: Async function(params, batch) -> (loss, extra_info)
            val_step: Async function(params, val_data) -> (val_loss, val_metric)
            train_data: Training data (passed to train_step)
            val_data: Validation data (passed to val_step)
            current_lr: Initial learning rate

        Returns:
            Final TrainingLoopState
        """
        self._state = TrainingLoopState(is_training=True)
        self._history = []

        params = initial_params.copy()
        current_lr_value = current_lr

        logger.info(
            f"Starting training: max_epochs={self.max_epochs}, "
            f"early_stopping_patience={self.early_stopping_patience}, "
            f"mode={self.early_stopping_mode.value}"
        )

        for epoch in range(1, self.max_epochs + 1):
            self._state.current_epoch = epoch
            epoch_start = time.time()

            # Apply learning rate schedule
            if self.lr_scheduler_fn:
                current_lr_value = self.lr_scheduler_fn(epoch)
                logger.debug(f"Epoch {epoch}: lr={current_lr_value:.8f}")

            # Training step
            train_loss, train_info = await train_step(params, train_data)

            # Validation step
            val_loss, val_metric = await val_step(params, val_data)

            # Create epoch metrics
            epoch_metrics = EpochMetrics(
                epoch=epoch,
                train_loss=train_loss,
                val_loss=val_loss,
                train_metric=train_info.get("metric"),
                val_metric=val_metric,
                learning_rate=current_lr_value,
                duration_seconds=time.time() - epoch_start,
            )

            self._history.append(epoch_metrics)
            self._update_best(epoch_metrics)

            # Log progress
            if epoch % self.log_interval == 0 or epoch == 1:
                logger.info(
                    f"Epoch {epoch}/{self.max_epochs}: "
                    f"train_loss={train_loss:.6f}, val_loss={val_loss:.6f}, "
                    f"val_metric={val_metric}, best_epoch={self._state.best_epoch}, "
                    f"epochs_no_improve={self._state.epochs_without_improvement}"
                )

            # Checkpoint callback
            if self.checkpoint_callback:
                try:
                    self.checkpoint_callback(epoch, epoch_metrics)
                except Exception as e:
                    logger.warning(f"Checkpoint callback failed: {e}")

            # Check early stopping
            self._state.should_stop = self._check_early_stopping(epoch_metrics)

            if self._state.should_stop:
                logger.info(
                    f"Early stopping triggered at epoch {epoch}. "
                    f"Best epoch: {self._state.best_epoch}, "
                    f"best_val_loss: {self._state.best_val_loss:.6f}"
                )
                break

        self._state.is_training = False

        logger.info(
            f"Training completed: {self._state.current_epoch} epochs, "
            f"best_epoch={self._state.best_epoch}, "
            f"best_val_loss={self._state.best_val_loss:.6f}"
        )

        return self._state


class SyncTrainingLoop:
    """Synchronous version of TrainingLoop.

    Use this when train_step and val_step are synchronous functions.
    """

    def __init__(
        self,
        max_epochs: int = 100,
        early_stopping_patience: int = 10,
        early_stopping_mode: EarlyStoppingMode = EarlyStoppingMode.PATIENCE,
        early_stopping_threshold: float = 0.0,
        early_stopping_metric_direction: str = "minimize",
        min_epochs: int = 1,
        log_interval: int = 1,
        checkpoint_callback: Callable[[int, EpochMetrics], Any] | None = None,
        lr_scheduler_fn: Callable[[int], float] | None = None,
    ):
        """Initialize synchronous training loop.

        Args:
            Same as TrainingLoop
        """
        self._loop = TrainingLoop(
            max_epochs=max_epochs,
            early_stopping_patience=early_stopping_patience,
            early_stopping_mode=early_stopping_mode,
            early_stopping_threshold=early_stopping_threshold,
            early_stopping_metric_direction=early_stopping_metric_direction,
            min_epochs=min_epochs,
            log_interval=log_interval,
            checkpoint_callback=checkpoint_callback,
            lr_scheduler_fn=lr_scheduler_fn,
        )

    @property
    def state(self) -> TrainingLoopState:
        """Get current training state."""
        return self._loop.state

    @property
    def history(self) -> list[EpochMetrics]:
        """Get training history."""
        return self._loop.history

    def run(
        self,
        initial_params: dict[str, float],
        train_step: Callable[[dict[str, float], Any], tuple[float, dict[str, Any]]],
        val_step: Callable[[dict[str, float], Any], tuple[float, float | None]],
        train_data: Any,
        val_data: Any,
        current_lr: float = 0.01,
    ) -> TrainingLoopState:
        """Run the synchronous training loop.

        Args:
            Same as TrainingLoop.run()

        Returns:
            Final TrainingLoopState
        """
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            self._loop.run(
                initial_params=initial_params,
                train_step=train_step,
                val_step=val_step,
                train_data=train_data,
                val_data=val_data,
                current_lr=current_lr,
            )
        )
