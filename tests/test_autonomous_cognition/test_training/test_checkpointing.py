"""Tests for checkpointing module."""

import shutil
import tempfile

from src.autonomous_cognition.training.checkpointing import (
    CheckpointType,
    ModelCheckpoint,
    ModelCheckpointConfig,
    ModelCheckpointing,
    create_model_checkpointing,
)


class TestModelCheckpoint:
    """Tests for ModelCheckpoint dataclass."""

    def test_creation(self):
        """Test checkpoint creation."""
        cp = ModelCheckpoint(
            checkpoint_id="test_1",
            checkpoint_type=CheckpointType.BEST,
            epoch=5,
            params={"x": 1.0, "y": 2.0},
            metrics={"val_loss": 0.5},
        )
        assert cp.checkpoint_id == "test_1"
        assert cp.epoch == 5
        assert cp.params["x"] == 1.0

    def test_to_dict(self):
        """Test checkpoint to dict."""
        cp = ModelCheckpoint(
            checkpoint_id="test_1",
            checkpoint_type=CheckpointType.BEST,
            epoch=5,
            params={"x": 1.0},
        )
        d = cp.to_dict()
        assert d["checkpoint_id"] == "test_1"
        assert d["checkpoint_type"] == "best"
        assert d["params"] == {"x": 1.0}


class TestModelCheckpointConfig:
    """Tests for ModelCheckpointConfig dataclass."""

    def test_defaults(self):
        """Test default configuration."""
        config = ModelCheckpointConfig()
        assert config.checkpoint_dir == "checkpoints/autocog"
        assert config.max_checkpoints == 5
        assert config.save_best_only is True
        assert config.metric_name == "val_loss"
        assert config.metric_direction == "minimize"


