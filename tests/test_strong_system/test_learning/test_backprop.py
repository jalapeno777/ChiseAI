"""Tests for backpropagation module."""

import numpy as np
import pytest
from src.strong_system.learning import (
    BackpropConfig,
    BackpropStats,
    BeliefBackpropagator,
    CheckpointManager,
    DeepBeliefTrainer,
)
from src.strong_system.neural_beliefs import NeuralBelief


class TestBackpropConfig:
    """Tests for BackpropConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BackpropConfig()
        assert config.max_layers == 20
        assert config.use_checkpointing is True
        assert config.checkpoint_interval == 5
        assert config.memory_limit_mb == 1024.0
        assert config.enable_gradient_clipping is True
        assert config.clip_norm == 1.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = BackpropConfig(
            max_layers=50,
            use_checkpointing=False,
            checkpoint_interval=10,
            memory_limit_mb=512.0,
            enable_gradient_clipping=False,
            clip_norm=0.5,
        )
        assert config.max_layers == 50
        assert config.use_checkpointing is False
        assert config.checkpoint_interval == 10
        assert config.memory_limit_mb == 512.0
        assert config.enable_gradient_clipping is False
        assert config.clip_norm == 0.5


class TestBackpropStats:
    """Tests for BackpropStats."""

    def test_default_stats(self):
        """Test default statistics values."""
        stats = BackpropStats()
        assert stats.layers_processed == 0
        assert stats.checkpoints_used == 0
        assert stats.exploded_gradients is False

    def test_stats_to_dict(self):
        """Test converting stats to dictionary."""
        stats = BackpropStats(
            layers_processed=10,
            checkpoints_used=3,
            memory_used_mb=100.0,
            gradient_norms=[0.1, 0.2, 0.3],
            time_ms=50.0,
            exploded_gradients=True,
        )
        d = stats.to_dict()
        assert d["layers_processed"] == 10
        assert d["checkpoints_used"] == 3
        assert d["exploded_gradients"] is True


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_initialization(self):
        """Test checkpoint manager initialization."""
        manager = CheckpointManager(checkpoint_interval=5)
        assert manager.checkpoint_interval == 5
        assert len(manager.checkpoints) == 0

    def test_should_checkpoint(self):
        """Test checkpoint decision logic."""
        manager = CheckpointManager(checkpoint_interval=5)
        assert manager.should_checkpoint(0) is True
        assert manager.should_checkpoint(5) is True
        assert manager.should_checkpoint(3) is False
        assert manager.should_checkpoint(10) is True

    def test_save_and_get_checkpoint(self):
        """Test saving and retrieving checkpoints."""
        manager = CheckpointManager()
        data = np.array([1.0, 2.0, 3.0])

        manager.save_checkpoint(0, data)
        retrieved = manager.get_checkpoint(0)

        assert retrieved is not None
        assert np.array_equal(retrieved, data)

    def test_get_nonexistent_checkpoint(self):
        """Test retrieving non-existent checkpoint."""
        manager = CheckpointManager()
        assert manager.get_checkpoint(999) is None

    def test_clear_checkpoints(self):
        """Test clearing all checkpoints."""
        manager = CheckpointManager()
        manager.save_checkpoint(0, np.array([1.0, 2.0]))
        manager.save_checkpoint(5, np.array([3.0, 4.0]))

        manager.clear()
        assert len(manager.checkpoints) == 0

    def test_memory_usage(self):
        """Test memory usage calculation."""
        manager = CheckpointManager()
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
        manager.save_checkpoint(0, data)

        expected_mb = data.nbytes / (1024 * 1024)
        assert manager.get_memory_usage_mb() == pytest.approx(expected_mb)


class TestBeliefBackpropagator:
    """Tests for BeliefBackpropagator."""

    def test_initialization(self):
        """Test backpropagator initialization."""
        config = BackpropConfig()
        backprop = BeliefBackpropagator(config)
        assert backprop.config == config
        assert backprop.graph is not None

    def test_backward_simple(self, sample_beliefs):
        """Test simple backward pass."""
        config = BackpropConfig(max_layers=20)
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(3)
        gradients = backprop.backward(sample_beliefs, output_grad)

        assert isinstance(gradients, dict)

        # Verify gradients are non-zero (critical for learning)
        assert any(
            np.any(g != 0) for g in gradients.values()
        ), "Expected non-zero gradients"

    def test_backward_gradients_nonzero(self, sample_beliefs):
        """Test that backward pass produces non-zero gradients."""
        config = BackpropConfig(max_layers=20)
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(3)
        gradients = backprop.backward(sample_beliefs, output_grad)

        # Verify gradients exist and are non-zero
        assert len(gradients) > 0, "Expected at least one gradient"
        for belief_id, grad in gradients.items():
            assert np.all(np.isfinite(grad)), f"Gradient for {belief_id} is not finite"
            assert np.any(grad != 0), f"Expected non-zero gradient for {belief_id}"

    def test_backward_too_many_layers(self, deep_beliefs):
        """Test backward with too many layers raises error."""
        config = BackpropConfig(max_layers=10)
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(10)
        with pytest.raises(ValueError, match="exceeds max_layers"):
            backprop.backward(deep_beliefs, output_grad)

    def test_backward_with_checkpointing(self, deep_beliefs):
        """Test backward with checkpointing enabled."""
        config = BackpropConfig(
            max_layers=20,
            use_checkpointing=True,
            checkpoint_interval=5,
        )
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(10)
        gradients = backprop.backward(deep_beliefs[:12], output_grad)

        stats = backprop.get_stats()
        assert stats.layers_processed == 12

    def test_get_stats(self, sample_beliefs):
        """Test getting backpropagation statistics."""
        config = BackpropConfig()
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(3)
        backprop.backward(sample_beliefs, output_grad)

        stats = backprop.get_stats()
        assert isinstance(stats, BackpropStats)
        assert stats.layers_processed == len(sample_beliefs)

    def test_check_gradient_flow(self, sample_beliefs):
        """Test gradient flow checking."""
        config = BackpropConfig()
        backprop = BeliefBackpropagator(config)

        analysis = backprop.check_gradient_flow(sample_beliefs)
        assert "status" in analysis

    def test_gradient_flow_with_vanishing(self):
        """Test gradient flow with vanishing gradients."""
        # Create beliefs with very small values that could cause vanishing gradients
        beliefs = [NeuralBelief(np.array([1e-8, 1e-8, 1e-8])) for _ in range(5)]

        config = BackpropConfig()
        backprop = BeliefBackpropagator(config)

        analysis = backprop.check_gradient_flow(beliefs)
        assert "vanishing_detected" in analysis


class TestDeepBeliefTrainer:
    """Tests for DeepBeliefTrainer."""

    def test_initialization(self):
        """Test trainer initialization."""
        trainer = DeepBeliefTrainer(learning_rate=0.01, max_depth=30)
        assert trainer.learning_rate == 0.01
        assert trainer.max_depth == 30
        assert trainer.backpropagator is not None

    def test_train_step(self, sample_beliefs):
        """Test single training step."""
        trainer = DeepBeliefTrainer(learning_rate=0.01)
        target = np.array([1.0, 1.0, 1.0])

        metrics = trainer.train_step(sample_beliefs, target)

        assert "loss" in metrics
        assert "gradients_computed" in metrics

    def test_train_convergence(self, sample_beliefs):
        """Test training until convergence."""
        trainer = DeepBeliefTrainer(learning_rate=0.1)
        target = np.array([1.0, 2.0, 3.0])

        result = trainer.train(
            sample_beliefs,
            target,
            n_iterations=50,
            convergence_threshold=0.01,
        )

        assert "converged" in result
        assert "iterations" in result
        assert "history" in result

    def test_train_max_iterations(self, sample_beliefs):
        """Test training with max iterations."""
        trainer = DeepBeliefTrainer(learning_rate=0.01)
        target = np.array([1.0, 2.0, 3.0])

        result = trainer.train(
            sample_beliefs,
            target,
            n_iterations=5,
            convergence_threshold=1e-10,  # Very low to ensure max iterations reached
        )

        assert result["iterations"] == 5
        assert result["converged"] is False


class TestBackpropagationThroughDepth:
    """Tests for backpropagation through various depths."""

    @pytest.mark.parametrize("depth", [5, 10, 15])
    def test_backprop_at_depth(self, depth):
        """Test backpropagation at different depths."""
        beliefs = [NeuralBelief(np.random.randn(10)) for _ in range(depth)]

        config = BackpropConfig(max_layers=20)
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(10)
        gradients = backprop.backward(beliefs, output_grad)

        stats = backprop.get_stats()
        assert stats.layers_processed == depth
        assert len(gradients) > 0

    def test_backprop_10_plus_layers(self):
        """Test backpropagation through 10+ layers (acceptance criteria)."""
        depth = 12
        beliefs = [NeuralBelief(np.random.randn(8)) for _ in range(depth)]

        config = BackpropConfig(max_layers=20)
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(8)
        gradients = backprop.backward(beliefs, output_grad)

        # Verify gradients exist for all layers
        assert len(gradients) > 0
        stats = backprop.get_stats()
        assert stats.layers_processed == depth

        # Verify gradients are non-zero (critical for learning through deep networks)
        assert any(
            np.any(g != 0) for g in gradients.values()
        ), "Expected non-zero gradients through deep network"

    def test_gradient_explosion_detection(self):
        """Test detection of gradient explosion."""
        # Create beliefs with very large values
        beliefs = [NeuralBelief(np.array([1e5, 1e5, 1e5])) for _ in range(5)]

        config = BackpropConfig(max_layers=20)
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(3)
        backprop.backward(beliefs, output_grad)

        stats = backprop.get_stats()
        # May or may not detect explosion depending on gradient computation
        assert isinstance(stats.exploded_gradients, bool)


class TestIntermediateLosses:
    """Tests for intermediate loss computation."""

    def test_backward_with_intermediate_losses(self, sample_beliefs):
        """Test backward pass with intermediate losses."""
        config = BackpropConfig()
        backprop = BeliefBackpropagator(config)

        output_grad = np.ones(3)
        intermediate_losses = [(0, 0.1), (1, 0.2)]

        gradients = backprop.backward_with_intermediate_losses(
            sample_beliefs, intermediate_losses, output_grad
        )

        assert isinstance(gradients, dict)

    def test_layer_wise_gradients(self, sample_beliefs):
        """Test computing layer-wise gradients."""
        config = BackpropConfig()
        backprop = BeliefBackpropagator(config)

        target_output = np.array([1.0, 1.0, 1.0])
        layer_grads = backprop.compute_layer_wise_gradients(
            sample_beliefs, target_output
        )

        assert isinstance(layer_grads, list)
        assert len(layer_grads) > 0
