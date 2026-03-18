"""Tests for Experiment Query REST API.

Tests all API endpoints for the experiments API including:
- GET /api/v1/experiments - List experiments with filters
- GET /api/v1/experiments/{experiment_id} - Get experiment details
- GET /api/v1/experiments/{experiment_id}/artifacts - List artifacts
- GET /api/v1/experiments/{experiment_id}/hyperparameters - Get hyperparams
- GET /api/v1/experiments/{experiment_id}/lineage - Get lineage graph
- GET /api/v1/experiments/compare - Compare two experiments
- POST /api/v1/experiments/{experiment_id}/rollback - Rollback to version
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from api.experiments import (
    ArtifactInfo,
    ArtifactListResponse,
    ComparisonHyperparam,
    ComparisonMetrics,
    ComparisonResponse,
    ExperimentDetail,
    ExperimentListResponse,
    ExperimentStatus,
    ExperimentStore,
    ExperimentSummary,
    HyperparametersResponse,
    LineageEdge,
    LineageNode,
    LineageResponse,
    RollbackResponse,
    router,
    set_experiment_store,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store():
    """Create a mock experiment store for testing."""
    store = MagicMock(spec=ExperimentStore)
    return store


@pytest.fixture
def client(mock_store):
    """Create a test client with mock store."""
    app = FastAPI()
    app.include_router(router)
    set_experiment_store(mock_store)
    return TestClient(app)


@pytest.fixture
def sample_experiments() -> list[dict[str, Any]]:
    """Create sample experiment data."""
    return [
        {
            "experiment_id": "exp-001",
            "model_id": "model-alpha",
            "status": "completed",
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T14:00:00",
            "metrics": {"accuracy": 0.95, "f1": 0.93},
            "tags": ["production", "v1"],
            "description": "Initial training run",
            "hyperparameters": {"lr": 0.001, "epochs": 100},
            "artifact_count": 3,
            "duration_seconds": 7200.0,
        },
        {
            "experiment_id": "exp-002",
            "model_id": "model-alpha",
            "status": "running",
            "created_at": "2024-01-02T10:00:00",
            "updated_at": None,
            "metrics": {},
            "tags": ["dev"],
            "description": "Hyperparameter sweep",
            "hyperparameters": {"lr": 0.0005, "epochs": 200},
            "artifact_count": 1,
            "duration_seconds": None,
        },
        {
            "experiment_id": "exp-003",
            "model_id": "model-beta",
            "status": "failed",
            "created_at": "2024-01-03T08:00:00",
            "updated_at": "2024-01-03T09:00:00",
            "metrics": {"accuracy": 0.70},
            "tags": [],
            "description": "Failed convergence",
            "hyperparameters": {"lr": 0.1, "epochs": 10},
            "artifact_count": 0,
            "duration_seconds": 3600.0,
            "error_message": "Loss diverged at epoch 5",
        },
    ]


@pytest.fixture
def sample_artifacts() -> list[dict[str, Any]]:
    """Create sample artifact data."""
    return [
        {
            "artifact_id": "art-001",
            "artifact_type": "checkpoint",
            "created_at": "2024-01-01T13:00:00",
            "metadata": {"epoch": 50, "path": "/checkpoints/ckpt-50.pt"},
        },
        {
            "artifact_id": "art-002",
            "artifact_type": "config",
            "created_at": "2024-01-01T12:00:00",
            "metadata": {"framework": "pytorch"},
        },
        {
            "artifact_id": "art-003",
            "artifact_type": "log",
            "created_at": "2024-01-01T14:00:00",
            "metadata": {"training_duration_s": 7200},
        },
    ]


@pytest.fixture
def sample_comparison() -> dict[str, Any]:
    """Create sample comparison data."""
    return {
        "experiment1": {
            "experiment_id": "exp-001",
            "model_id": "model-alpha",
            "status": "completed",
            "created_at": "2024-01-01T12:00:00",
            "metrics": {"accuracy": 0.95, "f1": 0.93},
            "tags": ["production"],
        },
        "experiment2": {
            "experiment_id": "exp-002",
            "model_id": "model-alpha",
            "status": "running",
            "created_at": "2024-01-02T10:00:00",
            "metrics": {"accuracy": 0.92, "f1": 0.90},
            "tags": ["dev"],
        },
        "metric_diffs": [
            {
                "metric_name": "accuracy",
                "exp1_value": 0.95,
                "exp2_value": 0.92,
                "difference": -0.03,
            },
            {
                "metric_name": "f1",
                "exp1_value": 0.93,
                "exp2_value": 0.90,
                "difference": -0.03,
            },
        ],
        "hyperparam_diffs": [
            {
                "param_name": "lr",
                "exp1_value": 0.001,
                "exp2_value": 0.0005,
                "changed": True,
            },
            {
                "param_name": "epochs",
                "exp1_value": 100,
                "exp2_value": 200,
                "changed": True,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Test: List Experiments
# ---------------------------------------------------------------------------


class TestListExperiments:
    """Tests for GET /api/v1/experiments."""

    def test_list_all_experiments(self, client, mock_store, sample_experiments):
        """Test listing all experiments without filters."""
        mock_store.list_experiments.return_value = sample_experiments

        response = client.get("/api/v1/experiments")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["experiments"]) == 3
        assert data["count"] == 3
        mock_store.list_experiments.assert_called_once_with(
            model_id=None,
            experiment_status=None,
            limit=50,
            offset=0,
        )

    def test_list_filter_by_model_id(self, client, mock_store, sample_experiments):
        """Test filtering experiments by model_id."""
        mock_store.list_experiments.return_value = [
            e for e in sample_experiments if e["model_id"] == "model-alpha"
        ]

        response = client.get("/api/v1/experiments?model_id=model-alpha")

        assert response.status_code == 200
        data = response.json()
        assert len(data["experiments"]) == 2
        assert all(e["model_id"] == "model-alpha" for e in data["experiments"])

    def test_list_filter_by_status(self, client, mock_store, sample_experiments):
        """Test filtering experiments by status."""
        mock_store.list_experiments.return_value = [
            e for e in sample_experiments if e["status"] == "completed"
        ]

        response = client.get("/api/v1/experiments?status=completed")

        assert response.status_code == 200
        data = response.json()
        assert len(data["experiments"]) == 1
        assert data["experiments"][0]["status"] == "completed"

    def test_list_with_pagination(self, client, mock_store, sample_experiments):
        """Test pagination parameters."""
        mock_store.list_experiments.return_value = sample_experiments[:2]

        response = client.get("/api/v1/experiments?limit=2&offset=1")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        mock_store.list_experiments.assert_called_once_with(
            model_id=None,
            experiment_status=None,
            limit=2,
            offset=1,
        )

    def test_list_empty_results(self, client, mock_store):
        """Test listing when no experiments exist."""
        mock_store.list_experiments.return_value = []

        response = client.get("/api/v1/experiments")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["experiments"]) == 0
        assert data["count"] == 0

    def test_list_store_error(self, client, mock_store):
        """Test error handling when store raises exception."""
        mock_store.list_experiments.side_effect = RuntimeError("DB connection failed")

        response = client.get("/api/v1/experiments")

        assert response.status_code == 500
        assert "Failed to list experiments" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Get Experiment Detail
# ---------------------------------------------------------------------------


class TestGetExperiment:
    """Tests for GET /api/v1/experiments/{experiment_id}."""

    def test_get_experiment_success(self, client, mock_store, sample_experiments):
        """Test successful experiment retrieval."""
        mock_store.get_experiment.return_value = sample_experiments[0]

        response = client.get("/api/v1/experiments/exp-001")

        assert response.status_code == 200
        data = response.json()
        assert data["experiment_id"] == "exp-001"
        assert data["model_id"] == "model-alpha"
        assert data["status"] == "completed"
        assert data["metrics"]["accuracy"] == 0.95
        assert data["artifact_count"] == 3
        assert data["duration_seconds"] == 7200.0

    def test_get_experiment_not_found(self, client, mock_store):
        """Test retrieval of non-existent experiment."""
        mock_store.get_experiment.return_value = None

        response = client.get("/api/v1/experiments/exp-nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_experiment_with_error_message(
        self, client, mock_store, sample_experiments
    ):
        """Test experiment with error message (failed experiment)."""
        mock_store.get_experiment.return_value = sample_experiments[2]

        response = client.get("/api/v1/experiments/exp-003")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Loss diverged at epoch 5"

    def test_get_experiment_store_error(self, client, mock_store):
        """Test error handling when store raises exception."""
        mock_store.get_experiment.side_effect = RuntimeError("Store error")

        response = client.get("/api/v1/experiments/exp-001")

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Test: Get Artifacts
# ---------------------------------------------------------------------------


class TestGetArtifacts:
    """Tests for GET /api/v1/experiments/{experiment_id}/artifacts."""

    def test_get_artifacts_success(self, client, mock_store, sample_artifacts):
        """Test successful artifact listing."""
        mock_store.get_artifacts.return_value = sample_artifacts

        response = client.get("/api/v1/experiments/exp-001/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment_id"] == "exp-001"
        assert len(data["artifacts"]) == 3
        assert data["count"] == 3
        assert data["artifacts"][0]["artifact_type"] == "checkpoint"

    def test_get_artifacts_empty(self, client, mock_store):
        """Test artifact listing with no artifacts."""
        mock_store.get_artifacts.return_value = []

        response = client.get("/api/v1/experiments/exp-003/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert len(data["artifacts"]) == 0

    def test_get_artifacts_store_error(self, client, mock_store):
        """Test error handling."""
        mock_store.get_artifacts.side_effect = RuntimeError("Store error")

        response = client.get("/api/v1/experiments/exp-001/artifacts")

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Test: Get Hyperparameters
# ---------------------------------------------------------------------------


class TestGetHyperparameters:
    """Tests for GET /api/v1/experiments/{experiment_id}/hyperparameters."""

    def test_get_hyperparameters_success(self, client, mock_store):
        """Test successful hyperparameters retrieval."""
        mock_store.get_hyperparameters.return_value = {
            "hyperparameters": {
                "learning_rate": 0.001,
                "batch_size": 32,
                "epochs": 100,
                "optimizer": "adam",
            },
            "fingerprint": "abc123def456",
        }

        response = client.get("/api/v1/experiments/exp-001/hyperparameters")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment_id"] == "exp-001"
        assert data["hyperparameters"]["learning_rate"] == 0.001
        assert data["fingerprint"] == "abc123def456"

    def test_get_hyperparameters_not_found(self, client, mock_store):
        """Test retrieval when hyperparameters don't exist."""
        mock_store.get_hyperparameters.return_value = None

        response = client.get("/api/v1/experiments/exp-001/hyperparameters")

        assert response.status_code == 404
        assert "hyperparameters not found" in response.json()["detail"].lower()

    def test_get_hyperparameters_store_error(self, client, mock_store):
        """Test error handling."""
        mock_store.get_hyperparameters.side_effect = RuntimeError("Error")

        response = client.get("/api/v1/experiments/exp-001/hyperparameters")

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Test: Get Lineage
# ---------------------------------------------------------------------------


