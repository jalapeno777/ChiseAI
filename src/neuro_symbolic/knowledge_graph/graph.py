"""
KnowledgeGraph - Core graph database for market relationships.

This module provides the main KnowledgeGraph class that serves as the
graph database for storing and managing market relationships.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from src.neuro_symbolic.knowledge_graph.models import (
    Edge,
    EdgeType,
    GraphMetrics,
    Node,
    NodeType,
)


class KnowledgeGraph:
    """
    A graph database for storing and managing market relationships.

    This class provides functionality for:
    - Node and edge management
    - Graph traversal and queries
    - Metrics computation
    - Serialization and persistence
    """

    def __init__(self, name: str = "default"):
        """
        Initialize the knowledge graph.

        Args:
            name: Name identifier for the graph
        """
        self.name = name
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple[str, str, EdgeType], Edge] = {}
        self._adjacency: dict[str, set[str]] = defaultdict(set)
        self._reverse_adjacency: dict[str, set[str]] = defaultdict(set)
        self._node_type_index: dict[NodeType, set[str]] = defaultdict(set)
        self._edge_type_index: dict[EdgeType, set[tuple[str, str]]] = defaultdict(set)
        self._created_at = datetime.now(UTC)
        self._modified_at = datetime.now(UTC)

    # =========================================================================
    # Node Operations
    # =========================================================================

    def add_node(
        self,
        node_id: str,
        node_type: NodeType | str,
        properties: dict[str, Any] | None = None,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> Node:
        """
        Add a node to the graph.

        Args:
            node_id: Unique identifier for the node
            node_type: Type of the node (NodeType enum or string)
            properties: Optional properties dictionary
            confidence: Confidence score for the node (0-1)
            source: Source of the node data

        Returns:
            The created Node object
        """
        if isinstance(node_type, str):
            node_type = NodeType(node_type)

        node = Node(
            id=node_id,
            node_type=node_type,
            properties=properties or {},
            confidence=confidence,
            source=source,
        )

        self._nodes[node_id] = node
        self._node_type_index[node_type].add(node_id)
        self._touch()

        return node

    def get_node(self, node_id: str) -> Node | None:
        """
        Get a node by ID.

        Args:
            node_id: The node identifier

        Returns:
            The Node object or None if not found
        """
        return self._nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        """
        Check if a node exists in the graph.

        Args:
            node_id: The node identifier

        Returns:
            True if node exists, False otherwise
        """
        return node_id in self._nodes

    def update_node(
        self,
        node_id: str,
        properties: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> Node | None:
        """
        Update a node's properties.

        Args:
            node_id: The node identifier
            properties: Properties to update (merged with existing)
            confidence: New confidence score

        Returns:
            Updated Node or None if not found
        """
        node = self._nodes.get(node_id)
        if node is None:
            return None

        if properties:
            node.properties.update(properties)
        if confidence is not None:
            node.confidence = confidence

        node.updated_at = datetime.now(UTC)
        self._touch()

        return node

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node and all its edges from the graph.

        Args:
            node_id: The node identifier

        Returns:
            True if node was removed, False if not found
        """
        if node_id not in self._nodes:
            return False

        # Remove all edges involving this node
        edges_to_remove = []
        for src, tgt, etype in self._edges:
            if src == node_id or tgt == node_id:
                edges_to_remove.append((src, tgt, etype))

        for edge_key in edges_to_remove:
            self.remove_edge(edge_key[0], edge_key[1], edge_key[2])

        # Remove from type index
        node = self._nodes[node_id]
        self._node_type_index[node.node_type].discard(node_id)

        # Remove from adjacency lists
        del self._nodes[node_id]
        if node_id in self._adjacency:
            del self._adjacency[node_id]
        if node_id in self._reverse_adjacency:
            del self._reverse_adjacency[node_id]

        # Clean up references in other adjacency lists
        for adj in self._adjacency.values():
            adj.discard(node_id)
        for adj in self._reverse_adjacency.values():
            adj.discard(node_id)

        self._touch()
        return True

    def get_nodes_by_type(self, node_type: NodeType | str) -> list[Node]:
        """
        Get all nodes of a specific type.

        Args:
            node_type: The type to filter by

        Returns:
            List of nodes of the specified type
        """
        if isinstance(node_type, str):
            node_type = NodeType(node_type)

        node_ids = self._node_type_index.get(node_type, set())
        return [self._nodes[nid] for nid in node_ids if nid in self._nodes]

    def get_all_nodes(self) -> list[Node]:
        """Get all nodes in the graph."""
        return list(self._nodes.values())

    # =========================================================================
    # Edge Operations
    # =========================================================================

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | str,
        properties: dict[str, Any] | None = None,
        weight: float = 1.0,
        confidence: float = 1.0,
        evidence: list[str] | None = None,
    ) -> Edge | None:
        """
        Add an edge between two nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship
            properties: Optional properties dictionary
            weight: Edge weight (default 1.0)
            confidence: Confidence in the relationship (0-1)
            evidence: List of evidence supporting this relationship

        Returns:
            The created Edge or None if nodes don't exist
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)

        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            properties=properties or {},
            weight=weight,
            confidence=confidence,
            evidence=evidence or [],
        )

        key = (source_id, target_id, edge_type)
        self._edges[key] = edge
        self._adjacency[source_id].add(target_id)
        self._reverse_adjacency[target_id].add(source_id)
        self._edge_type_index[edge_type].add((source_id, target_id))
        self._touch()

        return edge

    def get_edge(
        self, source_id: str, target_id: str, edge_type: EdgeType | str
    ) -> Edge | None:
        """
        Get an edge by source, target, and type.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship

        Returns:
            The Edge object or None if not found
        """
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)

        return self._edges.get((source_id, target_id, edge_type))

    def has_edge(
        self, source_id: str, target_id: str, edge_type: EdgeType | str
    ) -> bool:
        """
        Check if an edge exists.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship

        Returns:
            True if edge exists, False otherwise
        """
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)

        return (source_id, target_id, edge_type) in self._edges

    def update_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | str,
        properties: dict[str, Any] | None = None,
        weight: float | None = None,
        confidence: float | None = None,
    ) -> Edge | None:
        """
        Update an edge's properties.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship
            properties: Properties to update (merged with existing)
            weight: New weight
            confidence: New confidence score

        Returns:
            Updated Edge or None if not found
        """
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)

        edge = self._edges.get((source_id, target_id, edge_type))
        if edge is None:
            return None

        if properties:
            edge.properties.update(properties)
        if weight is not None:
            edge.weight = weight
        if confidence is not None:
            edge.confidence = confidence

        edge.updated_at = datetime.now(UTC)
        self._touch()

        return edge

    def remove_edge(
        self, source_id: str, target_id: str, edge_type: EdgeType | str
    ) -> bool:
        """
        Remove an edge from the graph.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship

        Returns:
            True if edge was removed, False if not found
        """
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)

        key = (source_id, target_id, edge_type)
        if key not in self._edges:
            return False

        del self._edges[key]
        self._adjacency[source_id].discard(target_id)
        self._reverse_adjacency[target_id].discard(source_id)
        self._edge_type_index[edge_type].discard((source_id, target_id))
        self._touch()

        return True

    def get_edges_by_type(self, edge_type: EdgeType | str) -> list[Edge]:
        """
        Get all edges of a specific type.

        Args:
            edge_type: The type to filter by

        Returns:
            List of edges of the specified type
        """
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)

        pairs = self._edge_type_index.get(edge_type, set())
        return [
            self._edges[(src, tgt, edge_type)]
            for src, tgt in pairs
            if (src, tgt, edge_type) in self._edges
        ]

    def get_all_edges(self) -> list[Edge]:
        """Get all edges in the graph."""
        return list(self._edges.values())

    # =========================================================================
    # Graph Traversal
    # =========================================================================

    def get_neighbors(self, node_id: str) -> list[str]:
        """
        Get all neighbor node IDs.

        Args:
            node_id: The node identifier

        Returns:
            List of neighbor node IDs
        """
        return list(self._adjacency.get(node_id, set()))

    def get_predecessors(self, node_id: str) -> list[str]:
        """
        Get all predecessor node IDs.

        Args:
            node_id: The node identifier

        Returns:
            List of predecessor node IDs
        """
        return list(self._reverse_adjacency.get(node_id, set()))

    def get_degree(self, node_id: str) -> int:
        """
        Get the degree (number of connections) of a node.

        Args:
            node_id: The node identifier

        Returns:
            The degree of the node
        """
        out_degree = len(self._adjacency.get(node_id, set()))
        in_degree = len(self._reverse_adjacency.get(node_id, set()))
        return out_degree + in_degree

    def get_out_edges(self, node_id: str) -> list[Edge]:
        """
        Get all outgoing edges from a node.

        Args:
            node_id: The node identifier

        Returns:
            List of outgoing edges
        """
        edges = []
        for (src, _tgt, _etype), edge in self._edges.items():
            if src == node_id:
                edges.append(edge)
        return edges

    def get_in_edges(self, node_id: str) -> list[Edge]:
        """
        Get all incoming edges to a node.

        Args:
            node_id: The node identifier

        Returns:
            List of incoming edges
        """
        edges = []
        for (_src, tgt, _etype), edge in self._edges.items():
            if tgt == node_id:
                edges.append(edge)
        return edges

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> GraphMetrics:
        """
        Compute graph metrics.

        Returns:
            GraphMetrics object with computed metrics
        """
        # Count nodes by type
        nodes_by_type: dict[str, int] = {}
        for node_type, node_ids in self._node_type_index.items():
            nodes_by_type[node_type.value] = len(node_ids)

        # Count edges by type
        edges_by_type: dict[str, int] = {}
        for edge_type, pairs in self._edge_type_index.items():
            edges_by_type[edge_type.value] = len(pairs)

        # Compute connectivity
        total_nodes = len(self._nodes)
        total_edges = len(self._edges)

        if total_nodes > 0:
            degrees = [self.get_degree(nid) for nid in self._nodes]
            avg_connectivity = sum(degrees) / total_nodes
            max_connectivity = max(degrees) if degrees else 0
        else:
            avg_connectivity = 0.0
            max_connectivity = 0

        # Compute density
        max_possible_edges = total_nodes * (total_nodes - 1)
        density = total_edges / max_possible_edges if max_possible_edges > 0 else 0.0

        return GraphMetrics(
            total_nodes=total_nodes,
            total_edges=total_edges,
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
            avg_connectivity=avg_connectivity,
            max_connectivity=max_connectivity,
            density=density,
            last_updated=self._modified_at,
        )

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the graph to a dictionary.

        Returns:
            Dictionary representation of the graph
        """
        return {
            "name": self.name,
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
            "edges": [edge.to_dict() for edge in self._edges.values()],
            "created_at": self._created_at.isoformat(),
            "modified_at": self._modified_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeGraph":
        """
        Deserialize a graph from a dictionary.

        Args:
            data: Dictionary representation of the graph

        Returns:
            KnowledgeGraph instance
        """
        graph = cls(name=data.get("name", "default"))

        # Add nodes
        for nid, node_data in data.get("nodes", {}).items():
            node = Node.from_dict(node_data)
            graph._nodes[nid] = node
            graph._node_type_index[node.node_type].add(nid)

        # Add edges
        for edge_data in data.get("edges", []):
            edge = Edge.from_dict(edge_data)
            key = (edge.source_id, edge.target_id, edge.edge_type)
            graph._edges[key] = edge
            graph._adjacency[edge.source_id].add(edge.target_id)
            graph._reverse_adjacency[edge.target_id].add(edge.source_id)
            graph._edge_type_index[edge.edge_type].add((edge.source_id, edge.target_id))

        if "created_at" in data:
            graph._created_at = datetime.fromisoformat(data["created_at"])
        if "modified_at" in data:
            graph._modified_at = datetime.fromisoformat(data["modified_at"])

        return graph

    def clear(self) -> None:
        """Clear all nodes and edges from the graph."""
        self._nodes.clear()
        self._edges.clear()
        self._adjacency.clear()
        self._reverse_adjacency.clear()
        self._node_type_index.clear()
        self._edge_type_index.clear()
        self._touch()

    def _touch(self) -> None:
        """Update the modified timestamp."""
        self._modified_at = datetime.now(UTC)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return len(self._edges)

    @property
    def is_empty(self) -> bool:
        """Whether the graph is empty."""
        return len(self._nodes) == 0

    def __len__(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self._nodes)

    def __contains__(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        return node_id in self._nodes

    def __repr__(self) -> str:
        """String representation of the graph."""
        return f"KnowledgeGraph(name={self.name!r}, nodes={self.node_count}, edges={self.edge_count})"
