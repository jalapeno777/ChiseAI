"""Belief graph with networkx integration for graph traversal and analysis."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from autonomous_cognition.beliefs.models import Belief, BeliefRelationship

logger = logging.getLogger(__name__)

# Redis keys for graph persistence
GRAPH_INDEX_KEY = "bmad:chiseai:autocog:belief_graph:index"
GRAPH_RELATIONSHIPS_KEY = "bmad:chiseai:autocog:belief_graph:relationships"
GRAPH_METADATA_KEY = "bmad:chiseai:autocog:belief_graph:metadata"


class BeliefGraph:
    """Graph structure for beliefs with relationship tracking.

    Supports both in-memory operations and Redis persistence.
    Can export to networkx for advanced graph algorithms.
    """

    def __init__(self, redis_client: Any | None = None):
        self._redis_client = redis_client
        self._nodes: dict[str, Belief] = {}
        self._edges: dict[str, BeliefRelationship] = {}
        self._adjacency: dict[str, dict[str, str]] = (
            {}
        )  # belief_id -> {neighbor_id -> relationship_id}

    def add_belief(self, belief: Belief) -> None:
        """Add a belief as a node in the graph."""
        logger.info("[BELIEF_GRAPH] Adding belief: %s", belief.belief_id)
        self._nodes[belief.belief_id] = belief
        if belief.belief_id not in self._adjacency:
            self._adjacency[belief.belief_id] = {}

    def add_relationship(self, rel: BeliefRelationship) -> None:
        """Add a relationship as an edge in the graph."""
        logger.info(
            "[BELIEF_GRAPH] Adding relationship: %s (%s -> %s)",
            rel.relationship_id,
            rel.source_belief_id,
            rel.target_belief_id,
        )
        self._edges[rel.relationship_id] = rel

        # Ensure both nodes exist
        if rel.source_belief_id not in self._nodes:
            logger.warning(
                "[BELIEF_GRAPH] Source belief %s not in graph, adding placeholder",
                rel.source_belief_id,
            )
            self._nodes[rel.source_belief_id] = Belief(
                belief_id=rel.source_belief_id,
                statement="",
                domain="unknown",
                confidence=0.0,
            )
        if rel.target_belief_id not in self._nodes:
            logger.warning(
                "[BELIEF_GRAPH] Target belief %s not in graph, adding placeholder",
                rel.target_belief_id,
            )
            self._nodes[rel.target_belief_id] = Belief(
                belief_id=rel.target_belief_id,
                statement="",
                domain="unknown",
                confidence=0.0,
            )

        # Update adjacency lists (bidirectional for graph traversal)
        self._adjacency.setdefault(rel.source_belief_id, {})[
            rel.target_belief_id
        ] = rel.relationship_id
        self._adjacency.setdefault(rel.target_belief_id, {})[
            rel.source_belief_id
        ] = rel.relationship_id

    def get_belief(self, belief_id: str) -> Belief | None:
        """Get a belief by ID."""
        return self._nodes.get(belief_id)

    def get_relationship(self, relationship_id: str) -> BeliefRelationship | None:
        """Get a relationship by ID."""
        return self._edges.get(relationship_id)

    def get_neighbors(self, belief_id: str) -> list[Belief]:
        """Get all beliefs directly connected to the given belief."""
        if belief_id not in self._adjacency:
            return []
        neighbor_ids = self._adjacency[belief_id].keys()
        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    def get_transitive_closure(self, belief_id: str, max_depth: int = 10) -> set[str]:
        """Get all beliefs reachable from the given belief."""
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(belief_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth:
                continue
            if current in visited:
                continue
            visited.add(current)

            if current in self._adjacency:
                for neighbor_id in self._adjacency[current]:
                    if neighbor_id not in visited:
                        queue.append((neighbor_id, depth + 1))

        visited.discard(belief_id)  # Exclude the starting node
        return visited

    def find_paths(self, start: str, end: str, max_length: int = 5) -> list[list[str]]:
        """Find all paths between two beliefs up to max_length."""
        if start not in self._adjacency or end not in self._adjacency:
            return []

        paths: list[list[str]] = []
        queue: list[tuple[str, list[str]]] = [(start, [start])]

        while queue:
            current, path = queue.pop(0)
            if len(path) > max_length:
                continue
            if current == end and len(path) > 1:
                paths.append(path)
                continue

            if current in self._adjacency:
                for neighbor_id in self._adjacency[current]:
                    if neighbor_id not in path:  # Avoid cycles
                        queue.append((neighbor_id, path + [neighbor_id]))

        return paths

    def get_subgraph(self, domain: str) -> BeliefGraph:
        """Get beliefs and relationships within a specific domain."""
        subgraph = BeliefGraph(redis_client=self._redis_client)

        # Add beliefs in domain
        for _, belief in self._nodes.items():
            if belief.domain == domain:
                subgraph.add_belief(belief)

        # Add relationships where both beliefs are in domain
        for rel in self._edges.values():
            if (
                rel.source_belief_id in subgraph._nodes
                and rel.target_belief_id in subgraph._nodes
            ):
                subgraph.add_relationship(rel)

        return subgraph

    def to_networkx(self) -> Any:
        """Export to networkx DiGraph for visualization and advanced algorithms."""
        try:
            import networkx as nx

            G = nx.DiGraph()

            # Add nodes with attributes
            for belief_id, belief in self._nodes.items():
                G.add_node(
                    belief_id,
                    statement=belief.statement,
                    domain=belief.domain,
                    confidence=belief.confidence,
                    status=belief.status,
                )

            # Add edges with attributes
            for rel in self._edges.values():
                G.add_edge(
                    rel.source_belief_id,
                    rel.target_belief_id,
                    relationship_id=rel.relationship_id,
                    relationship_type=rel.relationship_type,
                    strength=rel.strength,
                )

            return G
        except ImportError:
            logger.warning("networkx not available, cannot export to networkx")
            return None

    def save_to_redis(self) -> None:
        """Persist graph structure to Redis."""
        logger.info("[BELIEF_GRAPH] Saving graph to Redis")
        try:
            if self._redis_client is not None:
                self._save_with_external_client()
            else:
                self._save_with_module_tools()
        except Exception as e:
            logger.error("[BELIEF_GRAPH] Failed to save to Redis: %s", e)
            raise

    def _save_with_external_client(self) -> None:
        """Save using external Redis client."""
        # Save nodes
        nodes_data = {
            belief_id: json.dumps(belief.to_dict())
            for belief_id, belief in self._nodes.items()
        }
        if nodes_data:
            self._redis_client.hset(GRAPH_INDEX_KEY, mapping=nodes_data)

        # Save edges
        edges_data = {
            rel_id: json.dumps(rel.to_dict()) for rel_id, rel in self._edges.items()
        }
        if edges_data:
            self._redis_client.hset(GRAPH_RELATIONSHIPS_KEY, mapping=edges_data)

        # Save metadata
        metadata = {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "saved_at": datetime.now(UTC).isoformat(),
        }
        self._redis_client.set(GRAPH_METADATA_KEY, json.dumps(metadata))

    def _save_with_module_tools(self) -> None:
        """Save using module-level Redis tools."""
        from tools.redis_state import redis_state_hset, redis_state_set

        # Save nodes
        for belief_id, belief in self._nodes.items():
            hset_result = redis_state_hset(
                GRAPH_INDEX_KEY, belief_id, json.dumps(belief.to_dict())
            )
            logger.debug(
                "[BELIEF_GRAPH] hset result for node %s: %s", belief_id, hset_result
            )

        # Save edges
        for rel_id, rel in self._edges.items():
            hset_result = redis_state_hset(
                GRAPH_RELATIONSHIPS_KEY, rel_id, json.dumps(rel.to_dict())
            )
            logger.debug(
                "[BELIEF_GRAPH] hset result for edge %s: %s", rel_id, hset_result
            )

        # Save metadata
        metadata = {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "saved_at": datetime.now(UTC).isoformat(),
        }
        set_result = redis_state_set(GRAPH_METADATA_KEY, json.dumps(metadata))
        logger.debug("[BELIEF_GRAPH] metadata save result: %s", set_result)

    def load_from_redis(self) -> None:
        """Reconstruct graph from Redis."""
        logger.info("[BELIEF_GRAPH] Loading graph from Redis")
        try:
            if self._redis_client is not None:
                self._load_with_external_client()
            else:
                self._load_with_module_tools()
        except Exception as e:
            logger.error("[BELIEF_GRAPH] Failed to load from Redis: %s", e)
            raise

    def _load_with_external_client(self) -> None:
        """Load using external Redis client."""
        # Load nodes
        nodes_data = self._redis_client.hgetall(GRAPH_INDEX_KEY) or {}
        for belief_id, payload in nodes_data.items():
            belief = Belief.from_dict(json.loads(payload))
            self._nodes[belief_id] = belief
            self._adjacency[belief_id] = {}

        # Load edges
        edges_data = self._redis_client.hgetall(GRAPH_RELATIONSHIPS_KEY) or {}
        for rel_id, payload in edges_data.items():
            rel = BeliefRelationship.from_dict(json.loads(payload))
            self._edges[rel_id] = rel
            self._adjacency.setdefault(rel.source_belief_id, {})[
                rel.target_belief_id
            ] = rel_id
            self._adjacency.setdefault(rel.target_belief_id, {})[
                rel.source_belief_id
            ] = rel_id

    def _load_with_module_tools(self) -> None:
        """Load using module-level Redis tools."""
        from tools.redis_state import redis_state_hgetall

        # Load nodes
        nodes_data = redis_state_hgetall(GRAPH_INDEX_KEY) or {}
        for belief_id, payload in nodes_data.items():
            if isinstance(payload, str):
                payload = json.loads(payload)
            belief = Belief.from_dict(payload)
            self._nodes[belief_id] = belief
            self._adjacency[belief_id] = {}

        # Load edges
        edges_data = redis_state_hgetall(GRAPH_RELATIONSHIPS_KEY) or {}
        for rel_id, payload in edges_data.items():
            if isinstance(payload, str):
                payload = json.loads(payload)
            rel = BeliefRelationship.from_dict(payload)
            self._edges[rel_id] = rel
            self._adjacency.setdefault(rel.source_belief_id, {})[
                rel.target_belief_id
            ] = rel_id
            self._adjacency.setdefault(rel.target_belief_id, {})[
                rel.source_belief_id
            ] = rel_id

    def get_beliefs_with_relationships(
        self,
    ) -> tuple[list[Belief], list[BeliefRelationship]]:
        """Return all beliefs and relationships as lists."""
        return list(self._nodes.values()), list(self._edges.values())

    def belief_count(self) -> int:
        """Return the number of beliefs in the graph."""
        return len(self._nodes)

    def relationship_count(self) -> int:
        """Return the number of relationships in the graph."""
        return len(self._edges)

    def get_beliefs_by_domain(self, domain: str) -> list[Belief]:
        """Get all beliefs in a specific domain."""
        return [b for b in self._nodes.values() if b.domain == domain]

    def get_conflicts_involving(self, belief_id: str) -> list[BeliefRelationship]:
        """Get all CONTRADICTS relationships involving a belief."""
        return [
            rel
            for rel in self._edges.values()
            if rel.relationship_type == "contradicts"
            and (rel.source_belief_id == belief_id or rel.target_belief_id == belief_id)
        ]

    def clear(self) -> None:
        """Clear all nodes and edges from the graph."""
        self._nodes.clear()
        self._edges.clear()
        self._adjacency.clear()

    def __repr__(self) -> str:
        return f"BeliefGraph(nodes={len(self._nodes)}, edges={len(self._edges)})"
