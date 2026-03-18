"""Lineage tracker for experiment tracking.

This module provides the LineageTracker class for recording and querying
experiment lineage, including data sources, experiments, and models.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ml.training.lineage.models import (
    LineageEdge,
    LineageGraph,
    LineageNode,
    NodeType,
    RelationshipType,
)

logger = logging.getLogger(__name__)


class LineageTracker:
    """Tracks experiment lineage with data sources, experiments, and models.

    This class provides methods to record lineage information and query
    relationships between data, experiments, and models.
    """

    def __init__(self, graph: LineageGraph | None = None):
        """Initialize the lineage tracker.

        Args:
            graph: Optional existing lineage graph to use
        """
        self.graph = graph if graph is not None else LineageGraph()

    def record_data_source(
        self, data_id: str, metadata: dict[str, Any] | None = None
    ) -> LineageNode:
        """Record a data source in the lineage graph.

        Args:
            data_id: Unique identifier for the data source
            metadata: Additional metadata about the data source

        Returns:
            The created LineageNode
        """
        node = LineageNode(
            node_id=data_id,
            node_type=NodeType.DATA,
            metadata=metadata or {},
        )

        try:
            self.graph.add_node(node)
            logger.debug(f"Recorded data source: {data_id}")
        except ValueError as e:
            logger.warning(f"Data source {data_id} already exists: {e}")
            existing = self.graph.get_node(data_id)
            if existing:
                return existing

        return node

    def record_experiment(
        self,
        experiment_id: str,
        parent_experiment_id: str | None = None,
        data_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LineageNode:
        """Record an experiment in the lineage graph.

        Args:
            experiment_id: Unique identifier for the experiment
            parent_experiment_id: Optional ID of parent experiment
            data_id: Optional ID of data source used
            metadata: Additional metadata about the experiment

        Returns:
            The created LineageNode
        """
        node = LineageNode(
            node_id=experiment_id,
            node_type=NodeType.EXPERIMENT,
            metadata=metadata or {},
        )

        try:
            self.graph.add_node(node)
            logger.debug(f"Recorded experiment: {experiment_id}")
        except ValueError:
            logger.warning(f"Experiment {experiment_id} already exists")
            existing = self.graph.get_node(experiment_id)
            if existing:
                return existing

        # Record relationship to data source if provided
        if data_id:
            if data_id not in self.graph.nodes:
                logger.warning(f"Data source {data_id} not found, creating placeholder")
                self.record_data_source(data_id)

            edge = LineageEdge(
                edge_id=f"{experiment_id}_trained_on_{data_id}",
                source_id=experiment_id,
                target_id=data_id,
                relationship_type=RelationshipType.TRAINED_ON,
                metadata={"created_at": datetime.now(UTC).isoformat()},
            )
            try:
                self.graph.add_edge(edge)
                logger.debug(
                    f"Recorded training relationship: {experiment_id} -> {data_id}"
                )
            except ValueError as e:
                logger.warning(f"Failed to add training edge: {e}")

        # Record parent relationship if provided
        if parent_experiment_id:
            if parent_experiment_id not in self.graph.nodes:
                logger.warning(f"Parent experiment {parent_experiment_id} not found")
            else:
                parent_edge = LineageEdge(
                    edge_id=f"{parent_experiment_id}_parent_of_{experiment_id}",
                    source_id=parent_experiment_id,
                    target_id=experiment_id,
                    relationship_type=RelationshipType.PARENT_OF,
                    metadata={"created_at": datetime.now(UTC).isoformat()},
                )
                try:
                    self.graph.add_edge(parent_edge)
                    logger.debug(
                        f"Recorded parent relationship: {parent_experiment_id} -> {experiment_id}"
                    )
                except ValueError as e:
                    logger.warning(f"Failed to add parent edge: {e}")

        return node

    def record_model(
        self,
        model_id: str,
        experiment_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> LineageNode:
        """Record a model in the lineage graph.

        Args:
            model_id: Unique identifier for the model
            experiment_id: ID of the experiment that produced the model
            metadata: Additional metadata about the model

        Returns:
            The created LineageNode
        """
        node = LineageNode(
            node_id=model_id,
            node_type=NodeType.MODEL,
            metadata=metadata or {},
        )

        try:
            self.graph.add_node(node)
            logger.debug(f"Recorded model: {model_id}")
        except ValueError:
            logger.warning(f"Model {model_id} already exists")
            existing = self.graph.get_node(model_id)
            if existing:
                return existing

        # Ensure experiment exists
        if experiment_id not in self.graph.nodes:
            logger.warning(
                f"Experiment {experiment_id} not found, creating placeholder"
            )
            self.record_experiment(experiment_id)

        # Record derived_from relationship
        edge = LineageEdge(
            edge_id=f"{model_id}_derived_from_{experiment_id}",
            source_id=model_id,
            target_id=experiment_id,
            relationship_type=RelationshipType.DERIVED_FROM,
            metadata={"created_at": datetime.now(UTC).isoformat()},
        )
        try:
            self.graph.add_edge(edge)
            logger.debug(
                f"Recorded derivation relationship: {model_id} -> {experiment_id}"
            )
        except ValueError as e:
            logger.warning(f"Failed to add derivation edge: {e}")

        return node

    def get_lineage(self, node_id: str) -> LineageGraph:
        """Get full ancestry (lineage) for a node.

        Returns all parent nodes recursively up to the root data sources.

        Args:
            node_id: The node ID to get lineage for

        Returns:
            LineageGraph containing all ancestors
        """
        if node_id not in self.graph.nodes:
            logger.warning(f"Node {node_id} not found")
            return LineageGraph()

        # Get the node itself
        node = self.graph.nodes[node_id]
        ancestry = self.graph.get_ancestors(node_id)

        # Include the starting node in the result
        result = LineageGraph()
        result.add_node(node)

        # Merge ancestry into result
        for ancestor_node in ancestry.nodes.values():
            if ancestor_node.node_id not in result.nodes:
                result.add_node(ancestor_node)
        for edge in ancestry.edges:
            if edge not in result.edges:
                result.edges.append(edge)

        return result

    def get_descendants(self, node_id: str) -> LineageGraph:
        """Get all descendants for a node.

        Returns all child nodes recursively down to leaf nodes.

        Args:
            node_id: The node ID to get descendants for

        Returns:
            LineageGraph containing all descendants
        """
        if node_id not in self.graph.nodes:
            logger.warning(f"Node {node_id} not found")
            return LineageGraph()

        # Get the node itself
        node = self.graph.nodes[node_id]
        descendants = self.graph.get_descendants(node_id)

        # Include the starting node in the result
        result = LineageGraph()
        result.add_node(node)

        # Merge descendants into result
        for descendant_node in descendants.nodes.values():
            if descendant_node.node_id not in result.nodes:
                result.add_node(descendant_node)
        for edge in descendants.edges:
            if edge not in result.edges:
                result.edges.append(edge)

        return result

    def get_data_to_model_path(
        self, data_id: str, model_id: str
    ) -> list[LineageEdge] | None:
        """Get the path from a data source to a model.

        Finds the lineage path showing how a specific data source
        contributed to a specific model.

        Args:
            data_id: The data source ID
            model_id: The model ID

        Returns:
            List of edges forming the path, or None if no path exists
        """
        if data_id not in self.graph.nodes:
            logger.warning(f"Data source {data_id} not found")
            return None

        if model_id not in self.graph.nodes:
            logger.warning(f"Model {model_id} not found")
            return None

        # Find path from model to data (reverse direction since edges point
        # from child to parent)
        path = self.graph.find_path(model_id, data_id)
        return path

    def get_experiments_for_data(self, data_id: str) -> list[LineageNode]:
        """Get all experiments that used a specific data source.

        Args:
            data_id: The data source ID

        Returns:
            List of experiment nodes that trained on this data
        """
        if data_id not in self.graph.nodes:
            return []

        experiments = []
        for edge in self.graph.edges:
            if (
                edge.target_id == data_id
                and edge.relationship_type == RelationshipType.TRAINED_ON
            ):
                node = self.graph.nodes.get(edge.source_id)
                if node and node.node_type == NodeType.EXPERIMENT:
                    experiments.append(node)

        return experiments

    def get_models_for_experiment(self, experiment_id: str) -> list[LineageNode]:
        """Get all models derived from a specific experiment.

        Args:
            experiment_id: The experiment ID

        Returns:
            List of model nodes derived from this experiment
        """
        if experiment_id not in self.graph.nodes:
            return []

        models = []
        for edge in self.graph.edges:
            if (
                edge.target_id == experiment_id
                and edge.relationship_type == RelationshipType.DERIVED_FROM
            ):
                node = self.graph.nodes.get(edge.source_id)
                if node and node.node_type == NodeType.MODEL:
                    models.append(node)

        return models

    def get_experiment_chain(self, experiment_id: str) -> list[LineageNode]:
        """Get the full experiment chain from root to this experiment.

        Traces parent relationships to build the full experiment lineage chain.

        Args:
            experiment_id: The experiment ID

        Returns:
            List of experiment nodes from root to this experiment
        """
        if experiment_id not in self.graph.nodes:
            return []

        chain = []
        current_id = experiment_id
        visited = set()

        while current_id and current_id not in visited:
            visited.add(current_id)
            node = self.graph.nodes.get(current_id)
            if node:
                chain.append(node)

            # Find parent experiment
            parent_id = None
            for edge in self.graph.edges:
                if (
                    edge.target_id == current_id
                    and edge.relationship_type == RelationshipType.PARENT_OF
                ):
                    parent_id = edge.source_id
                    break

            current_id = parent_id

        # Reverse to get root -> ... -> current
        chain.reverse()
        return chain

    def get_graph(self) -> LineageGraph:
        """Get the current lineage graph.

        Returns:
            The LineageGraph managed by this tracker
        """
        return self.graph

    def set_graph(self, graph: LineageGraph) -> None:
        """Set the lineage graph.

        Args:
            graph: The LineageGraph to use
        """
        self.graph = graph
