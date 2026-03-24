"""Tests for Model Registry REST API.

Tests all API endpoints for the model registry including:
- POST /api/v1/models - Register new model
- GET /api/v1/models/{name} - List all versions
- GET /api/v1/models/{name}/{version} - Get specific model
- GET /api/v1/models/{name}/latest - Get latest model
- POST /api/v1/models/{name}/rollback - Rollback to version
- GET /api/v1/models/{name}/history - Get version history
- GET /api/v1/models/{name}/compare - Compare two versions
- GET /health - Health check endpoint
"""

from __future__ import annotations

import io
import pickle

# Import after path setup
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fastapi import FastAPI

from api.model_registry_api import (
    health_router,
    router,
    set_model_registry,
)
from ml.models.model_registry import ModelRegistry
from ml.models.model_storage import (
    ModelMetadata,
    ModelNotFoundError,
    ModelRegistryError,
    ModelValidationError,
    ModelVersion,
    ModelVersionExistsError,
)


@pytest.fixture
def mock_registry():
    """Create a mock registry for testing."""
    registry = MagicMock(spec=ModelRegistry)
    return registry


@pytest.fixture
def client(mock_registry):
    """Create a test client with mock registry."""
    app = FastAPI()
    app.include_router(router)
    app.include_router(health_router)

    # Set the mock registry
    set_model_registry(mock_registry)

    return TestClient(app)


@pytest.fixture
def sample_model():
    """Create a sample model for testing."""
    return {"type": "test_model", "weights": [1.0, 2.0, 3.0]}


@pytest.fixture
def sample_metadata():
    """Create sample metadata for testing."""
    return ModelMetadata(
        model_name="test_model",
        version="1.0.0",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        training_data="dataset_v1",
        hyperparameters={"lr": 0.001, "epochs": 100},
        metrics={"accuracy": 0.95, "f1": 0.93},
        tags=["production", "v1"],
    )


