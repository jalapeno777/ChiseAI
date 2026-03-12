"""Model storage backends for ChiseAI Model Registry.

Provides pluggable storage backends for model artifacts:
- FilesystemBackend: Local filesystem storage (primary)
- S3Backend: AWS S3 storage (interface for future implementation)
"""

from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib


class ModelRegistryError(Exception):
    """Base exception for model registry errors."""

    pass


class ModelNotFoundError(ModelRegistryError):
    """Raised when a model or version is not found."""

    pass


class ModelVersionExistsError(ModelRegistryError):
    """Raised when attempting to register a version that already exists."""

    pass


class ModelValidationError(ModelRegistryError):
    """Raised when model validation fails."""

    pass


class ModelIntegrityError(ModelRegistryError):
    """Raised when model integrity check fails."""

    pass


class StorageBackendError(ModelRegistryError):
    """Raised when storage backend operation fails."""

    pass


@dataclass(frozen=True)
class ModelMetadata:
    """Metadata for a registered model version.

    Attributes:
        model_name: Name of the model
        version: Semantic version string (MAJOR.MINOR.PATCH)
        created_at: UTC timestamp when model was registered
        training_data: Reference to training dataset
        hyperparameters: Model hyperparameters dict
        metrics: Performance metrics dict (accuracy, precision, recall, F1, etc.)
        tags: List of tags for categorization
        checksum: Optional SHA256 checksum of model artifact for integrity verification
    """

    model_name: str
    version: str
    created_at: datetime
    training_data: str
    hyperparameters: dict[str, Any]
    metrics: dict[str, float]
    tags: list[str]
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary for JSON serialization."""
        result = {
            "model_name": self.model_name,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "training_data": self.training_data,
            "hyperparameters": self.hyperparameters,
            "metrics": self.metrics,
            "tags": self.tags,
        }
        if self.checksum is not None:
            result["checksum"] = self.checksum
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelMetadata:
        """Create metadata from dictionary."""
        return cls(
            model_name=data["model_name"],
            version=data["version"],
            created_at=datetime.fromisoformat(data["created_at"]),
            training_data=data["training_data"],
            hyperparameters=data["hyperparameters"],
            metrics=data["metrics"],
            tags=data["tags"],
            checksum=data.get("checksum"),
        )


@dataclass(frozen=True)
class ModelVersion:
    """Model version information.

    Attributes:
        model_name: Name of the model
        version: Semantic version string
        created_at: UTC timestamp
        metadata_path: Path to metadata file
        model_path: Path to model artifact
        checksum: SHA256 checksum of model artifact
    """

    model_name: str
    version: str
    created_at: datetime
    metadata_path: str
    model_path: str
    checksum: str | None = None


class StorageBackend(ABC):
    """Abstract base class for model storage backends."""

    @abstractmethod
    def save_model(
        self,
        model: Any,
        metadata: ModelMetadata,
    ) -> ModelVersion:
        """Save a model with metadata.

        Args:
            model: Model object to serialize
            metadata: Model metadata

        Returns:
            ModelVersion with paths/info
        """
        pass

    @abstractmethod
    def load_model(self, model_name: str, version: str) -> tuple[Any, ModelMetadata]:
        """Load a model and its metadata.

        Args:
            model_name: Name of the model
            version: Version string

        Returns:
            Tuple of (model, metadata)
        """
        pass

    @abstractmethod
    def list_versions(self, model_name: str) -> list[ModelVersion]:
        """List all versions of a model.

        Args:
            model_name: Name of the model

        Returns:
            List of model versions
        """
        pass

    @abstractmethod
    def delete_version(self, model_name: str, version: str) -> bool:
        """Delete a specific model version.

        Args:
            model_name: Name of the model
            version: Version string

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    def get_latest_version(self, model_name: str) -> ModelVersion | None:
        """Get the latest version of a model.

        Args:
            model_name: Name of the model

        Returns:
            Latest ModelVersion or None if no versions exist
        """
        pass

    @abstractmethod
    def set_latest_pointer(self, model_name: str, version: str) -> bool:
        """Update the "latest" pointer to a specific version.

        Args:
            model_name: Name of the model
            version: Version string to point to

        Returns:
            True if successful, False if version not found
        """
        pass


