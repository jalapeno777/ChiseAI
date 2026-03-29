#!/usr/bin/env python3
"""
Autocog Weekly Summary Generator

Reads the last 7 days of autocog cycle artifacts and self-assessment scores,
compiles a summary, and outputs both JSON and markdown reports.

Usage:
    python scripts/autocog_weekly_summary.py [--days 7] [--output-dir _bmad-output/autocog/summaries]
"""

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Paths
CYCLES_DIR = Path("_bmad-output/autocog/cycles")
SELF_ASSESSMENTS_DIR = Path("docs/governance/self_assessments")
OUTPUT_DIR = Path("_bmad-output/autocog/summaries")


@dataclass
class CycleSummary:
    """Summary statistics for autocog cycles."""

    total_cycles: int = 0
    completed_cycles: int = 0
    failed_cycles: int = 0
    by_mode: dict = field(default_factory=dict)
    belief_conflicts_detected: int = 0
    belief_revisions_made: int = 0
    constitution_violations: int = 0
    autonomy_changes: int = 0
    autonomy_level_distribution: dict = field(default_factory=dict)


@dataclass
class ExperimentSummary:
    """Summary of experiments run."""

    total_experiments: int = 0
    experiments_by_outcome: dict = field(default_factory=dict)
    promoted: int = 0
    rejected: int = 0


@dataclass
class SelfAssessmentTrend:
    """Self-assessment score trend over the period."""

    start_score: float | None = None
    end_score: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    min_score: float = 1.0
    max_score: float = 0.0
    avg_score: float = 0.0
    score_count: int = 0
    dimension_averages: dict = field(default_factory=dict)


@dataclass
class AnomalyReport:
    """Detected anomalies and errors."""

    skip_rate_alerts: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class WeeklySummary:
    """Complete weekly summary."""

    generated_at: str = ""
    period_start: str = ""
    period_end: str = ""
    cycles: CycleSummary = field(default_factory=CycleSummary)
    experiments: ExperimentSummary = field(default_factory=ExperimentSummary)
    self_assessment_trend: SelfAssessmentTrend = field(
        default_factory=SelfAssessmentTrend
    )
    anomalies: AnomalyReport = field(default_factory=AnomalyReport)
    recommendations: list = field(default_factory=list)


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def infer_cycle_mode(cycle_data: dict) -> str:
    """
    Infer the cycle mode from cycle data.

    Modes are derived from job context. If a cycle has experiments_run > 0,
    it's likely an improvement cycle. Belief conflicts indicate belief_consistency.
    Constitution checks are periodic. Calibration is weekly.

    Returns one of: full, belief_consistency, improvement, calibration, constitution_audit
    """
    # Check for explicit mode field first (future-proofing)
    if "mode" in cycle_data:
        return cycle_data["mode"]

    # Infer from metrics
    metrics = cycle_data.get("metrics", {})

    # Belief consistency cycles have belief conflicts
    if cycle_data.get("belief_conflicts", 0) > 0:
        return "belief_consistency"

    # Constitution audit cycles check constitution violations
    if cycle_data.get("constitution_violations", 0) > 0:
        return "constitution_audit"

    # Improvement cycles run experiments
    if cycle_data.get("experiments_run", 0) > 0:
        return "improvement"

    # Skip rate alerts suggest regular full cycles
    if metrics.get("skip_rate_check", {}).get("alert_triggered", False):
        return "full"

    # Default mode based on autonomy level check
    autonomy_before = cycle_data.get("autonomy_level_before", "unknown")
    autonomy_after = cycle_data.get("autonomy_level_after", "unknown")
    if autonomy_before != autonomy_after:
        return "autonomy_tune"

    return "full"


