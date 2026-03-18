"""Unit tests for experiment lineage tracking.

This module provides comprehensive tests for the lineage tracking system,
including models, tracker, and storage components.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from ml.training.lineage import (
    LineageEdge,
    LineageGraph,
    LineageNode,
    LineageStorage,
    LineageTracker,
    NodeType,
    RelationshipType,
)


class TestNodeType:
    """Tests for NodeType enum."""

    def test_node_type_values(self):
        """Test NodeType enum values."""
        assert NodeType.DATA.value == "data"
        assert NodeType.MODEL.value == "model"
        assert NodeType.EXPERIMENT.value == "experiment"

    def test_node_type_from_string(self):
        """Test creating NodeType from string."""
        assert NodeType("data") == NodeType.DATA
        assert NodeType("model") == NodeType.MODEL
        assert NodeType("experiment") == NodeType.EXPERIMENT


class TestRelationshipType:
    """Tests for RelationshipType enum."""

    def test_relationship_type_values(self):
        """Test RelationshipType enum values."""
        assert RelationshipType.DERIVED_FROM.value == "derived_from"
        assert RelationshipType.TRAINED_ON.value == "trained_on"
        assert RelationshipType.PARENT_OF.value == "parent_of"

    def test_relationship_type_from_string(self):
        """Test creating RelationshipType from string."""
        assert RelationshipType("derived_from") == RelationshipType.DERIVED_FROM
        assert RelationshipType("trained_on") == RelationshipType.TRAINED_ON
        assert RelationshipType("parent_of") == RelationshipType.PARENT_OF


class TestLineageNode:
    """Tests for LineageNode dataclass."""

    def test_valid_node_creation(self):
        """Test creating a valid LineageNode."""
        node = LineageNode(
            node_id="test-node-001",
            node_type=NodeType.DATA,
            metadata={"format": "parquet"},
        )

        assert node.node_id == "test-node-001"
        assert node.node_type == NodeType.DATA
        assert node.metadata == {"format": "parquet"}
        assert node.created_at is not None

    def test_node_default_metadata(self):
        """Test LineageNode with default metadata."""
        node = LineageNode(
            node_id="test-node-002",
            node_type=NodeType.EXPERIMENT,
        )

        assert node.metadata == {}

    def test_empty_node_id_raises_error(self):
        """Test that empty node_id raises ValueError."""
        with pytest.raises(ValueError, match="node_id cannot be empty"):
            LineageNode(
                node_id="",
                node_type=NodeType.MODEL,
            )

    def test_invalid_node_type_raises_error(self):
        """Test that invalid node_type raises ValueError."""
        with pytest.raises(ValueError, match="node_type must be a NodeType enum"):
            LineageNode(
                node_id="test-node",
                node_type="invalid_type",
            )

    def test_node_to_dict(self):
        """Test converting LineageNode to dictionary."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        node = LineageNode(
            node_id="test-node",
            node_type=NodeType.DATA,
            metadata={"key": "value"},
            created_at=timestamp,
        )

        data = node.to_dict()

        assert data["node_id"] == "test-node"
        assert data["node_type"] == "data"
        assert data["metadata"] == {"key": "value"}
        assert data["created_at"] == "2024-01-15T12:00:00+00:00"

    def test_node_from_dict(self):
        """Test creating LineageNode from dictionary."""
        data = {
            "node_id": "test-node",
            "node_type": "experiment",
            "metadata": {"version": "1.0"},
            "created_at": "2024-01-15T12:00:00+00:00",
        }

        node = LineageNode.from_dict(data)

        assert node.node_id == "test-node"
        assert node.node_type == NodeType.EXPERIMENT
        assert node.metadata == {"version": "1.0"}

    def test_node_from_dict_without_timestamp(self):
        """Test creating LineageNode without timestamp."""
        data = {
            "node_id": "test-node",
            "node_type": "model",
        }

        node = LineageNode.from_dict(data)

        assert node.node_id == "test-node"
        assert node.node_type == NodeType.MODEL
        assert node.created_at is not None


