"""High-level artifact manager for training artifacts.

Provides a unified interface for managing training artifacts across
experiments, including save, load, query, and delete operations.

Coordinates between different artifact types and the storage backend.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ml.training.artifacts.models import (
    ArtifactType,
    CheckpointArtifact,
    ConfigArtifact,
    LogArtifact,
    TrainingArtifact,
)
from ml.training.artifacts.storage import ArtifactStorage

logger = logging.getLogger(__name__)


class ArtifactManager:
    """High-level interface for training artifact operations.

    Wraps ArtifactStorage with experiment-scoped convenience methods
    and type-safe artifact handling.

    Example:
        manager = ArtifactManager(base_path="/data/artifacts")

        # Save artifacts
        manager.save_checkpoint(checkpoint, binary_weights)
        manager.save_config(config)
        manager.save_log(log)

        # Query artifacts
        checkpoints = manager.get_checkpoints("exp-001")
        config = manager.get_config("exp-001")

        # Delete
        manager.delete_artifact("ckpt-001", "exp-001")
    """

    def __init__(self, base_path: str | Path) -> None:
        """Initialize the artifact manager.

        Args:
            base_path: Root directory for all artifact storage
        """
        self._base_path = Path(base_path)
        self._storage = ArtifactStorage()

    @property
    def base_path(self) -> Path:
        """Return the configured base path."""
        return self._base_path

    def save_artifact(
        self,
        artifact: TrainingArtifact,
        binary_data: bytes | None = None,
    ) -> Path:
        """Save any artifact type to storage.

        Args:
            artifact: TrainingArtifact instance
            binary_data: Optional binary payload

        Returns:
            Path to the saved metadata file
        """
        return self._storage.save_artifact(artifact, self._base_path, binary_data)

    def save_checkpoint(
        self,
        checkpoint: CheckpointArtifact,
        binary_data: bytes | None = None,
    ) -> Path:
        """Save a checkpoint artifact.

        Args:
            checkpoint: CheckpointArtifact instance
            binary_data: Optional model weights binary data

        Returns:
            Path to the saved metadata file
        """
        logger.info(
            "Saving checkpoint %s for experiment %s (epoch %d)",
            checkpoint.artifact_id,
            checkpoint.experiment_id,
            checkpoint.epoch,
        )
        return self.save_artifact(checkpoint, binary_data)

    def save_config(self, config: ConfigArtifact) -> Path:
        """Save a configuration artifact.

        Args:
            config: ConfigArtifact instance

        Returns:
            Path to the saved metadata file
        """
        logger.info(
            "Saving config %s for experiment %s",
            config.artifact_id,
            config.experiment_id,
        )
        return self.save_artifact(config)

    def save_log(self, log: LogArtifact) -> Path:
        """Save a log artifact.

        Args:
            log: LogArtifact instance

        Returns:
            Path to the saved metadata file
        """
        logger.info(
            "Saving log %s for experiment %s (status=%s)",
            log.artifact_id,
            log.experiment_id,
            log.status,
        )
        return self.save_artifact(log)

    def load_artifact(self, artifact_id: str) -> TrainingArtifact:
        """Load an artifact by ID.

        Args:
            artifact_id: Unique artifact identifier

        Returns:
            Loaded TrainingArtifact instance
        """
        return self._storage.load_artifact(artifact_id, self._base_path)

    def load_binary(self, artifact_id: str) -> bytes | None:
        """Load binary data for an artifact.

        Args:
            artifact_id: Unique artifact identifier

        Returns:
            Binary data or None
        """
        return self._storage.load_binary(artifact_id, self._base_path)

    def get_artifacts(
        self,
        experiment_id: str,
        artifact_type: ArtifactType | None = None,
    ) -> list[TrainingArtifact]:
        """Get all artifacts for an experiment.

        Args:
            experiment_id: Experiment to query
            artifact_type: Optional type filter

        Returns:
            List of matching artifacts
        """
        return self._storage.list_artifacts(
            experiment_id, self._base_path, artifact_type
        )

    def get_checkpoints(self, experiment_id: str) -> list[CheckpointArtifact]:
        """Get all checkpoints for an experiment.

        Args:
            experiment_id: Experiment to query

        Returns:
            List of CheckpointArtifact instances
        """
        artifacts = self._storage.list_artifacts(
            experiment_id, self._base_path, ArtifactType.CHECKPOINT
        )
        return [a for a in artifacts if isinstance(a, CheckpointArtifact)]

    def get_configs(self, experiment_id: str) -> list[ConfigArtifact]:
        """Get all configs for an experiment.

        Args:
            experiment_id: Experiment to query

        Returns:
            List of ConfigArtifact instances
        """
        artifacts = self._storage.list_artifacts(
            experiment_id, self._base_path, ArtifactType.CONFIG
        )
        return [a for a in artifacts if isinstance(a, ConfigArtifact)]

    def get_logs(self, experiment_id: str) -> list[LogArtifact]:
        """Get all logs for an experiment.

        Args:
            experiment_id: Experiment to query

        Returns:
            List of LogArtifact instances
        """
        artifacts = self._storage.list_artifacts(
            experiment_id, self._base_path, ArtifactType.LOG
        )
        return [a for a in artifacts if isinstance(a, LogArtifact)]

    def get_best_checkpoint(
        self, experiment_id: str, metric_key: str = "val_loss", minimize: bool = True
    ) -> CheckpointArtifact | None:
        """Get the best checkpoint by a specific metric.

        Args:
            experiment_id: Experiment to query
            metric_key: Metric name to compare (e.g., "val_loss", "accuracy")
            minimize: If True, find minimum; if False, find maximum

        Returns:
            Best CheckpointArtifact or None if no checkpoints exist
        """
        checkpoints = self.get_checkpoints(experiment_id)
        if not checkpoints:
            return None

        best = checkpoints[0]
        best_value = best.metrics_snapshot.get(metric_key)

        for ckpt in checkpoints[1:]:
            value = ckpt.metrics_snapshot.get(metric_key)
            if value is None:
                continue
            if best_value is None or minimize and value < best_value or not minimize and value > best_value:
                best, best_value = ckpt, value

        return best

    def get_latest_checkpoint(self, experiment_id: str) -> CheckpointArtifact | None:
        """Get the most recent checkpoint by epoch number.

        Args:
            experiment_id: Experiment to query

        Returns:
            CheckpointArtifact with highest epoch, or None
        """
        checkpoints = self.get_checkpoints(experiment_id)
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda c: c.epoch)

    def list_experiments(self) -> list[str]:
        """List all experiment IDs.

        Returns:
            Sorted list of experiment ID strings
        """
        return self._storage.list_experiments(self._base_path)

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact by ID.

        Args:
            experiment_id: Experiment the artifact belongs to
            artifact_id: Unique artifact identifier

        Returns:
            True if deleted
        """
        return self._storage.delete_artifact(artifact_id, self._base_path)

    def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an entire experiment and all its artifacts.

        Args:
            experiment_id: Experiment to delete

        Returns:
            True if deleted
        """
        logger.info("Deleting experiment %s", experiment_id)
        return self._storage.delete_experiment(experiment_id, self._base_path)

    def experiment_summary(self, experiment_id: str) -> dict[str, Any]:
        """Get a summary of all artifacts for an experiment.

        Args:
            experiment_id: Experiment to summarize

        Returns:
            Dictionary with artifact counts and latest info
        """
        checkpoints = self.get_checkpoints(experiment_id)
        configs = self.get_configs(experiment_id)
        logs = self.get_logs(experiment_id)

        summary: dict[str, Any] = {
            "experiment_id": experiment_id,
            "checkpoint_count": len(checkpoints),
            "config_count": len(configs),
            "log_count": len(logs),
            "latest_checkpoint_epoch": (
                max(c.epoch for c in checkpoints) if checkpoints else None
            ),
            "latest_config_id": configs[-1].artifact_id if configs else None,
            "latest_log_status": logs[-1].status if logs else None,
        }

        if logs:
            latest_log = logs[-1]
            summary["training_duration_seconds"] = latest_log.training_duration_seconds
            summary["final_metrics"] = latest_log.final_metrics

        return summary
