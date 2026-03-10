"""KPI persistence layer for brain evaluation.

Provides persistence and retrieval of KPI snapshots with time-bucketed storage
in Redis and file artifact output. Supports hourly, daily, and weekly aggregation.

Redis Key Patterns:
    - Hourly: bmad:chiseai:brain:kpi:hourly:{YYYYMMDDHH}:{run_id}
    - Daily: bmad:chiseai:brain:kpi:daily:{YYYYMMDD}:{run_id}
    - Weekly: bmad:chiseai:brain:kpi:weekly:{YYYY-WNN}:{run_id}

TTL Configuration:
    - Hourly: 30 days (2,592,000 seconds)
    - Daily: 90 days (7,776,000 seconds)
    - Weekly: 90 days (7,776,000 seconds)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# TTL constants (in seconds)
HOURLY_TTL = 30 * 24 * 3600  # 30 days
DAILY_TTL = 90 * 24 * 3600  # 90 days
WEEKLY_TTL = 90 * 24 * 3600  # 90 days


@dataclass
class KPISnapshot:
    """KPI snapshot with provenance information.

    Attributes:
        kpi_data: The actual KPI metrics and values
        source: Source of the KPI measurement (e.g., 'brain_eval', 'backtest')
        measured_vs_proxy: Whether KPI is measured (actual) or proxy (estimated)
        run_id: Unique identifier for this evaluation run
        timestamp: ISO timestamp when snapshot was created
        bucket_type: Type of time bucket (hourly, daily, weekly)
        bucket_key: Time bucket key (e.g., '2026030214', '20260302', '2026-W09')
        metadata: Additional metadata
    """

    kpi_data: dict[str, Any]
    source: str
    measured_vs_proxy: str
    run_id: str
    timestamp: str
    bucket_type: str
    bucket_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "kpi_data": self.kpi_data,
            "source": self.source,
            "measured_vs_proxy": self.measured_vs_proxy,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "bucket_type": self.bucket_type,
            "bucket_key": self.bucket_key,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KPISnapshot:
        """Create from dictionary."""
        return cls(
            kpi_data=data["kpi_data"],
            source=data["source"],
            measured_vs_proxy=data["measured_vs_proxy"],
            run_id=data["run_id"],
            timestamp=data["timestamp"],
            bucket_type=data["bucket_type"],
            bucket_key=data["bucket_key"],
            metadata=data.get("metadata", {}),
        )


class KPIPersistenceError(Exception):
    """Base exception for KPI persistence errors."""

    pass


class NonCanonicalSourceError(KPIPersistenceError):
    """Raised when non-canonical source is used for GO gate decisions."""

    pass


# Canonical source configuration
CANONICAL_SOURCE = "bybit_truth"
NON_CANONICAL_SOURCES = ["paper_journal_sim"]


def validate_canonical_source(
    kpi_source: str,
    trading_mode: str,
    enforce: bool = True,
) -> tuple[bool, str]:
    """Validate that KPI source is canonical for GO gate decisions.

    This is a HARD GUARDRAIL - enforces that only bybit_truth can be used
    for GO gate decisions in demo/live trading modes.

    Args:
        kpi_source: The KPI source identifier (e.g., 'bybit_truth', 'paper_journal_sim')
        trading_mode: Trading mode ('demo', 'live', 'paper', 'backtest')
        enforce: If True, raises exception on validation failure.
                 If False, returns (False, reason) without raising.

    Returns:
        Tuple of (is_valid, reason) where:
        - is_valid: True if source is canonical for the trading mode
        - reason: Human-readable explanation

    Raises:
        NonCanonicalSourceError: If enforce=True and source is not canonical
                                 for demo/live trading modes

    Examples:
        >>> validate_canonical_source("bybit_truth", "demo")
        (True, "Source 'bybit_truth' is canonical for demo trading mode")

        >>> validate_canonical_source("paper_journal_sim", "demo")
        Traceback (most recent call last):
            ...
        NonCanonicalSourceError: Source 'paper_journal_sim' is NOT canonical...
    """
    # Normalize inputs
    kpi_source = kpi_source.lower().strip()
    trading_mode = trading_mode.lower().strip()

    # Define which sources are canonical for which modes
    canonical_sources_by_mode = {
        "demo": ["bybit_truth"],
        "live": ["bybit_truth"],
        "paper": ["paper_journal_sim"],  # Paper mode only allows paper source
        "backtest": ["paper_journal_sim", "backtest_sim"],
    }

    # Get canonical sources for this mode
    mode_canonical = canonical_sources_by_mode.get(trading_mode, [])

    # Check if source is canonical for this mode
    is_canonical = kpi_source in mode_canonical

    if is_canonical:
        reason = f"Source '{kpi_source}' is canonical for {trading_mode} trading mode"
        return True, reason

    # Source is not canonical - determine appropriate message
    if kpi_source == "bybit_truth" and trading_mode == "paper":
        reason = (
            f"Source '{kpi_source}' is NOT expected in {trading_mode} mode. "
            f"Paper mode should use 'paper_journal_sim' source. "
            f"This may indicate data contamination."
        )
    elif kpi_source in NON_CANONICAL_SOURCES and trading_mode in ["demo", "live"]:
        reason = (
            f"Source '{kpi_source}' is NOT canonical for {trading_mode} trading mode. "
            f"GO gate decisions in {trading_mode} mode MUST use '{CANONICAL_SOURCE}'. "
            f"Using non-canonical source for GO gates is PROHIBITED."
        )
    else:
        reason = (
            f"Source '{kpi_source}' is not recognized as canonical for {trading_mode} mode. "
            f"Canonical sources for {trading_mode}: {mode_canonical}"
        )

    # Raise exception if enforcing
    if enforce and trading_mode in ["demo", "live"]:
        raise NonCanonicalSourceError(reason)

    return False, reason


def is_source_canonical_for_go(kpi_source: str, trading_mode: str) -> bool:
    """Check if source is canonical for GO gates without raising.

    Args:
        kpi_source: The KPI source identifier
        trading_mode: Trading mode ('demo', 'live', 'paper', 'backtest')

    Returns:
        True if source is canonical for GO gates in the given mode
    """
    is_valid, _ = validate_canonical_source(kpi_source, trading_mode, enforce=False)
    return is_valid


class KPIPersistence:
    """Persists and retrieves KPI snapshots with time-bucketed storage.

    Stores KPI snapshots in Redis with time-based bucketing and exports
    to file artifacts for long-term storage and analysis.

    Attributes:
        redis_client: Optional Redis client for persistence
        output_dir: Directory for file artifact output

    Examples:
        >>> persistence = KPIPersistence(redis_client=redis)
        >>> snapshot = persistence.persist_kpi_snapshot(
        ...     kpi_data={"accuracy": 0.95, "f1_score": 0.92},
        ...     source="brain_eval",
        ...     run_id="eval-20260302-001"
        ... )
        >>> print(snapshot.bucket_type)
        'daily'
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        output_dir: str | Path = "_bmad-output/brain-eval/kpi-snapshots",
    ) -> None:
        """Initialize KPI persistence layer.

        Args:
            redis_client: Optional Redis client for persistence
            output_dir: Directory for file artifact output
        """
        self.redis_client = redis_client
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def persist_kpi_snapshot(
        self,
        kpi_data: dict[str, Any],
        source: str,
        run_id: str,
        measured_vs_proxy: str = "measured",
        metadata: dict[str, Any] | None = None,
    ) -> KPISnapshot:
        """Persist KPI snapshot to Redis and file artifact.

        Creates time-bucketed keys in Redis (hourly, daily, weekly) and
        exports snapshot to file artifact.

        Args:
            kpi_data: KPI metrics and values to persist
            source: Source of the KPI measurement
            run_id: Unique identifier for this run
            measured_vs_proxy: Whether KPI is measured or proxy
            metadata: Additional metadata

        Returns:
            KPISnapshot with provenance information

        Raises:
            KPIPersistenceError: If persistence fails
        """
        timestamp = datetime.now(UTC).isoformat()

        # Create snapshots for each bucket type
        snapshots = []
        for bucket_type in ["hourly", "daily", "weekly"]:
            bucket_key = self._get_bucket_key(timestamp, bucket_type)
            snapshot = KPISnapshot(
                kpi_data=kpi_data,
                source=source,
                measured_vs_proxy=measured_vs_proxy,
                run_id=run_id,
                timestamp=timestamp,
                bucket_type=bucket_type,
                bucket_key=bucket_key,
                metadata=metadata or {},
            )
            snapshots.append(snapshot)

            # Store in Redis
            self._store_in_redis(snapshot)

        # Export primary snapshot (daily) to file
        daily_snapshot = snapshots[1]  # Daily is the primary
        filepath = self._get_artifact_path(daily_snapshot)
        self.export_to_file(daily_snapshot, filepath)

        logger.info(
            f"Persisted KPI snapshot for run {run_id} from {source} "
            f"to buckets: hourly, daily, weekly"
        )

        return daily_snapshot

    def get_kpi_snapshots(
        self,
        bucket: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[KPISnapshot]:
        """Query KPI snapshots by time range.

        Args:
            bucket: Bucket type (hourly, daily, weekly)
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of KPISnapshot objects within the time range

        Raises:
            KPIPersistenceError: If query fails
        """
        if not self.redis_client:
            logger.warning("No Redis client available for querying snapshots")
            return []

        if bucket not in ["hourly", "daily", "weekly"]:
            raise KPIPersistenceError(
                f"Invalid bucket type: {bucket}. Must be hourly, daily, or weekly."
            )

        try:
            snapshots = []
            pattern = f"bmad:chiseai:brain:kpi:{bucket}:*"

            # Scan for keys matching pattern
            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        snapshot = KPISnapshot.from_dict(json.loads(data))

                        # Parse timestamp and check range
                        snapshot_time = datetime.fromisoformat(
                            snapshot.timestamp.replace("Z", "+00:00")
                        )

                        if start_time <= snapshot_time <= end_time:
                            snapshots.append(snapshot)

                if cursor == 0:
                    break

            # Sort by timestamp
            snapshots.sort(key=lambda s: s.timestamp)
            return snapshots

        except Exception as e:
            logger.error(f"Failed to query KPI snapshots: {e}")
            raise KPIPersistenceError(f"Failed to query snapshots: {e}") from e

    def get_latest_snapshot(self, source: str) -> KPISnapshot | None:
        """Get most recent KPI snapshot for a source.

        Args:
            source: Source to query (e.g., 'brain_eval', 'backtest')

        Returns:
            Most recent KPISnapshot for the source, or None if not found
        """
        if not self.redis_client:
            logger.warning("No Redis client available for querying snapshots")
            return None

        try:
            # Query daily bucket for latest
            pattern = "bmad:chiseai:brain:kpi:daily:*"
            latest_snapshot = None
            latest_timestamp = None

            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        snapshot = KPISnapshot.from_dict(json.loads(data))

                        if snapshot.source == source:
                            timestamp = datetime.fromisoformat(
                                snapshot.timestamp.replace("Z", "+00:00")
                            )

                            if latest_timestamp is None or timestamp > latest_timestamp:
                                latest_timestamp = timestamp
                                latest_snapshot = snapshot

                if cursor == 0:
                    break

            return latest_snapshot

        except Exception as e:
            logger.error(f"Failed to get latest snapshot for source {source}: {e}")
            return None

    def export_to_file(
        self, snapshot: KPISnapshot, filepath: Path | None = None
    ) -> Path:
        """Export KPI snapshot to file artifact.

        Args:
            snapshot: KPISnapshot to export
            filepath: Optional custom filepath. If None, generates from snapshot.

        Returns:
            Path to the exported file

        Raises:
            KPIPersistenceError: If export fails
        """
        if filepath is None:
            filepath = self._get_artifact_path(snapshot)

        try:
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON artifact
            with open(filepath, "w") as f:
                json.dump(snapshot.to_dict(), f, indent=2)

            logger.info(f"Exported KPI snapshot to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to export KPI snapshot to file: {e}")
            raise KPIPersistenceError(f"Failed to export snapshot: {e}") from e

    def check_bybit_truth_freshness(
        self,
        threshold_hours: float = 24.0,
    ) -> dict[str, Any]:
        """Check if bybit_truth data is fresh before loading KPIs.

        Queries Redis for the last collection timestamp and determines
        if the data is stale. Returns a warning if data is stale.

        Args:
            threshold_hours: Hours before data is considered stale

        Returns:
            Dictionary with freshness status and warning information
        """
        result = {
            "is_fresh": False,
            "status": "unknown",
            "reason": "unknown",
            "hours_since_collection": 0.0,
            "last_collection_timestamp": None,
            "last_collection_count": 0,
            "warning": None,
        }

        if not self.redis_client:
            result["status"] = "error"
            result["reason"] = "no_redis_client"
            result["warning"] = "No Redis client available for freshness check"
            return result

        try:
            # Fetch collection metadata from Redis
            timestamp_str = self.redis_client.get(
                "bmad:chiseai:bybit_truth:last_collection_timestamp"
            )
            count_str = self.redis_client.get(
                "bmad:chiseai:bybit_truth:last_collection_count"
            )
            status_str = self.redis_client.get(
                "bmad:chiseai:bybit_truth:last_collection_status"
            )

            result["last_collection_count"] = int(count_str) if count_str else 0

            # Check if we have any collection data
            if not timestamp_str:
                result["status"] = "stale"
                result["reason"] = "no_collection"
                result["warning"] = (
                    "WARNING: No bybit_truth collection data found in Redis. "
                    "KPIs may be based on stale data."
                )
                return result

            result["last_collection_timestamp"] = timestamp_str

            # Parse timestamp
            try:
                if timestamp_str.endswith("Z"):
                    timestamp_str = timestamp_str[:-1] + "+00:00"
                last_collection = datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                result["status"] = "error"
                result["reason"] = "invalid_timestamp"
                result["warning"] = (
                    f"WARNING: Invalid collection timestamp in Redis: {timestamp_str}"
                )
                return result

            # Calculate hours since collection
            now = datetime.now(UTC)
            if last_collection.tzinfo is None:
                last_collection = last_collection.replace(tzinfo=UTC)

            hours_since = (now - last_collection).total_seconds() / 3600
            result["hours_since_collection"] = round(hours_since, 2)

            # Check if collection had an error
            if status_str == "api_error":
                result["status"] = "stale"
                result["reason"] = "api_error"
                result["warning"] = (
                    f"WARNING: Last bybit_truth collection failed with API error "
                    f"({hours_since:.1f}h ago). KPIs may be based on stale data."
                )
                return result

            if status_str == "redis_error":
                result["status"] = "stale"
                result["reason"] = "redis_error"
                result["warning"] = (
                    f"WARNING: Last bybit_truth collection failed with Redis error "
                    f"({hours_since:.1f}h ago). KPIs may be based on stale data."
                )
                return result

            # Check if data is stale based on threshold
            if hours_since > threshold_hours:
                result["is_fresh"] = False
                result["status"] = "stale"
                result["reason"] = "old_data"
                result["warning"] = (
                    f"WARNING: bybit_truth data is stale "
                    f"({hours_since:.1f}h > {threshold_hours}h threshold). "
                    f"KPIs may be based on outdated data."
                )
                return result

            # Data is fresh
            result["is_fresh"] = True
            result["status"] = "fresh"
            result["reason"] = "fresh"
            result["warning"] = None

        except Exception as e:
            result["status"] = "error"
            result["reason"] = "redis_error"
            result["warning"] = f"WARNING: Redis error during freshness check: {e}"

        return result

    def _store_in_redis(self, snapshot: KPISnapshot) -> None:
        """Store snapshot in Redis with appropriate TTL.

        Args:
            snapshot: KPISnapshot to store
        """
        if not self.redis_client:
            logger.debug("No Redis client, skipping Redis storage")
            return

        try:
            # Construct Redis key
            key = (
                f"bmad:chiseai:brain:kpi:{snapshot.bucket_type}:"
                f"{snapshot.bucket_key}:{snapshot.run_id}"
            )

            # Determine TTL based on bucket type
            ttl_map = {
                "hourly": HOURLY_TTL,
                "daily": DAILY_TTL,
                "weekly": WEEKLY_TTL,
            }
            ttl = ttl_map.get(snapshot.bucket_type, DAILY_TTL)

            # Store with TTL
            self.redis_client.set(key, json.dumps(snapshot.to_dict()), ex=ttl)

            logger.debug(f"Stored KPI snapshot in Redis: {key} (TTL: {ttl}s)")

        except Exception as e:
            logger.error(f"Failed to store snapshot in Redis: {e}")
            # Don't raise - Redis failure shouldn't block the operation

    def _get_bucket_key(self, timestamp: str, bucket_type: str) -> str:
        """Generate time bucket key from timestamp.

        Args:
            timestamp: ISO timestamp
            bucket_type: Type of bucket (hourly, daily, weekly)

        Returns:
            Bucket key string (e.g., '2026030214', '20260302', '2026-W09')
        """
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        if bucket_type == "hourly":
            # Format: YYYYMMDDHH
            return dt.strftime("%Y%m%d%H")
        elif bucket_type == "daily":
            # Format: YYYYMMDD
            return dt.strftime("%Y%m%d")
        elif bucket_type == "weekly":
            # Format: YYYY-WNN (ISO week)
            return dt.strftime("%Y-W%V")
        else:
            raise KPIPersistenceError(f"Unknown bucket type: {bucket_type}")

    def _get_artifact_path(self, snapshot: KPISnapshot) -> Path:
        """Generate file artifact path for snapshot.

        Args:
            snapshot: KPISnapshot to generate path for

        Returns:
            Path object for the artifact file
        """
        # Structure: output_dir/bucket_type/source/YYYY/MM/DD/run_id.json
        dt = datetime.fromisoformat(snapshot.timestamp.replace("Z", "+00:00"))

        filename = f"{snapshot.run_id}.json"
        filepath = (
            self.output_dir
            / snapshot.bucket_type
            / snapshot.source
            / dt.strftime("%Y")
            / dt.strftime("%m")
            / dt.strftime("%d")
            / filename
        )

        return filepath
