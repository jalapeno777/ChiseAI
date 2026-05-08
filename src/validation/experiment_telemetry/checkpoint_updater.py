#!/usr/bin/env python3
"""Checkpoint updater for experiment telemetry.

Reads experiment telemetry from Redis and updates the observation checkpoint file.

Redis Keys:
    - experiment:signals:control: List of control signal IDs
    - experiment:signals:treatment: List of treatment signal IDs
    - experiment:signal:{id}: Hash with signal data (signal_type, direction, entry_price, confluence_score)
    - experiment:outcome:{id}: Hash with outcome data (pnl, outcome, exit_price)
    - experiment:meta: Hash with experiment metadata

Excludes BOS/CHoCH signals per BL-BOS-CHOCH-001.

Usage:
    python checkpoint_updater.py --dry-run  # Preview changes
    python checkpoint_updater.py --update  # Write to checkpoint.md
    python checkpoint_updater.py --json     # Output JSON for automation
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Import Redis state functions
from tools.redis_state import redis_state_hgetall, redis_state_lrange

# Import statistical functions
from validation.statistical import two_proportion_z_test

# Redis key patterns
REDIS_KEYS = {
    "control_signals": "experiment:signals:control",
    "treatment_signals": "experiment:signals:treatment",
    "signal_prefix": "experiment:signal:",
    "outcome_prefix": "experiment:outcome:",
    "meta": "experiment:meta",
}

# Checkpoint file path (project_root / docs / observation / checkpoint.md)
CHECKPOINT_FILE = (
    Path(__file__).parent.parent.parent.parent
    / "docs"
    / "observation"
    / "ST-ICT-020-PART-B-checkpoint.md"
)

# Signal types no longer excluded (BL-BOS-CHOCH-001 lifted)
EXCLUDED_SIGNAL_TYPES: set[str] = set()


def calculate_cohens_h(proportion1: float, proportion2: float) -> float:
    """Calculate Cohen's h effect size between two proportions.

    Args:
        proportion1: First proportion (e.g., treatment win rate)
        proportion2: Second proportion (e.g., control win rate)

    Returns:
        Cohen's h effect size
    """
    if proportion1 <= 0 or proportion1 >= 1 or proportion2 <= 0 or proportion2 >= 1:
        return float("nan")
    return 2 * math.asin(math.sqrt(proportion1)) - 2 * math.asin(math.sqrt(proportion2))


def get_signal_ids(group: str) -> list[str]:
    """Get list of signal IDs for a group from Redis.

    Args:
        group: 'control' or 'treatment'

    Returns:
        List of signal ID strings
    """
    key = (
        REDIS_KEYS["control_signals"]
        if group == "control"
        else REDIS_KEYS["treatment_signals"]
    )
    return redis_state_lrange(key, 0, -1)


def get_signal_data(signal_id: str) -> dict[str, Any]:
    """Get signal data from Redis.

    Args:
        signal_id: The signal ID

    Returns:
        Dictionary with signal data or empty dict if not found
    """
    key = f"{REDIS_KEYS['signal_prefix']}{signal_id}"
    return redis_state_hgetall(key)


def get_outcome_data(signal_id: str) -> dict[str, Any]:
    """Get outcome data from Redis.

    Args:
        signal_id: The signal ID

    Returns:
        Dictionary with outcome data or empty dict if not found
    """
    key = f"{REDIS_KEYS['outcome_prefix']}{signal_id}"
    return redis_state_hgetall(key)


def get_experiment_meta() -> dict[str, Any]:
    """Get experiment metadata from Redis.

    Returns:
        Dictionary with experiment metadata
    """
    return redis_state_hgetall(REDIS_KEYS["meta"])


def calculate_group_metrics(signal_ids: list[str]) -> dict[str, Any]:
    """Calculate metrics for a signal group.

    Args:
        signal_ids: List of signal IDs in the group

    Returns:
        Dictionary with count, win_count, win_rate, avg_pnl
    """
    valid_signals = []

    for sig_id in signal_ids:
        signal = get_signal_data(sig_id)

        # Skip if signal not found or has excluded signal type
        if not signal:
            continue
        signal_type = signal.get("signal_type", "").lower()
        if signal_type in EXCLUDED_SIGNAL_TYPES:
            continue

        outcome = get_outcome_data(sig_id)
        if not outcome:
            continue

        valid_signals.append(
            {"signal_id": sig_id, "signal": signal, "outcome": outcome}
        )

    if not valid_signals:
        return {
            "count": 0,
            "win_count": 0,
            "win_rate": float("nan"),
            "avg_pnl": float("nan"),
            "pnl_sum": 0.0,
        }

    win_count = 0
    pnl_sum = 0.0

    for item in valid_signals:
        outcome = item["outcome"]
        # outcome field might be "win", "loss", "breakeven" or similar
        outcome_val = outcome.get("outcome", "").lower()
        if outcome_val == "win" or outcome_val == "profitable":
            win_count += 1

        # Get PnL
        pnl = outcome.get("pnl", 0)
        with suppress(TypeError, ValueError):
            pnl_sum += float(pnl)

    count = len(valid_signals)
    win_rate = win_count / count if count > 0 else float("nan")
    avg_pnl = pnl_sum / count if count > 0 else float("nan")

    return {
        "count": count,
        "win_count": win_count,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "pnl_sum": pnl_sum,
    }


def calculate_experiment_metrics() -> dict[str, Any]:
    """Calculate all experiment metrics from Redis.

    Returns:
        Dictionary with all metrics
    """
    # Get signal IDs for each group
    control_ids = get_signal_ids("control")
    treatment_ids = get_signal_ids("treatment")

    # Calculate group metrics (filters out bos/choch automatically)
    control_metrics = calculate_group_metrics(control_ids)
    treatment_metrics = calculate_group_metrics(treatment_ids)

    # Get experiment metadata
    meta = get_experiment_meta()

    # Calculate effect size and p-value
    effect_size = float("nan")
    p_value = float("nan")
    z_statistic = float("nan")

    if not math.isnan(control_metrics["win_rate"]) and not math.isnan(
        treatment_metrics["win_rate"]
    ):
        if control_metrics["win_rate"] > 0 and control_metrics["win_rate"] < 1:
            effect_size = calculate_cohens_h(
                treatment_metrics["win_rate"], control_metrics["win_rate"]
            )

        # Two-proportion z-test
        try:
            p_value, z_statistic = two_proportion_z_test(
                treatment_metrics["win_count"],
                treatment_metrics["count"],
                control_metrics["win_count"],
                control_metrics["count"],
            )
        except (ValueError, ZeroDivisionError):
            p_value = float("nan")
            z_statistic = float("nan")

    # Calculate days elapsed
    days_elapsed = 0
    start_date_str = meta.get("observation_start", "") or meta.get("start_date", "")
    if start_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            now = datetime.now(UTC)
            days_elapsed = (now - start_date).days
        except (ValueError, TypeError):
            days_elapsed = 0

    total_signals = control_metrics["count"] + treatment_metrics["count"]

    return {
        "days_elapsed": days_elapsed,
        "total_signals": total_signals,
        "control": control_metrics,
        "treatment": treatment_metrics,
        "effect_size": effect_size,
        "p_value": p_value,
        "z_statistic": z_statistic,
        "meta": meta,
    }


def format_metrics_for_markdown(metrics: dict[str, Any]) -> str:
    """Format metrics for the checkpoint markdown file.

    Args:
        metrics: Dictionary of experiment metrics

    Returns:
        Formatted markdown string for the metrics table
    """

    def fmt_val(val: Any) -> str:
        if isinstance(val, float):
            if math.isnan(val):
                return "N/A"
            return f"{val:.4f}"
        return str(val)

    control = metrics["control"]
    treatment = metrics["treatment"]

    markdown = f"""## Current Metrics

