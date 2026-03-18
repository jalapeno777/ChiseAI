"""Tests for checkpoint module."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
from src.strong_system.computational_graph import Node
from src.strong_system.computational_graph.optimizer import (
    CheckpointStrategy,
    GraphOptimizer,
)
from src.strong_system.learning import (
    Checkpoint,
    CheckpointFormat,
    CheckpointMetadata,
    GradientCheckpointManager,
    create_checkpoint_manager_from_optimizer,
)


class TestCheckpointMetadata:
    """Tests for CheckpointMetadata."""

    def test_default_metadata(self):
        """Test default metadata values."""
        metadata = CheckpointMetadata(layer_id="layer_0")
        assert metadata.layer_id == "layer_0"
        assert metadata.step_number == 0
        assert metadata.timestamp == ""
        assert metadata.memory_bytes == 0

    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        metadata = CheckpointMetadata(
            layer_id="layer_1",
            step_number=10,
            timestamp="2024-01-01T00:00:00",
            shape=(3, 4),
            dtype="float64",
            memory_bytes=96,
            description="Test checkpoint",
        )
        d = metadata.to_dict()
        assert d["layer_id"] == "layer_1"
        assert d["step_number"] == 10
        assert d["shape"] == (3, 4)

    def test_metadata_from_dict(self):
        """Test creating metadata from dictionary."""
        data = {
            "layer_id": "layer_2",
            "step_number": 5,
            "timestamp": "2024-01-01T00:00:00",
            "shape": [2, 3],
            "dtype": "float32",
            "memory_bytes": 24,
        }
        metadata = CheckpointMetadata.from_dict(data)
        assert metadata.layer_id == "layer_2"
        assert metadata.step_number == 5
        assert metadata.shape == (2, 3)


class TestCheckpoint:
    """Tests for Checkpoint class."""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        data = np.array([1.0, 2.0, 3.0])
        metadata = CheckpointMetadata(layer_id="test_layer")
        checkpoint = Checkpoint(data=data, metadata=metadata)

        assert np.array_equal(checkpoint.data, data)
        assert checkpoint.metadata.layer_id == "test_layer"

    def test_checkpoint_to_dict(self):
        """Test converting checkpoint to dictionary."""
        data = np.array([1.0, 2.0, 3.0])
        metadata = CheckpointMetadata(layer_id="test_layer")
        checkpoint = Checkpoint(data=data, metadata=metadata)

        d = checkpoint.to_dict()
        assert "data" in d
        assert "metadata" in d


class TestGradientCheckpointManager:
    """Tests for GradientCheckpointManager."""

    def test_initialization(self):
        """Test manager initialization."""
        manager = GradientCheckpointManager()
        assert manager.strategy == CheckpointStrategy.SELECTIVE
        assert manager.memory_limit_mb == 1024.0
        assert len(manager.checkpoints) == 0

    def test_initialization_with_params(self):
        """Test initialization with custom parameters."""
        manager = GradientCheckpointManager(
            strategy=CheckpointStrategy.ALL,
            memory_limit_mb=512.0,
            checkpoint_interval=10,
        )
        assert manager.strategy == CheckpointStrategy.ALL
        assert manager.memory_limit_mb == 512.0
        assert manager.checkpoint_interval == 10

    def test_should_checkpoint_none_strategy(self):
        """Test checkpoint decision with NONE strategy."""
        manager = GradientCheckpointManager(strategy=CheckpointStrategy.NONE)
        assert manager.should_checkpoint("layer_0") is False

    def test_should_checkpoint_all_strategy(self):
        """Test checkpoint decision with ALL strategy."""
        manager = GradientCheckpointManager(strategy=CheckpointStrategy.ALL)
        assert manager.should_checkpoint("layer_0") is True

    def test_should_checkpoint_selective_strategy(self):
        """Test checkpoint decision with SELECTIVE strategy."""
        manager = GradientCheckpointManager(
            strategy=CheckpointStrategy.SELECTIVE,
            checkpoint_interval=5,
        )
        assert manager.should_checkpoint("layer_0", layer_idx=0) is True
        assert manager.should_checkpoint("layer_5", layer_idx=5) is True
        assert manager.should_checkpoint("layer_3", layer_idx=3) is False

    def test_add_checkpoint(self, sample_node):
        """Test adding a checkpoint."""
        manager = GradientCheckpointManager()
        checkpoint = manager.add_checkpoint(sample_node, "layer_0")

        assert checkpoint is not None
        assert "layer_0" in manager.checkpoints

    def test_get_checkpoint(self, sample_node):
        """Test getting a checkpoint."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0")

        checkpoint = manager.get_checkpoint("layer_0")
        assert checkpoint is not None
        assert checkpoint.metadata.layer_id == "layer_0"

    def test_get_nonexistent_checkpoint(self):
        """Test getting non-existent checkpoint."""
        manager = GradientCheckpointManager()
        assert manager.get_checkpoint("nonexistent") is None

    def test_restore_checkpoint(self, sample_node):
        """Test restoring a checkpoint."""
        manager = GradientCheckpointManager()
        original_value = sample_node.value.copy()
        manager.add_checkpoint(sample_node, "layer_0")

        # Modify node value
        sample_node.value = np.array([99.0, 99.0, 99.0])

        # Restore
        success = manager.restore_checkpoint("layer_0", sample_node)
        assert success is True
        assert np.array_equal(sample_node.value, original_value)

    def test_remove_checkpoint(self, sample_node):
        """Test removing a checkpoint."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0")

        success = manager.remove_checkpoint("layer_0")
        assert success is True
        assert "layer_0" not in manager.checkpoints

    def test_clear_checkpoints(self, sample_node):
        """Test clearing all checkpoints."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0")
        manager.add_checkpoint(sample_node, "layer_1")

        manager.clear()
        assert len(manager.checkpoints) == 0

    def test_get_memory_usage(self, sample_node):
        """Test memory usage calculation."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0")

        usage = manager.get_memory_usage_mb()
        assert usage > 0

    def test_get_checkpoint_count(self, sample_node):
        """Test getting checkpoint count."""
        manager = GradientCheckpointManager()
        assert manager.get_checkpoint_count() == 0

        manager.add_checkpoint(sample_node, "layer_0")
        assert manager.get_checkpoint_count() == 1

    def test_get_checkpoint_ids(self, sample_node):
        """Test getting checkpoint IDs."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0")
        manager.add_checkpoint(sample_node, "layer_1")

        ids = manager.get_checkpoint_ids()
        assert "layer_0" in ids
        assert "layer_1" in ids

    def test_step_counter(self):
        """Test step counter increment."""
        manager = GradientCheckpointManager()
        assert manager.current_step == 0

        manager.step()
        assert manager.current_step == 1

        manager.step()
        assert manager.current_step == 2

    def test_get_stats(self, sample_node):
        """Test getting statistics."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0")

        stats = manager.get_stats()
        assert stats["checkpoint_count"] == 1
        assert stats["memory_usage_mb"] > 0
        assert stats["strategy"] == "SELECTIVE"

    def test_create_checkpoint_plan(self):
        """Test creating checkpoint plan."""
        manager = GradientCheckpointManager(
            strategy=CheckpointStrategy.SELECTIVE,
            checkpoint_interval=5,
        )

        plan = manager.create_checkpoint_plan(num_layers=20)
        assert 0 in plan  # First layer always checkpointed
        assert 19 in plan  # Last layer always checkpointed
        assert 5 in plan
        assert 10 in plan

    def test_create_checkpoint_plan_none_strategy(self):
        """Test checkpoint plan with NONE strategy."""
        manager = GradientCheckpointManager(strategy=CheckpointStrategy.NONE)
        plan = manager.create_checkpoint_plan(num_layers=20)
        assert len(plan) == 0


class TestCheckpointPersistence:
    """Tests for checkpoint save/load functionality."""

    def test_save_and_load_numpy(self, sample_node):
        """Test saving and loading checkpoints in NumPy format."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0", description="Test layer")

        with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as f:
            path = f.name

        try:
            manager.save_checkpoints(path, format=CheckpointFormat.NUMPY)

            # Load into new manager
            new_manager = GradientCheckpointManager()
            new_manager.load_checkpoints(path, format=CheckpointFormat.NUMPY)

            assert new_manager.get_checkpoint_count() == 1
            checkpoint = new_manager.get_checkpoint("layer_0")
            assert checkpoint is not None
            assert np.array_equal(checkpoint.data, sample_node.value)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_save_and_load_json(self, sample_node):
        """Test saving and loading checkpoints in JSON format."""
        manager = GradientCheckpointManager()
        manager.add_checkpoint(sample_node, "layer_0")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            manager.save_checkpoints(path, format=CheckpointFormat.JSON)

            # Load into new manager
            new_manager = GradientCheckpointManager()
            new_manager.load_checkpoints(path, format=CheckpointFormat.JSON)

            assert new_manager.get_checkpoint_count() == 1
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_nonexistent_file(self):
        """Test loading from non-existent file."""
        manager = GradientCheckpointManager()
        with pytest.raises(FileNotFoundError):
            manager.load_checkpoints("/nonexistent/path.npz")


