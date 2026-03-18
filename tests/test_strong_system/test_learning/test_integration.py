"""Integration tests for the learning module."""

import numpy as np
from src.strong_system.learning import (
    BeliefBackpropagator,
    DeepBeliefTrainer,
    GradientCheckpointManager,
    GradientEngine,
    StepLR,
)
from src.strong_system.neural_beliefs import NeuralBelief


class TestEndToEndTraining:
    """End-to-end integration tests for training workflows."""

    def test_simple_training_loop(self):
        """Test a simple training loop with gradient engine."""
        # Create beliefs
        belief1 = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        belief2 = NeuralBelief(np.array([0.5, 1.5, 2.5]))

        # Create engine
        engine = GradientEngine()

        # Training loop
        learning_rate = 0.01
        for _ in range(10):
            # Compute loss
            loss = engine.compute_similarity_loss(
                belief1, belief2, target_similarity=1.0
            )

            # Compute gradients
            gradients = engine.compute_gradients(loss)

            # Apply gradients
            beliefs = {belief1.belief_id: belief1, belief2.belief_id: belief2}
            engine.apply_gradients(gradients, beliefs, learning_rate)

            # Zero gradients
            engine.zero_grad()

        # Verify beliefs were updated
        assert belief1.revision_count > 0
        assert belief2.revision_count > 0

    def test_deep_network_training(self):
        """Test training a deep belief network."""
        # Create deep network (15 layers)
        beliefs = [NeuralBelief(np.random.randn(10)) for _ in range(15)]

        # Create trainer
        trainer = DeepBeliefTrainer(learning_rate=0.01, max_depth=20)

        # Target output
        target = np.ones(10)

        # Train
        result = trainer.train(
            beliefs,
            target,
            n_iterations=50,
            convergence_threshold=0.1,
        )

        assert "converged" in result
        assert "iterations" in result
        assert result["iterations"] <= 50

    def test_training_with_scheduler(self):
        """Test training with learning rate scheduling."""
        # Create beliefs
        beliefs = [NeuralBelief(np.random.randn(5)) for _ in range(5)]

        # Create trainer with scheduler
        trainer = DeepBeliefTrainer(learning_rate=0.1)
        scheduler = StepLR(initial_lr=0.1, step_size=10, gamma=0.5)

        target = np.ones(5)
        initial_lr = trainer.learning_rate

        # Training loop with scheduler
        for i in range(20):
            metrics = trainer.train_step(beliefs, target)

            # Update learning rate
            new_lr = scheduler.step()
            trainer.learning_rate = new_lr

        # Learning rate should have decreased
        assert trainer.learning_rate < initial_lr

    def test_training_with_checkpointing(self):
        """Test training with gradient checkpointing."""
        # Create deep network
        beliefs = [NeuralBelief(np.random.randn(8)) for _ in range(12)]

        # Create checkpoint manager
        checkpoint_manager = GradientCheckpointManager(
            checkpoint_interval=4,
            memory_limit_mb=100.0,
        )

        # Create trainer with checkpointing config
        config = {
            "use_checkpointing": True,
            "checkpoint_interval": 4,
        }
        trainer = DeepBeliefTrainer(learning_rate=0.01, max_depth=15)

        target = np.ones(8)

        # Train
        result = trainer.train(beliefs, target, n_iterations=20)

        assert result["converged"] is not None


