"""
Models and data structures for the Symbolic Knowledge Graph.

This module defines the core data types used in the knowledge graph
including nodes, edges, relationship types, and query results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class NodeType(Enum):
    """Types of nodes in the knowledge graph."""

    ASSET = "asset"
    MARKET = "market"
    INDICATOR = "indicator"
    EVENT = "event"
    STRATEGY = "strategy"
    SIGNAL = "signal"
    TIMEFRAME = "timeframe"
    PATTERN = "pattern"
    CORRELATION_CLUSTER = "correlation_cluster"
    SECTOR = "sector"


class EdgeType(Enum):
    """Types of relationships between nodes."""

    # Correlation relationships
    CORRELATED_WITH = "correlated_with"
    NEGATIVELY_CORRELATED = "negatively_correlated"

    # Causal relationships
    CAUSES = "causes"
    INFLUENCES = "influences"
    PREDICTS = "predicts"

    # Structural relationships
    PART_OF = "part_of"
    BELONGS_TO = "belongs_to"
    DERIVED_FROM = "derived_from"

    # Temporal relationships
    PRECEDES = "precedes"
    FOLLOWS = "follows"
    CO_OCCURS_WITH = "co_occurs_with"

    # Signal relationships
    GENERATES = "generates"
    TRIGGERS = "triggers"
    SUPPRESSES = "suppresses"

    # Market relationships
    LEADS = "leads"
    LAGS = "lags"
    TRACKS = "tracks"


class RelationshipStrength(Enum):
    """Strength levels for relationships."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"

    @classmethod
    def from_correlation(cls, correlation: float) -> "RelationshipStrength":
        """
        Determine relationship strength from correlation coefficient.

        Args:
            correlation: Correlation coefficient (-1 to 1)

        Returns:
            RelationshipStrength enum value
        """
        abs_corr = abs(correlation)
        if abs_corr >= 0.9:
            return cls.VERY_STRONG
        elif abs_corr >= 0.7:
            return cls.STRONG
        elif abs_corr >= 0.4:
            return cls.MODERATE
        else:
            return cls.WEAK


@dataclass
class Node:
    """
    A node in the knowledge graph.

    Represents an entity such as an asset, indicator, or event.
    """

    id: str
    node_type: NodeType
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    source: Optional[str] = None

    def update_property(self, key: str, value: Any) -> None:
        """Update a property and touch the timestamp."""
        self.properties[key] = value
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert node to dictionary representation."""
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "properties": self.properties,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Node":
        """Create a Node from dictionary representation."""
        return cls(
            id=data["id"],
            node_type=NodeType(data["node_type"]),
            properties=data.get("properties", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            confidence=data.get("confidence", 1.0),
            source=data.get("source"),
        )


@dataclass
class Edge:
    """
    An edge in the knowledge graph.

    Represents a relationship between two nodes.
    """

    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    evidence: list[str] = field(default_factory=list)

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if edge is valid at given timestamp."""
        if self.valid_from and timestamp < self.valid_from:
            return False
        if self.valid_until and timestamp > self.valid_until:
            return False
        return True

    def add_evidence(self, evidence: str) -> None:
        """Add evidence supporting this relationship."""
        self.evidence.append(evidence)
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert edge to dictionary representation."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "properties": self.properties,
            "weight": self.weight,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edge":
        """Create an Edge from dictionary representation."""
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=EdgeType(data["edge_type"]),
            properties=data.get("properties", {}),
            weight=data.get("weight", 1.0),
            confidence=data.get("confidence", 1.0),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            valid_from=(
                datetime.fromisoformat(data["valid_from"])
                if data.get("valid_from")
                else None
            ),
            valid_until=(
                datetime.fromisoformat(data["valid_until"])
                if data.get("valid_until")
                else None
            ),
            evidence=data.get("evidence", []),
        )


@dataclass
class QueryResult:
    """Result from a graph query."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    paths: list[list[str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0

    @property
    def node_count(self) -> int:
        """Number of nodes in result."""
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in result."""
        return len(self.edges)

    @property
    def path_count(self) -> int:
        """Number of paths in result."""
        return len(self.paths)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "paths": self.paths,
            "metadata": self.metadata,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class GraphMetrics:
    """Metrics about the knowledge graph."""

    total_nodes: int = 0
    total_edges: int = 0
    nodes_by_type: dict[str, int] = field(default_factory=dict)
    edges_by_type: dict[str, int] = field(default_factory=dict)
    avg_connectivity: float = 0.0
    max_connectivity: int = 0
    density: float = 0.0
    strongly_connected_components: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "nodes_by_type": self.nodes_by_type,
            "edges_by_type": self.edges_by_type,
            "avg_connectivity": self.avg_connectivity,
            "max_connectivity": self.max_connectivity,
            "density": self.density,
            "strongly_connected_components": self.strongly_connected_components,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class ExtractionResult:
    """Result from relationship extraction."""

    source_node: Node
    target_node: Node
    edge: Edge
    extraction_method: str
    extraction_confidence: float
    supporting_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "source_node": self.source_node.to_dict(),
            "target_node": self.target_node.to_dict(),
            "edge": self.edge.to_dict(),
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
            "supporting_data": self.supporting_data,
        }


@dataclass
class UpdateResult:
    """Result from a graph update operation."""

    nodes_added: int = 0
    nodes_updated: int = 0
    nodes_removed: int = 0
    edges_added: int = 0
    edges_updated: int = 0
    edges_removed: int = 0
    conflicts_resolved: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_changes(self) -> int:
        """Total number of changes made."""
        return (
            self.nodes_added
            + self.nodes_updated
            + self.nodes_removed
            + self.edges_added
            + self.edges_updated
            + self.edges_removed
        )

    @property
    def success(self) -> bool:
        """Whether the update was successful (no errors)."""
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "nodes_added": self.nodes_added,
            "nodes_updated": self.nodes_updated,
            "nodes_removed": self.nodes_removed,
            "edges_added": self.edges_added,
            "edges_updated": self.edges_updated,
            "edges_removed": self.edges_removed,
            "conflicts_resolved": self.conflicts_resolved,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat(),
            "total_changes": self.total_changes,
            "success": self.success,
        }
