"""Checkpointing for parameter state persistence and rollback.

This module provides checkpoint save/load functionality for parameter states,
supporting both JSON and pickle formats.
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Represents a saved checkpoint of parameter state.

    Attributes:
        checkpoint_id: Unique identifier for this checkpoint
        step: Optimization step number
        params: Parameter values at checkpoint time
        optimizer_state: Optimizer state at checkpoint time
        scheduler_state: Learning rate scheduler state
        clipper_state: Gradient clipper state
        metrics: Optional metrics snapshot
        timestamp: When checkpoint was created
        metadata: Additional metadata
    """

    checkpoint_id: str
    step: int
    params: dict[str, float]
    optimizer_state: dict[str, Any]
    scheduler_state: dict[str, Any] | None = None
    clipper_state: dict[str, Any] | None = None
    metrics: dict[str, float] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "step": self.step,
            "params": self.params,
            "optimizer_state": self.optimizer_state,
            "scheduler_state": self.scheduler_state,
            "clipper_state": self.clipper_state,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        """Create checkpoint from dictionary."""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            step=data["step"],
            params=data["params"],
            optimizer_state=data["optimizer_state"],
            scheduler_state=data.get("scheduler_state"),
            clipper_state=data.get("clipper_state"),
            metrics=data.get("metrics"),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


class CheckpointManager:
    """Manages checkpoint save/load operations.

    Supports both JSON and pickle formats for serialization.
    """

    DEFAULT_MAX_CHECKPOINTS = 10

    def __init__(
        self,
        checkpoint_dir: str | Path = "checkpoints",
        max_checkpoints: int | None = None,
        format: str = "json",
    ):
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoints
            max_checkpoints: Maximum number of checkpoints to keep (default: 10)
            format: Serialization format ('json' or 'pickle')
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.max_checkpoints = max_checkpoints or self.DEFAULT_MAX_CHECKPOINTS
        self.format = format.lower()

        if self.format not in ("json", "pickle"):
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'pickle'")

        # Create directory if it doesn't exist
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_checkpoint_path(self, checkpoint_id: str) -> Path:
        """Get file path for a checkpoint.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            Path to checkpoint file
        """
        ext = ".json" if self.format == "json" else ".pkl"
        return self.checkpoint_dir / f"checkpoint_{checkpoint_id}{ext}"

    def save(
        self,
        checkpoint: Checkpoint,
        checkpoint_id: str | None = None,
    ) -> str:
        """Save a checkpoint.

        Args:
            checkpoint: Checkpoint to save
            checkpoint_id: Optional checkpoint ID override

        Returns:
            Checkpoint ID used
        """
        if checkpoint_id:
            checkpoint.checkpoint_id = checkpoint_id

        path = self._get_checkpoint_path(checkpoint.checkpoint_id)

        if self.format == "json":
            with open(path, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
        else:
            with open(path, "wb") as f:
                pickle.dump(checkpoint, f)

        logger.info(
            "Saved checkpoint %s at step %d to %s",
            checkpoint.checkpoint_id,
            checkpoint.step,
            path,
        )

        # Clean up old checkpoints
        self._cleanup_old_checkpoints()

        return checkpoint.checkpoint_id

    def load(self, checkpoint_id: str) -> Checkpoint:
        """Load a checkpoint.

        Args:
            checkpoint_id: Checkpoint identifier to load

        Returns:
            Loaded Checkpoint

        Raises:
            FileNotFoundError: If checkpoint doesn't exist
        """
        path = self._get_checkpoint_path(checkpoint_id)

        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")

        if self.format == "json":
            with open(path) as f:
                data = json.load(f)
            return Checkpoint.from_dict(data)
        else:
            with open(path, "rb") as f:
                return pickle.load(f)

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """List all available checkpoints.

        Returns:
            List of checkpoint info (id, step, timestamp)
        """
        checkpoints = []
        for path in sorted(self.checkpoint_dir.glob("checkpoint_*")):
            if self.format == "json" and path.suffix == ".json":
                try:
                    with open(path) as f:
                        data = json.load(f)
                    checkpoints.append(
                        {
                            "checkpoint_id": data.get("checkpoint_id", path.stem),
                            "step": data.get("step", 0),
                            "timestamp": data.get("timestamp", ""),
                        }
                    )
                except (json.JSONDecodeError, KeyError):
                    logger.warning("Invalid checkpoint file: %s", path)
            elif self.format == "pickle" and path.suffix == ".pkl":
                try:
                    with open(path, "rb") as f:
                        cp = pickle.load(f)
                    checkpoints.append(
                        {
                            "checkpoint_id": cp.checkpoint_id,
                            "step": cp.step,
                            "timestamp": cp.timestamp,
                        }
                    )
                except Exception as e:
                    logger.warning("Invalid checkpoint file: %s: %s", path, e)

        return sorted(checkpoints, key=lambda x: x["step"])

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint identifier to delete

        Returns:
            True if deleted, False if not found
        """
        path = self._get_checkpoint_path(checkpoint_id)
        if path.exists():
            path.unlink()
            logger.info("Deleted checkpoint: %s", checkpoint_id)
            return True
        return False

    def _cleanup_old_checkpoints(self) -> None:
        """Remove old checkpoints exceeding max_checkpoints limit."""
        checkpoints = self.list_checkpoints()
        if len(checkpoints) > self.max_checkpoints:
            # Delete oldest checkpoints
            to_delete = checkpoints[: len(checkpoints) - self.max_checkpoints]
            for cp_info in to_delete:
                self.delete(cp_info["checkpoint_id"])

    def rollback(
        self,
        target_step: int | None = None,
        checkpoint_id: str | None = None,
    ) -> Checkpoint:
        """Rollback to a specific checkpoint.

        Args:
            target_step: Step number to rollback to (uses latest if None)
            checkpoint_id: Specific checkpoint ID to restore

        Returns:
            Checkpoint to restore

        Raises:
            ValueError: If neither target_step nor checkpoint_id is provided
        """
        if checkpoint_id:
            return self.load(checkpoint_id)

        if target_step is not None:
            checkpoints = self.list_checkpoints()
            for cp in checkpoints:
                if cp["step"] == target_step:
                    return self.load(cp["checkpoint_id"])
            raise ValueError(f"No checkpoint found at step {target_step}")

        raise ValueError("Must provide either target_step or checkpoint_id")
