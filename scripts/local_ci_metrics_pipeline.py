#!/usr/bin/env python3
"""Local CI Metrics Pipeline - Orchestrates metrics collection, aggregation, and export.

This script provides a complete pipeline for:
1. Collecting metrics from various CI sources
2. Aggregating historical data by time windows
3. Computing trend analyses
4. Exporting results for Grafana dashboards

Usage:
    python scripts/local_ci_metrics_pipeline.py
    python scripts/local_ci_metrics_pipeline.py --collect-only
    python scripts/local_ci_metrics_pipeline.py --aggregate-only
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
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
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Local CI Metrics Pipeline - Complete metrics aggregation workflow"
    )
    parser.add_argument(
        "--input-dir",
        default="_bmad-output/ci",
        help="Input directory containing metrics files",
    )
    parser.add_argument(
        "--output-dir",
        default="_bmad-output/ci",
        help="Output directory for aggregated metrics",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only collect and store raw metrics, skip aggregation",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Only aggregate existing metrics, skip collection",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=30,
        help="Maximum age of metrics to include (default: 30)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    return parser.parse_args()


def collect_metrics(output_dir: Path, verbose: bool = False) -> list:
    """Collect and store raw metrics.

    This function:
    1. Runs the metrics exporter to generate fresh metrics
    2. Stores them to the output directory

    Args:
        output_dir: Directory to store collected metrics
        verbose: Enable verbose output

    Returns:
        List of collected MetricPoints
    """
    if verbose:
        print("Collecting metrics...")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Try to import and run the exporter
    try:
        from scripts.local_ci_metrics_exporter import emit_metrics

        metrics = emit_metrics(export_json=True, output_dir=str(output_dir))
        if verbose:
            print(f"  Collected metrics: test_count={metrics.test_count}")
    except Exception as e:
        if verbose:
            print(f"  Could not run exporter: {e}")
            print("  Using existing metrics files instead")

    # Load any collected metrics
    storage = MetricsStorage(str(output_dir))
    metrics = storage.load_metrics_from_dir(output_dir)

    if verbose:
        print(f"  Total metrics loaded: {len(metrics)}")

    return metrics


def aggregate_metrics(
    metrics: list,
    output_dir: Path,
    max_days: int = 30,
    verbose: bool = False,
) -> AggregatedMetricsOutput:
    """Aggregate metrics and compute trends.

    Args:
        metrics: List of metric points
        output_dir: Output directory for aggregated results
        max_days: Maximum age of metrics to include
        verbose: Enable verbose output

    Returns:
        AggregatedMetricsOutput with results
    """
    if verbose:
        print(f"Aggregating {len(metrics)} metrics...")

    # Filter by age if specified
    if max_days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=max_days)
        filtered = []
        for m in metrics:
            if m.timestamp:
                try:
                    dt = m.get_datetime()
                    if dt >= cutoff:
                        filtered.append(m)
                except Exception:
                    filtered.append(m)
        metrics = filtered

    if verbose:
        print(f"  Filtered to {len(metrics)} recent metrics")

    # Aggregate
    aggregator = MetricsAggregator()
    aggregator.add_metrics(metrics)
    output = aggregator.get_aggregated_output()
    output.source_metrics_count = len(metrics)

    # Save aggregated output
    output_path = output_dir / "metrics_aggregated.json"
    storage = MetricsStorage(str(output_dir))
    storage.save_aggregated(output, output_path)

    if verbose:
        print(f"  Saved aggregated metrics to: {output_path}")
        print(f"  Aggregation windows: {len(output.aggregation_windows)}")
        print(f"  Trends computed: {len(output.trends)}")

    return output


def generate_summary_report(output: AggregatedMetricsOutput) -> str:
    """Generate a human-readable summary report.

    Args:
        output: AggregatedMetricsOutput to summarize

    Returns:
        Summary report as string
    """
    lines = [
        "=" * 60,
        "Local CI Metrics - Aggregation Summary",
        "=" * 60,
        f"Generated: {output.generated_at}",
        f"Source metrics processed: {output.source_metrics_count}",
        "",
    ]

    # Summarize by window
    for window_name, aggregations in output.aggregation_windows.items():
        lines.append(f"Aggregation Window: {window_name.upper()}")
        lines.append("-" * 40)
        for agg in aggregations:
            period = agg.get("window_start", "unknown")
            if isinstance(period, str):
                period_str = period[:10] if len(period) > 10 else period
            else:
                period_str = str(period)[:10]
            lines.append(
                f"  {period_str}: "
                f"tests={agg.get('test_count_avg', 0):.0f} "
                f"cache_hit={agg.get('cache_hit_rate_avg', 0):.1f}% "
                f"duration={agg.get('duration_avg', 0):.1f}s"
            )
        lines.append("")

    # Summarize trends
    if output.trends:
        lines.append("TRENDS")
        lines.append("-" * 40)
        for trend in output.trends[:10]:
            metric = trend.get("metric_name", "unknown")
            direction = trend.get("direction", "stable")
            change = trend.get("percent_change", 0)
            window = trend.get("window", "?")
            r2 = trend.get("r_squared", 0)
            lines.append(
                f"  {metric} ({window}): {direction} {change:+.1f}% (R²={r2:.2f})"
            )
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if args.verbose:
        print(f"Input directory: {input_dir}")
        print(f"Output directory: {output_dir}")
        print(f"Max days: {args.max_days}")

    metrics: list = []

    # Collection phase
    if not args.aggregate_only:
        metrics = collect_metrics(output_dir, verbose=args.verbose)

    # Aggregation phase
    if not args.collect_only:
        if not metrics:
            # Load from history
            metrics = load_metrics_history(str(input_dir), args.max_days)

        if not metrics:
            print("No metrics found to aggregate.")
            return 1

        output = aggregate_metrics(
            metrics,
            output_dir,
            max_days=args.max_days,
            verbose=args.verbose,
        )

        # Print summary report
        report = generate_summary_report(output)
        if args.verbose:
            print()
            print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
