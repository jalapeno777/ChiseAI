"""Unit tests for CheckpointManager."""

import tempfile

import pytest
from src.autonomous_cognition.gradient_learning.checkpoint import (
    Checkpoint,
    CheckpointManager,
)


class TestCheckpoint:
    """Tests for Checkpoint dataclass."""

    def test_to_dict(self):
        """Test converting checkpoint to dict."""
        checkpoint = Checkpoint(
            checkpoint_id="test_001",
            step=10,
            params={"x": 1.0, "y": 2.0},
            optimizer_state={"type": "SGD", "learning_rate": 0.1},
        )

        data = checkpoint.to_dict()
        assert data["checkpoint_id"] == "test_001"
        assert data["step"] == 10
        assert data["params"]["x"] == 1.0

    def test_from_dict(self):
        """Test creating checkpoint from dict."""
        data = {
            "checkpoint_id": "test_001",
            "step": 10,
            "params": {"x": 1.0},
            "optimizer_state": {"type": "SGD"},
            "scheduler_state": None,
            "clipper_state": None,
            "metrics": None,
            "timestamp": "2024-01-01T00:00:00Z",
            "metadata": {},
        }

        checkpoint = Checkpoint.from_dict(data)
        assert checkpoint.checkpoint_id == "test_001"
        assert checkpoint.step == 10
        assert checkpoint.params["x"] == 1.0


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = CheckpointManager(
            checkpoint_dir=self.temp_dir,
            max_checkpoints=5,
            format="json",
        )

    def teardown_method(self):
        """Clean up temp files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_json(self):
        """Test saving and loading checkpoint in JSON format."""
        checkpoint = Checkpoint(
            checkpoint_id="test_001",
            step=10,
            params={"x": 1.0, "y": 2.0},
            optimizer_state={"type": "SGD"},
        )

        self.manager.save(checkpoint)
        loaded = self.manager.load("test_001")

        assert loaded.checkpoint_id == "test_001"
        assert loaded.step == 10
        assert loaded.params["x"] == 1.0

    def test_save_and_load_pickle(self):
        """Test saving and loading checkpoint in pickle format."""
        manager = CheckpointManager(
            checkpoint_dir=self.temp_dir,
            format="pickle",
        )
        checkpoint = Checkpoint(
            checkpoint_id="test_pickle",
            step=5,
            params={"a": 1.0},
            optimizer_state={"type": "Adam"},
        )

        manager.save(checkpoint)
        loaded = manager.load("test_pickle")

        assert loaded.checkpoint_id == "test_pickle"
        assert loaded.step == 5

    def test_list_checkpoints(self):
        """Test listing checkpoints."""
        for i in range(3):
            checkpoint = Checkpoint(
                checkpoint_id=f"test_{i:03d}",
                step=i * 10,
                params={"x": float(i)},
                optimizer_state={},
            )
            self.manager.save(checkpoint)

        checkpoints = self.manager.list_checkpoints()
        assert len(checkpoints) == 3
        # Should be sorted by step
        assert checkpoints[0]["step"] == 0
        assert checkpoints[-1]["step"] == 20

    def test_delete_checkpoint(self):
        """Test deleting a checkpoint."""
        checkpoint = Checkpoint(
            checkpoint_id="to_delete",
            step=1,
            params={"x": 1.0},
            optimizer_state={},
        )
        self.manager.save(checkpoint)

        assert self.manager.delete("to_delete") is True
        assert self.manager.delete("nonexistent") is False

        checkpoints = self.manager.list_checkpoints()
        assert not any(cp["checkpoint_id"] == "to_delete" for cp in checkpoints)

    def test_cleanup_old_checkpoints(self):
        """Test that old checkpoints are cleaned up."""
        manager = CheckpointManager(
            checkpoint_dir=self.temp_dir,
            max_checkpoints=3,
            format="json",
        )

        # Create 5 checkpoints
        for i in range(5):
            checkpoint = Checkpoint(
                checkpoint_id=f"old_{i}",
                step=i,
                params={"x": float(i)},
                optimizer_state={},
            )
            manager.save(checkpoint)

        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 3
        # Oldest should be removed
        assert all(cp["step"] >= 2 for cp in checkpoints)

    def test_rollback_by_step(self):
        """Test rolling back to a specific step."""
        for i in range(5):
            checkpoint = Checkpoint(
                checkpoint_id=f"step_{i}",
                step=i * 10,
                params={"x": float(i)},
                optimizer_state={},
            )
            self.manager.save(checkpoint)

        rolled_back = self.manager.rollback(target_step=20)
        assert rolled_back.step == 20
        assert rolled_back.params["x"] == 2.0

    def test_rollback_by_id(self):
        """Test rolling back to a specific checkpoint ID."""
        checkpoint = Checkpoint(
            checkpoint_id="specific_id",
            step=42,
            params={"x": 999.0},
            optimizer_state={},
        )
        self.manager.save(checkpoint)

        rolled_back = self.manager.rollback(checkpoint_id="specific_id")
        assert rolled_back.step == 42
        assert rolled_back.params["x"] == 999.0

    def test_checkpoint_not_found_raises(self):
        """Test that loading nonexistent checkpoint raises."""
        with pytest.raises(FileNotFoundError):
            self.manager.load("nonexistent")

    def test_invalid_format_raises(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError):
            CheckpointManager(checkpoint_dir=self.temp_dir, format="invalid")
