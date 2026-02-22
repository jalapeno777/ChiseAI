"""Model Registry for ChiseAI.

Provides versioning, storage, and retrieval of ML models with metadata
and rollback support. Uses semantic versioning (MAJOR.MINOR.PATCH).

Example:
    registry = ModelRegistry()

    # Register a new model version
    version = registry.register_model(
        model=my_model,
        metadata=ModelMetadata(
            model_name="price_predictor",
            version="1.0.0",
            created_at=datetime.utcnow(),
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001, "epochs": 100},
            metrics={"accuracy": 0.95, "f1": 0.93},
            tags=["production", "v1"],
        )
    )

    # Get latest model
    model, metadata = registry.get_latest("price_predictor")

    # Rollback to previous version
    registry.rollback("price_predictor", "0.9.0")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ml.models.model_storage import (
    FilesystemBackend,
    ModelMetadata,
    ModelVersion,
    S3Backend,
    StorageBackend,
)


@dataclass(frozen=True)
class SemanticVersion:
    """Semantic version (MAJOR.MINOR.PATCH).

    Attributes:
        major: Major version (breaking changes: architecture, feature set)
        minor: Minor version (new features, backward compatible)
        patch: Patch version (bug fixes, backward compatible)
    """

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        """Return version string."""
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def from_string(cls, version_str: str) -> SemanticVersion:
        """Parse version from string.

        Args:
            version_str: Version string like "1.0.0"

        Returns:
            SemanticVersion instance

        Raises:
            ValueError: If version string is invalid
        """
        pattern = r"^(\d+)\.(\d+)\.(\d+)$"
        match = re.match(pattern, version_str)
        if not match:
            raise ValueError(
                f"Invalid version string: {version_str}. "
                "Expected format: MAJOR.MINOR.PATCH (e.g., 1.0.0)"
            )
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def is_compatible_with(self, other: SemanticVersion) -> bool:
        """Check if this version is backward compatible with another.

        Compatibility rules:
        - Same major version = compatible
        - Different major version = breaking change

        Args:
            other: Version to check compatibility with

        Returns:
            True if compatible, False otherwise
        """
        return self.major == other.major

    def is_newer_than(self, other: SemanticVersion) -> bool:
        """Check if this version is newer than another.

        Args:
            other: Version to compare against

        Returns:
            True if this version is newer
        """
        if self.major != other.major:
            return self.major > other.major
        if self.minor != other.minor:
            return self.minor > other.minor
        return self.patch > other.patch

    def bump_major(self) -> SemanticVersion:
        """Return new version with bumped major number."""
        return SemanticVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> SemanticVersion:
        """Return new version with bumped minor number."""
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> SemanticVersion:
        """Return new version with bumped patch number."""
        return SemanticVersion(self.major, self.minor, self.patch + 1)


class ModelRegistry:
    """Model registry for versioning, storage, and retrieval.

    Provides semantic versioning, metadata tracking, and rollback support.
    Models are immutable - once registered, versions cannot be modified.

    Attributes:
        backend: Storage backend (FilesystemBackend or S3Backend)
    """

    def __init__(self, backend: StorageBackend | None = None) -> None:
        """Initialize model registry.

        Args:
            backend: Storage backend (defaults to FilesystemBackend)
        """
        self.backend = backend or FilesystemBackend()

    def register_model(
        self,
        model: Any,
        metadata: ModelMetadata,
    ) -> ModelVersion:
        """Register a new model version.

        Validates semantic version format and saves model with metadata.
        Automatically updates "latest" pointer to this version.

        Args:
            model: Model object to register
            metadata: Model metadata including version

        Returns:
            ModelVersion with storage information

        Raises:
            ValueError: If version format is invalid
            RuntimeError: If version already exists (immutable)
        """
        # Validate semantic version
        try:
            version = SemanticVersion.from_string(metadata.version)
        except ValueError as e:
            raise ValueError(f"Invalid version: {e}") from e

        # Check if version already exists (immutable registry)
        existing_versions = self.backend.list_versions(metadata.model_name)
        if any(v.version == str(version) for v in existing_versions):
            raise RuntimeError(
                f"Version {version} already exists for model {metadata.model_name}. "
                "Model versions are immutable."
            )

        # Save model and metadata
        model_version = self.backend.save_model(model, metadata)

        # Update latest pointer
        self.backend.set_latest_pointer(metadata.model_name, str(version))

        return model_version

    def get_model(self, model_name: str, version: str) -> tuple[Any, ModelMetadata]:
        """Get a model by version.

        Args:
            model_name: Name of the model
            version: Version string (e.g., "1.0.0") or "latest"

        Returns:
            Tuple of (model, metadata)

        Raises:
            FileNotFoundError: If model or version not found
            ValueError: If version format is invalid
        """
        if version == "latest":
            return self.get_latest(model_name)

        # Validate version format
        SemanticVersion.from_string(version)

        result: tuple[Any, ModelMetadata] = self.backend.load_model(model_name, version)
        return result

    def get_latest(self, model_name: str) -> tuple[Any, ModelMetadata]:
        """Get the latest version of a model.

        Args:
            model_name: Name of the model

        Returns:
            Tuple of (model, metadata)

        Raises:
            FileNotFoundError: If no versions exist for the model
        """
        latest = self.backend.get_latest_version(model_name)
        if latest is None:
            raise FileNotFoundError(f"No versions found for model: {model_name}")

        result: tuple[Any, ModelMetadata] = self.backend.load_model(
            model_name, latest.version
        )
        return result

    def rollback(self, model_name: str, target_version: str) -> bool:
        """Rollback to a previous model version.

        This operation updates the "latest" pointer to the target version,
        effectively rolling back to that version. The actual model files
        are not modified (immutable).

        Rollback completes in <5 seconds as it only updates a pointer.

        Args:
            model_name: Name of the model
            target_version: Version to rollback to

        Returns:
            True if rollback successful

        Raises:
            FileNotFoundError: If target version doesn't exist
            ValueError: If target version format is invalid
        """
        # Validate version format
        SemanticVersion.from_string(target_version)

        # Verify target version exists
        try:
            self.backend.load_model(model_name, target_version)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Cannot rollback: version {target_version} "
                f"not found for model {model_name}"
            ) from e

        # Update latest pointer (fast operation)
        result: bool = self.backend.set_latest_pointer(model_name, target_version)
        return result

    def list_versions(self, model_name: str) -> list[ModelVersion]:
        """List all versions of a model.

        Returns versions sorted by creation time (newest first).

        Args:
            model_name: Name of the model

        Returns:
            List of ModelVersion objects
        """
        versions: list[ModelVersion] = self.backend.list_versions(model_name)
        return versions

    def delete_version(self, model_name: str, version: str) -> bool:
        """Delete a specific model version.

        Warning: This permanently deletes the model files. Use with caution.
        Consider using rollback instead for reverting to previous versions.

        Args:
            model_name: Name of the model
            version: Version string to delete

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If version format is invalid
            RuntimeError: If trying to delete the current "latest" version
        """
        # Validate version format
        SemanticVersion.from_string(version)

        # Check if this is the latest version
        latest = self.backend.get_latest_version(model_name)
        if latest and latest.version == version:
            raise RuntimeError(
                f"Cannot delete version {version}: it is the current 'latest' version. "
                "Rollback to a different version first."
            )

        deleted: bool = self.backend.delete_version(model_name, version)
        return deleted

    def get_version_history(self, model_name: str) -> list[dict[str, Any]]:
        """Get detailed version history with metadata.

        Args:
            model_name: Name of the model

        Returns:
            List of version info dictionaries with metadata
        """
        versions = self.list_versions(model_name)
        history = []

        for version in versions:
            try:
                _, metadata = self.backend.load_model(model_name, version.version)
                history.append(
                    {
                        "version": version.version,
                        "created_at": version.created_at.isoformat(),
                        "model_name": version.model_name,
                        "metrics": metadata.metrics,
                        "tags": metadata.tags,
                        "training_data": metadata.training_data,
                    }
                )
            except FileNotFoundError:
                continue

        return history

    def compare_versions(
        self, model_name: str, version1: str, version2: str
    ) -> dict[str, Any]:
        """Compare two model versions.

        Args:
            model_name: Name of the model
            version1: First version to compare
            version2: Second version to compare

        Returns:
            Dictionary with comparison results
        """
        _, meta1 = self.get_model(model_name, version1)
        _, meta2 = self.get_model(model_name, version2)

        return {
            "version1": {
                "version": version1,
                "created_at": meta1.created_at.isoformat(),
                "metrics": meta1.metrics,
            },
            "version2": {
                "version": version2,
                "created_at": meta2.created_at.isoformat(),
                "metrics": meta2.metrics,
            },
            "metric_diffs": {
                key: meta2.metrics.get(key, 0) - meta1.metrics.get(key, 0)
                for key in set(meta1.metrics.keys()) | set(meta2.metrics.keys())
            },
        }

    def create_new_version(
        self,
        model: Any,
        model_name: str,
        training_data: str,
        hyperparameters: dict[str, Any],
        metrics: dict[str, float],
        tags: list[str] | None = None,
        bump: str = "patch",
    ) -> ModelVersion:
        """Create and register a new model version with auto-incremented version.

        Automatically determines the next version number based on the bump type.

        Args:
            model: Model object to register
            model_name: Name of the model
            training_data: Reference to training dataset
            hyperparameters: Model hyperparameters
            metrics: Performance metrics
            tags: Optional tags for categorization
            bump: Version bump type - "major", "minor", or "patch" (default)

        Returns:
            ModelVersion with storage information

        Raises:
            ValueError: If bump type is invalid
        """
        if bump not in ("major", "minor", "patch"):
            raise ValueError(
                f"Invalid bump type: {bump}. Use 'major', 'minor', or 'patch'"
            )

        # Get current latest version
        try:
            latest = self.backend.get_latest_version(model_name)
            if latest:
                current = SemanticVersion.from_string(latest.version)
                if bump == "major":
                    new_version = current.bump_major()
                elif bump == "minor":
                    new_version = current.bump_minor()
                else:
                    new_version = current.bump_patch()
            else:
                new_version = SemanticVersion(0, 1, 0)
        except FileNotFoundError:
            # No existing versions
            new_version = SemanticVersion(0, 1, 0)

        metadata = ModelMetadata(
            model_name=model_name,
            version=str(new_version),
            created_at=datetime.utcnow(),
            training_data=training_data,
            hyperparameters=hyperparameters,
            metrics=metrics,
            tags=tags or [],
        )

        return self.register_model(model, metadata)


class ModelRegistryFactory:
    """Factory for creating model registries with different backends."""

    @staticmethod
    def create_filesystem_registry(base_path: str = "models") -> ModelRegistry:
        """Create a model registry with filesystem backend.

        Args:
            base_path: Base directory for model storage

        Returns:
            ModelRegistry instance
        """
        backend = FilesystemBackend(base_path)
        return ModelRegistry(backend)

    @staticmethod
    def create_s3_registry(
        bucket: str,
        prefix: str = "models",
        region: str = "us-east-1",
    ) -> ModelRegistry:
        """Create a model registry with S3 backend.

        Note: S3Backend is currently an interface for future implementation.
        Use create_filesystem_registry for production use.

        Args:
            bucket: S3 bucket name
            prefix: Key prefix for models
            region: AWS region

        Returns:
            ModelRegistry instance (with S3 backend interface)

        Raises:
            NotImplementedError: When attempting to use S3 operations
        """
        backend = S3Backend(bucket, prefix, region)
        return ModelRegistry(backend)