@pytest.fixture
def sample_model_version(sample_metadata):
    """Create a sample model version for testing."""
    return ModelVersion(
        model_name=sample_metadata.model_name,
        version=sample_metadata.version,
        created_at=sample_metadata.created_at,
        metadata_path="/path/to/metadata.json",
        model_path="/path/to/model.pkl",
        checksum="abc123def456",
    )


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check_initialized(self, client, mock_registry):
        """Test health check when registry is initialized."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["registry_initialized"] is True
        assert "timestamp" in data

    def test_health_check_not_initialized(self, client):
        """Test health check when registry is not initialized."""
        # Reset registry to None
        set_model_registry(None)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["registry_initialized"] is False


class TestRegisterModel:
    """Tests for the register model endpoint."""

    def test_register_model_success(
        self, client, mock_registry, sample_model, sample_model_version
    ):
        """Test successful model registration."""
        mock_registry.register_model.return_value = sample_model_version

        # Create model file
        model_bytes = pickle.dumps(sample_model)
        model_file = ("model.pkl", io.BytesIO(model_bytes), "application/octet-stream")

        response = client.post(
            "/api/v1/models",
            data={
                "model_name": "test_model",
                "version": "1.0.0",
                "training_data": "dataset_v1",
                "hyperparameters": '{"lr": 0.001}',
                "metrics": '{"accuracy": 0.95}',
                "tags": '["production"]',
            },
            files={"model_file": model_file},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "test_model@1.0.0" in data["message"]
        assert data["model"]["version"] == "1.0.0"

    def test_register_model_version_exists(self, client, mock_registry, sample_model):
        """Test registration with existing version."""
        mock_registry.register_model.side_effect = ModelVersionExistsError(
            "Version 1.0.0 already exists"
        )

        model_bytes = pickle.dumps(sample_model)
        model_file = ("model.pkl", io.BytesIO(model_bytes), "application/octet-stream")

        response = client.post(
            "/api/v1/models",
            data={
                "model_name": "test_model",
                "version": "1.0.0",
                "training_data": "dataset_v1",
                "hyperparameters": "{}",
                "metrics": "{}",
                "tags": "[]",
            },
            files={"model_file": model_file},
        )

        assert response.status_code == 409
        data = response.json()
        assert "already exists" in data["detail"]

    def test_register_model_validation_error(self, client, mock_registry, sample_model):
        """Test registration with validation error."""
        mock_registry.register_model.side_effect = ModelValidationError(
            "Model validation failed"
        )

        model_bytes = pickle.dumps(sample_model)
        model_file = ("model.pkl", io.BytesIO(model_bytes), "application/octet-stream")

        response = client.post(
            "/api/v1/models",
            data={
                "model_name": "test_model",
                "version": "1.0.0",
                "training_data": "dataset_v1",
                "hyperparameters": "{}",
                "metrics": "{}",
                "tags": "[]",
            },
            files={"model_file": model_file},
        )

        assert response.status_code == 400
        data = response.json()
        assert "validation" in data["detail"].lower()

    def test_register_model_invalid_json(self, client, mock_registry):
        """Test registration with invalid JSON parameters."""
        model_bytes = pickle.dumps({"test": "model"})
        model_file = ("model.pkl", io.BytesIO(model_bytes), "application/octet-stream")

        response = client.post(
            "/api/v1/models",
            data={
                "model_name": "test_model",
                "version": "1.0.0",
                "training_data": "dataset_v1",
                "hyperparameters": "invalid json",
                "metrics": "{}",
                "tags": "[]",
            },
            files={"model_file": model_file},
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid JSON" in data["detail"]

    def test_register_model_invalid_version_format(self, client, mock_registry):
        """Test registration with invalid version format."""
        model_bytes = pickle.dumps({"test": "model"})
        model_file = ("model.pkl", io.BytesIO(model_bytes), "application/octet-stream")

        response = client.post(
            "/api/v1/models",
            data={
                "model_name": "test_model",
                "version": "invalid",
                "training_data": "dataset_v1",
                "hyperparameters": "{}",
                "metrics": "{}",
                "tags": "[]",
            },
            files={"model_file": model_file},
        )

        assert response.status_code == 422  # Validation error


class TestListVersions:
    """Tests for the list versions endpoint."""

    def test_list_versions_success(self, client, mock_registry):
        """Test successful version listing."""
        mock_registry.list_versions.return_value = [
            ModelVersion(
                model_name="test_model",
                version="1.1.0",
                created_at=datetime(2024, 1, 2, 12, 0, 0),
                metadata_path="/path/to/v1.1.0/metadata.json",
                model_path="/path/to/v1.1.0/model.pkl",
                checksum="abc123",
            ),
            ModelVersion(
                model_name="test_model",
                version="1.0.0",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
                metadata_path="/path/to/v1.0.0/metadata.json",
                model_path="/path/to/v1.0.0/model.pkl",
                checksum="def456",
            ),
        ]

        response = client.get("/api/v1/models/test_model")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["model_name"] == "test_model"
        assert len(data["versions"]) == 2
        assert data["versions"][0]["version"] == "1.1.0"
        assert data["count"] == 2

    def test_list_versions_empty(self, client, mock_registry):
        """Test listing with no versions."""
        mock_registry.list_versions.return_value = []

        response = client.get("/api/v1/models/test_model")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["versions"]) == 0
        assert data["count"] == 0

    def test_list_versions_pagination(self, client, mock_registry):
        """Test version listing with pagination."""
        versions = [
            ModelVersion(
                model_name="test_model",
                version=f"1.{i}.0",
                created_at=datetime(2024, 1, i + 1, 12, 0, 0),
                metadata_path=f"/path/to/v1.{i}.0/metadata.json",
                model_path=f"/path/to/v1.{i}.0/model.pkl",
                checksum=f"checksum{i}",
            )
            for i in range(10)
        ]
        mock_registry.list_versions.return_value = versions

        response = client.get("/api/v1/models/test_model?limit=5&offset=2")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 10  # Total count
        assert len(data["versions"]) == 5  # Paginated count


class TestGetModel:
    """Tests for the get model endpoint."""

    def test_get_model_success(self, client, mock_registry, sample_metadata):
        """Test successful model retrieval."""
        mock_registry.get_model.return_value = (None, sample_metadata)

        response = client.get("/api/v1/models/test_model/1.0.0")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["model_name"] == "test_model"
        assert data["version"] == "1.0.0"
        assert data["metadata"]["training_data"] == "dataset_v1"
        assert data["metadata"]["metrics"]["accuracy"] == 0.95

    def test_get_model_not_found(self, client, mock_registry):
        """Test retrieval of non-existent model."""
        mock_registry.get_model.side_effect = ModelNotFoundError(
            "Model version not found: test_model@1.0.0"
        )

        response = client.get("/api/v1/models/test_model/1.0.0")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_model_invalid_version(self, client, mock_registry):
        """Test retrieval with invalid version format."""
        mock_registry.get_model.side_effect = ValueError("Invalid version format")

        response = client.get("/api/v1/models/test_model/invalid")

        assert response.status_code == 400


class TestGetLatestModel:
    """Tests for the get latest model endpoint."""

    def test_get_latest_model_success(self, client, mock_registry, sample_metadata):
        """Test successful latest model retrieval."""
        mock_registry.get_latest.return_value = (None, sample_metadata)

        response = client.get("/api/v1/models/test_model/latest")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["model_name"] == "test_model"
        assert data["version"] == "1.0.0"

    def test_get_latest_model_not_found(self, client, mock_registry):
        """Test retrieval when no versions exist."""
        mock_registry.get_latest.side_effect = ModelNotFoundError(
            "No versions found for model: test_model"
        )

        response = client.get("/api/v1/models/test_model/latest")

        assert response.status_code == 404
        data = response.json()
        assert "no versions found" in data["detail"].lower()


class TestRollback:
    """Tests for the rollback endpoint."""

    def test_rollback_success(self, client, mock_registry):
        """Test successful rollback."""
        mock_registry.rollback.return_value = True

        response = client.post("/api/v1/models/test_model/rollback?version=1.0.0")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "rolled back" in data["message"].lower()
        assert data["model_name"] == "test_model"
        assert data["rolled_back_to"] == "1.0.0"

    def test_rollback_model_not_found(self, client, mock_registry):
        """Test rollback to non-existent version."""
        mock_registry.rollback.side_effect = ModelNotFoundError(
            "Version 1.0.0 not found"
        )

        response = client.post("/api/v1/models/test_model/rollback?version=1.0.0")

        assert response.status_code == 404

    def test_rollback_invalid_version(self, client, mock_registry):
        """Test rollback with invalid version format."""
        mock_registry.rollback.side_effect = ValueError("Invalid version format")

        response = client.post("/api/v1/models/test_model/rollback?version=invalid")

        assert response.status_code == 400


class TestHistory:
    """Tests for the history endpoint."""

    def test_history_success(self, client, mock_registry):
        """Test successful history retrieval."""
        mock_registry.get_version_history.return_value = [
            {
                "version": "1.1.0",
                "created_at": "2024-01-02T12:00:00",
                "model_name": "test_model",
                "metrics": {"accuracy": 0.96},
                "tags": ["production"],
                "training_data": "dataset_v2",
                "checksum": "abc123",
            },
            {
                "version": "1.0.0",
                "created_at": "2024-01-01T12:00:00",
                "model_name": "test_model",
                "metrics": {"accuracy": 0.95},
                "tags": ["production"],
                "training_data": "dataset_v1",
                "checksum": "def456",
            },
        ]

        response = client.get("/api/v1/models/test_model/history")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["model_name"] == "test_model"
        assert len(data["history"]) == 2
        assert data["history"][0]["version"] == "1.1.0"


class TestCompare:
    """Tests for the compare endpoint."""

    def test_compare_success(self, client, mock_registry):
        """Test successful version comparison."""
        mock_registry.compare_versions.return_value = {
            "version1": {
                "version": "1.0.0",
                "created_at": "2024-01-01T12:00:00",
                "metrics": {"accuracy": 0.95, "f1": 0.93},
            },
            "version2": {
                "version": "1.1.0",
                "created_at": "2024-01-02T12:00:00",
                "metrics": {"accuracy": 0.96, "f1": 0.94},
            },
            "metric_diffs": {"accuracy": 0.01, "f1": 0.01},
        }

        response = client.get(
            "/api/v1/models/test_model/compare?version1=1.0.0&version2=1.1.0"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["model_name"] == "test_model"
        assert data["version1"]["version"] == "1.0.0"
        assert data["version2"]["version"] == "1.1.0"
        assert data["metric_diffs"]["accuracy"] == 0.01

    def test_compare_model_not_found(self, client, mock_registry):
        """Test comparison with non-existent model."""
        mock_registry.compare_versions.side_effect = ModelNotFoundError(
            "Model not found"
        )

        response = client.get(
            "/api/v1/models/test_model/compare?version1=1.0.0&version2=1.1.0"
        )

        assert response.status_code == 404


class TestDelete:
    """Tests for the delete endpoint."""

    def test_delete_success(self, client, mock_registry):
        """Test successful version deletion."""
        mock_registry.delete_version.return_value = None

        response = client.delete("/api/v1/models/test_model/1.0.0")

        assert response.status_code == 204

    def test_delete_model_not_found(self, client, mock_registry):
        """Test deletion of non-existent version."""
        mock_registry.delete_version.side_effect = ModelNotFoundError(
            "Version not found"
        )

        response = client.delete("/api/v1/models/test_model/1.0.0")

        assert response.status_code == 404

    def test_delete_latest_version(self, client, mock_registry):
        """Test deletion of latest version (should fail)."""
        mock_registry.delete_version.side_effect = ModelRegistryError(
            "Cannot delete version 1.0.0: it is the current 'latest' version"
        )

        response = client.delete("/api/v1/models/test_model/1.0.0")

        assert response.status_code == 400
        data = response.json()
        assert "latest" in data["detail"].lower()


class TestRegistryNotInitialized:
    """Tests for when registry is not initialized."""

    def test_register_without_registry(self, client):
        """Test registration without initialized registry."""
        set_model_registry(None)

        model_bytes = pickle.dumps({"test": "model"})
        model_file = ("model.pkl", io.BytesIO(model_bytes), "application/octet-stream")

        response = client.post(
            "/api/v1/models",
            data={
                "model_name": "test_model",
                "version": "1.0.0",
                "training_data": "dataset_v1",
                "hyperparameters": "{}",
                "metrics": "{}",
                "tags": "[]",
            },
            files={"model_file": model_file},
        )

        assert response.status_code == 503
        data = response.json()
        assert "not initialized" in data["detail"].lower()

    def test_list_without_registry(self, client):
        """Test listing without initialized registry."""
        set_model_registry(None)

        response = client.get("/api/v1/models/test_model")

        assert response.status_code == 503

    def test_get_without_registry(self, client):
        """Test get without initialized registry."""
        set_model_registry(None)

        response = client.get("/api/v1/models/test_model/1.0.0")

        assert response.status_code == 503
