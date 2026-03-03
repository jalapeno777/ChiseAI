"""Trend rollup computation engine for KPI aggregation.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides rolling aggregate computation for evaluation KPIs across
multiple time windows (24h, 7d, 30d).
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


@dataclass
class TrendRollup:
    """Represents a trend rollup artifact.

    Attributes:
        window: Time window (24h, 7d, 30d)
        computed_at: Timestamp when rollup was computed
        source: Data source identifier
        kpis: Dictionary of KPI values
        data_points_count: Number of data points used in computation
        provenance: Source metadata
    """

    window: str
    computed_at: datetime
    source: str
    kpis: dict[str, float | int | str]
    data_points_count: int
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "window": self.window,
            "computed_at": self.computed_at.isoformat(),
            "source": self.source,
            "kpis": self.kpis,
            "data_points_count": self.data_points_count,
            "provenance": self.provenance,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrendRollup:
        """Create from dictionary."""
        return cls(
            window=data["window"],
            computed_at=datetime.fromisoformat(data["computed_at"]),
            source=data["source"],
            kpis=data["kpis"],
            data_points_count=data["data_points_count"],
            provenance=data.get("provenance", {}),
        )


class TrendRollupEngine:
    """Computes rolling aggregate KPIs for trend analysis.

    Provides capabilities to:
    - Compute KPI aggregates across multiple time windows
    - Read issue data from Redis (ST-KPI-001 persistence layer)
    - Export rollup artifacts to _bmad-output/brain-eval/trends/

    Example:
        >>> engine = TrendRollupEngine(redis_client=redis)
        >>> rollups = engine.compute_all_rollups(source="brain-eval")
        >>> engine.export_rollup_artifact(rollups["24h"], "trends/24h-20260302.json")
    """

    # Time window definitions
    WINDOWS = {
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
    }

    def __init__(
        self,
        redis_client: Any | None = None,
        output_dir: str = "_bmad-output/brain-eval/trends",
    ) -> None:
        """Initialize the trend rollup engine.

        Args:
            redis_client: Optional Redis client for reading KPI data
            output_dir: Directory for rollup artifacts
        """
        self.redis_client = redis_client
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def compute_24h_rollups(self, source: str = "brain-eval") -> TrendRollup:
        """Compute 24-hour aggregate KPIs.

        Args:
            source: Data source identifier

        Returns:
            TrendRollup with 24h aggregates
        """
        return self._compute_rollups("24h", source)

    def compute_7d_rollups(self, source: str = "brain-eval") -> TrendRollup:
        """Compute 7-day aggregate KPIs.

        Args:
            source: Data source identifier

        Returns:
            TrendRollup with 7d aggregates
        """
        return self._compute_rollups("7d", source)

    def compute_30d_rollups(self, source: str = "brain-eval") -> TrendRollup:
        """Compute 30-day aggregate KPIs.

        Args:
            source: Data source identifier

        Returns:
            TrendRollup with 30d aggregates
        """
        return self._compute_rollups("30d", source)

    def compute_all_rollups(self, source: str = "brain-eval") -> dict[str, TrendRollup]:
        """Compute all time window rollups.

        Args:
            source: Data source identifier

        Returns:
            Dictionary mapping window name to TrendRollup
        """
        return {
            "24h": self.compute_24h_rollups(source),
            "7d": self.compute_7d_rollups(source),
            "30d": self.compute_30d_rollups(source),
        }

    def _compute_rollups(self, window: str, source: str) -> TrendRollup:
        """Compute rollups for a specific time window.

        Args:
            window: Time window (24h, 7d, 30d)
            source: Data source identifier

        Returns:
            TrendRollup with computed KPIs
        """
        logger.info(f"Computing {window} rollups for source: {source}")

        hours = self.WINDOWS.get(window, 24)
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

        # Collect issues from Redis
        issues = self._collect_issues(hours)

        # Compute KPIs
        kpis = {
            "recurring_issue_rate": self._compute_recurring_issue_rate(issues),
            "median_time_lost_minutes": self._compute_median_time_lost_minutes(issues),
            "unresolved_issue_age": self._compute_unresolved_issue_age(
                issues, cutoff_time
            ),
            "top_fingerprint_repeat_count": self._compute_top_fingerprint_repeat_count(
                issues
            ),
            "fix_reopen_rate": self._compute_fix_reopen_rate(issues),
        }

        # Build provenance
        provenance = {
            "computation_method": "trend_rollup_engine",
            "redis_keys_scanned": "bmad:chiseai:kpi:*",
            "window_definition": f"{hours} hours",
            "story_id": "ST-KPI-002",
        }

        rollup = TrendRollup(
            window=window,
            computed_at=datetime.now(UTC),
            source=source,
            kpis=kpis,
            data_points_count=len(issues),
            provenance=provenance,
        )

        logger.info(
            f"Computed {window} rollup with {len(issues)} data points: "
            f"recurring_rate={kpis['recurring_issue_rate']:.2%}"
        )

        return rollup

    def _collect_issues(self, hours: int) -> list[dict]:
        """Collect issues from Redis KPI persistence layer.

        Reads from Redis keys established by ST-KPI-001:
        - bmad:chiseai:kpi:issues:* - Individual issue records
        - bmad:chiseai:kpi:clusters:* - Fingerprint cluster data

        Args:
            hours: Time window in hours

        Returns:
            List of issue dictionaries
        """
        issues: list[dict] = []
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

        if not self.redis_client:
            logger.warning("No Redis client configured, returning empty issue list")
            return issues

        try:
            # Scan for issue KPIs from ST-KPI-001 persistence layer
            pattern = "bmad:chiseai:kpi:issues:*"
            cursor = 0

            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                for key in keys:
                    try:
                        data = self.redis_client.get(key)
                        if data:
                            issue = json.loads(data)
                            issue_timestamp_str = issue.get("timestamp", "")

                            # Check if within time window
                            if issue_timestamp_str:
                                issue_time = datetime.fromisoformat(issue_timestamp_str)
                                if issue_time < cutoff_time:
                                    continue

                            issues.append(issue)

                    except Exception as e:
                        logger.error(f"Error processing key {key}: {e}")
                        continue

                if cursor == 0:
                    break

        except Exception as e:
            logger.error(f"Error collecting issues from Redis: {e}")

        logger.info(f"Collected {len(issues)} issues from Redis for last {hours}h")
        return issues

    def _compute_recurring_issue_rate(self, issues: list[dict]) -> float:
        """Compute the percentage of issues that are repeats.

        Args:
            issues: List of issue dictionaries

        Returns:
            Rate between 0.0 and 1.0
        """
        if not issues:
            return 0.0

        # Count issues with fingerprints that appear more than once
        fingerprint_counts: dict[str, int] = {}
        for issue in issues:
            fingerprint = issue.get("fingerprint", "")
            if fingerprint:
                fingerprint_counts[fingerprint] = (
                    fingerprint_counts.get(fingerprint, 0) + 1
                )

        # Count number of unique fingerprints that recur (appear more than once)
        recurring_fingerprint_count = sum(
            1 for count in fingerprint_counts.values() if count > 1
        )

        # Rate is recurring / total unique fingerprints
        total_unique = len(fingerprint_counts)
        if total_unique == 0:
            return 0.0

        return recurring_fingerprint_count / total_unique

    def _compute_median_time_lost_minutes(self, issues: list[dict]) -> float:
        """Compute median time lost to issues in minutes.

        Args:
            issues: List of issue dictionaries

        Returns:
            Median time lost in minutes
        """
        time_lost_values: list[float] = []

        for issue in issues:
            # Look for time_lost field (from issue metadata)
            time_lost = issue.get("metadata", {}).get("time_lost_minutes")
            if time_lost is not None:
                try:
                    time_lost_values.append(float(time_lost))
                except (ValueError, TypeError):
                    continue

        if not time_lost_values:
            return 0.0

        return float(statistics.median(time_lost_values))

    def _compute_unresolved_issue_age(
        self, issues: list[dict], cutoff_time: datetime
    ) -> float:
        """Compute average age of unresolved issues in hours.

        Args:
            issues: List of issue dictionaries
            cutoff_time: Cutoff time for the window

        Returns:
            Average age in hours
        """
        ages: list[float] = []
        now = datetime.now(UTC)

        for issue in issues:
            # Check if issue is unresolved
            resolved = issue.get("metadata", {}).get("resolved", False)
            if not resolved:
                timestamp_str = issue.get("timestamp", "")
                if timestamp_str:
                    try:
                        issue_time = datetime.fromisoformat(timestamp_str)
                        age_hours = (now - issue_time).total_seconds() / 3600
                        ages.append(age_hours)
                    except Exception:
                        continue

        if not ages:
            return 0.0

        return float(statistics.mean(ages))

    def _compute_top_fingerprint_repeat_count(self, issues: list[dict]) -> int:
        """Compute count of most repeated issue fingerprint.

        Args:
            issues: List of issue dictionaries

        Returns:
            Count of the most repeated fingerprint
        """
        fingerprint_counts: dict[str, int] = {}

        for issue in issues:
            fingerprint = issue.get("fingerprint", "")
            if fingerprint:
                fingerprint_counts[fingerprint] = (
                    fingerprint_counts.get(fingerprint, 0) + 1
                )

        if not fingerprint_counts:
            return 0

        return max(fingerprint_counts.values())

    def _compute_fix_reopen_rate(self, issues: list[dict]) -> float:
        """Compute fix reopen rate.

        NOTE: This metric is not yet implementable due to missing data tracking
        in the KPI persistence layer. To implement this metric, the following
        data structures and tracking are required:

        1. Issue lifecycle state tracking (open -> in_progress -> fixed)
        2. Reopen event logging (when a fixed issue recurs with same fingerprint)
        3. Temporal correlation between fix timestamps and subsequent occurrences
        4. Fix metadata (who fixed, when fixed, fix method)

        BACKLOG TRACKING:
        - Story: ST-KPI-003 (hypothetical future story)
        - Title: Add fix/reopen tracking to issue lifecycle
        - Description: Extend ST-KPI-001 persistence layer to track issue state
          transitions and reopen events for calculating fix_reopen_rate.

        Returns:
            0.0 (placeholder value until tracking infrastructure is available)
        """
        logger.warning(
            "fix_reopen_rate is a placeholder - requires fix tracking data "
            "not yet available in ST-KPI-001 persistence layer. "
            "See docstring for implementation requirements."
        )
        return 0.0

    def export_rollup_artifact(
        self, rollup: TrendRollup, filepath: str | None = None
    ) -> Path:
        """Export a rollup artifact to disk.

        Args:
            rollup: TrendRollup to export
            filepath: Optional custom filepath (relative to output_dir)

        Returns:
            Path to the exported artifact
        """
        if filepath:
            output_path = self.output_dir / filepath
        else:
            # Generate default filename: {window}-{timestamp}.json
            timestamp = rollup.computed_at.strftime("%Y%m%d-%H%M%S")
            filename = f"{rollup.window}-{timestamp}.json"
            output_path = self.output_dir / filename

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write artifact
        output_path.write_text(rollup.to_json())

        logger.info(f"Exported rollup artifact to: {output_path}")
        return output_path

    def export_all_rollups(self, rollups: dict[str, TrendRollup]) -> dict[str, Path]:
        """Export all rollup artifacts.

        Args:
            rollups: Dictionary of window name to TrendRollup

        Returns:
            Dictionary mapping window name to exported path
        """
        paths: dict[str, Path] = {}

        for window, rollup in rollups.items():
            path = self.export_rollup_artifact(rollup)
            paths[window] = path

        return paths

    def get_recent_rollups(self, limit: int = 10) -> list[TrendRollup]:
        """Get recent rollup artifacts from disk.

        Args:
            limit: Maximum number of rollups to return

        Returns:
            List of TrendRollup objects sorted by computed_at (newest first)
        """
        rollups: list[TrendRollup] = []

        try:
            # Find all JSON files in output directory
            json_files = list(self.output_dir.glob("*.json"))

            for json_file in json_files[:limit]:
                try:
                    data = json.loads(json_file.read_text())
                    rollup = TrendRollup.from_dict(data)
                    rollups.append(rollup)
                except Exception as e:
                    logger.error(f"Error loading rollup from {json_file}: {e}")
                    continue

            # Sort by computed_at descending
            rollups.sort(key=lambda r: r.computed_at, reverse=True)
            return rollups[:limit]

        except Exception as e:
            logger.error(f"Error getting recent rollups: {e}")
            return []
