"""XAI Visualization Module.

Provides visualization components for explainability analysis
including feature importance plots, SHAP visualizations, and
explanation summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import logging
import json

logger = logging.getLogger(__name__)


class PlotType(Enum):
    """Types of visualization plots."""

    BAR = "bar"  # Bar chart
    WATERFALL = "waterfall"  # Waterfall chart
    FORCE = "force"  # Force plot
    DECISION = "decision"  # Decision plot
    DEPENDENCE = "dependence"  # Dependence plot
    SUMMARY = "summary"  # Summary plot
    HEATMAP = "heatmap"  # Heatmap
    BEESSWARM = "beesswarm"  # Beeswarm plot


@dataclass
class VisualizationConfig:
    """Configuration for visualizations."""

    plot_type: PlotType = PlotType.BAR
    width: int = 800
    height: int = 600
    title: str = "Feature Importance"
    color_scheme: str = "RdBu"  # Red-Blue diverging
    show_values: bool = True
    sort_by_importance: bool = True
    max_features: int = 15
    interactive: bool = False
    format: str = "json"  # json, html, svg, png


@dataclass
class PlotData:
    """Data for a single plot."""

    plot_type: PlotType
    title: str
    x_data: list[Any] = field(default_factory=list)
    y_data: list[Any] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    annotations: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plot_type": self.plot_type.value,
            "title": self.title,
            "x_data": self.x_data,
            "y_data": self.y_data,
            "colors": self.colors,
            "labels": self.labels,
            "annotations": self.annotations,
            "metadata": self.metadata,
        }

    def to_vega_lite(self) -> dict[str, Any]:
        """Convert to Vega-Lite specification."""
        if self.plot_type == PlotType.BAR:
            return self._to_bar_spec()
        elif self.plot_type == PlotType.WATERFALL:
            return self._to_waterfall_spec()
        else:
            return self._to_generic_spec()

    def _to_bar_spec(self) -> dict[str, Any]:
        """Generate Vega-Lite bar chart spec."""
        data_values = [
            {"feature": label, "value": val, "color": color}
            for label, val, color in zip(self.labels, self.y_data, self.colors)
        ]

        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": self.title,
            "width": 600,
            "height": 400,
            "data": {"values": data_values},
            "mark": "bar",
            "encoding": {
                "x": {"field": "value", "type": "quantitative", "title": "SHAP Value"},
                "y": {"field": "feature", "type": "nominal", "sort": "-x"},
                "color": {
                    "field": "value",
                    "type": "quantitative",
                    "scale": {"scheme": "redblue", "domainMid": 0},
                    "legend": None,
                },
            },
        }

    def _to_waterfall_spec(self) -> dict[str, Any]:
        """Generate Vega-Lite waterfall chart spec."""
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": self.title,
            "width": 600,
            "height": 400,
            "data": {"values": self._waterfall_data()},
            "mark": "bar",
            "encoding": {
                "x": {"field": "feature", "type": "nominal"},
                "y": {"field": "value", "type": "quantitative"},
                "color": {
                    "condition": {
                        "test": "datum.value > 0",
                        "value": "#2ecc71",
                    },
                    "value": "#e74c3c",
                },
            },
        }

    def _waterfall_data(self) -> list[dict[str, Any]]:
        """Generate waterfall data."""
        cumulative = 0
        data = []
        for label, value in zip(self.labels, self.y_data):
            cumulative += value
            data.append(
                {
                    "feature": label,
                    "value": value,
                    "cumulative": cumulative,
                }
            )
        return data

    def _to_generic_spec(self) -> dict[str, Any]:
        """Generate generic plot spec."""
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": self.title,
            "data": {
                "values": [
                    {"x": x, "y": y, "label": label}
                    for x, y, label in zip(self.x_data, self.y_data, self.labels)
                ]
            },
            "mark": "point",
            "encoding": {
                "x": {"field": "x", "type": "quantitative"},
                "y": {"field": "y", "type": "quantitative"},
            },
        }


@dataclass
class VisualizationResult:
    """Complete visualization result with multiple plots."""

    plots: list[PlotData]
    summary: str
    config: VisualizationConfig
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plots": [p.to_dict() for p in self.plots],
            "summary": self.summary,
            "config": {
                "plot_type": self.config.plot_type.value,
                "width": self.config.width,
                "height": self.config.height,
            },
            "metadata": self.metadata,
        }

    def to_html(self) -> str:
        """Generate HTML representation."""
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>',
            '<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>',
            '<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>',
            "<style>",
            ".plot-container { margin: 20px 0; }",
            ".summary { padding: 15px; background: #f5f5f5; border-radius: 5px; }",
            "</style>",
            "</head>",
            "<body>",
            f'<div class="summary"><h2>Summary</h2><p>{self.summary}</p></div>',
        ]

        for i, plot in enumerate(self.plots):
            html_parts.append(f'<div id="plot-{i}" class="plot-container"></div>')
            html_parts.append("<script>")
            html_parts.append(
                f'vegaEmbed("#plot-{i}", {json.dumps(plot.to_vega_lite())});'
            )
            html_parts.append("</script>")

        html_parts.extend(["</body>", "</html>"])

        return "\n".join(html_parts)


class ExplanationVisualizer:
    """Creates visualizations for explanations and feature importance.

    This class generates various visualization types for understanding
    model explanations and feature contributions.

    Example:
        >>> visualizer = ExplanationVisualizer()
        >>> result = visualizer.create_feature_importance_plot(
        ...     feature_importance={'rsi': 0.3, 'macd': -0.2, 'volume': 0.1}
        ... )
        >>> print(result.plots[0].title)
        'Feature Importance'
    """

    # Color palettes
    _DIVERGING_COLORS = {
        "positive": "#2ecc71",
        "negative": "#e74c3c",
        "neutral": "#95a5a6",
    }

    _SEQUENTIAL_COLORS = [
        "#f7fbff",
        "#deebf7",
        "#c6dbef",
        "#9ecae1",
        "#6baed6",
        "#4292c6",
        "#2171b5",
        "#084594",
    ]

    def __init__(self, config: Optional[VisualizationConfig] = None):
        """Initialize the visualizer.

        Args:
            config: Default configuration for visualizations.
        """
        self.config = config or VisualizationConfig()
        logger.info(
            "ExplanationVisualizer initialized with plot_type=%s",
            self.config.plot_type.value,
        )

    def create_feature_importance_plot(
        self,
        feature_importance: dict[str, float],
        title: str = "Feature Importance",
        config: Optional[VisualizationConfig] = None,
    ) -> VisualizationResult:
        """Create a feature importance visualization.

        Args:
            feature_importance: Dictionary of feature names to importance values.
            title: Title for the plot.
            config: Optional configuration override.

        Returns:
            VisualizationResult with the plot.
        """
        cfg = config or self.config

        # Sort by absolute importance
        if cfg.sort_by_importance:
            sorted_items = sorted(
                feature_importance.items(),
                key=lambda x: abs(x[1]),
                reverse=True,
            )
        else:
            sorted_items = list(feature_importance.items())

        # Limit features
        sorted_items = sorted_items[: cfg.max_features]

        labels = [item[0] for item in sorted_items]
        values = [item[1] for item in sorted_items]

        # Assign colors based on value direction
        colors = []
        for val in values:
            if val > 0:
                colors.append(self._DIVERGING_COLORS["positive"])
            elif val < 0:
                colors.append(self._DIVERGING_COLORS["negative"])
            else:
                colors.append(self._DIVERGING_COLORS["neutral"])

        plot = PlotData(
            plot_type=cfg.plot_type,
            title=title,
            x_data=list(range(len(labels))),
            y_data=values,
            colors=colors,
            labels=labels,
            metadata={"feature_count": len(labels)},
        )

        summary = self._generate_importance_summary(sorted_items)

        return VisualizationResult(
            plots=[plot],
            summary=summary,
            config=cfg,
            metadata={"type": "feature_importance"},
        )

    def create_shap_waterfall(
        self,
        shap_values: dict[str, float],
        base_value: float,
        title: str = "SHAP Waterfall",
    ) -> VisualizationResult:
        """Create a SHAP waterfall visualization.

        Args:
            shap_values: Dictionary of SHAP values.
            base_value: Base/expected value.
            title: Title for the plot.

        Returns:
            VisualizationResult with waterfall plot.
        """
        # Sort by absolute value
        sorted_items = sorted(
            shap_values.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[: self.config.max_features]

        # Add base and final values
        labels = ["base"] + [item[0] for item in sorted_items] + ["final"]
        values = [base_value] + [item[1] for item in sorted_items]
        final_value = base_value + sum(v for v in shap_values.values())

        colors = [self._DIVERGING_COLORS["neutral"]]
        for val in values[1:-1]:
            if val > 0:
                colors.append(self._DIVERGING_COLORS["positive"])
            else:
                colors.append(self._DIVERGING_COLORS["negative"])
        colors.append("#3498db")  # Final value color

        plot = PlotData(
            plot_type=PlotType.WATERFALL,
            title=title,
            x_data=list(range(len(labels))),
            y_data=values,
            colors=colors,
            labels=labels,
            annotations=[
                {"x": i, "y": val, "text": f"{val:.3f}"} for i, val in enumerate(values)
            ],
            metadata={
                "base_value": base_value,
                "final_value": final_value,
            },
        )

        summary = f"Base value: {base_value:.3f}, Final prediction: {final_value:.3f}"

        return VisualizationResult(
            plots=[plot],
            summary=summary,
            config=self.config,
            metadata={"type": "shap_waterfall"},
        )

    def create_reasoning_chain_visualization(
        self,
        reasoning_steps: list[dict[str, Any]],
        title: str = "Reasoning Chain",
    ) -> VisualizationResult:
        """Create a visualization of the reasoning chain.

        Args:
            reasoning_steps: List of reasoning step dictionaries.
            title: Title for the plot.

        Returns:
            VisualizationResult with reasoning visualization.
        """
        if not reasoning_steps:
            return VisualizationResult(
                plots=[],
                summary="No reasoning steps to visualize",
                config=self.config,
                metadata={"type": "reasoning_chain"},
            )

        # Extract step information
        labels = [
            f"Step {s.get('step_number', i + 1)}" for i, s in enumerate(reasoning_steps)
        ]
        confidences = [s.get("confidence", 0.5) for s in reasoning_steps]

        # Color by confidence level
        colors = []
        for conf in confidences:
            if conf >= 0.75:
                colors.append(self._DIVERGING_COLORS["positive"])
            elif conf >= 0.5:
                colors.append("#f39c12")  # Warning orange
            else:
                colors.append(self._DIVERGING_COLORS["negative"])

        plot = PlotData(
            plot_type=PlotType.BAR,
            title=title,
            x_data=list(range(len(labels))),
            y_data=confidences,
            colors=colors,
            labels=labels,
            metadata={"step_count": len(reasoning_steps)},
        )

        avg_confidence = sum(confidences) / len(confidences)
        summary = f"Reasoning chain with {len(reasoning_steps)} steps, average confidence: {avg_confidence:.0%}"

        return VisualizationResult(
            plots=[plot],
            summary=summary,
            config=self.config,
            metadata={"type": "reasoning_chain"},
        )

    def create_confidence_gauge(
        self,
        confidence: float,
        title: str = "Confidence Level",
    ) -> VisualizationResult:
        """Create a confidence gauge visualization.

        Args:
            confidence: Confidence value (0-1).
            title: Title for the plot.

        Returns:
            VisualizationResult with gauge visualization.
        """
        # Map confidence to color
        if confidence >= 0.75:
            color = self._DIVERGING_COLORS["positive"]
        elif confidence >= 0.5:
            color = "#f39c12"
        else:
            color = self._DIVERGING_COLORS["negative"]

        plot = PlotData(
            plot_type=PlotType.BAR,  # Simplified as bar for gauge
            title=title,
            x_data=["confidence"],
            y_data=[confidence],
            colors=[color],
            labels=["Confidence"],
            annotations=[{"x": 0, "y": confidence, "text": f"{confidence:.0%}"}],
            metadata={"confidence": confidence},
        )

        level = self._get_confidence_level(confidence)
        summary = f"Confidence level: {level} ({confidence:.0%})"

        return VisualizationResult(
            plots=[plot],
            summary=summary,
            config=self.config,
            metadata={"type": "confidence_gauge", "level": level},
        )

    def create_multi_comparison(
        self,
        explanations: list[dict[str, Any]],
        title: str = "Explanation Comparison",
    ) -> VisualizationResult:
        """Create a comparison visualization for multiple explanations.

        Args:
            explanations: List of explanation dictionaries.
            title: Title for the plot.

        Returns:
            VisualizationResult with comparison visualization.
        """
        plots = []

        # Create bar chart comparing key factors across explanations
        all_features = set()
        for exp in explanations:
            all_features.update(exp.get("key_factors", {}).keys())

        all_features = sorted(all_features)[: self.config.max_features]

        for i, exp in enumerate(explanations):
            key_factors = exp.get("key_factors", {})
            values = [key_factors.get(f, 0) for f in all_features]

            colors = [
                self._DIVERGING_COLORS["positive"]
                if v > 0
                else self._DIVERGING_COLORS["negative"]
                for v in values
            ]

            plot = PlotData(
                plot_type=PlotType.BAR,
                title=f"Explanation {i + 1}",
                x_data=all_features,
                y_data=values,
                colors=colors,
                labels=all_features,
            )
            plots.append(plot)

        summary = f"Comparison of {len(explanations)} explanations"

        return VisualizationResult(
            plots=plots,
            summary=summary,
            config=self.config,
            metadata={"type": "comparison", "explanation_count": len(explanations)},
        )

    def _generate_importance_summary(
        self,
        feature_items: list[tuple[str, float]],
    ) -> str:
        """Generate a summary text for feature importance."""
        if not feature_items:
            return "No features to analyze"

        positive = [(n, v) for n, v in feature_items if v > 0]
        negative = [(n, v) for n, v in feature_items if v < 0]

        top_positive = positive[0] if positive else None
        top_negative = negative[0] if negative else None

        parts = [f"Analyzed {len(feature_items)} features."]

        if top_positive:
            parts.append(f"Top positive: {top_positive[0]} ({top_positive[1]:+.3f})")
        if top_negative:
            parts.append(f"Top negative: {top_negative[0]} ({top_negative[1]:+.3f})")

        return " ".join(parts)

    def _get_confidence_level(self, confidence: float) -> str:
        """Get confidence level description."""
        if confidence >= 0.9:
            return "Very High"
        elif confidence >= 0.75:
            return "High"
        elif confidence >= 0.5:
            return "Moderate"
        elif confidence >= 0.25:
            return "Low"
        return "Very Low"


__all__ = [
    "PlotType",
    "VisualizationConfig",
    "PlotData",
    "VisualizationResult",
    "ExplanationVisualizer",
]
