#!/usr/bin/env python3
"""Daily trends rollup and reflection generation script.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Computes 24h/7d/30d trend rollups using TrendRollupEngine and generates
daily reflection artifacts with bottleneck analysis and remediation recommendations.

Usage:
    python3 scripts/evaluation/run_daily_trends.py
    python3 scripts/evaluation/run_daily_trends.py --dry-run
    python3 scripts/evaluation/run_daily_trends.py --date 2026-03-02

Output:
    - _bmad-output/brain-eval/trends/24h-{timestamp}.json
    - _bmad-output/brain-eval/trends/7d-{timestamp}.json
    - _bmad-output/brain-eval/trends/30d-{timestamp}.json
    - _bmad-output/brain-eval/reflections/daily/{date}.json

Exit codes:
    0: Success
    1: Failure
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

try:
    from src.evaluation.trend_rollups import TrendRollup, TrendRollupEngine
except ImportError as e:
    print(f"ERROR: Failed to import TrendRollupEngine: {e}", file=sys.stderr)
    sys.exit(1)

try:
    from governance.reflection import (
        AutomationTarget,
        KPISnapshot,
        Priority,
        ReflectionArtifact,
        ReflectionType,
        RootCause,
        RootCauseCategory,
        create_reflection_artifact,
    )
except ImportError as e:
    print(f"ERROR: Failed to import reflection artifacts: {e}", file=sys.stderr)
    sys.exit(1)

try:
    import redis
except ImportError:
    redis = None  # type: ignore


# Configure logging
logger = logging.getLogger("run_daily_trends")


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration.

    Args:
        verbose: If True, enable DEBUG level logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_redis_client() -> Any:
    """Get Redis client if available.

    Returns:
        Redis client or None if unavailable
    """
    if redis is None:
        logger.warning("Redis package not available, running without Redis")
        return None

    try:
        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            decode_responses=True,
        )
        client.ping()
        logger.info("Connected to Redis at host.docker.internal:6380")
        return client
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        return None


@dataclass
class BottleneckAnalysis:
    """Analysis of a recurring bottleneck."""

    name: str
    fingerprint: str
    occurrence_count: int
    impact_scores: dict[str, int] = field(default_factory=dict)
    recommended_actions: list[str] = field(default_factory=list)
    priority: Priority = Priority.MEDIUM


@dataclass
class DailyReflectionOutput:
    """Output structure for daily reflection."""

    date: str
    computed_at: str
    rollup_summaries: dict[str, dict[str, Any]]
    top_bottlenecks: list[dict[str, Any]]
    estimated_impacts: dict[str, int]
    recommended_stories: list[dict[str, Any]]
    data_quality_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "date": self.date,
            "computed_at": self.computed_at,
            "rollup_summaries": self.rollup_summaries,
            "top_bottlenecks": self.top_bottlenecks,
            "estimated_impacts": self.estimated_impacts,
            "recommended_stories": self.recommended_stories,
            "data_quality_notes": self.data_quality_notes,
        }


def extract_bottlenecks_from_rollups(
    rollups: dict[str, TrendRollup], limit: int = 3
) -> list[BottleneckAnalysis]:
    """Extract top recurring bottlenecks from trend rollups.

    Args:
        rollups: Dictionary of window name to TrendRollup
        limit: Maximum number of bottlenecks to return

    Returns:
        List of BottleneckAnalysis objects
    """
    bottlenecks: list[BottleneckAnalysis] = []

    # Use 24h rollup for primary bottleneck analysis
    rollup_24h = rollups.get("24h")
    if not rollup_24h:
        logger.warning("No 24h rollup available for bottleneck analysis")
        return bottlenecks

    kpis = rollup_24h.kpis

    # Analyze recurring issue rate
    recurring_rate = kpis.get("recurring_issue_rate", 0.0)
    if recurring_rate > 0.1:  # More than 10%
        bottlenecks.append(
            BottleneckAnalysis(
                name="High Recurring Issue Rate",
                fingerprint="recurring_issue_rate",
                occurrence_count=int(recurring_rate * 100),
                impact_scores={
                    "throughput": 4,
                    "efficiency": 3,
                    "accuracy": 2,
                    "reliability": 5,
                },
                recommended_actions=[
                    "Investigate root cause of recurring issues",
                    "Implement fingerprint-based deduplication",
                    "Review CI/CD pipeline for flaky tests",
                ],
                priority=Priority.HIGH,
            )
        )

    # Analyze median time lost
    median_time = kpis.get("median_time_lost_minutes", 0.0)
    if median_time > 30:  # More than 30 minutes
        bottlenecks.append(
            BottleneckAnalysis(
                name="High Time Lost to Issues",
                fingerprint="median_time_lost",
                occurrence_count=int(median_time),
                impact_scores={
                    "throughput": 5,
                    "efficiency": 4,
                    "accuracy": 1,
                    "reliability": 3,
                },
                recommended_actions=[
                    "Implement faster failure detection",
                    "Add automated rollback mechanisms",
                    "Improve issue triage process",
                ],
                priority=Priority.HIGH,
            )
        )

    # Analyze unresolved issue age
    unresolved_age = kpis.get("unresolved_issue_age", 0.0)
    if unresolved_age > 24:  # More than 24 hours average
        bottlenecks.append(
            BottleneckAnalysis(
                name="Aging Unresolved Issues",
                fingerprint="unresolved_issue_age",
                occurrence_count=int(unresolved_age),
                impact_scores={
                    "throughput": 3,
                    "efficiency": 4,
                    "accuracy": 3,
                    "reliability": 4,
                },
                recommended_actions=[
                    "Review stale issue backlog",
                    "Implement issue escalation policy",
                    "Add reminder system for aging issues",
                ],
                priority=Priority.MEDIUM,
            )
        )

    # Analyze top fingerprint repeat count
    top_repeat = kpis.get("top_fingerprint_repeat_count", 0)
    if top_repeat > 3:  # Same issue appearing more than 3 times
        bottlenecks.append(
            BottleneckAnalysis(
                name=f"Repeated Fingerprint (x{top_repeat})",
                fingerprint="top_fingerprint",
                occurrence_count=top_repeat,
                impact_scores={
                    "throughput": 4,
                    "efficiency": 3,
                    "accuracy": 2,
                    "reliability": 5,
                },
                recommended_actions=[
                    "Deep dive into fingerprint root cause",
                    "Implement permanent fix",
                    "Add monitoring for this pattern",
                ],
                priority=Priority.HIGH,
            )
        )

    # Analyze fix reopen rate
    fix_reopen = kpis.get("fix_reopen_rate", 0.0)
    if fix_reopen > 0.05:  # More than 5%
        bottlenecks.append(
            BottleneckAnalysis(
                name="High Fix Reopen Rate",
                fingerprint="fix_reopen_rate",
                occurrence_count=int(fix_reopen * 100),
                impact_scores={
                    "throughput": 4,
                    "efficiency": 5,
                    "accuracy": 3,
                    "reliability": 5,
                },
                recommended_actions=[
                    "Review fix verification process",
                    "Add regression tests for reopened issues",
                    "Implement fix validation gates",
                ],
                priority=Priority.HIGH,
            )
        )

    # Sort by priority and limit
    priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
    bottlenecks.sort(key=lambda b: priority_order.get(b.priority, 3))

    return bottlenecks[:limit]


def compute_aggregate_impact_scores(
    bottlenecks: list[BottleneckAnalysis],
) -> dict[str, int]:
    """Compute aggregate impact scores from bottlenecks.

    Args:
        bottlenecks: List of BottleneckAnalysis objects

    Returns:
        Dictionary mapping impact area to score (1-5)
    """
    if not bottlenecks:
        return {
            "throughput": 1,
            "efficiency": 1,
            "accuracy": 1,
            "reliability": 1,
        }

    # Aggregate scores (use max for each category)
    aggregate = {
        "throughput": 1,
        "efficiency": 1,
        "accuracy": 1,
        "reliability": 1,
    }

    for bottleneck in bottlenecks:
        for key, score in bottleneck.impact_scores.items():
            if key in aggregate:
                aggregate[key] = max(aggregate[key], score)

    return aggregate


def generate_recommended_stories(
    bottlenecks: list[BottleneckAnalysis], date_str: str
) -> list[dict[str, Any]]:
    """Generate recommended remediation stories from bottlenecks.

    Args:
        bottlenecks: List of BottleneckAnalysis objects
        date_str: Date string for story ID generation

    Returns:
        List of recommended story dictionaries
    """
    stories: list[dict[str, Any]] = []

    for i, bottleneck in enumerate(bottlenecks, 1):
        story = {
            "story_id": f"ST-REMEDIAL-{date_str.replace('-', '')}-{i:02d}",
            "title": f"Address {bottleneck.name}",
            "priority": bottleneck.priority.value,
            "rationale": f"Based on trend analysis: {bottleneck.occurrence_count} occurrences detected",
            "recommended_actions": bottleneck.recommended_actions,
            "impact_areas": list(bottleneck.impact_scores.keys()),
            "estimated_effort": (
                "medium" if bottleneck.priority == Priority.HIGH else "low"
            ),
        }
        stories.append(story)

    return stories


def create_daily_reflection_artifact(
    rollups: dict[str, TrendRollup],
    bottlenecks: list[BottleneckAnalysis],
    impact_scores: dict[str, int],
    recommended_stories: list[dict[str, Any]],
    date_str: str,
) -> ReflectionArtifact:
    """Create a ReflectionArtifact from daily analysis.

    Args:
        rollups: Dictionary of rollup objects
        bottlenecks: List of bottleneck analyses
        impact_scores: Aggregate impact scores
        recommended_stories: List of recommended stories
        date_str: Date string

    Returns:
        ReflectionArtifact instance
    """
    # Build KPI snapshot from 24h rollup
    rollup_24h = rollups.get("24h")
    kpi_snapshot = None
    if rollup_24h:
        kpis = rollup_24h.kpis
        kpi_snapshot = KPISnapshot(
            ci_pass_rate=None,  # Not available from trend rollups
            coverage=None,  # Not available from trend rollups
            cycle_time_hours=kpis.get("median_time_lost_minutes", 0) / 60.0,
            test_count=rollup_24h.data_points_count,
            lines_changed=None,
        )

    # Build root causes from bottlenecks
    root_causes: list[RootCause] = []
    for bottleneck in bottlenecks:
        root_causes.append(
            RootCause(
                category=RootCauseCategory.PROCESS,
                description=f"{bottleneck.name}: {bottleneck.occurrence_count} occurrences",
                contributing_factors=bottleneck.recommended_actions[:3],
            )
        )

    # Build automation targets
    automation_targets: list[AutomationTarget] = []
    for story in recommended_stories[:3]:  # Limit to top 3
        automation_targets.append(
            AutomationTarget(
                target=story["title"],
                priority=Priority(story["priority"]),
                estimated_impact=f"Affects: {', '.join(story['impact_areas'])}",
            )
        )

    # Build what_changed summary
    impact_summary = ", ".join(f"{k}: {v}/5" for k, v in impact_scores.items())
    what_changed = f"Daily trend analysis identified {len(bottlenecks)} bottlenecks with impact: {impact_summary}"

    # Create the artifact
    artifact = create_reflection_artifact(
        story_id=f"ST-MACRO-DAILY-{date_str.replace('-', '')}",
        reflection_type=ReflectionType.MACRO,
        what_changed=what_changed,
        kpi_snapshot=kpi_snapshot,
        root_causes=root_causes,
        next_automation_targets=automation_targets,
    )

    return artifact


def run_daily_trends(
    date_str: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Run daily trends computation and reflection generation.

    Args:
        date_str: Optional date string (YYYY-MM-DD format), defaults to today
        dry_run: If True, don't write output files
        verbose: If True, enable verbose logging

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    setup_logging(verbose)

    # Determine date
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Invalid date format: {date_str}, expected YYYY-MM-DD")
            return 1
    else:
        target_date = datetime.now(UTC)
        date_str = target_date.strftime("%Y-%m-%d")

    logger.info(f"Starting daily trends computation for {date_str}")

    # Get Redis client
    redis_client = get_redis_client()

    # Initialize TrendRollupEngine
    try:
        engine = TrendRollupEngine(redis_client=redis_client)
    except Exception as e:
        logger.error(f"Failed to initialize TrendRollupEngine: {e}")
        return 1

    # Compute all rollups
    try:
        logger.info("Computing trend rollups...")
        rollups = engine.compute_all_rollups(source="brain-eval")
        logger.info(f"Computed {len(rollups)} rollup windows: {list(rollups.keys())}")
    except Exception as e:
        logger.error(f"Failed to compute rollups: {e}")
        return 1

    # Extract bottlenecks
    bottlenecks = extract_bottlenecks_from_rollups(rollups)
    logger.info(f"Identified {len(bottlenecks)} bottlenecks")

    # Compute impact scores
    impact_scores = compute_aggregate_impact_scores(bottlenecks)

    # Generate recommended stories
    recommended_stories = generate_recommended_stories(bottlenecks, date_str)
    logger.info(f"Generated {len(recommended_stories)} recommended stories")

    # Prepare output paths
    trends_dir = project_root / "_bmad-output" / "brain-eval" / "trends"
    reflections_dir = (
        project_root / "_bmad-output" / "brain-eval" / "reflections" / "daily"
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    artifact_paths: dict[str, Path] = {}
    for window, rollup in rollups.items():
        filename = f"{window}-{timestamp}.json"
        artifact_paths[window] = trends_dir / filename

    reflection_path = reflections_dir / f"{date_str}.json"

    if dry_run:
        logger.info("DRY RUN - No files will be written")
        logger.info(f"Would create {len(artifact_paths)} trend artifacts:")
        for window, path in artifact_paths.items():
            logger.info(f"  - {path}")
        logger.info(f"Would create reflection artifact: {reflection_path}")

        # Print summary
        for window, rollup in rollups.items():
            logger.info(f"{window} rollup KPIs: {rollup.kpis}")

        return 0

    # Create output directories
    try:
        trends_dir.mkdir(parents=True, exist_ok=True)
        reflections_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created output directories")
    except Exception as e:
        logger.error(f"Failed to create output directories: {e}")
        return 1

    # Export trend artifacts
    try:
        for window, rollup in rollups.items():
            path = artifact_paths[window]
            path.write_text(rollup.to_json())
            logger.info(f"Exported {window} trend artifact: {path}")
    except Exception as e:
        logger.error(f"Failed to export trend artifacts: {e}")
        return 1

    # Create and export daily reflection artifact
    try:
        reflection_artifact = create_daily_reflection_artifact(
            rollups=rollups,
            bottlenecks=bottlenecks,
            impact_scores=impact_scores,
            recommended_stories=recommended_stories,
            date_str=date_str,
        )
        reflection_path.write_text(reflection_artifact.to_json())
        logger.info(f"Exported daily reflection artifact: {reflection_path}")
    except Exception as e:
        logger.error(f"Failed to export reflection artifact: {e}")
        return 1

    # Summary output
    logger.info("=" * 60)
    logger.info("DAILY TRENDS SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Date: {date_str}")
    logger.info(f"Rollup windows: {list(rollups.keys())}")
    logger.info(f"Bottlenecks identified: {len(bottlenecks)}")
    logger.info(f"Impact scores: {impact_scores}")
    logger.info(f"Recommended stories: {len(recommended_stories)}")

    if bottlenecks:
        logger.info("\nTop Bottlenecks:")
        for i, b in enumerate(bottlenecks, 1):
            logger.info(f"  {i}. {b.name} (priority: {b.priority.value})")

    if recommended_stories:
        logger.info("\nRecommended Stories:")
        for story in recommended_stories[:3]:
            logger.info(f"  - {story['story_id']}: {story['title']}")

    logger.info("=" * 60)

    # Close Redis connection if we opened one
    if redis_client:
        with contextlib.suppress(Exception):
            redis_client.close()

    return 0


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Run daily trends rollup and reflection generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/evaluation/run_daily_trends.py
    python3 scripts/evaluation/run_daily_trends.py --dry-run
    python3 scripts/evaluation/run_daily_trends.py --date 2026-03-02
    python3 scripts/evaluation/run_daily_trends.py --verbose
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing output files",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date (YYYY-MM-DD format, default: today)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    return run_daily_trends(
        date_str=args.date,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