class FilesystemBackend(StorageBackend):
    """Filesystem-based model storage backend.

    Storage structure:
        {base_path}/{model_name}/{version}/
            model.pkl       - Serialized model
            metadata.json   - Model metadata
        {base_path}/{model_name}/latest.json - Points to latest version
    """

    def __init__(self, base_path: str | Path = "models") -> None:
        """Initialize filesystem backend.

        Args:
            base_path: Base directory for model storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_model_dir(self, model_name: str, version: str) -> Path:
        """Get directory path for a model version."""
        return self.base_path / model_name / version

    def _get_latest_file(self, model_name: str) -> Path:
        """Get path to latest pointer file."""
        return self.base_path / model_name / "latest.json"

    def save_model(
        self,
        model: Any,
        metadata: ModelMetadata,
    ) -> ModelVersion:
        """Save a model with metadata to filesystem."""
        model_dir = self._get_model_dir(metadata.model_name, metadata.version)
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save model artifact
        model_path = model_dir / "model.pkl"
        joblib.dump(model, model_path)

        # Save metadata
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        return ModelVersion(
            model_name=metadata.model_name,
            version=metadata.version,
            created_at=metadata.created_at,
            metadata_path=str(metadata_path),
            model_path=str(model_path),
        )

    def load_model(self, model_name: str, version: str) -> tuple[Any, ModelMetadata]:
        """Load a model and its metadata from filesystem."""
        model_dir = self._get_model_dir(model_name, version)

        if not model_dir.exists():
            raise FileNotFoundError(f"Model version not found: {model_name}@{version}")

        # Load metadata
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path) as f:
            metadata = ModelMetadata.from_dict(json.load(f))

        # Load model
        model_path = model_dir / "model.pkl"
        model = joblib.load(model_path)

        return model, metadata

    def list_versions(self, model_name: str) -> list[ModelVersion]:
        """List all versions of a model."""
        model_dir = self.base_path / model_name
        if not model_dir.exists():
            return []

        versions = []
        for version_dir in model_dir.iterdir():
            if version_dir.is_dir() and version_dir.name != "__pycache__":
                metadata_path = version_dir / "metadata.json"
                model_path = version_dir / "model.pkl"

                if metadata_path.exists() and model_path.exists():
                    with open(metadata_path) as f:
                        metadata_dict = json.load(f)
                    versions.append(
                        ModelVersion(
                            model_name=model_name,
                            version=version_dir.name,
                            created_at=datetime.fromisoformat(
                                metadata_dict["created_at"]
                            ),
                            metadata_path=str(metadata_path),
                            model_path=str(model_path),
                        )
                    )

        # Sort by creation time (newest first)
        versions.sort(key=lambda v: v.created_at, reverse=True)
        return versions

    def delete_version(self, model_name: str, version: str) -> bool:
        """Delete a specific model version."""
        model_dir = self._get_model_dir(model_name, version)

        if not model_dir.exists():
            return False

        shutil.rmtree(model_dir)
        return True

    def get_latest_version(self, model_name: str) -> ModelVersion | None:
        """Get the latest version of a model."""
        latest_file = self._get_latest_file(model_name)

        if latest_file.exists():
            with open(latest_file) as f:
                latest_data = json.load(f)
            version = latest_data["version"]
        else:
            # No latest pointer, find most recent version
            versions = self.list_versions(model_name)
            if not versions:
                return None
            version = versions[0].version

        return self._get_version_info(model_name, version)

    def _get_version_info(self, model_name: str, version: str) -> ModelVersion | None:
        """Get version info for a specific version."""
        model_dir = self._get_model_dir(model_name, version)

        if not model_dir.exists():
            return None

        metadata_path = model_dir / "metadata.json"
        model_path = model_dir / "model.pkl"

        if not metadata_path.exists() or not model_path.exists():
            return None

        with open(metadata_path) as f:
            metadata_dict = json.load(f)

        return ModelVersion(
            model_name=model_name,
            version=version,
            created_at=datetime.fromisoformat(metadata_dict["created_at"]),
            metadata_path=str(metadata_path),
            model_path=str(model_path),
        )

    def set_latest_pointer(self, model_name: str, version: str) -> bool:
        """Update the "latest" pointer to a specific version."""
        # Verify version exists
        version_info = self._get_version_info(model_name, version)
        if version_info is None:
            return False

        # Update latest pointer
        latest_file = self._get_latest_file(model_name)
        latest_file.parent.mkdir(parents=True, exist_ok=True)

        with open(latest_file, "w") as f:
            json.dump(
                {
                    "version": version,
                    "updated_at": datetime.utcnow().isoformat(),
                    "model_name": model_name,
                },
                f,
                indent=2,
            )

        return True

    def get_model_path(self, model_name: str, version: str) -> Path:
        """Get filesystem path to model artifact.

        Args:
            model_name: Name of the model
            version: Version string

        Returns:
            Path to model.pkl file
        """
        return self._get_model_dir(model_name, version) / "model.pkl"


class S3Backend(StorageBackend):
    """AWS S3-based model storage backend (interface for future implementation).

    Storage structure:
        s3://{bucket}/{prefix}/{model_name}/{version}/
            model.pkl       - Serialized model
            metadata.json   - Model metadata
        s3://{bucket}/{prefix}/{model_name}/latest.json - Points to latest version
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "models",
        region: str = "us-east-1",
    ) -> None:
        """Initialize S3 backend (interface only).

        Args:
            bucket: S3 bucket name
            prefix: Key prefix for models
            region: AWS region

        Raises:
            NotImplementedError: This is an interface for future implementation
        """
        self.bucket = bucket
        self.prefix = prefix
        self.region = region
        self._initialized = False

    def _check_initialized(self) -> None:
        """Check if backend is properly initialized."""
        if not self._initialized:
            raise NotImplementedError(
                "S3Backend is an interface for future implementation. "
                "Use FilesystemBackend for now."
            )

    def save_model(
        self,
        model: Any,
        metadata: ModelMetadata,
    ) -> ModelVersion:
        """Save a model to S3 (not implemented)."""
        self._check_initialized()
        raise NotImplementedError("S3Backend.save_model not implemented")

    def load_model(self, model_name: str, version: str) -> tuple[Any, ModelMetadata]:
        """Load a model from S3 (not implemented)."""
        self._check_initialized()
        raise NotImplementedError("S3Backend.load_model not implemented")

    def list_versions(self, model_name: str) -> list[ModelVersion]:
        """List model versions in S3 (not implemented)."""
        self._check_initialized()
        raise NotImplementedError("S3Backend.list_versions not implemented")

    def delete_version(self, model_name: str, version: str) -> bool:
        """Delete a model version from S3 (not implemented)."""
        self._check_initialized()
        raise NotImplementedError("S3Backend.delete_version not implemented")

    def get_latest_version(self, model_name: str) -> ModelVersion | None:
        """Get latest version from S3 (not implemented)."""
        self._check_initialized()
        raise NotImplementedError("S3Backend.get_latest_version not implemented")

    def set_latest_pointer(self, model_name: str, version: str) -> bool:
        """Update latest pointer in S3 (not implemented)."""
        self._check_initialized()
        raise NotImplementedError("S3Backend.set_latest_pointer not implemented")
