"""Repeated issue detection and aggregation system.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides detection and analysis of repeated issues across evaluation runs,
enabling identification of systemic problems and trend analysis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from evaluation.fingerprinting import (
    FingerprintCluster,
    FingerprintClusterer,
    IssueFingerprint,
)

if TYPE_CHECKING:
    from evaluation.schemas.mini_eval import Issue


logger = logging.getLogger(__name__)


@dataclass
class IssueCluster:
    """Represents a cluster of repeated issues.

    Attributes:
        fingerprint: Unique fingerprint for this issue type
        category: Issue category (e.g., "db_connectivity")
        count: Number of occurrences
        first_seen: Timestamp of first occurrence
        last_seen: Timestamp of most recent occurrence
        examples: List of recent example issues
        severity_trend: Trend in severity ("improving", "stable", "worsening")
        severity_history: List of severity levels over time
    """

    fingerprint: str
    category: str
    count: int
    first_seen: datetime
    last_seen: datetime
    examples: list[dict] = field(default_factory=list)
    severity_trend: str = "stable"
    severity_history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "fingerprint": self.fingerprint,
            "category": self.category,
            "count": self.count,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "examples": self.examples,
            "severity_trend": self.severity_trend,
            "severity_history": self.severity_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssueCluster:
        """Create from dictionary."""
        return cls(
            fingerprint=data["fingerprint"],
            category=data["category"],
            count=data["count"],
            first_seen=datetime.fromisoformat(data["first_seen"]),
            last_seen=datetime.fromisoformat(data["last_seen"]),
            examples=data.get("examples", []),
            severity_trend=data.get("severity_trend", "stable"),
            severity_history=data.get("severity_history", []),
        )


@dataclass
class TrendAnalysis:
    """Analysis of issue trends over time.

    Attributes:
        issues_by_hour: Dictionary mapping hour to issue count
        categories_trend: Dictionary mapping category to trend data
        severity_distribution: Dictionary mapping severity to count
        time_range_hours: Hours covered by this analysis
    """

    issues_by_hour: dict[str, int] = field(default_factory=dict)
    categories_trend: dict[str, dict] = field(default_factory=dict)
    severity_distribution: dict[str, int] = field(default_factory=dict)
    time_range_hours: int = 24

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "issues_by_hour": self.issues_by_hour,
            "categories_trend": self.categories_trend,
            "severity_distribution": self.severity_distribution,
            "time_range_hours": self.time_range_hours,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrendAnalysis:
        """Create from dictionary."""
        return cls(
            issues_by_hour=data.get("issues_by_hour", {}),
            categories_trend=data.get("categories_trend", {}),
            severity_distribution=data.get("severity_distribution", {}),
            time_range_hours=data.get("time_range_hours", 24),
        )


@dataclass
class RepeatedIssueReport:
    """Report of repeated issues detected in a time window.

    Attributes:
        generated_at: When the report was generated
        time_window_hours: Time window analyzed
        total_issues: Total number of issues in window
        unique_issues: Number of unique issue types
        repeated_issues: List of IssueCluster with count > 1
        top_recurring: Top 10 issues by occurrence count
        recommendations: Suggested framework improvements
        trend_analysis: Detailed trend analysis
    """

    generated_at: datetime
    time_window_hours: int
    total_issues: int
    unique_issues: int
    repeated_issues: list[IssueCluster] = field(default_factory=list)
    top_recurring: list[IssueCluster] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    trend_analysis: TrendAnalysis | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "time_window_hours": self.time_window_hours,
            "total_issues": self.total_issues,
            "unique_issues": self.unique_issues,
            "repeated_issues": [r.to_dict() for r in self.repeated_issues],
            "top_recurring": [r.to_dict() for r in self.top_recurring],
            "recommendations": self.recommendations,
            "trend_analysis": self.trend_analysis.to_dict()
            if self.trend_analysis
            else None,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepeatedIssueReport:
        """Create from dictionary."""
        trend_data = data.get("trend_analysis")
        trend_analysis = TrendAnalysis.from_dict(trend_data) if trend_data else None

        return cls(
            generated_at=datetime.fromisoformat(data["generated_at"]),
            time_window_hours=data["time_window_hours"],
            total_issues=data["total_issues"],
            unique_issues=data["unique_issues"],
            repeated_issues=[
                IssueCluster.from_dict(r) for r in data.get("repeated_issues", [])
            ],
            top_recurring=[
                IssueCluster.from_dict(r) for r in data.get("top_recurring", [])
            ],
            recommendations=data.get("recommendations", []),
            trend_analysis=trend_analysis,
        )

    @classmethod
    def from_json(cls, json_str: str) -> RepeatedIssueReport:
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def __str__(self) -> str:
        """Generate human-readable report string."""
        lines = [
            f"Repeated Issue Report (Last {self.time_window_hours}h)",
            "=" * 50,
            f"Total Issues: {self.total_issues}",
            f"Unique Issues: {self.unique_issues}",
            f"Repeated Issues: {len(self.repeated_issues)}",
            "",
            "Top Recurring:",
        ]

        for i, issue in enumerate(self.top_recurring[:10], 1):
            lines.append(f"{i}. [{issue.category}] ({issue.count} occurrences)")
            lines.append(
                f"   First: {issue.first_seen.isoformat()}, "
                f"Last: {issue.last_seen.isoformat()}"
            )
            if issue.examples:
                lines.append(f"   Examples: {len(issue.examples)} recent instances")
            lines.append(f"   Trend: {issue.severity_trend}")
            lines.append("")

        if self.recommendations:
            lines.append("Recommendations:")
            for rec in self.recommendations:
                lines.append(f"  - {rec}")

        return "\n".join(lines)


class RepeatedIssueDetector:
    """Detects and analyzes repeated issues across evaluation runs.

    Provides capabilities to:
    - Detect repeated issues within a time window
    - Cluster similar issues by fingerprint
    - Analyze trends in issue occurrence
    - Generate recommendations for framework improvements

    Example:
        >>> detector = RepeatedIssueDetector(redis_client=redis)
        >>> report = detector.detect_repeated_issues(time_window_hours=24)
        >>> print(report)
        Repeated Issue Report (Last 24h)
        ========================================
        ...
    """

    def __init__(self, redis_client: Any | None = None) -> None:
        """Initialize the repeated issue detector.

        Args:
            redis_client: Optional Redis client for reading/writing data
        """
        self.redis_client = redis_client
        self.clusterer = FingerprintClusterer()

    def detect_repeated_issues(
        self, time_window_hours: int = 24, min_occurrences: int = 2
    ) -> RepeatedIssueReport:
        """Detect repeated issues within a time window.

        Analyzes issues from Redis and issue ingestion results to identify
        repeated problems and generate a comprehensive report.

        Args:
            time_window_hours: Time window to analyze (default: 24)
            min_occurrences: Minimum occurrences to be considered repeated

        Returns:
            RepeatedIssueReport with analysis results
        """
        logger.info(f"Detecting repeated issues for last {time_window_hours}h")

        # Collect issues from all sources
        issues = self._collect_issues(time_window_hours)

        # Cluster issues by fingerprint
        clusters = self._cluster_issues(issues)

        # Build issue clusters with metadata
        issue_clusters = self._build_issue_clusters(clusters, issues)

        # Filter to repeated issues only
        repeated = [c for c in issue_clusters if c.count >= min_occurrences]

        # Sort by count descending
        repeated.sort(key=lambda x: x.count, reverse=True)

        # Get top 10
        top_recurring = repeated[:10]

        # Generate recommendations
        recommendations = self._generate_recommendations(repeated)

        # Perform trend analysis
        trend_analysis = self._analyze_trends(issues, time_window_hours)

        report = RepeatedIssueReport(
            generated_at=datetime.now(UTC),
            time_window_hours=time_window_hours,
            total_issues=len(issues),
            unique_issues=len(clusters),
            repeated_issues=repeated,
            top_recurring=top_recurring,
            recommendations=recommendations,
            trend_analysis=trend_analysis,
        )

        # Store report in Redis
        self._store_report(report)

        logger.info(
            f"Detected {len(repeated)} repeated issues out of "
            f"{len(issues)} total ({len(clusters)} unique)"
        )

        return report

    def get_issue_clusters(self) -> list[IssueCluster]:
        """Get all current issue clusters.

        Returns:
            List of IssueCluster objects sorted by count
        """
        return self.clusterer.get_clusters()

    def get_trend_analysis(self, time_window_hours: int = 24) -> TrendAnalysis:
        """Get trend analysis for the specified time window.

        Args:
            time_window_hours: Time window to analyze

        Returns:
            TrendAnalysis with trend data
        """
        issues = self._collect_issues(time_window_hours)
        return self._analyze_trends(issues, time_window_hours)

    def _collect_issues(self, time_window_hours: int) -> list[dict]:
        """Collect issues from all sources.

        Reads from Redis (bmad:chiseai:brain:eval:mini:*) and
        processes them into a standardized format.

        Args:
            time_window_hours: Time window to collect issues from

        Returns:
            List of issue dictionaries
        """
        issues: list[dict] = []
        cutoff_time = datetime.now(UTC) - timedelta(hours=time_window_hours)

        if not self.redis_client:
            logger.warning("No Redis client configured, returning empty issue list")
            return issues

        try:
            # Scan for mini eval results in Redis
            pattern = "bmad:chiseai:brain:eval:mini:*"
            cursor = 0

            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                for key in keys:
                    try:
                        data = self.redis_client.get(key)
                        if data:
                            result = json.loads(data)
                            result_timestamp = result.get("timestamp", "")

                            # Check if within time window
                            if result_timestamp:
                                result_time = datetime.fromisoformat(result_timestamp)
                                if result_time < cutoff_time:
                                    continue

                            # Extract issues from result
                            for issue in result.get("issues", []):
                                issue["_source_key"] = key
                                issue["_eval_timestamp"] = result_timestamp
                                issues.append(issue)

                    except Exception as e:
                        logger.error(f"Error processing key {key}: {e}")
                        continue

                if cursor == 0:
                    break

        except Exception as e:
            logger.error(f"Error collecting issues from Redis: {e}")

        logger.info(f"Collected {len(issues)} issues from Redis")
        return issues

    def _cluster_issues(self, issues: list[dict]) -> dict[str, FingerprintCluster]:
        """Cluster issues by fingerprint.

        Args:
            issues: List of issue dictionaries

        Returns:
            Dictionary mapping fingerprint to FingerprintCluster
        """
        self.clusterer.clear()

        for issue_data in issues:
            # Create a temporary Issue object for fingerprinting
            try:
                from evaluation.schemas.mini_eval import Issue

                issue = Issue(
                    issue_id=issue_data.get("issue_id", ""),
                    category=issue_data.get("category", "other"),
                    severity=issue_data.get("severity", "P3"),
                    description=issue_data.get("description", ""),
                    source=issue_data.get("source", ""),
                    timestamp=issue_data.get("timestamp", ""),
                )
                self.clusterer.add_issue(issue)
            except Exception as e:
                logger.error(f"Error fingerprinting issue: {e}")
                continue

        return self.clusterer.clusters

    def _build_issue_clusters(
        self, clusters: dict[str, FingerprintCluster], issues: list[dict]
    ) -> list[IssueCluster]:
        """Build IssueCluster objects with full metadata.

        Args:
            clusters: Dictionary of FingerprintCluster objects
            issues: List of raw issue dictionaries

        Returns:
            List of IssueCluster objects
        """
        issue_clusters: list[IssueCluster] = []

        # Group issues by fingerprint
        issues_by_fingerprint: dict[str, list[dict]] = {}
        for issue in issues:
            try:
                from evaluation.schemas.mini_eval import Issue

                temp_issue = Issue(
                    issue_id=issue.get("issue_id", ""),
                    category=issue.get("category", "other"),
                    severity=issue.get("severity", "P3"),
                    description=issue.get("description", ""),
                    source=issue.get("source", ""),
                    timestamp=issue.get("timestamp", ""),
                )
                fingerprint = IssueFingerprint.generate(temp_issue)

                if fingerprint not in issues_by_fingerprint:
                    issues_by_fingerprint[fingerprint] = []
                issues_by_fingerprint[fingerprint].append(issue)

            except Exception as e:
                logger.error(f"Error building cluster for issue: {e}")
                continue

        # Build IssueCluster for each fingerprint
        for fingerprint, fp_cluster in clusters.items():
            fingerprint_issues = issues_by_fingerprint.get(fingerprint, [])

            if not fingerprint_issues:
                continue

            # Get timestamps
            timestamps = []
            severities = []
            for issue in fingerprint_issues:
                try:
                    ts = issue.get("timestamp", "")
                    if ts:
                        timestamps.append(datetime.fromisoformat(ts))
                    severities.append(issue.get("severity", "P3"))
                except Exception:
                    continue

            if not timestamps:
                continue

            # Get recent examples (up to 3)
            sorted_issues = sorted(
                fingerprint_issues, key=lambda x: x.get("timestamp", ""), reverse=True
            )
            examples = [
                {
                    "issue_id": i.get("issue_id", ""),
                    "description": i.get("description", "")[:200],
                    "timestamp": i.get("timestamp", ""),
                    "severity": i.get("severity", ""),
                }
                for i in sorted_issues[:3]
            ]

            # Calculate severity trend
            severity_trend = self._calculate_severity_trend(severities)

            issue_cluster = IssueCluster(
                fingerprint=fingerprint,
                category=fp_cluster.category,
                count=fp_cluster.count,
                first_seen=min(timestamps),
                last_seen=max(timestamps),
                examples=examples,
                severity_trend=severity_trend,
                severity_history=severities,
            )

            issue_clusters.append(issue_cluster)

        return issue_clusters

    def _calculate_severity_trend(self, severities: list[str]) -> str:
        """Calculate trend in severity levels.

        Args:
            severities: List of severity strings (P0, P1, P2, P3)

        Returns:
            Trend string: "improving", "stable", or "worsening"
        """
        if len(severities) < 2:
            return "stable"

        # Map severities to numeric values (lower is worse)
        severity_values = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        values = [severity_values.get(s, 3) for s in severities]

        # Compare first half vs second half
        mid = len(values) // 2
        first_half = sum(values[:mid]) / max(len(values[:mid]), 1)
        second_half = sum(values[mid:]) / max(len(values[mid:]), 1)

        if second_half > first_half * 1.1:
            return "improving"
        elif second_half < first_half * 0.9:
            return "worsening"
        else:
            return "stable"

    def _analyze_trends(
        self, issues: list[dict], time_window_hours: int
    ) -> TrendAnalysis:
        """Analyze trends in issue occurrence.

        Args:
            issues: List of issue dictionaries
            time_window_hours: Time window analyzed

        Returns:
            TrendAnalysis with trend data
        """
        # Issues by hour
        issues_by_hour: dict[str, int] = {}
        categories_trend: dict[str, dict] = {}
        severity_distribution: dict[str, int] = {}

        for issue in issues:
            try:
                timestamp = issue.get("timestamp", "")
                category = issue.get("category", "other")
                severity = issue.get("severity", "P3")

                # Count by hour
                if timestamp:
                    hour = timestamp[:13]  # YYYY-MM-DDTHH
                    issues_by_hour[hour] = issues_by_hour.get(hour, 0) + 1

                # Count by category
                if category not in categories_trend:
                    categories_trend[category] = {"count": 0, "hours": {}}
                categories_trend[category]["count"] += 1

                if timestamp:
                    hour = timestamp[:13]
                    categories_trend[category]["hours"][hour] = (
                        categories_trend[category]["hours"].get(hour, 0) + 1
                    )

                # Count by severity
                severity_distribution[severity] = (
                    severity_distribution.get(severity, 0) + 1
                )

            except Exception as e:
                logger.error(f"Error analyzing trend for issue: {e}")
                continue

        return TrendAnalysis(
            issues_by_hour=issues_by_hour,
            categories_trend=categories_trend,
            severity_distribution=severity_distribution,
            time_range_hours=time_window_hours,
        )

    def _generate_recommendations(
        self, repeated_issues: list[IssueCluster]
    ) -> list[str]:
        """Generate recommendations based on repeated issues.

        Args:
            repeated_issues: List of repeated IssueCluster objects

        Returns:
            List of recommendation strings
        """
        recommendations: list[str] = []

        # Category-based recommendations
        category_counts: dict[str, int] = {}
        for issue in repeated_issues:
            category_counts[issue.category] = (
                category_counts.get(issue.category, 0) + issue.count
            )

        # DB connectivity issues
        if category_counts.get("db_connectivity", 0) > 5:
            recommendations.append(
                "Consider implementing connection pooling for database connections"
            )
            recommendations.append("Review database connection timeout settings")

        # File access issues
        if category_counts.get("file_access", 0) > 3:
            recommendations.append(
                "Review file permission configurations and path validations"
            )

        # Environment slowdown issues
        if category_counts.get("env_slowdown", 0) > 5:
            recommendations.append(
                "Consider resource scaling or optimization for evaluation environment"
            )
            recommendations.append("Review memory usage patterns and potential leaks")

        # Tool errors
        if category_counts.get("tool_error", 0) > 3:
            recommendations.append("Review MCP tool error handling and retry logic")
            recommendations.append(
                "Consider implementing circuit breaker pattern for external tools"
            )

        # Severity-based recommendations
        worsening_count = sum(
            1 for i in repeated_issues if i.severity_trend == "worsening"
        )
        if worsening_count > 2:
            recommendations.append(
                f"{worsening_count} issues show worsening severity trends - prioritize investigation"
            )

        # General recommendations
        if len(repeated_issues) > 10:
            recommendations.append(
                "High volume of repeated issues detected - consider systematic review"
            )

        return recommendations

    def _store_report(self, report: RepeatedIssueReport) -> None:
        """Store the report in Redis.

        Args:
            report: RepeatedIssueReport to store
        """
        if not self.redis_client:
            return

        try:
            report_id = report.generated_at.strftime("%Y%m%d_%H%M%S")
            key = f"bmad:chiseai:brain:eval:repeated_issues:{report_id}"

            self.redis_client.set(
                key,
                report.to_json(),
                ex=86400 * 30,  # 30 days TTL
            )
            logger.info(f"Stored repeated issue report in Redis: {key}")

        except Exception as e:
            logger.error(f"Failed to store report in Redis: {e}")

    def get_recent_reports(self, limit: int = 10) -> list[RepeatedIssueReport]:
        """Get recent repeated issue reports.

        Args:
            limit: Maximum number of reports to return

        Returns:
            List of RepeatedIssueReport objects
        """
        if not self.redis_client:
            return []

        reports: list[RepeatedIssueReport] = []

        try:
            pattern = "bmad:chiseai:brain:eval:repeated_issues:*"
            cursor = 0

            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                for key in keys:
                    try:
                        data = self.redis_client.get(key)
                        if data:
                            report = RepeatedIssueReport.from_json(data)
                            reports.append(report)
                    except Exception as e:
                        logger.error(f"Error loading report from {key}: {e}")
                        continue

                if cursor == 0 or len(reports) >= limit:
                    break

            # Sort by generation time descending
            reports.sort(key=lambda r: r.generated_at, reverse=True)
            return reports[:limit]

        except Exception as e:
            logger.error(f"Error getting recent reports: {e}")
            return []

    def get_report_by_id(self, report_id: str) -> RepeatedIssueReport | None:
        """Get a specific report by ID.

        Args:
            report_id: Report ID (timestamp format: YYYYMMDD_HHMMSS)

        Returns:
            RepeatedIssueReport if found, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            key = f"bmad:chiseai:brain:eval:repeated_issues:{report_id}"
            data = self.redis_client.get(key)

            if data:
                return RepeatedIssueReport.from_json(data)

        except Exception as e:
            logger.error(f"Error loading report {report_id}: {e}")

        return None
