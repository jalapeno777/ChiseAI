"""Tests for Model Registry.

Comprehensive test suite covering:
- Semantic versioning
- Model storage with metadata
- Model retrieval by version and "latest" tag
- Rollback support (<5 minute requirement)
- Filesystem and S3 backend interfaces
- Model metadata tracking
"""

from __future__ import annotations

# Add src to path for imports
import sys

sys.path.insert(0, "src")

import json
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ml.models import (
    FilesystemBackend,
    ModelMetadata,
    ModelRegistry,
    ModelRegistryFactory,
    S3Backend,
    SemanticVersion,
)


class TestSemanticVersion:
    """Tests for semantic versioning."""

    def test_from_string_valid(self) -> None:
        """Test parsing valid version strings."""
        v = SemanticVersion.from_string("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_from_string_invalid(self) -> None:
        """Test parsing invalid version strings."""
        with pytest.raises(ValueError, match="Invalid version string"):
            SemanticVersion.from_string("1.2")
        with pytest.raises(ValueError, match="Invalid version string"):
            SemanticVersion.from_string("1.2.3.4")
        with pytest.raises(ValueError, match="Invalid version string"):
            SemanticVersion.from_string("abc")
        with pytest.raises(ValueError, match="Invalid version string"):
            SemanticVersion.from_string("1.2.a")

    def test_to_string(self) -> None:
        """Test converting version to string."""
        v = SemanticVersion(1, 2, 3)
        assert str(v) == "1.2.3"

    def test_is_compatible_with(self) -> None:
        """Test version compatibility checking."""
        v1 = SemanticVersion(1, 0, 0)
        v2 = SemanticVersion(1, 5, 3)
        v3 = SemanticVersion(2, 0, 0)

        assert v1.is_compatible_with(v2) is True
        assert v2.is_compatible_with(v1) is True
        assert v1.is_compatible_with(v3) is False
        assert v3.is_compatible_with(v1) is False

    def test_is_newer_than(self) -> None:
        """Test version comparison."""
        v1 = SemanticVersion(1, 0, 0)
        v2 = SemanticVersion(1, 0, 1)
        v3 = SemanticVersion(1, 1, 0)
        v4 = SemanticVersion(2, 0, 0)

        assert v2.is_newer_than(v1) is True
        assert v3.is_newer_than(v2) is True
        assert v4.is_newer_than(v3) is True
        assert v1.is_newer_than(v2) is False
        assert v1.is_newer_than(v1) is False

    def test_bump_major(self) -> None:
        """Test bumping major version."""
        v = SemanticVersion(1, 2, 3)
        new_v = v.bump_major()
        assert new_v.major == 2
        assert new_v.minor == 0
        assert new_v.patch == 0

    def test_bump_minor(self) -> None:
        """Test bumping minor version."""
        v = SemanticVersion(1, 2, 3)
        new_v = v.bump_minor()
        assert new_v.major == 1
        assert new_v.minor == 3
        assert new_v.patch == 0

    def test_bump_patch(self) -> None:
        """Test bumping patch version."""
        v = SemanticVersion(1, 2, 3)
        new_v = v.bump_patch()
        assert new_v.major == 1
        assert new_v.minor == 2
        assert new_v.patch == 4


class TestModelMetadata:
    """Tests for ModelMetadata dataclass."""

    def test_to_dict(self) -> None:
        """Test converting metadata to dictionary."""
        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001, "epochs": 100},
            metrics={"accuracy": 0.95, "f1": 0.93},
            tags=["production"],
        )

        d = metadata.to_dict()
        assert d["model_name"] == "test_model"
        assert d["version"] == "1.0.0"
        assert d["created_at"] == "2024-01-01T12:00:00"
        assert d["training_data"] == "dataset_v1"
        assert d["hyperparameters"]["lr"] == 0.001
        assert d["metrics"]["accuracy"] == 0.95
        assert d["tags"] == ["production"]

    def test_from_dict(self) -> None:
        """Test creating metadata from dictionary."""
        data = {
            "model_name": "test_model",
            "version": "1.0.0",
            "created_at": "2024-01-01T12:00:00",
            "training_data": "dataset_v1",
            "hyperparameters": {"lr": 0.001},
            "metrics": {"accuracy": 0.95},
            "tags": ["production"],
        }

        metadata = ModelMetadata.from_dict(data)
        assert metadata.model_name == "test_model"
        assert metadata.version == "1.0.0"
        assert metadata.created_at == datetime(2024, 1, 1, 12, 0, 0)
        assert metadata.training_data == "dataset_v1"


