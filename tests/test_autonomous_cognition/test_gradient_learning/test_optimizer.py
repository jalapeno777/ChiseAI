"""Unit tests for Optimizer (SGD and Adam)."""

import pytest
from src.autonomous_cognition.gradient_learning.optimizer import (
    Optimizer,
    SGD,
    Adam,
    OptimizerState,
)


class TestSGD:
    """Tests for SGD optimizer."""

    def test_init_default(self):
        """Test SGD initialization with defaults."""
        sgd = SGD(learning_rate=0.1)
        assert sgd.learning_rate == 0.1
        assert sgd.momentum == 0.0
        assert sgd.weight_decay == 0.0

    def test_init_with_momentum(self):
        """Test SGD initialization with momentum."""
        sgd = SGD(learning_rate=0.1, momentum=0.9)
        assert sgd.momentum == 0.9

    def test_init_with_weight_decay(self):
        """Test SGD initialization with weight decay."""
        sgd = SGD(learning_rate=0.1, weight_decay=0.01)
        assert sgd.weight_decay == 0.01

    def test_step_basic(self):
        """Test basic SGD step."""
        sgd = SGD(learning_rate=0.1)
        params = {"x": 1.0}
        gradients = {"x": 1.0}

        updated = sgd.step(params, gradients)
        assert updated["x"] == pytest.approx(0.9)  # 1.0 - 0.1 * 1.0

    def test_step_with_momentum(self):
        """Test SGD step with momentum."""
        sgd = SGD(learning_rate=0.1, momentum=0.9)
        params = {"x": 0.0}
        gradients = {"x": 1.0}

        # First step
        updated1 = sgd.step(params, gradients)
        # v = 0.9 * 0 + 1.0 = 1.0
        # x = 0 - 0.1 * 1.0 = -0.1
        assert updated1["x"] == pytest.approx(-0.1)

        # Second step with accumulated momentum
        params = updated1
        updated2 = sgd.step(params, gradients)
        # v = 0.9 * 1.0 + 1.0 = 1.9
        # x = -0.1 - 0.1 * 1.9 = -0.29
        assert updated2["x"] == pytest.approx(-0.29)

    def test_step_with_weight_decay(self):
        """Test SGD step with L2 regularization."""
        sgd = SGD(learning_rate=0.1, weight_decay=0.1)
        params = {"x": 1.0}
        gradients = {"x": 0.0}  # Zero gradient

        updated = sgd.step(params, gradients)
        # With weight_decay: gradient = 0 + 0.1 * 1.0 = 0.1
        # x = 1.0 - 0.1 * 0.1 = 0.99
        assert updated["x"] == pytest.approx(0.99)

    def test_step_unknown_param(self):
        """Test step with unknown parameter uses zero gradient."""
        sgd = SGD(learning_rate=0.1)
        params = {"x": 1.0, "y": 2.0}
        gradients = {"x": 1.0}  # No gradient for y

        updated = sgd.step(params, gradients)
        assert updated["x"] == pytest.approx(0.9)
        assert updated["y"] == 2.0  # Unchanged

    def test_get_state(self):
        """Test getting optimizer state."""
        sgd = SGD(learning_rate=0.1, momentum=0.9)
        params = {"x": 1.0}
        gradients = {"x": 1.0}
        sgd.step(params, gradients)

        state = sgd.get_state()
        assert state["type"] == "SGD"
        assert state["learning_rate"] == 0.1
        assert state["momentum"] == 0.9
        assert "param_state" in state

    def test_load_state(self):
        """Test loading optimizer state."""
        sgd = SGD(learning_rate=0.1, momentum=0.9)
        params = {"x": 1.0}
        gradients = {"x": 1.0}
        sgd.step(params, gradients)

        state = sgd.get_state()
        new_sgd = SGD(learning_rate=0.2)
        new_sgd.load_state(state)

        assert new_sgd.learning_rate == 0.1
        assert new_sgd.momentum == 0.9


class TestAdam:
    """Tests for Adam optimizer."""

    def test_init_default(self):
        """Test Adam initialization with defaults."""
        adam = Adam(learning_rate=0.001)
        assert adam.learning_rate == 0.001
        assert adam.beta1 == 0.9
        assert adam.beta2 == 0.999
        assert adam.epsilon == 1e-8

    def test_step_basic(self):
        """Test basic Adam step."""
        adam = Adam(learning_rate=0.1)
        params = {"x": 0.0}
        gradients = {"x": 1.0}

        updated = adam.step(params, gradients)
        # First step: bias correction applied
        # m = 0.9 * 0 + 0.1 * 1 = 0.1
        # v = 0.999 * 0 + 0.001 * 1 = 0.001
        # m_hat = 0.1 / (1 - 0.9) = 1.0
        # v_hat = 0.001 / (1 - 0.999) = 1.0
        # update = 0.1 * 1.0 / (sqrt(1.0) + 1e-8) = 0.1
        # x = 0 - 0.1 = -0.1
        assert updated["x"] == pytest.approx(-0.1, abs=0.01)

    def test_step_accumulates_moments(self):
        """Test that Adam accumulates first and second moments."""
        adam = Adam(learning_rate=0.1)
        params = {"x": 0.0}
        gradients = {"x": 1.0}

        # Multiple steps
        for _ in range(10):
            updated = adam.step(params, gradients)
            params = updated

        # Should have moved in negative direction
        assert updated["x"] < 0

    def test_adam_vs_sgd_convergence(self):
        """Test that Adam and SGD converge differently."""
        sgd = SGD(learning_rate=0.1)
        adam = Adam(learning_rate=0.1)

        # Quadratic function: f(x) = (x - 2)^2, gradient = 2(x - 2)
        def quadratic_grad(x):
            return 2 * (x - 2)

        sgd_params = {"x": 0.0}
        adam_params = {"x": 0.0}

        for _ in range(100):
            grad = quadratic_grad(sgd_params["x"])
            sgd_params = sgd.step(sgd_params, {"x": grad})

            grad = quadratic_grad(adam_params["x"])
            adam_params = adam.step(adam_params, {"x": grad})

        # Both should converge towards 2
        assert sgd_params["x"] == pytest.approx(2.0, abs=0.5)
        assert adam_params["x"] == pytest.approx(2.0, abs=0.5)

    def test_get_state(self):
        """Test getting Adam optimizer state."""
        adam = Adam(learning_rate=0.001, beta1=0.9, beta2=0.99)
        params = {"x": 1.0}
        gradients = {"x": 1.0}
        adam.step(params, gradients)

        state = adam.get_state()
        assert state["type"] == "Adam"
        assert state["learning_rate"] == 0.001
        assert state["beta1"] == 0.9
        assert state["beta2"] == 0.99
        assert "param_state" in state

    def test_load_state(self):
        """Test loading Adam optimizer state."""
        adam = Adam(learning_rate=0.001)
        params = {"x": 1.0}
        gradients = {"x": 1.0}
        adam.step(params, gradients)

        state = adam.get_state()
        new_adam = Adam(learning_rate=0.002)
        new_adam.load_state(state)

        assert new_adam.learning_rate == 0.001
        assert new_adam.beta1 == 0.9
        assert new_adam.beta2 == 0.999


class TestOptimizerState:
    """Tests for OptimizerState dataclass."""

    def test_default_values(self):
        """Test OptimizerState default values."""
        state = OptimizerState(param_name="x", value=1.0)
        assert state.param_name == "x"
        assert state.value == 1.0
        assert state.gradient == 0.0
        assert state.momentum == 0.0
        assert state.velocity == 0.0
        assert state.step == 0
