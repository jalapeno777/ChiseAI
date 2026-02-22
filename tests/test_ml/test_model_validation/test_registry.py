"""Tests for model registry."""

from datetime import UTC, datetime

import pytest

from ml.model_registry.registry import (
    ModelRegistry,
    ModelStatus,
    ModelType,
    ModelVersion,
    PromotionCriteria,
)


class TestModelVersion:
    """Tests for ModelVersion dataclass."""

    def test_model_version_creation(self):
        """Test creating a model version."""
        version = ModelVersion(
            version_id="test_v1_20260222_120000",
            model_id="test_model",
            model_type=ModelType.SIGNAL_PREDICTOR,
            status=ModelStatus.DRAFT,
            model_path="/models/test_v1.pkl",
            metrics={"accuracy": 0.85},
        )

        assert version.version_id == "test_v1_20260222_120000"
        assert version.model_id == "test_model"
        assert version.status == ModelStatus.DRAFT
        assert version.metrics["accuracy"] == 0.85

    def test_model_version_to_dict(self):
        """Test converting model version to dict."""
        version = ModelVersion(
            version_id="test_v1",
            model_id="test_model",
            model_type=ModelType.SIGNAL_PREDICTOR,
            status=ModelStatus.CHAMPION,
            model_path="/models/test.pkl",
            metrics={"f1": 0.82},
        )

        data = version.to_dict()
        assert data["version_id"] == "test_v1"
        assert data["status"] == "champion"
        assert data["model_type"] == "signal_predictor"

    def test_model_version_from_dict(self):
        """Test creating model version from dict."""
        data = {
            "version_id": "test_v1",
            "model_id": "test_model",
            "model_type": "signal_predictor",
            "status": "champion",
            "model_path": "/models/test.pkl",
            "metrics": {"f1": 0.82},
            "created_at": datetime.now(UTC).isoformat(),
            "promoted_at": None,
            "metadata": {},
        }

        version = ModelVersion.from_dict(data)
        assert version.version_id == "test_v1"
        assert version.status == ModelStatus.CHAMPION


class TestPromotionCriteria:
    """Tests for PromotionCriteria."""

    def test_default_criteria(self):
        """Test default promotion criteria."""
        criteria = PromotionCriteria()

        assert criteria.min_accuracy == 0.75
        assert criteria.min_precision == 0.70
        assert criteria.min_recall == 0.70
        assert criteria.min_f1 == 0.72
        assert criteria.max_ece == 0.15
        assert criteria.require_human_approval is True

    def test_evaluate_passes_all_thresholds(self):
        """Test evaluation when all thresholds are met."""
        criteria = PromotionCriteria()
        metrics = {
            "accuracy": 0.80,
            "precision": 0.75,
            "recall": 0.75,
            "f1": 0.76,
            "ece": 0.10,
        }

        passes, failures = criteria.evaluate(metrics)
        assert passes is True
        assert len(failures) == 0

    def test_evaluate_fails_accuracy(self):
        """Test evaluation when accuracy is too low."""
        criteria = PromotionCriteria()
        metrics = {
            "accuracy": 0.70,  # Below 0.75
            "precision": 0.75,
            "recall": 0.75,
            "f1": 0.76,
            "ece": 0.10,
        }

        passes, failures = criteria.evaluate(metrics)
        assert passes is False
        assert any("accuracy" in f for f in failures)

    def test_evaluate_fails_ece(self):
        """Test evaluation when ECE is too high."""
        criteria = PromotionCriteria()
        metrics = {
            "accuracy": 0.80,
            "precision": 0.75,
            "recall": 0.75,
            "f1": 0.76,
            "ece": 0.20,  # Above 0.15
        }

        passes, failures = criteria.evaluate(metrics)
        assert passes is False
        assert any("ece" in f for f in failures)

    def test_evaluate_outperformance_required(self):
        """Test evaluation with outperformance requirement."""
        criteria = PromotionCriteria(
            require_outperformance=True,
            outperformance_margin_pct=5.0,
        )

        # Candidate worse than champion
        metrics = {"f1": 0.75}
        champion_metrics = {"f1": 0.80}

        passes, failures = criteria.evaluate(metrics, champion_metrics)
        assert passes is False
        assert any("outperform" in f.lower() for f in failures)

    def test_evaluate_outperformance_passes(self):
        """Test evaluation when candidate outperforms champion."""
        criteria = PromotionCriteria(
            require_outperformance=True,
            outperformance_margin_pct=5.0,
        )

        # Candidate better than champion by >5% (0.80 * 1.05 = 0.84, so 0.85 > 0.84)
        metrics = {
            "f1": 0.85,
            "accuracy": 0.80,
            "precision": 0.78,
            "recall": 0.76,
            "ece": 0.10,
        }
        champion_metrics = {"f1": 0.80}

        passes, failures = criteria.evaluate(metrics, champion_metrics)
        assert passes is True


