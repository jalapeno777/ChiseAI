"""
GraphUpdater - Updates graph based on new data.

This module provides functionality for incrementally updating the
knowledge graph with new data, including conflict resolution.
"""

import logging
from datetime import datetime
from typing import Any

from src.neuro_symbolic.knowledge_graph.graph import KnowledgeGraph
from src.neuro_symbolic.knowledge_graph.models import (
    Edge,
    EdgeType,
    ExtractionResult,
    Node,
    NodeType,
    UpdateResult,
)

logger = logging.getLogger(__name__)


class ConflictResolutionStrategy:
    """Strategy for resolving conflicts during graph updates."""

    KEEP_EXISTING = "keep_existing"
    OVERWRITE = "overwrite"
    MERGE = "merge"
    HIGHEST_CONFIDENCE = "highest_confidence"
    MOST_RECENT = "most_recent"


class GraphUpdater:
    """
    Updates the knowledge graph with new data.

    This class provides methods for:
    - Incremental graph construction
    - Batch updates from extraction results
    - Conflict resolution
    - Graph maintenance and cleanup
    """

    def __init__(
        self,
        graph: KnowledgeGraph,
        conflict_strategy: str = ConflictResolutionStrategy.HIGHEST_CONFIDENCE,
        min_confidence_threshold: float = 0.3,
        stale_edge_days: int = 30,
    ):
        """
        Initialize the graph updater.

        Args:
            graph: The KnowledgeGraph to update
            conflict_strategy: Strategy for resolving conflicts
            min_confidence_threshold: Minimum confidence to add edges
            stale_edge_days: Days after which edges are considered stale
        """
        self.graph = graph
        self.conflict_strategy = conflict_strategy
        self.min_confidence_threshold = min_confidence_threshold
        self.stale_edge_days = stale_edge_days
        self._update_count = 0

    def add_extraction_result(
        self,
        result: ExtractionResult,
        resolve_conflicts: bool = True,
    ) -> UpdateResult:
        """
        Add a single extraction result to the graph.

        Args:
            result: The extraction result to add
            resolve_conflicts: Whether to resolve conflicts

        Returns:
            UpdateResult with update statistics
        """
        update_result = UpdateResult()

        # Add source node
        src_added = self._add_or_update_node(result.source_node, update_result)

        # Add target node
        tgt_added = self._add_or_update_node(result.target_node, update_result)

        # Add edge if both nodes exist
        if (
            src_added
            or tgt_added
            or (
                self.graph.has_node(result.source_node.id)
                and self.graph.has_node(result.target_node.id)
            )
        ):
            self._add_or_update_edge(result.edge, update_result, resolve_conflicts)

        self._update_count += 1

        return update_result

    def add_extraction_results(
        self,
        results: list[ExtractionResult],
        resolve_conflicts: bool = True,
    ) -> UpdateResult:
        """
        Add multiple extraction results to the graph.

        Args:
            results: List of extraction results to add
            resolve_conflicts: Whether to resolve conflicts

        Returns:
            Combined UpdateResult
        """
        combined = UpdateResult()

        for result in results:
            single_result = self.add_extraction_result(result, resolve_conflicts)
            combined.nodes_added += single_result.nodes_added
            combined.nodes_updated += single_result.nodes_updated
            combined.nodes_removed += single_result.nodes_removed
            combined.edges_added += single_result.edges_added
            combined.edges_updated += single_result.edges_updated
            combined.edges_removed += single_result.edges_removed
            combined.conflicts_resolved += single_result.conflicts_resolved
            combined.errors.extend(single_result.errors)

        return combined

    def add_node(
        self,
        node_id: str,
        node_type: NodeType | str,
        properties: dict[str, Any] | None = None,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> UpdateResult:
        """
        Add a single node to the graph.

        Args:
            node_id: Unique identifier for the node
            node_type: Type of the node
            properties: Optional properties dictionary
            confidence: Confidence score (0-1)
            source: Source of the node data

        Returns:
            UpdateResult with update statistics
        """
        result = UpdateResult()

        if isinstance(node_type, str):
            node_type = NodeType(node_type)

        node = Node(
            id=node_id,
            node_type=node_type,
            properties=properties or {},
            confidence=confidence,
            source=source,
        )

        self._add_or_update_node(node, result)
        self._update_count += 1

        return result

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | str,
        properties: dict[str, Any] | None = None,
        weight: float = 1.0,
        confidence: float = 1.0,
        evidence: list[str] | None = None,
        resolve_conflicts: bool = True,
    ) -> UpdateResult:
        """
        Add a single edge to the graph.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship
            properties: Optional properties dictionary
            weight: Edge weight
            confidence: Confidence in the relationship
            evidence: List of evidence
            resolve_conflicts: Whether to resolve conflicts

        Returns:
            UpdateResult with update statistics
        """
        result = UpdateResult()

        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)

        if confidence < self.min_confidence_threshold:
            result.errors.append(
                f"Edge confidence {confidence} below threshold {self.min_confidence_threshold}"
            )
            return result

        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            properties=properties or {},
            weight=weight,
            confidence=confidence,
            evidence=evidence or [],
        )

        self._add_or_update_edge(edge, result, resolve_conflicts)
        self._update_count += 1

        return result

    def remove_stale_edges(self) -> UpdateResult:
        """
        Remove edges that haven't been updated recently.

        Returns:
            UpdateResult with removal statistics
        """
        result = UpdateResult()
        cutoff = datetime.utcnow()

        edges_to_remove = []
        for edge in self.graph.get_all_edges():
            if edge.updated_at:
                days_since_update = (cutoff - edge.updated_at).days
                if days_since_update > self.stale_edge_days:
                    edges_to_remove.append(edge)

        for edge in edges_to_remove:
            if self.graph.remove_edge(edge.source_id, edge.target_id, edge.edge_type):
                result.edges_removed += 1

        if edges_to_remove:
            logger.info(f"Removed {result.edges_removed} stale edges")

        return result

    def remove_low_confidence_edges(self, threshold: float = 0.2) -> UpdateResult:
        """
        Remove edges below confidence threshold.

        Args:
            threshold: Minimum confidence to keep

        Returns:
            UpdateResult with removal statistics
        """
        result = UpdateResult()

        edges_to_remove = [
            edge for edge in self.graph.get_all_edges() if edge.confidence < threshold
        ]

        for edge in edges_to_remove:
            if self.graph.remove_edge(edge.source_id, edge.target_id, edge.edge_type):
                result.edges_removed += 1

        if edges_to_remove:
            logger.info(
                f"Removed {result.edges_removed} low confidence edges (threshold={threshold})"
            )

        return result

    def merge_properties(
        self,
        node_id: str,
        new_properties: dict[str, Any],
        overwrite: bool = False,
    ) -> UpdateResult:
        """
        Merge new properties into an existing node.

        Args:
            node_id: The node to update
            new_properties: Properties to merge
            overwrite: Whether to overwrite existing values

        Returns:
            UpdateResult with update statistics
        """
        result = UpdateResult()

        node = self.graph.get_node(node_id)
        if not node:
            result.errors.append(f"Node {node_id} not found")
            return result

        updated = False
        for key, value in new_properties.items():
            if overwrite or key not in node.properties:
                node.properties[key] = value
                updated = True

        if updated:
            node.updated_at = datetime.utcnow()
            result.nodes_updated += 1

        return result

    def batch_update(
        self,
        nodes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
        resolve_conflicts: bool = True,
    ) -> UpdateResult:
        """
        Perform a batch update of nodes and edges.

        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            resolve_conflicts: Whether to resolve conflicts

        Returns:
            Combined UpdateResult
        """
        result = UpdateResult()

        # Add nodes first
        if nodes:
            for node_data in nodes:
                try:
                    node_type = node_data.get("node_type", NodeType.ASSET)
                    if isinstance(node_type, str):
                        node_type = NodeType(node_type)

                    node = Node(
                        id=node_data["id"],
                        node_type=node_type,
                        properties=node_data.get("properties", {}),
                        confidence=node_data.get("confidence", 1.0),
                        source=node_data.get("source"),
                    )
                    self._add_or_update_node(node, result)
                except Exception as e:
                    result.errors.append(f"Failed to add node: {e}")

        # Add edges
        if edges:
            for edge_data in edges:
                try:
                    edge_type = edge_data.get("edge_type", EdgeType.CORRELATED_WITH)
                    if isinstance(edge_type, str):
                        edge_type = EdgeType(edge_type)

                    edge = Edge(
                        source_id=edge_data["source_id"],
                        target_id=edge_data["target_id"],
                        edge_type=edge_type,
                        properties=edge_data.get("properties", {}),
                        weight=edge_data.get("weight", 1.0),
                        confidence=edge_data.get("confidence", 1.0),
                        evidence=edge_data.get("evidence", []),
                    )
                    self._add_or_update_edge(edge, result, resolve_conflicts)
                except Exception as e:
                    result.errors.append(f"Failed to add edge: {e}")

        self._update_count += 1

        return result

    def cleanup_orphan_nodes(self) -> UpdateResult:
        """
        Remove nodes that have no edges.

        Returns:
            UpdateResult with removal statistics
        """
        result = UpdateResult()

        nodes_to_remove = []
        for node in self.graph.get_all_nodes():
            if self.graph.get_degree(node.id) == 0:
                nodes_to_remove.append(node.id)

        for node_id in nodes_to_remove:
            if self.graph.remove_node(node_id):
                result.nodes_removed += 1

        if nodes_to_remove:
            logger.info(f"Removed {result.nodes_removed} orphan nodes")

        return result

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _add_or_update_node(self, node: Node, result: UpdateResult) -> bool:
        """
        Add or update a node in the graph.

        Returns:
            True if node was added, False if updated or no change
        """
        existing = self.graph.get_node(node.id)

        if existing is None:
            # Add new node
            self.graph.add_node(
                node_id=node.id,
                node_type=node.node_type,
                properties=node.properties,
                confidence=node.confidence,
                source=node.source,
            )
            result.nodes_added += 1
            return True

        # Check for conflicts and resolve
        if self._has_node_conflict(existing, node):
            result.conflicts_resolved += 1
            self._resolve_node_conflict(existing, node)

        # Update properties
        if node.properties:
            self.graph.update_node(node.id, properties=node.properties)
            result.nodes_updated += 1

        return False

    def _add_or_update_edge(
        self, edge: Edge, result: UpdateResult, resolve_conflicts: bool
    ) -> None:
        """Add or update an edge in the graph."""
        # Check confidence threshold
        if edge.confidence < self.min_confidence_threshold:
            result.errors.append(f"Edge confidence {edge.confidence} below threshold")
            return

        existing = self.graph.get_edge(edge.source_id, edge.target_id, edge.edge_type)

        if existing is None:
            # Add new edge
            added = self.graph.add_edge(
                source_id=edge.source_id,
                target_id=edge.target_id,
                edge_type=edge.edge_type,
                properties=edge.properties,
                weight=edge.weight,
                confidence=edge.confidence,
                evidence=edge.evidence,
            )
            if added:
                result.edges_added += 1
            else:
                result.errors.append(
                    f"Failed to add edge: nodes may not exist ({edge.source_id} -> {edge.target_id})"
                )
        elif resolve_conflicts:
            # Resolve conflict and update
            result.conflicts_resolved += 1
            self._resolve_edge_conflict(existing, edge)
            result.edges_updated += 1

    def _has_node_conflict(self, existing: Node, new: Node) -> bool:
        """Check if there's a conflict between existing and new node."""
        # Conflict if types differ
        if existing.node_type != new.node_type:
            return True

        # Conflict if sources differ and both are specified
        return bool(existing.source and new.source and existing.source != new.source)

    def _resolve_node_conflict(self, existing: Node, new: Node) -> None:
        """Resolve a node conflict based on the configured strategy."""
        if self.conflict_strategy == ConflictResolutionStrategy.KEEP_EXISTING:
            # Do nothing, keep existing
            pass

        elif self.conflict_strategy == ConflictResolutionStrategy.OVERWRITE:
            existing.properties = new.properties.copy()
            existing.confidence = new.confidence
            existing.source = new.source

        elif self.conflict_strategy == ConflictResolutionStrategy.MERGE:
            existing.properties.update(new.properties)
            if new.confidence > existing.confidence:
                existing.confidence = new.confidence

        elif self.conflict_strategy == ConflictResolutionStrategy.HIGHEST_CONFIDENCE:
            if new.confidence > existing.confidence:
                existing.properties.update(new.properties)
                existing.confidence = new.confidence
                existing.source = new.source

        elif self.conflict_strategy == ConflictResolutionStrategy.MOST_RECENT:
            existing.properties.update(new.properties)
            existing.confidence = new.confidence
            existing.source = new.source

        existing.updated_at = datetime.utcnow()

    def _resolve_edge_conflict(self, existing: Edge, new: Edge) -> None:
        """Resolve an edge conflict based on the configured strategy."""
        if self.conflict_strategy == ConflictResolutionStrategy.KEEP_EXISTING:
            # Do nothing, keep existing
            pass

        elif self.conflict_strategy == ConflictResolutionStrategy.OVERWRITE:
            existing.properties = new.properties.copy()
            existing.weight = new.weight
            existing.confidence = new.confidence
            existing.evidence = new.evidence.copy()

        elif self.conflict_strategy == ConflictResolutionStrategy.MERGE:
            existing.properties.update(new.properties)
            existing.evidence.extend(new.evidence)
            # Remove duplicate evidence
            existing.evidence = list(dict.fromkeys(existing.evidence))

        elif self.conflict_strategy == ConflictResolutionStrategy.HIGHEST_CONFIDENCE:
            if new.confidence > existing.confidence:
                existing.properties.update(new.properties)
                existing.weight = new.weight
                existing.confidence = new.confidence
                existing.evidence = new.evidence.copy()

        elif self.conflict_strategy == ConflictResolutionStrategy.MOST_RECENT:
            existing.properties.update(new.properties)
            existing.weight = new.weight
            existing.confidence = new.confidence
            existing.evidence = new.evidence.copy()

        existing.updated_at = datetime.utcnow()

    @property
    def update_count(self) -> int:
        """Number of updates performed."""
        return self._update_count

    def reset_count(self) -> None:
        """Reset the update counter."""
        self._update_count = 0