class TestFilesystemBackend:
    """Tests for FilesystemBackend storage."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def backend(self, temp_dir):
        """Create a FilesystemBackend instance."""
        return FilesystemBackend(temp_dir)

    @pytest.fixture
    def sample_model(self):
        """Create a sample model for testing."""
        return {"weights": [1.0, 2.0, 3.0], "bias": 0.5}

    @pytest.fixture
    def sample_metadata(self):
        """Create sample metadata for testing."""
        return ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001},
            metrics={"accuracy": 0.95},
            tags=["test"],
        )

    def test_save_model(self, backend, sample_model, sample_metadata) -> None:
        """Test saving a model."""
        version = backend.save_model(sample_model, sample_metadata)

        assert version.model_name == "test_model"
        assert version.version == "1.0.0"
        assert Path(version.model_path).exists()
        assert Path(version.metadata_path).exists()

    def test_load_model(self, backend, sample_model, sample_metadata) -> None:
        """Test loading a model."""
        backend.save_model(sample_model, sample_metadata)

        loaded_model, loaded_metadata = backend.load_model("test_model", "1.0.0")

        assert loaded_model == sample_model
        assert loaded_metadata.model_name == sample_metadata.model_name
        assert loaded_metadata.version == sample_metadata.version

    def test_load_model_not_found(self, backend) -> None:
        """Test loading a non-existent model."""
        with pytest.raises(FileNotFoundError):
            backend.load_model("nonexistent", "1.0.0")

    def test_list_versions(self, backend, sample_model) -> None:
        """Test listing model versions."""
        # Create multiple versions
        for version in ["1.0.0", "1.0.1", "1.1.0"]:
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={},
                tags=[],
            )
            backend.save_model(sample_model, metadata)
            time.sleep(0.01)  # Ensure different timestamps

        versions = backend.list_versions("test_model")

        assert len(versions) == 3
        # Should be sorted by creation time (newest first)
        assert versions[0].version == "1.1.0"

    def test_list_versions_empty(self, backend) -> None:
        """Test listing versions for non-existent model."""
        versions = backend.list_versions("nonexistent")
        assert versions == []

    def test_delete_version(self, backend, sample_model, sample_metadata) -> None:
        """Test deleting a model version."""
        backend.save_model(sample_model, sample_metadata)

        result = backend.delete_version("test_model", "1.0.0")
        assert result is True

        with pytest.raises(FileNotFoundError):
            backend.load_model("test_model", "1.0.0")

    def test_delete_version_not_found(self, backend) -> None:
        """Test deleting a non-existent version."""
        result = backend.delete_version("nonexistent", "1.0.0")
        assert result is False

    def test_get_latest_version(self, backend, sample_model) -> None:
        """Test getting latest version."""
        # Create versions
        for version in ["1.0.0", "1.0.1"]:
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={},
                tags=[],
            )
            backend.save_model(sample_model, metadata)
            backend.set_latest_pointer("test_model", version)
            time.sleep(0.01)

        latest = backend.get_latest_version("test_model")
        assert latest is not None
        assert latest.version == "1.0.1"

    def test_get_latest_version_no_pointer(self, backend, sample_model) -> None:
        """Test getting latest without explicit pointer."""
        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )
        backend.save_model(sample_model, metadata)

        latest = backend.get_latest_version("test_model")
        assert latest is not None
        assert latest.version == "1.0.0"

    def test_get_latest_version_empty(self, backend) -> None:
        """Test getting latest for non-existent model."""
        latest = backend.get_latest_version("nonexistent")
        assert latest is None

    def test_set_latest_pointer(self, backend, sample_model) -> None:
        """Test setting latest pointer."""
        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )
        backend.save_model(sample_model, metadata)

        result = backend.set_latest_pointer("test_model", "1.0.0")
        assert result is True

        # Verify pointer file exists
        latest_file = Path(backend.base_path) / "test_model" / "latest.json"
        assert latest_file.exists()

        with open(latest_file) as f:
            data = json.load(f)
            assert data["version"] == "1.0.0"
            assert data["model_name"] == "test_model"

    def test_set_latest_pointer_invalid_version(self, backend) -> None:
        """Test setting pointer to non-existent version."""
        result = backend.set_latest_pointer("test_model", "9.9.9")
        assert result is False


class TestModelRegistry:
    """Tests for ModelRegistry."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def registry(self, temp_dir):
        """Create a ModelRegistry instance."""
        backend = FilesystemBackend(temp_dir)
        return ModelRegistry(backend)

    @pytest.fixture
    def sample_model(self):
        """Create a sample model."""
        return {"type": "linear", "weights": [1.0, 2.0]}

    @pytest.fixture
    def sample_metadata(self):
        """Create sample metadata."""
        return ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001, "epochs": 100},
            metrics={"accuracy": 0.95, "precision": 0.93, "recall": 0.94, "f1": 0.935},
            tags=["production", "v1"],
        )

    def test_register_model(self, registry, sample_model, sample_metadata) -> None:
        """Test registering a model."""
        version = registry.register_model(sample_model, sample_metadata)

        assert version.model_name == "test_model"
        assert version.version == "1.0.0"

    def test_register_model_invalid_version(self, registry, sample_model) -> None:
        """Test registering with invalid version."""
        metadata = ModelMetadata(
            model_name="test_model",
            version="invalid",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )

        with pytest.raises(ValueError, match="Invalid version"):
            registry.register_model(sample_model, metadata)

    def test_register_model_duplicate_version(
        self, registry, sample_model, sample_metadata
    ) -> None:
        """Test registering duplicate version (immutable)."""
        registry.register_model(sample_model, sample_metadata)

        with pytest.raises(RuntimeError, match="already exists"):
            registry.register_model(sample_model, sample_metadata)

    def test_get_model(self, registry, sample_model, sample_metadata) -> None:
        """Test getting a model by version."""
        registry.register_model(sample_model, sample_metadata)

        model, metadata = registry.get_model("test_model", "1.0.0")

        assert model == sample_model
        assert metadata.model_name == "test_model"
        assert metadata.version == "1.0.0"

    def test_get_model_latest(self, registry, sample_model) -> None:
        """Test getting latest model."""
        # Register first version
        metadata1 = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )
        registry.register_model({"version": 1}, metadata1)

        # Register second version
        metadata2 = ModelMetadata(
            model_name="test_model",
            version="1.0.1",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )
        registry.register_model({"version": 2}, metadata2)

        # Get latest using "latest" keyword
        model, metadata = registry.get_model("test_model", "latest")
        assert model == {"version": 2}

        # Get latest using get_latest method
        model, metadata = registry.get_latest("test_model")
        assert model == {"version": 2}

    def test_get_model_not_found(self, registry) -> None:
        """Test getting non-existent model."""
        with pytest.raises(FileNotFoundError):
            registry.get_model("nonexistent", "1.0.0")

    def test_get_latest_not_found(self, registry) -> None:
        """Test getting latest for non-existent model."""
        with pytest.raises(FileNotFoundError, match="No versions found"):
            registry.get_latest("nonexistent")

    def test_rollback(self, registry, sample_model) -> None:
        """Test rollback to previous version."""
        # Register two versions
        for version, data in [("1.0.0", {"v": 1}), ("1.0.1", {"v": 2})]:
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={},
                tags=[],
            )
            registry.register_model(data, metadata)

        # Verify latest is 1.0.1
        model, _ = registry.get_latest("test_model")
        assert model == {"v": 2}

        # Rollback to 1.0.0
        result = registry.rollback("test_model", "1.0.0")
        assert result is True

        # Verify latest is now 1.0.0
        model, _ = registry.get_latest("test_model")
        assert model == {"v": 1}

    def test_rollback_performance(self, registry, sample_model) -> None:
        """Test rollback completes within 5 minutes."""
        # Setup: register multiple versions
        for version, data in [
            ("1.0.0", {"v": 1}),
            ("1.0.1", {"v": 2}),
            ("1.0.2", {"v": 3}),
        ]:
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={},
                tags=[],
            )
            registry.register_model(data, metadata)

        # Measure rollback time
        start_time = time.time()
        registry.rollback("test_model", "1.0.0")
        elapsed = time.time() - start_time

        # Should complete in well under 5 minutes (300 seconds)
        # Expecting sub-second for pointer update
        assert elapsed < 5.0, f"Rollback took {elapsed}s, expected <5s"

    def test_rollback_invalid_version(self, registry) -> None:
        """Test rollback to non-existent version."""
        with pytest.raises(FileNotFoundError, match="Cannot rollback"):
            registry.rollback("test_model", "9.9.9")

    def test_rollback_invalid_version_format(self, registry) -> None:
        """Test rollback with invalid version format."""
        with pytest.raises(ValueError):
            registry.rollback("test_model", "invalid")

    def test_list_versions(self, registry, sample_model) -> None:
        """Test listing model versions."""
        for version in ["1.0.0", "1.0.1", "1.1.0"]:
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={},
                tags=[],
            )
            registry.register_model(sample_model, metadata)
            time.sleep(0.01)

        versions = registry.list_versions("test_model")

        assert len(versions) == 3
        version_strings = [v.version for v in versions]
        assert "1.0.0" in version_strings
        assert "1.0.1" in version_strings
        assert "1.1.0" in version_strings

    def test_delete_version(self, registry, sample_model) -> None:
        """Test deleting a model version."""
        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )
        registry.register_model(sample_model, metadata)

        # Register another version to avoid deleting "latest"
        metadata2 = ModelMetadata(
            model_name="test_model",
            version="1.0.1",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )
        registry.register_model(sample_model, metadata2)

        result = registry.delete_version("test_model", "1.0.0")
        assert result is True

        versions = registry.list_versions("test_model")
        assert len(versions) == 1

    def test_delete_latest_version_fails(self, registry, sample_model) -> None:
        """Test that deleting the latest version fails."""
        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )
        registry.register_model(sample_model, metadata)

        with pytest.raises(RuntimeError, match="current 'latest' version"):
            registry.delete_version("test_model", "1.0.0")

    def test_get_version_history(self, registry, sample_model) -> None:
        """Test getting version history."""
        for version, accuracy in [("1.0.0", 0.90), ("1.0.1", 0.95)]:
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={"accuracy": accuracy},
                tags=["v1"],
            )
            registry.register_model(sample_model, metadata)

        history = registry.get_version_history("test_model")

        assert len(history) == 2
        assert all("metrics" in h for h in history)
        assert all("tags" in h for h in history)

    def test_compare_versions(self, registry, sample_model) -> None:
        """Test comparing two model versions."""
        for version, accuracy in [("1.0.0", 0.90), ("1.0.1", 0.95)]:
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={"accuracy": accuracy, "f1": accuracy - 0.02},
                tags=[],
            )
            registry.register_model(sample_model, metadata)

        comparison = registry.compare_versions("test_model", "1.0.0", "1.0.1")

        assert "version1" in comparison
        assert "version2" in comparison
        assert "metric_diffs" in comparison
        assert abs(comparison["metric_diffs"]["accuracy"] - 0.05) < 1e-9

    def test_create_new_version(self, registry, sample_model) -> None:
        """Test creating new version with auto-increment."""
        # First version
        version = registry.create_new_version(
            model=sample_model,
            model_name="test_model",
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001},
            metrics={"accuracy": 0.90},
            bump="minor",
        )
        assert version.version == "0.1.0"

        # Patch bump
        version = registry.create_new_version(
            model=sample_model,
            model_name="test_model",
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001},
            metrics={"accuracy": 0.91},
            bump="patch",
        )
        assert version.version == "0.1.1"

        # Minor bump
        version = registry.create_new_version(
            model=sample_model,
            model_name="test_model",
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001},
            metrics={"accuracy": 0.92},
            bump="minor",
        )
        assert version.version == "0.2.0"

        # Major bump
        version = registry.create_new_version(
            model=sample_model,
            model_name="test_model",
            training_data="dataset_v1",
            hyperparameters={"lr": 0.001},
            metrics={"accuracy": 0.93},
            bump="major",
        )
        assert version.version == "1.0.0"

    def test_create_new_version_invalid_bump(self, registry, sample_model) -> None:
        """Test creating version with invalid bump type."""
        with pytest.raises(ValueError, match="Invalid bump type"):
            registry.create_new_version(
                model=sample_model,
                model_name="test_model",
                training_data="dataset_v1",
                hyperparameters={},
                metrics={},
                bump="invalid",
            )