def load_cycles(days: int = 7) -> list:
    """Load cycle artifacts from the last N days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    cycles = []

    if not CYCLES_DIR.exists():
        return cycles

    for cycle_file in sorted(CYCLES_DIR.glob("autocog-*.json")):
        try:
            with open(cycle_file) as f:
                cycle_data = json.load(f)

            started_at = cycle_data.get("started_at")
            if started_at:
                cycle_time = parse_timestamp(started_at)
                if cycle_time >= cutoff:
                    cycles.append(cycle_data)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load {cycle_file}: {e}")

    return cycles


def load_self_assessments(days: int = 7) -> list:
    """Load self-assessment files from the last N days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    assessments = []

    if not SELF_ASSESSMENTS_DIR.exists():
        return assessments

    for sa_file in sorted(SELF_ASSESSMENTS_DIR.glob("self_assessment_*.json")):
        try:
            with open(sa_file) as f:
                sa_data = json.load(f)

            created_at = sa_data.get("created_at")
            if created_at:
                sa_time = parse_timestamp(created_at)
                if sa_time >= cutoff:
                    assessments.append(sa_data)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load {sa_file}: {e}")

    return assessments


def analyze_cycles(cycles: list) -> tuple[CycleSummary, AnomalyReport]:
    """Analyze cycles and return summary statistics."""
    summary = CycleSummary()
    anomalies = AnomalyReport()

    summary.total_cycles = len(cycles)

    for cycle in cycles:
        status = cycle.get("status", "unknown")
        if status == "completed":
            summary.completed_cycles += 1
        elif status == "failed":
            summary.failed_cycles += 1

        # Mode analysis
        mode = infer_cycle_mode(cycle)
        summary.by_mode[mode] = summary.by_mode.get(mode, 0) + 1

        # Belief analysis
        summary.belief_conflicts_detected += cycle.get("belief_conflicts", 0)
        summary.belief_revisions_made += cycle.get("belief_revisions", 0)

        # Constitution
        summary.constitution_violations += cycle.get("constitution_violations", 0)

        # Autonomy changes
        autonomy_before = cycle.get("autonomy_level_before", "unknown")
        autonomy_after = cycle.get("autonomy_level_after", "unknown")
        if autonomy_before != autonomy_after:
            summary.autonomy_changes += 1

        # Track autonomy level distribution
        summary.autonomy_level_distribution[autonomy_after] = (
            summary.autonomy_level_distribution.get(autonomy_after, 0) + 1
        )

        # Check for anomalies
        metrics = cycle.get("metrics", {})

        # Skip rate alerts
        skip_check = metrics.get("skip_rate_check", {})
        if skip_check.get("alert_triggered", False):
            anomalies.skip_rate_alerts += 1
            anomalies.warnings.append(
                f"Cycle {cycle.get('run_id')}: {skip_check.get('alert_message', 'High skip rate detected')}"
            )

        # Error status
        if cycle.get("self_assessment_status") == "error":
            anomalies.errors.append(
                f"Cycle {cycle.get('run_id')}: Self-assessment error"
            )

    return summary, anomalies


def analyze_experiments(cycles: list) -> ExperimentSummary:
    """Analyze experiments from cycles."""
    summary = ExperimentSummary()

    for cycle in cycles:
        experiments_run = cycle.get("experiments_run", 0)
        if experiments_run > 0:
            summary.total_experiments += experiments_run

            promotions = cycle.get("promotions", 0)
            rejections = cycle.get("rejections", 0)
            summary.promoted += promotions
            summary.rejected += rejections

            # Determine outcome
            if promotions > 0 and rejections == 0:
                outcome = "promoted"
            elif rejections > 0 and promotions == 0:
                outcome = "rejected"
            elif promotions > 0 and rejections > 0:
                outcome = "mixed"
            else:
                outcome = "pending"

            summary.experiments_by_outcome[outcome] = (
                summary.experiments_by_outcome.get(outcome, 0) + experiments_run
            )

    return summary


