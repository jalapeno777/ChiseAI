"""Training artifact data models for ChiseAI.

Provides dataclass-based artifact tracking for training runs, including
model checkpoints, configuration snapshots, and training logs.

All artifacts support to_dict/from_dict and to_json/from_json serialization,
following the pattern established in ml.models.model_storage.ModelMetadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ArtifactType(str, Enum):
    """Types of training artifacts."""

    CHECKPOINT = "checkpoint"
    CONFIG = "config"
    LOG = "log"


@dataclass
class TrainingArtifact:
    """Base training artifact with common fields.

    Attributes:
        artifact_id: Unique artifact identifier
        experiment_id: Parent experiment identifier
        created_at: UTC timestamp when artifact was created
        artifact_type: Type of artifact (checkpoint, config, log)
        metadata: Additional metadata key-value pairs
    """

    artifact_id: str
    experiment_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    artifact_type: ArtifactType = ArtifactType.LOG
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "experiment_id": self.experiment_id,
            "created_at": self.created_at.isoformat(),
            "artifact_type": self.artifact_type.value,
            "metadata": self.metadata,
        }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainingArtifact:
        """Create artifact from dictionary."""
        return cls(
            artifact_id=data["artifact_id"],
            experiment_id=data["experiment_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            artifact_type=ArtifactType(data["artifact_type"]),
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> TrainingArtifact:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class CheckpointArtifact(TrainingArtifact):
    """Model checkpoint artifact with path, epoch, and metrics snapshot.

    Attributes:
        checkpoint_path: Filesystem path to the checkpoint file
        epoch: Training epoch number
        metrics_snapshot: Metrics recorded at checkpoint time
        model_architecture: Optional model architecture identifier
        file_size_bytes: Optional file size for tracking
    """

    checkpoint_path: str = ""
    epoch: int = 0
    metrics_snapshot: dict[str, float] = field(default_factory=dict)
    model_architecture: str | None = None
    file_size_bytes: int | None = None

    def __post_init__(self) -> None:
        """Set artifact_type to checkpoint."""
        self.artifact_type = ArtifactType.CHECKPOINT

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = super().to_dict()
        result.update(
            {
                "checkpoint_path": self.checkpoint_path,
                "epoch": self.epoch,
                "metrics_snapshot": self.metrics_snapshot,
                "model_architecture": self.model_architecture,
                "file_size_bytes": self.file_size_bytes,
            }
        )
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointArtifact:
        """Create checkpoint artifact from dictionary."""
        return cls(
            artifact_id=data["artifact_id"],
            experiment_id=data["experiment_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            artifact_type=ArtifactType(data.get("artifact_type", "checkpoint")),
            metadata=data.get("metadata", {}),
            checkpoint_path=data["checkpoint_path"],
            epoch=data["epoch"],
            metrics_snapshot=data.get("metrics_snapshot", {}),
            model_architecture=data.get("model_architecture"),
            file_size_bytes=data.get("file_size_bytes"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> CheckpointArtifact:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class ConfigArtifact(TrainingArtifact):
    """Training configuration artifact with hyperparameters and model architecture.

    Attributes:
        hyperparameters: Training hyperparameters (lr, batch_size, epochs, etc.)
        model_architecture: Model architecture name or config
        data_config: Data preprocessing and split configuration
        random_seed: Random seed for reproducibility
        framework: ML framework used (pytorch, tensorflow, sklearn, etc.)
    """

    hyperparameters: dict[str, Any] = field(default_factory=dict)
    model_architecture: str = ""
    data_config: dict[str, Any] = field(default_factory=dict)
    random_seed: int | None = None
    framework: str | None = None

    def __post_init__(self) -> None:
        """Set artifact_type to config."""
        self.artifact_type = ArtifactType.CONFIG

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = super().to_dict()
        result.update(
            {
                "hyperparameters": self.hyperparameters,
                "model_architecture": self.model_architecture,
                "data_config": self.data_config,
                "random_seed": self.random_seed,
                "framework": self.framework,
            }
        )
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigArtifact:
        """Create config artifact from dictionary."""
        return cls(
            artifact_id=data["artifact_id"],
            experiment_id=data["experiment_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            artifact_type=ArtifactType(data.get("artifact_type", "config")),
            metadata=data.get("metadata", {}),
            hyperparameters=data.get("hyperparameters", {}),
            model_architecture=data.get("model_architecture", ""),
            data_config=data.get("data_config", {}),
            random_seed=data.get("random_seed"),
            framework=data.get("framework"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> ConfigArtifact:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class LogArtifact(TrainingArtifact):
    """Training log artifact with metrics history and loss curves.

    Attributes:
        metrics_history: List of epoch-level metric snapshots
        loss_curve: List of (epoch, loss) tuples for training loss
        val_loss_curve: List of (epoch, loss) tuples for validation loss
        training_duration_seconds: Total training duration in seconds
        final_metrics: Final training metrics at end of training
        status: Final training status (completed, failed, cancelled)
    """

    metrics_history: list[dict[str, Any]] = field(default_factory=list)
    loss_curve: list[dict[str, float]] = field(default_factory=list)
    val_loss_curve: list[dict[str, float]] = field(default_factory=list)
    training_duration_seconds: float = 0.0
    final_metrics: dict[str, float] = field(default_factory=dict)
    status: str = "completed"

    def __post_init__(self) -> None:
        """Set artifact_type to log."""
        self.artifact_type = ArtifactType.LOG

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = super().to_dict()
        result.update(
            {
                "metrics_history": self.metrics_history,
                "loss_curve": self.loss_curve,
                "val_loss_curve": self.val_loss_curve,
                "training_duration_seconds": self.training_duration_seconds,
                "final_metrics": self.final_metrics,
                "status": self.status,
            }
        )
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogArtifact:
        """Create log artifact from dictionary."""
        return cls(
            artifact_id=data["artifact_id"],
            experiment_id=data["experiment_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            artifact_type=ArtifactType(data.get("artifact_type", "log")),
            metadata=data.get("metadata", {}),
            metrics_history=data.get("metrics_history", []),
            loss_curve=data.get("loss_curve", []),
            val_loss_curve=data.get("val_loss_curve", []),
            training_duration_seconds=data.get("training_duration_seconds", 0.0),
            final_metrics=data.get("final_metrics", {}),
            status=data.get("status", "completed"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> LogArtifact:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))
