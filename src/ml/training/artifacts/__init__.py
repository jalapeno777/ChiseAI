"""Training Artifact Tracking for ChiseAI.

Provides dataclass-based artifact tracking for training runs, including
model checkpoints, configuration snapshots, and training logs.

Components:
- models: Dataclass definitions for artifact types
- storage: Filesystem-based artifact storage backend
- manager: High-level artifact management interface

Usage:
    from ml.training.artifacts import (
        TrainingArtifact,
        CheckpointArtifact,
        ConfigArtifact,
        LogArtifact,
        ArtifactType,
        ArtifactStorage,
        ArtifactManager,
    )

    # Create and save a checkpoint
    checkpoint = CheckpointArtifact(
        artifact_id="ckpt-001",
        experiment_id="exp-001",
        checkpoint_path="/models/checkpoint.pt",
        epoch=10,
        metrics_snapshot={"val_loss": 0.05, "accuracy": 0.95},
    )

    manager = ArtifactManager(base_path="/data/artifacts")
    manager.save_checkpoint(checkpoint, binary_data=model_weights)
"""

from __future__ import annotations

from ml.training.artifacts.manager import ArtifactManager
from ml.training.artifacts.models import (
    ArtifactType,
    CheckpointArtifact,
    ConfigArtifact,
    LogArtifact,
    TrainingArtifact,
)
from ml.training.artifacts.storage import (
    ArtifactNotFoundError,
    ArtifactStorage,
    ArtifactStorageError,
)

__all__ = [
    # Models
    "TrainingArtifact",
    "CheckpointArtifact",
    "ConfigArtifact",
    "LogArtifact",
    "ArtifactType",
    # Storage
    "ArtifactStorage",
    "ArtifactStorageError",
    "ArtifactNotFoundError",
    # Manager
    "ArtifactManager",
]
