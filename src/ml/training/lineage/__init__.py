"""Lineage tracking module for experiment tracking.

This module provides lineage tracking capabilities for ML experiments,
including data sources, experiments, and models in a graph structure.

Components:
- models: Data models for lineage nodes, edges, and graphs
- tracker: LineageTracker class for recording and querying lineage
- storage: LineageStorage class for persistence

Usage:
    from ml.training.lineage import (
        LineageNode,
        LineageEdge,
        LineageGraph,
        NodeType,
        RelationshipType,
        LineageTracker,
        LineageStorage,
    )

    # Create and use a lineage tracker
    tracker = LineageTracker()

    # Record data source
    data_node = tracker.record_data_source(
        data_id="dataset_v1",
        metadata={"format": "parquet", "size": 10000}
    )

    # Record experiment
    exp_node = tracker.record_experiment(
        experiment_id="exp_001",
        data_id="dataset_v1",
        metadata={"model_type": "xgboost"}
    )

    # Record model
    model_node = tracker.record_model(
        model_id="model_v1",
        experiment_id="exp_001",
        metadata={"accuracy": 0.85}
    )

    # Query lineage
    lineage = tracker.get_lineage("model_v1")
    print(f"Model v1 has {len(lineage.nodes)} nodes in its lineage")

    # Save to storage
    storage = LineageStorage("/path/to/lineage")
    storage.save_lineage(tracker.get_graph(), "exp_001")

    # Load from storage
    loaded = storage.load_lineage("exp_001")

    # Query by data source
    data_lineage = storage.query_by_data_source("dataset_v1")

    # Query by model
    model_lineage = storage.query_by_model("model_v1")
"""

from __future__ import annotations

# Model components
from ml.training.lineage.models import (
    LineageEdge,
    LineageGraph,
    LineageNode,
    NodeType,
    RelationshipType,
)

# Storage component
from ml.training.lineage.storage import LineageStorage

# Tracker component
from ml.training.lineage.tracker import LineageTracker

__all__ = [
    # Models
    "LineageNode",
    "LineageEdge",
    "LineageGraph",
    "NodeType",
    "RelationshipType",
    # Tracker
    "LineageTracker",
    # Storage
    "LineageStorage",
]