class TestModelRegistry:
    """Tests for ModelRegistry."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return ModelRegistry()

    def test_register_model(self, registry):
        """Test registering a new model."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics={"accuracy": 0.85},
        )

        assert version.model_id == "test_model"
        assert version.status == ModelStatus.DRAFT
        assert version.model_type == ModelType.SIGNAL_PREDICTOR

    def test_get_version(self, registry):
        """Test retrieving a version."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        retrieved = registry.get_version(version.version_id)
        assert retrieved is not None
        assert retrieved.version_id == version.version_id

    def test_get_version_not_found(self, registry):
        """Test retrieving a non-existent version."""
        retrieved = registry.get_version("nonexistent")
        assert retrieved is None

    def test_promote_to_candidate(self, registry):
        """Test promoting to candidate status."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        promoted = registry.promote_to_candidate(version.version_id)
        assert promoted.status == ModelStatus.CANDIDATE
        assert promoted.promoted_at is not None

    def test_promote_to_challenger(self, registry):
        """Test promoting to challenger status."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        registry.promote_to_candidate(version.version_id)
        promoted = registry.promote_to_challenger(version.version_id)

        assert promoted.status == ModelStatus.CHALLENGER

        # Check challenger list
        challengers = registry.get_challengers(ModelType.SIGNAL_PREDICTOR)
        assert len(challengers) == 1
        assert challengers[0].version_id == version.version_id

    def test_promote_to_champion(self, registry):
        """Test promoting to champion status."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
            metrics={
                "accuracy": 0.85,
                "precision": 0.82,
                "recall": 0.80,
                "f1": 0.81,
                "ece": 0.10,
            },
        )

        registry.promote_to_candidate(version.version_id)
        registry.promote_to_challenger(version.version_id)

        new_champion, old_champion = registry.promote_to_champion(
            version.version_id, force=True
        )

        assert new_champion.status == ModelStatus.CHAMPION
        assert (
            registry.get_champion(ModelType.SIGNAL_PREDICTOR).version_id
            == version.version_id
        )

    def test_promote_to_champion_demotes_old(self, registry):
        """Test that promoting champion demotes old champion."""
        # Create first champion
        v1 = registry.register_model(
            model_id="test_model",
            model_path="/models/v1.pkl",
            metrics={"f1": 0.80},
        )
        registry.promote_to_candidate(v1.version_id)
        registry.promote_to_challenger(v1.version_id)
        registry.promote_to_champion(v1.version_id, force=True)

        # Create second champion
        v2 = registry.register_model(
            model_id="test_model",
            model_path="/models/v2.pkl",
            metrics={"f1": 0.85},
        )
        registry.promote_to_candidate(v2.version_id)
        registry.promote_to_challenger(v2.version_id)
        new_champ, old_champ = registry.promote_to_champion(v2.version_id, force=True)

        assert new_champ.status == ModelStatus.CHAMPION
        assert old_champ.status == ModelStatus.DEPRECATED
        assert old_champ.version_id == v1.version_id

    def test_promote_to_champion_fails_criteria(self, registry):
        """Test that promotion fails when criteria not met."""
        criteria = PromotionCriteria(min_f1=0.90)  # Very high threshold
        registry = ModelRegistry(promotion_criteria=criteria)

        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
            metrics={"f1": 0.80},  # Below threshold
        )

        registry.promote_to_candidate(version.version_id)
        registry.promote_to_challenger(version.version_id)

        with pytest.raises(ValueError, match="Promotion criteria not met"):
            registry.promote_to_champion(version.version_id)

    def test_mark_failed(self, registry):
        """Test marking a version as failed."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        failed = registry.mark_failed(version.version_id, "Test failure")
        assert failed.status == ModelStatus.FAILED
        assert failed.metadata["failure_reason"] == "Test failure"

    def test_get_rollback_target(self, registry):
        """Test getting rollback target."""
        # Create and deprecate a champion
        v1 = registry.register_model(
            model_id="test_model",
            model_path="/models/v1.pkl",
            metrics={"f1": 0.80},
        )
        registry.promote_to_candidate(v1.version_id)
        registry.promote_to_challenger(v1.version_id)
        registry.promote_to_champion(v1.version_id, force=True)

        # Create new champion (demotes v1)
        v2 = registry.register_model(
            model_id="test_model",
            model_path="/models/v2.pkl",
            metrics={"f1": 0.85},
        )
        registry.promote_to_candidate(v2.version_id)
        registry.promote_to_challenger(v2.version_id)
        registry.promote_to_champion(v2.version_id, force=True)

        # v1 should be rollback target
        target = registry.get_rollback_target(ModelType.SIGNAL_PREDICTOR)
        assert target is not None
        assert target.version_id == v1.version_id
        assert target.status == ModelStatus.DEPRECATED

    def test_list_versions(self, registry):
        """Test listing versions."""
        registry.register_model(model_id="model1", model_path="/models/m1.pkl")
        registry.register_model(model_id="model2", model_path="/models/m2.pkl")

        versions = registry.list_versions()
        assert len(versions) == 2

    def test_list_versions_by_status(self, registry):
        """Test listing versions filtered by status."""
        v1 = registry.register_model(model_id="model1", model_path="/models/m1.pkl")
        v2 = registry.register_model(model_id="model2", model_path="/models/m2.pkl")

        registry.promote_to_candidate(v1.version_id)

        candidates = registry.list_versions(status=ModelStatus.CANDIDATE)
        assert len(candidates) == 1
        assert candidates[0].version_id == v1.version_id

    def test_update_metrics(self, registry):
        """Test updating version metrics."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
            metrics={"accuracy": 0.80},
        )

        updated = registry.update_metrics(
            version.version_id, {"accuracy": 0.85, "f1": 0.82}
        )
        assert updated.metrics["accuracy"] == 0.85
        assert updated.metrics["f1"] == 0.82
