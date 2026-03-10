"""Trend rollup computation engine for KPI aggregation.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides rolling aggregate computation for evaluation KPIs across
multiple time windows (24h, 7d, 30d).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


def get_redis_client() -> Any | None:
    """Create and return a Redis client with proper configuration.

    Returns:
        Redis client or None if connection fails
    """
    try:
        import redis

        # Use host.docker.internal for Docker container connectivity
        # or localhost when on host machine
        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))
        # Always use DB 0 for iterlog data (bmad:chiseai:* keys are stored here)
        db = 0

        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )

        # Test connection
        client.ping()
        logger.info(f"Connected to Redis at {host}:{port}")
        return client

    except ImportError:
        logger.warning("redis package not installed")
        return None
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None


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
            redis_client: Optional Redis client for reading KPI data.
                If None, will auto-connect using get_redis_client().
            output_dir: Directory for rollup artifacts
        """
        self.redis_client = redis_client or get_redis_client()
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
        """Collect issues from Redis iterlog data.

        Reads from Redis iterlog keys:
        - bmad:chiseai:iterlog:story:*:incidents - Incident records
        - bmad:chiseai:iterlog:story:* - Story metadata

        Args:
            hours: Time window in hours

        Returns:
            List of issue dictionaries
        """
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

        if not self.redis_client:
            logger.warning("No Redis client configured, returning empty issue list")
            return []

        # Use the module-level function for consistency
        return _collect_incidents(self.redis_client, cutoff_time)

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


def calculate_kpis(
    window: str = "7d",
    redis_client: Any | None = None,
) -> dict[str, Any]:
    """Calculate KPIs from real iterlog data.

    This function extracts actionable metrics from Redis iterlog data:
    - cycle_time_hours: Time from started_at to completed_at
    - test_count: Number of tests from test_results
    - recurring_issue_rate: Pattern of repeated incidents
    - median_time_lost_minutes: Median incident resolution time
    - unresolved_issue_age: Age of issues still in progress
    - top_fingerprint_repeat_count: Most repeated issue pattern
    - fix_reopen_rate: Rate of reopened stories

    Args:
        window: Time window (24h, 7d, 30d)
        redis_client: Optional Redis client (will create if None)

    Returns:
        Dictionary with KPI values and metadata
    """
    # Get or create Redis client
    if redis_client is None:
        redis_client = get_redis_client()

    if not redis_client:
        return {
            "status": "error",
            "message": "No Redis connection available",
            "kpis": {
                "cycle_time_hours": 0.0,
                "test_count": 0,
                "recurring_issue_rate": 0.0,
                "median_time_lost_minutes": 0.0,
                "unresolved_issue_age_hours": 0.0,
                "top_fingerprint_repeat_count": 0,
                "fix_reopen_rate": 0.0,
            },
            "data_points": 0,
        }

    # Parse window
    window_hours = {"24h": 24, "7d": 7 * 24, "30d": 30 * 24}.get(window, 7 * 24)
    cutoff_time = datetime.now(UTC) - timedelta(hours=window_hours)

    # Collect iterlog data
    stories = _collect_iterlog_stories(redis_client, cutoff_time)
    incidents = _collect_incidents(redis_client, cutoff_time)

    # Calculate KPIs
    kpis = {
        "cycle_time_hours": _calculate_cycle_time(stories),
        "test_count": _calculate_test_count(stories),
        "recurring_issue_rate": _calculate_recurring_issue_rate(incidents),
        "median_time_lost_minutes": _calculate_median_time_lost(incidents),
        "unresolved_issue_age_hours": _calculate_unresolved_age(stories),
        "top_fingerprint_repeat_count": _calculate_top_fingerprint_repeats(incidents),
        "fix_reopen_rate": _calculate_fix_reopen_rate(stories),
    }

    return {
        "status": "success",
        "window": window,
        "kpis": kpis,
        "data_points": {"stories": len(stories), "incidents": len(incidents)},
        "computed_at": datetime.now(UTC).isoformat(),
    }


