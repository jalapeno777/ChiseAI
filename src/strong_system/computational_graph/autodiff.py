"""Auto-differentiation engine for the computational graph.

Provides reverse-mode automatic differentiation for computing gradients
through the computational graph using topological sort.

Example:
    >>> from src.strong_system.computational_graph import Node, backward
    >>> import numpy as np
    >>>
    >>> # Simple gradient: y = x^2
    >>> x = Node(3.0, name="x")
    >>> y = x * x
    >>> backward(y)
    >>> print(x.gradient)  # 6.0 (dy/dx = 2*x)

    >>> # Matrix multiplication gradient
    >>> A = Node(np.array([[1.0, 2.0], [3.0, 4.0]]), name="A")
    >>> B = Node(np.array([[5.0, 6.0], [7.0, 8.0]]), name="B")
    >>> C = A @ B  # Matrix multiplication
    >>> backward(C)
    >>> print(A.gradient)  # Gradient w.r.t. A
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.strong_system.computational_graph.node import Node


def backward(
    output_node: Node, grad_output: np.ndarray | float | int | None = None
) -> None:
    """Compute gradients via reverse-mode automatic differentiation.

    This is the main entry point for backpropagation. It computes gradients
    for all nodes that contribute to the output_node by traversing the
    computational graph in reverse topological order.

    The gradient of the output with respect to itself is 1.0 by default,
    but can be specified via grad_output for multi-output scenarios or
    when computing gradients of intermediate nodes.

    Args:
        output_node: The output node to compute gradients from.
        grad_output: The gradient of the loss with respect to the output.
                     Defaults to 1.0 (computing dy/dy).

    Example:
        >>> x = Node(3.0, name="x")
        >>> y = x * x  # y = x^2
        >>> backward(y)
        >>> assert x.gradient == 6.0  # dy/dx = 2*x = 6

        >>> # With custom grad_output
        >>> x = Node(3.0, name="x")
        >>> y = x * x
        >>> backward(y, grad_output=2.0)  # dL/dy = 2.0
        >>> assert x.gradient == 12.0  # dL/dx = 2 * 2*x = 12
    """
    # Default gradient is 1.0 (dy/dy)
    if grad_output is None:
        grad_output = np.ones_like(output_node.value, dtype=np.float64)
    elif isinstance(grad_output, (int, float)):
        grad_output = np.array(grad_output, dtype=np.float64)
    else:
        grad_output = np.array(grad_output, dtype=np.float64)

    # Set the initial gradient on the output node
    output_node.gradient = grad_output

    # Get all nodes reachable from output_node in reverse topological order
    # (children before parents, so we process from output back to inputs)
    nodes = _get_reverse_topological_order(output_node)

    # Process each node to propagate gradients to its parents
    for node in nodes:
        # Skip leaf nodes (they don't have operations to backprop through)
        if node.operation is None:
            continue

        # Skip nodes without gradients (they weren't on the path to output)
        if node.gradient is None:
            continue

        # Get the operation's backward method
        operation = node.operation

        # Call the backward method to get gradients w.r.t. inputs
        # The backward method signature varies by operation number of inputs
        parent_grads = operation.backward(node.gradient, *node.parents)

        # Accumulate gradients to parent nodes
        for parent, parent_grad in zip(node.parents, parent_grads, strict=True):
            parent.set_grad(parent_grad)


def compute_gradients(graph: Graph, output_node: Node) -> dict[Node, np.ndarray]:
    """Compute gradients for all nodes in a graph with respect to an output.

    This is a higher-level interface that works with a Graph object and returns
    a dictionary mapping nodes to their gradients.

    Args:
        graph: The computational graph containing all nodes.
        output_node: The output node to compute gradients from.

    Returns:
        Dictionary mapping each node to its computed gradient.

    Example:
        >>> graph = Graph()
        >>> x = Node(2.0, name="x")
        >>> y = Node(3.0, name="y")
        >>> z = x * y + x  # z = xy + x
        >>>
        >>> gradients = compute_gradients(graph, z)
        >>> print(gradients[x])  # dz/dx = y + 1 = 4.0
        >>> print(gradients[y])  # dz/dy = x = 2.0
    """
    # Clear all existing gradients
    clear_gradients(graph)

    # Run backpropagation
    backward(output_node)

    # Collect gradients into a dictionary
    gradients = {}
    for node in graph.nodes.values():
        if node.gradient is not None:
            gradients[node] = node.gradient

    return gradients


def clear_gradients(graph: Graph) -> None:
    """Clear all gradients in a graph.

    Resets the gradient field of all nodes in the graph to None.
    This should be called before each backward pass to ensure clean
    gradient computation.

    Args:
        graph: The computational graph to clear gradients from.

    Example:
        >>> graph = Graph()
        >>> x = Node(2.0, name="x")
        >>> y = x * x
        >>> backward(y)
        >>> print(x.gradient)  # 4.0
        >>>
        >>> clear_gradients(graph)
        >>> print(x.gradient)  # None
    """
    for node in graph.nodes.values():
        node.gradient = None


def _get_reverse_topological_order(output_node: Node) -> list[Node]:
    """Get all nodes reachable from output_node in reverse topological order.

    This performs a breadth-first search from the output node and returns
    nodes in an order where children come before their parents. This is the
    correct order for backpropagation (process output first, then propagate
    backward to inputs).

    Args:
        output_node: The output node to start from.

    Returns:
        List of nodes in reverse topological order (output first, inputs last).
    """
    # Use BFS to find all reachable nodes
    visited: set[int] = set()
    queue: deque[Node] = deque([output_node])
    all_nodes: list[Node] = []

    while queue:
        node = queue.popleft()
        node_id = id(node)

        if node_id in visited:
            continue

        visited.add(node_id)
        all_nodes.append(node)

        # Add parents to queue (we want to process them after children)
        for parent in node.parents:
            if id(parent) not in visited:
                queue.append(parent)

    # all_nodes is in BFS order (output first, then parents)
    # This is already reverse topological order for backprop
    return all_nodes


# Import Graph at the end to avoid circular imports
from src.strong_system.computational_graph.graph import Graph  # noqa: E402
