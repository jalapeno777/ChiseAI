"""
Health Scorer - Per-Agent and Swarm Health Scoring (ST-GOV-008).

Implements health scoring based on four weighted dimensions:
- Performance (25%): task_completion_time, pr_merge_time, ci_duration
- Quality (25%): bug_escape_rate, review_rejection_rate, rollback_frequency
- Reliability (25%): uptime, error_rate, recovery_time
- Collaboration (25%): conflict_rate, handoff_success, knowledge_sharing

Story: ST-GOV-008
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"  # Score >= 80
    DEGRADED = "degraded"  # Score >= 60 and < 80
    UNHEALTHY = "unhealthy"  # Score >= 40 and < 60
    CRITICAL = "critical"  # Score < 40


@dataclass
class DimensionConfig:
    """Configuration for a health dimension."""

    name: str
    weight: float  # 0.0 to 1.0
    metrics: list[str]
    baseline: float = 0.0  # Baseline value for normalization


@dataclass
class HealthDimension:
    """Health dimension with score."""

    name: str
    score: float  # 0-100
    weight: float
    metrics: dict[str, float] = field(default_factory=dict)
    contributing_factors: list[str] = field(default_factory=list)


@dataclass
class AgentHealthScore:
    """Complete health score for an agent."""

    agent_id: str
    overall_score: float  # 0-100
    status: HealthStatus
    dimensions: dict[str, HealthDimension]
    timestamp: datetime
    trend: str = "stable"  # "improving", "declining", "stable"
    previous_score: float | None = None

    def is_healthy(self) -> bool:
        """Check if agent is healthy (score >= 70)."""
        return self.overall_score >= 70.0


@dataclass
class SwarmHealthScore:
    """Aggregated health score for the entire swarm."""

    overall_score: float  # 0-100
    status: HealthStatus
    agent_count: int
    healthy_count: int
    degraded_count: int
    unhealthy_count: int
    critical_count: int
    dimensions: dict[str, float]  # Average per dimension
    timestamp: datetime

    def is_healthy(self) -> bool:
        """Check if swarm is healthy (score >= 70)."""
        return self.overall_score >= 70.0


# Default dimension configurations
DEFAULT_DIMENSIONS = {
    "performance": DimensionConfig(
        name="performance",
        weight=0.25,
        metrics=["task_completion_time", "pr_merge_time", "ci_duration"],
        baseline=1.0,  # Normalized baseline
    ),
    "quality": DimensionConfig(
        name="quality",
        weight=0.25,
        metrics=["bug_escape_rate", "review_rejection_rate", "rollback_frequency"],
        baseline=0.0,
    ),
    "reliability": DimensionConfig(
        name="reliability",
        weight=0.25,
        metrics=["uptime", "error_rate", "recovery_time"],
        baseline=99.0,  # Uptime baseline
    ),
    "collaboration": DimensionConfig(
        name="collaboration",
        weight=0.25,
        metrics=["conflict_rate", "handoff_success", "knowledge_sharing"],
        baseline=0.0,
    ),
}


class HealthScorer:
    """
    Calculates health scores for agents and the swarm.

    Uses weighted dimensions to compute overall health scores
    with support for trend analysis and status classification.
    """

    def __init__(
        self,
        dimensions: dict[str, DimensionConfig] | None = None,
        history_window_hours: int = 24,
    ):
        """
        Initialize health scorer.

        Args:
            dimensions: Custom dimension configurations (defaults to DEFAULT_DIMENSIONS)
            history_window_hours: Hours of history to consider for trends
        """
        self.dimensions = dimensions or DEFAULT_DIMENSIONS
        self.history_window = timedelta(hours=history_window_hours)
        self._score_history: dict[str, list[AgentHealthScore]] = {}

    def score_agent(
        self,
        agent_id: str,
        metrics: dict[str, dict[str, float]],
        previous_score: float | None = None,
    ) -> AgentHealthScore:
        """
        Calculate health score for a single agent.

        Args:
            agent_id: Agent identifier
            metrics: Dict mapping dimension name to metric values
                    e.g., {"performance": {"task_completion_time": 120.5}}
            previous_score: Previous overall score for trend calculation

        Returns:
            AgentHealthScore with overall and dimension scores
        """
        dimension_scores: dict[str, HealthDimension] = {}
        total_weight = sum(d.weight for d in self.dimensions.values())

        for dim_name, dim_config in self.dimensions.items():
            dim_metrics = metrics.get(dim_name, {})
            dim_score = self._calculate_dimension_score(dim_config, dim_metrics)

            dimension_scores[dim_name] = HealthDimension(
                name=dim_name,
                score=dim_score,
                weight=dim_config.weight,
                metrics=dim_metrics,
                contributing_factors=self._identify_contributing_factors(
                    dim_config, dim_metrics, dim_score
                ),
            )

        # Calculate weighted overall score
        overall_score = (
            sum(d.score * d.weight for d in dimension_scores.values()) / total_weight
        )

        # Determine trend
        trend = "stable"
        if previous_score is not None:
            diff = overall_score - previous_score
            if diff > 5:
                trend = "improving"
            elif diff < -5:
                trend = "declining"

        score = AgentHealthScore(
            agent_id=agent_id,
            overall_score=round(overall_score, 2),
            status=self._classify_status(overall_score),
            dimensions=dimension_scores,
            timestamp=datetime.now(UTC),
            trend=trend,
            previous_score=previous_score,
        )

        # Store in history
        if agent_id not in self._score_history:
            self._score_history[agent_id] = []
        self._score_history[agent_id].append(score)

        # Prune old history
        cutoff = datetime.now(UTC) - self.history_window
        self._score_history[agent_id] = [
            s for s in self._score_history[agent_id] if s.timestamp >= cutoff
        ]

        return score

    def score_swarm(
        self,
        agent_scores: list[AgentHealthScore],
    ) -> SwarmHealthScore:
        """
        Calculate aggregated swarm health score.

        Args:
            agent_scores: List of individual agent health scores

        Returns:
            SwarmHealthScore with aggregated metrics
        """
        if not agent_scores:
            return SwarmHealthScore(
                overall_score=0.0,
                status=HealthStatus.CRITICAL,
                agent_count=0,
                healthy_count=0,
                degraded_count=0,
                unhealthy_count=0,
                critical_count=0,
                dimensions={},
                timestamp=datetime.now(UTC),
            )

        # Count by status
        healthy = sum(1 for s in agent_scores if s.status == HealthStatus.HEALTHY)
        degraded = sum(1 for s in agent_scores if s.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for s in agent_scores if s.status == HealthStatus.UNHEALTHY)
        critical = sum(1 for s in agent_scores if s.status == HealthStatus.CRITICAL)

        # Calculate weighted average (healthier agents weighted more)
        total_score = sum(s.overall_score for s in agent_scores)
        avg_score = total_score / len(agent_scores)

        # Aggregate dimension scores
        dimension_avgs: dict[str, float] = {}
        for dim_name in self.dimensions:
            dim_scores = [
                s.dimensions[dim_name].score
                for s in agent_scores
                if dim_name in s.dimensions
            ]
            if dim_scores:
                dimension_avgs[dim_name] = round(sum(dim_scores) / len(dim_scores), 2)

        return SwarmHealthScore(
            overall_score=round(avg_score, 2),
            status=self._classify_status(avg_score),
            agent_count=len(agent_scores),
            healthy_count=healthy,
            degraded_count=degraded,
            unhealthy_count=unhealthy,
            critical_count=critical,
            dimensions=dimension_avgs,
            timestamp=datetime.now(UTC),
        )

    def _calculate_dimension_score(
        self,
        config: DimensionConfig,
        metrics: dict[str, float],
    ) -> float:
        """
        Calculate score for a single dimension.

        Args:
            config: Dimension configuration
            metrics: Metric values for this dimension

        Returns:
            Dimension score (0-100)
        """
        if not metrics:
            return 50.0  # Default neutral score if no metrics

        scores = []
        for metric_name in config.metrics:
            if metric_name in metrics:
                value = metrics[metric_name]
                score = self._normalize_metric(metric_name, value, config)
                scores.append(score)

        if not scores:
            return 50.0

        return min(100.0, max(0.0, sum(scores) / len(scores)))

    def _normalize_metric(
        self,
        metric_name: str,
        value: float,
        config: DimensionConfig,
    ) -> float:
        """
        Normalize a metric value to 0-100 scale.

        Args:
            metric_name: Name of the metric
            value: Raw metric value
            config: Dimension configuration

        Returns:
            Normalized score (0-100)
        """
        # Metric-specific normalization logic
        if metric_name == "task_completion_time":
            # Lower is better. 0-30min = 100, 30-60min = 80, 1-2hr = 60, >2hr = 40
            if value <= 30:
                return 100.0
            elif value <= 60:
                return 80.0
            elif value <= 120:
                return 60.0
            else:
                return max(20.0, 60.0 - (value - 120) / 10)

        elif metric_name == "pr_merge_time":
            # Hours to merge. <1hr = 100, 1-4hr = 80, 4-24hr = 60, >24hr = 40
            if value <= 1:
                return 100.0
            elif value <= 4:
                return 80.0
            elif value <= 24:
                return 60.0
            else:
                return max(20.0, 40.0 - (value - 24) / 24)

        elif metric_name == "ci_duration":
            # Minutes. <5min = 100, 5-10min = 80, 10-20min = 60, >20min = 40
            if value <= 5:
                return 100.0
            elif value <= 10:
                return 80.0
            elif value <= 20:
                return 60.0
            else:
                return max(20.0, 40.0 - (value - 20) / 5)

        elif metric_name == "bug_escape_rate":
            # Percentage. 0% = 100, <5% = 90, <10% = 70, >=10% = 50
            if value == 0:
                return 100.0
            elif value < 5:
                return 90.0
            elif value < 10:
                return 70.0
            else:
                return max(20.0, 50.0 - value)

        elif metric_name == "review_rejection_rate":
            # Percentage. 0% = 100, <10% = 85, <25% = 70, >=25% = 50
            if value == 0:
                return 100.0
            elif value < 10:
                return 85.0
            elif value < 25:
                return 70.0
            else:
                return max(20.0, 50.0 - value / 2)

        elif metric_name == "rollback_frequency":
            # Count per day. 0 = 100, 1 = 80, 2 = 60, >=3 = 40
            if value == 0:
                return 100.0
            elif value == 1:
                return 80.0
            elif value == 2:
                return 60.0
            else:
                return max(20.0, 40.0 - value * 5)

        elif metric_name == "uptime":
            # Percentage. >=99.9% = 100, >=99% = 90, >=95% = 70, <95% = 50
            if value >= 99.9:
                return 100.0
            elif value >= 99:
                return 90.0
            elif value >= 95:
                return 70.0
            else:
                return max(20.0, value / 2)

        elif metric_name == "error_rate":
            # Percentage. 0% = 100, <1% = 90, <5% = 70, >=5% = 40
            if value == 0:
                return 100.0
            elif value < 1:
                return 90.0
            elif value < 5:
                return 70.0
            else:
                return max(20.0, 40.0 - value * 4)

        elif metric_name == "recovery_time":
            # Minutes. <1min = 100, <5min = 85, <15min = 60, >=15min = 40
            if value < 1:
                return 100.0
            elif value < 5:
                return 85.0
            elif value < 15:
                return 60.0
            else:
                return max(20.0, 40.0 - (value - 15) / 5)

        elif metric_name == "conflict_rate":
            # Conflicts per day. 0 = 100, <2 = 85, <5 = 60, >=5 = 40
            if value == 0:
                return 100.0
            elif value < 2:
                return 85.0
            elif value < 5:
                return 60.0
            else:
                return max(20.0, 40.0 - value * 4)

        elif metric_name == "handoff_success":
            # Percentage. 100% = 100, >=90% = 85, >=75% = 60, <75% = 40
            if value >= 100:
                return 100.0
            elif value >= 90:
                return 85.0
            elif value >= 75:
                return 60.0
            else:
                return max(20.0, value / 2)

        elif metric_name == "knowledge_sharing":
            # Score 0-100 based on documentation/mentoring. Direct mapping.
            return min(100.0, max(0.0, value))

        # Default: assume value is already 0-100
        return min(100.0, max(0.0, value))

    def _classify_status(self, score: float) -> HealthStatus:
        """Classify health status based on score."""
        if score >= 80:
            return HealthStatus.HEALTHY
        elif score >= 60:
            return HealthStatus.DEGRADED
        elif score >= 40:
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.CRITICAL

    def _identify_contributing_factors(
        self,
        config: DimensionConfig,
        metrics: dict[str, float],
        score: float,
    ) -> list[str]:
        """Identify factors contributing to low scores."""
        factors = []

        if score < 70:
            for metric_name in config.metrics:
                if metric_name in metrics:
                    value = metrics[metric_name]
                    metric_score = self._normalize_metric(metric_name, value, config)
                    if metric_score < 60:
                        factors.append(
                            f"{metric_name}={value} (score: {metric_score:.0f})"
                        )

        return factors

    def get_agent_history(
        self,
        agent_id: str,
        limit: int = 10,
    ) -> list[AgentHealthScore]:
        """
        Get score history for an agent.

        Args:
            agent_id: Agent identifier
            limit: Maximum number of records to return

        Returns:
            List of historical scores, most recent first
        """
        history = self._score_history.get(agent_id, [])
        return list(reversed(history[-limit:]))

    def get_trend(self, agent_id: str) -> str:
        """
        Calculate trend for an agent based on recent history.

        Args:
            agent_id: Agent identifier

        Returns:
            Trend string: "improving", "declining", or "stable"
        """
        history = self.get_agent_history(agent_id, limit=5)
        if len(history) < 2:
            return "stable"

        recent = [s.overall_score for s in history]
        avg_recent = sum(recent[:2]) / 2
        avg_older = sum(recent[2:]) / len(recent[2:]) if len(recent) > 2 else avg_recent

        diff = avg_recent - avg_older
        if diff > 5:
            return "improving"
        elif diff < -5:
            return "declining"
        return "stable"
