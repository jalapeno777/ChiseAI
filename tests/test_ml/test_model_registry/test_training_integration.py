"""Tests for model registry training integration."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from ml.model_registry.artifact_linker import ArtifactLinker, TrainingArtifact
from ml.model_registry.registry import ModelRegistry, ModelStatus, ModelVersion
from ml.model_registry.training_integration import (
    TrainingConfig,
    TrainingIntegration,
)


class TestTrainingArtifact:
    """Test TrainingArtifact dataclass."""

    def test_training_artifact_creation(self):
        """Test creating a TrainingArtifact."""
        artifact = TrainingArtifact(
            model_path="/models/test_model.pkl",
            metrics={"accuracy": 0.95, "loss": 0.05},
            hyperparameters={"learning_rate": 0.001, "epochs": 100},
            training_metadata={"dataset": "test_data", "trained_at": "2024-01-01"},
        )

        assert artifact.model_path == "/models/test_model.pkl"
        assert artifact.metrics["accuracy"] == 0.95
        assert artifact.hyperparameters["learning_rate"] == 0.001

    def test_training_artifact_to_dict(self):
        """Test converting TrainingArtifact to dict."""
        artifact = TrainingArtifact(
            model_path="/models/test_model.pkl",
            metrics={"accuracy": 0.95},
            hyperparameters={"lr": 0.001},
            training_metadata={"dataset": "test"},
            validation_results={"val_accuracy": 0.93},
        )

        result = artifact.to_dict()
        assert result["model_path"] == "/models/test_model.pkl"
        assert result["metrics"]["accuracy"] == 0.95
        assert result["validation_results"]["val_accuracy"] == 0.93


class TestArtifactLinker:
    """Test ArtifactLinker functionality."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock model registry."""
        registry = Mock(spec=ModelRegistry)
        return registry

    @pytest.fixture
    def linker(self, mock_registry):
        """Create an ArtifactLinker instance."""
        return ArtifactLinker(mock_registry)

    @pytest.fixture
    def sample_artifact(self):
        """Create a sample training artifact."""
        return TrainingArtifact(
            model_path="/models/grid_btc_1h_v2.pkl",
            metrics={"accuracy": 0.85, "precision": 0.82},
            hyperparameters={"learning_rate": 0.001, "epochs": 100},
            training_metadata={
                "dataset": "btc_1h_2024",
                "trained_at": "2024-01-15T10:00:00",
            },
        )

    def test_link_training_run(self, linker, mock_registry, sample_artifact):
        """Test linking a training run to registry."""
        # Setup mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.version_id = "v1"
        mock_registry.register_model.return_value = mock_version

        # Execute
        result = linker.link_training_run(
            "grid_btc_1h", sample_artifact, tags=["training-run"]
        )

        # Verify
        assert result.version_id == "v1"
        mock_registry.register_model.assert_called_once()
        call_args = mock_registry.register_model.call_args
        assert call_args.kwargs["model_id"] == "grid_btc_1h"
        assert call_args.kwargs["metadata"]["linked_artifact"] is True

    def test_update_with_validation(self, linker, mock_registry):
        """Test updating model with validation results.

        Note: ModelRegistry doesn't support metadata updates after registration,
        so this method verifies the version exists and returns it.
        """
        # Setup mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.metadata = {}
        mock_registry.get_version.return_value = mock_version

        # Execute
        validation_results = {"val_accuracy": 0.88, "val_loss": 0.12}
        result = linker.update_with_validation("v1", validation_results)

        # Verify
        assert result == mock_version
        mock_registry.get_version.assert_called_once_with("v1")
        # update_metrics is not called since ModelRegistry doesn't support metadata updates

    def test_update_with_validation_not_found(self, linker, mock_registry):
        """Test updating non-existent version."""
        mock_registry.get_version.return_value = None

        with pytest.raises(ValueError, match="Version v999 not found"):
            linker.update_with_validation("v999", {})

    def test_get_training_lineage(self, linker, mock_registry):
        """Test getting training lineage."""
        # Setup mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.model_id = "test_model"
        mock_version.version_id = "v1"
        mock_version.status = ModelStatus.DRAFT
        mock_version.model_path = "/models/test.pkl"
        mock_version.metrics = {"accuracy": 0.9}
        mock_version.metadata = {"linked_artifact": True}
        mock_version.created_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_registry.get_version.return_value = mock_version

        # Execute
        lineage = linker.get_training_lineage("v1")

        # Verify
        assert lineage["model_id"] == "test_model"
        assert lineage["version_id"] == "v1"
        assert lineage["training_artifact"] is True


