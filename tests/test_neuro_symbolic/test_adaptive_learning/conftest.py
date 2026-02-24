"""Shared fixtures for adaptive learning tests."""

import numpy as np
import pytest
from src.neuro_symbolic.adaptive_learning.adapter import (
    ModelAdapter,
)
from src.neuro_symbolic.adaptive_learning.engine import (
    AdaptiveLearningEngine,
    EngineConfig,
)
from src.neuro_symbolic.adaptive_learning.feedback import (
    FeedbackIntegrator,
)
from src.neuro_symbolic.adaptive_learning.scheduler import (
    LearningScheduler,
)
from src.neuro_symbolic.learning.base import (
    LearningConfig,
)


@pytest.fixture
def sample_parameters():
    """Sample model parameters for testing."""
    return {
        "weights": np.array([1.0, 2.0, 3.0]),
        "bias": np.array([0.1]),
    }


@pytest.fixture
def sample_gradients():
    """Sample gradients for testing."""
    return {
        "weights": np.array([0.1, -0.1, 0.05]),
        "bias": np.array([-0.01]),
    }


@pytest.fixture
def sample_outcome_profit():
    """Sample profitable trade outcome."""
    return {
        "pnl": 100.0,
        "pnl_pct": 0.05,
        "confidence": 0.8,
        "duration": 3600,
        "exit_reason": "take_profit",
    }


@pytest.fixture
def sample_outcome_loss():
    """Sample losing trade outcome."""
    return {
        "pnl": -50.0,
        "pnl_pct": -0.025,
        "confidence": 0.7,
        "duration": 1800,
        "exit_reason": "stop_loss",
    }


@pytest.fixture
def learning_config():
    """Standard learning configuration for testing."""
    return LearningConfig(
        learning_rate=0.001,
        min_samples_for_adaptation=10,  # Lower for testing
        performance_window=50,
        degradation_threshold=0.1,
        max_adaptations_per_day=100,
    )


@pytest.fixture
def feedback_integrator():
    """FeedbackIntegrator instance for testing."""
    return FeedbackIntegrator()


@pytest.fixture
def model_adapter():
    """ModelAdapter instance for testing."""
    return ModelAdapter()


@pytest.fixture
def learning_scheduler():
    """LearningScheduler instance for testing."""
    return LearningScheduler()


@pytest.fixture
def adaptive_engine():
    """AdaptiveLearningEngine instance for testing."""
    config = EngineConfig(
        learning_config=LearningConfig(min_samples_for_adaptation=10),
    )
    return AdaptiveLearningEngine(config)
