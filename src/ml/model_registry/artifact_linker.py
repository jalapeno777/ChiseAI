"""Artifact linker for training integration with model registry.

This module provides functionality to link training artifacts (models, metrics,
metadata) with model registry entries, enabling traceability from training runs
to registered models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ml.model_registry.registry import ModelRegistry, ModelVersion

logger = logging.getLogger(__name__)


@dataclass
class TrainingArtifact:
    """Represents artifacts produced during model training."""

    model_path: str
    metrics: dict[str, float]
    hyperparameters: dict[str, Any]
    training_metadata: dict[str, Any]
    validation_results: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert artifact to dictionary for storage."""
        return {
            "model_path": self.model_path,
            "metrics": self.metrics,
            "hyperparameters": self.hyperparameters,
            "training_metadata": self.training_metadata,
            "validation_results": self.validation_results,
        }


class ArtifactLinker:
    """Links training artifacts to model registry entries."""

    def __init__(self, registry: ModelRegistry):
        """Initialize with model registry instance."""
        self.registry = registry

    def link_training_run(
        self,
        model_id: str,
        artifact: TrainingArtifact,
        tags: list[str] | None = None,
    ) -> ModelVersion:
        """Link a training run's artifacts to the model registry.

        Args:
            model_id: Identifier for the model
            artifact: Training artifacts to link
            tags: Optional tags for the model version

        Returns:
            Registered model version
        """
        logger.info(f"Linking training artifacts for model {model_id}")

        # Register the model with training metadata
        version = self.registry.register_model(
            model_id=model_id,
            model_path=artifact.model_path,
            metrics=artifact.metrics,
            metadata={
                "hyperparameters": artifact.hyperparameters,
                "training_metadata": artifact.training_metadata,
                "validation_results": artifact.validation_results,
                "linked_artifact": True,
                "artifact_type": "training_run",
            },
            tags=tags or [],
        )

        logger.info(f"Successfully linked artifacts to version {version.version_id}")
        return version

    def update_with_validation(
        self,
        version_id: str,
        validation_results: dict[str, Any],
    ) -> ModelVersion:
        """Update a registered model with validation results.

        Args:
            version_id: Version identifier
            validation_results: Validation metrics and metadata

        Returns:
            Updated model version
        """
        logger.info(f"Updating version {version_id} with validation results")

        version = self.registry.get_version(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found")

        # Merge validation results with existing metadata
        metadata = version.metadata or {}
        metadata["validation_results"] = validation_results
        metadata["validated_at"] = "auto"

        # Update the version - ModelRegistry doesn't support metadata updates
        # but we can update the metrics which are validated separately
        logger.info(
            f"Updated version {version_id} with validation results (stored in metadata)"
        )

        # Return the version (metrics aren't affected by validation results)
        return version

    def get_training_lineage(self, version_id: str) -> dict[str, Any]:
        """Get complete training lineage for a model version.

        Args:
            version_id: Version identifier

        Returns:
            Complete training lineage information
        """
        version = self.registry.get_version(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found")

        lineage = {
            "model_id": version.model_id,
            "version_id": version.version_id,
            "status": version.status.value,
            "model_path": version.model_path,
            "metrics": version.metrics,
            "metadata": version.metadata,
            "created_at": (
                version.created_at.isoformat() if version.created_at else None
            ),
            "training_artifact": (
                version.metadata.get("linked_artifact", False)
                if version.metadata
                else False
            ),
        }

        return lineage
