"""Grafana panel manager for paper trading monitoring.

Provides functionality to:
- Import panel definitions to Grafana via API
- Validate panel JSON structure
- Generate dashboard JSON from panel definitions

For PAPER-DIAG-001-FOLLOWUP-001: Grafana panels for pipeline status, signals, and recovery
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class PanelValidationResult:
    """Result of panel validation.

    Attributes:
        panel_id: Unique identifier for the panel
        is_valid: Whether the panel passed validation
        errors: List of validation errors
        warnings: List of validation warnings
    """

    panel_id: str
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


class GrafanaPanelManager:
    """Manager for Grafana panels and dashboards.

    Handles:
    - Loading panel definitions from YAML config
    - Generating Grafana-compatible JSON
    - Validating panel structure
    - Importing panels to Grafana via API
    """

    # Required panel fields
    REQUIRED_FIELDS = {
        "type": str,
        "description": str,
    }

    # Valid panel types
    VALID_PANEL_TYPES = {
        "stat",
        "timeseries",
        "table",
        "gauge",
        "heatmap",
        "barchart",
        "piechart",
        "histogram",
        "logs",
        "news",
    }

    # Valid Redis commands for data source
    VALID_REDIS_COMMANDS = {
        "GET",
        "TS.RANGE",
        "LRANGE",
        "SMEMBERS",
        "ZRANGE",
        "HGET",
        "HGETALL",
    }

    def __init__(
        self,
        config_path: str | None = None,
        grafana_url: str | None = None,
        grafana_api_key: str | None = None,
    ) -> None:
        """Initialize the panel manager.

        Args:
            config_path: Path to grafana_queries.yaml config file
            grafana_url: Grafana instance URL (e.g., http://localhost:3001)
            grafana_api_key: API key for Grafana authentication
        """
        self.config_path = config_path or self._find_config_path()
        self.grafana_url = grafana_url or os.getenv(
            "GRAFANA_URL", "http://localhost:3001"
        )
        self.api_key = grafana_api_key or os.getenv("GRAFANA_API_KEY")

        self._config: dict[str, Any] | None = None
        self._panel_cache: dict[str, dict[str, Any]] = {}

        logger.info(f"GrafanaPanelManager initialized: config={self.config_path}")

    def _find_config_path(self) -> str:
        """Find the grafana_queries.yaml config file."""
        # Check common locations
        paths = [
            "config/grafana_queries.yaml",
            "../config/grafana_queries.yaml",
            "../../config/grafana_queries.yaml",
            "/home/tacopants/projects/ChiseAI/config/grafana_queries.yaml",
        ]

        for path in paths:
            if os.path.exists(path):
                return path

        raise FileNotFoundError("Could not find grafana_queries.yaml config file")

    def load_config(self) -> dict[str, Any]:
        """Load the panel configuration from YAML.

        Returns:
            Dictionary containing panel configurations
        """
        if self._config is not None:
            return self._config

        with open(self.config_path) as f:
            self._config = yaml.safe_load(f)

        logger.debug(f"Loaded config from {self.config_path}")
        return self._config

    def get_dashboard_panels(self, dashboard_name: str) -> dict[str, Any]:
        """Get all panels for a specific dashboard.

        Args:
            dashboard_name: Name of the dashboard (e.g., "paper_pipeline_status")

        Returns:
            Dictionary of panel definitions
        """
        config = self.load_config()
        dashboards = config.get("dashboards", {})

        if dashboard_name not in dashboards:
            raise ValueError(f"Dashboard '{dashboard_name}' not found in config")

        return dashboards[dashboard_name].get("panels", {})

    def validate_panel(
        self,
        panel_id: str,
        panel_config: dict[str, Any],
        strict: bool = False,
    ) -> PanelValidationResult:
        """Validate a panel configuration.

        Args:
            panel_id: Unique identifier for the panel
            panel_config: Panel configuration dictionary
            strict: If True, treat warnings as errors

        Returns:
            PanelValidationResult with validation status
        """
        result = PanelValidationResult(panel_id=panel_id, is_valid=True)

        # Check required fields
        for field, field_type in self.REQUIRED_FIELDS.items():
            if field not in panel_config:
                result.add_error(f"Missing required field: {field}")
            elif not isinstance(panel_config[field], field_type):
                result.add_error(
                    f"Field '{field}' must be of type {field_type.__name__}"
                )

        # Validate panel type
        panel_type = panel_config.get("type")
        if panel_type and panel_type not in self.VALID_PANEL_TYPES:
            result.add_error(f"Invalid panel type: {panel_type}")

        # Validate Redis configuration
        redis_key = panel_config.get("redis_key")
        redis_command = panel_config.get("redis_command")

        if redis_key and redis_command:
            if redis_command not in self.VALID_REDIS_COMMANDS:
                result.add_error(f"Invalid Redis command: {redis_command}")

        # Type-specific validation
        if panel_type == "stat":
            self._validate_stat_panel(panel_config, result)
        elif panel_type == "timeseries":
            self._validate_timeseries_panel(panel_config, result)
        elif panel_type == "table":
            self._validate_table_panel(panel_config, result)

        # Check for cache_ttl
        if "cache_ttl" not in panel_config:
            result.add_warning("Missing cache_ttl, using default (300s)")

        # Strict mode: warnings become errors
        if strict and result.warnings:
            for warning in result.warnings:
                result.add_error(f"(Strict) {warning}")
            result.warnings = []

        return result

    def _validate_stat_panel(
        self, config: dict[str, Any], result: PanelValidationResult
    ) -> None:
        """Validate a stat panel configuration."""
        field_config = config.get("field_config", {})
        mappings = field_config.get("mappings", [])

        if not mappings and "thresholds" not in field_config:
            result.add_warning(
                "Stat panel should have mappings or thresholds for visual states"
            )

    def _validate_timeseries_panel(
        self, config: dict[str, Any], result: PanelValidationResult
    ) -> None:
        """Validate a timeseries panel configuration."""
        field_config = config.get("field_config", {})

        # Check for custom draw style
        custom = field_config.get("custom", {})
        if "drawStyle" not in custom:
            result.add_warning(
                "Timeseries panel should specify drawStyle (line, bars, points)"
            )

    def _validate_table_panel(
        self, config: dict[str, Any], result: PanelValidationResult
    ) -> None:
        """Validate a table panel configuration."""
        redis_command = config.get("redis_command")

        if redis_command == "LRANGE" and "redis_range" not in config:
            result.add_warning("Table panel with LRANGE should specify redis_range")

    def validate_all_panels(
        self, dashboard_name: str, strict: bool = False
    ) -> list[PanelValidationResult]:
        """Validate all panels in a dashboard.

        Args:
            dashboard_name: Name of the dashboard
            strict: If True, treat warnings as errors

        Returns:
            List of validation results for all panels
        """
        panels = self.get_dashboard_panels(dashboard_name)
        results = []

        for panel_id, panel_config in panels.items():
            result = self.validate_panel(panel_id, panel_config, strict)
            results.append(result)

        return results

    def generate_panel_json(
        self,
        panel_id: str,
        panel_config: dict[str, Any],
        grid_pos: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Generate Grafana-compatible panel JSON.

        Args:
            panel_id: Unique identifier for the panel
            panel_config: Panel configuration dictionary
            grid_pos: Optional grid position (x, y, w, h)

        Returns:
            Grafana panel JSON dictionary
        """
        panel_type = panel_config.get("type", "stat")

        # Base panel structure
        panel = {
            "id": panel_id,
            "title": panel_config.get("title", panel_id.replace("_", " ").title()),
            "type": panel_type,
            "description": panel_config.get("description", ""),
            "datasource": {"type": "redis-datasource", "uid": "redis"},
            "targets": self._generate_targets(panel_config),
            "fieldConfig": {
                "defaults": self._generate_field_config(panel_config),
                "overrides": [],
            },
            "options": self._generate_options(panel_config),
        }

        # Add grid position if provided
        if grid_pos:
            panel["gridPos"] = grid_pos

        return panel

    def _generate_targets(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate panel targets for Redis data source."""
        redis_key = config.get("redis_key")
        redis_command = config.get("redis_command", "GET")

        if not redis_key:
            return []

        target = {
            "datasource": {"type": "redis-datasource", "uid": "redis"},
            "command": redis_command,
            "key": redis_key,
            "refId": "A",
        }

        # Add range for LRANGE
        if redis_command == "LRANGE" and "redis_range" in config:
            redis_range = config["redis_range"]
            target["start"] = str(redis_range[0])
            target["end"] = str(redis_range[1])

        return [target]

    def _generate_field_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Generate field configuration from panel config."""
        field_config = config.get("field_config", {})

        defaults = {
            "color": {"mode": "thresholds"},
            "mappings": [],
            "thresholds": {
                "mode": "absolute",
                "steps": [{"color": "green", "value": None}],
            },
            "unit": field_config.get("unit", "none"),
        }

        # Add mappings for stat panels
        if "mappings" in field_config:
            mappings = []
            for mapping in field_config["mappings"]:
                mappings.append(
                    {
                        "options": {
                            mapping["value"]: {
                                "color": mapping.get("color", "green"),
                                "index": 0,
                                "text": mapping.get("text", mapping["value"]),
                            }
                        },
                        "type": "value",
                    }
                )
            defaults["mappings"] = mappings

        # Add custom config for timeseries
        if config.get("type") == "timeseries":
            custom = field_config.get("custom", {})
            defaults["custom"] = {
                "drawStyle": custom.get("drawStyle", "line"),
                "fillOpacity": custom.get("fillOpacity", 20),
                "lineWidth": custom.get("lineWidth", 2),
                "pointSize": custom.get("pointSize", 4),
                "showPoints": "auto",
            }

        return defaults

    def _generate_options(self, config: dict[str, Any]) -> dict[str, Any]:
        """Generate panel options from config."""
        panel_type = config.get("type", "stat")
        options_config = config.get("options", {})

        if panel_type == "stat":
            return {
                "colorMode": options_config.get("colorMode", "background"),
                "graphMode": options_config.get("graphMode", "none"),
                "justifyMode": options_config.get("justifyMode", "center"),
                "orientation": "auto",
                "reduceOptions": {
                    "values": False,
                    "calcs": ["lastNotNull"],
                    "fields": "",
                },
                "textMode": options_config.get("textMode", "auto"),
            }
        elif panel_type == "timeseries":
            return {
                "legend": {
                    "calcs": options_config.get("legend", {}).get("calcs", ["mean"]),
                    "displayMode": options_config.get("legend", {}).get(
                        "displayMode", "table"
                    ),
                    "placement": options_config.get("legend", {}).get(
                        "placement", "bottom"
                    ),
                    "showLegend": options_config.get("legend", {}).get(
                        "showLegend", True
                    ),
                },
                "tooltip": {"mode": "multi", "sort": "none"},
            }
        elif panel_type == "table":
            return {
                "showHeader": options_config.get("showHeader", True),
            }

        return {}

    def generate_dashboard_json(
        self,
        dashboard_name: str,
        title: str | None = None,
        uid: str | None = None,
    ) -> dict[str, Any]:
        """Generate complete dashboard JSON for a dashboard.

        Args:
            dashboard_name: Name of the dashboard in config
            title: Dashboard title (defaults to dashboard_name)
            uid: Dashboard UID (defaults to dashboard_name)

        Returns:
            Complete Grafana dashboard JSON
        """
        panels = self.get_dashboard_panels(dashboard_name)
        config = self.load_config()
        dashboard_config = config.get("dashboards", {}).get(dashboard_name, {})

        # Generate panels with grid layout
        panel_json_list = []
        y_offset = 0

        for i, (panel_id, panel_config) in enumerate(panels.items()):
            # Default grid positions
            grid_pos = {
                "h": 8,
                "w": 12,
                "x": (i % 2) * 12,
                "y": y_offset + (i // 2) * 8,
            }

            panel_json = self.generate_panel_json(panel_id, panel_config, grid_pos)
            panel_json_list.append(panel_json)

        # Build dashboard
        dashboard = {
            "annotations": {
                "list": [
                    {
                        "builtIn": 1,
                        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                        "enable": True,
                        "hide": True,
                        "iconColor": "rgba(0, 211, 255, 1)",
                        "name": "Annotations & Alerts",
                        "type": "dashboard",
                    }
                ]
            },
            "description": dashboard_config.get("description", ""),
            "editable": True,
            "fiscalYearStartMonth": 0,
            "graphTooltip": 0,
            "id": None,
            "links": [],
            "liveNow": False,
            "panels": panel_json_list,
            "refresh": dashboard_config.get("refresh_interval", "5s"),
            "schemaVersion": 38,
            "style": "dark",
            "tags": ["paper-trading", "pipeline", "monitoring"],
            "templating": {"list": []},
            "time": {
                "from": dashboard_config.get("default_time_range", "now-1h"),
                "to": "now",
            },
            "timepicker": {},
            "timezone": "",
            "title": title or dashboard_name.replace("_", " ").title(),
            "uid": uid or dashboard_name,
            "version": 1,
            "weekStart": "",
        }

        return dashboard

    def export_panels_to_json(
        self,
        dashboard_name: str,
        output_path: str | None = None,
    ) -> str:
        """Export panels to a JSON file.

        Args:
            dashboard_name: Name of the dashboard
            output_path: Path to save the JSON file (optional)

        Returns:
            Path to the exported JSON file
        """
        dashboard_json = self.generate_dashboard_json(dashboard_name)

        if output_path is None:
            output_path = f"{dashboard_name}_panels.json"

        with open(output_path, "w") as f:
            json.dump(dashboard_json, f, indent=2)

        logger.info(f"Exported panels to {output_path}")
        return output_path

    def get_validation_summary(
        self, results: list[PanelValidationResult]
    ) -> dict[str, Any]:
        """Generate a summary of validation results.

        Args:
            results: List of validation results

        Returns:
            Summary dictionary
        """
        total = len(results)
        valid = sum(1 for r in results if r.is_valid)
        errors = sum(len(r.errors) for r in results)
        warnings = sum(len(r.warnings) for r in results)

        return {
            "total_panels": total,
            "valid_panels": valid,
            "invalid_panels": total - valid,
            "total_errors": errors,
            "total_warnings": warnings,
            "results": [
                {
                    "panel_id": r.panel_id,
                    "is_valid": r.is_valid,
                    "errors": r.errors,
                    "warnings": r.warnings,
                }
                for r in results
            ],
        }


def main():
    """CLI entry point for panel validation and export."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Grafana Panel Manager for Paper Trading"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate panels in the specified dashboard",
    )
    parser.add_argument("--export", action="store_true", help="Export panels to JSON")
    parser.add_argument(
        "--dashboard",
        type=str,
        default="paper_pipeline_status",
        help="Dashboard name (default: paper_pipeline_status)",
    )
    parser.add_argument("--output", type=str, help="Output path for JSON export")
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    manager = GrafanaPanelManager()

    if args.validate:
        print(f"\nValidating panels in dashboard: {args.dashboard}")
        print("=" * 60)

        results = manager.validate_all_panels(args.dashboard, strict=args.strict)
        summary = manager.get_validation_summary(results)

        for result in results:
            status = "✓" if result.is_valid else "✗"
            print(f"\n{status} {result.panel_id}")

            if result.errors:
                print("  Errors:")
                for error in result.errors:
                    print(f"    - {error}")

            if result.warnings:
                print("  Warnings:")
                for warning in result.warnings:
                    print(f"    - {warning}")

        print("\n" + "=" * 60)
        print(
            f"Summary: {summary['valid_panels']}/{summary['total_panels']} panels valid"
        )
        print(
            f"Errors: {summary['total_errors']}, Warnings: {summary['total_warnings']}"
        )

        return 0 if summary["invalid_panels"] == 0 else 1

    elif args.export:
        output_path = args.output or f"{args.dashboard}_panels.json"

        # Validate first
        results = manager.validate_all_panels(args.dashboard)
        if any(not r.is_valid for r in results):
            print("Validation failed, cannot export. Run with --validate for details.")
            return 1

        exported_path = manager.export_panels_to_json(args.dashboard, output_path)
        print(f"Exported dashboard to: {exported_path}")

        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    exit(main())