def analyze_self_assessments(assessments: list) -> SelfAssessmentTrend:
    """Analyze self-assessment score trends."""
    trend = SelfAssessmentTrend()

    if not assessments:
        return trend

    # Sort by created_at
    sorted_assessments = sorted(assessments, key=lambda x: x.get("created_at", ""))

    scores = []
    dimension_totals = {}
    dimension_counts = {}

    for sa in sorted_assessments:
        score = sa.get("overall_score")
        if score is not None:
            scores.append(score)

            # Track start/end
            if trend.start_score is None:
                trend.start_score = score
                trend.start_date = sa.get("assessment_date")

            trend.end_score = score
            trend.end_date = sa.get("assessment_date")

            # Track min/max
            trend.min_score = min(trend.min_score, score)
            trend.max_score = max(trend.max_score, score)

            # Dimension averages
            dimensions = sa.get("dimensions", {})
            for dim_name, dim_value in dimensions.items():
                dimension_totals[dim_name] = (
                    dimension_totals.get(dim_name, 0) + dim_value
                )
                dimension_counts[dim_name] = dimension_counts.get(dim_name, 0) + 1

    trend.score_count = len(scores)
    trend.avg_score = sum(scores) / len(scores) if scores else 0.0

    # Calculate dimension averages
    for dim_name in dimension_totals:
        trend.dimension_averages[dim_name] = (
            dimension_totals[dim_name] / dimension_counts[dim_name]
        )

    return trend


def generate_recommendations(
    cycles_summary: CycleSummary,
    experiments: ExperimentSummary,
    assessments: SelfAssessmentTrend,
    anomalies: AnomalyReport,
) -> list:
    """Generate recommendations based on analysis."""
    recommendations = []

    # Skip rate recommendations
    if anomalies.skip_rate_alerts > 0:
        recommendations.append(
            f"Address high skip rate: {anomalies.skip_rate_alerts} alert(s) triggered. "
            "Consider reviewing candidate generation or threshold settings."
        )

    # Experiment recommendations
    if experiments.total_experiments == 0:
        recommendations.append(
            "No experiments run this week. Enable experimental learning mode "
            "to test hypothesis-driven improvements."
        )
    elif experiments.promoted == 0 and experiments.rejected > 0:
        recommendations.append(
            f"All {experiments.rejected} experiments were rejected. "
            "Review rejection reasons and adjust experimental parameters."
        )

    # Belief conflict recommendations
    if cycles_summary.belief_conflicts_detected > 10:
        recommendations.append(
            f"High belief conflicts ({cycles_summary.belief_conflicts_detected}). "
            "Run more belief_consistency cycles to resolve."
        )

    # Self-assessment recommendations
    if assessments.score_count > 0:
        if assessments.end_score < assessments.start_score - 0.1:
            recommendations.append(
                f"Self-assessment score declined from {assessments.start_score:.2f} "
                f"to {assessments.end_score:.2f}. Investigate root causes."
            )
        elif assessments.end_score > assessments.start_score + 0.1:
            recommendations.append(
                f"Self-assessment score improved from {assessments.start_score:.2f} "
                f"to {assessments.end_score:.2f}. Continue current practices."
            )

        if assessments.min_score < 0.5:
            recommendations.append(
                f"Minimum self-assessment score of {assessments.min_score:.2f} detected. "
                "Review infrastructure health and memory systems."
            )

    # Autonomy recommendations
    if cycles_summary.autonomy_changes == 0:
        recommendations.append(
            "No autonomy level changes this week. Consider reviewing "
            "if autonomy tuning criteria need adjustment."
        )

    # Default recommendation if none apply
    if not recommendations:
        recommendations.append("Continue autonomous monitoring and trend tracking.")

    return recommendations