class TestGetLineage:
    """Tests for GET /api/v1/experiments/{experiment_id}/lineage."""

    def test_get_lineage_success(self, client, mock_store):
        """Test successful lineage retrieval."""
        mock_store.get_lineage.return_value = {
            "nodes": [
                {
                    "experiment_id": "exp-parent",
                    "model_id": "model-alpha",
                    "status": "completed",
                    "created_at": "2023-12-01T10:00:00",
                },
                {
                    "experiment_id": "exp-001",
                    "model_id": "model-alpha",
                    "status": "completed",
                    "created_at": "2024-01-01T12:00:00",
                },
                {
                    "experiment_id": "exp-child",
                    "model_id": "model-alpha",
                    "status": "running",
                    "created_at": "2024-01-02T10:00:00",
                },
            ],
            "edges": [
                {
                    "source_id": "exp-parent",
                    "target_id": "exp-001",
                    "relationship": "derived_from",
                },
                {
                    "source_id": "exp-001",
                    "target_id": "exp-child",
                    "relationship": "parent_of",
                },
            ],
        }

        response = client.get("/api/v1/experiments/exp-001/lineage")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment_id"] == "exp-001"
        assert len(data["nodes"]) == 3
        assert len(data["edges"]) == 2
        assert data["edges"][0]["relationship"] == "derived_from"

    def test_get_lineage_not_found(self, client, mock_store):
        """Test retrieval when lineage doesn't exist."""
        mock_store.get_lineage.return_value = None

        response = client.get("/api/v1/experiments/exp-001/lineage")

        assert response.status_code == 404
        assert "lineage not found" in response.json()["detail"].lower()

    def test_get_lineage_store_error(self, client, mock_store):
        """Test error handling."""
        mock_store.get_lineage.side_effect = RuntimeError("Error")

        response = client.get("/api/v1/experiments/exp-001/lineage")

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Test: Compare Experiments
# ---------------------------------------------------------------------------


