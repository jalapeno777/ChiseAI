"""Meta-learning training loops and algorithms.

Provides training infrastructure for meta-learning including episode-based
training, meta-gradient computation, and support for multiple algorithms.

Example:
    >>> from src.strong_system.meta_learning.training import MetaTrainingLoop
    >>> from src.strong_system.meta_learning.models import MAML, LinearModel
    >>>
    >>> # Create model and training loop
    >>> base_model = LinearModel(input_dim=10, output_dim=5)
    >>> maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)
    >>> trainer = MetaTrainingLoop(maml)
    >>>
    >>> # Train
    >>> metrics = trainer.train(
    ...     episodes=train_episodes,
    ...     n_epochs=100,
    ...     episodes_per_epoch=10,
    ...     meta_lr=0.001
    ... )
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class TrainingMetrics:
    """Metrics tracked during meta-learning training.

    Attributes:
        epoch: Current epoch number
        meta_loss: Meta-learning loss
        inner_losses: List of inner loop losses
        pre_adapt_accuracy: Accuracy before adaptation
        post_adapt_accuracy: Accuracy after adaptation
        custom_metrics: Additional custom metrics
    """

    epoch: int = 0
    meta_loss: float = 0.0
    inner_losses: list[float] = field(default_factory=list)
    pre_adapt_accuracy: float = 0.0
    post_adapt_accuracy: float = 0.0
    custom_metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "epoch": self.epoch,
            "meta_loss": self.meta_loss,
            "inner_losses": self.inner_losses,
            "pre_adapt_accuracy": self.pre_adapt_accuracy,
            "post_adapt_accuracy": self.post_adapt_accuracy,
            **self.custom_metrics,
        }


@dataclass
class TrainingConfig:
    """Configuration for meta-learning training.

    Attributes:
        n_epochs: Number of training epochs
        episodes_per_epoch: Number of episodes per epoch
        meta_lr: Meta learning rate (outer loop)
        inner_lr: Inner loop learning rate
        n_inner_steps: Number of inner loop steps
        eval_interval: Evaluate every N epochs
        early_stopping_patience: Epochs to wait for improvement
        min_improvement: Minimum improvement for early stopping
        verbose: Print training progress
    """

    n_epochs: int = 100
    episodes_per_epoch: int = 10
    meta_lr: float = 0.001
    inner_lr: float = 0.01
    n_inner_steps: int = 5
    eval_interval: int = 10
    early_stopping_patience: int = 20
    min_improvement: float = 1e-4
    verbose: bool = True


class MetaTrainingLoop:
    """Training loop for meta-learning algorithms.

    Coordinates the meta-training process including episode sampling,
    inner loop adaptation, outer loop meta-gradient computation,
    and evaluation.

    Attributes:
        meta_model: Meta-learning model (MAML, Reptile, etc.)
        config: Training configuration
        history: Training history

    Example:
        >>> base_model = LinearModel(input_dim=10, output_dim=5)
        >>> maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)
        >>> trainer = MetaTrainingLoop(maml)
        >>>
        >>> # Configure training
        >>> trainer.config.n_epochs = 50
        >>> trainer.config.meta_lr = 0.001
        >>>
        >>> # Train with episodes from controller
        >>> metrics = trainer.train(train_episodes, val_episodes)
    """

    def __init__(self, meta_model: Any, config: TrainingConfig | None = None) -> None:
        """Initialize training loop.

        Args:
            meta_model: Meta-learning model with adapt() and compute_meta_gradient()
            config: Optional training configuration
        """
        self.meta_model = meta_model
        self.config = config or TrainingConfig()
        self.history: list[TrainingMetrics] = []
        self._best_loss = float("inf")
        self._patience_counter = 0

    def train(
        self,
        train_episodes: list,
        val_episodes: list | None = None,
        callback: Callable[[int, TrainingMetrics], None] | None = None,
        verbose: bool | None = None,
    ) -> dict[str, Any]:
        """Run meta-learning training.

        Args:
            train_episodes: List of training episodes
            val_episodes: Optional validation episodes
            callback: Optional callback function(epoch, metrics)
            verbose: Override config.verbose if provided

        Returns:
            Training summary dictionary
        """
        self.history = []
        self._best_loss = float("inf")
        self._patience_counter = 0

        # Use provided verbose or fall back to config
        verbose = verbose if verbose is not None else self.config.verbose

        if verbose:
            print(f"Starting meta-training for {self.config.n_epochs} epochs")
            print(f"Episodes per epoch: {self.config.episodes_per_epoch}")
            print(f"Meta learning rate: {self.config.meta_lr}")
            print(f"Inner learning rate: {self.config.inner_lr}")
            print(f"Inner steps: {self.config.n_inner_steps}")

        for epoch in range(self.config.n_epochs):
            # Sample episodes for this epoch
            epoch_episodes = self._sample_episodes(
                train_episodes, self.config.episodes_per_epoch
            )

            # Train on epoch episodes
            metrics = self._train_epoch(epoch, epoch_episodes)
            self.history.append(metrics)

            # Evaluate on validation set
            if val_episodes is not None and epoch % self.config.eval_interval == 0:
                val_metrics = self.evaluate(val_episodes)
                metrics.custom_metrics["val_loss"] = val_metrics["post_adapt_loss"]

                # Check for early stopping
                val_loss = val_metrics["post_adapt_loss"]
                if val_loss < self._best_loss - self.config.min_improvement:
                    self._best_loss = val_loss
                    self._patience_counter = 0
                else:
                    self._patience_counter += 1

                if self._patience_counter >= self.config.early_stopping_patience:
                    if verbose:
                        print(f"Early stopping at epoch {epoch}")
                    break

            # Print progress
            if verbose and epoch % self.config.eval_interval == 0:
                self._print_progress(epoch, metrics)

            # Call callback if provided
            if callback:
                callback(epoch, metrics)

        return self._create_summary()

    def _train_epoch(self, epoch: int, episodes: list) -> TrainingMetrics:
        """Train for one epoch.

        Args:
            epoch: Current epoch number
            episodes: Episodes for this epoch

        Returns:
            Training metrics for this epoch
        """
        metrics = TrainingMetrics(epoch=epoch)

        # Compute meta-gradient
        if hasattr(self.meta_model, "compute_meta_gradient"):
            meta_gradient = self.meta_model.compute_meta_gradient(
                episodes,
                inner_lr=self.config.inner_lr,
                n_inner_steps=self.config.n_inner_steps,
            )

            # Update meta-parameters
            if hasattr(self.meta_model, "meta_update"):
                self.meta_model.meta_update(meta_gradient, self.config.meta_lr)
            else:
                # Manual update if meta_update not available
                for key in self.meta_model.meta_parameters:
                    if key in meta_gradient:
                        self.meta_model.meta_parameters[key] = (
                            self.meta_model.meta_parameters[key]
                            - self.config.meta_lr * meta_gradient[key]
                        )

            # Compute meta-loss (average query loss)
            meta_loss = 0.0
            for episode in episodes:
                adapted_params = self.meta_model.adapt(
                    episode.support_data,
                    episode.support_labels,
                    n_steps=self.config.n_inner_steps,
                    lr=self.config.inner_lr,
                )
                loss = self.meta_model.compute_loss(
                    adapted_params, episode.query_data, episode.query_labels
                )
                meta_loss += loss
            metrics.meta_loss = meta_loss / len(episodes)

        # Track inner loop losses
        inner_losses = []
        for episode in episodes[:5]:  # Sample a few for tracking
            adapted_params = self.meta_model.adapt(
                episode.support_data,
                episode.support_labels,
                n_steps=self.config.n_inner_steps,
                lr=self.config.inner_lr,
            )
            loss = self.meta_model.compute_loss(
                adapted_params, episode.query_data, episode.query_labels
            )
            inner_losses.append(loss)
        metrics.inner_losses = inner_losses

        return metrics

    def _sample_episodes(self, episodes: list, n: int) -> list:
        """Sample episodes for an epoch.

        Args:
            episodes: Pool of episodes
            n: Number to sample

        Returns:
            Sampled episodes
        """
        if n >= len(episodes):
            return episodes
        indices = np.random.choice(len(episodes), size=n, replace=False)
        return [episodes[i] for i in indices]

    def evaluate(self, episodes: list) -> dict[str, float]:
        """Evaluate model on episodes.

        Args:
            episodes: Evaluation episodes

        Returns:
            Evaluation metrics
        """
        if hasattr(self.meta_model, "evaluate"):
            return self.meta_model.evaluate(episodes)
        else:
            # Manual evaluation
            return self._manual_evaluate(episodes)

    def _manual_evaluate(self, episodes: list) -> dict[str, float]:
        """Manual evaluation without model.evaluate().

        Args:
            episodes: Evaluation episodes

        Returns:
            Evaluation metrics
        """
        total_pre_loss = 0.0
        total_post_loss = 0.0

        for episode in episodes:
            # Pre-adaptation loss
            pre_loss = self.meta_model.compute_loss(
                self.meta_model.meta_parameters,
                episode.query_data,
                episode.query_labels,
            )
            total_pre_loss += pre_loss

            # Adapt and compute post-adaptation loss
            adapted_params = self.meta_model.adapt(
                episode.support_data,
                episode.support_labels,
                n_steps=self.config.n_inner_steps,
                lr=self.config.inner_lr,
            )
            post_loss = self.meta_model.compute_loss(
                adapted_params, episode.query_data, episode.query_labels
            )
            total_post_loss += post_loss

        n = len(episodes)
        return {
            "pre_adapt_loss": total_pre_loss / n,
            "post_adapt_loss": total_post_loss / n,
            "improvement": total_pre_loss / n - total_post_loss / n,
        }

    def _print_progress(self, epoch: int, metrics: TrainingMetrics) -> None:
        """Print training progress.

        Args:
            epoch: Current epoch
            metrics: Current metrics
        """
        msg = f"Epoch {epoch}/{self.config.n_epochs}: "
        msg += f"meta_loss={metrics.meta_loss:.4f}"

        if metrics.inner_losses:
            avg_inner = np.mean(metrics.inner_losses)
            msg += f", avg_inner_loss={avg_inner:.4f}"

        if "val_loss" in metrics.custom_metrics:
            msg += f", val_loss={metrics.custom_metrics['val_loss']:.4f}"

        print(msg)

    def _create_summary(self) -> dict[str, Any]:
        """Create training summary.

        Returns:
            Summary dictionary
        """
        if not self.history:
            return {"epochs_trained": 0}

        final_metrics = self.history[-1]

        summary = {
            "epochs_trained": len(self.history),
            "final_meta_loss": final_metrics.meta_loss,
            "best_loss": self._best_loss,
            "history": [m.to_dict() for m in self.history],
        }

        return summary

    def get_learning_curve(self) -> dict[str, list[float]]:
        """Get learning curve data.

        Returns:
            Dictionary with epoch and loss lists
        """
        return {
            "epochs": [m.epoch for m in self.history],
            "meta_losses": [m.meta_loss for m in self.history],
            "inner_losses": [
                np.mean(m.inner_losses) if m.inner_losses else 0 for m in self.history
            ],
        }


class EpisodeTrainer:
    """Simplified trainer for single-episode training.

    Useful for fine-tuning on a specific task after meta-training.

    Attributes:
        model: Model to train
        lr: Learning rate
        n_steps: Number of training steps

    Example:
        >>> trainer = EpisodeTrainer(maml, lr=0.01, n_steps=20)
        >>> loss_history = trainer.train_on_episode(episode)
    """

    def __init__(self, model: Any, lr: float = 0.01, n_steps: int = 20) -> None:
        """Initialize episode trainer.

        Args:
            model: Model to train
            lr: Learning rate
            n_steps: Number of training steps
        """
        self.model = model
        self.lr = lr
        self.n_steps = n_steps

    def train_on_episode(
        self, episode: Any, use_support_only: bool = False
    ) -> list[float]:
        """Train on a single episode.

        Args:
            episode: Episode to train on
            use_support_only: If True, only use support set

        Returns:
            List of loss values
        """
        loss_history = []

        # Use support set or full episode
        if use_support_only:
            data = episode.support_data
            labels = episode.support_labels
        else:
            # Combine support and query
            data = np.vstack([episode.support_data, episode.query_data])
            labels = np.concatenate([episode.support_labels, episode.query_labels])

        # Training loop
        for _step in range(self.n_steps):
            # Compute loss
            loss = self.model.compute_loss(self.model.meta_parameters, data, labels)
            loss_history.append(loss)

            # Compute gradients and update
            if hasattr(self.model.base_model, "compute_gradients"):
                grads = self.model.base_model.compute_gradients(
                    self.model.meta_parameters, data, labels
                )

                for key in self.model.meta_parameters:
                    if key in grads:
                        self.model.meta_parameters[key] = (
                            self.model.meta_parameters[key] - self.lr * grads[key]
                        )

        return loss_history

    def evaluate_on_episode(self, episode: Any) -> dict[str, float]:
        """Evaluate on episode.

        Args:
            episode: Episode to evaluate

        Returns:
            Evaluation metrics
        """
        # Evaluate on query set
        loss = self.model.compute_loss(
            self.model.meta_parameters, episode.query_data, episode.query_labels
        )

        # Compute predictions
        predictions = self.model.predict(episode.query_data, self.model.meta_parameters)

        # Compute accuracy for classification
        if predictions.ndim > 1 and predictions.shape[1] > 1:
            pred_labels = np.argmax(predictions, axis=1)
            accuracy = np.mean(pred_labels == episode.query_labels)
        else:
            accuracy = 0.0

        return {"loss": loss, "accuracy": accuracy}