def compile_summary(days: int = 7) -> WeeklySummary:
    """Compile the complete weekly summary."""
    cycles = load_cycles(days)
    assessments = load_self_assessments(days)

    cycles_summary, anomalies = analyze_cycles(cycles)
    experiments_summary = analyze_experiments(cycles)
    assessments_trend = analyze_self_assessments(assessments)
    recommendations = generate_recommendations(
        cycles_summary, experiments_summary, assessments_trend, anomalies
    )

    # Calculate period
    now = datetime.now(UTC)
    period_end = now.strftime("%Y-%m-%d")
    period_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    summary = WeeklySummary(
        generated_at=now.isoformat(),
        period_start=period_start,
        period_end=period_end,
        cycles=cycles_summary,
        experiments=experiments_summary,
        self_assessment_trend=assessments_trend,
        anomalies=anomalies,
        recommendations=recommendations,
    )

    return summary


def summary_to_json(summary: WeeklySummary) -> dict:
    """Convert summary to JSON-serializable dict."""
    result = {
        "generated_at": summary.generated_at,
        "period": {"start": summary.period_start, "end": summary.period_end},
        "cycles": {
            "total": summary.cycles.total_cycles,
            "completed": summary.cycles.completed_cycles,
            "failed": summary.cycles.failed_cycles,
            "by_mode": summary.cycles.by_mode,
            "belief_conflicts_detected": summary.cycles.belief_conflicts_detected,
            "belief_revisions_made": summary.cycles.belief_revisions_made,
            "constitution_violations": summary.cycles.constitution_violations,
            "autonomy_changes": summary.cycles.autonomy_changes,
            "autonomy_level_distribution": summary.cycles.autonomy_level_distribution,
        },
        "experiments": {
            "total_run": summary.experiments.total_experiments,
            "by_outcome": summary.experiments.experiments_by_outcome,
            "promoted": summary.experiments.promoted,
            "rejected": summary.experiments.rejected,
        },
        "self_assessment_trend": {
            "start_score": summary.self_assessment_trend.start_score,
            "end_score": summary.self_assessment_trend.end_score,
            "start_date": summary.self_assessment_trend.start_date,
            "end_date": summary.self_assessment_trend.end_date,
            "min_score": summary.self_assessment_trend.min_score,
            "max_score": summary.self_assessment_trend.max_score,
            "avg_score": summary.self_assessment_trend.avg_score,
            "sample_count": summary.self_assessment_trend.score_count,
            "dimension_averages": summary.self_assessment_trend.dimension_averages,
        },
        "anomalies": {
            "skip_rate_alerts": summary.anomalies.skip_rate_alerts,
            "errors": summary.anomalies.errors,
            "warnings": summary.anomalies.warnings,
        },
        "recommendations": summary.recommendations,
    }
    return result


