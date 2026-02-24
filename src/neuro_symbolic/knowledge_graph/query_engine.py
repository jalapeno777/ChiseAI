"""
GraphQueryEngine - Query interface for the knowledge graph.

This module provides a query engine for pattern matching, path finding,
and complex graph queries on the knowledge graph.
"""

import time
from collections import deque
from typing import Any

from src.neuro_symbolic.knowledge_graph.graph import KnowledgeGraph
from src.neuro_symbolic.knowledge_graph.models import (
    Edge,
    EdgeType,
    Node,
    NodeType,
    QueryResult,
)


class GraphQueryEngine:
    """
    Query engine for the knowledge graph.

    This class provides methods for:
    - Pattern matching in the graph
    - Path finding algorithms
    - Neighborhood queries
    - Complex graph traversals
    """

    def __init__(self, graph: KnowledgeGraph):
        """
        Initialize the query engine.

        Args:
            graph: The KnowledgeGraph to query
        """
        self.graph = graph

    def find_node(
        self,
        node_id: str | None = None,
        node_type: NodeType | str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> QueryResult:
        """
        Find nodes matching criteria.

        Args:
            node_id: Specific node ID to find
            node_type: Filter by node type
            properties: Filter by properties (all must match)

        Returns:
            QueryResult with matching nodes
        """
        start_time = time.time()

        nodes = []

        if node_id:
            node = self.graph.get_node(node_id)
            if node:
                nodes = [node]
        elif node_type:
            if isinstance(node_type, str):
                node_type = NodeType(node_type)
            nodes = self.graph.get_nodes_by_type(node_type)
        else:
            nodes = self.graph.get_all_nodes()

        # Filter by properties
        if properties:
            nodes = [
                n
                for n in nodes
                if all(
                    n.properties.get(k) == v
                    or (isinstance(v, list) and n.properties.get(k) in v)
                    for k, v in properties.items()
                )
            ]

        execution_time = (time.time() - start_time) * 1000

        return QueryResult(
            nodes=nodes,
            metadata={"query_type": "find_node", "filters": properties},
            execution_time_ms=execution_time,
        )

    def find_neighbors(
        self,
        node_id: str,
        edge_types: list[EdgeType | str] | None = None,
        min_confidence: float = 0.0,
        max_depth: int = 1,
        direction: str = "out",
    ) -> QueryResult:
        """
        Find neighbors of a node.

        Args:
            node_id: Starting node ID
            edge_types: Filter by edge types
            min_confidence: Minimum edge confidence
            max_depth: Maximum traversal depth
            direction: "out", "in", or "both"

        Returns:
            QueryResult with neighboring nodes and edges
        """
        start_time = time.time()

        if not self.graph.has_node(node_id):
            return QueryResult(
                metadata={"error": f"Node {node_id} not found"},
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        visited_nodes: set[str] = {node_id}
        visited_edges: set[tuple[str, str, EdgeType]] = set()
        result_nodes: list[Node] = []
        result_edges: list[Edge] = []

        # Convert edge types
        if edge_types:
            edge_types = [
                EdgeType(et) if isinstance(et, str) else et for et in edge_types
            ]

        # BFS traversal
        queue = deque([(node_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            if depth >= max_depth:
                continue

            # Get edges based on direction
            if direction in ("out", "both"):
                for edge in self.graph.get_out_edges(current_id):
                    if edge_types and edge.edge_type not in edge_types:
                        continue
                    if edge.confidence < min_confidence:
                        continue

                    edge_key = (edge.source_id, edge.target_id, edge.edge_type)
                    if edge_key not in visited_edges:
                        visited_edges.add(edge_key)
                        result_edges.append(edge)

                        neighbor_id = edge.target_id
                        if neighbor_id not in visited_nodes:
                            visited_nodes.add(neighbor_id)
                            neighbor = self.graph.get_node(neighbor_id)
                            if neighbor:
                                result_nodes.append(neighbor)
                            queue.append((neighbor_id, depth + 1))

            if direction in ("in", "both"):
                for edge in self.graph.get_in_edges(current_id):
                    if edge_types and edge.edge_type not in edge_types:
                        continue
                    if edge.confidence < min_confidence:
                        continue

                    edge_key = (edge.source_id, edge.target_id, edge.edge_type)
                    if edge_key not in visited_edges:
                        visited_edges.add(edge_key)
                        result_edges.append(edge)

                        neighbor_id = edge.source_id
                        if neighbor_id not in visited_nodes:
                            visited_nodes.add(neighbor_id)
                            neighbor = self.graph.get_node(neighbor_id)
                            if neighbor:
                                result_nodes.append(neighbor)
                            queue.append((neighbor_id, depth + 1))

        execution_time = (time.time() - start_time) * 1000

        return QueryResult(
            nodes=result_nodes,
            edges=result_edges,
            metadata={
                "query_type": "find_neighbors",
                "start_node": node_id,
                "max_depth": max_depth,
                "direction": direction,
            },
            execution_time_ms=execution_time,
        )

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        edge_types: list[EdgeType | str] | None = None,
        min_confidence: float = 0.0,
    ) -> QueryResult:
        """
        Find paths between two nodes.

        Args:
            source_id: Starting node ID
            target_id: Target node ID
            max_depth: Maximum path length
            edge_types: Filter by edge types
            min_confidence: Minimum edge confidence

        Returns:
            QueryResult with paths and involved nodes/edges
        """
        start_time = time.time()

        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            return QueryResult(
                metadata={"error": "Source or target node not found"},
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        # Convert edge types
        if edge_types:
            edge_types = [
                EdgeType(et) if isinstance(et, str) else et for et in edge_types
            ]

        # BFS to find shortest path(s)
        paths: list[list[str]] = []
        visited: dict[str, int] = {source_id: 0}
        queue = deque([(source_id, [source_id])])

        while queue:
            current_id, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current_id == target_id:
                paths.append(path)
                continue  # Continue to find more paths

            for edge in self.graph.get_out_edges(current_id):
                if edge_types and edge.edge_type not in edge_types:
                    continue
                if edge.confidence < min_confidence:
                    continue

                neighbor_id = edge.target_id
                # Allow revisiting if we haven't found target yet and depth allows
                if neighbor_id not in visited or visited[neighbor_id] >= len(path) + 1:
                    visited[neighbor_id] = len(path) + 1
                    queue.append((neighbor_id, path + [neighbor_id]))

        # Collect nodes and edges from paths
        result_nodes: list[Node] = []
        result_edges: list[Edge] = []
        seen_node_ids: set[str] = set()
        seen_edge_keys: set[tuple[str, str, EdgeType]] = set()

        for path in paths:
            for node_id in path:
                if node_id not in seen_node_ids:
                    node = self.graph.get_node(node_id)
                    if node:
                        result_nodes.append(node)
                        seen_node_ids.add(node_id)

            for i in range(len(path) - 1):
                for edge in self.graph.get_out_edges(path[i]):
                    if edge.target_id == path[i + 1]:
                        edge_key = (edge.source_id, edge.target_id, edge.edge_type)
                        if edge_key not in seen_edge_keys:
                            result_edges.append(edge)
                            seen_edge_keys.add(edge_key)

        execution_time = (time.time() - start_time) * 1000

        return QueryResult(
            nodes=result_nodes,
            edges=result_edges,
            paths=paths,
            metadata={
                "query_type": "find_path",
                "source": source_id,
                "target": target_id,
                "max_depth": max_depth,
            },
            execution_time_ms=execution_time,
        )

    def find_pattern(
        self,
        pattern: dict[str, Any],
    ) -> QueryResult:
        """
        Find subgraphs matching a pattern.

        Pattern format:
        {
            "nodes": [
                {"id": "a", "type": "ASSET"},
                {"id": "b", "type": "ASSET"},
            ],
            "edges": [
                {"from": "a", "to": "b", "type": "CORRELATED_WITH"},
            ]
        }

        Args:
            pattern: Pattern specification

        Returns:
            QueryResult with matching subgraphs
        """
        start_time = time.time()

        pattern_nodes = pattern.get("nodes", [])
        pattern_edges = pattern.get("edges", [])

        if not pattern_nodes:
            return QueryResult(
                metadata={"error": "Pattern must have at least one node"},
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        # Find candidate nodes for each pattern node
        candidates: dict[str, list[Node]] = {}
        for pn in pattern_nodes:
            node_type = pn.get("type")
            if node_type:
                if isinstance(node_type, str):
                    node_type = NodeType(node_type)
                candidates[pn["id"]] = self.graph.get_nodes_by_type(node_type)
            else:
                candidates[pn["id"]] = self.graph.get_all_nodes()

        # Find matching subgraphs
        matching_subgraphs: list[dict[str, Any]] = []
        result_nodes: list[Node] = []
        result_edges: list[Edge] = []
        seen_node_ids: set[str] = set()
        seen_edge_keys: set[tuple[str, str, EdgeType]] = set()

        # For single node patterns
        if len(pattern_nodes) == 1:
            node_id = pattern_nodes[0]["id"]
            props = pattern_nodes[0].get("properties", {})
            for node in candidates[node_id]:
                if self._node_matches_properties(node, props):
                    matching_subgraphs.append({"nodes": {node_id: node.id}})
                    if node.id not in seen_node_ids:
                        result_nodes.append(node)
                        seen_node_ids.add(node.id)

        # For patterns with edges
        elif pattern_edges:
            # Try to match from each candidate for the first pattern node
            first_pn = pattern_nodes[0]["id"]
            for start_node in candidates[first_pn]:
                subgraph = self._try_match_pattern(
                    start_node, pattern_nodes, pattern_edges, candidates
                )
                if subgraph:
                    matching_subgraphs.append(subgraph)
                    # Collect nodes and edges
                    for pn in pattern_nodes:
                        node_id = subgraph["nodes"].get(pn["id"])
                        if node_id and node_id not in seen_node_ids:
                            node = self.graph.get_node(node_id)
                            if node:
                                result_nodes.append(node)
                                seen_node_ids.add(node_id)

                    for pe in pattern_edges:
                        src_id = subgraph["nodes"].get(pe["from"])
                        tgt_id = subgraph["nodes"].get(pe["to"])
                        if src_id and tgt_id:
                            edge_type = pe.get("type")
                            if isinstance(edge_type, str):
                                edge_type = EdgeType(edge_type)
                            edge = self.graph.get_edge(src_id, tgt_id, edge_type)
                            if edge:
                                edge_key = (
                                    edge.source_id,
                                    edge.target_id,
                                    edge.edge_type,
                                )
                                if edge_key not in seen_edge_keys:
                                    result_edges.append(edge)
                                    seen_edge_keys.add(edge_key)

        execution_time = (time.time() - start_time) * 1000

        return QueryResult(
            nodes=result_nodes,
            edges=result_edges,
            metadata={
                "query_type": "find_pattern",
                "pattern": pattern,
                "match_count": len(matching_subgraphs),
            },
            execution_time_ms=execution_time,
        )

    def find_related(
        self,
        node_id: str,
        relationship_types: list[EdgeType | str] | None = None,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> QueryResult:
        """
        Find all nodes related to a given node.

        Args:
            node_id: The node to find relationships for
            relationship_types: Filter by relationship types
            min_confidence: Minimum confidence threshold
            limit: Maximum number of results

        Returns:
            QueryResult with related nodes and edges
        """
        start_time = time.time()

        if not self.graph.has_node(node_id):
            return QueryResult(
                metadata={"error": f"Node {node_id} not found"},
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        # Convert relationship types
        if relationship_types:
            relationship_types = [
                EdgeType(rt) if isinstance(rt, str) else rt for rt in relationship_types
            ]

        related_edges: list[Edge] = []

        # Get all edges involving this node
        for edge in self.graph.get_out_edges(node_id):
            if relationship_types and edge.edge_type not in relationship_types:
                continue
            if edge.confidence >= min_confidence:
                related_edges.append(edge)

        for edge in self.graph.get_in_edges(node_id):
            if relationship_types and edge.edge_type not in relationship_types:
                continue
            if edge.confidence >= min_confidence:
                related_edges.append(edge)

        # Sort by confidence and limit
        related_edges.sort(key=lambda e: e.confidence, reverse=True)
        related_edges = related_edges[:limit]

        # Get related nodes
        related_nodes: list[Node] = []
        seen_ids: set[str] = {node_id}
        for edge in related_edges:
            for nid in [edge.source_id, edge.target_id]:
                if nid not in seen_ids:
                    node = self.graph.get_node(nid)
                    if node:
                        related_nodes.append(node)
                        seen_ids.add(nid)

        execution_time = (time.time() - start_time) * 1000

        return QueryResult(
            nodes=related_nodes,
            edges=related_edges,
            metadata={
                "query_type": "find_related",
                "node_id": node_id,
                "min_confidence": min_confidence,
            },
            execution_time_ms=execution_time,
        )

    def find_clusters(
        self,
        node_type: NodeType | str | None = None,
        min_cluster_size: int = 3,
        edge_types: list[EdgeType | str] | None = None,
    ) -> QueryResult:
        """
        Find clusters/communities in the graph.

        Args:
            node_type: Filter by node type
            min_cluster_size: Minimum cluster size
            edge_types: Edge types to consider for clustering

        Returns:
            QueryResult with cluster information
        """
        start_time = time.time()

        # Convert types
        if node_type and isinstance(node_type, str):
            node_type = NodeType(node_type)
        if edge_types:
            edge_types = [
                EdgeType(et) if isinstance(et, str) else et for et in edge_types
            ]

        # Get nodes to consider
        if node_type:
            nodes = self.graph.get_nodes_by_type(node_type)
        else:
            nodes = self.graph.get_all_nodes()

        # Simple connected components approach
        visited: set[str] = set()
        clusters: list[list[str]] = []

        for node in nodes:
            if node.id in visited:
                continue

            # BFS to find connected component
            cluster: list[str] = []
            queue = deque([node.id])

            while queue:
                current_id = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)
                cluster.append(current_id)

                for edge in self.graph.get_out_edges(current_id):
                    if edge_types and edge.edge_type not in edge_types:
                        continue
                    if edge.target_id not in visited:
                        queue.append(edge.target_id)

                for edge in self.graph.get_in_edges(current_id):
                    if edge_types and edge.edge_type not in edge_types:
                        continue
                    if edge.source_id not in visited:
                        queue.append(edge.source_id)

            if len(cluster) >= min_cluster_size:
                clusters.append(cluster)

        # Build result
        result_nodes: list[Node] = []
        result_edges: list[Edge] = []
        seen_node_ids: set[str] = set()

        for cluster in clusters:
            for node_id in cluster:
                if node_id not in seen_node_ids:
                    node = self.graph.get_node(node_id)
                    if node:
                        result_nodes.append(node)
                        seen_node_ids.add(node_id)

        execution_time = (time.time() - start_time) * 1000

        return QueryResult(
            nodes=result_nodes,
            edges=result_edges,
            metadata={
                "query_type": "find_clusters",
                "cluster_count": len(clusters),
                "clusters": clusters,
                "min_cluster_size": min_cluster_size,
            },
            execution_time_ms=execution_time,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _node_matches_properties(self, node: Node, properties: dict[str, Any]) -> bool:
        """Check if node matches all specified properties."""
        for key, value in properties.items():
            if node.properties.get(key) != value:
                return False
        return True

    def _try_match_pattern(
        self,
        start_node: Node,
        pattern_nodes: list[dict[str, Any]],
        pattern_edges: list[dict[str, Any]],
        candidates: dict[str, list[Node]],
    ) -> dict[str, Any] | None:
        """
        Try to match a pattern starting from a given node.

        Returns a mapping of pattern node IDs to actual node IDs if successful.
        """
        mapping: dict[str, str] = {}
        first_pn = pattern_nodes[0]["id"]

        # Check if start node matches first pattern node
        props = pattern_nodes[0].get("properties", {})
        if not self._node_matches_properties(start_node, props):
            return None

        mapping[first_pn] = start_node.id

        # Try to match remaining nodes and edges
        for pe in pattern_edges:
            src_pn = pe["from"]
            tgt_pn = pe["to"]
            edge_type = pe.get("type")
            if isinstance(edge_type, str):
                edge_type = EdgeType(edge_type)

            if src_pn not in mapping:
                continue  # Can't match this edge yet

            src_id = mapping[src_pn]

            # Find matching edge and target
            for edge in self.graph.get_out_edges(src_id):
                if edge_type and edge.edge_type != edge_type:
                    continue

                tgt_node = self.graph.get_node(edge.target_id)
                if tgt_node:
                    # Check if target matches pattern
                    tgt_pattern = next(
                        (pn for pn in pattern_nodes if pn["id"] == tgt_pn), None
                    )
                    if tgt_pattern:
                        tgt_props = tgt_pattern.get("properties", {})
                        if self._node_matches_properties(tgt_node, tgt_props):
                            if tgt_pn not in mapping:
                                mapping[tgt_pn] = tgt_node.id
                            break

        # Check if all pattern nodes are mapped
        for pn in pattern_nodes:
            if pn["id"] not in mapping:
                return None

        return {"nodes": mapping}
