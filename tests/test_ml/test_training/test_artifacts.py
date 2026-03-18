"""Tests for training artifact models, storage, and manager.

Covers:
- Dataclass serialization (to_dict, from_dict, to_json, from_json)
- ArtifactStorage CRUD operations
- ArtifactManager high-level operations
- Edge cases and error handling
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ml.training.artifacts.manager import ArtifactManager
from ml.training.artifacts.models import (
    ArtifactType,
    CheckpointArtifact,
    ConfigArtifact,
    LogArtifact,
    TrainingArtifact,
)
from ml.training.artifacts.storage import (
    ArtifactNotFoundError,
    ArtifactStorage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_base_artifact() -> TrainingArtifact:
    return TrainingArtifact(
        artifact_id="art-001",
        experiment_id="exp-001",
        created_at=datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC),
        metadata={"author": "test"},
    )


def _make_checkpoint() -> CheckpointArtifact:
    return CheckpointArtifact(
        artifact_id="ckpt-001",
        experiment_id="exp-001",
        created_at=datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC),
        checkpoint_path="/models/checkpoint.pt",
        epoch=10,
        metrics_snapshot={"val_loss": 0.05, "accuracy": 0.95},
        model_architecture="resnet50",
        file_size_bytes=1024000,
    )


def _make_config() -> ConfigArtifact:
    return ConfigArtifact(
        artifact_id="cfg-001",
        experiment_id="exp-001",
        created_at=datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC),
        hyperparameters={"lr": 0.001, "batch_size": 32, "epochs": 100},
        model_architecture="resnet50",
        data_config={"split": [0.7, 0.15, 0.15]},
        random_seed=42,
        framework="pytorch",
    )


def _make_log() -> LogArtifact:
    return LogArtifact(
        artifact_id="log-001",
        experiment_id="exp-001",
        created_at=datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC),
        metrics_history=[
            {"epoch": 1, "loss": 1.0, "val_loss": 0.9},
            {"epoch": 2, "loss": 0.5, "val_loss": 0.4},
        ],
        loss_curve=[{"epoch": 1, "loss": 1.0}, {"epoch": 2, "loss": 0.5}],
        val_loss_curve=[{"epoch": 1, "loss": 0.9}, {"epoch": 2, "loss": 0.4}],
        training_duration_seconds=3600.0,
        final_metrics={"val_loss": 0.4, "accuracy": 0.95},
        status="completed",
    )


# ===========================================================================
# TrainingArtifact model tests
# ===========================================================================


class TestTrainingArtifact:
    """Tests for the base TrainingArtifact dataclass."""

    def test_to_dict_contains_required_fields(self) -> None:
        artifact = _make_base_artifact()
        d = artifact.to_dict()
        assert d["artifact_id"] == "art-001"
        assert d["experiment_id"] == "exp-001"
        assert d["created_at"] == "2026-03-18T12:00:00+00:00"
        assert d["artifact_type"] == "log"
        assert d["metadata"] == {"author": "test"}

    def test_from_dict_roundtrip(self) -> None:
        original = _make_base_artifact()
        restored = TrainingArtifact.from_dict(original.to_dict())
        assert restored.artifact_id == original.artifact_id
        assert restored.experiment_id == original.experiment_id
        assert restored.created_at == original.created_at
        assert restored.artifact_type == original.artifact_type
        assert restored.metadata == original.metadata

    def test_to_json_valid(self) -> None:
        artifact = _make_base_artifact()
        json_str = artifact.to_json()
        parsed = json.loads(json_str)
        assert parsed["artifact_id"] == "art-001"

    def test_from_json_roundtrip(self) -> None:
        original = _make_base_artifact()
        restored = TrainingArtifact.from_json(original.to_json())
        assert restored.artifact_id == original.artifact_id
        assert restored.experiment_id == original.experiment_id

    def test_default_values(self) -> None:
        artifact = TrainingArtifact(
            artifact_id="x",
            experiment_id="y",
        )
        assert isinstance(artifact.created_at, datetime)
        assert artifact.artifact_type == ArtifactType.LOG
        assert artifact.metadata == {}


# ===========================================================================
# CheckpointArtifact model tests
# ===========================================================================


class TestCheckpointArtifact:
    """Tests for the CheckpointArtifact dataclass."""

    def test_artifact_type_is_checkpoint(self) -> None:
        ckpt = _make_checkpoint()
        assert ckpt.artifact_type == ArtifactType.CHECKPOINT

    def test_to_dict_roundtrip(self) -> None:
        original = _make_checkpoint()
        restored = CheckpointArtifact.from_dict(original.to_dict())
        assert restored.artifact_id == original.artifact_id
        assert restored.checkpoint_path == "/models/checkpoint.pt"
        assert restored.epoch == 10
        assert restored.metrics_snapshot == {"val_loss": 0.05, "accuracy": 0.95}
        assert restored.model_architecture == "resnet50"
        assert restored.file_size_bytes == 1024000

    def test_from_json_roundtrip(self) -> None:
        original = _make_checkpoint()
        restored = CheckpointArtifact.from_json(original.to_json())
        assert restored.epoch == original.epoch
        assert restored.metrics_snapshot == original.metrics_snapshot

    def test_post_init_sets_type(self) -> None:
        ckpt = CheckpointArtifact(
            artifact_id="c1",
            experiment_id="e1",
            artifact_type=ArtifactType.LOG,  # overridden by __post_init__
        )
        assert ckpt.artifact_type == ArtifactType.CHECKPOINT


# ===========================================================================
# ConfigArtifact model tests
# ===========================================================================


class TestConfigArtifact:
    """Tests for the ConfigArtifact dataclass."""

    def test_artifact_type_is_config(self) -> None:
        cfg = _make_config()
        assert cfg.artifact_type == ArtifactType.CONFIG

    def test_to_dict_roundtrip(self) -> None:
        original = _make_config()
        restored = ConfigArtifact.from_dict(original.to_dict())
        assert restored.hyperparameters == original.hyperparameters
        assert restored.model_architecture == "resnet50"
        assert restored.data_config == {"split": [0.7, 0.15, 0.15]}
        assert restored.random_seed == 42
        assert restored.framework == "pytorch"

    def test_from_json_roundtrip(self) -> None:
        original = _make_config()
        restored = ConfigArtifact.from_json(original.to_json())
        assert restored.framework == original.framework
        assert restored.random_seed == original.random_seed


# ===========================================================================
# LogArtifact model tests
# ===========================================================================


class TestLogArtifact:
    """Tests for the LogArtifact dataclass."""

    def test_artifact_type_is_log(self) -> None:
        log = _make_log()
        assert log.artifact_type == ArtifactType.LOG

    def test_to_dict_roundtrip(self) -> None:
        original = _make_log()
        restored = LogArtifact.from_dict(original.to_dict())
        assert len(restored.metrics_history) == 2
        assert restored.loss_curve == original.loss_curve
        assert restored.val_loss_curve == original.val_loss_curve
        assert restored.training_duration_seconds == 3600.0
        assert restored.final_metrics == original.final_metrics
        assert restored.status == "completed"

    def test_from_json_roundtrip(self) -> None:
        original = _make_log()
        restored = LogArtifact.from_json(original.to_json())
        assert restored.status == original.status
        assert len(restored.metrics_history) == 2

    def test_default_values(self) -> None:
        log = LogArtifact(artifact_id="l1", experiment_id="e1")
        assert log.metrics_history == []
        assert log.loss_curve == []
        assert log.val_loss_curve == []
        assert log.training_duration_seconds == 0.0
        assert log.final_metrics == {}
        assert log.status == "completed"


# ===========================================================================
# ArtifactStorage tests
# ===========================================================================


class TestArtifactStorage:
    """Tests for the ArtifactStorage filesystem backend."""

    def _storage_with_tmpdir(self, tmp_path: Path) -> tuple[ArtifactStorage, Path]:
        base = tmp_path / "artifacts"
        return ArtifactStorage(), base

    def test_save_and_load_artifact(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        artifact = _make_checkpoint()

        saved_path = storage.save_artifact(artifact, base)
        assert saved_path.exists()

        loaded = storage.load_artifact("ckpt-001", base)
        assert isinstance(loaded, CheckpointArtifact)
        assert loaded.epoch == 10
        assert loaded.checkpoint_path == "/models/checkpoint.pt"

    def test_save_and_load_with_binary(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        artifact = _make_checkpoint()
        binary_data = b"\x00\x01\x02\x03\x04"

        storage.save_artifact(artifact, base, binary_data=binary_data)

        loaded_bin = storage.load_binary("ckpt-001", base)
        assert loaded_bin == binary_data

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        with pytest.raises(ArtifactNotFoundError):
            storage.load_artifact("nonexistent", base)

    def test_load_binary_nonexistent_returns_none(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        # Save without binary
        storage.save_artifact(_make_checkpoint(), base)
        result = storage.load_binary("ckpt-001", base)
        assert result is None

    def test_list_artifacts_by_experiment(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        storage.save_artifact(_make_checkpoint(), base)
        storage.save_artifact(_make_config(), base)
        storage.save_artifact(_make_log(), base)

        artifacts = storage.list_artifacts("exp-001", base)
        assert len(artifacts) == 3

    def test_list_artifacts_filter_by_type(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        storage.save_artifact(_make_checkpoint(), base)
        storage.save_artifact(_make_config(), base)
        storage.save_artifact(_make_log(), base)

        checkpoints = storage.list_artifacts("exp-001", base, ArtifactType.CHECKPOINT)
        assert len(checkpoints) == 1
        assert isinstance(checkpoints[0], CheckpointArtifact)

    def test_list_artifacts_nonexistent_experiment(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        artifacts = storage.list_artifacts("nonexistent", base)
        assert artifacts == []

    def test_delete_artifact(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        storage.save_artifact(_make_checkpoint(), base, binary_data=b"data")

        result = storage.delete_artifact("ckpt-001", base)
        assert result is True

        with pytest.raises(ArtifactNotFoundError):
            storage.load_artifact("ckpt-001", base)

    def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        result = storage.delete_artifact("nonexistent", base)
        assert result is False

    def test_delete_experiment(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        storage.save_artifact(_make_checkpoint(), base)
        storage.save_artifact(_make_config(), base)

        result = storage.delete_experiment("exp-001", base)
        assert result is True

        assert not (base / "exp-001").exists()
        assert storage.list_artifacts("exp-001", base) == []

    def test_list_experiments(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        storage.save_artifact(
            CheckpointArtifact(
                artifact_id="c1",
                experiment_id="exp-alpha",
            ),
            base,
        )
        storage.save_artifact(
            CheckpointArtifact(
                artifact_id="c2",
                experiment_id="exp-beta",
            ),
            base,
        )

        experiments = storage.list_experiments(base)
        assert experiments == ["exp-alpha", "exp-beta"]

    def test_save_creates_experiment_directory(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        storage.save_artifact(_make_checkpoint(), base)

        assert (base / "exp-001").is_dir()

    def test_load_returns_correct_type(self, tmp_path: Path) -> None:
        storage, base = self._storage_with_tmpdir(tmp_path)
        storage.save_artifact(_make_config(), base)

        loaded = storage.load_artifact("cfg-001", base)
        assert isinstance(loaded, ConfigArtifact)
        assert loaded.hyperparameters == {"lr": 0.001, "batch_size": 32, "epochs": 100}


# ===========================================================================
# ArtifactManager tests
# ===========================================================================


class TestArtifactManager:
    """Tests for the ArtifactManager high-level interface."""

    def _manager(self, tmp_path: Path) -> ArtifactManager:
        base = tmp_path / "artifacts"
        return ArtifactManager(base_path=str(base))

    def test_save_and_load_checkpoint(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        ckpt = _make_checkpoint()

        mgr.save_checkpoint(ckpt, binary_data=b"weights")

        loaded = mgr.load_artifact("ckpt-001")
        assert isinstance(loaded, CheckpointArtifact)
        assert loaded.epoch == 10

        assert mgr.load_binary("ckpt-001") == b"weights"

    def test_save_and_load_config(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        cfg = _make_config()
        mgr.save_config(cfg)

        loaded = mgr.load_artifact("cfg-001")
        assert isinstance(loaded, ConfigArtifact)
        assert loaded.framework == "pytorch"

    def test_save_and_load_log(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        log = _make_log()
        mgr.save_log(log)

        loaded = mgr.load_artifact("log-001")
        assert isinstance(loaded, LogArtifact)
        assert loaded.status == "completed"

    def test_get_checkpoints(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(
            CheckpointArtifact(artifact_id="c1", experiment_id="exp-001", epoch=5)
        )
        mgr.save_checkpoint(
            CheckpointArtifact(artifact_id="c2", experiment_id="exp-001", epoch=10)
        )
        mgr.save_config(_make_config())

        checkpoints = mgr.get_checkpoints("exp-001")
        assert len(checkpoints) == 2

    def test_get_configs(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_config(_make_config())

        configs = mgr.get_configs("exp-001")
        assert len(configs) == 1
        assert configs[0].framework == "pytorch"

    def test_get_logs(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_log(_make_log())

        logs = mgr.get_logs("exp-001")
        assert len(logs) == 1
        assert logs[0].status == "completed"

    def test_get_best_checkpoint_minimize(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(
            CheckpointArtifact(
                artifact_id="c1",
                experiment_id="exp-001",
                epoch=5,
                metrics_snapshot={"val_loss": 0.5},
            )
        )
        mgr.save_checkpoint(
            CheckpointArtifact(
                artifact_id="c2",
                experiment_id="exp-001",
                epoch=10,
                metrics_snapshot={"val_loss": 0.1},
            )
        )

        best = mgr.get_best_checkpoint("exp-001", metric_key="val_loss", minimize=True)
        assert best is not None
        assert best.artifact_id == "c2"

    def test_get_best_checkpoint_maximize(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(
            CheckpointArtifact(
                artifact_id="c1",
                experiment_id="exp-001",
                epoch=5,
                metrics_snapshot={"accuracy": 0.8},
            )
        )
        mgr.save_checkpoint(
            CheckpointArtifact(
                artifact_id="c2",
                experiment_id="exp-001",
                epoch=10,
                metrics_snapshot={"accuracy": 0.95},
            )
        )

        best = mgr.get_best_checkpoint("exp-001", metric_key="accuracy", minimize=False)
        assert best is not None
        assert best.artifact_id == "c2"

    def test_get_best_checkpoint_none_when_empty(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        assert mgr.get_best_checkpoint("exp-001") is None

    def test_get_latest_checkpoint(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(
            CheckpointArtifact(artifact_id="c1", experiment_id="exp-001", epoch=5)
        )
        mgr.save_checkpoint(
            CheckpointArtifact(artifact_id="c2", experiment_id="exp-001", epoch=20)
        )
        mgr.save_checkpoint(
            CheckpointArtifact(artifact_id="c3", experiment_id="exp-001", epoch=10)
        )

        latest = mgr.get_latest_checkpoint("exp-001")
        assert latest is not None
        assert latest.epoch == 20

    def test_list_experiments(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(CheckpointArtifact(artifact_id="c1", experiment_id="exp-a"))
        mgr.save_checkpoint(CheckpointArtifact(artifact_id="c2", experiment_id="exp-b"))

        experiments = mgr.list_experiments()
        assert experiments == ["exp-a", "exp-b"]

    def test_delete_artifact(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(_make_checkpoint())

        result = mgr.delete_artifact("ckpt-001")
        assert result is True

        with pytest.raises(ArtifactNotFoundError):
            mgr.load_artifact("ckpt-001")

    def test_delete_experiment(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(_make_checkpoint())
        mgr.save_config(_make_config())

        result = mgr.delete_experiment("exp-001")
        assert result is True

        assert mgr.list_experiments() == []

    def test_experiment_summary(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        mgr.save_checkpoint(
            CheckpointArtifact(artifact_id="c1", experiment_id="exp-001", epoch=10)
        )
        mgr.save_config(_make_config())
        mgr.save_log(_make_log())

        summary = mgr.experiment_summary("exp-001")
        assert summary["experiment_id"] == "exp-001"
        assert summary["checkpoint_count"] == 1
        assert summary["config_count"] == 1
        assert summary["log_count"] == 1
        assert summary["latest_checkpoint_epoch"] == 10
        assert summary["latest_log_status"] == "completed"
        assert summary["training_duration_seconds"] == 3600.0

    def test_base_path_property(self, tmp_path: Path) -> None:
        mgr = self._manager(tmp_path)
        assert mgr.base_path == tmp_path / "artifacts"