class TestCompareExperiments:
    """Tests for GET /api/v1/experiments/compare."""

    def test_compare_success(self, client, mock_store, sample_comparison):
        """Test successful experiment comparison."""
        mock_store.compare_experiments.return_value = sample_comparison

        response = client.get(
            "/api/v1/experiments/compare?exp1_id=exp-001&exp2_id=exp-002"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment1"]["experiment_id"] == "exp-001"
        assert data["experiment2"]["experiment_id"] == "exp-002"
        assert len(data["metric_diffs"]) == 2
        assert len(data["hyperparam_diffs"]) == 2
        assert data["metric_diffs"][0]["metric_name"] == "accuracy"
        assert data["metric_diffs"][0]["difference"] == -0.03
        assert data["hyperparam_diffs"][0]["changed"] is True

    def test_compare_experiment_not_found(self, client, mock_store):
        """Test comparison when one experiment doesn't exist."""
        mock_store.compare_experiments.side_effect = ValueError(
            "Experiment exp-nonexistent not found"
        )

        response = client.get(
            "/api/v1/experiments/compare?exp1_id=exp-001&exp2_id=exp-nonexistent"
        )

        assert response.status_code == 404

    def test_compare_missing_params(self, client, mock_store):
        """Test comparison with missing query parameters."""
        response = client.get("/api/v1/experiments/compare?exp1_id=exp-001")

        assert response.status_code == 422  # Validation error

    def test_compare_store_error(self, client, mock_store):
        """Test error handling."""
        mock_store.compare_experiments.side_effect = RuntimeError("Error")

        response = client.get(
            "/api/v1/experiments/compare?exp1_id=exp-001&exp2_id=exp-002"
        )

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Test: Rollback
# ---------------------------------------------------------------------------


class TestRollbackExperiment:
    """Tests for POST /api/v1/experiments/{experiment_id}/rollback."""

    def test_rollback_success(self, client, mock_store):
        """Test successful rollback."""
        mock_store.rollback_experiment.return_value = {
            "success": True,
            "message": "Rolled back to experiment exp-001 (version 1.0.0)",
            "rolled_back_to_version": "1.0.0",
            "previous_version": "1.1.0",
        }

        response = client.post("/api/v1/experiments/exp-001/rollback")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment_id"] == "exp-001"
        assert data["rolled_back_to_version"] == "1.0.0"
        assert data["previous_version"] == "1.1.0"

    def test_rollback_invalid_request(self, client, mock_store):
        """Test rollback with invalid request."""
        mock_store.rollback_experiment.side_effect = ValueError(
            "Cannot rollback: experiment has no model version"
        )

        response = client.post("/api/v1/experiments/exp-001/rollback")

        assert response.status_code == 400
        assert "cannot rollback" in response.json()["detail"].lower()

    def test_rollback_store_error(self, client, mock_store):
        """Test error handling."""
        mock_store.rollback_experiment.side_effect = RuntimeError("Error")

        response = client.post("/api/v1/experiments/exp-001/rollback")

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Test: Store Not Initialized
# ---------------------------------------------------------------------------


class TestStoreNotInitialized:
    """Tests for when the experiment store is not initialized."""

    def test_list_without_store(self, client, mock_store):
        """Test listing without initialized store."""
        set_experiment_store(None)

        response = client.get("/api/v1/experiments")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()

    def test_get_without_store(self, client, mock_store):
        """Test get without initialized store."""
        set_experiment_store(None)

        response = client.get("/api/v1/experiments/exp-001")

        assert response.status_code == 503

    def test_compare_without_store(self, client, mock_store):
        """Test compare without initialized store."""
        set_experiment_store(None)

        response = client.get(
            "/api/v1/experiments/compare?exp1_id=exp-001&exp2_id=exp-002"
        )

        assert response.status_code == 503

    def test_rollback_without_store(self, client, mock_store):
        """Test rollback without initialized store."""
        set_experiment_store(None)

        response = client.post("/api/v1/experiments/exp-001/rollback")

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Test: Response Models
# ---------------------------------------------------------------------------


class TestResponseModels:
    """Tests for Pydantic response model validation."""

    def test_experiment_summary_model(self):
        """Test ExperimentSummary model."""
        summary = ExperimentSummary(
            experiment_id="exp-001",
            model_id="model-alpha",
            status="completed",
            created_at="2024-01-01T12:00:00",
            metrics={"accuracy": 0.95},
            tags=["production"],
        )
        data = summary.model_dump()
        assert data["experiment_id"] == "exp-001"
        assert data["metrics"]["accuracy"] == 0.95

    def test_experiment_detail_model(self):
        """Test ExperimentDetail model."""
        detail = ExperimentDetail(
            experiment_id="exp-001",
            model_id="model-alpha",
            status="failed",
            created_at="2024-01-01T12:00:00",
            error_message="Loss diverged",
            artifact_count=5,
            duration_seconds=3600.0,
        )
        assert detail.error_message == "Loss diverged"
        assert detail.artifact_count == 5

    def test_comparison_response_model(self):
        """Test ComparisonResponse model."""
        response = ComparisonResponse(
            success=True,
            experiment1=ExperimentSummary(
                experiment_id="exp-001",
                model_id="m1",
                status="completed",
                created_at="2024-01-01T00:00:00",
            ),
            experiment2=ExperimentSummary(
                experiment_id="exp-002",
                model_id="m1",
                status="completed",
                created_at="2024-01-02T00:00:00",
            ),
            metric_diffs=[
                ComparisonMetrics(
                    metric_name="accuracy",
                    exp1_value=0.95,
                    exp2_value=0.92,
                    difference=-0.03,
                )
            ],
            hyperparam_diffs=[
                ComparisonHyperparam(
                    param_name="lr",
                    exp1_value=0.001,
                    exp2_value=0.0005,
                    changed=True,
                )
            ],
        )
        assert len(response.metric_diffs) == 1
        assert response.hyperparam_diffs[0].changed is True

    def test_lineage_response_model(self):
        """Test LineageResponse model."""
        response = LineageResponse(
            success=True,
            experiment_id="exp-001",
            nodes=[
                LineageNode(
                    experiment_id="exp-001",
                    model_id="m1",
                    status="completed",
                    created_at="2024-01-01T00:00:00",
                )
            ],
            edges=[
                LineageEdge(
                    source_id="exp-parent",
                    target_id="exp-001",
                    relationship="derived_from",
                )
            ],
        )
        assert len(response.nodes) == 1
        assert len(response.edges) == 1

    def test_artifact_list_response_model(self):
        """Test ArtifactListResponse model."""
        response = ArtifactListResponse(
            success=True,
            experiment_id="exp-001",
            artifacts=[
                ArtifactInfo(
                    artifact_id="art-001",
                    artifact_type="checkpoint",
                    created_at="2024-01-01T00:00:00",
                )
            ],
            count=1,
        )
        assert response.count == 1

    def test_experiment_status_enum(self):
        """Test ExperimentStatus enum values."""
        assert ExperimentStatus.PENDING.value == "pending"
        assert ExperimentStatus.RUNNING.value == "running"
        assert ExperimentStatus.COMPLETED.value == "completed"
        assert ExperimentStatus.FAILED.value == "failed"
        assert ExperimentStatus.CANCELLED.value == "cancelled"
