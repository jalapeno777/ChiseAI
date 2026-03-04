"""
Bottleneck-oriented reflection output generator.

This module generates daily and weekly reflection artifacts focused on
identifying and remediating bottlenecks in the agent swarm workflow.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .artifacts import Priority, RootCauseCategory
from .feature_flags import is_reflection_enabled

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# LLM integration is optional - graceful degradation if unavailable
try:
    from . import llm_integration

    LLM_INTEGRATION_AVAILABLE = True
except ImportError:
    LLM_INTEGRATION_AVAILABLE = False
    logger.debug("LLM integration not available for reflections")


@dataclass
class BottleneckKPI:
    """KPI data for a specific bottleneck."""

    bottleneck_type: str
    occurrence_count: int
    avg_impact_score: float  # 1-5 scale
    affected_stories: list[str] = field(default_factory=list)
    trend_direction: str = "stable"  # "improving", "stable", "worsening"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "bottleneck_type": self.bottleneck_type,
            "occurrence_count": self.occurrence_count,
            "avg_impact_score": self.avg_impact_score,
            "affected_stories": self.affected_stories,
            "trend_direction": self.trend_direction,
        }


@dataclass
class ImpactScore:
    """Impact scores for different dimensions (1-5 scale)."""

    throughput: int = 1  # 1=minimal, 5=critical
    efficiency: int = 1
    accuracy: int = 1
    reliability: int = 1

    def __post_init__(self):
        """Validate scores are in 1-5 range."""
        for attr in ["throughput", "efficiency", "accuracy", "reliability"]:
            val = getattr(self, attr)
            if not 1 <= val <= 5:
                raise ValueError(f"{attr} must be between 1 and 5, got {val}")

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {
            "throughput": self.throughput,
            "efficiency": self.efficiency,
            "accuracy": self.accuracy,
            "reliability": self.reliability,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> ImpactScore:
        """Create from dictionary."""
        return cls(
            throughput=data.get("throughput", 1),
            efficiency=data.get("efficiency", 1),
            accuracy=data.get("accuracy", 1),
            reliability=data.get("reliability", 1),
        )


@dataclass
class RemediationAction:
    """Recommended remediation action for a bottleneck."""

    action: str
    priority: Priority
    owner_placeholder: str  # e.g., "OWNER_TBD: senior-dev"
    estimated_effort: str  # e.g., "2-4 hours", "1-2 days"
    impact_score: ImpactScore | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "action": self.action,
            "priority": self.priority.value,
            "owner_placeholder": self.owner_placeholder,
            "estimated_effort": self.estimated_effort,
        }
        if self.impact_score:
            result["impact_score"] = self.impact_score.to_dict()
        return result


@dataclass
class TrendDelta:
    """Week-over-week trend delta for a KPI."""

    kpi_name: str
    current_value: float
    previous_value: float
    delta: float
    delta_percent: float
    direction: str  # "improved", "regressed", "stable"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "kpi_name": self.kpi_name,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "delta": self.delta,
            "delta_percent": self.delta_percent,
            "direction": self.direction,
        }


@dataclass
class FrameworkImprovement:
    """Prioritized framework improvement recommendation."""

    improvement: str
    priority: Priority
    owner_placeholder: str
    rationale: str
    estimated_impact: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "improvement": self.improvement,
            "priority": self.priority.value,
            "owner_placeholder": self.owner_placeholder,
            "rationale": self.rationale,
            "estimated_impact": self.estimated_impact,
        }


@dataclass
class DailyReflectionArtifact:
    """
    Daily reflection artifact focused on bottlenecks.

    Contains:
    - Top 3 recurring bottlenecks
    - Impact scores (1-5 scale)
    - Remediation recommendations
    - LLM-generated insights (optional)
    """

    date: str
    timestamp: str
    provenance: str
    top_bottlenecks: list[BottleneckKPI]
    impact_scores: ImpactScore
    remediation_actions: list[RemediationAction]
    summary: str
    llm_insights: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "date": self.date,
            "timestamp": self.timestamp,
            "provenance": self.provenance,
            "top_bottlenecks": [b.to_dict() for b in self.top_bottlenecks],
            "impact_scores": self.impact_scores.to_dict(),
            "remediation_actions": [r.to_dict() for r in self.remediation_actions],
            "summary": self.summary,
        }
        if self.llm_insights:
            result["llm_insights"] = self.llm_insights
        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class WeeklyReflectionArtifact:
    """
    Weekly reflection artifact with trend analysis.

    Contains:
    - Week-over-week KPI deltas
    - Improvements and regressions
    - Framework improvement recommendations
    - LLM-powered executive summary (optional)
    """

    week_start: str
    week_end: str
    timestamp: str
    provenance: str
    trend_deltas: list[TrendDelta]
    improvements: list[str]
    regressions: list[str]
    framework_improvements: list[FrameworkImprovement]
    summary: str
    llm_executive_summary: str = ""
    llm_insights: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "week_start": self.week_start,
            "week_end": self.week_end,
            "timestamp": self.timestamp,
            "provenance": self.provenance,
            "trend_deltas": [t.to_dict() for t in self.trend_deltas],
            "improvements": self.improvements,
            "regressions": self.regressions,
            "framework_improvements": [
                f.to_dict() for f in self.framework_improvements
            ],
            "summary": self.summary,
        }
        if self.llm_executive_summary:
            result["llm_executive_summary"] = self.llm_executive_summary
        if self.llm_insights:
            result["llm_insights"] = self.llm_insights
        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class BottleneckReflectionGenerator:
    """
    Generates bottleneck-oriented reflection artifacts.

    Produces daily and weekly reflections that identify recurring
    bottlenecks and recommend remediation actions.
    """

    # Bottleneck type mappings to root cause categories
    BOTTLENECK_TO_ROOT_CAUSE = {
        "ci_failures": RootCauseCategory.INFRASTRUCTURE,
        "test_failures": RootCauseCategory.CODE_QUALITY,
        "merge_conflicts": RootCauseCategory.PROCESS,
        "timeout_issues": RootCauseCategory.INFRASTRUCTURE,
        "coverage_gaps": RootCauseCategory.TEST_COVERAGE,
        "dependency_issues": RootCauseCategory.DEPENDENCY,
        "knowledge_gaps": RootCauseCategory.KNOWLEDGE_GAP,
    }

    # Impact score defaults by bottleneck type
    DEFAULT_IMPACT_SCORES = {
        "ci_failures": ImpactScore(
            throughput=4, efficiency=3, accuracy=2, reliability=4
        ),
        "test_failures": ImpactScore(
            throughput=3, efficiency=3, accuracy=4, reliability=3
        ),
        "merge_conflicts": ImpactScore(
            throughput=4, efficiency=4, accuracy=2, reliability=2
        ),
        "timeout_issues": ImpactScore(
            throughput=5, efficiency=4, accuracy=2, reliability=3
        ),
        "coverage_gaps": ImpactScore(
            throughput=2, efficiency=2, accuracy=3, reliability=4
        ),
        "dependency_issues": ImpactScore(
            throughput=3, efficiency=3, accuracy=3, reliability=4
        ),
        "knowledge_gaps": ImpactScore(
            throughput=3, efficiency=4, accuracy=3, reliability=2
        ),
    }

    def __init__(self, output_dir: str | Path | None = None):
        """
        Initialize the generator.

        Args:
            output_dir: Directory for output artifacts. Defaults to
                       _bmad-output/brain-eval/reflections/
        """
        if output_dir is None:
            # Default to _bmad-output/brain-eval/reflections/
            output_dir = Path("_bmad-output/brain-eval/reflections")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_daily_reflection(
        self,
        trend_rollups: list[dict[str, Any]],
        date: str | datetime | None = None,
        use_llm: bool = False,
    ) -> DailyReflectionArtifact | None:
        """
        Generate a daily reflection artifact from trend rollups.

        Args:
            trend_rollups: List of trend rollup dictionaries containing
                          bottleneck KPIs from the monitoring system.
            date: Date for the reflection. Defaults to today (UTC).
            use_llm: Whether to use LLM for insight generation.
                    Falls back to deterministic approach if LLM unavailable.

        Returns:
            DailyReflectionArtifact with top bottlenecks and remediation,
            or None if reflection is disabled by feature flag.
        """
        # Check feature flag
        if not is_reflection_enabled():
            logger.info("Daily reflection disabled by feature flag")
            date_obj = date if isinstance(date, datetime) else datetime.now(UTC)
            if isinstance(date, str):
                date_obj = datetime.fromisoformat(date.replace("Z", "+00:00"))
            return DailyReflectionArtifact(
                date=date_obj.strftime("%Y-%m-%d"),
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                provenance="bottleneck_reflection.BottleneckReflectionGenerator",
                top_bottlenecks=[],
                impact_scores=ImpactScore(),
                remediation_actions=[],
                summary="Reflection disabled by feature flag",
            )

        # Normalize date
        if date is None:
            date = datetime.now(UTC)
        elif isinstance(date, str):
            date = datetime.fromisoformat(date.replace("Z", "+00:00"))

        date_str = date.strftime("%Y-%m-%d")
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Extract and rank bottlenecks from trend rollups
        bottlenecks = self._extract_bottlenecks(trend_rollups)
        top_bottlenecks = sorted(
            bottlenecks,
            key=lambda b: (b.occurrence_count, b.avg_impact_score),
            reverse=True,
        )[:3]

        # Calculate aggregate impact scores
        impact_scores = self._calculate_aggregate_impact(top_bottlenecks)

        # Generate remediation actions
        remediation_actions = self._generate_remediation_actions(top_bottlenecks)

        # Generate summary
        summary = self._generate_daily_summary(date_str, top_bottlenecks, impact_scores)

        # LLM insights (optional)
        llm_insights: dict[str, Any] = {}
        if use_llm and LLM_INTEGRATION_AVAILABLE:
            try:
                llm_insights = self._generate_llm_insights_for_daily(
                    top_bottlenecks, impact_scores, trend_rollups
                )
            except Exception as e:
                logger.warning(f"LLM insight generation failed, using fallback: {e}")
                llm_insights = {"error": str(e), "fallback_used": True}

        return DailyReflectionArtifact(
            date=date_str,
            timestamp=timestamp,
            provenance="bottleneck_reflection.BottleneckReflectionGenerator",
            top_bottlenecks=top_bottlenecks,
            impact_scores=impact_scores,
            remediation_actions=remediation_actions,
            summary=summary,
            llm_insights=llm_insights,
        )

    def generate_weekly_reflection(
        self,
        trend_rollups: list[dict[str, Any]],
        previous_week_rollups: list[dict[str, Any]] | None = None,
        week_start: str | datetime | None = None,
        use_llm: bool = False,
    ) -> WeeklyReflectionArtifact | None:
        """
        Generate a weekly reflection artifact with trend analysis.

        Args:
            trend_rollups: List of trend rollup dictionaries for current week.
            previous_week_rollups: Optional trend rollups from previous week
                                  for comparison. If None, assumes stable.
            week_start: Start date of the week. Defaults to current week's Monday.
            use_llm: Whether to use LLM for insight generation.
                    Falls back to deterministic approach if LLM unavailable.

        Returns:
            WeeklyReflectionArtifact with trend deltas and recommendations,
            or None if reflection is disabled by feature flag.
        """
        # Check feature flag
        if not is_reflection_enabled():
            logger.info("Weekly reflection disabled by feature flag")
            week_start_obj = (
                week_start if isinstance(week_start, datetime) else datetime.now(UTC)
            )
            if isinstance(week_start, str):
                week_start_obj = datetime.fromisoformat(
                    week_start.replace("Z", "+00:00")
                )
            elif week_start is None:
                today = datetime.now(UTC)
                week_start_obj = today - timedelta(days=today.weekday())
            week_end_obj = week_start_obj + timedelta(days=6)
            return WeeklyReflectionArtifact(
                week_start=week_start_obj.strftime("%Y-%m-%d"),
                week_end=week_end_obj.strftime("%Y-%m-%d"),
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                provenance="bottleneck_reflection.BottleneckReflectionGenerator",
                trend_deltas=[],
                improvements=[],
                regressions=[],
                framework_improvements=[],
                summary="Reflection disabled by feature flag",
            )

        # Normalize week_start
        if week_start is None:
            today = datetime.now(UTC)
            # Find Monday of current week
            week_start = today - timedelta(days=today.weekday())
        elif isinstance(week_start, str):
            week_start = datetime.fromisoformat(week_start.replace("Z", "+00:00"))

        week_end = week_start + timedelta(days=6)
        week_start_str = week_start.strftime("%Y-%m-%d")
        week_end_str = week_end.strftime("%Y-%m-%d")
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Calculate trend deltas for all 5 KPIs
        trend_deltas = self._calculate_trend_deltas(
            trend_rollups, previous_week_rollups
        )

        # Identify improvements and regressions
        improvements = [d.kpi_name for d in trend_deltas if d.direction == "improved"]
        regressions = [d.kpi_name for d in trend_deltas if d.direction == "regressed"]

        # Generate framework improvements
        framework_improvements = self._generate_framework_improvements(
            trend_deltas, trend_rollups
        )

        # Generate summary
        summary = self._generate_weekly_summary(
            week_start_str, week_end_str, trend_deltas, improvements, regressions
        )

        # LLM insights (optional)
        llm_executive_summary = ""
        llm_insights: dict[str, Any] = {}
        if use_llm and LLM_INTEGRATION_AVAILABLE:
            try:
                llm_executive_summary, llm_insights = (
                    self._generate_llm_insights_for_weekly(
                        trend_deltas, improvements, regressions, framework_improvements
                    )
                )
            except Exception as e:
                logger.warning(f"LLM insight generation failed, using fallback: {e}")
                llm_insights = {"error": str(e), "fallback_used": True}

        return WeeklyReflectionArtifact(
            week_start=week_start_str,
            week_end=week_end_str,
            timestamp=timestamp,
            provenance="bottleneck_reflection.BottleneckReflectionGenerator",
            trend_deltas=trend_deltas,
            improvements=improvements,
            regressions=regressions,
            framework_improvements=framework_improvements,
            summary=summary,
            llm_executive_summary=llm_executive_summary,
            llm_insights=llm_insights,
        )

    def export_reflection_artifact(
        self,
        reflection: DailyReflectionArtifact | WeeklyReflectionArtifact,
        filepath: str | Path | None = None,
    ) -> Path:
        """
        Export a reflection artifact to a JSON file.

        Args:
            reflection: The reflection artifact to export.
            filepath: Optional filepath. If None, generates from artifact type and date.

        Returns:
            Path to the exported file.
        """
        if filepath is None:
            # Generate filepath from artifact type
            if isinstance(reflection, DailyReflectionArtifact):
                filename = f"daily-{reflection.date}.json"
            else:
                filename = f"weekly-{reflection.week_start}.json"
            filepath = self.output_dir / filename
        else:
            filepath = Path(filepath)

        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Write artifact
        with open(filepath, "w") as f:
            f.write(reflection.to_json(indent=2))

        logger.info(f"Exported reflection artifact to {filepath}")

        # Send Discord notification (non-blocking)
        try:
            import asyncio

            from governance.notifications import DiscordNotifier

            notifier = DiscordNotifier()
            artifact_type = (
                "daily" if isinstance(reflection, DailyReflectionArtifact) else "weekly"
            )
            asyncio.create_task(
                notifier.notify_reflection(reflection, artifact_type, str(filepath))
            )
        except Exception as e:
            logger.debug(f"Discord notification skipped: {e}")

        return filepath

    def _extract_bottlenecks(
        self, trend_rollups: list[dict[str, Any]]
    ) -> list[BottleneckKPI]:
        """Extract bottleneck KPIs from trend rollups."""
        bottlenecks = []

        # Group by bottleneck type
        bottleneck_data: dict[str, dict[str, Any]] = {}

        for rollup in trend_rollups:
            # Handle both direct bottleneck data and wrapped formats
            if "bottlenecks" in rollup:
                # Format: {"bottlenecks": [...]}
                for bn in rollup["bottlenecks"]:
                    bn_type = bn.get("type", bn.get("bottleneck_type", "unknown"))
                    if bn_type not in bottleneck_data:
                        bottleneck_data[bn_type] = {
                            "count": 0,
                            "impact_scores": [],
                            "stories": [],
                            "trends": [],
                        }
                    bottleneck_data[bn_type]["count"] += bn.get("count", 1)
                    if "impact_score" in bn:
                        bottleneck_data[bn_type]["impact_scores"].append(
                            bn["impact_score"]
                        )
                    if "stories" in bn:
                        bottleneck_data[bn_type]["stories"].extend(bn["stories"])
                    if "trend" in bn:
                        bottleneck_data[bn_type]["trends"].append(bn["trend"])

            # Handle direct KPI format
            for key in [
                "ci_failures",
                "test_failures",
                "merge_conflicts",
                "timeout_issues",
                "coverage_gaps",
                "dependency_issues",
                "knowledge_gaps",
            ]:
                if key in rollup and rollup[key] > 0:
                    if key not in bottleneck_data:
                        bottleneck_data[key] = {
                            "count": 0,
                            "impact_scores": [],
                            "stories": [],
                            "trends": [],
                        }
                    bottleneck_data[key]["count"] += rollup[key]
                    if "story_id" in rollup:
                        bottleneck_data[key]["stories"].append(rollup["story_id"])

        # Create BottleneckKPI objects
        for bn_type, data in bottleneck_data.items():
            avg_impact = 3.0  # Default
            if data["impact_scores"]:
                avg_impact = sum(data["impact_scores"]) / len(data["impact_scores"])

            # Determine trend direction
            trend = "stable"
            if data["trends"]:
                improving = sum(1 for t in data["trends"] if t == "improving")
                worsening = sum(1 for t in data["trends"] if t == "worsening")
                if improving > worsening:
                    trend = "improving"
                elif worsening > improving:
                    trend = "worsening"

            bottlenecks.append(
                BottleneckKPI(
                    bottleneck_type=bn_type,
                    occurrence_count=data["count"],
                    avg_impact_score=round(avg_impact, 2),
                    affected_stories=list(set(data["stories"])),
                    trend_direction=trend,
                )
            )

        return bottlenecks

    def _calculate_aggregate_impact(
        self, bottlenecks: list[BottleneckKPI]
    ) -> ImpactScore:
        """Calculate aggregate impact scores from bottlenecks."""
        if not bottlenecks:
            return ImpactScore()

        total_throughput = 0
        total_efficiency = 0
        total_accuracy = 0
        total_reliability = 0
        count = 0

        for bn in bottlenecks:
            default_scores = self.DEFAULT_IMPACT_SCORES.get(
                bn.bottleneck_type, ImpactScore()
            )
            # Weight by occurrence count
            weight = bn.occurrence_count
            total_throughput += default_scores.throughput * weight
            total_efficiency += default_scores.efficiency * weight
            total_accuracy += default_scores.accuracy * weight
            total_reliability += default_scores.reliability * weight
            count += weight

        if count == 0:
            return ImpactScore()

        # Round to nearest integer and clamp to 1-5
        return ImpactScore(
            throughput=max(1, min(5, round(total_throughput / count))),
            efficiency=max(1, min(5, round(total_efficiency / count))),
            accuracy=max(1, min(5, round(total_accuracy / count))),
            reliability=max(1, min(5, round(total_reliability / count))),
        )

    def _generate_remediation_actions(
        self, bottlenecks: list[BottleneckKPI]
    ) -> list[RemediationAction]:
        """Generate remediation actions for bottlenecks."""
        actions = []

        # Remediation templates by bottleneck type
        remediation_templates = {
            "ci_failures": (
                "Review and fix CI pipeline configuration issues",
                Priority.HIGH,
                "OWNER_TBD: devops-engineer",
                "2-4 hours",
            ),
            "test_failures": (
                "Investigate and fix failing test cases",
                Priority.HIGH,
                "OWNER_TBD: senior-dev",
                "4-8 hours",
            ),
            "merge_conflicts": (
                "Implement automated conflict resolution workflow",
                Priority.MEDIUM,
                "OWNER_TBD: senior-dev",
                "1-2 days",
            ),
            "timeout_issues": (
                "Optimize resource allocation and timeout thresholds",
                Priority.HIGH,
                "OWNER_TBD: devops-engineer",
                "2-4 hours",
            ),
            "coverage_gaps": (
                "Add missing test coverage for identified gaps",
                Priority.MEDIUM,
                "OWNER_TBD: senior-dev",
                "1-2 days",
            ),
            "dependency_issues": (
                "Update and pin dependency versions",
                Priority.MEDIUM,
                "OWNER_TBD: senior-dev",
                "2-4 hours",
            ),
            "knowledge_gaps": (
                "Create documentation and runbooks for identified gaps",
                Priority.LOW,
                "OWNER_TBD: senior-dev",
                "1-2 days",
            ),
        }

        for bn in bottlenecks[:3]:  # Top 3 only
            template = remediation_templates.get(
                bn.bottleneck_type,
                (
                    f"Investigate and address {bn.bottleneck_type}",
                    Priority.MEDIUM,
                    "OWNER_TBD: senior-dev",
                    "4-8 hours",
                ),
            )

            impact = self.DEFAULT_IMPACT_SCORES.get(bn.bottleneck_type)

            actions.append(
                RemediationAction(
                    action=template[0],
                    priority=template[1],
                    owner_placeholder=template[2],
                    estimated_effort=template[3],
                    impact_score=impact,
                )
            )

        # Sort by priority (HIGH first)
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        actions.sort(key=lambda a: priority_order.get(a.priority, 1))

        return actions

    def _calculate_trend_deltas(
        self,
        current_rollups: list[dict[str, Any]],
        previous_rollups: list[dict[str, Any]] | None,
    ) -> list[TrendDelta]:
        """Calculate week-over-week trend deltas for the 5 KPIs."""
        # The 5 KPIs from KPISnapshot
        kpi_names = [
            "ci_pass_rate",
            "coverage",
            "cycle_time_hours",
            "test_count",
            "lines_changed",
        ]

        # Calculate current week averages
        current_kpis = self._aggregate_kpis(current_rollups)

        # Calculate previous week averages (or use defaults)
        if previous_rollups:
            previous_kpis = self._aggregate_kpis(previous_rollups)
        else:
            # Assume stable if no previous data
            previous_kpis = current_kpis.copy()

        deltas = []
        for kpi_name in kpi_names:
            current = current_kpis.get(kpi_name, 0.0)
            previous = previous_kpis.get(kpi_name, 0.0)

            if previous == 0:
                delta = current
                delta_percent = 100.0 if current > 0 else 0.0
            else:
                delta = current - previous
                delta_percent = (delta / abs(previous)) * 100

            # Determine direction
            # For cycle_time_hours, lower is better
            if kpi_name == "cycle_time_hours":
                if delta < -0.01:
                    direction = "improved"
                elif delta > 0.01:
                    direction = "regressed"
                else:
                    direction = "stable"
            else:
                # For other KPIs, higher is better
                if delta > 0.01:
                    direction = "improved"
                elif delta < -0.01:
                    direction = "regressed"
                else:
                    direction = "stable"

            deltas.append(
                TrendDelta(
                    kpi_name=kpi_name,
                    current_value=round(current, 4),
                    previous_value=round(previous, 4),
                    delta=round(delta, 4),
                    delta_percent=round(delta_percent, 2),
                    direction=direction,
                )
            )

        return deltas

    def _aggregate_kpis(self, rollups: list[dict[str, Any]]) -> dict[str, float]:
        """Aggregate KPI values from rollups."""
        if not rollups:
            return {}

        totals: dict[str, float] = {}
        counts: dict[str, int] = {}

        for rollup in rollups:
            # Handle kpi_snapshot format
            if "kpi_snapshot" in rollup:
                snapshot = rollup["kpi_snapshot"]
                for key in [
                    "ci_pass_rate",
                    "coverage",
                    "cycle_time_hours",
                    "test_count",
                    "lines_changed",
                ]:
                    if key in snapshot and snapshot[key] is not None:
                        totals[key] = totals.get(key, 0.0) + snapshot[key]
                        counts[key] = counts.get(key, 0) + 1

            # Handle direct KPI format
            for key in [
                "ci_pass_rate",
                "coverage",
                "cycle_time_hours",
                "test_count",
                "lines_changed",
            ]:
                if key in rollup and rollup[key] is not None:
                    totals[key] = totals.get(key, 0.0) + rollup[key]
                    counts[key] = counts.get(key, 0) + 1

        # Calculate averages
        averages = {}
        for key in totals:
            if counts[key] > 0:
                averages[key] = totals[key] / counts[key]

        return averages

    def _generate_framework_improvements(
        self,
        trend_deltas: list[TrendDelta],
        rollups: list[dict[str, Any]],
    ) -> list[FrameworkImprovement]:
        """Generate prioritized framework improvement recommendations."""
        improvements = []

        # Analyze trend deltas for improvement opportunities
        for delta in trend_deltas:
            if delta.direction == "regressed":
                if delta.kpi_name == "ci_pass_rate":
                    improvements.append(
                        FrameworkImprovement(
                            improvement="Enhance CI reliability monitoring and auto-retry mechanisms",
                            priority=Priority.HIGH,
                            owner_placeholder="OWNER_TBD: devops-engineer",
                            rationale=f"CI pass rate regressed by {abs(delta.delta_percent):.1f}%",
                            estimated_impact="Reduce CI-related delays by 30-50%",
                        )
                    )
                elif delta.kpi_name == "coverage":
                    improvements.append(
                        FrameworkImprovement(
                            improvement="Implement coverage gate enforcement and auto-test generation",
                            priority=Priority.MEDIUM,
                            owner_placeholder="OWNER_TBD: senior-dev",
                            rationale=f"Coverage regressed by {abs(delta.delta_percent):.1f}%",
                            estimated_impact="Maintain >80% coverage threshold",
                        )
                    )
                elif delta.kpi_name == "cycle_time_hours":
                    improvements.append(
                        FrameworkImprovement(
                            improvement="Optimize workflow automation and reduce manual handoffs",
                            priority=Priority.HIGH,
                            owner_placeholder="OWNER_TBD: senior-dev",
                            rationale=f"Cycle time increased by {abs(delta.delta_percent):.1f}%",
                            estimated_impact="Reduce cycle time by 20-30%",
                        )
                    )

        # Add general improvements if no specific regressions
        if not improvements:
            improvements.append(
                FrameworkImprovement(
                    improvement="Continue monitoring and maintain current KPI levels",
                    priority=Priority.LOW,
                    owner_placeholder="OWNER_TBD: senior-dev",
                    rationale="All KPIs stable or improving",
                    estimated_impact="Sustain current performance",
                )
            )

        return improvements

    def _generate_daily_summary(
        self,
        date: str,
        bottlenecks: list[BottleneckKPI],
        impact: ImpactScore,
    ) -> str:
        """Generate a summary text for daily reflection."""
        lines = [
            f"Daily Bottleneck Reflection for {date}",
            "",
            f"Top Bottlenecks Identified: {len(bottlenecks)}",
        ]

        for i, bn in enumerate(bottlenecks, 1):
            lines.append(
                f"  {i}. {bn.bottleneck_type}: {bn.occurrence_count} occurrences "
                f"(impact: {bn.avg_impact_score:.1f}/5, trend: {bn.trend_direction})"
            )

        lines.extend(
            [
                "",
                "Aggregate Impact Scores (1-5 scale):",
                f"  Throughput: {impact.throughput}",
                f"  Efficiency: {impact.efficiency}",
                f"  Accuracy: {impact.accuracy}",
                f"  Reliability: {impact.reliability}",
            ]
        )

        return "\n".join(lines)

    def _generate_weekly_summary(
        self,
        week_start: str,
        week_end: str,
        trend_deltas: list[TrendDelta],
        improvements: list[str],
        regressions: list[str],
    ) -> str:
        """Generate a summary text for weekly reflection."""
        lines = [
            f"Weekly Trend Reflection: {week_start} to {week_end}",
            "",
            "KPI Trend Summary:",
        ]

        for delta in trend_deltas:
            direction_icon = {
                "improved": "↑",
                "regressed": "↓",
                "stable": "→",
            }.get(delta.direction, "→")
            lines.append(
                f"  {direction_icon} {delta.kpi_name}: {delta.current_value:.2f} "
                f"({delta.direction}, {abs(delta.delta_percent):.1f}%)"
            )

        lines.extend(
            [
                "",
                f"Improvements: {len(improvements)}",
                f"Regressions: {len(regressions)}",
            ]
        )

        if improvements:
            lines.append(f"  Improved: {', '.join(improvements)}")
        if regressions:
            lines.append(f"  Regressed: {', '.join(regressions)}")

        return "\n".join(lines)

    def _generate_llm_insights_for_daily(
        self,
        top_bottlenecks: list[BottleneckKPI],
        impact_scores: ImpactScore,
        trend_rollups: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate LLM insights for daily reflection.

        Args:
            top_bottlenecks: Top bottleneck KPIs
            impact_scores: Aggregate impact scores
            trend_rollups: Raw trend rollup data

        Returns:
            Dictionary with LLM insights
        """
        trend_data = {
            "bottlenecks": [b.to_dict() for b in top_bottlenecks],
            "impact_scores": impact_scores.to_dict(),
            "rollup_count": len(trend_rollups),
        }

        kpi_data = {
            "total_bottlenecks": len(top_bottlenecks),
            "highest_impact": (
                top_bottlenecks[0].bottleneck_type if top_bottlenecks else None
            ),
        }

        result = llm_integration.generate_llm_insights(trend_data, kpi_data)
        return (
            result.to_dict() if hasattr(result, "to_dict") else {"summary": str(result)}
        )

    def _generate_llm_insights_for_weekly(
        self,
        trend_deltas: list[TrendDelta],
        improvements: list[str],
        regressions: list[str],
        framework_improvements: list[FrameworkImprovement],
    ) -> tuple[str, dict[str, Any]]:
        """Generate LLM insights for weekly reflection.

        Args:
            trend_deltas: Week-over-week trend deltas
            improvements: List of improved KPIs
            regressions: List of regressed KPIs
            framework_improvements: Framework improvement recommendations

        Returns:
            Tuple of (executive_summary, insights_dict)
        """
        artifact_data = {
            "trend_deltas": [d.to_dict() for d in trend_deltas],
            "improvements": improvements,
            "regressions": regressions,
            "framework_improvements": [f.to_dict() for f in framework_improvements],
        }

        # Generate executive summary
        summary = llm_integration.summarize_weekly_reflection(artifact_data)

        # Generate insights
        trend_data = {
            "deltas": [d.to_dict() for d in trend_deltas],
            "improvement_count": len(improvements),
            "regression_count": len(regressions),
        }

        kpi_data = {
            "framework_improvements": len(framework_improvements),
            "priority_high": sum(
                1 for f in framework_improvements if f.priority == Priority.HIGH
            ),
        }

        insights_result = llm_integration.generate_llm_insights(trend_data, kpi_data)
        insights_dict = (
            insights_result.to_dict()
            if hasattr(insights_result, "to_dict")
            else {"summary": str(insights_result)}
        )

        return summary, insights_dict


