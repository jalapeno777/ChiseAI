"""Visualization module for calibration ECE curves.

This module provides utilities for generating ECE curve visualizations
suitable for Grafana dashboards and other monitoring tools.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ml.calibration.optimizer import ECECurve

logger = logging.getLogger(__name__)


@dataclass
class CurveVisualization:
    """Visualization-ready ECE curve data.

    Attributes:
        signal_type: Type of signal
        title: Chart title
        x_label: X-axis label
        y_label: Y-axis label
        data_points: List of (threshold, ece) tuples
        optimal_point: (threshold, ece) tuple for optimal threshold
        annotations: List of annotation strings
        metadata: Additional metadata for the visualization
    """

    signal_type: str
    title: str
    x_label: str = "Confidence Threshold"
    y_label: str = "Expected Calibration Error (ECE)"
    data_points: list[tuple[float, float]] = field(default_factory=list)
    optimal_point: tuple[float, float] | None = None
    annotations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_grafana_format(self) -> dict[str, Any]:
        """Convert to Grafana-compatible JSON format.

        Returns:
            Dictionary suitable for Grafana panels
        """
        series = [
            {
                "name": "ECE vs Threshold",
                "data": [{"x": t, "y": ece} for t, ece in self.data_points],
            }
        ]

        if self.optimal_point:
            series.append(
                {
                    "name": "Optimal Threshold",
                    "data": [{"x": self.optimal_point[0], "y": self.optimal_point[1]}],
                    "pointRadius": 8,
                    "color": "#00ff00",
                }
            )

        return {
            "title": self.title,
            "type": "graph",
            "x_axis": {"label": self.x_label},
            "y_axis": {"label": self.y_label, "min": 0, "max": 1},
            "series": series,
            "annotations": self.annotations,
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type,
            "title": self.title,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "data_points": self.data_points,
            "optimal_point": self.optimal_point,
            "annotations": self.annotations,
            "metadata": self.metadata,
        }


class ECECurveVisualizer:
    """Visualizer for ECE curves.

    Generates visualization-ready data for ECE vs threshold curves,
    suitable for Grafana dashboards and other monitoring tools.

    Example:
        >>> from ml.calibration import ThresholdOptimizer
        >>> optimizer = ThresholdOptimizer(collector)
        >>> curve = optimizer.generate_ece_curve('LONG')
        >>> visualizer = ECECurveVisualizer()
        >>> viz = visualizer.create_visualization(curve)
        >>> grafana_json = viz.to_grafana_format()
    """

    def __init__(self):
        """Initialize the visualizer."""
        pass

    def create_visualization(
        self,
        curve: ECECurve,
        include_annotations: bool = True,
    ) -> CurveVisualization:
        """Create visualization from ECE curve.

        Args:
            curve: ECECurve with threshold and ECE data
            include_annotations: Whether to include annotations

        Returns:
            CurveVisualization ready for display
        """
        # Create data points
        data_points = list(zip(curve.thresholds, curve.ece_values))

        # Get optimal point
        optimal_point = None
        if 0 <= curve.optimal_idx < len(curve.thresholds):
            optimal_point = (
                curve.thresholds[curve.optimal_idx],
                curve.ece_values[curve.optimal_idx],
            )

        # Generate annotations
        annotations = []
        if include_annotations and optimal_point:
            annotations.append(
                f"Optimal threshold: {optimal_point[0]:.2f} (ECE: {optimal_point[1]:.4f})"
            )
            if curve.sample_sizes:
                optimal_samples = curve.sample_sizes[curve.optimal_idx]
                annotations.append(f"Sample size at optimal: {optimal_samples}")

        # Build metadata
        metadata = {
            "signal_type": curve.signal_type,
            "min_ece": (
                curve.min_ece if hasattr(curve, "min_ece") else min(curve.ece_values)
            ),
            "max_ece": max(curve.ece_values),
            "threshold_count": len(curve.thresholds),
        }

        return CurveVisualization(
            signal_type=curve.signal_type,
            title=f"ECE Curve - {curve.signal_type}",
            data_points=data_points,
            optimal_point=optimal_point,
            annotations=annotations,
            metadata=metadata,
        )

    def create_all_visualizations(
        self,
        curves: dict[str, ECECurve],
        include_annotations: bool = True,
    ) -> dict[str, CurveVisualization]:
        """Create visualizations for multiple ECE curves.

        Args:
            curves: Dict mapping signal type to ECECurve
            include_annotations: Whether to include annotations

        Returns:
            Dict mapping signal type to CurveVisualization
        """
        return {
            signal_type: self.create_visualization(curve, include_annotations)
            for signal_type, curve in curves.items()
        }

    def export_to_json(
        self,
        curves: dict[str, ECECurve],
        filepath: str,
        format: str = "grafana",
    ) -> bool:
        """Export curves to JSON file.

        Args:
            curves: Dict mapping signal type to ECECurve
            filepath: Path to output JSON file
            format: Export format ("grafana" or "raw")

        Returns:
            True if export successful
        """
        try:
            if format == "grafana":
                visualizations = self.create_all_visualizations(curves)
                data = {
                    "dashboard": {
                        "title": "ECE Threshold Optimization",
                        "panels": [
                            viz.to_grafana_format() for viz in visualizations.values()
                        ],
                    }
                }
            else:  # raw format
                data = {
                    "curves": {
                        signal_type: curve.to_dict()
                        for signal_type, curve in curves.items()
                    }
                }

            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Exported ECE curves to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export curves: {e}")
            return False

    def generate_metrics(
        self,
        curves: dict[str, ECECurve],
    ) -> dict[str, dict[str, float]]:
        """Generate metrics from ECE curves for monitoring.

        Args:
            curves: Dict mapping signal type to ECECurve

        Returns:
            Dict of metrics suitable for InfluxDB/prometheus
        """
        metrics = {}

        for signal_type, curve in curves.items():
            metrics[signal_type] = {
                "optimal_threshold": curve.optimal_threshold,
                "min_ece": curve.min_ece,
                "max_ece": max(curve.ece_values),
                "mean_ece": np.mean(curve.ece_values),
                "std_ece": np.std(curve.ece_values),
                "threshold_count": len(curve.thresholds),
            }

            if curve.sample_sizes:
                metrics[signal_type]["optimal_sample_size"] = curve.sample_sizes[
                    curve.optimal_idx
                ]
                metrics[signal_type]["total_samples"] = sum(curve.sample_sizes)

        return metrics

    def export_metrics_to_line_protocol(
        self,
        curves: dict[str, ECECurve],
        measurement: str = "ece_optimization",
    ) -> str:
        """Export metrics as InfluxDB Line Protocol.

        Args:
            curves: Dict mapping signal type to ECECurve
            measurement: Measurement name

        Returns:
            Line protocol formatted string
        """
        lines = []
        timestamp = int(np.datetime64("now").astype("datetime64[ns]").astype(int))

        for signal_type, curve in curves.items():
            # Main metrics line
            fields = [
                f"optimal_threshold={curve.optimal_threshold:.4f}",
                f"min_ece={curve.min_ece:.6f}",
                f"max_ece={max(curve.ece_values):.6f}",
                f"mean_ece={np.mean(curve.ece_values):.6f}",
            ]

            if curve.sample_sizes:
                fields.append(
                    f"optimal_sample_size={curve.sample_sizes[curve.optimal_idx]}i"
                )
                fields.append(f"total_samples={sum(curve.sample_sizes)}i")

            line = f"{measurement},signal_type={signal_type} {','.join(fields)} {timestamp}"
            lines.append(line)

        return "\n".join(lines)


def create_grafana_panel_json(
    signal_types: list[str],
    title: str = "ECE Threshold Optimization",
) -> dict[str, Any]:
    """Create Grafana dashboard panel JSON for ECE curves.

    Args:
        signal_types: List of signal types to display
        title: Panel title

    Returns:
        Grafana panel JSON configuration
    """
    targets = []
    for signal_type in signal_types:
        targets.append(
            {
                "expr": f'ece_optimization{{signal_type="{signal_type}"}}',
                "legendFormat": f"{{{{signal_type}}}} - Optimal Threshold",
                "refId": f"{signal_type}_threshold",
            }
        )
        targets.append(
            {
                "expr": f'ece_optimization{{signal_type="{signal_type}"}}',
                "legendFormat": f"{{{{signal_type}}}} - Min ECE",
                "refId": f"{signal_type}_ece",
            }
        )

    return {
        "id": None,
        "title": title,
        "type": "graph",
        "targets": targets,
        "fieldConfig": {
            "defaults": {
                "custom": {"lineWidth": 2, "fillOpacity": 10},
                "unit": "percentunit",
                "min": 0,
                "max": 1,
            },
            "overrides": [],
        },
        "options": {
            "tooltip": {"mode": "multi"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        },
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
    }