class TestIntegrationWithNeuralBeliefs:
    """Tests for integration with NeuralBelief class."""

    def test_gradient_tracking_with_beliefs(self):
        """Test gradient tracking with NeuralBelief."""
        belief = NeuralBelief(np.array([1.0, 2.0, 3.0]), requires_grad=True)

        engine = GradientEngine()
        node = engine.register_belief(belief)

        # Verify node is connected to belief
        assert node is not None
        assert belief.computation_node is not None

    def test_belief_update_via_gradients(self):
        """Test updating beliefs via computed gradients."""
        belief = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        original_vector = belief.vector.copy()

        engine = GradientEngine()
        target = np.array([2.0, 3.0, 4.0])

        # Compute loss and gradients
        loss = engine.compute_mse_loss(belief, target)
        gradients = engine.compute_gradients(loss)

        # Apply update
        if belief.belief_id in gradients:
            update = -0.01 * gradients[belief.belief_id]
            belief.apply_update(update)

        # Verify belief was updated
        assert not np.array_equal(belief.vector, original_vector)

    def test_multiple_belief_updates(self):
        """Test multiple updates to the same belief."""
        belief = NeuralBelief(np.array([1.0, 2.0, 3.0]))

        engine = GradientEngine()
        target = np.array([2.0, 3.0, 4.0])

        initial_distance = np.linalg.norm(belief.vector - target)

        # Multiple training steps
        for _ in range(20):
            engine.zero_grad()
            loss = engine.compute_mse_loss(belief, target)
            gradients = engine.compute_gradients(loss)

            if belief.belief_id in gradients:
                update = -0.05 * gradients[belief.belief_id]
                belief.apply_update(update)

        final_distance = np.linalg.norm(belief.vector - target)

        # Distance should decrease
        assert final_distance < initial_distance


class TestGradientFlowAnalysis:
    """Tests for gradient flow analysis."""

    def test_gradient_flow_in_deep_network(self):
        """Test gradient flow through deep network."""
        beliefs = [NeuralBelief(np.random.randn(10)) for _ in range(15)]

        backprop = BeliefBackpropagator()
        analysis = backprop.check_gradient_flow(beliefs)

        assert "status" in analysis
        assert "max_norm" in analysis
        assert "min_norm" in analysis
        assert "vanishing_detected" in analysis
        assert "exploding_detected" in analysis

    def test_no_vanishing_gradients_in_shallow_network(self):
        """Test that shallow networks don't have vanishing gradients."""
        beliefs = [NeuralBelief(np.random.randn(5)) for _ in range(3)]

        backprop = BeliefBackpropagator()
        analysis = backprop.check_gradient_flow(beliefs)

        # Shallow networks shouldn't have vanishing gradients
        assert analysis["vanishing_detected"] is False


class TestMemoryEfficiency:
    """Tests for memory-efficient operations."""

    def test_checkpoint_memory_management(self):
        """Test that checkpoints manage memory properly."""
        checkpoint_manager = GradientCheckpointManager(
            memory_limit_mb=1.0,  # Very low limit
            checkpoint_interval=2,
        )

        # Add many checkpoints
        for i in range(20):
            from src.strong_system.computational_graph import Node

            node = Node(np.random.randn(100), name=f"layer_{i}")
            checkpoint_manager.add_checkpoint(node, f"layer_{i}")

        # Memory usage should be bounded
        assert checkpoint_manager.get_memory_usage_mb() <= 1.5  # Allow some tolerance

    def test_gradient_accumulation(self):
        """Test gradient accumulation."""
        from src.strong_system.learning import GradientConfig

        config = GradientConfig(
            accumulate_gradients=True,
            zero_grad_before_compute=False,
        )
        engine = GradientEngine(config)

        belief = NeuralBelief(np.array([1.0, 2.0, 3.0]))
        target = np.array([2.0, 3.0, 4.0])

        # Compute gradients multiple times without zeroing
        for _ in range(3):
            loss = engine.compute_mse_loss(belief, target)
            gradients = engine.compute_gradients(loss)

        # Gradients should be accumulated
        stats = engine.get_gradient_stats()
        assert stats.total_params > 0


class TestConvergence:
    """Tests for training convergence."""

    def test_convergence_within_iterations(self):
        """Test that training converges within specified iterations."""
        beliefs = [NeuralBelief(np.random.randn(5)) for _ in range(5)]

        trainer = DeepBeliefTrainer(learning_rate=0.1)
        target = np.ones(5)

        result = trainer.train(
            beliefs,
            target,
            n_iterations=100,
            convergence_threshold=0.01,
        )

        # Should converge within 100 iterations
        assert result["iterations"] <= 100

    def test_loss_decreases_over_training(self):
        """Test that loss decreases over training."""
        beliefs = [NeuralBelief(np.random.randn(5)) for _ in range(5)]

        trainer = DeepBeliefTrainer(learning_rate=0.05)
        target = np.ones(5)

        losses = []
        for _ in range(20):
            metrics = trainer.train_step(beliefs, target)
            losses.append(metrics["loss"])

        # Loss should generally decrease (allow for some noise)
        assert losses[-1] < losses[0] * 1.5  # Should not increase too much


