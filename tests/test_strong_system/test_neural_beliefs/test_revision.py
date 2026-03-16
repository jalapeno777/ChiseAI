"""Tests for BeliefRevisionEngine."""

import numpy as np
import pytest
from src.strong_system.belief_embeddings import ValidationError
from src.strong_system.neural_beliefs import (
    BeliefRevisionEngine,
    LearningRateScheduler,
    NeuralBelief,
    OptimizerConfig,
    OptimizerType,
    RevisionMetrics,
)


class TestOptimizerConfig:
    """Test cases for OptimizerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = OptimizerConfig()

        assert config.optimizer_type == OptimizerType.ADAM
        assert config.learning_rate == 0.001
        assert config.momentum == 0.9
        assert config.beta1 == 0.9
        assert config.beta2 == 0.999
        assert config.epsilon == 1e-8
        assert config.weight_decay == 0.0

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = OptimizerConfig(
            optimizer_type=OptimizerType.SGD,
            learning_rate=0.01,
            momentum=0.95,
        )

        assert config.optimizer_type == OptimizerType.SGD
        assert config.learning_rate == 0.01
        assert config.momentum == 0.95

    def test_invalid_learning_rate(self) -> None:
        """Test validation of invalid learning rate."""
        with pytest.raises(ValidationError):
            OptimizerConfig(learning_rate=0.0)

        with pytest.raises(ValidationError):
            OptimizerConfig(learning_rate=-0.1)

    def test_invalid_momentum(self) -> None:
        """Test validation of invalid momentum."""
        with pytest.raises(ValidationError):
            OptimizerConfig(momentum=1.0)

        with pytest.raises(ValidationError):
            OptimizerConfig(momentum=-0.1)


class TestLearningRateScheduler:
    """Test cases for LearningRateScheduler."""

    def test_constant_schedule(self) -> None:
        """Test constant learning rate schedule."""
        scheduler = LearningRateScheduler(initial_lr=0.01, schedule_type="constant")

        for _ in range(10):
            lr = scheduler.step()
            assert lr == 0.01

    def test_step_schedule(self) -> None:
        """Test step decay schedule."""
        scheduler = LearningRateScheduler(
            initial_lr=0.1,
            schedule_type="step",
            decay_factor=0.5,
            decay_steps=3,
        )

        assert scheduler.step() == 0.1  # Step 1
        assert scheduler.step() == 0.1  # Step 2
        assert scheduler.step() == 0.05  # Step 3 (decay)
        assert scheduler.step() == 0.05  # Step 4

    def test_exponential_schedule(self) -> None:
        """Test exponential decay schedule."""
        scheduler = LearningRateScheduler(
            initial_lr=0.1,
            schedule_type="exponential",
            decay_factor=0.5,
            decay_steps=10,
        )

        lr1 = scheduler.step()
        assert lr1 < 0.1
        assert lr1 > 0

    def test_cosine_schedule(self) -> None:
        """Test cosine annealing schedule."""
        scheduler = LearningRateScheduler(
            initial_lr=0.1,
            schedule_type="cosine",
            decay_steps=10,
            min_lr=0.01,
        )

        lr_start = scheduler.get_lr()
        for _ in range(10):
            scheduler.step()
        lr_end = scheduler.get_lr()

        assert lr_end < lr_start
        assert lr_end >= 0.01

    def test_min_lr_bound(self) -> None:
        """Test minimum learning rate bound."""
        scheduler = LearningRateScheduler(
            initial_lr=0.1,
            schedule_type="step",
            decay_factor=0.1,
            decay_steps=1,
            min_lr=0.01,
        )

        # Decay multiple times
        for _ in range(10):
            scheduler.step()

        assert scheduler.get_lr() >= 0.01

    def test_reset(self) -> None:
        """Test scheduler reset."""
        scheduler = LearningRateScheduler(
            initial_lr=0.1, schedule_type="step", decay_steps=1
        )

        scheduler.step()
        assert scheduler.get_lr() < 0.1

        scheduler.reset()
        assert scheduler.get_lr() == 0.1
        assert scheduler.step_count == 0


class TestBeliefRevisionEngine:
    """Test cases for BeliefRevisionEngine."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        engine = BeliefRevisionEngine()

        assert engine.step_count == 0
        assert engine.config.optimizer_type == OptimizerType.ADAM
        assert isinstance(engine.scheduler, LearningRateScheduler)

    def test_init_custom(self) -> None:
        """Test initialization with custom config."""
        config = OptimizerConfig(optimizer_type=OptimizerType.SGD, learning_rate=0.01)
        scheduler = LearningRateScheduler(initial_lr=0.01, schedule_type="constant")

        engine = BeliefRevisionEngine(config=config, scheduler=scheduler)

        assert engine.config.optimizer_type == OptimizerType.SGD
        assert engine.scheduler.get_lr() == 0.01

    def test_step_sgd(self) -> None:
        """Test SGD optimization step."""
        config = OptimizerConfig(optimizer_type=OptimizerType.SGD, learning_rate=0.1)
        engine = BeliefRevisionEngine(config=config)

        belief = NeuralBelief(vector=np.array([1.0, 2.0, 3.0]))
        belief.set_gradient(np.array([0.1, 0.1, 0.1]))

        initial_vector = belief.vector.copy()
        metrics = engine.step([belief])

        # Vector should have moved in direction opposite to gradient
        assert np.all(belief.vector < initial_vector)
        assert isinstance(metrics, RevisionMetrics)
        assert metrics.step_number == 1
        assert metrics.num_beliefs == 1

    def test_step_momentum(self) -> None:
        """Test Momentum optimization step."""
        config = OptimizerConfig(
            optimizer_type=OptimizerType.MOMENTUM,
            learning_rate=0.1,
            momentum=0.9,
        )
        engine = BeliefRevisionEngine(config=config)

        belief = NeuralBelief(vector=np.array([1.0, 2.0]))
        belief.set_gradient(np.array([0.1, 0.1]))

        metrics = engine.step([belief])

        assert metrics.step_number == 1
        assert belief.revision_count > 0

    def test_step_adam(self) -> None:
        """Test Adam optimization step."""
        config = OptimizerConfig(optimizer_type=OptimizerType.ADAM, learning_rate=0.1)
        engine = BeliefRevisionEngine(config=config)

        belief = NeuralBelief(vector=np.array([1.0, 2.0, 3.0]))
        belief.set_gradient(np.array([0.1, 0.2, 0.3]))

        metrics = engine.step([belief])

        assert metrics.step_number == 1
        assert metrics.learning_rate == 0.1

    def test_step_rmsprop(self) -> None:
        """Test RMSprop optimization step."""
        config = OptimizerConfig(
            optimizer_type=OptimizerType.RMSPROP, learning_rate=0.1
        )
        engine = BeliefRevisionEngine(config=config)

        belief = NeuralBelief(vector=np.array([1.0, 2.0]))
        belief.set_gradient(np.array([0.1, 0.1]))

        metrics = engine.step([belief])

        assert metrics.step_number == 1

    def test_step_multiple_beliefs(self) -> None:
        """Test optimization step with multiple beliefs."""
        engine = BeliefRevisionEngine()

        beliefs = [
            NeuralBelief(vector=np.array([1.0, 2.0])),
            NeuralBelief(vector=np.array([3.0, 4.0])),
        ]

        for belief in beliefs:
            belief.set_gradient(np.array([0.1, 0.1]))

        metrics = engine.step(beliefs)

        assert metrics.num_beliefs == 2

    def test_step_no_gradient(self) -> None:
        """Test step with belief that has no gradient."""
        engine = BeliefRevisionEngine()

        belief = NeuralBelief(vector=np.array([1.0, 2.0]))
        # Don't set gradient

        metrics = engine.step([belief])

        assert metrics.num_beliefs == 1
        # Belief should be unchanged
        assert np.allclose(belief.vector, np.array([1.0, 2.0]))

    def test_gradient_clipping(self) -> None:
        """Test gradient clipping."""
        config = OptimizerConfig(
            optimizer_type=OptimizerType.SGD,
            learning_rate=0.1,
            max_grad_norm=1.0,
        )
        engine = BeliefRevisionEngine(config=config)

        belief = NeuralBelief(vector=np.array([1.0, 2.0]))
        # Large gradient that should be clipped
        belief.set_gradient(np.array([10.0, 10.0]))

        initial_vector = belief.vector.copy()
        engine.step([belief])

        # Update should be limited by clipping
        update_magnitude = np.linalg.norm(initial_vector - belief.vector)
        assert update_magnitude <= 1.0 * 0.1 + 1e-6

    def test_weight_decay(self) -> None:
        """Test L2 weight decay."""
        config = OptimizerConfig(
            optimizer_type=OptimizerType.SGD,
            learning_rate=0.1,
            weight_decay=0.01,
        )
        engine = BeliefRevisionEngine(config=config)

        belief = NeuralBelief(vector=np.array([1.0, 1.0]))
        belief.set_gradient(np.array([0.0, 0.0]))

        engine.step([belief])

        # Weight decay should shrink the vector
        assert np.all(belief.vector < 1.0)

    def test_convergence_detection(self) -> None:
        """Test convergence detection."""
        engine = BeliefRevisionEngine()

        # Initially not converged
        assert not engine.has_converged()

        # Run many steps with small gradients
        belief = NeuralBelief(vector=np.array([1.0, 2.0]))
        for _ in range(15):
            belief.set_gradient(np.array([0.0001, 0.0001]))
            engine.step([belief])

        # Should be converged now
        assert engine.has_converged(threshold=0.9, min_steps=10)

    def test_has_converged_min_steps(self) -> None:
        """Test convergence requires minimum steps."""
        engine = BeliefRevisionEngine()

        # Run a few steps
        belief = NeuralBelief(vector=np.array([1.0]))
        for _ in range(3):
            belief.set_gradient(np.array([0.0001]))
            engine.step([belief])

        # Should not be converged due to min_steps
        assert not engine.has_converged(min_steps=10)

    def test_get_metrics_summary(self) -> None:
        """Test metrics summary."""
        engine = BeliefRevisionEngine()

        # Empty history
        summary = engine.get_metrics_summary()
        assert summary["total_steps"] == 0

        # Run some steps
        belief = NeuralBelief(vector=np.array([1.0, 2.0]))
        for _ in range(5):
            belief.set_gradient(np.array([0.1, 0.1]))
            engine.step([belief])

        summary = engine.get_metrics_summary()
        assert summary["total_steps"] == 5
        assert summary["avg_gradient"] > 0

    def test_reset(self) -> None:
        """Test engine reset."""
        engine = BeliefRevisionEngine()

        belief = NeuralBelief(vector=np.array([1.0]))
        belief.set_gradient(np.array([0.1]))
        engine.step([belief])

        assert engine.step_count == 1
        assert len(engine.history) == 1

        engine.reset()

        assert engine.step_count == 0
        assert len(engine.history) == 0
        assert len(engine.state) == 0

    def test_zero_grad(self) -> None:
        """Test zero_grad method."""
        engine = BeliefRevisionEngine()

        beliefs = [
            NeuralBelief(vector=np.array([1.0])),
            NeuralBelief(vector=np.array([2.0])),
        ]

        for belief in beliefs:
            belief.set_gradient(np.array([0.1]))

        engine.zero_grad(beliefs)

        for belief in beliefs:
            assert belief.gradient is None

    def test_history_tracking(self) -> None:
        """Test that metrics history is tracked."""
        engine = BeliefRevisionEngine()

        belief = NeuralBelief(vector=np.array([1.0, 2.0, 3.0]))

        for i in range(5):
            belief.set_gradient(np.array([0.1 * (i + 1), 0.1, 0.1]))
            engine.step([belief])

        assert len(engine.history) == 5

        for i, metrics in enumerate(engine.history):
            assert metrics.step_number == i + 1
            assert isinstance(metrics.timestamp, type(metrics.timestamp))

    def test_metrics_to_dict(self) -> None:
        """Test RevisionMetrics serialization."""
        metrics = RevisionMetrics(
            step_number=1,
            timestamp=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
            num_beliefs=2,
            avg_gradient_magnitude=0.05,
            max_gradient_magnitude=0.1,
            learning_rate=0.001,
            convergence_score=0.8,
        )

        data = metrics.to_dict()

        assert data["step_number"] == 1
        assert data["num_beliefs"] == 2
        assert data["avg_gradient_magnitude"] == 0.05
        assert data["convergence_score"] == 0.8