def create_daily_reflection(
    trend_rollups: list[dict[str, Any]],
    date: str | datetime | None = None,
    output_dir: str | Path | None = None,
    use_llm: bool = False,
) -> tuple[DailyReflectionArtifact, Path]:
    """
    Convenience function to create and export a daily reflection.

    Args:
        trend_rollups: List of trend rollup dictionaries.
        date: Date for the reflection. Defaults to today.
        output_dir: Output directory for artifacts.
        use_llm: Whether to use LLM for insight generation.

    Returns:
        Tuple of (artifact, filepath).
    """
    generator = BottleneckReflectionGenerator(output_dir)
    artifact = generator.generate_daily_reflection(trend_rollups, date, use_llm=use_llm)
    filepath = generator.export_reflection_artifact(artifact)
    return artifact, filepath


def create_weekly_reflection(
    trend_rollups: list[dict[str, Any]],
    previous_week_rollups: list[dict[str, Any]] | None = None,
    week_start: str | datetime | None = None,
    output_dir: str | Path | None = None,
    use_llm: bool = False,
) -> tuple[WeeklyReflectionArtifact, Path]:
    """
    Convenience function to create and export a weekly reflection.

    Args:
        trend_rollups: List of trend rollup dictionaries for current week.
        previous_week_rollups: Optional trend rollups from previous week.
        week_start: Start date of the week.
        output_dir: Output directory for artifacts.
        use_llm: Whether to use LLM for insight generation.

    Returns:
        Tuple of (artifact, filepath).
    """
    generator = BottleneckReflectionGenerator(output_dir)
    artifact = generator.generate_weekly_reflection(
        trend_rollups, previous_week_rollups, week_start, use_llm=use_llm
    )
    filepath = generator.export_reflection_artifact(artifact)
    return artifact, filepath