def _collect_iterlog_stories(redis_client: Any, cutoff_time: datetime) -> list[dict]:
    """Collect story iterlog data from Redis hashes.

    Args:
        redis_client: Redis client
        cutoff_time: Cutoff time for filtering

    Returns:
        List of story data dictionaries
    """
    stories = []

    try:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(
                cursor=cursor,
                match="bmad:chiseai:iterlog:story:*",
                count=100,
            )

            # Filter out sub-keys (decisions, incidents, learnings, etc.)
            # Sub-keys have additional colons after the story_id
            sub_key_suffixes = (
                ":decisions",
                ":incidents",
                ":learnings",
                ":events",
                ":evidence",
                ":ci-sync",
                ":meta",
            )
            story_keys = [
                k
                for k in keys
                if not any(k.endswith(suffix) for suffix in sub_key_suffixes)
            ]

            for key in story_keys:
                try:
                    # Check key type first to avoid WRONGTYPE errors
                    key_type = redis_client.type(key)
                    if key_type != "hash":
                        logger.debug(f"Skipping non-hash key {key} (type: {key_type})")
                        continue

                    # Use HGETALL for hash data
                    story_data = redis_client.hgetall(key)
                    if not story_data:
                        continue

                    # Extract story_id from key
                    story_id = key.split(":")[-1]
                    story_data["story_id"] = story_id
                    story_data["redis_key"] = key

                    # Parse timestamps for filtering
                    # Check multiple timestamp fields
                    timestamps_to_check = []
                    for ts_field in [
                        "started_at",
                        "completed_at",
                        "updated_at",
                        "created_at",
                    ]:
                        ts = story_data.get(ts_field, "")
                        if ts:
                            timestamps_to_check.append(ts)

                    # If any timestamp is within window, include the story
                    story_in_window = False
                    if not timestamps_to_check:
                        # No timestamps, include anyway (assume recent)
                        story_in_window = True
                    else:
                        for ts in timestamps_to_check:
                            try:
                                # Handle various timestamp formats
                                ts_clean = ts.replace("Z", "+00:00")
                                story_time = datetime.fromisoformat(ts_clean)
                                # Ensure timezone-aware
                                if story_time.tzinfo is None:
                                    story_time = story_time.replace(tzinfo=UTC)
                                if story_time >= cutoff_time:
                                    story_in_window = True
                                    break
                            except (ValueError, TypeError):
                                continue

                    if not story_in_window:
                        continue

                    stories.append(story_data)

                except Exception as e:
                    logger.warning(f"Error reading story {key}: {e}")
                    continue

            if cursor == 0:
                break

    except Exception as e:
        logger.error(f"Error collecting stories: {e}")

    logger.info(f"Collected {len(stories)} stories from iterlog")
    return stories


def _collect_incidents(redis_client: Any, cutoff_time: datetime) -> list[dict]:
    """Collect incidents from Redis lists.

    Args:
        redis_client: Redis client
        cutoff_time: Cutoff time for filtering

    Returns:
        List of incident dictionaries
    """
    incidents = []

    try:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(
                cursor=cursor,
                match="bmad:chiseai:iterlog:story:*:incidents",
                count=100,
            )

            for key in keys:
                try:
                    # Get incident list
                    incident_list = redis_client.lrange(key, 0, -1)
                    story_id = (
                        key.split(":")[4] if len(key.split(":")) > 4 else "unknown"
                    )

                    for incident_json in incident_list:
                        try:
                            incident = json.loads(incident_json)
                            incident["story_id"] = story_id
                            incident["source_key"] = key

                            # Check timestamp if available
                            incident_time = incident.get("timestamp") or incident.get(
                                "occurred_at"
                            )
                            if incident_time:
                                try:
                                    t = datetime.fromisoformat(
                                        incident_time.replace("Z", "+00:00")
                                    )
                                    if t < cutoff_time:
                                        continue
                                except (ValueError, TypeError):
                                    pass

                            incidents.append(incident)
                        except json.JSONDecodeError:
                            # Raw string incident
                            incidents.append(
                                {
                                    "description": incident_json,
                                    "story_id": story_id,
                                    "source_key": key,
                                }
                            )

                except Exception as e:
                    logger.warning(f"Error reading incidents from {key}: {e}")
                    continue

            if cursor == 0:
                break

    except Exception as e:
        logger.error(f"Error collecting incidents: {e}")

    logger.info(f"Collected {len(incidents)} incidents")
    return incidents


def _calculate_cycle_time(stories: list[dict]) -> float:
    """Calculate median cycle time in hours.

    Args:
        stories: List of story data

    Returns:
        Median cycle time in hours
    """
    cycle_times = []

    for story in stories:
        started_at = story.get("started_at")
        completed_at = story.get("completed_at")

        if started_at and completed_at:
            try:
                start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                hours = (end - start).total_seconds() / 3600
                if hours > 0:
                    cycle_times.append(hours)
            except (ValueError, TypeError):
                continue

    if not cycle_times:
        return 0.0

    return float(statistics.median(cycle_times))


