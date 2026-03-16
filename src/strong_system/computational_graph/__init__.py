"""Computational graph module for the Strong AI System.

This module provides the core computational graph infrastructure for
automatic differentiation and neural network operations.

Components:
    - Node: Base class for graph nodes with value and gradient storage
    - Graph: Container for managing nodes and execution order
    - Operation: Base class for operations (Add, Multiply, ReLU, etc.)

Example:
    >>> from src.strong_system.computational_graph import Graph, Node
    >>> import numpy as np
    >>>
    >>> # Create a simple computation: z = (x + y) * 2
    >>> x = Node(np.array([1.0, 2.0, 3.0]), name="x")
    >>> y = Node(np.array([4.0, 5.0, 6.0]), name="y")
    >>> z = (x + y) * 2
    >>> print(z.value)  # [10. 14. 18.]
"""

from src.strong_system.computational_graph.graph import Graph
from src.strong_system.computational_graph.node import Node, Operation
from src.strong_system.computational_graph.operations import (
    Add,
    MatMul,
    Multiply,
    ReLU,
    Sum,
)

__all__ = [
    "Graph",
    "Node",
    "Operation",
    "Add",
    "Multiply",
    "ReLU",
    "MatMul",
    "Sum",
]