class TestLineageEdge:
    """Tests for LineageEdge dataclass."""

    def test_valid_edge_creation(self):
        """Test creating a valid LineageEdge."""
        edge = LineageEdge(
            edge_id="edge-001",
            source_id="source-node",
            target_id="target-node",
            relationship_type=RelationshipType.DERIVED_FROM,
        )

        assert edge.edge_id == "edge-001"
        assert edge.source_id == "source-node"
        assert edge.target_id == "target-node"
        assert edge.relationship_type == RelationshipType.DERIVED_FROM

    def test_empty_edge_id_raises_error(self):
        """Test that empty edge_id raises ValueError."""
        with pytest.raises(ValueError, match="edge_id cannot be empty"):
            LineageEdge(
                edge_id="",
                source_id="source",
                target_id="target",
                relationship_type=RelationshipType.TRAINED_ON,
            )

    def test_empty_source_id_raises_error(self):
        """Test that empty source_id raises ValueError."""
        with pytest.raises(ValueError, match="source_id cannot be empty"):
            LineageEdge(
                edge_id="edge-001",
                source_id="",
                target_id="target",
                relationship_type=RelationshipType.TRAINED_ON,
            )

    def test_empty_target_id_raises_error(self):
        """Test that empty target_id raises ValueError."""
        with pytest.raises(ValueError, match="target_id cannot be empty"):
            LineageEdge(
                edge_id="edge-001",
                source_id="source",
                target_id="",
                relationship_type=RelationshipType.TRAINED_ON,
            )

    def test_same_source_target_raises_error(self):
        """Test that same source and target raises ValueError."""
        with pytest.raises(
            ValueError, match="source_id and target_id cannot be the same"
        ):
            LineageEdge(
                edge_id="edge-001",
                source_id="same-node",
                target_id="same-node",
                relationship_type=RelationshipType.PARENT_OF,
            )

    def test_invalid_relationship_type_raises_error(self):
        """Test that invalid relationship_type raises ValueError."""
        with pytest.raises(
            ValueError, match="relationship_type must be a RelationshipType enum"
        ):
            LineageEdge(
                edge_id="edge-001",
                source_id="source",
                target_id="target",
                relationship_type="invalid",
            )

    def test_edge_to_dict(self):
        """Test converting LineageEdge to dictionary."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        edge = LineageEdge(
            edge_id="edge-001",
            source_id="source",
            target_id="target",
            relationship_type=RelationshipType.TRAINED_ON,
            created_at=timestamp,
        )

        data = edge.to_dict()

        assert data["edge_id"] == "edge-001"
        assert data["source_id"] == "source"
        assert data["target_id"] == "target"
        assert data["relationship_type"] == "trained_on"

    def test_edge_from_dict(self):
        """Test creating LineageEdge from dictionary."""
        data = {
            "edge_id": "edge-001",
            "source_id": "source",
            "target_id": "target",
            "relationship_type": "parent_of",
            "metadata": {},
        }

        edge = LineageEdge.from_dict(data)

        assert edge.edge_id == "edge-001"
        assert edge.relationship_type == RelationshipType.PARENT_OF


class TestLineageGraph:
    """Tests for LineageGraph class."""

    def test_empty_graph_creation(self):
        """Test creating an empty LineageGraph."""
        graph = LineageGraph()

        assert graph.nodes == {}
        assert graph.edges == []

    def test_add_node(self):
        """Test adding a node to the graph."""
        graph = LineageGraph()
        node = LineageNode(node_id="node-001", node_type=NodeType.DATA)

        result = graph.add_node(node)

        assert result == node
        assert "node-001" in graph.nodes
        assert graph.nodes["node-001"] == node

    def test_add_duplicate_node_raises_error(self):
        """Test that adding duplicate node raises ValueError."""
        graph = LineageGraph()
        node = LineageNode(node_id="node-001", node_type=NodeType.DATA)

        graph.add_node(node)

        with pytest.raises(ValueError, match="Node with ID 'node-001' already exists"):
            graph.add_node(node)

    def test_add_edge(self):
        """Test adding an edge to the graph."""
        graph = LineageGraph()
        source = LineageNode(node_id="source", node_type=NodeType.EXPERIMENT)
        target = LineageNode(node_id="target", node_type=NodeType.DATA)
        edge = LineageEdge(
            edge_id="edge-001",
            source_id="source",
            target_id="target",
            relationship_type=RelationshipType.TRAINED_ON,
        )

        graph.add_node(source)
        graph.add_node(target)
        result = graph.add_edge(edge)

        assert result == edge
        assert len(graph.edges) == 1
        assert graph.edges[0] == edge

    def test_add_edge_without_nodes_raises_error(self):
        """Test that adding edge without nodes raises ValueError."""
        graph = LineageGraph()
        edge = LineageEdge(
            edge_id="edge-001",
            source_id="missing-source",
            target_id="missing-target",
            relationship_type=RelationshipType.TRAINED_ON,
        )

        with pytest.raises(
            ValueError, match="Source node 'missing-source' does not exist"
        ):
            graph.add_edge(edge)

    def test_get_node(self):
        """Test getting a node by ID."""
        graph = LineageGraph()
        node = LineageNode(node_id="node-001", node_type=NodeType.DATA)

        graph.add_node(node)

        assert graph.get_node("node-001") == node
        assert graph.get_node("nonexistent") is None

    def test_get_parents(self):
        """Test getting parent edges."""
        graph = LineageGraph()
        data = LineageNode(node_id="data", node_type=NodeType.DATA)
        exp = LineageNode(node_id="exp", node_type=NodeType.EXPERIMENT)
        edge = LineageEdge(
            edge_id="edge-001",
            source_id="exp",
            target_id="data",
            relationship_type=RelationshipType.TRAINED_ON,
        )

        graph.add_node(data)
        graph.add_node(exp)
        graph.add_edge(edge)

        parents = graph.get_parents("exp")

        assert len(parents) == 1
        assert parents[0] == edge

    def test_get_children(self):
        """Test getting child edges.

        Children are nodes that point TO this node (incoming edges).
        For edge exp->data, data has exp as a child.
        """
        graph = LineageGraph()
        data = LineageNode(node_id="data", node_type=NodeType.DATA)
        exp = LineageNode(node_id="exp", node_type=NodeType.EXPERIMENT)
        edge = LineageEdge(
            edge_id="edge-001",
            source_id="exp",
            target_id="data",
            relationship_type=RelationshipType.TRAINED_ON,
        )

        graph.add_node(data)
        graph.add_node(exp)
        graph.add_edge(edge)

        # data is the target, so exp is its child
        children = graph.get_children("data")

        assert len(children) == 1
        assert children[0] == edge

    def test_get_ancestors(self):
        """Test getting ancestors of a node."""
        graph = LineageGraph()

        # Create a chain: data -> exp -> model
        data = LineageNode(node_id="data", node_type=NodeType.DATA)
        exp = LineageNode(node_id="exp", node_type=NodeType.EXPERIMENT)
        model = LineageNode(node_id="model", node_type=NodeType.MODEL)

        edge1 = LineageEdge(
            edge_id="e1",
            source_id="exp",
            target_id="data",
            relationship_type=RelationshipType.TRAINED_ON,
        )
        edge2 = LineageEdge(
            edge_id="e2",
            source_id="model",
            target_id="exp",
            relationship_type=RelationshipType.DERIVED_FROM,
        )

        for node in [data, exp, model]:
            graph.add_node(node)
        for edge in [edge1, edge2]:
            graph.add_edge(edge)

        ancestors = graph.get_ancestors("model")

        assert "data" in ancestors.nodes
        assert "exp" in ancestors.nodes
        assert "model" not in ancestors.nodes  # Starting node not included
        assert len(ancestors.edges) == 2

    def test_get_descendants(self):
        """Test getting descendants of a node."""
        graph = LineageGraph()

        # Create a chain: data -> exp -> model
        data = LineageNode(node_id="data", node_type=NodeType.DATA)
        exp = LineageNode(node_id="exp", node_type=NodeType.EXPERIMENT)
        model = LineageNode(node_id="model", node_type=NodeType.MODEL)

        edge1 = LineageEdge(
            edge_id="e1",
            source_id="exp",
            target_id="data",
            relationship_type=RelationshipType.TRAINED_ON,
        )
        edge2 = LineageEdge(
            edge_id="e2",
            source_id="model",
            target_id="exp",
            relationship_type=RelationshipType.DERIVED_FROM,
        )

        for node in [data, exp, model]:
            graph.add_node(node)
        for edge in [edge1, edge2]:
            graph.add_edge(edge)

        descendants = graph.get_descendants("data")

        assert "exp" in descendants.nodes
        assert "model" in descendants.nodes
        assert "data" not in descendants.nodes  # Starting node not included

    def test_find_path(self):
        """Test finding path between nodes."""
        graph = LineageGraph()

        data = LineageNode(node_id="data", node_type=NodeType.DATA)
        exp = LineageNode(node_id="exp", node_type=NodeType.EXPERIMENT)
        model = LineageNode(node_id="model", node_type=NodeType.MODEL)

        edge1 = LineageEdge(
            edge_id="e1",
            source_id="exp",
            target_id="data",
            relationship_type=RelationshipType.TRAINED_ON,
        )
        edge2 = LineageEdge(
            edge_id="e2",
            source_id="model",
            target_id="exp",
            relationship_type=RelationshipType.DERIVED_FROM,
        )

        for node in [data, exp, model]:
            graph.add_node(node)
        for edge in [edge1, edge2]:
            graph.add_edge(edge)

        path = graph.find_path("model", "data")

        assert path is not None
        assert len(path) == 2

    def test_find_no_path(self):
        """Test finding path when no path exists."""
        graph = LineageGraph()

        node1 = LineageNode(node_id="node1", node_type=NodeType.DATA)
        node2 = LineageNode(node_id="node2", node_type=NodeType.DATA)

        graph.add_node(node1)
        graph.add_node(node2)

        path = graph.find_path("node1", "node2")

        assert path is None

    def test_graph_to_dict(self):
        """Test converting LineageGraph to dictionary."""
        graph = LineageGraph()
        node = LineageNode(node_id="node", node_type=NodeType.DATA)

        graph.add_node(node)

        data = graph.to_dict()

        assert "nodes" in data
        assert "edges" in data
        assert "node" in data["nodes"]

    def test_graph_from_dict(self):
        """Test creating LineageGraph from dictionary."""
        data = {
            "nodes": {
                "node1": {
                    "node_id": "node1",
                    "node_type": "data",
                    "metadata": {},
                    "created_at": "2024-01-15T12:00:00+00:00",
                }
            },
            "edges": [],
        }

        graph = LineageGraph.from_dict(data)

        assert "node1" in graph.nodes
        assert graph.nodes["node1"].node_type == NodeType.DATA

    def test_graph_merge(self):
        """Test merging two graphs."""
        graph1 = LineageGraph()
        graph2 = LineageGraph()

        node1 = LineageNode(node_id="node1", node_type=NodeType.DATA)
        node2 = LineageNode(node_id="node2", node_type=NodeType.EXPERIMENT)

        graph1.add_node(node1)
        graph2.add_node(node2)

        merged = graph1.merge(graph2)

        assert "node1" in merged.nodes
        assert "node2" in merged.nodes


class TestLineageTracker:
    """Tests for LineageTracker class."""

    def test_tracker_creation(self):
        """Test creating a LineageTracker."""
        tracker = LineageTracker()

        assert tracker.graph is not None

    def test_record_data_source(self):
        """Test recording a data source."""
        tracker = LineageTracker()

        node = tracker.record_data_source(
            data_id="dataset_v1",
            metadata={"format": "parquet"},
        )

        assert node.node_id == "dataset_v1"
        assert node.node_type == NodeType.DATA
        assert "dataset_v1" in tracker.graph.nodes

    def test_record_experiment(self):
        """Test recording an experiment."""
        tracker = LineageTracker()

        tracker.record_data_source("dataset_v1")
        node = tracker.record_experiment(
            experiment_id="exp_001",
            data_id="dataset_v1",
            metadata={"model_type": "xgboost"},
        )

        assert node.node_id == "exp_001"
        assert node.node_type == NodeType.EXPERIMENT
        assert len(tracker.graph.edges) == 1

    def test_record_experiment_with_parent(self):
        """Test recording an experiment with a parent."""
        tracker = LineageTracker()

        tracker.record_experiment(experiment_id="parent_exp")
        node = tracker.record_experiment(
            experiment_id="child_exp",
            parent_experiment_id="parent_exp",
        )

        assert node.node_id == "child_exp"

        # Check parent relationship
        parent_edges = [
            e
            for e in tracker.graph.edges
            if e.relationship_type == RelationshipType.PARENT_OF
        ]
        assert len(parent_edges) == 1
        assert parent_edges[0].source_id == "parent_exp"
        assert parent_edges[0].target_id == "child_exp"

    def test_record_model(self):
        """Test recording a model."""
        tracker = LineageTracker()

        tracker.record_experiment(experiment_id="exp_001")
        node = tracker.record_model(
            model_id="model_v1",
            experiment_id="exp_001",
            metadata={"accuracy": 0.85},
        )

        assert node.node_id == "model_v1"
        assert node.node_type == NodeType.MODEL
        assert len(tracker.graph.edges) == 1

    def test_get_lineage(self):
        """Test getting lineage for a node."""
        tracker = LineageTracker()

        tracker.record_data_source("dataset_v1")
        tracker.record_experiment(experiment_id="exp_001", data_id="dataset_v1")
        tracker.record_model(model_id="model_v1", experiment_id="exp_001")

        lineage = tracker.get_lineage("model_v1")

        assert "dataset_v1" in lineage.nodes
        assert "exp_001" in lineage.nodes
        assert "model_v1" in lineage.nodes

    def test_get_descendants(self):
        """Test getting descendants for a node."""
        tracker = LineageTracker()

        tracker.record_data_source("dataset_v1")
        tracker.record_experiment(experiment_id="exp_001", data_id="dataset_v1")
        tracker.record_model(model_id="model_v1", experiment_id="exp_001")

        descendants = tracker.get_descendants("dataset_v1")

        assert "exp_001" in descendants.nodes
        assert "model_v1" in descendants.nodes
        assert "dataset_v1" in descendants.nodes  # Starting node included

    def test_get_data_to_model_path(self):
        """Test getting path from data to model."""
        tracker = LineageTracker()

        tracker.record_data_source("dataset_v1")
        tracker.record_experiment(experiment_id="exp_001", data_id="dataset_v1")
        tracker.record_model(model_id="model_v1", experiment_id="exp_001")

        path = tracker.get_data_to_model_path("dataset_v1", "model_v1")

        assert path is not None
        assert len(path) == 2

    def test_get_data_to_model_path_not_found(self):
        """Test getting path when data or model not found."""
        tracker = LineageTracker()

        path = tracker.get_data_to_model_path("missing_data", "missing_model")

        assert path is None

    def test_get_experiments_for_data(self):
        """Test getting experiments that used a data source."""
        tracker = LineageTracker()

        tracker.record_data_source("dataset_v1")
        tracker.record_experiment(experiment_id="exp_001", data_id="dataset_v1")
        tracker.record_experiment(experiment_id="exp_002", data_id="dataset_v1")

        experiments = tracker.get_experiments_for_data("dataset_v1")

        assert len(experiments) == 2
        assert all(e.node_type == NodeType.EXPERIMENT for e in experiments)

    def test_get_models_for_experiment(self):
        """Test getting models derived from an experiment."""
        tracker = LineageTracker()

        tracker.record_experiment(experiment_id="exp_001")
        tracker.record_model(model_id="model_v1", experiment_id="exp_001")
        tracker.record_model(model_id="model_v2", experiment_id="exp_001")

        models = tracker.get_models_for_experiment("exp_001")

        assert len(models) == 2
        assert all(m.node_type == NodeType.MODEL for m in models)

    def test_get_experiment_chain(self):
        """Test getting experiment chain."""
        tracker = LineageTracker()

        tracker.record_experiment(experiment_id="exp_001")
        tracker.record_experiment(
            experiment_id="exp_002",
            parent_experiment_id="exp_001",
        )
        tracker.record_experiment(
            experiment_id="exp_003",
            parent_experiment_id="exp_002",
        )

        chain = tracker.get_experiment_chain("exp_003")

        assert len(chain) == 3
        assert chain[0].node_id == "exp_001"
        assert chain[2].node_id == "exp_003"

    def test_duplicate_node_creation(self):
        """Test handling of duplicate node creation."""
        tracker = LineageTracker()

        node1 = tracker.record_data_source("dataset_v1", metadata={"version": "1"})
        node2 = tracker.record_data_source("dataset_v1", metadata={"version": "2"})

        # Should return existing node
        assert node1.node_id == node2.node_id


class TestLineageStorage:
    """Tests for LineageStorage class."""

    def test_storage_creation(self):
        """Test creating LineageStorage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)

            assert storage.base_path == Path(tmpdir)
            assert storage.base_path.exists()

    def test_save_and_load_lineage(self):
        """Test saving and loading lineage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)
            graph = LineageGraph()
            node = LineageNode(node_id="node", node_type=NodeType.DATA)
            graph.add_node(node)

            saved_path = storage.save_lineage(graph, "test_experiment")
            loaded = storage.load_lineage("test_experiment")

            assert saved_path.exists()
            assert loaded is not None
            assert "node" in loaded.nodes

    def test_load_nonexistent_lineage(self):
        """Test loading non-existent lineage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)

            loaded = storage.load_lineage("nonexistent")

            assert loaded is None

    def test_load_all_lineages(self):
        """Test loading all lineages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)

            graph1 = LineageGraph()
            graph1.add_node(LineageNode(node_id="node1", node_type=NodeType.DATA))

            graph2 = LineageGraph()
            graph2.add_node(LineageNode(node_id="node2", node_type=NodeType.EXPERIMENT))

            storage.save_lineage(graph1, "exp1")
            storage.save_lineage(graph2, "exp2")

            merged = storage.load_all_lineages()

            assert "node1" in merged.nodes
            assert "node2" in merged.nodes

    def test_query_by_data_source(self):
        """Test querying by data source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)
            tracker = LineageTracker()

            tracker.record_data_source("dataset_v1")
            tracker.record_experiment(experiment_id="exp_001", data_id="dataset_v1")
            tracker.record_model(model_id="model_v1", experiment_id="exp_001")

            storage.save_lineage(tracker.get_graph(), "exp_001")

            result = storage.query_by_data_source("dataset_v1")

            assert "dataset_v1" in result.nodes
            assert "exp_001" in result.nodes
            assert "model_v1" in result.nodes

    def test_query_by_model(self):
        """Test querying by model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)
            tracker = LineageTracker()

            tracker.record_data_source("dataset_v1")
            tracker.record_experiment(experiment_id="exp_001", data_id="dataset_v1")
            tracker.record_model(model_id="model_v1", experiment_id="exp_001")

            storage.save_lineage(tracker.get_graph(), "exp_001")

            result = storage.query_by_model("model_v1")

            assert "dataset_v1" in result.nodes
            assert "exp_001" in result.nodes

    def test_query_by_experiment(self):
        """Test querying by experiment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)
            tracker = LineageTracker()

            tracker.record_data_source("dataset_v1")
            tracker.record_experiment(experiment_id="exp_001", data_id="dataset_v1")
            tracker.record_model(model_id="model_v1", experiment_id="exp_001")

            storage.save_lineage(tracker.get_graph(), "exp_001")

            result = storage.query_by_experiment("exp_001")

            assert "exp_001" in result.nodes
            assert "model_v1" in result.nodes

    def test_delete_lineage(self):
        """Test deleting lineage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)
            graph = LineageGraph()
            graph.add_node(LineageNode(node_id="node", node_type=NodeType.DATA))

            storage.save_lineage(graph, "to_delete")

            assert storage.exists("to_delete")

            deleted = storage.delete_lineage("to_delete")

            assert deleted is True
            assert not storage.exists("to_delete")

    def test_delete_nonexistent_lineage(self):
        """Test deleting non-existent lineage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)

            deleted = storage.delete_lineage("nonexistent")

            assert deleted is False

    def test_list_experiments(self):
        """Test listing experiments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)
            graph = LineageGraph()
            graph.add_node(LineageNode(node_id="node", node_type=NodeType.DATA))

            storage.save_lineage(graph, "exp1")
            storage.save_lineage(graph, "exp2")

            experiments = storage.list_experiments()

            assert "exp1" in experiments
            assert "exp2" in experiments

    def test_exists(self):
        """Test checking if lineage exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LineageStorage(tmpdir)
            graph = LineageGraph()
            graph.add_node(LineageNode(node_id="node", node_type=NodeType.DATA))

            storage.save_lineage(graph, "existing")

            assert storage.exists("existing") is True
            assert storage.exists("nonexistent") is False
