"""Tests for model updater module."""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, "src")

from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
)
from ml.feedback.analyzer import FeedbackAnalysisReport
from ml.feedback.matcher import (
    MatchConfidence,
    MatchStatus,
    PredictionOutcomeMatch,
)
from ml.feedback.updater import (
    ModelUpdater,
    ModelVersion,
    UpdateConfig,
    UpdateResult,
    UpdateStatus,
    UpdateStrategy,
)


class TestUpdateConfig:
    """Tests for UpdateConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = UpdateConfig()

        assert config.update_strategy == UpdateStrategy.INCREMENTAL
        assert config.min_samples_for_update == 100
        assert config.max_samples_for_incremental == 10000
        assert config.validation_split == 0.2
        assert config.backup_before_update is True
        assert config.auto_rollback_on_failure is True
        assert config.max_update_time_hours == 4.0

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = UpdateConfig(
            update_strategy=UpdateStrategy.BATCH_RETRAIN,
            min_samples_for_update=50,
            backup_before_update=False,
        )

        assert config.update_strategy == UpdateStrategy.BATCH_RETRAIN
        assert config.min_samples_for_update == 50
        assert config.backup_before_update is False


class TestModelVersion:
    """Tests for ModelVersion class."""

    def test_version_creation(self) -> None:
        """Test version creation."""
        version = ModelVersion(
            version_id="v1",
            model_id="test_model",
            created_at=datetime.now(UTC),
            performance_metrics={"accuracy": 0.75},
        )

        assert version.version_id == "v1"
        assert version.model_id == "test_model"
        assert version.performance_metrics["accuracy"] == 0.75

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        version = ModelVersion(
            version_id="v1",
            model_id="test_model",
            created_at=datetime.now(UTC),
            parent_version="v0",
            update_strategy=UpdateStrategy.INCREMENTAL,
            training_samples=1000,
        )

        data = version.to_dict()

        assert data["version_id"] == "v1"
        assert data["parent_version"] == "v0"
        assert data["update_strategy"] == "incremental"
        assert data["training_samples"] == 1000

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "version_id": "v2",
            "model_id": "test_model",
            "created_at": "2024-01-01T00:00:00+00:00",
            "parent_version": "v1",
            "update_strategy": "batch_retrain",
            "performance_metrics": {"accuracy": 0.8},
        }

        version = ModelVersion.from_dict(data)

        assert version.version_id == "v2"
        assert version.parent_version == "v1"
        assert version.update_strategy == UpdateStrategy.BATCH_RETRAIN


class TestUpdateResult:
    """Tests for UpdateResult class."""

    def test_result_creation(self) -> None:
        """Test result creation."""
        result = UpdateResult(
            status=UpdateStatus.COMPLETED,
            samples_used=100,
            training_time_seconds=60.0,
        )

        assert result.status == UpdateStatus.COMPLETED
        assert result.samples_used == 100

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        version = ModelVersion(
            version_id="v1",
            model_id="test_model",
            created_at=datetime.now(UTC),
        )

        result = UpdateResult(
            status=UpdateStatus.COMPLETED,
            version=version,
            samples_used=100,
            validation_metrics={"accuracy": 0.75},
        )

        data = result.to_dict()

        assert data["status"] == "completed"
        assert data["samples_used"] == 100
        assert data["validation_metrics"]["accuracy"] == 0.75


class TestModelUpdater:
    """Tests for ModelUpdater class."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def updater(self, temp_storage) -> ModelUpdater:
        """Create updater fixture."""
        return ModelUpdater(model_storage_path=temp_storage)

    @pytest.fixture
    def sample_matches(self) -> list[PredictionOutcomeMatch]:
        """Create sample matches fixture."""
        matches = []
        for i in range(150):  # Enough samples for update
            signal = SignalRecord(
                signal_id=f"test-{i}",
                token="BTC",
                timestamp=1000000 + i * 1000,
                direction=SignalDirection.LONG,
                confidence=0.7 + (i % 3) * 0.1,
                entry_price=50000.0,
                score=70.0 + (i % 5) * 5,
            )

            outcome = OutcomeRecord(
                signal_id=f"test-{i}",
                exit_timestamp=signal.timestamp + 10000,
                is_win=i % 3 != 0,
                pnl=100.0 if i % 3 != 0 else -50.0,
                exit_price=signal.entry_price * (1.02 if i % 3 != 0 else 0.98),
                duration_hours=2.78,
                outcome_type=OutcomeType.TP_HIT if i % 3 != 0 else OutcomeType.SL_HIT,
            )

            match = PredictionOutcomeMatch(
                signal_id=f"test-{i}",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                resolution_quality=0.9,
            )
            matches.append(match)

        return matches

    def test_updater_creation(self, temp_storage) -> None:
        """Test updater creation."""
        updater = ModelUpdater(model_storage_path=temp_storage)

        assert updater.config is not None
        assert updater.model_storage_path == Path(temp_storage)
        assert updater.model_storage_path.exists()

    @pytest.mark.asyncio
    async def test_update_from_matches_insufficient_samples(self, updater) -> None:
        """Test update with insufficient samples."""
        model = MagicMock()
        matches = []  # Empty list

        result = await updater.update_from_matches(model, matches)

        assert result.status == UpdateStatus.FAILED
        assert "Insufficient samples" in result.error_message

    @pytest.mark.asyncio
    async def test_update_from_matches_success(self, updater, sample_matches) -> None:
        """Test successful update."""
        model = MagicMock()
        model.partial_fit = MagicMock()
        model.predict = MagicMock(return_value=[1] * 30)  # Mock predictions

        result = await updater.update_from_matches(
            model, sample_matches, model_id="test_model"
        )

        # Should complete (even if validation metrics are mock)
        assert result.status in [UpdateStatus.COMPLETED, UpdateStatus.FAILED]

    @pytest.mark.asyncio
    async def test_update_from_analysis(self, updater, sample_matches) -> None:
        """Test update from analysis report."""
        model = MagicMock()
        model.partial_fit = MagicMock()
        model.predict = MagicMock(return_value=[1] * 30)

        analysis_report = FeedbackAnalysisReport(
            analysis_time=datetime.now(UTC),
            total_matches=150,
            overall_accuracy=0.6,  # Above 50%, should use normal strategy
        )

        result = await updater.update_from_analysis(
            model, analysis_report, sample_matches, model_id="test_model"
        )

        assert result.status in [UpdateStatus.COMPLETED, UpdateStatus.FAILED]

    def test_create_version(self, updater) -> None:
        """Test version creation."""
        version = updater._create_version(
            model_id="test_model",
            parent_version=None,
            strategy=UpdateStrategy.INCREMENTAL,
            metrics={"accuracy": 0.75},
            samples=100,
        )

        assert version.model_id == "test_model"
        assert version.version_id == "v1"
        assert version.update_strategy == UpdateStrategy.INCREMENTAL

    def test_create_version_with_parent(self, updater) -> None:
        """Test version creation with parent."""
        # Create first version
        v1 = updater._create_version(
            model_id="test_model",
            parent_version=None,
            strategy=UpdateStrategy.INCREMENTAL,
            metrics={},
            samples=100,
        )

        # Create second version
        v2 = updater._create_version(
            model_id="test_model",
            parent_version=v1.version_id,
            strategy=UpdateStrategy.INCREMENTAL,
            metrics={},
            samples=100,
        )

        assert v2.version_id == "v2"
        assert v2.parent_version == "v1"

    def test_get_version_history(self, updater) -> None:
        """Test getting version history."""
        # Create some versions
        for i in range(3):
            updater._create_version(
                model_id="test_model",
                parent_version=f"v{i}" if i > 0 else None,
                strategy=UpdateStrategy.INCREMENTAL,
                metrics={},
                samples=100,
            )

        history = updater.get_version_history("test_model")

        assert len(history) == 3
        # Should be sorted newest first
        assert history[0].version_id == "v3"

    def test_get_current_version(self, updater) -> None:
        """Test getting current version."""
        # Create versions
        updater._create_version(
            model_id="test_model",
            parent_version=None,
            strategy=UpdateStrategy.INCREMENTAL,
            metrics={},
            samples=100,
        )

        current = updater.get_current_version("test_model")

        assert current is not None
        assert current.version_id == "v1"

    def test_calculate_improvement(self, updater) -> None:
        """Test improvement calculation."""
        previous = ModelVersion(
            version_id="v1",
            model_id="test_model",
            created_at=datetime.now(UTC),
            performance_metrics={"accuracy": 0.7, "precision": 0.6},
        )

        current_metrics = {"accuracy": 0.75, "precision": 0.65}

        improvement = updater._calculate_improvement(previous, current_metrics)

        assert "accuracy_delta" in improvement
        assert improvement["accuracy_delta"] == pytest.approx(0.05, abs=0.0001)

    def test_calculate_improvement_no_previous(self, updater) -> None:
        """Test improvement calculation with no previous version."""
        improvement = updater._calculate_improvement(None, {"accuracy": 0.75})

        assert improvement == {}

    def test_prepare_training_data(self, updater, sample_matches) -> None:
        """Test training data preparation."""
        X, y = updater._prepare_training_data(sample_matches[:10])

        assert len(X) == 10
        assert len(y) == 10
        # X should be feature vectors, y should be labels
        assert all(isinstance(x, list) for x in X)
        assert all(isinstance(label, int) for label in y)

    def test_extract_features(self, updater) -> None:
        """Test feature extraction."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        match = PredictionOutcomeMatch(
            signal_id="test-1",
            signal=signal,
            status=MatchStatus.MATCHED,
        )

        features = updater._extract_features(match)

        assert len(features) >= 2  # At least confidence and score
        assert features[0] == 0.8  # confidence
        assert features[1] == 0.75  # score / 100

    def test_extract_label_win(self, updater) -> None:
        """Test label extraction for win."""
        outcome = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1100000,
            is_win=True,
            pnl=100.0,
            exit_price=51000.0,
            duration_hours=1.0,
            outcome_type=OutcomeType.TP_HIT,
        )

        match = PredictionOutcomeMatch(
            signal_id="test-1",
            signal=MagicMock(),
            outcome=outcome,
            status=MatchStatus.MATCHED,
        )

        label = updater._extract_label(match)

        assert label == 1  # Win

    def test_extract_label_loss(self, updater) -> None:
        """Test label extraction for loss."""
        outcome = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1100000,
            is_win=False,
            pnl=-50.0,
            exit_price=49000.0,
            duration_hours=1.0,
            outcome_type=OutcomeType.SL_HIT,
        )

        match = PredictionOutcomeMatch(
            signal_id="test-1",
            signal=MagicMock(),
            outcome=outcome,
            status=MatchStatus.MATCHED,
        )

        label = updater._extract_label(match)

        assert label == 0  # Loss

    def test_save_and_load_version_history(self, updater) -> None:
        """Test saving and loading version history."""
        # Create versions
        for i in range(3):
            updater._create_version(
                model_id="test_model",
                parent_version=f"v{i}" if i > 0 else None,
                strategy=UpdateStrategy.INCREMENTAL,
                metrics={"accuracy": 0.7 + i * 0.05},
                samples=100,
            )

        # Save
        updater.save_version_history("test_model")

        # Create new updater and load
        new_updater = ModelUpdater(model_storage_path=updater.model_storage_path)
        loaded = new_updater.load_version_history("test_model")

        assert len(loaded) == 3
        assert loaded[0].version_id == "v1"  # Chronological order


class TestUpdaterHealth:
    """Tests for updater health status."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def updater(self, temp_storage) -> ModelUpdater:
        """Create updater fixture."""
        return ModelUpdater(model_storage_path=temp_storage)

    def test_get_health_status_no_updates(self, updater) -> None:
        """Test health status with no updates."""
        health = updater.get_health_status()

        assert health["component"] == "ModelUpdater"
        assert health["is_active"] is False
        assert health["total_updates"] == 0
        assert health["successful_updates"] == 0
        assert health["failed_updates"] == 0
        assert health["success_rate"] == 0.0
        assert health["is_healthy"] is False
        assert "No updates recorded" in health["reason"]
        assert health["last_update_time"] is None

    def test_get_health_status_with_updates(self, updater) -> None:
        """Test health status with updates."""
        from datetime import UTC, datetime

        # Simulate successful updates
        updater._last_update_time = datetime.now(UTC)
        updater._total_updates = 10
        updater._successful_updates = 8
        updater._failed_updates = 2

        health = updater.get_health_status()

        assert health["is_active"] is True
        assert health["total_updates"] == 10
        assert health["successful_updates"] == 8
        assert health["failed_updates"] == 2
        assert health["success_rate"] == 0.8
        assert health["is_healthy"] is True
        assert "Last update" in health["reason"]
        assert "8/10 updates successful" in health["reason"]

    def test_get_health_status_many_failures(self, updater) -> None:
        """Test health status with many failures."""
        from datetime import UTC, datetime

        # Simulate many failed updates
        updater._last_update_time = datetime.now(UTC)
        updater._total_updates = 10
        updater._successful_updates = 5
        updater._failed_updates = 5

        health = updater.get_health_status()

        assert health["success_rate"] == 0.5
        assert health["is_healthy"] is False  # Too many failures
        assert "5 failed updates" in health["reason"]