def summary_to_markdown(summary: WeeklySummary) -> str:
    """Convert summary to human-readable markdown."""
    sa = summary.self_assessment_trend
    cyc = summary.cycles
    exp = summary.experiments
    ano = summary.anomalies

    # Calculate score change
    score_change = ""
    if sa.start_score is not None and sa.end_score is not None:
        delta = sa.end_score - sa.start_score
        sign = "+" if delta >= 0 else ""
        score_change = f" ({sign}{delta:.2f})"

    # Format score values safely
    start_score_str = f"{sa.start_score:.2f}" if sa.start_score is not None else "N/A"
    end_score_str = f"{sa.end_score:.2f}" if sa.end_score is not None else "N/A"
    avg_score_str = f"{sa.avg_score:.2f}" if sa.score_count > 0 else "N/A"
    min_score_str = f"{sa.min_score:.2f}" if sa.score_count > 0 else "N/A"
    max_score_str = f"{sa.max_score:.2f}" if sa.score_count > 0 else "N/A"

    md = f"""# Autocog Weekly Summary

**Period:** {summary.period_start} to {summary.period_end}  
**Generated:** {summary.generated_at}

---

## Cycle Overview

| Metric | Value |
|--------|-------|
| Total Cycles | {cyc.total_cycles} |
| Completed | {cyc.completed_cycles} |
| Failed | {cyc.failed_cycles} |
| Belief Conflicts Detected | {cyc.belief_conflicts_detected} |
| Belief Revisions Made | {cyc.belief_revisions_made} |
| Constitution Violations | {cyc.constitution_violations} |
| Autonomy Changes | {cyc.autonomy_changes} |

### Cycles by Mode

"""

    for mode, count in sorted(cyc.by_mode.items()):
        md += f"- **{mode}**: {count}\n"

    md += """
### Autonomy Level Distribution

"""
    for level, count in sorted(cyc.autonomy_level_distribution.items()):
        md += f"- **{level}**: {count}\n"

    md += f"""

## Self-Assessment Trend

| Metric | Value |
|--------|-------|
| Start Score | {start_score_str} |
| End Score | {end_score_str}{score_change} |
| Average Score | {avg_score_str} |
| Min Score | {min_score_str} |
| Max Score | {max_score_str} |
| Sample Count | {sa.score_count} |

### Dimension Averages

"""

    for dim, avg in sorted(sa.dimension_averages.items()):
        md += f"- **{dim}**: {avg:.2f}\n"

    md += f"""

## Experiments

| Metric | Value |
|--------|-------|
| Total Experiments Run | {exp.total_experiments} |
| Promoted | {exp.promoted} |
| Rejected | {exp.rejected} |

"""

    if exp.experiments_by_outcome:
        md += "### By Outcome\n\n"
        for outcome, count in sorted(exp.experiments_by_outcome.items()):
            md += f"- **{outcome}**: {count}\n"
        md += "\n"

    md += f"""## Anomalies & Alerts

| Type | Count |
|------|-------|
| Skip Rate Alerts | {ano.skip_rate_alerts} |
| Errors | {len(ano.errors)} |
| Warnings | {len(ano.warnings)} |

"""

    if ano.errors:
        md += "### Errors\n\n"
        for error in ano.errors:
            md += f"- {error}\n"
        md += "\n"

    if ano.warnings:
        md += "### Warnings\n\n"
        for warning in ano.warnings[:10]:  # Limit to first 10
            md += f"- {warning}\n"
        if len(ano.warnings) > 10:
            md += f"- ... and {len(ano.warnings) - 10} more\n"
        md += "\n"

    md += """## Recommendations

"""
    for i, rec in enumerate(summary.recommendations, 1):
        md += f"{i}. {rec}\n"

    md += """

---
*Generated by autocog_weekly_summary.py*
"""

    return md


def write_outputs(summary: WeeklySummary, output_dir: Path) -> tuple[Path, Path]:
    """Write JSON and markdown outputs to files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filenames with timestamp
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"weekly_summary_{timestamp}.json"
    md_path = output_dir / f"weekly_summary_{timestamp}.md"

    # Also write to latest pointers
    json_latest = output_dir / "weekly_summary_latest.json"
    md_latest = output_dir / "weekly_summary_latest.md"

    # Write JSON
    json_data = summary_to_json(summary)
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    with open(json_latest, "w") as f:
        json.dump(json_data, f, indent=2)

    # Write Markdown
    md_content = summary_to_markdown(summary)
    with open(md_path, "w") as f:
        f.write(md_content)
    with open(md_latest, "w") as f:
        f.write(md_content)

    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate autocog weekly summary report"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to look back (default: 7)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help=f"Output directory (default: {OUTPUT_DIR})",
    )

    args = parser.parse_args()

    print(f"Generating weekly summary for last {args.days} days...")

    summary = compile_summary(days=args.days)
    json_path, md_path = write_outputs(summary, Path(args.output_dir))

    print("\nSummary generated successfully!")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print("\nStatistics:")
    print(f"  Cycles analyzed: {summary.cycles.total_cycles}")
    print(f"  Self-assessments: {summary.self_assessment_trend.score_count}")
    print(f"  Experiments: {summary.experiments.total_experiments}")
    print(f"  Recommendations: {len(summary.recommendations)}")

    return 0


if __name__ == "__main__":
    exit(main())
