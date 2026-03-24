"""Differentiable operations for symbolic rules.

Provides soft predicates and fuzzy logic operations that enable
symbolic rules to be differentiated and learned via gradient descent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass


def sigmoid(x: np.ndarray | float, steepness: float = 1.0) -> np.ndarray:
    """Compute the sigmoid function.

    The sigmoid provides a smooth transition from 0 to 1,
    useful for soft thresholding in predicates.

    Args:
        x: Input value(s)
        steepness: Controls the steepness of the transition

    Returns:
        Sigmoid of x: 1 / (1 + exp(-steepness * x))

    Example:
        >>> sigmoid(0.0)  # 0.5
        >>> sigmoid(2.0, steepness=2.0)  # ~0.98
    """
    # Clip to prevent overflow
    x_clipped = np.clip(np.array(x, dtype=np.float64) * steepness, -500, 500)
    return 1.0 / (1.0 + np.exp(-x_clipped))


def soft_predicate(
    value: float | np.ndarray,
    threshold: float,
    steepness: float = 1.0,
    mode: str = "greater",
) -> float | np.ndarray:
    """Create a soft predicate that outputs probabilities.

    Instead of a hard threshold (value > threshold), this returns
    a probability based on how far the value is from the threshold.

    Args:
        value: Input value to evaluate
        threshold: Threshold value
        steepness: Controls how sharp the transition is (higher = sharper)
        mode: Comparison mode - "greater", "less", "equal", "not_equal"

    Returns:
        Probability (0.0 to 1.0) representing predicate satisfaction

    Example:
        >>> soft_predicate(5.0, 3.0)  # ~0.88 (high probability value > 3)
        >>> soft_predicate(2.0, 3.0, mode="less")  # ~0.73 (value < 3)
    """
    value_arr = np.array(value, dtype=np.float64)

    if mode == "greater":
        # P(value > threshold) = sigmoid(value - threshold)
        return sigmoid(value_arr - threshold, steepness)
    elif mode == "less":
        # P(value < threshold) = sigmoid(threshold - value)
        return sigmoid(threshold - value_arr, steepness)
    elif mode == "equal":
        # P(value ≈ threshold) = exp(-steepness * (value - threshold)^2)
        diff = value_arr - threshold
        return np.exp(-steepness * diff * diff)
    elif mode == "not_equal":
        # P(value ≠ threshold) = 1 - P(value ≈ threshold)
        return 1.0 - soft_predicate(value_arr, threshold, steepness, "equal")
    else:
        raise ValueError(
            f"Unknown mode: {mode}. Use 'greater', 'less', 'equal', or 'not_equal'"
        )


def fuzzy_and(
    probabilities: list[float] | np.ndarray, method: str = "product"
) -> float:
    """Combine multiple probabilities with fuzzy AND.

    Args:
        probabilities: List of probabilities to combine
        method: Combination method - "product", "min", "mean"

    Returns:
        Combined probability

    Example:
        >>> fuzzy_and([0.8, 0.9])  # 0.72 (product)
        >>> fuzzy_and([0.8, 0.9], method="min")  # 0.8
    """
    if len(probabilities) == 0:
        return 1.0  # Empty conjunction is true

    probs = np.array(probabilities, dtype=np.float64)

    if method == "product":
        # Product t-norm: P(A and B) = P(A) * P(B)
        return float(np.prod(probs))
    elif method == "min":
        # Minimum t-norm: P(A and B) = min(P(A), P(B))
        return float(np.min(probs))
    elif method == "mean":
        # Average: P(A and B) = mean(P(A), P(B))
        return float(np.mean(probs))
    else:
        raise ValueError(f"Unknown method: {method}. Use 'product', 'min', or 'mean'")


def fuzzy_or(
    probabilities: list[float] | np.ndarray, method: str = "probabilistic"
) -> float:
    """Combine multiple probabilities with fuzzy OR.

    Args:
        probabilities: List of probabilities to combine
        method: Combination method - "probabilistic", "max", "mean"

    Returns:
        Combined probability

    Example:
        >>> fuzzy_or([0.8, 0.9])  # ~0.98 (probabilistic sum)
        >>> fuzzy_or([0.8, 0.9], method="max")  # 0.9
    """
    if len(probabilities) == 0:
        return 0.0  # Empty disjunction is false

    probs = np.array(probabilities, dtype=np.float64)

    if method == "probabilistic":
        # Probabilistic sum: P(A or B) = P(A) + P(B) - P(A)*P(B)
        result = probs[0]
        for p in probs[1:]:
            result = result + p - result * p
        return float(result)
    elif method == "max":
        # Maximum t-conorm: P(A or B) = max(P(A), P(B))
        return float(np.max(probs))
    elif method == "mean":
        # Average
        return float(np.mean(probs))
    else:
        raise ValueError(
            f"Unknown method: {method}. Use 'probabilistic', 'max', or 'mean'"
        )


def fuzzy_not(probability: float) -> float:
    """Fuzzy negation of a probability.

    Args:
        probability: Input probability

    Returns:
        Negated probability: 1 - P

    Example:
        >>> fuzzy_not(0.8)  # 0.2
    """
    return 1.0 - float(probability)


def rule_loss(
    predicted: float | np.ndarray,
    target: float | np.ndarray,
    loss_type: str = "mse",
) -> float:
    """Compute differentiable loss for rule learning.

    Args:
        predicted: Predicted rule activation (0.0 to 1.0)
        target: Target activation (0.0 or 1.0)
        loss_type: Type of loss - "mse", "bce" (binary cross-entropy), "l1"

    Returns:
        Loss value

    Example:
        >>> rule_loss(0.8, 1.0)  # MSE: 0.04
        >>> rule_loss(0.8, 1.0, loss_type="bce")  # Binary cross-entropy
    """
    pred = np.array(predicted, dtype=np.float64)
    tgt = np.array(target, dtype=np.float64)

    if loss_type == "mse":
        # Mean squared error
        return float(np.mean((pred - tgt) ** 2))
    elif loss_type == "l1":
        # L1 loss
        return float(np.mean(np.abs(pred - tgt)))
    elif loss_type == "bce":
        # Binary cross-entropy
        # Clip to prevent log(0)
        pred_clipped = np.clip(pred, 1e-7, 1 - 1e-7)
        return float(
            -np.mean(tgt * np.log(pred_clipped) + (1 - tgt) * np.log(1 - pred_clipped))
        )
    else:
        raise ValueError(f"Unknown loss type: {loss_type}. Use 'mse', 'bce', or 'l1'")


def rule_loss_gradient(
    predicted: float | np.ndarray,
    target: float | np.ndarray,
    loss_type: str = "mse",
) -> np.ndarray:
    """Compute gradient of rule loss with respect to predictions.

    Args:
        predicted: Predicted rule activation
        target: Target activation
        loss_type: Type of loss

    Returns:
        Gradient of loss w.r.t. predictions
    """
    pred = np.array(predicted, dtype=np.float64)
    tgt = np.array(target, dtype=np.float64)

    if loss_type == "mse":
        # d/dx (x - y)^2 = 2(x - y)
        return 2 * (pred - tgt)
    elif loss_type == "l1":
        # d/dx |x - y| = sign(x - y)
        return np.sign(pred - tgt)
    elif loss_type == "bce":
        # d/dx [-y*log(x) - (1-y)*log(1-x)] = -y/x + (1-y)/(1-x)
        pred_clipped = np.clip(pred, 1e-7, 1 - 1e-7)
        return -tgt / pred_clipped + (1 - tgt) / (1 - pred_clipped)
    else:
        raise ValueError(f"Unknown loss type: {loss_type}")


class DifferentiablePredicate:
    """A predicate that can be evaluated differentiably.

    Wraps a predicate function to work with the computational graph
    for gradient-based learning.
    """

    def __init__(
        self,
        name: str,
        predicate_fn: callable,
        steepness: float = 1.0,
    ):
        """Initialize a differentiable predicate.

        Args:
            name: Predicate name
            predicate_fn: Function that computes predicate value
            steepness: Steepness parameter for soft thresholds
        """
        self._name = name
        self.predicate_fn = predicate_fn
        self.steepness = steepness

    @property
    def name(self) -> str:
        """Return the predicate name."""
        return self._name

    def evaluate(self, inputs: dict) -> float:
        """Evaluate the predicate on input data.

        Args:
            inputs: Dictionary of input values

        Returns:
            Predicate probability (0.0 to 1.0)
        """
        return self.predicate_fn(inputs, self.steepness)

    def __call__(self, inputs: dict) -> float:
        """Allow predicate to be called directly."""
        return self.evaluate(inputs)


class DifferentiableAction:
    """An action that can be executed with learned confidence.

    Wraps an action function to work with confidence-weighted execution.
    """

    def __init__(self, name: str, action_fn: callable):
        """Initialize a differentiable action.

        Args:
            name: Action name
            action_fn: Function that executes the action
        """
        self._name = name
        self.action_fn = action_fn

    @property
    def name(self) -> str:
        """Return the action name."""
        return self._name

    def execute(self, inputs: dict, confidence: float) -> any:
        """Execute the action with given confidence.

        Args:
            inputs: Dictionary of input values
            confidence: Rule confidence (0.0 to 1.0)

        Returns:
            Action result
        """
        return self.action_fn(inputs, confidence)

    def __call__(self, inputs: dict, confidence: float = 1.0) -> any:
        """Allow action to be called directly."""
        return self.execute(inputs, confidence)