class TestTrainingConfig:
    """Test TrainingConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = TrainingConfig()

        assert config.auto_register is True
        assert config.auto_promote_to_challenger is False
        assert config.validation_threshold == 0.0
        assert config.required_metrics == []
        assert config.tags == []

    def test_custom_config(self):
        """Test custom configuration."""
        config = TrainingConfig(
            auto_register=False,
            auto_promote_to_challenger=True,
            validation_threshold=0.85,
            required_metrics=["accuracy", "precision"],
            tags=["production", "grid-trading"],
        )

        assert config.auto_register is False
        assert config.auto_promote_to_challenger is True
        assert config.validation_threshold == 0.85
        assert "accuracy" in config.required_metrics
        assert "production" in config.tags


class TestTrainingIntegration:
    """Test TrainingIntegration functionality."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock model registry."""
        registry = Mock(spec=ModelRegistry)
        return registry

    @pytest.fixture
    def integration(self, mock_registry):
        """Create a TrainingIntegration instance."""
        config = TrainingConfig(
            auto_register=True,
            auto_promote_to_challenger=False,
            validation_threshold=0.8,
            required_metrics=["accuracy"],
            tags=["training-run"],
        )
        return TrainingIntegration(mock_registry, config)

    @pytest.fixture
    def sample_training_data(self):
        """Create sample training data."""
        return {
            "model_id": "grid_btc_1h_v2",
            "model_path": "/models/grid_btc_1h_v2.pkl",
            "metrics": {"accuracy": 0.85, "precision": 0.82},
            "hyperparameters": {"learning_rate": 0.001, "epochs": 100},
            "training_metadata": {"dataset": "btc_1h_2024"},
        }

    def test_on_training_complete_success(
        self, integration, mock_registry, sample_training_data
    ):
        """Test successful training completion."""
        # Setup mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.version_id = "v1"
        mock_registry.register_model.return_value = mock_version

        # Execute
        version_id = integration.on_training_complete(**sample_training_data)

        # Verify
        assert version_id == "v1"
        mock_registry.register_model.assert_called_once()

    def test_on_training_complete_missing_metrics(
        self, integration, mock_registry, sample_training_data
    ):
        """Test training completion with missing required metrics."""
        # Remove required metric
        sample_training_data["metrics"] = {"precision": 0.82}  # Missing "accuracy"

        # Execute
        version_id = integration.on_training_complete(**sample_training_data)

        # Verify
        assert version_id is None
        mock_registry.register_model.assert_not_called()

    def test_on_training_complete_validation_threshold_fail(
        self, integration, mock_registry, sample_training_data
    ):
        """Test training completion failing validation threshold."""
        # Set metrics below threshold
        sample_training_data["metrics"] = {"accuracy": 0.6}  # Below 0.8 threshold

        # Execute
        version_id = integration.on_training_complete(**sample_training_data)

        # Verify
        assert version_id is None
        mock_registry.register_model.assert_not_called()

    def test_on_training_complete_auto_promote(
        self, integration, mock_registry, sample_training_data
    ):
        """Test auto-promotion to challenger."""
        # Enable auto-promotion
        integration.config.auto_promote_to_challenger = True

        # Setup mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.version_id = "v1"
        mock_registry.register_model.return_value = mock_version

        # Execute
        version_id = integration.on_training_complete(**sample_training_data)

        # Verify
        assert version_id == "v1"
        mock_registry.promote_to_challenger.assert_called_once_with("v1")

    def test_validate_and_promote_success(self, integration, mock_registry):
        """Test successful validation and promotion."""
        # Setup mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.metadata = {}
        mock_registry.get_version.return_value = mock_version
        mock_registry.update_metrics.return_value = mock_version

        # Execute
        validation_metrics = {"val_accuracy": 0.88}
        promotion_criteria = {"val_accuracy": 0.85}
        result = integration.validate_and_promote(
            "v1", validation_metrics, promotion_criteria
        )

        # Verify
        assert result is True
        mock_registry.promote_to_challenger.assert_called_once_with("v1")

    def test_validate_and_promote_criteria_not_met(self, integration, mock_registry):
        """Test validation where promotion criteria not met."""
        # Setup mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.metadata = {}
        mock_registry.get_version.return_value = mock_version
        mock_registry.update_metrics.return_value = mock_version

        # Execute
        validation_metrics = {"val_accuracy": 0.80}
        promotion_criteria = {"val_accuracy": 0.85}
        result = integration.validate_and_promote(
            "v1", validation_metrics, promotion_criteria
        )

        # Verify
        assert result is False
        mock_registry.promote_to_challenger.assert_not_called()

    def test_get_training_summary(self, integration, mock_registry):
        """Test getting training summary."""
        # Setup mock
        mock_version1 = Mock(spec=ModelVersion)
        mock_version1.version_id = "v1"
        mock_version1.model_id = "test_model"
        mock_version1.created_at = datetime(2024, 1, 1)

        mock_version2 = Mock(spec=ModelVersion)
        mock_version2.version_id = "v2"
        mock_version2.model_id = "test_model"
        mock_version2.created_at = datetime(2024, 1, 2)

        mock_registry.list_versions.return_value = [mock_version1, mock_version2]

        # Execute
        summary = integration.get_training_summary("test_model")

        # Verify
        assert summary["model_id"] == "test_model"
        assert summary["total_versions"] == 2
        assert len(summary["training_runs"]) == 2

    def test_cleanup_old_versions(self, integration, mock_registry):
        """Test cleaning up old versions.

        Note: ModelRegistry doesn't support deletion, so this test
        verifies that the cleanup logic identifies which versions
        would be candidates for cleanup without actually deleting them.
        """
        # Setup mock versions
        versions = []
        for i in range(10):
            version = Mock(spec=ModelVersion)
            version.version_id = f"v{i}"
            version.created_at = datetime(2024, 1, i + 1)
            versions.append(version)

        mock_registry.list_versions.return_value = versions

        # Execute
        candidates_for_cleanup = integration.cleanup_old_versions(
            "test_model", keep_last_n=5
        )

        # Verify - should identify 5 oldest versions as cleanup candidates
        assert len(candidates_for_cleanup) == 5
        assert "v0" in candidates_for_cleanup
        assert "v4" in candidates_for_cleanup
        assert "v5" not in candidates_for_cleanup  # Should keep v5-v9
        assert "v9" not in candidates_for_cleanup

    def test_callback_invocation(
        self, integration, mock_registry, sample_training_data
    ):
        """Test callback invocation on training complete."""
        # Setup mock callback
        mock_callback = Mock()
        integration.register_callback(mock_callback)

        # Setup registry mock
        mock_version = Mock(spec=ModelVersion)
        mock_version.version_id = "v1"
        mock_registry.register_model.return_value = mock_version

        # Execute
        integration.on_training_complete(**sample_training_data)

        # Verify callback was called
        mock_callback.on_training_complete.assert_called_once()
        call_args = mock_callback.on_training_complete.call_args
        assert call_args.kwargs["model_id"] == "grid_btc_1h_v2"


class TestTrainingIntegrationIntegration:
    """Integration tests for training integration."""

    def test_end_to_end_training_flow(self):
        """Test end-to-end training flow."""
        # This would be a more comprehensive integration test
        # For now, we'll test the key components work together

        # Create real registry (or mock)
        registry = Mock(spec=ModelRegistry)

        # Create integration
        config = TrainingConfig(
            auto_register=True,
            validation_threshold=0.7,
            required_metrics=["accuracy"],
        )
        integration = TrainingIntegration(registry, config)

        # Simulate training completion
        mock_version = Mock(spec=ModelVersion)
        mock_version.version_id = "v1"
        registry.register_model.return_value = mock_version

        version_id = integration.on_training_complete(
            model_id="test_model",
            model_path="/models/test.pkl",
            metrics={"accuracy": 0.85},
            hyperparameters={"lr": 0.001},
            training_metadata={"dataset": "test"},
        )

        assert version_id == "v1"
        registry.register_model.assert_called_once()
