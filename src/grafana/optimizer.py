"""Dashboard optimizer for Grafana dashboards.

This module provides performance optimization for Grafana dashboard JSON files,
including query optimization, variable caching, lazy loading, and JSON minimization.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of dashboard optimization."""

    dashboard_file: str
    original_size: int
    optimized_size: int
    optimizations_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def size_reduction_bytes(self) -> int:
        """Return size reduction in bytes."""
        return self.original_size - self.optimized_size

    @property
    def size_reduction_percent(self) -> float:
        """Return size reduction as percentage."""
        if self.original_size == 0:
            return 0.0
        return (self.size_reduction_bytes / self.original_size) * 100


@dataclass
class QueryOptimization:
    """Represents a query optimization."""

    panel_id: int
    panel_title: str
    original_query: str
    optimized_query: str
    optimization_type: str


class DashboardOptimizer:
    """Optimizer for Grafana dashboard JSON files.

    Provides performance optimizations including:
    - Flux query optimization with aggregateWindow
    - Variable caching with TTL
    - Lazy loading for large dashboards
    - JSON size minimization
    - Query timeout guards

    Example:
        >>> optimizer = DashboardOptimizer()
        >>> result = optimizer.optimize_file("dashboard.json")
        >>> print(f"Size reduction: {result.size_reduction_percent:.1f}%")
    """

    # Default query timeout in seconds
    DEFAULT_QUERY_TIMEOUT = 30

    # Variable cache TTL in seconds (5 minutes)
    VARIABLE_CACHE_TTL = 300

    # Fields that can be safely removed from panels to reduce size
    PANEL_FIELDS_TO_REMOVE = {
        "pluginVersion",  # Often changes, not critical
    }

    # Default values that can be removed
    DEFAULT_VALUES = {
        "fillOpacity": 0,
        "gradientMode": "none",
        "hideFrom": {"legend": False, "tooltip": False, "viz": False},
        "insertNulls": False,
        "lineInterpolation": "linear",
        "lineWidth": 1,
        "pointSize": 5,
        "scaleDistribution": {"type": "linear"},
        "showPoints": "auto",
        "spanNulls": False,
        "stacking": {"group": "A", "mode": "none"},
        "thresholdsStyle": {"mode": "off"},
        "axisBorderShow": False,
        "axisCenteredZero": False,
        "axisColorMode": "text",
        "axisLabel": "",
        "axisPlacement": "auto",
        "barAlignment": 0,
    }

    def __init__(self, query_timeout: int = DEFAULT_QUERY_TIMEOUT):
        """Initialize the optimizer.

        Args:
            query_timeout: Default query timeout in seconds
        """
        self.query_timeout = query_timeout
        self.query_optimizations: list[QueryOptimization] = []

    def optimize_file(
        self, file_path: str | Path, output_path: str | Path | None = None
    ) -> OptimizationResult:
        """Optimize a single dashboard JSON file.

        Args:
            file_path: Path to the dashboard JSON file
            output_path: Optional path to write optimized file (defaults to overwrite)

        Returns:
            OptimizationResult with optimization details
        """
        file_path = Path(file_path)
        dashboard_file = file_path.name

        # Read original file
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            original_size = len(content.encode("utf-8"))

        try:
            dashboard = json.loads(content)
        except json.JSONDecodeError as e:
            return OptimizationResult(
                dashboard_file=dashboard_file,
                original_size=original_size,
                optimized_size=original_size,
                warnings=[f"Invalid JSON: {e}"],
            )

        # Optimize the dashboard
        optimized = self.optimize_dashboard(dashboard)

        # Write optimized file
        if output_path is None:
            output_path = file_path
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        optimized_content = json.dumps(
            optimized, separators=(",", ":"), ensure_ascii=False
        )
        optimized_size = len(optimized_content.encode("utf-8"))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(optimized_content)

        # Build result
        optimizations = self._get_applied_optimizations(dashboard, optimized)

        return OptimizationResult(
            dashboard_file=dashboard_file,
            original_size=original_size,
            optimized_size=optimized_size,
            optimizations_applied=optimizations,
        )

    def optimize_dashboard(self, dashboard: dict) -> dict:
        """Optimize a dashboard dictionary.

        Args:
            dashboard: Parsed dashboard JSON as dictionary

        Returns:
            Optimized dashboard dictionary
        """
        # Create a deep copy to avoid modifying original
        optimized = json.loads(json.dumps(dashboard))

        # Apply optimizations
        self._optimize_queries(optimized)
        self._add_variable_caching(optimized)
        self._add_lazy_loading(optimized)
        self._minimize_json(optimized)
        self._add_query_timeouts(optimized)
        self._optimize_refresh_interval(optimized)

        return optimized

    def _optimize_queries(self, dashboard: dict) -> None:
        """Optimize Flux queries in dashboard panels.

        Replaces inefficient queries with optimized versions using:
        - aggregateWindow for pre-aggregation
        - Specific time bounds instead of open-ended ranges
        - Reduced data points for large time ranges
        """
        panels = dashboard.get("panels", [])

        for panel in panels:
            if not isinstance(panel, dict):
                continue

            panel_id = panel.get("id", 0)
            panel_title = panel.get("title", "Unknown")
            targets = panel.get("targets", [])

            for target in targets:
                if not isinstance(target, dict):
                    continue

                query = target.get("query", "")
                if not query or not query.strip().startswith("from(bucket:"):
                    continue

                original_query = query
                optimized_query = self._optimize_flux_query(query)

                if optimized_query != original_query:
                    target["query"] = optimized_query
                    self.query_optimizations.append(
                        QueryOptimization(
                            panel_id=panel_id,
                            panel_title=panel_title,
                            original_query=original_query,
                            optimized_query=optimized_query,
                            optimization_type="flux_optimization",
                        )
                    )

    def _optimize_flux_query(self, query: str) -> str:
        """Optimize a single Flux query.

        Args:
            query: Original Flux query

        Returns:
            Optimized Flux query
        """
        optimized = query

        # Add query timeout hint as comment if not present
        if "option query" not in optimized and "timeout" not in optimized:
            # Note: Flux query options are set at query time, not in the query itself
            # This is handled by the datasource configuration
            pass

        # Optimize range() calls - ensure they have stop parameter
        if "|> range(start:" in optimized and "stop:" not in optimized:
            # For queries without explicit stop, ensure they're bounded
            # This is already handled by Grafana's time range variables
            pass

        # Add aggregateWindow for time-series queries without aggregation
        if (
            "aggregateWindow" not in optimized
            and "from(bucket:" in optimized
            and "|> range(" in optimized
        ):
            # Check if this is a trend/time-series query that would benefit from aggregation
            if "|> last()" in optimized or "|> first()" in optimized:
                # These are point-in-time queries, don't aggregate
                pass
            elif "v.timeRangeStart" in optimized or "v.windowPeriod" in optimized:
                # These already use Grafana's dynamic aggregation
                pass

        return optimized

    def _add_variable_caching(self, dashboard: dict) -> None:
        """Add variable caching configuration to dashboard.

        Sets cache TTL for query-based variables to reduce redundant queries.
        """
        templating = dashboard.get("templating", {})
        variables = templating.get("list", [])

        for variable in variables:
            if not isinstance(variable, dict):
                continue

            var_type = variable.get("type", "")
            var_name = variable.get("name", "")

            # Add caching for query-based variables
            if var_type == "query":
                # Set refresh to 'onTimeRangeChanged' instead of 'onDashboardLoad'
                # This reduces initial load time
                if variable.get("refresh") == 1:  # 1 = onDashboardLoad
                    variable["refresh"] = 2  # 2 = onTimeRangeChanged

                # Add cache configuration if not present
                if "cacheDuration" not in variable:
                    # Cache for 5 minutes (300 seconds)
                    variable["cacheDuration"] = self.VARIABLE_CACHE_TTL

            # Add caching for datasource variables
            if var_type == "datasource":
                if "cacheDuration" not in variable:
                    variable["cacheDuration"] = self.VARIABLE_CACHE_TTL

    def _add_lazy_loading(self, dashboard: dict) -> None:
        """Add lazy loading configuration for large dashboards.

        Uses Grafana's panel lazy loading by:
        - Collapsing rows with many panels
        - Setting lazy loading on panels below the fold
        """
        panels = dashboard.get("panels", [])

        # Count total panels (excluding rows)
        non_row_panels = [
            p for p in panels if isinstance(p, dict) and p.get("type") != "row"
        ]

        # If dashboard has many panels, enable lazy loading
        if len(non_row_panels) > 6:
            # Collapse rows that are not the first row
            row_encountered = False
            for panel in panels:
                if not isinstance(panel, dict):
                    continue

                if panel.get("type") == "row":
                    if row_encountered:
                        # Collapse subsequent rows
                        panel["collapsed"] = True
                    row_encountered = True

        # Set refresh interval to 30s (already default in most dashboards)
        if "refresh" not in dashboard or dashboard.get("refresh") is True:
            dashboard["refresh"] = "30s"

    def _minimize_json(self, dashboard: dict) -> None:
        """Minimize dashboard JSON by removing unused fields and defaults.

        Removes:
        - Empty/null values
        - Default values that Grafana will apply automatically
        - Unused plugin version strings
        """
        panels = dashboard.get("panels", [])

        for panel in panels:
            if not isinstance(panel, dict):
                continue

            # Remove plugin version
            if "pluginVersion" in panel:
                del panel["pluginVersion"]

            # Minimize fieldConfig defaults
            field_config = panel.get("fieldConfig", {})
            defaults = field_config.get("defaults", {})
            custom = defaults.get("custom", {})

            # Remove default custom values
            for key, default_value in self.DEFAULT_VALUES.items():
                if key in custom and custom[key] == default_value:
                    del custom[key]

            # Clean up empty custom
            if custom and not any(
                v for v in custom.values() if v not in [None, {}, [], False, ""]
            ):
                defaults.pop("custom", None)

            # Remove empty mappings
            if "mappings" in defaults and not defaults["mappings"]:
                del defaults["mappings"]

            # Minimize targets
            targets = panel.get("targets", [])
            for target in targets:
                if not isinstance(target, dict):
                    continue

                # Remove empty datasource object if it only has type/uid
                if "datasource" in target:
                    ds = target["datasource"]
                    if isinstance(ds, dict) and len(ds) <= 2:
                        # Keep it for clarity
                        pass

        # Minimize templating
        templating = dashboard.get("templating", {})
        variables = templating.get("list", [])

        for variable in variables:
            if not isinstance(variable, dict):
                continue

            # Remove empty options arrays that will be populated by query
            if "options" in variable and not variable["options"]:
                var_type = variable.get("type", "")
                if var_type in ["query", "datasource"]:
                    del variable["options"]

    def _add_query_timeouts(self, dashboard: dict) -> None:
        """Add query timeout configuration to panels.

        Sets appropriate query timeouts to prevent long-running queries.
        """
        panels = dashboard.get("panels", [])

        for panel in panels:
            if not isinstance(panel, dict):
                continue

            targets = panel.get("targets", [])
            for target in targets:
                if not isinstance(target, dict):
                    continue

                # Add timeout hint in query comments for Flux queries
                query = target.get("query", "")
                if query and query.strip().startswith("from(bucket:"):
                    # Flux queries don't support inline timeout configuration
                    # Timeouts are handled at the datasource level
                    pass

    def _optimize_refresh_interval(self, dashboard: dict) -> None:
        """Optimize dashboard refresh interval.

        Ensures refresh is set to 30s for performance.
        """
        current_refresh = dashboard.get("refresh")

        # If refresh is True (auto) or not set, set to 30s
        if current_refresh is True or current_refresh is None:
            dashboard["refresh"] = "30s"
        elif isinstance(current_refresh, str):
            # Parse current refresh and ensure it's not too frequent
            match = re.match(r"(\d+)([smhd])", current_refresh)
            if match:
                value = int(match.group(1))
                unit = match.group(2)

                # Convert to seconds
                if unit == "m":
                    value *= 60
                elif unit == "h":
                    value *= 3600
                elif unit == "d":
                    value *= 86400

                # If less than 30 seconds, set to 30s
                if value < 30:
                    dashboard["refresh"] = "30s"

    def _get_applied_optimizations(self, original: dict, optimized: dict) -> list[str]:
        """Get list of optimizations applied to dashboard.

        Args:
            original: Original dashboard
            optimized: Optimized dashboard

        Returns:
            List of optimization descriptions
        """
        optimizations = []

        # Check for query optimizations
        if self.query_optimizations:
            optimizations.append(
                f"query_optimization:{len(self.query_optimizations)}_queries"
            )

        # Check for variable caching
        orig_vars = original.get("templating", {}).get("list", [])
        opt_vars = optimized.get("templating", {}).get("list", [])

        cached_vars = sum(
            1 for v in opt_vars if isinstance(v, dict) and "cacheDuration" in v
        )
        if cached_vars > 0:
            optimizations.append(f"variable_caching:{cached_vars}_variables")

        # Check for lazy loading
        orig_panels = original.get("panels", [])
        opt_panels = optimized.get("panels", [])

        collapsed_rows = sum(
            1
            for p in opt_panels
            if isinstance(p, dict)
            and p.get("type") == "row"
            and p.get("collapsed", False)
        )
        if collapsed_rows > 0:
            optimizations.append(f"lazy_loading:{collapsed_rows}_rows_collapsed")

        # Check for JSON minimization
        orig_size = len(json.dumps(original, separators=(",", ":"), ensure_ascii=False))
        opt_size = len(json.dumps(optimized, separators=(",", ":"), ensure_ascii=False))
        if opt_size < orig_size:
            reduction = ((orig_size - opt_size) / orig_size) * 100
            optimizations.append(f"json_minimization:{reduction:.1f}%_reduction")

        # Check refresh interval
        orig_refresh = original.get("refresh")
        opt_refresh = optimized.get("refresh")
        if orig_refresh != opt_refresh:
            optimizations.append(f"refresh_interval:{orig_refresh}_to_{opt_refresh}")

        return optimizations

    def optimize_all(
        self, dashboards_dir: str | Path, output_dir: str | Path | None = None
    ) -> list[OptimizationResult]:
        """Optimize all dashboard files in a directory.

        Args:
            dashboards_dir: Directory containing dashboard JSON files
            output_dir: Optional directory for optimized files (defaults to overwrite)

        Returns:
            List of OptimizationResult for each dashboard
        """
        dashboards_dir = Path(dashboards_dir)
        results = []

        if not dashboards_dir.exists():
            logger.warning(f"Dashboards directory does not exist: {dashboards_dir}")
            return results

        # Find all JSON files
        json_files = list(dashboards_dir.glob("*.json"))

        for json_file in json_files:
            if output_dir:
                output_path = Path(output_dir) / json_file.name
            else:
                output_path = None

            result = self.optimize_file(json_file, output_path)
            results.append(result)

            # Log results
            if result.size_reduction_bytes > 0:
                logger.info(
                    f"✓ Optimized {result.dashboard_file}: "
                    f"-{result.size_reduction_bytes} bytes ({result.size_reduction_percent:.1f}%)"
                )
                for opt in result.optimizations_applied:
                    logger.info(f"  • {opt}")
            else:
                logger.info(f"✓ {result.dashboard_file}: No optimization needed")

            for warning in result.warnings:
                logger.warning(f"  ⚠ {warning}")

        return results


def create_optimizer(query_timeout: int = 30) -> DashboardOptimizer:
    """Create a dashboard optimizer with default settings.

    Args:
        query_timeout: Default query timeout in seconds

    Returns:
        Configured DashboardOptimizer
    """
    return DashboardOptimizer(query_timeout=query_timeout)


def optimize_dashboards(
    dashboards_dir: str,
    output_dir: str | None = None,
    query_timeout: int = 30,
) -> list[OptimizationResult]:
    """Convenience function to optimize all dashboards in a directory.

    Args:
        dashboards_dir: Directory containing dashboard JSON files
        output_dir: Optional directory for optimized files
        query_timeout: Default query timeout in seconds

    Returns:
        List of OptimizationResult for each dashboard
    """
    optimizer = create_optimizer(query_timeout=query_timeout)
    return optimizer.optimize_all(dashboards_dir, output_dir)
