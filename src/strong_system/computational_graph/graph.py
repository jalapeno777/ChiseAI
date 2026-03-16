"""Graph class for computational graph.

Provides the graph structure for managing nodes and their connections,
with support for topological sorting for execution order.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from src.strong_system.computational_graph.node import Node


class Graph:
    """A computational graph for managing nodes and operations.

    The graph maintains a registry of all nodes and provides methods for:
    - Adding nodes to the graph
    - Connecting nodes with edges
    - Computing topological sort for execution order
    - Traversing the graph

    Attributes:
        nodes: Dictionary mapping node IDs to nodes
        node_counter: Counter for generating unique node IDs
        name: Optional name for the graph
    """

    def __init__(self, name: str | None = None):
        """Initialize an empty computational graph.

        Args:
            name: Optional name for the graph
        """
        self.nodes: dict[int, Node] = {}
        self.node_counter: int = 0
        self.name = name or "Graph"

    def __repr__(self) -> str:
        """Return string representation of the graph."""
        return f"Graph(name='{self.name}', nodes={len(self.nodes)})"

    def __len__(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self.nodes)

    def __contains__(self, node: Node) -> bool:
        """Check if a node is in the graph.

        Args:
            node: The node to check

        Returns:
            True if the node is in the graph
        """
        return any(n is node for n in self.nodes.values())

    def add_node(
        self,
        node: Node,
    ) -> int:
        """Add a node to the graph.

        Args:
            node: The node to add

        Returns:
            The ID assigned to the node
        """
        node_id = self.node_counter
        self.nodes[node_id] = node
        self.node_counter += 1
        return node_id

    def get_node(self, node_id: int) -> Node | None:
        """Get a node by its ID.

        Args:
            node_id: The ID of the node to retrieve

        Returns:
            The node if found, None otherwise
        """
        return self.nodes.get(node_id)

    def remove_node(self, node_id: int) -> Node | None:
        """Remove a node from the graph.

        Args:
            node_id: The ID of the node to remove

        Returns:
            The removed node if it existed, None otherwise
        """
        if node_id not in self.nodes:
            return None

        node = self.nodes.pop(node_id)

        # Remove this node from its parents' children lists
        for parent in node.parents:
            if node in parent.children:
                parent.children.remove(node)

        # Remove this node from its children's parent lists
        for child in node.children:
            if node in child.parents:
                child.parents.remove(node)

        return node

    def connect(self, from_node: Node, to_node: Node) -> None:
        """Create an edge between two nodes.

        This establishes a parent-child relationship where from_node
        is a parent of to_node.

        Args:
            from_node: The source node (parent)
            to_node: The destination node (child)

        Raises:
            ValueError: If either node is not in the graph
        """
        if from_node not in self:
            raise ValueError("from_node must be added to the graph first")
        if to_node not in self:
            raise ValueError("to_node must be added to the graph first")

        # Add parent-child relationship
        if from_node not in to_node.parents:
            to_node.parents.append(from_node)
        if to_node not in from_node.children:
            from_node.children.append(to_node)

    def topological_sort(self) -> list[Node]:
        """Compute topological sort of the graph.

        Returns nodes in an order where all parents come before their children.
        This is the correct execution order for forward passes.

        Uses Kahn's algorithm for topological sorting.

        Returns:
            List of nodes in topological order

        Raises:
            ValueError: If the graph contains a cycle
        """
        # Build in-degree map (count of parents not yet processed)
        in_degree: dict[int, int] = {}
        node_to_id: dict[int, int] = {
            id(node): node_id for node_id, node in self.nodes.items()
        }

        for node_id, node in self.nodes.items():
            # Count parents that are also in the graph
            in_degree[node_id] = sum(1 for parent in node.parents if parent in self)

        # Start with nodes that have no parents in the graph
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])

        result: list[Node] = []

        while queue:
            node_id = queue.popleft()
            node = self.nodes[node_id]
            result.append(node)

            # Decrease in-degree of children
            for child in node.children:
                if child in self:
                    child_id = node_to_id.get(id(child))
                    if child_id is not None and child_id in in_degree:
                        in_degree[child_id] -= 1
                        if in_degree[child_id] == 0:
                            queue.append(child_id)

        # Check for cycles
        if len(result) != len(self.nodes):
            raise ValueError("Graph contains a cycle, cannot perform topological sort")

        return result

    def get_leaf_nodes(self) -> list[Node]:
        """Get all leaf nodes (nodes with no parents in the graph).

        Returns:
            List of leaf nodes
        """
        return [
            node
            for node in self.nodes.values()
            if not any(parent in self for parent in node.parents)
        ]

    def get_output_nodes(self) -> list[Node]:
        """Get all output nodes (nodes with no children in the graph).

        Returns:
            List of output nodes
        """
        return [
            node
            for node in self.nodes.values()
            if not any(child in self for child in node.children)
        ]

    def clear(self) -> None:
        """Remove all nodes from the graph."""
        self.nodes.clear()
        self.node_counter = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert graph to dictionary representation.

        Returns:
            Dictionary containing graph information
        """
        return {
            "name": self.name,
            "node_count": len(self.nodes),
            "nodes": {
                node_id: {
                    "name": node.name,
                    "shape": node.shape,
                    "is_leaf": node.is_leaf,
                    "parent_count": len(node.parents),
                    "child_count": len(node.children),
                }
                for node_id, node in self.nodes.items()
            },
        }

    def get_execution_order(self) -> list[Node]:
        """Get the execution order for the graph.

        This is an alias for topological_sort() with a more descriptive name.

        Returns:
            List of nodes in execution order
        """
        return self.topological_sort()

    def validate(self) -> list[str]:
        """Validate the graph structure.

        Checks for:
        - Cycles in the graph
        - Disconnected nodes
        - Invalid node references

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        # Check for cycles by attempting topological sort
        try:
            self.topological_sort()
        except ValueError as e:
            errors.append(str(e))

        # Check for disconnected nodes
        for node_id, node in self.nodes.items():
            has_connection = any(parent in self for parent in node.parents) or any(
                child in self for child in node.children
            )
            if not has_connection and len(self.nodes) > 1:
                errors.append(
                    f"Node {node_id} is disconnected from the rest of the graph"
                )

        return errors
