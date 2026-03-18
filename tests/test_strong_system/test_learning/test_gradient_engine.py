"""Tests for gradient engine."""

import numpy as np
import pytest
from src.strong_system.learning import (
    BeliefGradientFunction,
    GradientConfig,
    GradientEngine,
    GradientStats,
)
from src.strong_system.neural_beliefs import NeuralBelief


class TestGradientConfig:
    """Tests for GradientConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GradientConfig()
        assert config.clip_norm == 1.0
        assert config.clip_value is None
        assert config.accumulate_gradients is False
        assert config.zero_grad_before_compute is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = GradientConfig(
            clip_norm=0.5,
            clip_value=1.0,
            accumulate_gradients=True,
            zero_grad_before_compute=False,
        )
        assert config.clip_norm == 0.5
        assert config.clip_value == 1.0
        assert config.accumulate_gradients is True
        assert config.zero_grad_before_compute is False


class TestGradientStats:
    """Tests for GradientStats."""

    def test_default_stats(self):
        """Test default statistics values."""
        stats = GradientStats()
        assert stats.mean_magnitude == 0.0
        assert stats.max_magnitude == 0.0
        assert stats.has_nans is False
        assert stats.has_infs is False

    def test_stats_to_dict(self):
        """Test converting stats to dictionary."""
        stats = GradientStats(
            mean_magnitude=0.5,
            max_magnitude=1.0,
            clipped_count=2,
            has_nans=True,
        )
        d = stats.to_dict()
        assert d["mean_magnitude"] == 0.5
        assert d["max_magnitude"] == 1.0
        assert d["clipped_count"] == 2
        assert d["has_nans"] is True


class TestGradientEngine:
    """Tests for GradientEngine."""

    def test_initialization(self):
        """Test gradient engine initialization."""
        engine = GradientEngine()
        assert engine.config is not None
        assert engine.graph is not None
        assert len(engine._belief_nodes) == 0

    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        config = GradientConfig(clip_norm=0.5)
        engine = GradientEngine(config)
        assert engine.config.clip_norm == 0.5

    def test_register_belief(self, sample_belief):
        """Test registering a belief."""
        engine = GradientEngine()
        node = engine.register_belief(sample_belief)
        assert node is not None
        assert sample_belief.belief_id in engine._belief_nodes

    def test_register_belief_with_name(self, sample_belief):
        """Test registering a belief with custom name."""
        engine = GradientEngine()
        node = engine.register_belief(sample_belief, name="custom_name")
        assert "custom_name" in engine._belief_nodes

    def test_register_same_belief_twice(self, sample_belief):
        """Test registering the same belief twice returns same node."""
        engine = GradientEngine()
        node1 = engine.register_belief(sample_belief)
        node2 = engine.register_belief(sample_belief)
        assert node1 is node2

    def test_compute_similarity_loss(self, sample_beliefs):
        """Test computing similarity loss."""
        engine = GradientEngine()
        belief1, belief2, _ = sample_beliefs
        loss = engine.compute_similarity_loss(belief1, belief2)
        assert loss is not None
        assert loss.value is not None

    def test_compute_mse_loss(self, sample_belief):
        """Test computing MSE loss."""
        engine = GradientEngine()
        target = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
        loss = engine.compute_mse_loss(sample_belief, target)
        assert loss is not None
        assert loss.value is not None
        assert loss.value >= 0

    def test_compute_contrastive_loss(self, sample_beliefs):
        """Test computing contrastive loss."""
        engine = GradientEngine()
        anchor, positive, negative = sample_beliefs
        loss = engine.compute_contrastive_loss(anchor, positive, negative, margin=1.0)
        assert loss is not None
        assert loss.value is not None
        assert loss.value >= 0

    def test_compute_gradients_no_loss(self):
        """Test computing gradients without loss raises error."""
        engine = GradientEngine()
        with pytest.raises(ValueError, match="No loss node"):
            engine.compute_gradients()

    def test_zero_grad(self, sample_belief):
        """Test zeroing gradients."""
        engine = GradientEngine()
        engine.register_belief(sample_belief)
        engine.zero_grad()
        # Should not raise any errors

    def test_reset(self, sample_belief):
        """Test resetting engine."""
        engine = GradientEngine()
        engine.register_belief(sample_belief)
        engine.reset()
        assert len(engine._belief_nodes) == 0
        assert engine._loss_node is None

    def test_get_gradient_stats(self, sample_beliefs):
        """Test getting gradient statistics."""
        engine = GradientEngine()
        belief1, belief2, _ = sample_beliefs
        loss = engine.compute_similarity_loss(belief1, belief2)
        engine.compute_gradients(loss)
        stats = engine.get_gradient_stats()
        assert isinstance(stats, GradientStats)


class TestBeliefGradientFunction:
    """Tests for BeliefGradientFunction."""

    def test_initialization(self):
        """Test gradient function initialization."""

        def dummy_fn(belief):
            return belief.vector

        grad_fn = BeliefGradientFunction(dummy_fn, name="test_fn")
        assert grad_fn.name == "test_fn"
        assert grad_fn.func == dummy_fn

    def test_call(self, sample_belief):
        """Test calling gradient function."""

        def similarity_fn(b1, b2):
            return np.dot(b1.vector, b2.vector)

        grad_fn = BeliefGradientFunction(similarity_fn)
        belief2 = NeuralBelief(np.array([0.5, 1.5, 2.5, 3.5, 4.5]))
        result = grad_fn(sample_belief, belief2)
        assert isinstance(result, (float, np.number))


class TestGradientClipping:
    """Tests for gradient clipping functionality."""

    def test_clip_by_norm(self):
        """Test gradient clipping by norm."""
        config = GradientConfig(clip_norm=1.0)
        engine = GradientEngine(config)

        # Create a belief with large values
        belief = NeuralBelief(np.array([10.0, 10.0, 10.0]))
        target = np.array([0.0, 0.0, 0.0])

        loss = engine.compute_mse_loss(belief, target)
        gradients = engine.compute_gradients(loss)

        # Check that gradients are clipped
        for grad in gradients.values():
            assert np.linalg.norm(grad) <= 1.0 + 1e-6

    def test_clip_by_value(self):
        """Test gradient clipping by value."""
        config = GradientConfig(clip_value=0.5)
        engine = GradientEngine(config)

        belief = NeuralBelief(np.array([10.0, 10.0, 10.0]))
        target = np.array([0.0, 0.0, 0.0])

        loss = engine.compute_mse_loss(belief, target)
        gradients = engine.compute_gradients(loss)

        # Check that gradients are clipped
        for grad in gradients.values():
            assert np.all(np.abs(grad) <= 0.5 + 1e-6)

    def test_nan_detection(self):
        """Test NaN detection in gradients."""
        engine = GradientEngine()

        # Create a valid belief
        belief = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        target = np.array([0.0, 0.0, 0.0])

        loss = engine.compute_mse_loss(belief, target)
        gradients = engine.compute_gradients(loss)

        # Manually inject NaN into gradients to test detection
        for grad in gradients.values():
            grad[0] = np.nan

        # Update stats with NaN gradients
        engine._update_stats(gradients)

        stats = engine.get_gradient_stats()
        assert stats.has_nans is True


class TestGradientEngineIntegration:
    """Integration tests for GradientEngine."""

    def test_full_gradient_flow(self):
        """Test complete gradient computation flow."""
        engine = GradientEngine()

        # Create beliefs
        belief1 = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        belief2 = NeuralBelief(np.array([1.5, 2.5, 3.5]))

        # Compute loss
        loss = engine.compute_similarity_loss(belief1, belief2, target_similarity=1.0)

        # Compute gradients
        gradients = engine.compute_gradients(loss)

        # Verify gradients exist
        assert len(gradients) > 0

        # Verify gradients are finite
        for grad in gradients.values():
            assert np.all(np.isfinite(grad))

        # Verify gradients are non-zero (critical for learning)
        assert any(
            np.any(g != 0) for g in gradients.values()
        ), "Expected non-zero gradients"

    def test_contrastive_loss_gradients_nonzero(self):
        """Test that contrastive loss produces non-zero gradients."""
        engine = GradientEngine()

        # Create beliefs where the negative is closer than positive + margin
        # This ensures the loss is positive and gradients are non-zero
        anchor = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        positive = NeuralBelief(
            np.array([5.0, 6.0, 7.0])
        )  # Far from anchor (dist ~6.9)
        negative = NeuralBelief(
            np.array([1.5, 2.5, 3.5])
        )  # Close to anchor (dist ~0.87)

        # Compute contrastive loss
        loss = engine.compute_contrastive_loss(anchor, positive, negative, margin=1.0)

        # Compute gradients
        gradients = engine.compute_gradients(loss)

        # Verify gradients exist and are finite
        assert len(gradients) > 0
        for grad in gradients.values():
            assert np.all(np.isfinite(grad))

        # Verify gradients are non-zero (critical for learning)
        assert any(
            np.any(g != 0) for g in gradients.values()
        ), "Expected non-zero gradients for contrastive loss"

    def test_mse_loss_gradients_nonzero(self):
        """Test that MSE loss produces non-zero gradients."""
        engine = GradientEngine()

        # Create belief and target with significant difference
        belief = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        target = np.array([5.0, 6.0, 7.0])  # Different from belief

        # Compute MSE loss
        loss = engine.compute_mse_loss(belief, target)

        # Compute gradients
        gradients = engine.compute_gradients(loss)

        # Verify gradients exist and are finite
        assert len(gradients) > 0
        for grad in gradients.values():
            assert np.all(np.isfinite(grad))

        # Verify gradients are non-zero (critical for learning)
        assert any(
            np.any(g != 0) for g in gradients.values()
        ), "Expected non-zero gradients for MSE loss"

    def test_apply_gradients(self):
        """Test applying gradients to beliefs."""
        engine = GradientEngine()

        belief = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        original_vector = belief.vector.copy()

        # Create fake gradients
        gradients = {belief.belief_id: np.array([0.1, 0.1, 0.1])}
        beliefs = {belief.belief_id: belief}

        # Apply gradients
        engine.apply_gradients(gradients, beliefs, learning_rate=0.1)

        # Verify belief was updated
        assert not np.array_equal(belief.vector, original_vector)
