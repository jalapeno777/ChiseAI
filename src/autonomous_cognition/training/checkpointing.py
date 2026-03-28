"""Model checkpointing for autocog training.

This module provides model checkpointing that saves best models based on
validation metrics, keeps top N checkpoints, and supports rollback to
previous best models.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from src.autonomous_cognition.gradient_learning import CheckpointManager

logger = logging.getLogger(__name__)


class CheckpointType(Enum):
    """Type of checkpoint."""

    BEST = "best"  # Best model based on validation metric
    PERIODIC = "periodic"  # Periodic checkpoint
    FINAL = "final"  # Final checkpoint at end of training


@dataclass
class ModelCheckpoint:
    """Represents a saved model checkpoint.

    Attributes:
        checkpoint_id: Unique identifier
        checkpoint_type: Type of checkpoint
        epoch: Epoch number
        params: Model parameters
        metrics: Validation metrics at checkpoint time
        created_at: When checkpoint was created
        is_best: Whether this is the current best model
    """

    checkpoint_id: str
    checkpoint_type: CheckpointType
    epoch: int
    params: dict[str, float]
    metrics: dict[str, float] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_best: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_type": self.checkpoint_type.value,
            "epoch": self.epoch,
            "params": self.params,
            "metrics": self.metrics,
            "created_at": self.created_at,
            "is_best": self.is_best,
        }


@dataclass
class ModelCheckpointConfig:
    """Configuration for model checkpointing.

    Attributes:
        checkpoint_dir: Directory to save checkpoints
        max_checkpoints: Maximum number of checkpoints to keep
        save_best_only: Only save when model is best
        metric_name: Metric to use for best model selection
        metric_direction: 'minimize' or 'maximize'
        save_every_n_epochs: Save checkpoint every N epochs (0 = disabled)
    """

    checkpoint_dir: str = "checkpoints/autocog"
    max_checkpoints: int = 5
    save_best_only: bool = True
    metric_name: str = "val_loss"
    metric_direction: str = "minimize"
    save_every_n_epochs: int = 0


class ModelCheckpointing:
    """Manages model checkpoints for autocog training.

    Features:
    - Save best models based on validation metric
    - Keep top N checkpoints
    - Support rollback to previous best
    - Periodic checkpointing
    - Integration with GradientLearningOptimizer

    Example:
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir="checkpoints/calibration",
                max_checkpoints=5,
                metric_name="val_loss",
                metric_direction="minimize",
            )
        )

        # After each epoch
        is_best = checkpointing.check_and_save(
            epoch=1,
            params=model_params,
            metrics={"val_loss": 0.5, "accuracy": 0.9},
        )

        # Rollback if needed
        if should_rollback:
            params = checkpointing.rollback_to_best()
    """

    def __init__(
        self,
        config: ModelCheckpointConfig | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ):
        """Initialize model checkpointing.

        Args:
            config: Checkpointing configuration
            checkpoint_manager: Optional GradientLearning CheckpointManager
        """
        self.config = config or ModelCheckpointConfig()

        # Use provided CheckpointManager or create new one
        if checkpoint_manager:
            self._checkpoint_manager = checkpoint_manager
        else:
            self._checkpoint_manager = CheckpointManager(
                checkpoint_dir=self.config.checkpoint_dir,
                max_checkpoints=self.config.max_checkpoints,
            )

        self._best_checkpoint: ModelCheckpoint | None = None
        self._checkpoints: list[ModelCheckpoint] = []
        self._best_metric_value: float = (
            float("inf")
            if self.config.metric_direction == "minimize"
            else float("-inf")
        )

    @property
    def best_checkpoint(self) -> ModelCheckpoint | None:
        """Get the current best checkpoint."""
        return self._best_checkpoint

    @property
    def checkpoints(self) -> list[ModelCheckpoint]:
        """Get all checkpoints."""
        return self._checkpoints.copy()

    def _get_metric_value(self, metrics: dict[str, float]) -> float:
        """Extract metric value from metrics dict.

        Args:
            metrics: Metrics dictionary

        Returns:
            Metric value
        """
        metric_name = self.config.metric_name
        if metric_name not in metrics:
            # Try common alternatives
            for alt in ["val_loss", "loss", "validation_loss"]:
                if alt in metrics:
                    metric_name = alt
                    break
            else:
                raise ValueError(
                    f"Metric '{self.config.metric_name}' not found in metrics. "
                    f"Available: {list(metrics.keys())}"
                )

        return metrics[metric_name]

    def _is_better(self, metrics: dict[str, float]) -> bool:
        """Check if metrics represent an improvement.

        Args:
            metrics: Current metrics

        Returns:
            True if metrics are better than current best
        """
        current_value = self._get_metric_value(metrics)

        if self.config.metric_direction == "minimize":
            return current_value < self._best_metric_value
        else:
            return current_value > self._best_metric_value

    def check_and_save(
        self,
        epoch: int,
        params: dict[str, float],
        metrics: dict[str, float] | None = None,
        checkpoint_type: CheckpointType = CheckpointType.PERIODIC,
    ) -> bool:
        """Check if checkpoint should be saved and save it.

        Args:
            epoch: Current epoch number
            params: Model parameters to save
            metrics: Current validation metrics
            checkpoint_type: Type of checkpoint

        Returns:
            True if this is the new best model
        """
        metrics = metrics or {}

        # Check if this is a new best
        is_best = False

        if self._best_checkpoint is None or self._is_better(metrics):
            is_best = True
            best_metric_value = self._get_metric_value(metrics)

            if self.config.metric_direction == "minimize":
                improved_by = self._best_metric_value - best_metric_value
            else:
                improved_by = best_metric_value - self._best_metric_value

            logger.info(
                f"New best model at epoch {epoch}: "
                f"{self.config.metric_name}={best_metric_value:.6f} "
                f"(improved by {improved_by:.6f})"
            )

            self._best_metric_value = best_metric_value
            self._best_checkpoint = ModelCheckpoint(
                checkpoint_id=f"best_epoch_{epoch}",
                checkpoint_type=CheckpointType.BEST,
                epoch=epoch,
                params=params.copy(),
                metrics=metrics.copy(),
                is_best=True,
            )

            # Update previous best to non-best
            for cp in self._checkpoints:
                cp.is_best = False

        # Determine if we should save this checkpoint
        should_save = False

        if (
            self.config.save_best_only
            and not is_best
            or checkpoint_type == CheckpointType.BEST
            and not is_best
        ):
            should_save = False
        elif self.config.save_every_n_epochs > 0:
            should_save = epoch % self.config.save_every_n_epochs == 0
        else:
            should_save = is_best

        if should_save:
            return self._save_checkpoint(
                epoch, params, metrics, checkpoint_type, is_best
            )

        return is_best

    def _save_checkpoint(
        self,
        epoch: int,
        params: dict[str, float],
        metrics: dict[str, float],
        checkpoint_type: CheckpointType,
        is_best: bool,
    ) -> bool:
        """Save a checkpoint.

        Args:
            epoch: Current epoch
            params: Model parameters
            metrics: Validation metrics
            checkpoint_type: Type of checkpoint
            is_best: Whether this is the best model

        Returns:
            True if saved successfully
        """
        checkpoint_id = f"epoch_{epoch}_{checkpoint_type.value}"

        if is_best:
            checkpoint_id = f"best_epoch_{epoch}"

        checkpoint = ModelCheckpoint(
            checkpoint_id=checkpoint_id,
            checkpoint_type=checkpoint_type,
            epoch=epoch,
            params=params.copy(),
            metrics=metrics.copy(),
            is_best=is_best,
        )

        self._checkpoints.append(checkpoint)

        # Save to disk using GradientLearning CheckpointManager
        try:
            from src.autonomous_cognition.gradient_learning import Checkpoint

            disk_checkpoint = Checkpoint(
                checkpoint_id=checkpoint_id,
                step=epoch,
                params=params.copy(),
                optimizer_state={},
                scheduler_state=None,
                clipper_state=None,
                metrics=metrics.copy(),
            )

            self._checkpoint_manager.save(disk_checkpoint, checkpoint_id)

            # Also save metadata
            metadata_path = (
                Path(self.config.checkpoint_dir)
                / f"checkpoint_{checkpoint_id}_meta.json"
            )
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with open(metadata_path, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)

            logger.debug(f"Saved checkpoint {checkpoint_id}")

        except Exception as e:
            logger.warning(f"Failed to save checkpoint to disk: {e}")

        # Cleanup old checkpoints
        self._cleanup_checkpoints()

        return True

    def _cleanup_checkpoints(self) -> None:
        """Remove old checkpoints exceeding max_checkpoints limit."""
        if len(self._checkpoints) <= self.config.max_checkpoints:
            return

        # Sort by epoch (keep most recent)
        sorted_checkpoints = sorted(
            self._checkpoints,
            key=lambda x: (not x.is_best, x.epoch),
            reverse=True,
        )

        # Remove excess
        to_remove = sorted_checkpoints[self.config.max_checkpoints :]
        self._checkpoints = sorted_checkpoints[: self.config.max_checkpoints]

        # Remove from disk
        for cp in to_remove:
            if not cp.is_best:  # Don't remove best
                try:
                    self._checkpoint_manager.delete(cp.checkpoint_id)
                    meta_path = (
                        Path(self.config.checkpoint_dir)
                        / f"checkpoint_{cp.checkpoint_id}_meta.json"
                    )
                    if meta_path.exists():
                        meta_path.unlink()
                except Exception as e:
                    logger.warning(
                        f"Failed to delete checkpoint {cp.checkpoint_id}: {e}"
                    )

    def rollback_to_best(self) -> dict[str, float] | None:
        """Rollback to the best checkpoint.

        Returns:
            Parameters from best checkpoint or None
        """
        if self._best_checkpoint is None:
            logger.warning("No best checkpoint to rollback to")
            return None

        logger.info(
            f"Rolling back to best checkpoint: "
            f"epoch={self._best_checkpoint.epoch}, "
            f"metrics={self._best_checkpoint.metrics}"
        )

        return self._best_checkpoint.params.copy()

    def rollback_to_epoch(self, epoch: int) -> dict[str, float] | None:
        """Rollback to a specific epoch.

        Args:
            epoch: Epoch number to rollback to

        Returns:
            Parameters at that epoch or None
        """
        for cp in self._checkpoints:
            if cp.epoch == epoch:
                logger.info(f"Rolling back to epoch {epoch}, metrics={cp.metrics}")
                return cp.params.copy()

        logger.warning(f"No checkpoint found for epoch {epoch}")
        return None

    def get_best_params(self) -> dict[str, float] | None:
        """Get parameters from the best checkpoint.

        Returns:
            Best parameters or None
        """
        if self._best_checkpoint is None:
            return None
        return self._best_checkpoint.params.copy()

    def get_best_metrics(self) -> dict[str, float] | None:
        """Get metrics from the best checkpoint.

        Returns:
            Best metrics or None
        """
        if self._best_checkpoint is None:
            return None
        return self._best_checkpoint.metrics.copy()

    def get_checkpoint_info(self) -> list[dict[str, Any]]:
        """Get info about all checkpoints.

        Returns:
            List of checkpoint info dicts
        """
        return [
            {
                "checkpoint_id": cp.checkpoint_id,
                "epoch": cp.epoch,
                "checkpoint_type": cp.checkpoint_type.value,
                "is_best": cp.is_best,
                "metrics": cp.metrics,
                "created_at": cp.created_at,
            }
            for cp in self._checkpoints
        ]

    def load_checkpoint_info(self) -> None:
        """Load checkpoint metadata from disk."""
        checkpoint_dir = Path(self.config.checkpoint_dir)
        if not checkpoint_dir.exists():
            return

        # Load metadata files
        for meta_file in checkpoint_dir.glob("checkpoint_*_meta.json"):
            try:
                with open(meta_file) as f:
                    data = json.load(f)

                checkpoint = ModelCheckpoint(
                    checkpoint_id=data["checkpoint_id"],
                    checkpoint_type=CheckpointType(data["checkpoint_type"]),
                    epoch=data["epoch"],
                    params=data["params"],
                    metrics=data.get("metrics"),
                    created_at=data.get("created_at", ""),
                    is_best=data.get("is_best", False),
                )

                self._checkpoints.append(checkpoint)

                # Track best
                if checkpoint.is_best:
                    self._best_checkpoint = checkpoint
                    if (
                        checkpoint.metrics
                        and self.config.metric_name in checkpoint.metrics
                    ):
                        self._best_metric_value = checkpoint.metrics[
                            self.config.metric_name
                        ]

            except Exception as e:
                logger.warning(f"Failed to load checkpoint metadata {meta_file}: {e}")

        # Sort checkpoints by epoch
        self._checkpoints.sort(key=lambda x: x.epoch, reverse=True)


def create_model_checkpointing(
    checkpoint_dir: str = "checkpoints/autocog",
    max_checkpoints: int = 5,
    metric_name: str = "val_loss",
    metric_direction: str = "minimize",
    save_best_only: bool = True,
) -> ModelCheckpointing:
    """Factory function to create ModelCheckpointing.

    Args:
        checkpoint_dir: Directory for checkpoints
        max_checkpoints: Maximum checkpoints to keep
        metric_name: Metric for best selection
        metric_direction: 'minimize' or 'maximize'
        save_best_only: Only save best models

    Returns:
        Configured ModelCheckpointing instance
    """
    config = ModelCheckpointConfig(
        checkpoint_dir=checkpoint_dir,
        max_checkpoints=max_checkpoints,
        metric_name=metric_name,
        metric_direction=metric_direction,
        save_best_only=save_best_only,
    )

    return ModelCheckpointing(config=config)
