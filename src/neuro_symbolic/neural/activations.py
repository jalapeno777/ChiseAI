"""
Activation functions for neural networks.

Provides common activation functions with their derivatives for backpropagation.
"""

from typing import Union
import numpy as np

ArrayLike = Union[np.ndarray, float]


def relu(x: ArrayLike) -> ArrayLike:
    """Rectified Linear Unit activation function.

    Args:
        x: Input value or array

    Returns:
        ReLU activated output (max(0, x))
    """
    return np.maximum(0, x)


def relu_derivative(x: ArrayLike) -> ArrayLike:
    """Derivative of ReLU function.

    Args:
        x: Input value or array

    Returns:
        1 if x > 0, else 0
    """
    return np.where(x > 0, 1.0, 0.0)


def sigmoid(x: ArrayLike) -> ArrayLike:
    """Sigmoid activation function.

    Args:
        x: Input value or array

    Returns:
        Sigmoid activated output in range (0, 1)
    """
    # Clip to avoid overflow
    x_clipped = np.clip(x, -500, 500)
    return 1.0 / (1.0 + np.exp(-x_clipped))


def sigmoid_derivative(x: ArrayLike) -> ArrayLike:
    """Derivative of sigmoid function.

    Args:
        x: Input value or array (sigmoid output)

    Returns:
        Derivative: sigmoid(x) * (1 - sigmoid(x))
    """
    return x * (1.0 - x)


def tanh(x: ArrayLike) -> ArrayLike:
    """Hyperbolic tangent activation function.

    Args:
        x: Input value or array

    Returns:
        Tanh activated output in range (-1, 1)
    """
    return np.tanh(x)


def tanh_derivative(x: ArrayLike) -> ArrayLike:
    """Derivative of tanh function.

    Args:
        x: Input value or array (tanh output)

    Returns:
        Derivative: 1 - tanh(x)^2
    """
    return 1.0 - x**2


def softmax(x: ArrayLike) -> ArrayLike:
    """Softmax activation function for multi-class classification.

    Args:
        x: Input array (typically logits)

    Returns:
        Probability distribution over classes
    """
    # Subtract max for numerical stability
    x_shifted = x - np.max(x, axis=-1, keepdims=True)
    exp_x = np.exp(x_shifted)
    return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


def softmax_derivative(x: ArrayLike) -> ArrayLike:
    """Derivative of softmax (Jacobian).

    For softmax, this returns the simplified gradient for cross-entropy.
    In practice, use combined softmax-cross-entropy for efficiency.

    Args:
        x: Softmax output probabilities

    Returns:
        Placeholder - full Jacobian computation handled in loss
    """
    # Simplified: actual derivative is Jacobian matrix
    # For cross-entropy loss, gradient simplifies to (p - y)
    return x


def leaky_relu(x: ArrayLike, alpha: float = 0.01) -> ArrayLike:
    """Leaky ReLU activation function.

    Args:
        x: Input value or array
        alpha: Slope for negative values (default: 0.01)

    Returns:
        Leaky ReLU activated output
    """
    return np.where(x > 0, x, alpha * x)


def leaky_relu_derivative(x: ArrayLike, alpha: float = 0.01) -> ArrayLike:
    """Derivative of Leaky ReLU function.

    Args:
        x: Input value or array
        alpha: Slope for negative values

    Returns:
        1 if x > 0, else alpha
    """
    return np.where(x > 0, 1.0, alpha)


def get_activation(name: str):
    """Get activation function by name.

    Args:
        name: Name of activation function

    Returns:
        Tuple of (activation_fn, derivative_fn)

    Raises:
        ValueError: If activation name is not recognized
    """
    activations = {
        "relu": (relu, relu_derivative),
        "sigmoid": (sigmoid, sigmoid_derivative),
        "tanh": (tanh, tanh_derivative),
        "softmax": (softmax, softmax_derivative),
        "leaky_relu": (leaky_relu, leaky_relu_derivative),
    }

    if name not in activations:
        raise ValueError(
            f"Unknown activation: {name}. Available: {list(activations.keys())}"
        )

    return activations[name]
