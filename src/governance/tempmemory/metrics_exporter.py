"""
Tempmemory Metrics Exporter for ChiseAI Governance.

Exports metrics related to tempmemory ingestion,
migration statistics, and file processing.

Story: ST-MEMORY-INGEST-002
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.governance.metrics.base_exporter import (
    BaseMetricsExporter,
    MetricPoint,
    MetricType,
)

logger = logging.getLogger(__name__)

# Redis keys for tempmemory metrics
TEMPMEMORY_PREFIX = "bmad:chiseai:tempmemory"
INGESTION_STATUS_KEY = f"{TEMPMEMORY_PREFIX}:ingestion:status"
MIGRATION_STATUS_KEY = f"{TEMPMEMORY_PREFIX}:migration:status"
INGESTION_HASHES_KEY = f"{TEMPMEMORY_PREFIX}:ingestion:hashes"
PROVENANCE_PREFIX = f"{TEMPMEMORY_PREFIX}:provenance"


class TempmemoryMetricsExporter(BaseMetricsExporter):
    """
    Metrics exporter for the Tempmemory Ingestion governance feature.

    Collects and exports:
    - Ingestion statistics (files processed, success/failed counts)
    - Migration metrics (files migrated, success rate)
    - Ingestion duration and latency
    - Files by type (decision, pattern, summary, anti-pattern)
    - Feature flag state

    Example:
        exporter = TempmemoryMetricsExporter(redis_client=redis)
        points = exporter.collect()
        # Returns metrics about tempmemory ingestion
    """

    def __init__(
        self,
        influx_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the tempmemory metrics exporter.

        Args:
            influx_client: Optional InfluxDB client
            redis_client: Optional Redis client for reading metrics
        """
        super().__init__(
            feature_name="tempmemory",
            influx_client=influx_client,
            redis_client=redis_client,
        )

    def collect(self) -> list[MetricPoint]:
        """
        Collect tempmemory-related metrics.

        Returns:
            List of MetricPoint objects with tempmemory metrics
        """
        points: list[MetricPoint] = []
        now = datetime.now(UTC)

        # Get ingestion status from Redis
        ingestion_status = self._get_ingestion_status()
        migration_status = self._get_migration_status()

        # 1. Files ingested (counter)
        files_ingested = ingestion_status.get("total_files_ingested", 0)
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.files",
                value=float(files_ingested),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "tempmemory", "status": "ingested"},
            )
        )

        # 2. Files failed (counter)
        files_failed = ingestion_status.get("total_files_failed", 0)
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.files",
                value=float(files_failed),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "tempmemory", "status": "failed"},
            )
        )

        # 3. Files processed total
        files_processed = ingestion_status.get("total_files_processed", 0)
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.files",
                value=float(files_processed),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "tempmemory", "status": "processed"},
            )
        )

        # 4. Success rate (gauge)
        if files_processed > 0:
            success_rate = (files_ingested / files_processed) * 100
        else:
            success_rate = 0.0
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.success_rate",
                value=success_rate,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
                fields={"unit": "percent"},
            )
        )

        # 5. Ingestion duration (gauge)
        duration = ingestion_status.get("duration_seconds", 0)
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.duration",
                value=duration,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
                fields={"unit": "seconds"},
            )
        )

        # 6. Migration files
        migration_total = migration_status.get("total_files", 0)
        migration_migrated = migration_status.get("migrated_files", 0)
        migration_failed = migration_status.get("failed_files", 0)
        migration_skipped = migration_status.get("skipped_files", 0)

        points.append(
            MetricPoint(
                name="governance.tempmemory.migration.files",
                value=float(migration_total),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory", "status": "total"},
            )
        )

        points.append(
            MetricPoint(
                name="governance.tempmemory.migration.files",
                value=float(migration_migrated),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory", "status": "migrated"},
            )
        )

        points.append(
            MetricPoint(
                name="governance.tempmemory.migration.files",
                value=float(migration_failed),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory", "status": "failed"},
            )
        )

        points.append(
            MetricPoint(
                name="governance.tempmemory.migration.files",
                value=float(migration_skipped),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory", "status": "skipped"},
            )
        )

        # 7. Migration success rate
        if migration_total > 0:
            migration_success_rate = (migration_migrated / migration_total) * 100
        else:
            migration_success_rate = 0.0
        points.append(
            MetricPoint(
                name="governance.tempmemory.migration.success_rate",
                value=migration_success_rate,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
                fields={"unit": "percent"},
            )
        )

        # 8. Files by type (from provenance data)
        files_by_type = self._get_files_by_type()
        for memory_type, count in files_by_type.items():
            points.append(
                MetricPoint(
                    name="governance.tempmemory.files.by_type",
                    value=float(count),
                    metric_type=MetricType.GAUGE,
                    timestamp=now,
                    tags={"feature": "tempmemory", "memory_type": memory_type},
                )
            )

        # 9. Last run timestamp (as seconds since epoch for easier querying)
        last_run = ingestion_status.get("last_run")
        if last_run:
            try:
                last_run_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                seconds_since_last_run = (now - last_run_dt).total_seconds()
            except (ValueError, TypeError):
                seconds_since_last_run = 0
        else:
            seconds_since_last_run = 0

        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.last_run_age",
                value=seconds_since_last_run,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
                fields={"unit": "seconds"},
            )
        )

        # 10. Last run success status
        last_success = 1.0 if ingestion_status.get("last_success", False) else 0.0
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.last_run_success",
                value=last_success,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
            )
        )

        # 11. Consecutive failures (calculated from status history)
        consecutive_failures = self._get_consecutive_failures()
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.consecutive_failures",
                value=float(consecutive_failures),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
            )
        )

        # 12. Backlog count (files pending ingestion)
        backlog = self._get_backlog_count()
        points.append(
            MetricPoint(
                name="governance.tempmemory.ingestion.backlog",
                value=float(backlog),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
            )
        )

        # 13. Feature flag state
        is_enabled = self._is_feature_enabled()
        points.append(
            MetricPoint(
                name="governance.tempmemory.enabled",
                value=1.0 if is_enabled else 0.0,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "tempmemory"},
            )
        )

        return points

    def _get_ingestion_status(self) -> dict[str, Any]:
        """Get ingestion status from Redis."""
        if self._redis_client is None:
            return {}

        try:
            status_data = self._redis_client.get(INGESTION_STATUS_KEY)
            if status_data:
                data_str = (
                    status_data.decode()
                    if isinstance(status_data, bytes)
                    else status_data
                )
                return json.loads(data_str)
        except Exception as e:
            logger.warning(f"Failed to get ingestion status: {e}")

        return {}

    def _get_migration_status(self) -> dict[str, Any]:
        """Get migration status from Redis."""
        if self._redis_client is None:
            return {}

        try:
            status_data = self._redis_client.get(MIGRATION_STATUS_KEY)
            if status_data:
                data_str = (
                    status_data.decode()
                    if isinstance(status_data, bytes)
                    else status_data
                )
                return json.loads(data_str)
        except Exception as e:
            logger.warning(f"Failed to get migration status: {e}")

        return {}

    def _get_files_by_type(self) -> dict[str, int]:
        """Get count of files by memory type from provenance data."""
        files_by_type: dict[str, int] = {
            "decision": 0,
            "pattern": 0,
            "summary": 0,
            "anti-pattern": 0,
            "unknown": 0,
        }

        if self._redis_client is None:
            return files_by_type

        try:
            # Scan for provenance keys
            cursor = 0
            while True:
                cursor, keys = self._redis_client.scan(
                    cursor=cursor, match=f"{PROVENANCE_PREFIX}:*", count=100
                )

                for key in keys:
                    try:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        # Extract type from key or hash data
                        data = self._redis_client.hgetall(key_str)
                        if data:
                            memory_type = None
                            if isinstance(data, dict):
                                memory_type = data.get(b"type", data.get("type"))
                            if memory_type:
                                type_str = (
                                    memory_type.decode()
                                    if isinstance(memory_type, bytes)
                                    else memory_type
                                )
                                if type_str in files_by_type:
                                    files_by_type[type_str] += 1
                                else:
                                    files_by_type["unknown"] += 1
                    except Exception:
                        continue

                if cursor == 0:
                    break

        except Exception as e:
            logger.warning(f"Failed to get files by type: {e}")

        return files_by_type

    def _get_consecutive_failures(self) -> int:
        """Get count of consecutive ingestion failures."""
        if self._redis_client is None:
            return 0

        try:
            # Check for consecutive failures key
            failures = self._redis_client.get(
                f"{TEMPMEMORY_PREFIX}:consecutive_failures"
            )
            if failures:
                return int(failures)
        except Exception as e:
            logger.warning(f"Failed to get consecutive failures: {e}")

        return 0

    def _get_backlog_count(self) -> int:
        """Get count of files pending ingestion."""
        if self._redis_client is None:
            return 0

        try:
            # Count files in migration status that are pending
            status_data = self._redis_client.hgetall(MIGRATION_STATUS_KEY)
            if status_data:
                pending_count = 0
                for _file_path, status_json in status_data.items():
                    try:
                        status_str = (
                            status_json.decode()
                            if isinstance(status_json, bytes)
                            else status_json
                        )
                        status_data = json.loads(status_str)
                        if status_data.get("status") in ("pending", "in_progress"):
                            pending_count += 1
                    except Exception:
                        continue
                return pending_count
        except Exception as e:
            logger.warning(f"Failed to get backlog count: {e}")

        return 0

    def _is_feature_enabled(self) -> bool:
        """Check if tempmemory ingestion feature is enabled."""
        if self._redis_client is None:
            return False

        try:
            val: bytes | str | None = self._redis_client.get(
                "chise:feature_flags:governance:tempmemory_ingestion_enabled"
            )
            return val == b"true" or val == "true"
        except Exception:
            pass

        return False

    # Methods for updating metrics (called by ingestion runner)
    def record_ingestion_run(
        self,
        files_processed: int,
        files_ingested: int,
        files_failed: int,
        duration_seconds: float,
    ) -> None:
        """Record an ingestion run."""
        if self._redis_client is None:
            return

        try:
            status = {
                "last_run": datetime.now(UTC).isoformat(),
                "last_success": files_failed == 0,
                "total_files_processed": files_processed,
                "total_files_ingested": files_ingested,
                "total_files_failed": files_failed,
                "duration_seconds": duration_seconds,
            }
            self._redis_client.set(INGESTION_STATUS_KEY, json.dumps(status))

            # Update consecutive failures counter
            if files_failed > 0:
                self._redis_client.incr(f"{TEMPMEMORY_PREFIX}:consecutive_failures")
            else:
                self._redis_client.delete(f"{TEMPMEMORY_PREFIX}:consecutive_failures")

        except Exception as e:
            logger.warning(f"Could not record ingestion run to Redis: {e}")

    def record_migration_run(
        self,
        total_files: int,
        migrated_files: int,
        failed_files: int,
        skipped_files: int,
    ) -> None:
        """Record a migration run."""
        if self._redis_client is None:
            return

        try:
            status = {
                "timestamp": datetime.now(UTC).isoformat(),
                "total_files": total_files,
                "migrated_files": migrated_files,
                "failed_files": failed_files,
                "skipped_files": skipped_files,
            }
            self._redis_client.set(MIGRATION_STATUS_KEY, json.dumps(status))
        except Exception as e:
            logger.warning(f"Could not record migration run to Redis: {e}")