class TestModelCheckpointing:
    """Tests for ModelCheckpointing class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temp files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creation(self):
        """Test checkpointing creation."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                max_checkpoints=3,
            )
        )
        assert checkpointing.best_checkpoint is None
        assert len(checkpointing.checkpoints) == 0

    def test_check_and_save_first(self):
        """Test first checkpoint is saved as best."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                max_checkpoints=3,
            )
        )

        params = {"x": 1.0}
        metrics = {"val_loss": 0.5}

        is_best = checkpointing.check_and_save(
            epoch=1,
            params=params,
            metrics=metrics,
        )

        assert is_best is True
        assert checkpointing.best_checkpoint is not None
        assert checkpointing.best_checkpoint.epoch == 1

    def test_check_and_save_better(self):
        """Test better checkpoint replaces best."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                max_checkpoints=3,
                metric_direction="minimize",
            )
        )

        # First checkpoint
        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"val_loss": 0.5},
        )

        # Second checkpoint (better)
        is_best = checkpointing.check_and_save(
            epoch=2,
            params={"x": 2.0},
            metrics={"val_loss": 0.3},
        )

        assert is_best is True
        assert checkpointing.best_checkpoint.epoch == 2
        assert checkpointing.best_checkpoint.metrics["val_loss"] == 0.3

    def test_check_and_save_worse(self):
        """Test worse checkpoint is not best."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                max_checkpoints=3,
                metric_direction="minimize",
            )
        )

        # First checkpoint
        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"val_loss": 0.5},
        )

        # Second checkpoint (worse)
        is_best = checkpointing.check_and_save(
            epoch=2,
            params={"x": 2.0},
            metrics={"val_loss": 0.7},
        )

        assert is_best is False
        assert checkpointing.best_checkpoint.epoch == 1

    def test_maximize_direction(self):
        """Test maximize direction for metrics."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                max_checkpoints=3,
                metric_name="accuracy",
                metric_direction="maximize",
            )
        )

        # First checkpoint
        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"accuracy": 0.8},
        )

        # Second checkpoint (better - higher accuracy)
        is_best = checkpointing.check_and_save(
            epoch=2,
            params={"x": 2.0},
            metrics={"accuracy": 0.9},
        )

        assert is_best is True
        assert checkpointing.best_checkpoint.epoch == 2

    def test_max_checkpoints(self):
        """Test max checkpoints limit."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                max_checkpoints=3,
                save_best_only=False,  # Save all
            )
        )

        # Save more than max checkpoints
        for i in range(5):
            checkpointing.check_and_save(
                epoch=i + 1,
                params={"x": float(i)},
                metrics={"val_loss": 0.5 - i * 0.1},
                checkpoint_type=CheckpointType.PERIODIC,
            )

        # Should keep only max_checkpoints
        assert len(checkpointing.checkpoints) <= 3

    def test_best_checkpoint_preserved(self):
        """Test that best checkpoint is never deleted."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                max_checkpoints=2,
                save_best_only=False,
            )
        )

        # Save multiple checkpoints
        for i in range(5):
            checkpointing.check_and_save(
                epoch=i + 1,
                params={"x": float(i)},
                metrics={"val_loss": 0.5 - i * 0.1},
                checkpoint_type=CheckpointType.PERIODIC,
            )

        # Best should always be preserved
        assert checkpointing.best_checkpoint is not None

    def test_rollback_to_best(self):
        """Test rollback to best checkpoint."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(checkpoint_dir=self.temp_dir)
        )

        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"val_loss": 0.5},
        )

        checkpointing.check_and_save(
            epoch=2,
            params={"x": 2.0},
            metrics={"val_loss": 0.3},
        )

        # Rollback
        best_params = checkpointing.rollback_to_best()

        assert best_params == {"x": 2.0}
        assert checkpointing.best_checkpoint.epoch == 2

    def test_rollback_to_best_no_checkpoint(self):
        """Test rollback with no checkpoint."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(checkpoint_dir=self.temp_dir)
        )

        result = checkpointing.rollback_to_best()
        assert result is None

    def test_rollback_to_epoch(self):
        """Test rollback to specific epoch."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                save_best_only=False,
            )
        )

        for i in range(3):
            checkpointing.check_and_save(
                epoch=i + 1,
                params={"x": float(i + 1)},
                metrics={"val_loss": 0.5 - i * 0.1},
            )

        params = checkpointing.rollback_to_epoch(epoch=1)
        assert params == {"x": 1.0}

    def test_rollback_to_epoch_not_found(self):
        """Test rollback to non-existent epoch."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(checkpoint_dir=self.temp_dir)
        )

        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"val_loss": 0.5},
        )

        result = checkpointing.rollback_to_epoch(epoch=99)
        assert result is None

    def test_get_best_params(self):
        """Test getting best params."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(checkpoint_dir=self.temp_dir)
        )

        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"val_loss": 0.5},
        )

        best = checkpointing.get_best_params()
        assert best == {"x": 1.0}

    def test_get_best_metrics(self):
        """Test getting best metrics."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(checkpoint_dir=self.temp_dir)
        )

        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"val_loss": 0.5, "accuracy": 0.9},
        )

        best = checkpointing.get_best_metrics()
        assert best["val_loss"] == 0.5
        assert best["accuracy"] == 0.9

    def test_get_checkpoint_info(self):
        """Test getting checkpoint info."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                save_best_only=False,
            )
        )

        checkpointing.check_and_save(
            epoch=1,
            params={"x": 1.0},
            metrics={"val_loss": 0.5},
        )

        info = checkpointing.get_checkpoint_info()
        assert len(info) == 1
        assert info[0]["epoch"] == 1

    def test_periodic_checkpointing(self):
        """Test periodic checkpointing."""
        checkpointing = ModelCheckpointing(
            config=ModelCheckpointConfig(
                checkpoint_dir=self.temp_dir,
                save_every_n_epochs=5,
                save_best_only=False,  # Allow periodic saves
            )
        )

        # Should not save (not at interval)
        checkpointing.check_and_save(
            epoch=3,
            params={"x": 3.0},
            metrics={"val_loss": 0.3},
            checkpoint_type=CheckpointType.PERIODIC,
        )

        assert len(checkpointing.checkpoints) == 0

        # Should save (at interval)
        checkpointing.check_and_save(
            epoch=5,
            params={"x": 5.0},
            metrics={"val_loss": 0.5},
            checkpoint_type=CheckpointType.PERIODIC,
        )

        assert len(checkpointing.checkpoints) == 1


class TestCreateModelCheckpointing:
    """Tests for create_model_checkpointing factory."""

    def test_factory(self):
        """Test factory function."""
        checkpointing = create_model_checkpointing(
            checkpoint_dir="/tmp/test",
            max_checkpoints=10,
            metric_name="accuracy",
            metric_direction="maximize",
        )

        assert checkpointing.config.checkpoint_dir == "/tmp/test"
        assert checkpointing.config.max_checkpoints == 10
        assert checkpointing.config.metric_name == "accuracy"
        assert checkpointing.config.metric_direction == "maximize"
