#!/usr/bin/env python3
"""Local CI Metrics Aggregator - Aggregates historical metrics and computes trends.

This script:
- Reads metrics from _bmad-output/ci/metrics.json
- Aggregates historical data by day/week/month
- Computes trends (cache hit rate trends, duration trends, etc.)
- Exports aggregated data to _bmad-output/ci/metrics_aggregated.json

Usage:
    python scripts/local_ci_metrics_aggregator.py
    python scripts/local_ci_metrics_aggregator.py --input /path/to/metrics.json
    python scripts/local_ci_metrics_aggregator.py --output /path/to/aggregated.json
    python scripts/local_ci_metrics_aggregator.py --max-days 7
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
_script_dir = Path(__file__).parent.resolve()
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.ci.metrics import (
    AggregatedMetricsOutput,
    AggregationWindow,
    MetricsAggregator,
    MetricsStorage,
    load_metrics_history,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Local CI Metrics Aggregator - Aggregate historical metrics and compute trends"
    )
    parser.add_argument(
        "--input",
        "-i",
        default="_bmad-output/ci/metrics.json",
        help="Input metrics JSON file (default: _bmad-output/ci/metrics.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="_bmad-output/ci/metrics_aggregated.json",
        help="Output aggregated JSON file (default: _bmad-output/ci/metrics_aggregated.json)",
    )
    parser.add_argument(
        "--max-days",
        "-d",
        type=int,
        default=30,
        help="Maximum age of metrics to include in days (default: 30)",
    )
    parser.add_argument(
        "--window",
        "-w",
        choices=["day", "week", "month"],
        help="Only compute aggregation for specific window",
    )
    parser.add_argument(
        "--pretty",
        "-p",
        action="store_true",
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    return parser.parse_args()


def load_metrics(input_path: str, max_days: int) -> list:
    """Load metrics from input file or history.

    Args:
        input_path: Path to metrics JSON file
        max_days: Maximum age of metrics

    Returns:
        List of MetricPoints
    """
    storage = MetricsStorage()

    # Try to load from input path
    input_file = Path(input_path)
    if input_file.exists():
        metrics = storage.load_metrics(input_path)
        if metrics:
            return metrics

    # Fall back to loading from directory history
    if input_file.parent.exists():
        metrics = load_metrics_history(str(input_file.parent), max_days)
        if metrics:
            return metrics

    return []


def aggregate_metrics(
    metrics: list,
    window: str | None = None,
    verbose: bool = False,
) -> AggregatedMetricsOutput:
    """Aggregate metrics and compute trends.

    Args:
        metrics: List of MetricPoints
        window: Specific window to aggregate, or None for all
        verbose: Enable verbose output

    Returns:
        AggregatedMetricsOutput with results
    """
    aggregator = MetricsAggregator()
    aggregator.add_metrics(metrics)

    if verbose:
        print(f"Loaded {len(metrics)} metric points")

    output = AggregatedMetricsOutput(
        generated_at=metrics[0].timestamp if metrics else "",
    )
    output.source_metrics_count = len(metrics)

    windows_to_process = (
        [AggregationWindow(window)]
        if window
        else [
            AggregationWindow.DAILY,
            AggregationWindow.WEEKLY,
            AggregationWindow.MONTHLY,
        ]
    )

    for win in windows_to_process:
        aggregated = aggregator.aggregate(win)
        if aggregated:
            output.aggregation_windows[win.value] = [
                agg.to_dict() for agg in aggregated
            ]
            if verbose:
                print(f"  {win.value}: {len(aggregated)} aggregation periods")

        trends = aggregator.compute_trends(win)
        if trends:
            for trend in trends:
                trend_dict = trend.to_dict()
                trend_dict["window"] = win.value
                output.trends.append(trend_dict)
            if verbose:
                print(f"  {win.value} trends: {len(trends)} computed")

    return output


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    if args.verbose:
        print(f"Loading metrics from: {args.input}")
        print(f"Max days: {args.max_days}")

    metrics = load_metrics(args.input, args.max_days)

    if not metrics:
        print("No metrics found. Ensure metrics.json exists or run CI first.")
        return 1

    if args.verbose:
        print(f"Loaded {len(metrics)} metrics")

    output = aggregate_metrics(
        metrics,
        window=args.window,
        verbose=args.verbose,
    )

    # Save aggregated output
    storage = MetricsStorage()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if storage.save_aggregated(output, output_path):
        print(f"Aggregated metrics saved to: {output_path}")
    else:
        print("Failed to save aggregated metrics", file=sys.stderr)
        return 1

    # Print summary
    print("\nSummary:")
    print(f"  Source metrics: {output.source_metrics_count}")
    print(f"  Aggregation windows: {len(output.aggregation_windows)}")
    print(f"  Trends computed: {len(output.trends)}")

    # Show trends if verbose
    if args.verbose and output.trends:
        print("\nTop Trends:")
        for trend in output.trends[:5]:
            direction = trend.get("direction", "stable")
            metric = trend.get("metric_name", "unknown")
            change = trend.get("percent_change", 0)
            r2 = trend.get("r_squared", 0)
            print(
                f"  {metric} ({trend.get('window', '?')}): {direction} {change:+.1f}% (R²={r2:.2f})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
