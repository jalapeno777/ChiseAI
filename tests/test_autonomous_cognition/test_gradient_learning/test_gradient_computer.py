"""Unit tests for GradientComputer."""

import pytest
from src.autonomous_cognition.gradient_learning.gradient_computer import (
    GradientComputer,
    GradientResult,
)


class TestGradientComputer:
    """Tests for GradientComputer class."""

    def test_init_default_epsilon(self):
        """Test initialization with default epsilon."""
        gc = GradientComputer()
        assert gc.epsilon == GradientComputer.DEFAULT_EPSILON

    def test_init_custom_epsilon(self):
        """Test initialization with custom epsilon."""
        gc = GradientComputer(epsilon=1e-3)
        assert gc.epsilon == 1e-3

    def test_compute_gradient_simple_quadratic(self):
        """Test gradient computation for f(x) = x^2 at x=3."""

        def metric_fn(params):
            x = params["x"]
            return x**2

        gc = GradientComputer(epsilon=1e-5)
        params = {"x": 3.0}
        result = gc.compute_gradient(metric_fn, params, "quadratic")

        assert isinstance(result, GradientResult)
        assert "x" in result.gradients
        # f'(x) = 2x, so f'(3) = 6
        assert abs(result.gradients["x"] - 6.0) < 1e-3

    def test_compute_gradient_multiple_params(self):
        """Test gradient computation with multiple parameters."""

        def metric_fn(params):
            return params["a"] * 2 + params["b"] * 3

        gc = GradientComputer(epsilon=1e-5)
        params = {"a": 1.0, "b": 2.0}
        result = gc.compute_gradient(metric_fn, params, "linear")

        assert "a" in result.gradients
        assert "b" in result.gradients
        assert abs(result.gradients["a"] - 2.0) < 1e-3
        assert abs(result.gradients["b"] - 3.0) < 1e-3

    def test_compute_gradient_empty_params_raises(self):
        """Test that empty params raises ValueError."""
        gc = GradientComputer()

        with pytest.raises(ValueError, match="cannot be empty"):
            gc.compute_gradient(lambda p: 1.0, {}, "empty")

    def test_compute_gradient_non_callable_raises(self):
        """Test that non-callable metric_fn raises ValueError."""
        gc = GradientComputer()

        with pytest.raises(ValueError, match="must be a callable"):
            gc.compute_gradient("not a function", {"x": 1.0}, "invalid")

    def test_compute_gradient_for_metrics(self):
        """Test computing gradients for multiple metrics."""

        def metric_a(params):
            return params["x"] * 2

        def metric_b(params):
            return params["x"] * 3

        gc = GradientComputer(epsilon=1e-5)
        params = {"x": 1.0}
        results = gc.compute_gradients_for_metrics(
            {"metric_a": metric_a, "metric_b": metric_b}, params
        )

        assert "metric_a" in results
        assert "metric_b" in results
        assert abs(results["metric_a"].gradients["x"] - 2.0) < 1e-3
        assert abs(results["metric_b"].gradients["x"] - 3.0) < 1e-3

    def test_compute_jacobian(self):
        """Test Jacobian matrix computation."""

        def metric_a(params):
            return params["x"] * 2 + params["y"]

        def metric_b(params):
            return params["x"] + params["y"] * 2

        gc = GradientComputer(epsilon=1e-5)
        params = {"x": 1.0, "y": 1.0}
        jacobian = gc.compute_jacobian({"a": metric_a, "b": metric_b}, params)

        assert jacobian["a"]["x"] == pytest.approx(2.0, abs=1e-3)
        assert jacobian["a"]["y"] == pytest.approx(1.0, abs=1e-3)
        assert jacobian["b"]["x"] == pytest.approx(1.0, abs=1e-3)
        assert jacobian["b"]["y"] == pytest.approx(2.0, abs=1e-3)

    def test_gradient_result_dataclass(self):
        """Test GradientResult dataclass."""
        result = GradientResult(
            gradients={"x": 1.0, "y": 2.0},
            metric_name="test_metric",
            epsilon=1e-5,
            timestamp=1234567890.0,
        )

        assert result.gradients["x"] == 1.0
        assert result.gradients["y"] == 2.0
        assert result.metric_name == "test_metric"
        assert result.epsilon == 1e-5
