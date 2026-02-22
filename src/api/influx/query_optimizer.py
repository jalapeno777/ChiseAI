"""
Query Optimizer for Grafana InfluxDB Queries

This module provides utilities to optimize InfluxDB queries for Grafana dashboards,
reducing data cardinality and improving performance through intelligent aggregation.

Target: <3s dashboard load time
"""

import re
from datetime import timedelta
from typing import Any, Dict, Optional


class QueryOptimizer:
    """Optimizes InfluxDB queries for Grafana dashboard performance."""

    # Aggregation windows based on time range
    AGGREGATION_WINDOWS = {
        "raw": timedelta(minutes=5),  # Raw data for <5 min
        "1m": timedelta(hours=1),  # 1-minute agg for <1 hour
        "5m": timedelta(days=1),  # 5-minute agg for <1 day
        "1h": timedelta(days=7),  # 1-hour agg for <1 week
        "1d": timedelta(days=365),  # 1-day agg for longer
    }

    # Cache hint patterns for cache layer
    CACHE_HINT_PREFIX = "-- @cacheable"

    def __init__(self, default_bucket: str = "chiseai"):
        """Initialize the query optimizer.

        Args:
            default_bucket: Default InfluxDB bucket name
        """
        self.default_bucket = default_bucket

    def suggest_aggregation(self, time_range: timedelta) -> str:
        """Suggest appropriate aggregation window based on time range.

        Args:
            time_range: The time range of the query

        Returns:
            Aggregation window string (e.g., "1m", "5m", "1h", "1d")
        """
        if time_range <= self.AGGREGATION_WINDOWS["raw"]:
            return "1s"  # Raw data
        elif time_range <= self.AGGREGATION_WINDOWS["1m"]:
            return "1m"
        elif time_range <= self.AGGREGATION_WINDOWS["5m"]:
            return "5m"
        elif time_range <= self.AGGREGATION_WINDOWS["1h"]:
            return "1h"
        else:
            return "1d"

    def optimize_query(
        self,
        query: str,
        time_range: timedelta,
        measurement: Optional[str] = None,
        fields: Optional[list] = None,
        group_by: Optional[list] = None,
    ) -> str:
        """Optimize an InfluxDB query for performance.

        Args:
            query: Original Flux query
            time_range: Time range of the query
            measurement: Measurement name (optional)
            fields: List of fields to select (optional)
            group_by: Additional columns to group by (optional)

        Returns:
            Optimized Flux query
        """
        aggregation = self.suggest_aggregation(time_range)

        # If aggregation is raw (1s), don't add aggregateWindow
        if aggregation == "1s":
            return self._add_cache_hints(query)

        # Build optimized query with aggregation
        optimized = self._build_aggregated_query(
            query, aggregation, measurement, fields, group_by
        )

        return self._add_cache_hints(optimized)

    def _build_aggregated_query(
        self,
        base_query: str,
        aggregation: str,
        measurement: Optional[str],
        fields: Optional[list],
        group_by: Optional[list],
    ) -> str:
        """Build query with appropriate aggregation.

        Args:
            base_query: Base query string
            aggregation: Aggregation window (e.g., "5m", "1h")
            measurement: Measurement name
            fields: Fields to select
            group_by: Additional group by columns

        Returns:
            Optimized query string
        """
        # Extract bucket from query or use default
        bucket_match = re.search(r'from\(bucket:\s*"([^"]+)"\)', base_query)
        bucket = bucket_match.group(1) if bucket_match else self.default_bucket

        # Build optimized query
        lines = [f'from(bucket: "{bucket}")']

        # Use variable time range if present, otherwise use the range from query
        if "v.timeRangeStart" in base_query:
            lines.append("  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)")
        else:
            range_match = re.search(r"range\(start:\s*([^)]+)\)", base_query)
            if range_match:
                lines.append(f"  |> range(start: {range_match.group(1)})")
            else:
                lines.append(
                    "  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)"
                )

        # Add measurement filter if provided
        if measurement:
            lines.append(f'  |> filter(fn: (r) => r._measurement == "{measurement}")')
        else:
            # Try to extract from original query
            meas_match = re.search(r'_measurement\s*==\s*"([^"]+)"', base_query)
            if meas_match:
                lines.append(
                    f'  |> filter(fn: (r) => r._measurement == "{meas_match.group(1)}")'
                )

        # Add field filter if provided
        if fields:
            if len(fields) == 1:
                lines.append(f'  |> filter(fn: (r) => r._field == "{fields[0]}")')
            else:
                field_conditions = " or ".join([f'r._field == "{f}"' for f in fields])
                lines.append(f"  |> filter(fn: (r) => {field_conditions})")
        else:
            # Try to extract from original query
            field_match = re.search(r'_field\s*==\s*"([^"]+)"', base_query)
            if field_match:
                lines.append(
                    f'  |> filter(fn: (r) => r._field == "{field_match.group(1)}")'
                )

        # Add additional filters from original query (tags)
        tag_filters = re.findall(r'r\.([a-z_]+)\s*==\s*"([^"]+)"', base_query)
        for tag, value in tag_filters:
            if tag not in ["_measurement", "_field"]:
                lines.append(f'  |> filter(fn: (r) => r.{tag} == "{value}")')

        # Add variable-based tag filters if present
        if "strategy_id" in base_query and "${strategy_id}" in base_query:
            lines.append(
                '  |> filter(fn: (r) => "${strategy_id}" == "$__all" or r.strategy_id == "${strategy_id}")'
            )

        # Add aggregation window
        lines.append(
            f"  |> aggregateWindow(every: {aggregation}, fn: mean, createEmpty: false)"
        )

        # Add group by if specified
        if group_by:
            group_cols = ", ".join([f'"{col}"' for col in group_by])
            lines.append(f"  |> group(columns: [{group_cols}])")

        # Add last() for stat panels
        if "last()" in base_query and "aggregateWindow" not in base_query:
            lines.append("  |> last()")

        return "\n".join(lines)

    def _add_cache_hints(self, query: str) -> str:
        """Add cache hints to query for cache layer optimization.

        Args:
            query: Query string

        Returns:
            Query with cache hints
        """
        # Add cache hint comment at the beginning
        cache_hint = f"{self.CACHE_HINT_PREFIX}: ttl=300, key=auto\n"
        return cache_hint + query

    def optimize_time_range(
        self, panel_type: str, default_range: Optional[str] = None
    ) -> Dict[str, Any]:
        """Suggest optimal time range for a panel type.

        Args:
            panel_type: Type of panel (e.g., "stat", "timeseries", "table")
            default_range: Current default range

        Returns:
            Dict with optimized time range settings
        """
        ranges = {
            "stat": {"from": "now-1h", "to": "now"},
            "timeseries": {"from": "now-7d", "to": "now"},
            "table": {"from": "now-24h", "to": "now"},
            "piechart": {"from": "now-30d", "to": "now"},
        }

        return ranges.get(panel_type, {"from": "now-7d", "to": "now"})

    def get_panel_refresh_rate(self, panel_type: str) -> str:
        """Get optimal refresh rate for panel type.

        Args:
            panel_type: Type of panel

        Returns:
            Refresh rate string (e.g., "5s", "30s", "1m")
        """
        rates = {
            "stat": "30s",
            "timeseries": "30s",
            "table": "1m",
            "piechart": "5m",
        }
        return rates.get(panel_type, "30s")

    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string to timedelta.

        Args:
            duration_str: Duration string (e.g., "7d", "24h", "5m")

        Returns:
            Timedelta object
        """
        duration_str = duration_str.strip()

        # Handle simple numeric with unit
        match = re.match(r"^(\d+)([smhdw])$", duration_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)

            if unit == "s":
                return timedelta(seconds=value)
            elif unit == "m":
                return timedelta(minutes=value)
            elif unit == "h":
                return timedelta(hours=value)
            elif unit == "d":
                return timedelta(days=value)
            elif unit == "w":
                return timedelta(weeks=value)

        # Handle complex durations (e.g., "1h30m")
        # For simplicity, extract the largest unit
        for unit, multiplier in [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]:
            match = re.search(r"(\d+)" + unit, duration_str)
            if match:
                return timedelta(seconds=int(match.group(1)) * multiplier)

        return timedelta(days=7)  # Default


class DashboardQueryOptimizer:
    """Optimizes all queries in a Grafana dashboard JSON."""

    def __init__(self, optimizer: Optional[QueryOptimizer] = None):
        """Initialize dashboard optimizer.

        Args:
            optimizer: QueryOptimizer instance
        """
        self.optimizer = optimizer or QueryOptimizer()

    def optimize_dashboard(self, dashboard_json: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize all queries in a dashboard.

        Args:
            dashboard_json: Grafana dashboard JSON

        Returns:
            Optimized dashboard JSON
        """
        optimized = dashboard_json.copy()

        for panel in optimized.get("panels", []):
            panel_type = panel.get("type", "")

            # Skip non-data panels
            if panel_type in ["row", "text"]:
                continue

            # Optimize time range
            time_range = self.optimizer.optimize_time_range(panel_type)
            if "timeFrom" not in panel:
                panel["timeFrom"] = time_range["from"]
            if "timeShift" not in panel:
                panel["timeShift"] = None

            # Optimize targets (queries)
            for target in panel.get("targets", []):
                if "query" in target:
                    query = target["query"]

                    # Parse time range from query
                    time_range_delta = self._parse_time_range(query)

                    # Optimize query
                    optimized_query = self.optimizer.optimize_query(
                        query, time_range_delta
                    )
                    target["query"] = optimized_query

        return optimized

    def _parse_time_range(self, query: str) -> timedelta:
        """Parse time range from query.

        Args:
            query: Flux query string

        Returns:
            Time range as timedelta
        """
        # Check for variable time ranges
        if "v.timeRangeStart" in query:
            return timedelta(days=7)  # Default assumption

        # Parse explicit ranges like -7d, -30d, -5m, etc.
        range_match = re.search(r"range\(start:\s*-?([^,)]+)\)", query)
        if range_match:
            range_str = range_match.group(1)
            return self._parse_duration(range_str)

        return timedelta(days=7)  # Default

    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string to timedelta.

        Args:
            duration_str: Duration string (e.g., "7d", "24h", "5m")

        Returns:
            Timedelta object
        """
        duration_str = duration_str.strip()

        # Handle simple numeric with unit
        match = re.match(r"^(\d+)([smhdw])$", duration_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)

            if unit == "s":
                return timedelta(seconds=value)
            elif unit == "m":
                return timedelta(minutes=value)
            elif unit == "h":
                return timedelta(hours=value)
            elif unit == "d":
                return timedelta(days=value)
            elif unit == "w":
                return timedelta(weeks=value)

        # Handle complex durations (e.g., "1h30m")
        # For simplicity, extract the largest unit
        for unit, multiplier in [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]:
            match = re.search(r"(\d+)" + unit, duration_str)
            if match:
                return timedelta(seconds=int(match.group(1)) * multiplier)

        return timedelta(days=7)  # Default


def optimize_grafana_query(
    query: str,
    time_range: str,
    measurement: Optional[str] = None,
    fields: Optional[list] = None,
) -> str:
    """Convenience function to optimize a single query.

    Args:
        query: Original Flux query
        time_range: Time range string (e.g., "7d", "24h")
        measurement: Measurement name
        fields: List of fields

    Returns:
        Optimized query string
    """
    optimizer = QueryOptimizer()

    # Parse time range
    time_delta = optimizer._parse_duration(time_range)

    # Optimize
    return optimizer.optimize_query(query, time_delta, measurement, fields)


# Pre-defined optimized queries for common patterns
OPTIMIZED_QUERIES = {
    "backtest_kpis": {
        "sharpe_ratio": """from(bucket: "${influxdb_bucket}")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "backtest_kpis")
  |> filter(fn: (r) => r._field == "sharpe_ratio")
  |> filter(fn: (r) => "${strategy_id}" == "$__all" or r.strategy_id == "${strategy_id}")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> last()""",
        "max_drawdown": """from(bucket: "${influxdb_bucket}")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "backtest_kpis")
  |> filter(fn: (r) => r._field == "max_drawdown")
  |> filter(fn: (r) => "${strategy_id}" == "$__all" or r.strategy_id == "${strategy_id}")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> last()""",
        "win_rate": """from(bucket: "${influxdb_bucket}")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "backtest_kpis")
  |> filter(fn: (r) => r._field == "win_rate")
  |> filter(fn: (r) => "${strategy_id}" == "$__all" or r.strategy_id == "${strategy_id}")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> last()""",
        "trade_count": """from(bucket: "${influxdb_bucket}")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "backtest_kpis")
  |> filter(fn: (r) => r._field == "trade_count")
  |> filter(fn: (r) => "${strategy_id}" == "$__all" or r.strategy_id == "${strategy_id}")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> last()""",
    },
    "data_freshness": {
        "last_update_age": """from(bucket: "${influxdb_bucket}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "last_update_age_seconds")
  |> filter(fn: (r) => r.source == "${source}")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> last()""",
        "freshness_trend": """from(bucket: "${influxdb_bucket}")
  |> range(start: -${lookback_days}d)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "last_update_age_seconds")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)""",
    },
    "strategy_registry": {
        "status_count": """from(bucket: "${influxdb_bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "strategy_registry")
  |> filter(fn: (r) => r._field == "status")
  |> filter(fn: (r) => r.status == "${status}")
  |> aggregateWindow(every: 1d, fn: count, createEmpty: false)
  |> last()""",
        "status_distribution": """from(bucket: "${influxdb_bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "strategy_registry")
  |> filter(fn: (r) => r._field == "status")
  |> group(columns: ["status"])
  |> aggregateWindow(every: 1d, fn: count, createEmpty: false)
  |> last()""",
    },
}


if __name__ == "__main__":
    # Example usage and testing
    optimizer = QueryOptimizer()

    # Test aggregation suggestions
    print("Aggregation suggestions:")
    for duration in ["5m", "30m", "2h", "12h", "3d", "30d"]:
        delta = optimizer._parse_duration(duration)
        agg = optimizer.suggest_aggregation(delta)
        print(f"  {duration} -> {agg}")

    # Test query optimization
    print("\nOptimized query example:")
    query = """from(bucket: "chiseai")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "trades")
  |> filter(fn: (r) => r._field == "price")"""

    optimized = optimizer.optimize_query(query, timedelta(days=7))
    print(optimized)
