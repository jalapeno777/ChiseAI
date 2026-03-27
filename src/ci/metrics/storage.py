"""File-based Storage for Aggregated Metrics.

Provides persistence for aggregated metrics data to/from JSON files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ci.metrics.models import AggregatedMetricsOutput, MetricPoint

from src.ci.metrics.models import AggregatedMetricsOutput, MetricPoint


class MetricsStorage:
    """File-based storage for CI metrics.

    Handles reading raw metrics and writing aggregated metrics to JSON files.

    Example:
        >>> storage = MetricsStorage()
        >>> metrics = storage.load_metrics("/path/to/metrics.json")
        >>> storage.save_aggregated(output, "/path/to/aggregated.json")
    """

    def __init__(self, base_path: str = "_bmad-output/ci") -> None:
        """Initialize storage with base path.

        Args:
            base_path: Base directory for metrics files
        """
        self.base_path = Path(base_path)

    def _ensure_dir(self, path: Path) -> None:
        """Ensure directory exists.

        Args:
            path: Path to ensure exists
        """
        path.parent.mkdir(parents=True, exist_ok=True)

    def load_metrics(self, filepath: str | Path) -> list[MetricPoint]:
        """Load metrics from a JSON file.

        Args:
            filepath: Path to metrics JSON file

        Returns:
            List of MetricPoints loaded from file

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file contains invalid JSON
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Metrics file not found: {path}")

        try:
            with open(path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in metrics file: {e}") from e

        metrics: list[MetricPoint] = []

        # Handle both single metric dict and list of metrics
        if isinstance(data, dict):
            if "timestamp" in data:
                # Single metric object
                metrics.append(MetricPoint.from_dict(data))
            elif "results" in data:
                # Wrapped format
                for item in data.get("results", []):
                    if isinstance(item, dict):
                        metrics.append(MetricPoint.from_dict(item))
        elif isinstance(data, list):
            # List of metrics
            for item in data:
                if isinstance(item, dict):
                    metrics.append(MetricPoint.from_dict(item))

        return metrics

    def load_metrics_from_dir(self, dirname: str | Path) -> list[MetricPoint]:
        """Load all metrics from a directory.

        Looks for metrics.json and metrics_*.json files.

        Args:
            dirname: Directory to load from

        Returns:
            Combined list of all metrics found
        """
        dir_path = Path(dirname)
        if not dir_path.exists():
            return []

        all_metrics: list[MetricPoint] = []

        # Look for metrics files
        for pattern in ["metrics.json", "metrics_*.json"]:
            for path in dir_path.glob(pattern):
                try:
                    metrics = self.load_metrics(path)
                    all_metrics.extend(metrics)
                except (FileNotFoundError, ValueError):
                    # Skip invalid files
                    pass

        # Sort by timestamp
        all_metrics.sort(key=lambda m: m.timestamp if m.timestamp else "")

        return all_metrics

    def save_metrics(
        self,
        metrics: list[MetricPoint],
        filepath: str | Path,
    ) -> bool:
        """Save metrics to a JSON file.

        Args:
            metrics: List of MetricPoints to save
            filepath: Path to save to

        Returns:
            True if successful
        """
        try:
            path = Path(filepath)
            self._ensure_dir(path)

            data = [m.to_dict() for m in metrics]
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Failed to save metrics: {e}", file=sys.stderr)
            return False

    def save_aggregated(
        self,
        output: AggregatedMetricsOutput,
        filepath: str | Path,
    ) -> bool:
        """Save aggregated metrics output to a JSON file.

        Args:
            output: AggregatedMetricsOutput to save
            filepath: Path to save to

        Returns:
            True if successful
        """
        try:
            path = Path(filepath)
            self._ensure_dir(path)

            with open(path, "w") as f:
                json.dump(output.to_dict(), f, indent=2)

            return True
        except Exception as e:
            print(f"Failed to save aggregated metrics: {e}", file=sys.stderr)
            return False

    def load_aggregated(self, filepath: str | Path) -> AggregatedMetricsOutput | None:
        """Load aggregated metrics output from a JSON file.

        Args:
            filepath: Path to load from

        Returns:
            AggregatedMetricsOutput or None if not found
        """
        path = Path(filepath)
        if not path.exists():
            return None

        try:
            with open(path) as f:
                data = json.load(f)

            output = AggregatedMetricsOutput(
                generated_at=data.get("generated_at", ""),
                source_metrics_count=data.get("source_metrics_count", 0),
            )
            output.aggregation_windows = data.get("aggregation_windows", {})
            output.trends = data.get("trends", [])

            return output
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Failed to load aggregated metrics: {e}", file=sys.stderr)
            return None


def load_metrics_history(
    metrics_dir: str = "_bmad-output/ci",
    max_days: int = 30,
) -> list[MetricPoint]:
    """Load historical metrics from the metrics directory.

    This function loads all available historical metrics and filters
    to the specified time range.

    Args:
        metrics_dir: Directory containing metrics files
        max_days: Maximum age of metrics to include (default 30 days)

    Returns:
        List of historical metric points
    """
    from datetime import UTC, datetime, timedelta

    storage = MetricsStorage(metrics_dir)
    all_metrics = storage.load_metrics_from_dir(metrics_dir)

    if not max_days:
        return all_metrics

    cutoff = datetime.now(UTC) - timedelta(days=max_days)
    filtered = []

    for metric in all_metrics:
        if metric.timestamp:
            try:
                metric_dt = metric.get_datetime()
                if metric_dt >= cutoff:
                    filtered.append(metric)
            except Exception:
                # Include metrics with unparseable timestamps
                filtered.append(metric)

    return filtered
