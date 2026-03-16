"""Operations for computational graph.

Provides basic operations for the computational graph including
arithmetic operations and activation functions.

Note: Backward pass (auto-differentiation) will be implemented in Slice 2.
"""

from __future__ import annotations

import numpy as np
from src.strong_system.computational_graph.node import Node, Operation


class Add(Operation):
    """Addition operation.

    Computes: output = a + b

    Shape requirements:
        - a and b must be broadcastable to the same shape
    """

    @classmethod
    def forward(cls, a: Node, b: Node) -> Node:
        """Compute the forward pass.

        Args:
            a: First input node
            b: Second input node

        Returns:
            A new node containing a + b
        """
        result_value = a.value + b.value
        return Node(
            value=result_value,
            operation=cls(),
            parents=[a, b],
            name=f"add({a.name or 'a'}, {b.name or 'b'})",
        )

    @classmethod
    def backward(
        cls, grad_output: np.ndarray, a: Node, b: Node
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute the backward pass.

        For addition: d(a + b)/da = 1, d(a + b)/db = 1

        Args:
            grad_output: Gradient of the loss with respect to the output
            a: First input node
            b: Second input node

        Returns:
            Tuple of (grad_a, grad_b)
        """
        # Gradient flows through unchanged for addition
        # Sum over broadcasted dimensions if needed
        grad_a = cls._reduce_grad(grad_output, a.value.shape)
        grad_b = cls._reduce_grad(grad_output, b.value.shape)
        return grad_a, grad_b

    @staticmethod
    def _reduce_grad(grad: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
        """Reduce gradient to match target shape.

        When broadcasting occurs, we need to sum over the broadcasted dimensions.

        Args:
            grad: The gradient to reduce
            target_shape: The target shape

        Returns:
            Reduced gradient
        """
        if grad.shape == target_shape:
            return grad

        # Sum over extra dimensions
        while len(grad.shape) > len(target_shape):
            grad = grad.sum(axis=0)

        # Sum over dimensions where target has size 1
        for i, (g_dim, t_dim) in enumerate(zip(grad.shape, target_shape, strict=False)):
            if t_dim == 1 and g_dim > 1:
                grad = grad.sum(axis=i, keepdims=True)

        return grad


class Multiply(Operation):
    """Element-wise multiplication operation.

    Computes: output = a * b

    Shape requirements:
        - a and b must be broadcastable to the same shape
    """

    @classmethod
    def forward(cls, a: Node, b: Node) -> Node:
        """Compute the forward pass.

        Args:
            a: First input node
            b: Second input node

        Returns:
            A new node containing a * b
        """
        result_value = a.value * b.value
        return Node(
            value=result_value,
            operation=cls(),
            parents=[a, b],
            name=f"mul({a.name or 'a'}, {b.name or 'b'})",
        )

    @classmethod
    def backward(
        cls, grad_output: np.ndarray, a: Node, b: Node
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute the backward pass.

        For multiplication: d(a * b)/da = b, d(a * b)/db = a

        Args:
            grad_output: Gradient of the loss with respect to the output
            a: First input node
            b: Second input node

        Returns:
            Tuple of (grad_a, grad_b)
        """
        grad_a = grad_output * b.value
        grad_b = grad_output * a.value

        # Reduce if broadcasting occurred
        grad_a = Add._reduce_grad(grad_a, a.value.shape)
        grad_b = Add._reduce_grad(grad_b, b.value.shape)

        return grad_a, grad_b


class ReLU(Operation):
    """Rectified Linear Unit activation function.

    Computes: output = max(0, x)

    Shape requirements:
        - Input can be any shape
        - Output has the same shape as input
    """

    @classmethod
    def forward(cls, x: Node) -> Node:
        """Compute the forward pass.

        Args:
            x: Input node

        Returns:
            A new node containing max(0, x)
        """
        result_value = np.maximum(0, x.value)
        return Node(
            value=result_value,
            operation=cls(),
            parents=[x],
            name=f"relu({x.name or 'x'})",
        )

    @classmethod
    def backward(cls, grad_output: np.ndarray, x: Node) -> tuple[np.ndarray]:
        """Compute the backward pass.

        For ReLU: d(max(0, x))/dx = 1 if x > 0 else 0

        Args:
            grad_output: Gradient of the loss with respect to the output
            x: Input node

        Returns:
            Tuple of (grad_x,)
        """
        grad_x = grad_output * (x.value > 0).astype(np.float64)
        return (grad_x,)


class MatMul(Operation):
    """Matrix multiplication operation.

    Computes: output = a @ b

    Shape requirements:
        - a.shape[-1] must equal b.shape[-2]
        - Supports broadcasting over batch dimensions
    """

    @classmethod
    def forward(cls, a: Node, b: Node) -> Node:
        """Compute the forward pass.

        Args:
            a: First input node (left matrix)
            b: Second input node (right matrix)

        Returns:
            A new node containing a @ b

        Raises:
            ValueError: If matrix dimensions are incompatible
        """
        try:
            result_value = np.matmul(a.value, b.value)
        except ValueError as e:
            raise ValueError(
                f"Matrix multiplication shape mismatch: {a.shape} @ {b.shape}"
            ) from e

        return Node(
            value=result_value,
            operation=cls(),
            parents=[a, b],
            name=f"matmul({a.name or 'a'}, {b.name or 'b'})",
        )

    @classmethod
    def backward(
        cls, grad_output: np.ndarray, a: Node, b: Node
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute the backward pass.

        For matrix multiplication:
            d(a @ b)/da = grad_output @ b.T
            d(a @ b)/db = a.T @ grad_output

        Args:
            grad_output: Gradient of the loss with respect to the output
            a: First input node
            b: Second input node

        Returns:
            Tuple of (grad_a, grad_b)
        """
        grad_a = np.matmul(grad_output, b.value.T)
        grad_b = np.matmul(a.value.T, grad_output)
        return grad_a, grad_b


class Sum(Operation):
    """Sum reduction operation.

    Computes: output = sum(input, axis=axis, keepdims=keepdims)

    Attributes:
        axis: Axis or axes to sum over (None for all axes)
        keepdims: Whether to keep reduced dimensions
    """

    def __init__(
        self, axis: int | tuple[int, ...] | None = None, keepdims: bool = False
    ):
        """Initialize the sum operation.

        Args:
            axis: Axis or axes to sum over (None for all axes)
            keepdims: Whether to keep reduced dimensions
        """
        super().__init__(name=f"Sum(axis={axis}, keepdims={keepdims})")
        self.axis = axis
        self.keepdims = keepdims

    @classmethod
    def forward(
        cls, x: Node, axis: int | tuple[int, ...] | None = None, keepdims: bool = False
    ) -> Node:
        """Compute the forward pass.

        Args:
            x: Input node
            axis: Axis or axes to sum over
            keepdims: Whether to keep reduced dimensions

        Returns:
            A new node containing the sum
        """
        result_value = np.sum(x.value, axis=axis, keepdims=keepdims)
        return Node(
            value=result_value,
            operation=cls(axis=axis, keepdims=keepdims),
            parents=[x],
            name=f"sum({x.name or 'x'})",
        )

    @classmethod
    def backward(
        cls,
        grad_output: np.ndarray,
        x: Node,
        axis: int | tuple[int, ...] | None = None,
        keepdims: bool = False,
    ) -> tuple[np.ndarray]:
        """Compute the backward pass.

        For sum: gradient is broadcast back to input shape

        Args:
            grad_output: Gradient of the loss with respect to the output
            x: Input node
            axis: Axis or axes that were summed over
            keepdims: Whether dimensions were kept

        Returns:
            Tuple of (grad_x,)
        """
        if not keepdims and axis is not None:
            # Need to expand grad_output to match input shape
            grad_output = np.expand_dims(grad_output, axis=axis)

        # Broadcast to input shape
        grad_x = np.broadcast_to(grad_output, x.value.shape)
        return (grad_x,)
