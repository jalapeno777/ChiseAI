"""Data models for experiment lineage tracking.

This module defines the data structures used for tracking experiment lineage,
including data sources, experiments, and models in a graph structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    """Types of nodes in the lineage graph."""

    DATA = "data"
    MODEL = "model"
    EXPERIMENT = "experiment"


class RelationshipType(str, Enum):
    """Types of relationships between lineage nodes."""

    DERIVED_FROM = "derived_from"
    TRAINED_ON = "trained_on"
    PARENT_OF = "parent_of"


@dataclass(frozen=True)
class LineageNode:
    """Represents a node in the lineage graph.

    Attributes:
        node_id: Unique identifier for the node
        node_type: Type of node (data, model, experiment)
        metadata: Additional metadata for the node
        created_at: Timestamp when the node was created
    """

    node_id: str
    node_type: NodeType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate the node after initialization."""
        if not self.node_id:
            raise ValueError("node_id cannot be empty")

        if not isinstance(self.node_type, NodeType):
            raise ValueError(
                f"node_type must be a NodeType enum, got {type(self.node_type)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert node to dictionary for serialization.

        Returns:
            Dictionary representation of the node
        """
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineageNode:
        """Create a LineageNode from a dictionary.

        Args:
            data: Dictionary containing node data

        Returns:
            LineageNode instance
        """
        timestamp_str = data.get("created_at")
        if timestamp_str:
            created_at = datetime.fromisoformat(timestamp_str)
        else:
            created_at = datetime.now(UTC)

        return cls(
            node_id=data["node_id"],
            node_type=NodeType(data["node_type"]),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


@dataclass(frozen=True)
class LineageEdge:
    """Represents a relationship between two lineage nodes.

    Attributes:
        edge_id: Unique identifier for the edge
        source_id: ID of the source node
        target_id: ID of the target node
        relationship_type: Type of relationship (derived_from, trained_on, parent_of)
        metadata: Additional metadata for the edge
        created_at: Timestamp when the edge was created
    """

    edge_id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate the edge after initialization."""
        if not self.edge_id:
            raise ValueError("edge_id cannot be empty")

        if not self.source_id:
            raise ValueError("source_id cannot be empty")

        if not self.target_id:
            raise ValueError("target_id cannot be empty")

        if self.source_id == self.target_id:
            raise ValueError("source_id and target_id cannot be the same")

        if not isinstance(self.relationship_type, RelationshipType):
            raise ValueError(
                f"relationship_type must be a RelationshipType enum, got {type(self.relationship_type)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert edge to dictionary for serialization.

        Returns:
            Dictionary representation of the edge
        """
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineageEdge:
        """Create a LineageEdge from a dictionary.

        Args:
            data: Dictionary containing edge data

        Returns:
            LineageEdge instance
        """
        timestamp_str = data.get("created_at")
        if timestamp_str:
            created_at = datetime.fromisoformat(timestamp_str)
        else:
            created_at = datetime.now(UTC)

        return cls(
            edge_id=data["edge_id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relationship_type=RelationshipType(data["relationship_type"]),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


@dataclass
class LineageGraph:
    """Container for nodes and edges in a lineage graph.

    Attributes:
        nodes: Dictionary mapping node_id to LineageNode
        edges: List of LineageEdge connections
    """

    nodes: dict[str, LineageNode] = field(default_factory=dict)
    edges: list[LineageEdge] = field(default_factory=list)

    def add_node(self, node: LineageNode) -> LineageNode:
        """Add a node to the graph.

        Args:
            node: The node to add

        Returns:
            The added node

        Raises:
            ValueError: If a node with the same ID already exists
        """
        if node.node_id in self.nodes:
            raise ValueError(f"Node with ID '{node.node_id}' already exists")

        self.nodes[node.node_id] = node
        return node

    def add_edge(self, edge: LineageEdge) -> LineageEdge:
        """Add an edge to the graph.

        Args:
            edge: The edge to add

        Returns:
            The added edge

        Raises:
            ValueError: If the edge references non-existent nodes
        """
        if edge.source_id not in self.nodes:
            raise ValueError(f"Source node '{edge.source_id}' does not exist")

        if edge.target_id not in self.nodes:
            raise ValueError(f"Target node '{edge.target_id}' does not exist")

        self.edges.append(edge)
        return edge

    def get_node(self, node_id: str) -> LineageNode | None:
        """Get a node by its ID.

        Args:
            node_id: The node ID to look up

        Returns:
            The node if found, None otherwise
        """
        return self.nodes.get(node_id)

    def get_parents(self, node_id: str) -> list[LineageEdge]:
        """Get all edges where this node points to its parents (outgoing edges).

        For example, if experiment "exp" has edge exp->data with TRAINED_ON,
        then "data" is the parent of "exp".

        Args:
            node_id: The node ID to find parents for

        Returns:
            List of edges where this node is the source (pointing to parents)
        """
        return [edge for edge in self.edges if edge.source_id == node_id]

    def get_children(self, node_id: str) -> list[LineageEdge]:
        """Get all edges where other nodes point to this node (incoming edges).

        For example, if model "model" has edge model->exp with DERIVED_FROM,
        then "model" is a child of "exp".

        Args:
            node_id: The node ID to find children for

        Returns:
            List of edges where this node is the target (pointed from children)
        """
        return [edge for edge in self.edges if edge.target_id == node_id]

    def get_ancestors(
        self, node_id: str, visited: set[str] | None = None
    ) -> LineageGraph:
        """Get all ancestor nodes (parents, grandparents, etc.).

        Args:
            node_id: The node ID to find ancestors for
            visited: Set of already visited node IDs (for cycle detection)

        Returns:
            LineageGraph containing all ancestors
        """
        if visited is None:
            visited = set()

        if node_id in visited:
            return LineageGraph()

        visited.add(node_id)
        result = LineageGraph()

        # Get direct parents (outgoing edges from this node to parents)
        parent_edges = self.get_parents(node_id)

        for edge in parent_edges:
            # The target of an outgoing edge is the parent
            parent_node = self.nodes.get(edge.target_id)
            if parent_node:
                result.add_node(parent_node)
                # Add edge directly without validation (source may not be in result)
                if edge not in result.edges:
                    result.edges.append(edge)

                # Recursively get ancestors of parent
                ancestor_graph = self.get_ancestors(edge.target_id, visited.copy())
                for node in ancestor_graph.nodes.values():
                    if node.node_id not in result.nodes:
                        result.add_node(node)
                for ancestor_edge in ancestor_graph.edges:
                    if ancestor_edge not in result.edges:
                        result.edges.append(ancestor_edge)

        return result

    def get_descendants(
        self, node_id: str, visited: set[str] | None = None
    ) -> LineageGraph:
        """Get all descendant nodes (children, grandchildren, etc.).

        Args:
            node_id: The node ID to find descendants for
            visited: Set of already visited node IDs (for cycle detection)

        Returns:
            LineageGraph containing all descendants
        """
        if visited is None:
            visited = set()

        if node_id in visited:
            return LineageGraph()

        visited.add(node_id)
        result = LineageGraph()

        # Get direct children (incoming edges from children to this node)
        child_edges = self.get_children(node_id)

        for edge in child_edges:
            # The source of an incoming edge is the child
            child_node = self.nodes.get(edge.source_id)
            if child_node:
                result.add_node(child_node)
                # Add edge directly without validation (target may not be in result)
                if edge not in result.edges:
                    result.edges.append(edge)

                # Recursively get descendants of child
                descendant_graph = self.get_descendants(edge.source_id, visited.copy())
                for node in descendant_graph.nodes.values():
                    if node.node_id not in result.nodes:
                        result.add_node(node)
                for descendant_edge in descendant_graph.edges:
                    if descendant_edge not in result.edges:
                        result.edges.append(descendant_edge)

        return result

    def find_path(
        self, source_id: str, target_id: str, visited: set[str] | None = None
    ) -> list[LineageEdge] | None:
        """Find a path from source to target node.

        Args:
            source_id: The starting node ID
            target_id: The target node ID
            visited: Set of already visited node IDs

        Returns:
            List of edges forming a path from source to target, or None if no path exists
        """
        if visited is None:
            visited = set()

        if source_id == target_id:
            return []

        if source_id in visited:
            return None

        visited.add(source_id)

        # Get outgoing edges (pointing to parents)
        # For example: model -> exp -> data
        parent_edges = self.get_parents(source_id)

        for edge in parent_edges:
            if edge.target_id == target_id:
                return [edge]

            # Recursively search from parent
            sub_path = self.find_path(edge.target_id, target_id, visited.copy())
            if sub_path is not None:
                return [edge] + sub_path

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert graph to dictionary for serialization.

        Returns:
            Dictionary representation of the graph
        """
        return {
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineageGraph:
        """Create a LineageGraph from a dictionary.

        Args:
            data: Dictionary containing graph data

        Returns:
            LineageGraph instance
        """
        graph = cls()

        # Load nodes first (required for edge validation)
        for node_data in data.get("nodes", {}).values():
            graph.add_node(LineageNode.from_dict(node_data))

        # Then load edges
        for edge_data in data.get("edges", []):
            graph.add_edge(LineageEdge.from_dict(edge_data))

        return graph

    def merge(self, other: LineageGraph) -> LineageGraph:
        """Merge another graph into this one.

        Args:
            other: The graph to merge

        Returns:
            A new graph containing nodes and edges from both graphs
        """
        merged = LineageGraph()

        # Add all nodes from both graphs
        for node in self.nodes.values():
            merged.add_node(node)
        for node in other.nodes.values():
            if node.node_id not in merged.nodes:
                merged.add_node(node)

        # Add all edges from both graphs
        for edge in self.edges:
            merged.add_edge(edge)
        for edge in other.edges:
            if edge not in merged.edges:
                merged.edges.append(edge)

        return merged
