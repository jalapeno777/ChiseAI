"""Lineage storage for persistence.

This module provides the LineageStorage class for saving and loading
lineage graphs to/from the filesystem.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ml.training.lineage.models import LineageGraph

logger = logging.getLogger(__name__)


class LineageStorage:
    """Storage handler for lineage graphs.

    Provides methods to save and load lineage graphs to/from the filesystem,
    with support for querying by data source and model.
    """

    def __init__(self, base_path: str | Path | None = None):
        """Initialize the storage handler.

        Args:
            base_path: Base directory for storing lineage files.
                      Defaults to 'lineage' in current directory.
        """
        self.base_path = Path(base_path) if base_path else Path("lineage")
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure the base directory exists."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured lineage directory: {self.base_path}")

    def _get_experiment_path(self, experiment_id: str) -> Path:
        """Get the file path for an experiment's lineage.

        Args:
            experiment_id: The experiment ID

        Returns:
            Path to the lineage file
        """
        return self.base_path / f"{experiment_id}.json"

    def save_lineage(
        self, graph: LineageGraph, experiment_id: str | None = None
    ) -> Path:
        """Save a lineage graph to storage.

        Args:
            graph: The lineage graph to save
            experiment_id: Optional experiment ID to use as filename.
                          If not provided, uses a timestamp.

        Returns:
            Path to the saved file
        """
        from datetime import UTC, datetime

        if experiment_id is None:
            experiment_id = f"lineage_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

        file_path = self._get_experiment_path(experiment_id)

        # Convert graph to dict and save as JSON
        data = graph.to_dict()

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Saved lineage to {file_path}")
        except OSError as e:
            logger.error(f"Failed to save lineage to {file_path}: {e}")
            raise

        return file_path

    def load_lineage(self, experiment_id: str) -> LineageGraph | None:
        """Load a lineage graph from storage.

        Args:
            experiment_id: The experiment ID

        Returns:
            The loaded LineageGraph, or None if not found
        """
        file_path = self._get_experiment_path(experiment_id)

        if not file_path.exists():
            logger.warning(f"Lineage file not found: {file_path}")
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            graph = LineageGraph.from_dict(data)
            logger.info(f"Loaded lineage from {file_path}")
            return graph

        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load lineage from {file_path}: {e}")
            return None

    def load_all_lineages(self) -> LineageGraph:
        """Load and merge all lineage graphs from storage.

        Returns:
            A merged LineageGraph containing all stored lineages
        """
        merged = LineageGraph()

        if not self.base_path.exists():
            logger.warning(f"Lineage directory does not exist: {self.base_path}")
            return merged

        json_files = list(self.base_path.glob("*.json"))
        logger.info(f"Found {len(json_files)} lineage files")

        for file_path in json_files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)

                graph = LineageGraph.from_dict(data)
                merged = merged.merge(graph)
                logger.debug(f"Merged lineage from {file_path}")

            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load {file_path}: {e}")
                continue

        logger.info(
            f"Loaded {len(merged.nodes)} nodes and {len(merged.edges)} edges total"
        )
        return merged

    def query_by_data_source(self, data_id: str) -> LineageGraph:
        """Query lineage graphs by data source.

        Returns all lineage graphs that contain the specified data source.

        Args:
            data_id: The data source ID

        Returns:
            LineageGraph containing matching nodes and their lineages
        """
        all_lineage = self.load_all_lineages()

        if data_id not in all_lineage.nodes:
            logger.info(f"Data source {data_id} not found in any lineage")
            return LineageGraph()

        # Get the data node
        data_node = all_lineage.nodes[data_id]

        # Get all descendants (experiments and models that used this data)
        result = all_lineage.get_descendants(data_id)

        # Include the data node itself
        result.add_node(data_node)

        return result

    def query_by_model(self, model_id: str) -> LineageGraph:
        """Query lineage graphs by model.

        Returns the full lineage for the specified model.

        Args:
            model_id: The model ID

        Returns:
            LineageGraph containing the model's full ancestry
        """
        all_lineage = self.load_all_lineages()

        if model_id not in all_lineage.nodes:
            logger.info(f"Model {model_id} not found in any lineage")
            return LineageGraph()

        # Get full ancestry for the model
        result = all_lineage.get_ancestors(model_id)

        # Include the model node itself
        model_node = all_lineage.nodes[model_id]
        if model_id not in result.nodes:
            result.add_node(model_node)

        return result

    def query_by_experiment(self, experiment_id: str) -> LineageGraph:
        """Query lineage graphs by experiment.

        Returns the full lineage for the specified experiment.

        Args:
            experiment_id: The experiment ID

        Returns:
            LineageGraph containing the experiment's lineage
        """
        all_lineage = self.load_all_lineages()

        if experiment_id not in all_lineage.nodes:
            logger.info(f"Experiment {experiment_id} not found in any lineage")
            return LineageGraph()

        # Get full ancestry for the experiment
        result = all_lineage.get_ancestors(experiment_id)

        # Include the experiment node itself
        exp_node = all_lineage.nodes[experiment_id]
        if experiment_id not in result.nodes:
            result.add_node(exp_node)

        # Also include models derived from this experiment
        for edge in all_lineage.edges:
            if edge.target_id == experiment_id and edge.source_id in all_lineage.nodes:
                model_node = all_lineage.nodes[edge.source_id]
                if model_node.node_id not in result.nodes:
                    result.add_node(model_node)
                    result.add_edge(edge)

        return result

    def delete_lineage(self, experiment_id: str) -> bool:
        """Delete a lineage file from storage.

        Args:
            experiment_id: The experiment ID

        Returns:
            True if deleted successfully, False otherwise
        """
        file_path = self._get_experiment_path(experiment_id)

        if not file_path.exists():
            logger.warning(f"Lineage file not found for deletion: {file_path}")
            return False

        try:
            file_path.unlink()
            logger.info(f"Deleted lineage file: {file_path}")
            return True
        except OSError as e:
            logger.error(f"Failed to delete lineage file {file_path}: {e}")
            return False

    def list_experiments(self) -> list[str]:
        """List all experiment IDs with stored lineage.

        Returns:
            List of experiment IDs
        """
        if not self.base_path.exists():
            return []

        experiment_ids = []
        for file_path in self.base_path.glob("*.json"):
            experiment_ids.append(file_path.stem)

        return sorted(experiment_ids)

    def exists(self, experiment_id: str) -> bool:
        """Check if lineage exists for an experiment.

        Args:
            experiment_id: The experiment ID

        Returns:
            True if lineage exists, False otherwise
        """
        file_path = self._get_experiment_path(experiment_id)
        return file_path.exists()
