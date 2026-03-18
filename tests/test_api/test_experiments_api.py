"""Tests for Experiment Query REST API.

Tests all API endpoints for experiment querying including:
- GET  /api/v1/experiments - List experiments with filters
- GET  /api/v1/experiments/{experiment_id} - Get experiment details
- GET  /api/v1/experiments/{experiment_id}/artifacts - Get artifacts
- GET  /api/v1/experiments/{experiment_id}/hyperparameters - Get hyperparams
- GET  /api/v1/experiments/{experiment_id}/lineage - Get lineage
- GET  /api/v1/experiments/compare - Compare two experiments
- POST /api/v1/experiments/{experiment_id}/rollback - Rollback
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.experiments import (
    router,
    set_experiment_services,
)
from ml.training.artifacts.models import (
    CheckpointArtifact,
    ConfigArtifact,
    LogArtifact,
)
from ml.training.lineage.models import (
    LineageGraph,
    LineageNode,
    NodeType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_artifact_manager():
    """Create a mock ArtifactManager."""
    return MagicMock()


@pytest.fixture
def mock_lineage_tracker():
    """Create a mock LineageTracker."""
    return MagicMock()


@pytest.fixture
def client(mock_artifact_manager, mock_lineage_tracker):
    """Create a test client with mocked services."""
    app = FastAPI()
    app.include_router(router)
    set_experiment_services(mock_artifact_manager, mock_lineage_tracker)
    return TestClient(app)


@pytest.fixture
def sample_checkpoints():
    """Create sample checkpoint artifacts."""
    return [
        CheckpointArtifact(
            artifact_id="ckpt-001",
            experiment_id="exp-001",
            checkpoint_path="/models/ckpt-001.pt",
            epoch=5,
            metrics_snapshot={"val_loss": 0.12, "accuracy": 0.93},
        ),
        CheckpointArtifact(
            artifact_id="ckpt-002",
            experiment_id="exp-001",
            checkpoint_path="/models/ckpt-002.pt",
            epoch=10,
            metrics_snapshot={"val_loss": 0.08, "accuracy": 0.96},
        ),
    ]


@pytest.fixture
def sample_configs():
    """Create sample config artifacts."""
    return [
        ConfigArtifact(
            artifact_id="cfg-001",
            experiment_id="exp-001",
            hyperparameters={
                "learning_rate": 0.001,
                "batch_size": 32,
                "epochs": 50,
                "optimizer": "adam",
                "loss_function": "mse",
            },
            model_architecture="lstm_v2",
            data_config={"train_split": 0.8},
            random_seed=42,
            framework="pytorch",
        ),
    ]


@pytest.fixture
def sample_logs():
    """Create sample log artifacts."""
    return [
        LogArtifact(
            artifact_id="log-001",
            experiment_id="exp-001",
            training_duration_seconds=3600.0,
            final_metrics={"val_loss": 0.08, "accuracy": 0.96},
            status="completed",
        ),
    ]


@pytest.fixture
def experiment_summary_dict():
    """Raw summary dict from ArtifactManager.experiment_summary()."""
    return {
        "experiment_id": "exp-001",
        "checkpoint_count": 2,
        "config_count": 1,
        "log_count": 1,
        "latest_checkpoint_epoch": 10,
        "latest_config_id": "cfg-001",
        "latest_log_status": "completed",
        "training_duration_seconds": 3600.0,
        "final_metrics": {"val_loss": 0.08, "accuracy": 0.96},
    }


# ---------------------------------------------------------------------------
# GET /api/v1/experiments
# ---------------------------------------------------------------------------


class TestListExperiments:
    """Tests for listing experiments."""

    def test_list_experiments_success(
        self, client, mock_artifact_manager, experiment_summary_dict
    ):
        """Test successful experiment listing."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001", "exp-002"]
        mock_artifact_manager.experiment_summary.return_value = experiment_summary_dict

        response = client.get("/api/v1/experiments")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert len(data["experiments"]) == 2
        assert data["experiments"][0]["experiment_id"] == "exp-001"

    def test_list_experiments_pagination(
        self, client, mock_artifact_manager, experiment_summary_dict
    ):
        """Test pagination parameters."""
        mock_artifact_manager.list_experiments.return_value = [
            f"exp-{i:03d}" for i in range(10)
        ]
        mock_artifact_manager.experiment_summary.return_value = experiment_summary_dict

        response = client.get("/api/v1/experiments?limit=3&offset=2")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 10  # total
        assert len(data["experiments"]) == 3  # returned

    def test_list_experiments_empty(self, client, mock_artifact_manager):
        """Test listing when no experiments exist."""
        mock_artifact_manager.list_experiments.return_value = []

        response = client.get("/api/v1/experiments")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["experiments"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/experiments/{experiment_id}
# ---------------------------------------------------------------------------


class TestGetExperiment:
    """Tests for getting experiment details."""

    def test_get_experiment_success(
        self, client, mock_artifact_manager, experiment_summary_dict
    ):
        """Test successful experiment detail retrieval."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]
        mock_artifact_manager.experiment_summary.return_value = experiment_summary_dict

        response = client.get("/api/v1/experiments/exp-001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment"]["experiment_id"] == "exp-001"
        assert data["experiment"]["checkpoint_count"] == 2
        assert data["experiment"]["final_metrics"]["accuracy"] == 0.96

    def test_get_experiment_not_found(self, client, mock_artifact_manager):
        """Test retrieval of non-existent experiment."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]

        response = client.get("/api/v1/experiments/exp-999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/v1/experiments/{experiment_id}/artifacts
# ---------------------------------------------------------------------------


class TestGetArtifacts:
    """Tests for getting experiment artifacts."""

    def test_get_artifacts_success(
        self,
        client,
        mock_artifact_manager,
        sample_checkpoints,
        sample_configs,
        sample_logs,
    ):
        """Test successful artifact listing."""
        mock_artifact_manager.get_artifacts.return_value = (
            sample_checkpoints + sample_configs + sample_logs
        )

        response = client.get("/api/v1/experiments/exp-001/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 4
        assert data["artifacts"][0]["artifact_type"] == "checkpoint"

    def test_get_artifacts_with_type_filter(
        self, client, mock_artifact_manager, sample_checkpoints
    ):
        """Test artifact listing with type filter."""
        mock_artifact_manager.get_artifacts.return_value = sample_checkpoints

        response = client.get(
            "/api/v1/experiments/exp-001/artifacts?artifact_type=checkpoint"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        for art in data["artifacts"]:
            assert art["artifact_type"] == "checkpoint"

    def test_get_artifacts_invalid_type(self, client, mock_artifact_manager):
        """Test artifact listing with invalid type filter."""
        response = client.get(
            "/api/v1/experiments/exp-001/artifacts?artifact_type=invalid_type"
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/v1/experiments/{experiment_id}/hyperparameters
# ---------------------------------------------------------------------------


class TestGetHyperparameters:
    """Tests for getting experiment hyperparameters."""

    def test_get_hyperparameters_success(
        self, client, mock_artifact_manager, sample_configs
    ):
        """Test successful hyperparameter retrieval."""
        mock_artifact_manager.get_configs.return_value = sample_configs

        response = client.get("/api/v1/experiments/exp-001/hyperparameters")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 1
        hp = data["hyperparameters"][0]
        assert hp["learning_rate"] == 0.001
        assert hp["batch_size"] == 32
        assert hp["epochs"] == 50
        assert hp["optimizer"] == "adam"
        assert hp["framework"] == "pytorch"
        assert hp["random_seed"] == 42

    def test_get_hyperparameters_empty(self, client, mock_artifact_manager):
        """Test hyperparameters when no configs exist."""
        mock_artifact_manager.get_configs.return_value = []

        response = client.get("/api/v1/experiments/exp-001/hyperparameters")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["hyperparameters"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/experiments/{experiment_id}/lineage
# ---------------------------------------------------------------------------


class TestGetLineage:
    """Tests for getting experiment lineage."""

    def test_get_lineage_success(
        self, client, mock_artifact_manager, mock_lineage_tracker
    ):
        """Test successful lineage retrieval."""
        # Build a small lineage graph
        graph = LineageGraph()
        graph.add_node(
            LineageNode(
                node_id="exp-001",
                node_type=NodeType.EXPERIMENT,
                metadata={"model": "lstm"},
            )
        )
        graph.add_node(
            LineageNode(
                node_id="data-v1",
                node_type=NodeType.DATA,
                metadata={"format": "parquet"},
            )
        )

        mock_lineage_tracker.get_lineage.return_value = graph
        mock_lineage_tracker.get_descendants.return_value = LineageGraph()

        response = client.get("/api/v1/experiments/exp-001/lineage")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment_id"] == "exp-001"
        assert len(data["nodes"]) == 2
        node_ids = {n["node_id"] for n in data["nodes"]}
        assert "exp-001" in node_ids
        assert "data-v1" in node_ids

    def test_get_lineage_no_tracker(self, client, mock_artifact_manager):
        """Test lineage when tracker is not initialized."""
        # Replace with None tracker
        from api import experiments as exp_mod

        exp_mod._lineage_tracker = None

        response = client.get("/api/v1/experiments/exp-001/lineage")

        assert response.status_code == 503

        # Restore
        exp_mod._lineage_tracker = mock_lineage_tracker


# ---------------------------------------------------------------------------
# GET /api/v1/experiments/compare
# ---------------------------------------------------------------------------


class TestCompareExperiments:
    """Tests for comparing experiments."""

    def test_compare_success(
        self, client, mock_artifact_manager, experiment_summary_dict
    ):
        """Test successful experiment comparison."""
        summary1 = dict(experiment_summary_dict)
        summary2 = dict(experiment_summary_dict)
        summary2["experiment_id"] = "exp-002"
        summary2["final_metrics"] = {"val_loss": 0.06, "accuracy": 0.97}

        mock_artifact_manager.list_experiments.return_value = ["exp-001", "exp-002"]

        def _summary_side_effect(eid):
            if eid == "exp-001":
                return summary1
            return summary2

        mock_artifact_manager.experiment_summary.side_effect = _summary_side_effect

        response = client.get(
            "/api/v1/experiments/compare"
            "?experiment_id_1=exp-001&experiment_id_2=exp-002"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment_1"]["experiment_id"] == "exp-001"
        assert data["experiment_2"]["experiment_id"] == "exp-002"
        # metric_diffs = exp2 - exp1
        assert data["metric_diffs"]["accuracy"] == pytest.approx(0.01)
        assert data["metric_diffs"]["val_loss"] == pytest.approx(-0.02)

    def test_compare_not_found(self, client, mock_artifact_manager):
        """Test comparison with non-existent experiment."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]

        response = client.get(
            "/api/v1/experiments/compare"
            "?experiment_id_1=exp-001&experiment_id_2=exp-missing"
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/experiments/{experiment_id}/rollback
# ---------------------------------------------------------------------------


class TestRollbackExperiment:
    """Tests for experiment rollback."""

    def test_rollback_to_best_checkpoint(
        self, client, mock_artifact_manager, sample_checkpoints
    ):
        """Test rollback to best checkpoint (default)."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]
        mock_artifact_manager.get_best_checkpoint.return_value = sample_checkpoints[1]

        response = client.post("/api/v1/experiments/exp-001/rollback")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["experiment_id"] == "exp-001"
        assert data["rolled_back_to"] == "ckpt-002"
        assert "epoch 10" in data["message"]

    def test_rollback_to_specific_epoch(
        self, client, mock_artifact_manager, sample_checkpoints
    ):
        """Test rollback to a specific epoch."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]
        mock_artifact_manager.get_checkpoints.return_value = sample_checkpoints

        response = client.post(
            "/api/v1/experiments/exp-001/rollback?target_checkpoint_epoch=5"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["rolled_back_to"] == "ckpt-001"
        assert "epoch 5" in data["message"]

    def test_rollback_experiment_not_found(self, client, mock_artifact_manager):
        """Test rollback with non-existent experiment."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]

        response = client.post("/api/v1/experiments/exp-999/rollback")

        assert response.status_code == 404

    def test_rollback_no_checkpoints(self, client, mock_artifact_manager):
        """Test rollback when experiment has no checkpoints."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]
        mock_artifact_manager.get_best_checkpoint.return_value = None
        mock_artifact_manager.get_checkpoints.return_value = []

        response = client.post("/api/v1/experiments/exp-001/rollback")

        assert response.status_code == 400
        assert "no checkpoints" in response.json()["detail"].lower()

    def test_rollback_invalid_epoch(
        self, client, mock_artifact_manager, sample_checkpoints
    ):
        """Test rollback with non-existent epoch."""
        mock_artifact_manager.list_experiments.return_value = ["exp-001"]
        mock_artifact_manager.get_checkpoints.return_value = sample_checkpoints

        response = client.post(
            "/api/v1/experiments/exp-001/rollback?target_checkpoint_epoch=99"
        )

        assert response.status_code == 400
        assert "epoch 99" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Services not initialized
# ---------------------------------------------------------------------------


class TestServicesNotInitialized:
    """Tests for when services are not initialized."""

    def test_list_without_services(self, client):
        """Test listing without initialized services."""
        from api import experiments as exp_mod

        original = exp_mod._artifact_manager
        exp_mod._artifact_manager = None

        try:
            response = client.get("/api/v1/experiments")
            assert response.status_code == 503
        finally:
            exp_mod._artifact_manager = original

    def test_get_experiment_without_services(self, client):
        """Test getting experiment without initialized services."""
        from api import experiments as exp_mod

        original = exp_mod._artifact_manager
        exp_mod._artifact_manager = None

        try:
            response = client.get("/api/v1/experiments/exp-001")
            assert response.status_code == 503
        finally:
            exp_mod._artifact_manager = original