class TestModelRegistryFactory:
    """Tests for ModelRegistryFactory."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)

    def test_create_filesystem_registry(self, temp_dir) -> None:
        """Test creating filesystem registry."""
        registry = ModelRegistryFactory.create_filesystem_registry(temp_dir)
        assert isinstance(registry, ModelRegistry)
        assert isinstance(registry.backend, FilesystemBackend)

    def test_create_s3_registry(self) -> None:
        """Test creating S3 registry (interface only)."""
        registry = ModelRegistryFactory.create_s3_registry(
            bucket="test-bucket",
            prefix="models",
            region="us-east-1",
        )
        assert isinstance(registry, ModelRegistry)
        assert isinstance(registry.backend, S3Backend)

        # Operations should raise NotImplementedError
        with pytest.raises(NotImplementedError):
            registry.backend.save_model(
                None,
                ModelMetadata(
                    model_name="test",
                    version="1.0.0",
                    created_at=datetime.now(UTC),
                    training_data="dataset",
                    hyperparameters={},
                    metrics={},
                    tags=[],
                ),
            )


class TestS3BackendInterface:
    """Tests for S3Backend interface."""

    def test_init(self) -> None:
        """Test S3Backend initialization."""
        backend = S3Backend(
            bucket="test-bucket",
            prefix="models",
            region="us-west-2",
        )
        assert backend.bucket == "test-bucket"
        assert backend.prefix == "models"
        assert backend.region == "us-west-2"

    def test_operations_not_implemented(self) -> None:
        """Test that all operations raise NotImplementedError."""
        backend = S3Backend("test-bucket")

        metadata = ModelMetadata(
            model_name="test",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset",
            hyperparameters={},
            metrics={},
            tags=[],
        )

        with pytest.raises(NotImplementedError):
            backend.save_model(None, metadata)

        with pytest.raises(NotImplementedError):
            backend.load_model("test", "1.0.0")

        with pytest.raises(NotImplementedError):
            backend.list_versions("test")

        with pytest.raises(NotImplementedError):
            backend.delete_version("test", "1.0.0")

        with pytest.raises(NotImplementedError):
            backend.get_latest_version("test")

        with pytest.raises(NotImplementedError):
            backend.set_latest_pointer("test", "1.0.0")


class TestAcceptanceCriteria:
    """Tests validating acceptance criteria."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def registry(self, temp_dir):
        """Create a registry for testing."""
        backend = FilesystemBackend(temp_dir)
        return ModelRegistry(backend)

    def test_ac1_semantic_versioning(self, registry) -> None:
        """AC1: Model versioning with semantic versioning (MAJOR.MINOR.PATCH)."""
        model = {"type": "test"}

        # Test MAJOR version bump (breaking changes)
        v1 = registry.create_new_version(
            model=model,
            model_name="test_model",
            training_data="dataset_v1",
            hyperparameters={"arch": "v1"},
            metrics={"accuracy": 0.90},
            bump="major",
        )
        # First version starts at 0.1.0 (no existing versions)
        assert v1.version == "0.1.0"

        # Test MINOR version bump (new features, backward compatible)
        v2 = registry.create_new_version(
            model=model,
            model_name="test_model",
            training_data="dataset_v1",
            hyperparameters={"arch": "v1", "feature": "new"},
            metrics={"accuracy": 0.92},
            bump="minor",
        )
        assert v2.version == "0.2.0"

        # Test PATCH version bump (bug fixes)
        v3 = registry.create_new_version(
            model=model,
            model_name="test_model",
            training_data="dataset_v1",
            hyperparameters={"arch": "v1", "feature": "new"},
            metrics={"accuracy": 0.925},
            bump="patch",
        )
        assert v3.version == "0.2.1"

        # Another MAJOR bump
        v4 = registry.create_new_version(
            model=model,
            model_name="test_model",
            training_data="dataset_v2",
            hyperparameters={"arch": "v2"},  # Breaking architecture change
            metrics={"accuracy": 0.95},
            bump="major",
        )
        assert v4.version == "1.0.0"

    def test_ac2_model_storage_with_metadata(self, registry) -> None:
        """AC2: Model storage with metadata (hyperparams, metrics, timestamp)."""
        model = {"weights": [1.0, 2.0, 3.0]}

        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={
                "learning_rate": 0.001,
                "epochs": 100,
                "batch_size": 32,
                "optimizer": "adam",
            },
            metrics={
                "accuracy": 0.95,
                "precision": 0.93,
                "recall": 0.94,
                "f1_score": 0.935,
                "auc_roc": 0.98,
            },
            tags=["production", "baseline"],
        )

        registry.register_model(model, metadata)
        loaded_model, loaded_metadata = registry.get_model("test_model", "1.0.0")

        # Verify hyperparameters stored correctly
        assert loaded_metadata.hyperparameters["learning_rate"] == 0.001
        assert loaded_metadata.hyperparameters["epochs"] == 100
        assert loaded_metadata.hyperparameters["optimizer"] == "adam"

        # Verify metrics stored correctly
        assert loaded_metadata.metrics["accuracy"] == 0.95
        assert loaded_metadata.metrics["precision"] == 0.93
        assert loaded_metadata.metrics["recall"] == 0.94
        assert loaded_metadata.metrics["f1_score"] == 0.935

        # Verify timestamp stored
        assert isinstance(loaded_metadata.created_at, datetime)

    def test_ac3_model_retrieval(self, registry) -> None:
        """AC3: Model retrieval by version or "latest" tag."""
        # Register multiple versions
        for i, version in enumerate(["1.0.0", "1.0.1", "1.1.0"]):
            model = {"version": i + 1}
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={},
                tags=[],
            )
            registry.register_model(model, metadata)
            time.sleep(0.01)

        # Retrieve by specific version
        model, _ = registry.get_model("test_model", "1.0.0")
        assert model == {"version": 1}

        model, _ = registry.get_model("test_model", "1.1.0")
        assert model == {"version": 3}

        # Retrieve by "latest" tag
        model, _ = registry.get_model("test_model", "latest")
        assert model == {"version": 3}

        # Retrieve using get_latest method
        model, _ = registry.get_latest("test_model")
        assert model == {"version": 3}

    def test_ac4_rollback_support(self, registry) -> None:
        """AC4: Rollback support - restore previous model version within 5 minutes."""
        # Register initial versions
        for i, version in enumerate(["1.0.0", "1.0.1", "1.1.0", "1.1.1"]):
            model = {"version": version, "data": i}
            metadata = ModelMetadata(
                model_name="test_model",
                version=version,
                created_at=datetime.now(UTC),
                training_data="dataset_v1",
                hyperparameters={},
                metrics={"accuracy": 0.90 + (i * 0.01)},
                tags=[],
            )
            registry.register_model(model, metadata)

        # Verify latest is 1.1.1
        model, metadata = registry.get_latest("test_model")
        assert model["version"] == "1.1.1"
        assert metadata.metrics["accuracy"] == 0.93

        # Time the rollback operation
        start_time = time.time()
        success = registry.rollback("test_model", "1.0.0")
        rollback_time = time.time() - start_time

        # Verify rollback succeeded
        assert success is True

        # Verify rollback completed well under 5 minutes (expecting <1 second)
        assert (
            rollback_time < 60
        ), f"Rollback took {rollback_time}s, must be <5min (300s)"

        # Verify latest is now 1.0.0
        model, metadata = registry.get_latest("test_model")
        assert model["version"] == "1.0.0"
        assert metadata.metrics["accuracy"] == 0.90

        # Verify all versions still exist
        versions = registry.list_versions("test_model")
        assert len(versions) == 4

        # Rollback to another version
        registry.rollback("test_model", "1.1.0")
        model, _ = registry.get_latest("test_model")
        assert model["version"] == "1.1.0"

    def test_ac5_storage_backends(self, temp_dir) -> None:
        """AC5: Storage backend supports filesystem and S3 backends."""
        # Test FilesystemBackend (primary)
        fs_backend = FilesystemBackend(temp_dir)
        fs_registry = ModelRegistry(fs_backend)

        model = {"type": "test"}
        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=datetime.now(UTC),
            training_data="dataset_v1",
            hyperparameters={},
            metrics={},
            tags=[],
        )

        version = fs_registry.register_model(model, metadata)
        assert version is not None

        loaded_model, _ = fs_registry.get_model("test_model", "1.0.0")
        assert loaded_model == model

        # Test S3Backend (interface only)
        s3_backend = S3Backend(
            bucket="test-bucket",
            prefix="models",
            region="us-east-1",
        )
        s3_registry = ModelRegistry(s3_backend)
        assert isinstance(s3_registry.backend, S3Backend)

        # Verify S3 operations raise NotImplementedError
        with pytest.raises(NotImplementedError):
            s3_registry.backend.save_model(model, metadata)

    def test_ac6_model_metadata_tracking(self, registry) -> None:
        """AC6: Model metadata tracks training data, performance metrics,
        creation date.
        """
        model = {"weights": [1.0, 2.0]}
        training_date = datetime(2024, 1, 15, 10, 30, 0)

        metadata = ModelMetadata(
            model_name="test_model",
            version="1.0.0",
            created_at=training_date,
            training_data="s3://chiseai-datasets/training/v1/run_20240115/",
            hyperparameters={"lr": 0.001, "batch_size": 64},
            metrics={
                "accuracy": 0.9523,
                "precision": 0.9487,
                "recall": 0.9512,
                "f1_score": 0.9499,
                "val_loss": 0.142,
                "train_loss": 0.098,
            },
            tags=["production", "baseline", "jan_2024"],
        )

        registry.register_model(model, metadata)
        _, loaded_metadata = registry.get_model("test_model", "1.0.0")

        # Verify training data reference
        assert (
            loaded_metadata.training_data
            == "s3://chiseai-datasets/training/v1/run_20240115/"
        )

        # Verify creation date
        assert loaded_metadata.created_at == training_date

        # Verify all performance metrics tracked
        assert loaded_metadata.metrics["accuracy"] == 0.9523
        assert loaded_metadata.metrics["precision"] == 0.9487
        assert loaded_metadata.metrics["recall"] == 0.9512
        assert loaded_metadata.metrics["f1_score"] == 0.9499
        assert loaded_metadata.metrics["val_loss"] == 0.142
        assert loaded_metadata.metrics["train_loss"] == 0.098

        # Verify history includes metadata
        history = registry.get_version_history("test_model")
        assert len(history) == 1
        assert (
            history[0]["training_data"]
            == "s3://chiseai-datasets/training/v1/run_20240115/"
        )
        assert "accuracy" in history[0]["metrics"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
