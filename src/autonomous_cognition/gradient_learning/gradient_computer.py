"""Gradient computation using finite differences for evaluation metrics.

This module computes numerical gradients of evaluation metrics with respect
to tunable parameters using finite differences method.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GradientResult:
    """Result of gradient computation.

    Attributes:
        gradients: Dictionary mapping parameter names to their gradients
        metric_name: Name of the metric the gradients were computed for
        epsilon: Step size used for finite differences
        timestamp: When the gradient was computed
    """

    gradients: dict[str, float]
    metric_name: str
    epsilon: float
    timestamp: float


class GradientComputer:
    """Computes numerical gradients using finite differences.

    Uses central finite differences for gradient computation:
    f'(x) ≈ (f(x + h) - f(x - h)) / (2 * h)

    Attributes:
        epsilon: Step size for finite differences
        default_epsilon: Class-level default epsilon
    """

    DEFAULT_EPSILON = 1e-5

    def __init__(self, epsilon: float | None = None):
        """Initialize the gradient computer.

        Args:
            epsilon: Step size for finite differences. If None, uses default.
        """
        self.epsilon = epsilon or self.DEFAULT_EPSILON
        logger.debug("GradientComputer initialized with epsilon=%s", self.epsilon)

    def compute_gradient(
        self,
        metric_fn: Callable[[dict[str, float]], float],
        params: dict[str, float],
        metric_name: str = "metric",
    ) -> GradientResult:
        """Compute gradients of a metric with respect to parameters.

        Args:
            metric_fn: Function that takes parameters and returns a metric value.
                      Must be deterministic.
            params: Current parameter values as {name: value}
            metric_name: Name of the metric for record keeping

        Returns:
            GradientResult containing computed gradients

        Raises:
            ValueError: If params is empty or metric_fn is not callable
        """
        if not params:
            raise ValueError("Parameters dictionary cannot be empty")
        if not callable(metric_fn):
            raise ValueError("metric_fn must be a callable")

        gradients: dict[str, float] = {}

        # Compute gradient for each parameter using central finite differences
        for param_name, param_value in params.items():
            # Ensure we work with a float value
            if not isinstance(param_value, (int, float)):
                raise ValueError(
                    f"Parameter {param_name} must be a number, got {type(param_value)}"
                )

            # Create perturbed parameter dictionaries
            params_plus = params.copy()
            params_minus = params.copy()

            epsilon = self.epsilon
            # Scale epsilon for large parameter values to maintain precision
            if abs(param_value) > 1.0:
                epsilon = self.epsilon * max(1.0, abs(param_value))

            params_plus[param_name] = param_value + epsilon
            params_minus[param_name] = param_value - epsilon

            # Compute metric at perturbed points
            metric_plus = metric_fn(params_plus)
            metric_minus = metric_fn(params_minus)

            # Central finite difference gradient
            gradient = (metric_plus - metric_minus) / (2 * epsilon)
            gradients[param_name] = gradient

            logger.debug(
                "Gradient for %s: %.6f (perturbed: +%.2e -> %.4f, -%.2e -> %.4f)",
                param_name,
                gradient,
                epsilon,
                metric_plus,
                epsilon,
                metric_minus,
            )

        import time

        return GradientResult(
            gradients=gradients,
            metric_name=metric_name,
            epsilon=self.epsilon,
            timestamp=time.time(),
        )

    def compute_gradients_for_metrics(
        self,
        metric_fns: dict[str, Callable[[dict[str, float]], float]],
        params: dict[str, float],
    ) -> dict[str, GradientResult]:
        """Compute gradients for multiple metrics simultaneously.

        More efficient than calling compute_gradient multiple times when
        the metrics share computation.

        Args:
            metric_fns: Dictionary of {metric_name: metric_function}
            params: Current parameter values

        Returns:
            Dictionary of {metric_name: GradientResult}
        """
        results: dict[str, GradientResult] = {}

        for metric_name, metric_fn in metric_fns.items():
            try:
                result = self.compute_gradient(metric_fn, params, metric_name)
                results[metric_name] = result
            except Exception as e:
                logger.warning(
                    "Failed to compute gradient for metric %s: %s", metric_name, e
                )

        return results

    def compute_jacobian(
        self,
        metric_fns: dict[str, Callable[[dict[str, float]], float]],
        params: dict[str, float],
    ) -> dict[str, dict[str, float]]:
        """Compute Jacobian matrix (gradients of all metrics w.r.t. all params).

        Args:
            metric_fns: Dictionary of {metric_name: metric_function}
            params: Current parameter values

        Returns:
            Dictionary of {metric_name: {param_name: gradient}}
        """
        jacobian: dict[str, dict[str, float]] = {}

        # Compute gradients for each metric
        gradient_results = self.compute_gradients_for_metrics(metric_fns, params)

        for metric_name, gradient_result in gradient_results.items():
            jacobian[metric_name] = gradient_result.gradients

        return jacobian
