"""Node class for computational graph.

Provides the base node implementation for building computational graphs
with support for forward computation and gradient storage (for backward pass).
"""

from __future__ import annotations

from typing import Any

import numpy as np


class Node:
    """A node in the computational graph.

    Represents a value in the computation with support for:
    - Storing computed values
    - Storing gradients (for backpropagation)
    - Tracking parent and child connections
    - Referencing the operation that created this node

    Attributes:
        value: The computed value stored in this node
        gradient: The gradient of the loss with respect to this node's value
        operation: The operation that produced this node (None for leaf nodes)
        parents: List of parent nodes (inputs to the operation)
        children: List of child nodes (nodes that use this as input)
        name: Optional name for debugging/identification
    """

    def __init__(
        self,
        value: np.ndarray | float | int,
        operation: Operation | None = None,
        parents: list[Node] | None = None,
        name: str | None = None,
    ):
        """Initialize a node.

        Args:
            value: The value to store in this node
            operation: The operation that produced this node
            parents: List of parent nodes
            name: Optional name for the node
        """
        # Convert scalar values to numpy arrays
        if isinstance(value, (int, float)):
            self.value = np.array(value, dtype=np.float64)
        else:
            self.value = np.array(value, dtype=np.float64)

        self.gradient: np.ndarray | None = None
        self.operation = operation
        self.parents = parents or []
        self.children: list[Node] = []
        self.name = name

        # Register this node as a child of its parents
        for parent in self.parents:
            parent.children.append(self)

    def __repr__(self) -> str:
        """Return string representation of the node."""
        name_str = f"'{self.name}'" if self.name else ""
        shape_str = f"shape={self.value.shape}"
        grad_str = f" grad={self.gradient is not None}"
        return f"Node({name_str} {shape_str}{grad_str})"

    def __add__(self, other: Node | float | int) -> Node:
        """Add this node with another node or scalar.

        Args:
            other: Another node or scalar value

        Returns:
            A new node representing the sum
        """
        from src.strong_system.computational_graph.operations import Add

        if not isinstance(other, Node):
            other = Node(other)
        return Add.forward(self, other)

    def __radd__(self, other: float | int) -> Node:
        """Add a scalar with this node (reverse addition).

        Args:
            other: A scalar value

        Returns:
            A new node representing the sum
        """
        return self.__add__(other)

    def __sub__(self, other: Node | float | int) -> Node:
        """Subtract another node or scalar from this node.

        Args:
            other: Another node or scalar value

        Returns:
            A new node representing the difference
        """
        from src.strong_system.computational_graph.operations import Add, Multiply

        if not isinstance(other, Node):
            other = Node(other)
        # a - b = a + (-1 * b)
        neg_other = Multiply.forward(other, Node(-1.0))
        return Add.forward(self, neg_other)

    def __rsub__(self, other: float | int) -> Node:
        """Subtract this node from a scalar (reverse subtraction).

        Args:
            other: A scalar value

        Returns:
            A new node representing the difference
        """
        from src.strong_system.computational_graph.operations import Add, Multiply

        # other - self = other + (-1 * self)
        neg_self = Multiply.forward(self, Node(-1.0))
        return Add.forward(Node(other), neg_self)

    def __mul__(self, other: Node | float | int) -> Node:
        """Multiply this node with another node or scalar.

        Args:
            other: Another node or scalar value

        Returns:
            A new node representing the product
        """
        from src.strong_system.computational_graph.operations import Multiply

        if not isinstance(other, Node):
            other = Node(other)
        return Multiply.forward(self, other)

    def __rmul__(self, other: float | int) -> Node:
        """Multiply a scalar with this node (reverse multiplication).

        Args:
            other: A scalar value

        Returns:
            A new node representing the product
        """
        return self.__mul__(other)

    def __matmul__(self, other: Node) -> Node:
        """Matrix multiply this node with another node.

        Args:
            other: Another node for matrix multiplication

        Returns:
            A new node representing the matrix product
        """
        from src.strong_system.computational_graph.operations import MatMul

        return MatMul.forward(self, other)

    def zero_grad(self) -> None:
        """Zero out the gradient for this node."""
        self.gradient = np.zeros_like(self.value)

    def set_grad(self, grad: np.ndarray | float | int) -> None:
        """Set the gradient for this node.

        Args:
            grad: The gradient value
        """
        if isinstance(grad, (int, float)):
            grad = np.array(grad, dtype=np.float64)
        else:
            grad = np.array(grad, dtype=np.float64)

        if self.gradient is None:
            self.gradient = grad
        else:
            self.gradient = self.gradient + grad

    @property
    def shape(self) -> tuple[int, ...]:
        """Return the shape of the node's value."""
        return self.value.shape

    @property
    def ndim(self) -> int:
        """Return the number of dimensions of the node's value."""
        return self.value.ndim

    @property
    def is_leaf(self) -> bool:
        """Check if this is a leaf node (no operation that created it)."""
        return self.operation is None

    @property
    def requires_grad(self) -> bool:
        """Check if this node requires gradient computation.

        For now, all non-leaf nodes require gradients.
        In the future, this could be configurable.
        """
        return not self.is_leaf


class Operation:
    """Base class for operations in the computational graph.

    Operations define how to compute forward passes and (in the future)
    backward passes for automatic differentiation.

    Attributes:
        name: Name of the operation for debugging
    """

    def __init__(self, name: str | None = None):
        """Initialize the operation.

        Args:
            name: Optional name for the operation
        """
        self.name = name or self.__class__.__name__

    def __repr__(self) -> str:
        """Return string representation of the operation."""
        return f"{self.__class__.__name__}(name='{self.name}')"

    @classmethod
    def forward(cls, *inputs: Node, **kwargs: Any) -> Node:
        """Compute the forward pass.

        Args:
            *inputs: Input nodes
            **kwargs: Additional keyword arguments

        Returns:
            A new node containing the result

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement forward()")

    @classmethod
    def backward(cls, grad_output: np.ndarray, *inputs: Node) -> tuple[np.ndarray, ...]:
        """Compute the backward pass (gradients).

        Args:
            grad_output: Gradient of the loss with respect to the output
            *inputs: Input nodes

        Returns:
            Tuple of gradients with respect to each input

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement backward()")
