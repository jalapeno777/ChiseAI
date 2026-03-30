"""Model storage backends for ChiseAI Model Registry.

Provides pluggable storage backends for model artifacts:
- FilesystemBackend: Local filesystem storage (primary)
- S3Backend: AWS S3 storage (interface for future implementation)
"""

from __future__ import annotations

import json
import shutil
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
        import joblib

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
        import joblib

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
                    "updated_at": datetime.now(UTC).isoformat(),
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


class NullMetricsCollector:
    """No-op metrics collector for model operations.

    Provides a no-op implementation of metrics collection that can be used
    when metrics are not needed or when a placeholder is required.
    """

    def record_save(self, model_name: str, version: str, duration_ms: float) -> None:
        """Record a model save operation (no-op)."""
        pass

    def record_load(self, model_name: str, version: str, duration_ms: float) -> None:
        """Record a model load operation (no-op)."""
        pass

    def record_cache_hit(self, model_name: str, version: str) -> None:
        """Record a cache hit (no-op)."""
        pass

    def record_cache_miss(self, model_name: str, version: str) -> None:
        """Record a cache miss (no-op)."""
        pass


@dataclass
class ModelCacheEntry:
    """Entry in the model cache.

    Attributes:
        model: The cached model object
        metadata: Model metadata
        loaded_at: UTC timestamp when the model was loaded
        last_accessed: UTC timestamp of last access
        access_count: Number of times the model has been accessed
    """

    model: Any
    metadata: ModelMetadata
    loaded_at: datetime
    last_accessed: datetime
    access_count: int = 0

    def touch(self) -> None:
        """Update access statistics."""
        self.last_accessed = datetime.now(UTC)
        self.access_count += 1


class ModelCache:
    """In-memory cache for loaded models with TTL and LRU eviction.

    Provides a thread-safe cache for model objects with support for:
    - TTL-based expiration
    - LRU eviction when cache is full
    - Statistics tracking
    """

    def __init__(self, max_size: int = 10, ttl_seconds: float | None = None) -> None:
        """Initialize the model cache.

        Args:
            max_size: Maximum number of models to cache
            ttl_seconds: Time-to-live for cache entries in seconds.
                        None means no expiration.
        """
        self._cache: dict[tuple[str, str], ModelCacheEntry] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()

    def get(self, model_name: str, version: str) -> tuple[Any, ModelMetadata] | None:
        """Get a model from the cache.

        Args:
            model_name: Name of the model
            version: Version of the model

        Returns:
            Tuple of (model, metadata) if found and not expired, None otherwise
        """
        with self._lock:
            key = (model_name, version)
            entry = self._cache.get(key)

            if entry is None:
                return None

            # Check TTL expiration
            if self._ttl_seconds is not None:
                age = (datetime.now(UTC) - entry.loaded_at).total_seconds()
                if age > self._ttl_seconds:
                    del self._cache[key]
                    return None

            # Update access statistics
            entry.touch()
            return entry.model, entry.metadata

    def put(
        self,
        model_name: str,
        version: str,
        model: Any,
        metadata: ModelMetadata,
    ) -> None:
        """Put a model into the cache.

        Args:
            model_name: Name of the model
            version: Version of the model
            model: The model object to cache
            metadata: Model metadata
        """
        with self._lock:
            key = (model_name, version)

            # Evict if cache is full and this key is not already in cache
            if key not in self._cache and len(self._cache) >= self._max_size:
                self._evict_lru()

            now = datetime.now(UTC)
            self._cache[key] = ModelCacheEntry(
                model=model,
                metadata=metadata,
                loaded_at=now,
                last_accessed=now,
                access_count=0,
            )

    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if not self._cache:
            return
        # Find entry with oldest last_accessed
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        del self._cache[lru_key]

    def invalidate(self, model_name: str, version: str) -> bool:
        """Invalidate a cache entry.

        Args:
            model_name: Name of the model
            version: Version of the model

        Returns:
            True if entry was removed, False if not found
        """
        with self._lock:
            key = (model_name, version)
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache statistics including size, max_size, and entry details
        """
        with self._lock:
            entries = []
            for (model_name, version), entry in self._cache.items():
                entries.append(
                    {
                        "model_name": model_name,
                        "version": version,
                        "loaded_at": entry.loaded_at.isoformat(),
                        "last_accessed": entry.last_accessed.isoformat(),
                        "access_count": entry.access_count,
                    }
                )
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "entries": entries,
            }


class S3Backend(StorageBackend):
    """AWS S3-based model storage backend (interface for future implementation).

    Storage structure:
    s3://{bucket}/{prefix}/{model_name}/{version}/
    model.pkl - Serialized model
    metadata.json - Model metadata
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
