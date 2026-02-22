"""Model Registry for ChiseAI.

Provides versioning, storage, and retrieval of ML models with metadata
and rollback support.

Key Components:
- ModelRegistry: Main registry for model versioning and management
- ModelMetadata: Metadata schema for model versions
- ModelVersion: Version information with storage paths
- FilesystemBackend: Local filesystem storage
- S3Backend: S3 storage interface (future implementation)
- SemanticVersion: Semantic versioning helper

Usage:
    from ml.models import (
        ModelRegistry,
        ModelMetadata,
        ModelVersion,
        FilesystemBackend,
        ModelRegistryFactory,
    )

    # Create registry
    registry = ModelRegistryFactory.create_filesystem_registry("models")

    # Register a model
    from datetime import datetime
    metadata = ModelMetadata(
        model_name="price_predictor",
        version="1.0.0",
        created_at=datetime.utcnow(),
        training_data="dataset_v1",
        hyperparameters={"lr": 0.001},
        metrics={"accuracy": 0.95},
        tags=["production"],
    )
    version = registry.register_model(my_model, metadata)

    # Get latest model
    model, meta = registry.get_latest("price_predictor")

    # Rollback to previous version
    registry.rollback("price_predictor", "0.9.0")
"""

from __future__ import annotations

from ml.models.model_registry import (
    ModelRegistry,
    ModelRegistryFactory,
    SemanticVersion,
)
from ml.models.model_storage import (
    FilesystemBackend,
    ModelMetadata,
    ModelVersion,
    S3Backend,
    StorageBackend,
)

__all__ = [
    # Registry
    "ModelRegistry",
    "ModelRegistryFactory",
    "SemanticVersion",
    # Storage
    "FilesystemBackend",
    "S3Backend",
    "StorageBackend",
    # Data classes
    "ModelMetadata",
    "ModelVersion",
]