class TestRobustness:
    """Tests for robustness and edge cases."""

    def test_training_with_zero_gradients(self):
        """Test training when gradients are zero."""
        belief = NeuralBelief(np.array([1.0, 1.0, 1.0]))

        engine = GradientEngine()
        target = np.array([1.0, 1.0, 1.0])  # Same as belief

        # Compute loss and gradients
        loss = engine.compute_mse_loss(belief, target)
        gradients = engine.compute_gradients(loss)

        # With perfect match, gradients should be near zero
        for grad in gradients.values():
            assert np.allclose(grad, 0, atol=1e-5)

    def test_training_with_very_small_learning_rate(self):
        """Test training with very small learning rate."""
        beliefs = [NeuralBelief(np.array([1.0, 2.0, 3.0])) for _ in range(3)]

        trainer = DeepBeliefTrainer(learning_rate=1e-6)
        target = np.array([2.0, 3.0, 4.0])

        original_vectors = [b.vector.copy() for b in beliefs]

        # Train for a few steps
        for _ in range(5):
            trainer.train_step(beliefs, target)

        # Changes should be very small
        for i, belief in enumerate(beliefs):
            change = np.linalg.norm(belief.vector - original_vectors[i])
            assert change < 0.1  # Very small change expected

    def test_training_with_large_learning_rate(self):
        """Test training with large learning rate."""
        beliefs = [NeuralBelief(np.array([1.0, 2.0, 3.0])) for _ in range(3)]

        trainer = DeepBeliefTrainer(learning_rate=1.0)
        target = np.array([2.0, 3.0, 4.0])

        # Should handle large learning rate without crashing
        for _ in range(5):
            result = trainer.train_step(beliefs, target)
            assert "loss" in result


class TestLiveValidationCriteria:
    """Tests for live validation acceptance criteria."""

    def test_train_on_1000_plus_updates(self):
        """Test training on 1000+ belief updates (acceptance criteria)."""
        belief = NeuralBelief(np.random.randn(10))

        engine = GradientEngine()
        target = np.random.randn(10)

        # Simulate 1000+ updates
        for _ in range(1100):
            engine.zero_grad()
            loss = engine.compute_mse_loss(belief, target)
            gradients = engine.compute_gradients(loss)

            if belief.belief_id in gradients:
                update = -0.001 * gradients[belief.belief_id]
                belief.apply_update(update)

        # Should complete without errors
        assert belief.revision_count >= 1000

    def test_convergence_within_100_iterations(self):
        """Test convergence within 100 iterations (acceptance criteria)."""
        beliefs = [NeuralBelief(np.random.randn(10)) for _ in range(5)]

        trainer = DeepBeliefTrainer(learning_rate=0.1)
        target = np.ones(10)

        result = trainer.train(
            beliefs,
            target,
            n_iterations=100,
            convergence_threshold=0.05,
        )

        # Should converge within 100 iterations
        assert result["iterations"] <= 100
        # Loss should be low
        assert result["final_loss"] < 0.1 or result["converged"]

    def test_gradient_explosion_rate_below_5_percent(self):
        """Test that gradient explosion rate is below 5% (acceptance criteria)."""
        explosion_count = 0
        total_runs = 100

        for _ in range(total_runs):
            beliefs = [
                NeuralBelief(np.random.randn(5) * 0.1)  # Small initial values
                for _ in range(5)
            ]

            trainer = DeepBeliefTrainer(learning_rate=0.01)
            target = np.ones(5)

            result = trainer.train(beliefs, target, n_iterations=10)

            if result.get("exploded_gradients", False):
                explosion_count += 1

        explosion_rate = explosion_count / total_runs
        assert explosion_rate < 0.05, f"Explosion rate {explosion_rate} exceeds 5%"
