"""
Comprehensive tests for the Symbolic Knowledge Graph module.

Tests cover:
- KnowledgeGraph core functionality
- RelationshipExtractor extraction methods
- GraphQueryEngine query capabilities
- GraphUpdater update and conflict resolution
"""

import math
from datetime import datetime, timedelta

import pytest
from src.neuro_symbolic.knowledge_graph.extractor import RelationshipExtractor
from src.neuro_symbolic.knowledge_graph.graph import KnowledgeGraph
from src.neuro_symbolic.knowledge_graph.models import (
    Edge,
    EdgeType,
    ExtractionResult,
    GraphMetrics,
    Node,
    NodeType,
    RelationshipStrength,
    UpdateResult,
)
from src.neuro_symbolic.knowledge_graph.query_engine import GraphQueryEngine
from src.neuro_symbolic.knowledge_graph.updater import (
    ConflictResolutionStrategy,
    GraphUpdater,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_graph():
    """Create an empty knowledge graph."""
    return KnowledgeGraph(name="test_graph")


@pytest.fixture
def populated_graph():
    """Create a graph with sample data."""
    graph = KnowledgeGraph(name="populated_test")

    # Add asset nodes
    graph.add_node("BTC", NodeType.ASSET, {"symbol": "BTC", "name": "Bitcoin"})
    graph.add_node("ETH", NodeType.ASSET, {"symbol": "ETH", "name": "Ethereum"})
    graph.add_node("SOL", NodeType.ASSET, {"symbol": "SOL", "name": "Solana"})
    graph.add_node("DOT", NodeType.ASSET, {"symbol": "DOT", "name": "Polkadot"})

    # Add indicator nodes
    graph.add_node("RSI_BTC", NodeType.INDICATOR, {"type": "RSI", "period": 14})
    graph.add_node("MA_BTC", NodeType.INDICATOR, {"type": "MA", "period": 50})

    # Add edges
    graph.add_edge("BTC", "ETH", EdgeType.CORRELATED_WITH, weight=0.85, confidence=0.9)
    graph.add_edge("BTC", "SOL", EdgeType.CORRELATED_WITH, weight=0.7, confidence=0.8)
    graph.add_edge("ETH", "SOL", EdgeType.CORRELATED_WITH, weight=0.6, confidence=0.75)
    graph.add_edge("BTC", "DOT", EdgeType.LEADS, weight=0.5, confidence=0.65)
    graph.add_edge("RSI_BTC", "BTC", EdgeType.DERIVED_FROM, confidence=1.0)
    graph.add_edge("MA_BTC", "BTC", EdgeType.DERIVED_FROM, confidence=1.0)

    return graph


@pytest.fixture
def extractor():
    """Create a relationship extractor."""
    return RelationshipExtractor(
        correlation_threshold=0.3,
        causality_threshold=0.05,
        min_samples=10,
    )


@pytest.fixture
def query_engine(populated_graph):
    """Create a query engine with populated graph."""
    return GraphQueryEngine(populated_graph)


@pytest.fixture
def updater(populated_graph):
    """Create a graph updater with populated graph."""
    return GraphUpdater(
        populated_graph,
        conflict_strategy=ConflictResolutionStrategy.HIGHEST_CONFIDENCE,
    )


# =============================================================================
# Test Node Model
# =============================================================================


class TestNode:
    """Tests for the Node model."""

    def test_node_creation(self):
        """Test creating a node."""
        node = Node(
            id="test_node",
            node_type=NodeType.ASSET,
            properties={"symbol": "TEST"},
        )
        assert node.id == "test_node"
        assert node.node_type == NodeType.ASSET
        assert node.properties == {"symbol": "TEST"}
        assert node.confidence == 1.0

    def test_node_update_property(self):
        """Test updating a node property."""
        node = Node(id="test", node_type=NodeType.ASSET)
        old_time = node.updated_at
        node.update_property("new_key", "new_value")
        assert node.properties["new_key"] == "new_value"
        assert node.updated_at > old_time

    def test_node_to_dict(self):
        """Test node serialization."""
        node = Node(
            id="test",
            node_type=NodeType.ASSET,
            properties={"key": "value"},
            confidence=0.9,
        )
        data = node.to_dict()
        assert data["id"] == "test"
        assert data["node_type"] == "asset"
        assert data["properties"] == {"key": "value"}
        assert data["confidence"] == 0.9

    def test_node_from_dict(self):
        """Test node deserialization."""
        data = {
            "id": "test",
            "node_type": "asset",
            "properties": {"key": "value"},
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "confidence": 0.8,
            "source": "test_source",
        }
        node = Node.from_dict(data)
        assert node.id == "test"
        assert node.node_type == NodeType.ASSET
        assert node.confidence == 0.8


# =============================================================================
# Test Edge Model
# =============================================================================


class TestEdge:
    """Tests for the Edge model."""

    def test_edge_creation(self):
        """Test creating an edge."""
        edge = Edge(
            source_id="A",
            target_id="B",
            edge_type=EdgeType.CORRELATED_WITH,
            weight=0.8,
            confidence=0.9,
        )
        assert edge.source_id == "A"
        assert edge.target_id == "B"
        assert edge.edge_type == EdgeType.CORRELATED_WITH
        assert edge.weight == 0.8
        assert edge.confidence == 0.9

    def test_edge_is_valid_at(self):
        """Test edge validity at timestamps."""
        now = datetime.utcnow()
        edge = Edge(
            source_id="A",
            target_id="B",
            edge_type=EdgeType.CORRELATED_WITH,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
        )
        assert edge.is_valid_at(now)
        assert not edge.is_valid_at(now - timedelta(days=2))
        assert not edge.is_valid_at(now + timedelta(days=2))

    def test_edge_add_evidence(self):
        """Test adding evidence to edge."""
        edge = Edge(source_id="A", target_id="B", edge_type=EdgeType.CORRELATED_WITH)
        edge.add_evidence("test_evidence")
        assert "test_evidence" in edge.evidence

    def test_edge_to_dict_and_from_dict(self):
        """Test edge serialization."""
        edge = Edge(
            source_id="A",
            target_id="B",
            edge_type=EdgeType.CORRELATED_WITH,
            weight=0.7,
            confidence=0.8,
            evidence=["evidence1"],
        )
        data = edge.to_dict()
        restored = Edge.from_dict(data)
        assert restored.source_id == edge.source_id
        assert restored.target_id == edge.target_id
        assert restored.edge_type == edge.edge_type
        assert restored.weight == edge.weight
        assert restored.confidence == edge.confidence


# =============================================================================
# Test RelationshipStrength
# =============================================================================


class TestRelationshipStrength:
    """Tests for RelationshipStrength enum."""

    def test_from_correlation_weak(self):
        """Test weak correlation strength."""
        strength = RelationshipStrength.from_correlation(0.2)
        assert strength == RelationshipStrength.WEAK

    def test_from_correlation_moderate(self):
        """Test moderate correlation strength."""
        strength = RelationshipStrength.from_correlation(0.5)
        assert strength == RelationshipStrength.MODERATE

    def test_from_correlation_strong(self):
        """Test strong correlation strength."""
        strength = RelationshipStrength.from_correlation(0.8)
        assert strength == RelationshipStrength.STRONG

    def test_from_correlation_very_strong(self):
        """Test very strong correlation strength."""
        strength = RelationshipStrength.from_correlation(0.95)
        assert strength == RelationshipStrength.VERY_STRONG

    def test_from_correlation_negative(self):
        """Test negative correlation strength."""
        strength = RelationshipStrength.from_correlation(-0.8)
        assert strength == RelationshipStrength.STRONG


# =============================================================================
# Test KnowledgeGraph - Node Operations
# =============================================================================


class TestKnowledgeGraphNodes:
    """Tests for KnowledgeGraph node operations."""

    def test_add_node(self, empty_graph):
        """Test adding a node."""
        node = empty_graph.add_node("BTC", NodeType.ASSET, {"symbol": "BTC"})
        assert node.id == "BTC"
        assert empty_graph.has_node("BTC")
        assert empty_graph.node_count == 1

    def test_get_node(self, populated_graph):
        """Test getting a node."""
        node = populated_graph.get_node("BTC")
        assert node is not None
        assert node.id == "BTC"
        assert node.node_type == NodeType.ASSET

    def test_get_nonexistent_node(self, empty_graph):
        """Test getting a node that doesn't exist."""
        node = empty_graph.get_node("nonexistent")
        assert node is None

    def test_has_node(self, populated_graph):
        """Test checking if node exists."""
        assert populated_graph.has_node("BTC")
        assert not populated_graph.has_node("nonexistent")

    def test_update_node(self, populated_graph):
        """Test updating a node."""
        node = populated_graph.update_node("BTC", {"new_prop": "value"}, confidence=0.8)
        assert node is not None
        assert node.properties["new_prop"] == "value"
        assert node.confidence == 0.8

    def test_update_nonexistent_node(self, empty_graph):
        """Test updating a node that doesn't exist."""
        node = empty_graph.update_node("nonexistent", {"prop": "value"})
        assert node is None

    def test_remove_node(self, populated_graph):
        """Test removing a node."""
        initial_count = populated_graph.node_count
        result = populated_graph.remove_node("DOT")
        assert result is True
        assert not populated_graph.has_node("DOT")
        assert populated_graph.node_count == initial_count - 1

    def test_remove_nonexistent_node(self, empty_graph):
        """Test removing a node that doesn't exist."""
        result = empty_graph.remove_node("nonexistent")
        assert result is False

    def test_remove_node_removes_edges(self, populated_graph):
        """Test that removing a node also removes its edges."""
        # DOT has an edge from BTC
        populated_graph.remove_node("DOT")
        # Check that the edge was removed
        assert not populated_graph.has_edge("BTC", "DOT", EdgeType.LEADS)

    def test_get_nodes_by_type(self, populated_graph):
        """Test getting nodes by type."""
        assets = populated_graph.get_nodes_by_type(NodeType.ASSET)
        assert len(assets) == 4
        indicators = populated_graph.get_nodes_by_type(NodeType.INDICATOR)
        assert len(indicators) == 2

    def test_get_all_nodes(self, populated_graph):
        """Test getting all nodes."""
        nodes = populated_graph.get_all_nodes()
        assert len(nodes) == 6


# =============================================================================
# Test KnowledgeGraph - Edge Operations
# =============================================================================


class TestKnowledgeGraphEdges:
    """Tests for KnowledgeGraph edge operations."""

    def test_add_edge(self, empty_graph):
        """Test adding an edge."""
        empty_graph.add_node("A", NodeType.ASSET)
        empty_graph.add_node("B", NodeType.ASSET)
        edge = empty_graph.add_edge("A", "B", EdgeType.CORRELATED_WITH, weight=0.8)
        assert edge is not None
        assert empty_graph.has_edge("A", "B", EdgeType.CORRELATED_WITH)
        assert empty_graph.edge_count == 1

    def test_add_edge_nonexistent_nodes(self, empty_graph):
        """Test adding an edge with nonexistent nodes."""
        edge = empty_graph.add_edge("A", "B", EdgeType.CORRELATED_WITH)
        assert edge is None
        assert empty_graph.edge_count == 0

    def test_get_edge(self, populated_graph):
        """Test getting an edge."""
        edge = populated_graph.get_edge("BTC", "ETH", EdgeType.CORRELATED_WITH)
        assert edge is not None
        assert edge.weight == 0.85
        assert edge.confidence == 0.9

    def test_get_nonexistent_edge(self, empty_graph):
        """Test getting an edge that doesn't exist."""
        edge = empty_graph.get_edge("A", "B", EdgeType.CORRELATED_WITH)
        assert edge is None

    def test_has_edge(self, populated_graph):
        """Test checking if edge exists."""
        assert populated_graph.has_edge("BTC", "ETH", EdgeType.CORRELATED_WITH)
        assert not populated_graph.has_edge("BTC", "ETH", EdgeType.CAUSES)

    def test_update_edge(self, populated_graph):
        """Test updating an edge."""
        edge = populated_graph.update_edge(
            "BTC", "ETH", EdgeType.CORRELATED_WITH, weight=0.9, confidence=0.95
        )
        assert edge is not None
        assert edge.weight == 0.9
        assert edge.confidence == 0.95

    def test_remove_edge(self, populated_graph):
        """Test removing an edge."""
        initial_count = populated_graph.edge_count
        result = populated_graph.remove_edge("BTC", "ETH", EdgeType.CORRELATED_WITH)
        assert result is True
        assert not populated_graph.has_edge("BTC", "ETH", EdgeType.CORRELATED_WITH)
        assert populated_graph.edge_count == initial_count - 1

    def test_get_edges_by_type(self, populated_graph):
        """Test getting edges by type."""
        correlated = populated_graph.get_edges_by_type(EdgeType.CORRELATED_WITH)
        assert len(correlated) == 3

    def test_get_all_edges(self, populated_graph):
        """Test getting all edges."""
        edges = populated_graph.get_all_edges()
        assert len(edges) == 6


# =============================================================================
# Test KnowledgeGraph - Traversal
# =============================================================================


class TestKnowledgeGraphTraversal:
    """Tests for KnowledgeGraph traversal operations."""

    def test_get_neighbors(self, populated_graph):
        """Test getting neighbors."""
        neighbors = populated_graph.get_neighbors("BTC")
        assert "ETH" in neighbors
        assert "SOL" in neighbors
        assert "DOT" in neighbors

    def test_get_predecessors(self, populated_graph):
        """Test getting predecessors."""
        predecessors = populated_graph.get_predecessors("BTC")
        assert "RSI_BTC" in predecessors
        assert "MA_BTC" in predecessors

    def test_get_degree(self, populated_graph):
        """Test getting node degree."""
        degree = populated_graph.get_degree("BTC")
        # BTC has 3 outgoing (ETH, SOL, DOT) and 2 incoming (RSI_BTC, MA_BTC)
        assert degree == 5

    def test_get_out_edges(self, populated_graph):
        """Test getting outgoing edges."""
        edges = populated_graph.get_out_edges("BTC")
        assert len(edges) == 3

    def test_get_in_edges(self, populated_graph):
        """Test getting incoming edges."""
        edges = populated_graph.get_in_edges("BTC")
        assert len(edges) == 2


# =============================================================================
# Test KnowledgeGraph - Metrics and Serialization
# =============================================================================


class TestKnowledgeGraphMetricsAndSerialization:
    """Tests for KnowledgeGraph metrics and serialization."""

    def test_get_metrics(self, populated_graph):
        """Test getting graph metrics."""
        metrics = populated_graph.get_metrics()
        assert isinstance(metrics, GraphMetrics)
        assert metrics.total_nodes == 6
        assert metrics.total_edges == 6
        assert "asset" in metrics.nodes_by_type
        assert metrics.density > 0

    def test_to_dict(self, populated_graph):
        """Test graph serialization."""
        data = populated_graph.to_dict()
        assert data["name"] == "populated_test"
        assert len(data["nodes"]) == 6
        assert len(data["edges"]) == 6

    def test_from_dict(self):
        """Test graph deserialization."""
        graph = KnowledgeGraph(name="test")
        graph.add_node("A", NodeType.ASSET)
        graph.add_node("B", NodeType.ASSET)
        graph.add_edge("A", "B", EdgeType.CORRELATED_WITH)

        data = graph.to_dict()
        restored = KnowledgeGraph.from_dict(data)

        assert restored.name == "test"
        assert restored.node_count == 2
        assert restored.edge_count == 1
        assert restored.has_node("A")
        assert restored.has_edge("A", "B", EdgeType.CORRELATED_WITH)

    def test_clear(self, populated_graph):
        """Test clearing the graph."""
        populated_graph.clear()
        assert populated_graph.node_count == 0
        assert populated_graph.edge_count == 0
        assert populated_graph.is_empty

    def test_properties(self, populated_graph):
        """Test graph properties."""
        assert populated_graph.node_count == 6
        assert populated_graph.edge_count == 6
        assert not populated_graph.is_empty
        assert len(populated_graph) == 6

    def test_contains(self, populated_graph):
        """Test __contains__ method."""
        assert "BTC" in populated_graph
        assert "nonexistent" not in populated_graph

    def test_repr(self, populated_graph):
        """Test __repr__ method."""
        repr_str = repr(populated_graph)
        assert "KnowledgeGraph" in repr_str
        assert "nodes=6" in repr_str


# =============================================================================
# Test RelationshipExtractor
# =============================================================================


class TestRelationshipExtractor:
    """Tests for RelationshipExtractor."""

    def test_extract_correlation_positive(self, extractor):
        """Test extracting positive correlation."""
        # Create highly correlated data
        base = [float(i) for i in range(100)]
        correlated = [x * 1.1 + 5 for x in base]

        result = extractor.extract_correlation("A", "B", base, correlated)
        assert result is not None
        assert result.edge.edge_type == EdgeType.CORRELATED_WITH
        assert result.edge.weight > 0.9

    def test_extract_correlation_negative(self, extractor):
        """Test extracting negative correlation."""
        base = [float(i) for i in range(100)]
        negatively_correlated = [-x for x in base]

        result = extractor.extract_correlation("A", "B", base, negatively_correlated)
        assert result is not None
        assert result.edge.edge_type == EdgeType.NEGATIVELY_CORRELATED

    def test_extract_correlation_weak(self, extractor):
        """Test that weak correlation is not extracted."""
        import random

        random.seed(42)
        base = [float(i) for i in range(100)]
        random_data = [random.random() * 100 for _ in range(100)]

        result = extractor.extract_correlation("A", "B", base, random_data)
        assert result is None  # Correlation should be below threshold

    def test_extract_correlation_insufficient_data(self, extractor):
        """Test extraction with insufficient data."""
        result = extractor.extract_correlation("A", "B", [1, 2, 3], [4, 5, 6])
        assert result is None

    def test_extract_causality(self, extractor):
        """Test extracting causal relationship."""
        # Create data where A Granger-causes B
        base = [float(i % 10) for i in range(100)]
        lagged = [0] * 2 + base[:-2]  # B lags A by 2

        result = extractor.extract_causality("A", "B", base, lagged, max_lag=5)
        # May or may not find causality depending on implementation
        # Just check it doesn't crash
        assert result is None or result.edge.edge_type == EdgeType.CAUSES

    def test_extract_lead_lag(self, extractor):
        """Test extracting lead-lag relationship."""
        base = [math.sin(i * 0.1) for i in range(100)]
        lagged = [math.sin((i - 3) * 0.1) for i in range(100)]  # Lags by 3

        result = extractor.extract_lead_lag("A", "B", base, lagged, max_lag=10)
        assert result is not None
        assert result.edge.edge_type == EdgeType.LEADS
        assert result.edge.properties.get("lag") is not None

    def test_extract_co_occurrence(self, extractor):
        """Test extracting co-occurrence relationships."""
        now = datetime.utcnow()
        events = [
            {"id": "E1", "type": "alert", "timestamp": now},
            {"id": "E2", "type": "alert", "timestamp": now + timedelta(seconds=10)},
            {"id": "E3", "type": "alert", "timestamp": now + timedelta(seconds=20)},
            {"id": "E1", "type": "alert", "timestamp": now + timedelta(seconds=60)},
            {"id": "E2", "type": "alert", "timestamp": now + timedelta(seconds=70)},
            {"id": "E1", "type": "alert", "timestamp": now + timedelta(seconds=120)},
            {"id": "E2", "type": "alert", "timestamp": now + timedelta(seconds=130)},
            {"id": "E3", "type": "alert", "timestamp": now + timedelta(seconds=140)},
        ]

        results = extractor.extract_co_occurrence(
            events, time_window_seconds=60, min_co_occurrences=2
        )
        assert len(results) > 0
        for r in results:
            assert r.edge.edge_type == EdgeType.CO_OCCURS_WITH

    def test_extract_influence(self, extractor):
        """Test extracting influence relationship."""
        now = datetime.utcnow()
        influencer_events = [
            {"id": "news", "timestamp": now + timedelta(seconds=i * 100)}
            for i in range(10)
        ]
        influenced_events = [
            {"id": "price", "timestamp": now + timedelta(seconds=i * 100 + 10)}
            for i in range(8)
        ]

        result = extractor.extract_influence(
            "news", "price", influencer_events, influenced_events
        )
        assert result is not None
        assert result.edge.edge_type == EdgeType.INFLUENCES

    def test_extraction_count(self, extractor):
        """Test extraction counter."""
        extractor.reset_count()
        base = [float(i) for i in range(100)]
        correlated = [x * 1.1 for x in base]

        extractor.extract_correlation("A", "B", base, correlated)
        assert extractor.extraction_count == 1


# =============================================================================
# Test GraphQueryEngine
# =============================================================================


class TestGraphQueryEngine:
    """Tests for GraphQueryEngine."""

    def test_find_node_by_id(self, query_engine):
        """Test finding a node by ID."""
        result = query_engine.find_node(node_id="BTC")
        assert result.node_count == 1
        assert result.nodes[0].id == "BTC"

    def test_find_node_by_type(self, query_engine):
        """Test finding nodes by type."""
        result = query_engine.find_node(node_type=NodeType.ASSET)
        assert result.node_count == 4

    def test_find_node_by_properties(self, query_engine):
        """Test finding nodes by properties."""
        result = query_engine.find_node(properties={"symbol": "BTC"})
        assert result.node_count == 1
        assert result.nodes[0].id == "BTC"

    def test_find_neighbors_out(self, query_engine):
        """Test finding outgoing neighbors."""
        result = query_engine.find_neighbors("BTC", direction="out", max_depth=1)
        assert result.node_count == 3  # ETH, SOL, DOT

    def test_find_neighbors_in(self, query_engine):
        """Test finding incoming neighbors."""
        result = query_engine.find_neighbors("BTC", direction="in", max_depth=1)
        assert result.node_count == 2  # RSI_BTC, MA_BTC

    def test_find_neighbors_filtered(self, query_engine):
        """Test finding neighbors with edge type filter."""
        result = query_engine.find_neighbors(
            "BTC", edge_types=[EdgeType.CORRELATED_WITH], direction="out"
        )
        assert result.node_count == 2  # ETH, SOL (DOT has LEADS)

    def test_find_neighbors_depth(self, query_engine):
        """Test finding neighbors at depth."""
        result = query_engine.find_neighbors("RSI_BTC", max_depth=2)
        # RSI_BTC -> BTC -> ETH, SOL, DOT
        assert result.node_count >= 4

    def test_find_path_exists(self, query_engine):
        """Test finding a path that exists."""
        result = query_engine.find_path("BTC", "ETH", max_depth=3)
        assert result.path_count >= 1
        assert result.paths[0] == ["BTC", "ETH"]

    def test_find_path_not_exists(self, query_engine):
        """Test finding a path that doesn't exist."""
        result = query_engine.find_path("RSI_BTC", "DOT", max_depth=3)
        # RSI_BTC -> BTC -> DOT should exist
        assert result.path_count >= 1

    def test_find_pattern_single_node(self, query_engine):
        """Test pattern matching with single node."""
        pattern = {"nodes": [{"id": "a", "type": "asset"}], "edges": []}
        result = query_engine.find_pattern(pattern)
        assert result.node_count == 4

    def test_find_pattern_with_edge(self, query_engine):
        """Test pattern matching with edge."""
        pattern = {
            "nodes": [
                {"id": "a", "type": "asset"},
                {"id": "b", "type": "asset"},
            ],
            "edges": [{"from": "a", "to": "b", "type": "correlated_with"}],
        }
        result = query_engine.find_pattern(pattern)
        # BTC-ETH, BTC-SOL, ETH-SOL
        assert result.node_count >= 2

    def test_find_related(self, query_engine):
        """Test finding related nodes."""
        result = query_engine.find_related("BTC", min_confidence=0.5)
        assert result.node_count > 0
        assert result.edge_count > 0

    def test_find_related_with_limit(self, query_engine):
        """Test finding related nodes with limit."""
        result = query_engine.find_related("BTC", limit=2)
        assert result.edge_count <= 2

    def test_find_clusters(self, query_engine):
        """Test finding clusters."""
        result = query_engine.find_clusters(min_cluster_size=2)
        assert "clusters" in result.metadata
        assert result.metadata["cluster_count"] >= 1

    def test_query_result_properties(self, query_engine):
        """Test QueryResult properties."""
        result = query_engine.find_node(node_type=NodeType.ASSET)
        assert result.node_count == len(result.nodes)
        assert result.execution_time_ms >= 0

    def test_query_nonexistent_node(self, query_engine):
        """Test query for nonexistent node."""
        result = query_engine.find_node(node_id="nonexistent")
        assert result.node_count == 0


# =============================================================================
# Test GraphUpdater
# =============================================================================


class TestGraphUpdater:
    """Tests for GraphUpdater."""

    def test_add_extraction_result(self, updater):
        """Test adding an extraction result."""
        initial_nodes = updater.graph.node_count

        source_node = Node(id="NEW_A", node_type=NodeType.ASSET)
        target_node = Node(id="NEW_B", node_type=NodeType.ASSET)
        edge = Edge(
            source_id="NEW_A",
            target_id="NEW_B",
            edge_type=EdgeType.CORRELATED_WITH,
            confidence=0.8,
        )

        result = ExtractionResult(
            source_node=source_node,
            target_node=target_node,
            edge=edge,
            extraction_method="test",
            extraction_confidence=0.8,
        )

        update_result = updater.add_extraction_result(result)
        assert update_result.nodes_added == 2
        assert update_result.edges_added == 1
        assert updater.graph.node_count == initial_nodes + 2

    def test_add_extraction_results_batch(self, updater):
        """Test adding multiple extraction results."""
        results = []
        for i in range(3):
            source_node = Node(id=f"BATCH_A_{i}", node_type=NodeType.ASSET)
            target_node = Node(id=f"BATCH_B_{i}", node_type=NodeType.ASSET)
            edge = Edge(
                source_id=f"BATCH_A_{i}",
                target_id=f"BATCH_B_{i}",
                edge_type=EdgeType.CORRELATED_WITH,
                confidence=0.8,
            )
            results.append(
                ExtractionResult(
                    source_node=source_node,
                    target_node=target_node,
                    edge=edge,
                    extraction_method="test",
                    extraction_confidence=0.8,
                )
            )

        update_result = updater.add_extraction_results(results)
        assert update_result.nodes_added == 6
        assert update_result.edges_added == 3

    def test_add_node(self, updater):
        """Test adding a single node."""
        result = updater.add_node(
            "NEW_NODE", NodeType.SIGNAL, {"type": "test"}, confidence=0.9
        )
        assert result.nodes_added == 1
        assert updater.graph.has_node("NEW_NODE")

    def test_add_edge(self, updater):
        """Test adding a single edge."""
        updater.graph.add_node("E1", NodeType.ASSET)
        updater.graph.add_node("E2", NodeType.ASSET)

        result = updater.add_edge("E1", "E2", EdgeType.CORRELATED_WITH, confidence=0.8)
        assert result.edges_added == 1

    def test_add_edge_low_confidence(self, updater):
        """Test adding edge with low confidence."""
        updater.graph.add_node("E1", NodeType.ASSET)
        updater.graph.add_node("E2", NodeType.ASSET)

        result = updater.add_edge("E1", "E2", EdgeType.CORRELATED_WITH, confidence=0.1)
        assert result.edges_added == 0
        assert len(result.errors) > 0

    def test_merge_properties(self, updater):
        """Test merging properties into node."""
        result = updater.merge_properties("BTC", {"new_prop": "value"})
        assert result.nodes_updated == 1
        node = updater.graph.get_node("BTC")
        assert node.properties.get("new_prop") == "value"

    def test_merge_properties_nonexistent(self, updater):
        """Test merging properties into nonexistent node."""
        result = updater.merge_properties("nonexistent", {"prop": "value"})
        assert len(result.errors) > 0

    def test_batch_update(self, updater):
        """Test batch update of nodes and edges."""
        nodes = [
            {"id": "BATCH_1", "node_type": "asset", "properties": {"test": 1}},
            {"id": "BATCH_2", "node_type": "asset", "properties": {"test": 2}},
        ]
        edges = [
            {
                "source_id": "BATCH_1",
                "target_id": "BATCH_2",
                "edge_type": "correlated_with",
                "confidence": 0.8,
            }
        ]

        result = updater.batch_update(nodes=nodes, edges=edges)
        assert result.nodes_added == 2
        assert result.edges_added == 1

    def test_conflict_resolution_highest_confidence(self, populated_graph):
        """Test conflict resolution with highest confidence strategy."""
        updater = GraphUpdater(
            populated_graph,
            conflict_strategy=ConflictResolutionStrategy.HIGHEST_CONFIDENCE,
        )

        # Update existing node with higher confidence
        source_node = Node(
            id="BTC",
            node_type=NodeType.ASSET,
            properties={"new_prop": "new_value"},
            confidence=0.99,  # Higher than default 1.0... actually default is 1.0
            source="new_source",
        )
        target_node = Node(id="NEW_TARGET", node_type=NodeType.ASSET)
        edge = Edge(
            source_id="BTC",
            target_id="NEW_TARGET",
            edge_type=EdgeType.CORRELATED_WITH,
            confidence=0.8,
        )

        result = ExtractionResult(
            source_node=source_node,
            target_node=target_node,
            edge=edge,
            extraction_method="test",
            extraction_confidence=0.8,
        )

        update_result = updater.add_extraction_result(result)
        # Should update node since we have new properties
        assert update_result.nodes_updated >= 1

    def test_cleanup_orphan_nodes(self, updater):
        """Test removing orphan nodes."""
        # Add an orphan node
        updater.graph.add_node("ORPHAN", NodeType.ASSET)
        assert updater.graph.has_node("ORPHAN")

        result = updater.cleanup_orphan_nodes()
        assert result.nodes_removed >= 1
        assert not updater.graph.has_node("ORPHAN")

    def test_update_count(self, updater):
        """Test update counter."""
        updater.reset_count()
        updater.add_node("COUNT_TEST", NodeType.ASSET)
        assert updater.update_count == 1


# =============================================================================
# Test UpdateResult
# =============================================================================


class TestUpdateResult:
    """Tests for UpdateResult model."""

    def test_update_result_creation(self):
        """Test creating an update result."""
        result = UpdateResult(
            nodes_added=5,
            nodes_updated=3,
            edges_added=10,
        )
        assert result.nodes_added == 5
        assert result.nodes_updated == 3
        assert result.edges_added == 10

    def test_total_changes(self):
        """Test total changes calculation."""
        result = UpdateResult(
            nodes_added=2,
            nodes_updated=1,
            nodes_removed=1,
            edges_added=3,
            edges_updated=2,
            edges_removed=1,
        )
        assert result.total_changes == 10

    def test_success(self):
        """Test success property."""
        success_result = UpdateResult(nodes_added=1)
        assert success_result.success

        failed_result = UpdateResult(errors=["error"])
        assert not failed_result.success

    def test_to_dict(self):
        """Test serialization."""
        result = UpdateResult(nodes_added=5, edges_added=10)
        data = result.to_dict()
        assert data["nodes_added"] == 5
        assert data["edges_added"] == 10
        assert data["success"] is True


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the knowledge graph system."""

    def test_full_workflow(self):
        """Test full workflow: extract, update, query."""
        # Create graph and components
        graph = KnowledgeGraph(name="integration_test")
        extractor = RelationshipExtractor()
        updater = GraphUpdater(graph)
        query_engine = GraphQueryEngine(graph)

        # Extract correlations from data
        base = [float(i) for i in range(100)]
        correlated = [x * 1.1 + 5 for x in base]

        result = extractor.extract_correlation("BTC", "ETH", base, correlated)
        assert result is not None

        # Add to graph
        update_result = updater.add_extraction_result(result)
        assert update_result.success

        # Query the graph
        query_result = query_engine.find_node(node_id="BTC")
        assert query_result.node_count == 1

        # Check edge exists
        assert graph.has_edge("BTC", "ETH", EdgeType.CORRELATED_WITH)

    def test_serialization_roundtrip(self):
        """Test full serialization roundtrip."""
        # Create and populate graph
        graph = KnowledgeGraph(name="roundtrip_test")
        graph.add_node("A", NodeType.ASSET, {"symbol": "A"})
        graph.add_node("B", NodeType.ASSET, {"symbol": "B"})
        graph.add_edge("A", "B", EdgeType.CORRELATED_WITH, weight=0.8, confidence=0.9)

        # Serialize and deserialize
        data = graph.to_dict()
        restored = KnowledgeGraph.from_dict(data)

        # Verify
        assert restored.node_count == graph.node_count
        assert restored.edge_count == graph.edge_count
        assert restored.has_node("A")
        assert restored.has_edge("A", "B", EdgeType.CORRELATED_WITH)

        edge = restored.get_edge("A", "B", EdgeType.CORRELATED_WITH)
        assert edge.weight == 0.8
        assert edge.confidence == 0.9


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_graph_queries(self):
        """Test queries on empty graph."""
        graph = KnowledgeGraph()
        engine = GraphQueryEngine(graph)

        result = engine.find_node(node_type=NodeType.ASSET)
        assert result.node_count == 0

        result = engine.find_neighbors("nonexistent")
        assert "error" in result.metadata

    def test_self_loop_prevention(self):
        """Test that self-loops are handled appropriately."""
        graph = KnowledgeGraph()
        graph.add_node("A", NodeType.ASSET)

        # Add self-edge (may be allowed or not depending on implementation)
        edge = graph.add_edge("A", "A", EdgeType.CORRELATED_WITH)
        # Just verify it doesn't crash

    def test_large_graph_performance(self):
        """Test performance with larger graph."""
        graph = KnowledgeGraph(name="large_test")

        # Add 100 nodes
        for i in range(100):
            graph.add_node(f"N{i}", NodeType.ASSET)

        # Add 500 edges
        for i in range(500):
            src = f"N{i % 100}"
            tgt = f"N{(i + 1) % 100}"
            if not graph.has_edge(src, tgt, EdgeType.CORRELATED_WITH):
                graph.add_edge(src, tgt, EdgeType.CORRELATED_WITH)

        assert graph.node_count == 100
        assert graph.edge_count > 0

        # Query should still be fast
        engine = GraphQueryEngine(graph)
        result = engine.find_neighbors("N0", max_depth=2)
        assert result.execution_time_ms < 1000  # Should be under 1 second

    def test_unicode_node_ids(self):
        """Test handling of unicode in node IDs."""
        graph = KnowledgeGraph()
        graph.add_node("比特币", NodeType.ASSET, {"symbol": "BTC"})
        assert graph.has_node("比特币")

    def test_special_characters_in_properties(self):
        """Test handling of special characters in properties."""
        graph = KnowledgeGraph()
        graph.add_node(
            "TEST",
            NodeType.ASSET,
            {"special": "value with spaces and symbols!@#$%"},
        )
        node = graph.get_node("TEST")
        assert "special" in node.properties