_Last updated: {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")} UTC_

| Metric                  | Value |
| ----------------------- | ----- |
| Days elapsed            | {metrics["days_elapsed"]}     |
| Signals collected       | {metrics["total_signals"]}     |
| Control win rate        | {fmt_val(control["win_rate"])}   |
| Treatment win rate      | {fmt_val(treatment["win_rate"])}   |
| Effect size (Cohen's h) | {fmt_val(metrics["effect_size"])} |
| Current p-value         | {fmt_val(metrics["p_value"])} |
"""
    return markdown


def format_metrics_for_json(metrics: dict[str, Any]) -> dict[str, Any]:
    """Format metrics for JSON output.

    Args:
        metrics: Dictionary of experiment metrics

    Returns:
        JSON-serializable dictionary
    """

    def sanitize(val: Any) -> Any:
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "days_elapsed": metrics["days_elapsed"],
        "total_signals": metrics["total_signals"],
        "control": {
            "count": metrics["control"]["count"],
            "win_count": metrics["control"]["win_count"],
            "win_rate": sanitize(metrics["control"]["win_rate"]),
            "avg_pnl": sanitize(metrics["control"]["avg_pnl"]),
        },
        "treatment": {
            "count": metrics["treatment"]["count"],
            "win_count": metrics["treatment"]["win_count"],
            "win_rate": sanitize(metrics["treatment"]["win_rate"]),
            "avg_pnl": sanitize(metrics["treatment"]["avg_pnl"]),
        },
        "effect_size_cohens_h": sanitize(metrics["effect_size"]),
        "p_value": sanitize(metrics["p_value"]),
        "z_statistic": sanitize(metrics["z_statistic"]),
    }


def update_checkpoint_file(metrics: dict[str, Any], dry_run: bool = False) -> bool:
    """Update the checkpoint markdown file with current metrics.

    Args:
        metrics: Dictionary of experiment metrics
        dry_run: If True, only print what would change

    Returns:
        True if successful, False otherwise
    """
    checkpoint_path = CHECKPOINT_FILE

    if not checkpoint_path.exists():
        print(f"Error: Checkpoint file not found at {checkpoint_path}", file=sys.stderr)
        return False

    try:
        content = checkpoint_path.read_text()
    except OSError as e:
        print(f"Error reading checkpoint file: {e}", file=sys.stderr)
        return False

    # Find the Current Metrics section and replace it
    marker_start = "## Current Metrics"
    marker_end = "## Next Checkpoint"

    start_idx = content.find(marker_start)
    end_idx = content.find(marker_end)

    if start_idx == -1 or end_idx == -1:
        print(
            "Error: Could not find Current Metrics section in checkpoint file",
            file=sys.stderr,
        )
        return False

    new_metrics_section = format_metrics_for_markdown(metrics)

    # Reconstruct the file content
    new_content = content[:start_idx] + new_metrics_section + "\n\n" + content[end_idx:]

    if dry_run:
        print("=== Dry run - would update checkpoint file with: ===")
        print(new_metrics_section)
        print("===")
        return True

    try:
        checkpoint_path.write_text(new_content)
        print(f"Successfully updated checkpoint file: {checkpoint_path}")
        return True
    except OSError as e:
        print(f"Error writing checkpoint file: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update experiment telemetry checkpoint"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing to file"
    )
    parser.add_argument(
        "--update", action="store_true", help="Write updated metrics to checkpoint file"
    )
    parser.add_argument("--json", action="store_true", help="Output metrics as JSON")

    args = parser.parse_args()

    if not any([args.dry_run, args.update, args.json]):
        parser.print_help()
        sys.exit(1)

    # Calculate metrics from Redis
    metrics = calculate_experiment_metrics()

    if args.json:
        json_output = format_metrics_for_json(metrics)
        print(json.dumps(json_output, indent=2))

    if args.dry_run:
        update_checkpoint_file(metrics, dry_run=True)

    if args.update:
        success = update_checkpoint_file(metrics, dry_run=False)
        sys.exit(0 if success else 1)

    # If only json, we're done
    if args.json and not args.dry_run and not args.update:
        sys.exit(0)

    # For dry-run without json, show formatted metrics
    if args.dry_run and not args.json:
        print("\n=== Current Metrics ===")
        print(f"Days elapsed: {metrics['days_elapsed']}")
        print(f"Total signals: {metrics['total_signals']}")
        print(
            f"Control: {metrics['control']['count']} signals, win rate: {metrics['control']['win_rate']}"
        )
        print(
            f"Treatment: {metrics['treatment']['count']} signals, win rate: {metrics['treatment']['win_rate']}"
        )
        print(f"Effect size (Cohen's h): {metrics['effect_size']}")
        print(f"P-value: {metrics['p_value']}")
        print()


if __name__ == "__main__":
    main()