def _calculate_test_count(stories: list[dict]) -> int:
    """Calculate total test count from stories.

    Args:
        stories: List of story data

    Returns:
        Total number of tests
    """
    total_tests = 0

    for story in stories:
        # Look for test_results field
        test_results = story.get("test_results", "")
        if test_results:
            try:
                # Try to parse as JSON
                if isinstance(test_results, str):
                    test_data = json.loads(test_results)
                else:
                    test_data = test_results

                if isinstance(test_data, dict):
                    total_tests += test_data.get("total", 0)
                    total_tests += test_data.get("passed", 0)
                    total_tests += test_data.get("failed", 0)
                elif isinstance(test_data, list):
                    total_tests += len(test_data)
            except json.JSONDecodeError:
                # Count mentions of "test" in the string
                total_tests += test_results.lower().count("test")

        # Also check for test_count field directly
        test_count = story.get("test_count", 0)
        if test_count:
            with contextlib.suppress(ValueError, TypeError):
                total_tests += int(test_count)

    return total_tests


def _calculate_recurring_issue_rate(incidents: list[dict]) -> float:
    """Calculate rate of recurring issues.

    Args:
        incidents: List of incident data

    Returns:
        Rate between 0.0 and 1.0
    """
    if not incidents:
        return 0.0

    # Group incidents by fingerprint or description pattern
    fingerprint_counts: dict[str, int] = {}

    for incident in incidents:
        # Try to get fingerprint
        fp = incident.get("fingerprint", "")
        if not fp:
            # Use description hash as fingerprint
            desc = incident.get("description", "")
            if desc:
                import hashlib

                fp = hashlib.sha256(desc.lower().encode()).hexdigest()[:16]

        if fp:
            fingerprint_counts[fp] = fingerprint_counts.get(fp, 0) + 1

    # Count recurring incidents (appear more than once)
    recurring = sum(1 for count in fingerprint_counts.values() if count > 1)
    total = len(fingerprint_counts)

    if total == 0:
        return 0.0

    return recurring / total


def _calculate_median_time_lost(incidents: list[dict]) -> float:
    """Calculate median time lost to incidents in minutes.

    Args:
        incidents: List of incident data

    Returns:
        Median time lost in minutes
    """
    time_lost_values = []

    for incident in incidents:
        # Check for time_lost_minutes field
        time_lost = incident.get("time_lost_minutes")
        if time_lost is not None:
            try:
                time_lost_values.append(float(time_lost))
                continue
            except (ValueError, TypeError):
                pass

        # Calculate from occurred_at and resolved_at timestamps
        occurred = incident.get("occurred_at") or incident.get("timestamp")
        resolved = incident.get("resolved_at")

        if occurred and resolved:
            try:
                start = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
                end = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
                minutes = (end - start).total_seconds() / 60
                if minutes > 0:
                    time_lost_values.append(minutes)
            except (ValueError, TypeError):
                pass

    if not time_lost_values:
        return 0.0

    return float(statistics.median(time_lost_values))


def _calculate_unresolved_age(stories: list[dict]) -> float:
    """Calculate average age of unresolved stories in hours.

    Args:
        stories: List of story data

    Returns:
        Average age in hours
    """
    ages = []
    now = datetime.now(UTC)

    for story in stories:
        status = story.get("status", "").lower()

        # Consider "in_progress", "planned", "open" as unresolved
        if status in ("in_progress", "planned", "open", "active"):
            started_at = story.get("started_at")
            if started_at:
                try:
                    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    hours = (now - start).total_seconds() / 3600
                    if hours > 0:
                        ages.append(hours)
                except (ValueError, TypeError):
                    pass

    if not ages:
        return 0.0

    return float(statistics.mean(ages))


def _calculate_top_fingerprint_repeats(incidents: list[dict]) -> int:
    """Calculate count of most repeated incident fingerprint.

    Args:
        incidents: List of incident data

    Returns:
        Count of most repeated fingerprint
    """
    if not incidents:
        return 0

    fingerprint_counts: dict[str, int] = {}

    for incident in incidents:
        fp = incident.get("fingerprint", "")
        if not fp:
            desc = incident.get("description", "")
            if desc:
                import hashlib

                fp = hashlib.sha256(desc.lower().encode()).hexdigest()[:16]

        if fp:
            fingerprint_counts[fp] = fingerprint_counts.get(fp, 0) + 1

    if not fingerprint_counts:
        return 0

    return max(fingerprint_counts.values())


def _calculate_fix_reopen_rate(stories: list[dict]) -> float:
    """Calculate rate of reopened stories.

    Args:
        stories: List of story data

    Returns:
        Rate between 0.0 and 1.0
    """
    if not stories:
        return 0.0

    reopened_count = 0
    total_completed = 0

    for story in stories:
        status = story.get("status", "").lower()

        # Count as reopened if status indicates reopening
        if status in ("reopened", "re-opened"):
            reopened_count += 1
            total_completed += 1
        elif status in ("completed", "done", "closed"):
            total_completed += 1

    if total_completed == 0:
        return 0.0

    return reopened_count / total_completed
