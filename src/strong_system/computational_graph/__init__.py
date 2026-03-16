"""Computational graph module for the Strong AI System.

This module provides the core computational graph infrastructure for
automatic differentiation and neural network operations.

Components:
    - Node: Base class for graph nodes with value and gradient storage
    - Graph: Container for managing nodes and execution order
    - Operation: Base class for operations (Add, Multiply, ReLU, etc.)
    - backward: Main entry point for reverse-mode automatic differentiation
    - compute_gradients: Compute gradients for all nodes in a graph
    - clear_gradients: Reset all gradients to None
    - GraphOptimizer: Optimizer for computational graphs
    - MemoryProfiler: Memory profiling utilities

Example:
    >>> from src.strong_system.computational_graph import Graph, Node, backward
    >>> import numpy as np
    >>>
    >>> # Create a simple computation: z = (x + y) * 2
    >>> x = Node(np.array([1.0, 2.0, 3.0]), name="x")
    >>> y = Node(np.array([4.0, 5.0, 6.0]), name="y")
    >>> z = (x + y) * 2
    >>> print(z.value)  # [10. 14. 18.]
    >>>
    >>> # Compute gradients
    >>> backward(z)
    >>> print(x.gradient)  # [2. 2. 2.]
"""

from src.strong_system.computational_graph.autodiff import (
    backward,
    clear_gradients,
    compute_gradients,
)
from src.strong_system.computational_graph.graph import Graph
from src.strong_system.computational_graph.memory import (
    MemoryOptimizer,
    MemoryProfiler,
    MemoryReport,
    estimate_graph_memory,
    format_memory_size,
    profile_memory,
)
from src.strong_system.computational_graph.node import Node, Operation
from src.strong_system.computational_graph.operations import (
    Add,
    MatMul,
    Multiply,
    ReLU,
    Sum,
)
from src.strong_system.computational_graph.optimizer import (
    CheckpointNode,
    CheckpointStrategy,
    GraphOptimizer,
    OptimizationConfig,
    OptimizationResult,
    optimize_graph,
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
    "backward",
    "compute_gradients",
    "clear_gradients",
    # Optimizer exports
    "GraphOptimizer",
    "OptimizationConfig",
    "OptimizationResult",
    "CheckpointStrategy",
    "CheckpointNode",
    "optimize_graph",
    # Memory exports
    "MemoryProfiler",
    "MemoryReport",
    "MemoryOptimizer",
    "profile_memory",
    "estimate_graph_memory",
    "format_memory_size",
]