class TestGraphOptimizerIntegration:
    """Tests for integration with GraphOptimizer."""

    def test_create_from_optimizer(self):
        """Test creating manager from GraphOptimizer."""
        optimizer = GraphOptimizer()
        manager = create_checkpoint_manager_from_optimizer(
            optimizer, memory_limit_mb=512.0
        )

        assert manager.strategy == optimizer.config.checkpoint_strategy
        assert manager.memory_limit_mb == 512.0
        assert manager._optimizer is optimizer

    def test_set_optimizer(self):
        """Test setting optimizer on manager."""
        manager = GradientCheckpointManager()
        optimizer = GraphOptimizer()

        manager.set_optimizer(optimizer)
        assert manager._optimizer is optimizer


class TestMemoryManagement:
    """Tests for memory management features."""

    def test_memory_limit_enforcement(self):
        """Test that memory limit is enforced."""
        # Create manager with very low memory limit
        manager = GradientCheckpointManager(memory_limit_mb=0.001)

        # Add large checkpoint
        large_data = np.ones((1000, 1000), dtype=np.float64)  # ~8MB
        node = Node(large_data, name="large_node")

        # Should still work but may evict
        checkpoint = manager.add_checkpoint(node, "large_layer")
        assert checkpoint is not None

    def test_eviction_on_memory_pressure(self, sample_node):
        """Test checkpoint eviction under memory pressure."""
        manager = GradientCheckpointManager(memory_limit_mb=0.0001)

        # Add multiple checkpoints
        for i in range(5):
            manager.add_checkpoint(sample_node, f"layer_{i}", step_number=i)

        # Some may have been evicted due to memory pressure
        assert (
            manager.get_memory_usage_mb() <= manager.memory_limit_mb * 1.1
        )  # Allow small tolerance
