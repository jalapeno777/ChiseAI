#!/usr/bin/env python3
"""Run weekly reflection for KPI trend analysis.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Generates weekly deep reflection artifacts with:
- Trend deltas week-over-week for all 5 KPIs
- What improved/regressed with magnitude (+/- %)
- Prioritized framework improvements with owner placeholders

Usage:
    python3 scripts/evaluation/run_weekly_reflection.py
    python3 scripts/evaluation/run_weekly_reflection.py --dry-run
    python3 scripts/evaluation/run_weekly_reflection.py --week 2026-W09

Exit codes:
    0 = Success
    1 = Failure
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.evaluation.trend_rollups import TrendRollup, TrendRollupEngine, calculate_kpis
from src.governance.reflection import (
    AutomationTarget,
    KPISnapshot,
    Priority,
    ReflectionArtifact,
    ReflectionType,
    RootCause,
    RootCauseCategory,
    create_reflection_artifact,
)
from src.governance.reflection.feature_flags import is_reflection_enabled

# LLM integration (optional, graceful degradation)
try:
    from src.governance.reflection.llm_integration import (
        ReflectionLLMIntegration,
        get_llm_telemetry,
    )

    LLM_INTEGRATION_AVAILABLE = True
except ImportError:
    LLM_INTEGRATION_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Output paths
OUTPUT_DIR = Path("_bmad-output/brain-eval/reflections/weekly")
TRENDS_DIR = Path("_bmad-output/brain-eval/trends")

# KPI names for tracking
KPI_NAMES = [
    "recurring_issue_rate",
    "median_time_lost_minutes",
    "unresolved_issue_age",
    "top_fingerprint_repeat_count",
    "fix_reopen_rate",
]


@dataclass
class WeekOverWeekDelta:
    """Week-over-week change for a single KPI."""

    kpi_name: str
    current_value: float
    previous_value: float | None
    delta_percent: float | None
    direction: str  # "improved", "regressed", "unchanged", "no_data"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "kpi_name": self.kpi_name,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "delta_percent": self.delta_percent,
            "direction": self.direction,
        }


@dataclass
class FrameworkImprovement:
    """Suggested framework improvement."""

    description: str
    owner_placeholder: str
    priority: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.description,
            "owner_placeholder": self.owner_placeholder,
            "priority": self.priority,
            "rationale": self.rationale,
        }


@dataclass
class WeeklyReflectionContent:
    """Content specific to weekly reflection."""

    week_id: str
    trend_deltas: list[WeekOverWeekDelta]
    improvements: list[FrameworkImprovement]
    regressions: list[FrameworkImprovement]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "week_id": self.week_id,
            "trend_deltas": [d.to_dict() for d in self.trend_deltas],
            "improvements": [i.to_dict() for i in self.improvements],
            "regressions": [r.to_dict() for r in self.regressions],
            "summary": self.summary,
        }


def get_week_identifier(dt: datetime | None = None) -> str:
    """Get week identifier in format YYYY-WXX.

    Args:
        dt: Datetime to get week for (defaults to now)

    Returns:
        Week identifier string
    """
    if dt is None:
        dt = datetime.now(UTC)
    iso_calendar = dt.isocalendar()
    return f"{iso_calendar[0]}-W{iso_calendar[1]:02d}"


def get_previous_week_id(week_id: str) -> str:
    """Get the previous week identifier.

    Args:
        week_id: Current week ID (YYYY-WXX)

    Returns:
        Previous week ID
    """
    year, week = map(int, week_id.split("-W"))

    # Go back one week
    week -= 1
    if week < 1:
        year -= 1
        # Get last week of previous year
        # Using datetime to calculate properly
        dec_31 = datetime(year, 12, 31)
        week = dec_31.isocalendar()[1]

    return f"{year}-W{week:02d}"


def parse_week_id(week_id: str) -> datetime:
    """Parse week ID to get a datetime in that week.

    Args:
        week_id: Week ID (YYYY-WXX)

    Returns:
        Datetime for the Monday of that week
    """
    year, week = map(int, week_id.split("-W"))
    # ISO week date: Monday of the given week
    return datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w").replace(tzinfo=UTC)


def load_previous_week_rollup(week_id: str) -> TrendRollup | None:
    """Load the 7d rollup from the previous week.

    Args:
        week_id: Current week ID

    Returns:
        TrendRollup from previous week, or None if not found
    """
    prev_week_id = get_previous_week_id(week_id)
    prev_week_dt = parse_week_id(prev_week_id)

    # Look for rollup files from the previous week
    # Pattern: 7d-YYYYMMDD-HHMMSS.json
    week_start = prev_week_dt
    week_end = week_start + timedelta(days=7)

    logger.info(f"Looking for previous week rollup: {prev_week_id}")

    if not TRENDS_DIR.exists():
        logger.warning(f"Trends directory not found: {TRENDS_DIR}")
        return None

    # Find all 7d rollups and look for one from the previous week
    rollup_files = sorted(TRENDS_DIR.glob("7d-*.json"))

    for rollup_file in rollup_files:
        try:
            data = json.loads(rollup_file.read_text())
            rollup = TrendRollup.from_dict(data)

            # Check if rollup was computed in the previous week
            if week_start <= rollup.computed_at < week_end:
                logger.info(f"Found previous week rollup: {rollup_file}")
                return rollup

        except Exception as e:
            logger.error(f"Error loading rollup {rollup_file}: {e}")
            continue

    # If no exact match, try to find the most recent 7d rollup
    if rollup_files:
        try:
            # Get the most recent one before current week
            latest_file = rollup_files[-1]
            data = json.loads(latest_file.read_text())
            rollup = TrendRollup.from_dict(data)

            current_week_dt = parse_week_id(week_id)
            if rollup.computed_at < current_week_dt:
                logger.info(f"Using most recent previous rollup: {latest_file}")
                return rollup

        except Exception as e:
            logger.error(f"Error loading latest rollup: {e}")

    logger.warning("No previous week rollup found")
    return None


def compute_wow_deltas(
    current_rollup: TrendRollup,
    previous_rollup: TrendRollup | None,
) -> list[WeekOverWeekDelta]:
    """Compute week-over-week deltas for all KPIs.

    Args:
        current_rollup: Current week's rollup
        previous_rollup: Previous week's rollup (may be None)

    Returns:
        List of WeekOverWeekDelta objects
    """
    deltas: list[WeekOverWeekDelta] = []

    for kpi_name in KPI_NAMES:
        current_value = current_rollup.kpis.get(kpi_name, 0.0)

        if isinstance(current_value, str):
            current_value = 0.0
        else:
            current_value = float(current_value)

        if previous_rollup is None:
            delta = WeekOverWeekDelta(
                kpi_name=kpi_name,
                current_value=current_value,
                previous_value=None,
                delta_percent=None,
                direction="no_data",
            )
        else:
            previous_value = previous_rollup.kpis.get(kpi_name, 0.0)

            if isinstance(previous_value, str):
                previous_value = 0.0
            else:
                previous_value = float(previous_value)

            # Calculate percentage change
            if previous_value == 0:
                if current_value == 0:
                    delta_percent = 0.0
                else:
                    delta_percent = 100.0  # New issue
            else:
                delta_percent = (
                    (current_value - previous_value) / previous_value
                ) * 100

            # Determine direction (for these KPIs, lower is generally better)
            # Exception: fix_reopen_rate - lower is better
            # Exception: recurring_issue_rate - lower is better
            # Exception: median_time_lost_minutes - lower is better
            # Exception: unresolved_issue_age - lower is better
            # Exception: top_fingerprint_repeat_count - lower is better

            if abs(delta_percent) < 1.0:  # Less than 1% change
                direction = "unchanged"
            elif delta_percent < 0:
                direction = "improved"  # Lower is better for all these KPIs
            else:
                direction = "regressed"

            delta = WeekOverWeekDelta(
                kpi_name=kpi_name,
                current_value=current_value,
                previous_value=previous_value,
                delta_percent=round(delta_percent, 2),
                direction=direction,
            )

        deltas.append(delta)

    return deltas


def generate_framework_improvements(
    deltas: list[WeekOverWeekDelta],
) -> tuple[list[FrameworkImprovement], list[FrameworkImprovement]]:
    """Generate prioritized framework improvements based on KPI changes.

    Args:
        deltas: List of week-over-week deltas

    Returns:
        Tuple of (improvements, regressions)
    """
    improvements: list[FrameworkImprovement] = []
    regressions: list[FrameworkImprovement] = []

    for delta in deltas:
        if delta.direction == "regressed":
            # Generate improvement suggestion for regression
            if delta.kpi_name == "recurring_issue_rate":
                regressions.append(
                    FrameworkImprovement(
                        description=f"Investigate recurring issues spike (+{delta.delta_percent:.1f}%)",
                        owner_placeholder="OWNER_TBD: senior-dev",
                        priority="high",
                        rationale="Recurring issues indicate systemic problems in codebase",
                    )
                )
            elif delta.kpi_name == "median_time_lost_minutes":
                regressions.append(
                    FrameworkImprovement(
                        description=f"Reduce issue resolution time (+{delta.delta_percent:.1f}%)",
                        owner_placeholder="OWNER_TBD: ops-lead",
                        priority="high",
                        rationale="Time lost impacts overall productivity",
                    )
                )
            elif delta.kpi_name == "unresolved_issue_age":
                regressions.append(
                    FrameworkImprovement(
                        description=f"Address aging unresolved issues (+{delta.delta_percent:.1f}%)",
                        owner_placeholder="OWNER_TBD: tech-lead",
                        priority="medium",
                        rationale="Old issues accumulate technical debt",
                    )
                )
            elif delta.kpi_name == "top_fingerprint_repeat_count":
                regressions.append(
                    FrameworkImprovement(
                        description=f"Fix root cause of repeated issue (+{delta.delta_percent:.1f}%)",
                        owner_placeholder="OWNER_TBD: domain-expert",
                        priority="high",
                        rationale="High fingerprint repeat indicates unresolved root cause",
                    )
                )
            elif delta.kpi_name == "fix_reopen_rate":
                regressions.append(
                    FrameworkImprovement(
                        description=f"Improve fix quality to prevent reopens (+{delta.delta_percent:.1f}%)",
                        owner_placeholder="OWNER_TBD: qa-lead",
                        priority="medium",
                        rationale="Reopened fixes waste engineering time",
                    )
                )

        elif delta.direction == "improved":
            # Document improvement as positive trend
            if delta.kpi_name == "recurring_issue_rate":
                improvements.append(
                    FrameworkImprovement(
                        description=f"Recurring issue rate improved ({delta.delta_percent:.1f}%)",
                        owner_placeholder="OWNER_TBD: team-lead",
                        priority="low",
                        rationale="Document successful patterns for reuse",
                    )
                )
            elif delta.kpi_name == "median_time_lost_minutes":
                improvements.append(
                    FrameworkImprovement(
                        description=f"Time to resolution improved ({delta.delta_percent:.1f}%)",
                        owner_placeholder="OWNER_TBD: process-owner",
                        priority="low",
                        rationale="Capture process improvements for knowledge base",
                    )
                )

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    regressions.sort(key=lambda x: priority_order.get(x.priority, 99))
    improvements.sort(key=lambda x: priority_order.get(x.priority, 99))

    return improvements, regressions


def generate_summary(
    deltas: list[WeekOverWeekDelta],
    improvements: list[FrameworkImprovement],
    regressions: list[FrameworkImprovement],
) -> str:
    """Generate a summary of the weekly reflection.

    Args:
        deltas: List of week-over-week deltas
        improvements: List of improvements
        regressions: List of regressions

    Returns:
        Summary string
    """
    improved_count = sum(1 for d in deltas if d.direction == "improved")
    regressed_count = sum(1 for d in deltas if d.direction == "regressed")
    unchanged_count = sum(1 for d in deltas if d.direction == "unchanged")

    parts = [
        "Weekly reflection summary:",
        f"- {improved_count} KPIs improved",
        f"- {regressed_count} KPIs regressed",
        f"- {unchanged_count} KPIs unchanged",
    ]

    if regressions:
        parts.append(f"- {len(regressions)} action items require attention")

    if improvements:
        parts.append(f"- {len(improvements)} positive trends documented")

    return "\n".join(parts)


def create_weekly_reflection_artifact(
    week_id: str,
    current_rollup: TrendRollup,
    previous_rollup: TrendRollup | None,
    use_llm: bool = False,
) -> dict[str, Any]:
    """Create the complete weekly reflection artifact.

    Args:
        week_id: Week identifier
        current_rollup: Current week's rollup
        previous_rollup: Previous week's rollup
        use_llm: Whether to use LLM for insight generation

    Returns:
        Dictionary containing the full reflection artifact
    """
    logger.info(f"Creating weekly reflection for {week_id}")

    # Get real KPI data from stories + incidents (not just incidents)
    logger.info("Calculating real KPIs from stories and incidents...")
    kpi_result = calculate_kpis(window="7d")

    if kpi_result.get("status") == "success":
        real_kpis = kpi_result.get("kpis", {})
        data_points = kpi_result.get("data_points", {})
        logger.info(
            f"Real KPIs calculated: {data_points.get('stories', 0)} stories, "
            f"{data_points.get('incidents', 0)} incidents"
        )

        # Merge real KPIs into current_rollup (override incident-only metrics)
        current_rollup.kpis.update(
            {
                "cycle_time_hours": real_kpis.get("cycle_time_hours", 0.0),
                "test_count": real_kpis.get("test_count", 0),
                "recurring_issue_rate": real_kpis.get("recurring_issue_rate", 0.0),
                "median_time_lost_minutes": real_kpis.get(
                    "median_time_lost_minutes", 0.0
                ),
                "unresolved_issue_age": real_kpis.get(
                    "unresolved_issue_age_hours", 0.0
                ),
                "top_fingerprint_repeat_count": real_kpis.get(
                    "top_fingerprint_repeat_count", 0
                ),
                "fix_reopen_rate": real_kpis.get("fix_reopen_rate", 0.0),
            }
        )

        # Update data_points_count to reflect stories + incidents
        current_rollup.data_points_count = data_points.get(
            "stories", 0
        ) + data_points.get("incidents", 0)
    else:
        logger.warning(f"Failed to calculate real KPIs: {kpi_result.get('message')}")

    # Compute deltas
    deltas = compute_wow_deltas(current_rollup, previous_rollup)

    # Generate improvements
    improvements, regressions = generate_framework_improvements(deltas)

    # Generate summary
    summary = generate_summary(deltas, improvements, regressions)

    # LLM-powered insights (optional)
    llm_executive_summary = ""
    llm_insights: dict[str, Any] = {}
    if use_llm and LLM_INTEGRATION_AVAILABLE:
        logger.info("Generating LLM-powered insights...")
        try:
            llm_integration = ReflectionLLMIntegration()
            import asyncio

            # Prepare artifact data for LLM
            artifact_data = {
                "week_id": week_id,
                "trend_deltas": [d.to_dict() for d in deltas],
                "improvements": [i.to_dict() for i in improvements],
                "regressions": [r.to_dict() for r in regressions],
                "summary": summary,
            }

            # Generate executive summary
            llm_executive_summary = asyncio.run(
                llm_integration.summarize_weekly_reflection(artifact_data)
            )
            if llm_executive_summary:
                logger.info("LLM executive summary generated successfully")

            # Generate insights
            trend_data = {
                "deltas": [d.to_dict() for d in deltas],
                "improvement_count": len(improvements),
                "regression_count": len(regressions),
            }
            kpi_data = {
                "data_points": current_rollup.data_points_count,
                "time_range_days": 7,
            }

            insights_result = asyncio.run(
                llm_integration.generate_llm_insights(trend_data, kpi_data)
            )
            if insights_result.success:
                llm_insights = insights_result.to_dict()
                logger.info(
                    f"LLM insights generated (provider: {insights_result.provider_used})"
                )
            else:
                logger.warning(f"LLM insights failed: {insights_result.error_message}")
                llm_insights = {
                    "error": insights_result.error_message,
                    "fallback_used": True,
                }

        except Exception as e:
            logger.warning(f"LLM insight generation failed: {e}")
            llm_insights = {"error": str(e), "fallback_used": True}

    # Create weekly content
    weekly_content = WeeklyReflectionContent(
        week_id=week_id,
        trend_deltas=deltas,
        improvements=improvements,
        regressions=regressions,
        summary=summary,
    )

    # Create base reflection artifact
    story_id = f"ST-MACRO-WEEKLY-{week_id.replace('-W', '')}"

    # Build KPI snapshot from current rollup with real data
    kpi_snapshot = KPISnapshot(
        ci_pass_rate=None,  # Not tracked in trend rollups
        coverage=None,  # Not tracked in trend rollups
        cycle_time_hours=float(current_rollup.kpis.get("cycle_time_hours", 0.0)),
        test_count=current_rollup.data_points_count,
        lines_changed=None,  # Not tracked in trend rollups
    )

    # Create root causes for regressions
    root_causes = []
    for regression in regressions:
        root_causes.append(
            RootCause(
                category=RootCauseCategory.PROCESS,
                description=regression.description,
                contributing_factors=[regression.rationale],
            )
        )

    # Create automation targets from improvements and regressions
    automation_targets = []
    for regression in regressions:
        automation_targets.append(
            AutomationTarget(
                target=regression.description,
                priority=(
                    Priority.HIGH if regression.priority == "high" else Priority.MEDIUM
                ),
                estimated_impact=regression.rationale,
            )
        )

    reflection = create_reflection_artifact(
        story_id=story_id,
        reflection_type=ReflectionType.MACRO,
        what_changed=summary,
        kpi_snapshot=kpi_snapshot,
        root_causes=root_causes,
        next_automation_targets=automation_targets,
    )

    # Combine base reflection with weekly content
    artifact = reflection.to_dict()
    artifact["weekly_content"] = weekly_content.to_dict()

    # Add LLM content if available
    if llm_executive_summary:
        artifact["llm_executive_summary"] = llm_executive_summary
    if llm_insights:
        artifact["llm_insights"] = llm_insights

    return artifact


def run_weekly_reflection(
    week_id: str | None = None,
    dry_run: bool = False,
    use_llm: bool = False,
) -> int:
    """Run the weekly reflection process.

    Args:
        week_id: Week identifier (defaults to current week)
        dry_run: If True, don't write artifact to disk
        use_llm: If True, use LLM for insight generation

    Returns:
        Exit code (0=success, 1=failure)
    """
    try:
        # Determine week
        if week_id is None:
            week_id = get_week_identifier()

        logger.info(f"Running weekly reflection for {week_id}")
        logger.info(f"Dry run: {dry_run}")
        logger.info(f"Use LLM: {use_llm}")

        if use_llm and not LLM_INTEGRATION_AVAILABLE:
            logger.warning("LLM integration requested but not available")

        # Initialize trend rollup engine
        engine = TrendRollupEngine(output_dir=str(TRENDS_DIR))

        # Compute current week's 7d rollup
        logger.info("Computing current week 7d rollup...")
        current_rollup = engine.compute_7d_rollups(source="weekly-reflection")

        # Load previous week's rollup
        logger.info("Loading previous week rollup...")
        previous_rollup = load_previous_week_rollup(week_id)

        # Create reflection artifact
        artifact = create_weekly_reflection_artifact(
            week_id=week_id,
            current_rollup=current_rollup,
            previous_rollup=previous_rollup,
            use_llm=use_llm,
        )

        # Output path
        output_path = OUTPUT_DIR / f"{week_id}.json"

        if dry_run:
            logger.info(f"[DRY RUN] Would write artifact to: {output_path}")
            logger.info(
                f"[DRY RUN] Artifact preview:\n{json.dumps(artifact, indent=2)}"
            )
            return 0

        # Create output directory
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Write artifact
        output_path.write_text(json.dumps(artifact, indent=2))
        logger.info(f"Wrote weekly reflection artifact to: {output_path}")

        # Log summary
        weekly_content = artifact.get("weekly_content", {})
        logger.info(f"Summary:\n{weekly_content.get('summary', 'No summary')}")

        # Log LLM usage metrics if applicable
        if use_llm and LLM_INTEGRATION_AVAILABLE:
            try:
                telemetry = get_llm_telemetry()
                logger.info(f"LLM telemetry: {json.dumps(telemetry, indent=2)}")
            except Exception as e:
                logger.debug(f"Could not retrieve LLM telemetry: {e}")

        return 0

    except Exception as e:
        logger.error(f"Weekly reflection failed: {e}", exc_info=True)
        return 1


def main() -> int:
    """Main entry point."""
    # Check feature flag early
    if not is_reflection_enabled():
        logger.info("Weekly reflection disabled by feature flag")
        return 0

    parser = argparse.ArgumentParser(
        description="Run weekly KPI trend reflection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing artifact to disk",
    )

    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="Week identifier (YYYY-WXX format, defaults to current week)",
    )

    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM for insight generation (requires LLM provider configuration)",
    )

    args = parser.parse_args()

    # Check feature flag
    if not is_reflection_enabled():
        logger.info("Weekly reflection disabled by feature flag")
        print("Weekly reflection is currently disabled by feature flag")
        return 0

    return run_weekly_reflection(
        week_id=args.week,
        dry_run=args.dry_run,
        use_llm=args.use_llm,
    )


if __name__ == "__main__":
    sys.exit(main())
