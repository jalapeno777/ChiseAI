"""Shared fixtures for learning module tests."""

import numpy as np
import pytest
from src.strong_system.computational_graph import Node
from src.strong_system.learning import (
    BackpropConfig,
    BeliefBackpropagator,
    GradientCheckpointManager,
    GradientConfig,
    GradientEngine,
)
from src.strong_system.neural_beliefs import NeuralBelief


@pytest.fixture
def sample_belief():
    """Create a sample neural belief for testing."""
    return NeuralBelief(
        vector=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        confidence=0.8,
        source="test",
    )


@pytest.fixture
def sample_beliefs():
    """Create multiple sample beliefs for testing."""
    return [
        NeuralBelief(
            vector=np.array([1.0, 2.0, 3.0]),
            confidence=0.8,
            source="test",
        ),
        NeuralBelief(
            vector=np.array([0.5, 1.5, 2.5]),
            confidence=0.7,
            source="test",
        ),
        NeuralBelief(
            vector=np.array([2.0, 1.0, 0.5]),
            confidence=0.9,
            source="test",
        ),
    ]


@pytest.fixture
def deep_beliefs():
    """Create a deep chain of beliefs for testing."""
    return [
        NeuralBelief(
            vector=np.random.randn(10),
            confidence=0.8,
            source="test",
        )
        for _ in range(15)
    ]


@pytest.fixture
def gradient_engine():
    """Create a gradient engine for testing."""
    return GradientEngine()


@pytest.fixture
def gradient_config():
    """Create a gradient configuration for testing."""
    return GradientConfig(
        clip_norm=1.0,
        clip_value=None,
        accumulate_gradients=False,
        zero_grad_before_compute=True,
    )


@pytest.fixture
def backpropagator():
    """Create a belief backpropagator for testing."""
    config = BackpropConfig(
        max_layers=20,
        use_checkpointing=True,
        checkpoint_interval=5,
    )
    return BeliefBackpropagator(config)


@pytest.fixture
def checkpoint_manager():
    """Create a checkpoint manager for testing."""
    return GradientCheckpointManager(
        memory_limit_mb=100.0,
        checkpoint_interval=3,
    )


@pytest.fixture
def sample_node():
    """Create a sample computational graph node."""
    return Node(
        value=np.array([1.0, 2.0, 3.0]),
        name="test_node",
    )


@pytest.fixture
def target_vector():
    """Create a target vector for loss computation."""
    return np.array([1.5, 2.5, 3.5])
