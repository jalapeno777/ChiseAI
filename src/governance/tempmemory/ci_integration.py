"""
CI Integration Module for Tempmemory Ingestion.

Provides functions to run tempmemory ingestion as part of CI pipeline,
with support for caching, validation, and reporting.

This module is part of ST-MEMORY-INGEST-005.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from governance.tempmemory.ingestion_runner import (
    TempmemoryIngestionRunner,
)
from governance.tempmemory.migration import MigrationStatus

logger = logging.getLogger(__name__)

# Feature flag environment variable
FEATURE_FLAG_ENV = "CI_TEMPMEMORY_INGESTION_ENABLED"

# Redis keys for CI caching
CI_CACHE_KEY_PREFIX = "bmad:chiseai:tempmemory:ci_cache"
CI_INGESTION_REPORT_KEY = f"{CI_CACHE_KEY_PREFIX}:last_report"
CI_INGESTED_MEMORIES_KEY = f"{CI_CACHE_KEY_PREFIX}:ingested_memories"


@dataclass
class CIIngestionReport:
    """Report of CI ingestion run."""

    success: bool
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    files_processed: int = 0
    files_ingested: int = 0
    files_failed: int = 0
    files_skipped: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    ingested_memory_ids: list[str] = field(default_factory=list)
    pipeline_id: str | None = None
    git_commit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "timestamp": self.timestamp,
            "files_processed": self.files_processed,
            "files_ingested": self.files_ingested,
            "files_failed": self.files_failed,
            "files_skipped": self.files_skipped,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "ingested_memory_ids": self.ingested_memory_ids,
            "pipeline_id": self.pipeline_id,
            "git_commit": self.git_commit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CIIngestionReport:
        """Create from dictionary."""
        return cls(
            success=data.get("success", False),
            timestamp=data.get("timestamp", datetime.now(UTC).isoformat()),
            files_processed=data.get("files_processed", 0),
            files_ingested=data.get("files_ingested", 0),
            files_failed=data.get("files_failed", 0),
            files_skipped=data.get("files_skipped", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            errors=data.get("errors", []),
            ingested_memory_ids=data.get("ingested_memory_ids", []),
            pipeline_id=data.get("pipeline_id"),
            git_commit=data.get("git_commit"),
        )

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


def is_ingestion_enabled() -> bool:
    """
    Check if tempmemory ingestion is enabled via feature flag.

    Returns:
        True if ingestion is enabled, False otherwise.
    """
    value = os.getenv(FEATURE_FLAG_ENV, "false").lower()
    return value in ("true", "1", "yes", "on")


def create_redis_client() -> Any | None:
    """
    Create a Redis client if available.

    Returns:
        Redis client if connection successful, None otherwise.
    """
    try:
        import redis as redis_lib

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD", None)

        client = redis_lib.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        logger.info(f"Redis connected: {redis_host}:{redis_port}")
        return client
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def create_qdrant_client() -> Any | None:
    """
    Create a Qdrant client if available.

    Returns:
        Qdrant client if connection successful, None otherwise.
    """
    try:
        from qdrant_client import QdrantClient

        qdrant_host = os.getenv("QDRANT_HOST", "host.docker.internal")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6334"))

        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        logger.info(f"Qdrant connected: {qdrant_host}:{qdrant_port}")
        return client
    except Exception as e:
        logger.warning(f"Qdrant not available: {e}")
        return None


def run_pre_eval_ingestion(
    dry_run: bool = False,
    force: bool = False,
    tempmemory_path: str | Path | None = None,
) -> CIIngestionReport:
    """
    Run tempmemory ingestion before BrainEval.

    This function runs the ingestion runner and generates a report
    suitable for CI consumption.

    Args:
        dry_run: If True, don't actually ingest (for testing).
        force: If True, re-ingest already processed files.
        tempmemory_path: Optional path to tempmemory directory.

    Returns:
        CIIngestionReport with detailed results.

    Raises:
        RuntimeError: If ingestion fails critically.
    """
    logger.info("Starting pre-evaluation tempmemory ingestion")

    # Check feature flag
    if not is_ingestion_enabled():
        logger.info(f"{FEATURE_FLAG_ENV}=false, skipping ingestion")
        return CIIngestionReport(
            success=True,
            errors=["Ingestion skipped (feature flag disabled)"],
        )

    # Create clients
    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    # Initialize runner
    runner = TempmemoryIngestionRunner(
        redis_client=redis_client,
        qdrant_client=qdrant_client,
        tempmemory_path=tempmemory_path,
        dry_run=dry_run,
        force=force,
    )

    # Run ingestion
    start_time = datetime.now(UTC)
    try:
        report = runner.run_with_lock()
    except RuntimeError as e:
        logger.error(f"Ingestion failed to acquire lock: {e}")
        return CIIngestionReport(
            success=False,
            errors=[f"Lock acquisition failed: {e}"],
        )
    except Exception as e:
        logger.exception("Ingestion failed with exception")
        return CIIngestionReport(
            success=False,
            errors=[f"Exception: {e}"],
        )

    duration = (datetime.now(UTC) - start_time).total_seconds()

    # Build report
    ci_report = CIIngestionReport(
        success=(report.failed_files == 0),
        files_processed=report.total_files,
        files_ingested=report.migrated_files,
        files_failed=report.failed_files,
        files_skipped=report.skipped_files,
        duration_seconds=duration,
        pipeline_id=os.getenv("CI_PIPELINE_NUMBER"),
        git_commit=os.getenv("CI_COMMIT_SHA"),
    )

    # Collect errors from failed results
    for result in report.results:
        if result.status == MigrationStatus.FAILED and result.error_message:
            ci_report.errors.append(f"{result.file_path}: {result.error_message}")

    # Collect ingested memory IDs
    for result in report.results:
        if result.status == MigrationStatus.COMPLETED:
            # Extract memory ID from file path
            memory_id = Path(result.file_path).stem
            ci_report.ingested_memory_ids.append(memory_id)

    # Cache the report
    cache_ingestion_report(ci_report, redis_client)
    cache_ingested_memories(ci_report.ingested_memory_ids, redis_client)

    logger.info(
        f"Pre-evaluation ingestion completed: "
        f"{ci_report.files_ingested} ingested, "
        f"{ci_report.files_failed} failed, "
        f"{ci_report.files_skipped} skipped"
    )

    return ci_report


def validate_ingestion_success(report: CIIngestionReport) -> bool:
    """
    Validate that ingestion completed successfully.

    Args:
        report: The ingestion report to validate.

    Returns:
        True if ingestion was successful, False otherwise.
    """
    if not report.success:
        logger.error(f"Ingestion failed with {len(report.errors)} errors")
        return False

    if report.files_failed > 0:
        logger.error(f"Ingestion had {report.files_failed} failed files")
        return False

    logger.info("Ingestion validation passed")
    return True


def cache_ingestion_report(
    report: CIIngestionReport, redis_client: Any | None = None
) -> bool:
    """
    Cache ingestion report in Redis for CI steps.

    Args:
        report: The report to cache.
        redis_client: Optional Redis client.

    Returns:
        True if cached successfully, False otherwise.
    """
    if redis_client is None:
        redis_client = create_redis_client()

    if redis_client is None:
        logger.warning("Redis not available, skipping report cache")
        return False

    try:
        redis_client.set(
            CI_INGESTION_REPORT_KEY,
            json.dumps(report.to_dict()),
            ex=3600,  # 1 hour TTL
        )
        logger.debug("Ingestion report cached")
        return True
    except Exception as e:
        logger.warning(f"Failed to cache ingestion report: {e}")
        return False


def cache_ingested_memories(
    memory_ids: list[str], redis_client: Any | None = None
) -> bool:
    """
    Cache list of ingested memory IDs for subsequent CI steps.

    Args:
        memory_ids: List of memory IDs that were ingested.
        redis_client: Optional Redis client.

    Returns:
        True if cached successfully, False otherwise.
    """
    if redis_client is None:
        redis_client = create_redis_client()

    if redis_client is None:
        logger.warning("Redis not available, skipping memory cache")
        return False

    try:
        # Use a Redis set for efficient membership testing
        if memory_ids:
            redis_client.sadd(CI_INGESTED_MEMORIES_KEY, *memory_ids)
            redis_client.expire(CI_INGESTED_MEMORIES_KEY, 3600)  # 1 hour TTL
        logger.debug(f"Cached {len(memory_ids)} ingested memory IDs")
        return True
    except Exception as e:
        logger.warning(f"Failed to cache ingested memories: {e}")
        return False


def get_ingestion_report(redis_client: Any | None = None) -> CIIngestionReport | None:
    """
    Retrieve cached ingestion report.

    Args:
        redis_client: Optional Redis client.

    Returns:
        CIIngestionReport if found, None otherwise.
    """
    if redis_client is None:
        redis_client = create_redis_client()

    if redis_client is None:
        logger.warning("Redis not available, cannot retrieve report")
        return None

    try:
        data = redis_client.get(CI_INGESTION_REPORT_KEY)
        if data:
            if isinstance(data, bytes):
                data = data.decode()
            return CIIngestionReport.from_dict(json.loads(data))
        return None
    except Exception as e:
        logger.warning(f"Failed to retrieve ingestion report: {e}")
        return None


def get_cached_memories(redis_client: Any | None = None) -> list[str]:
    """
    Get list of ingested memory IDs from cache.

    Args:
        redis_client: Optional Redis client.

    Returns:
        List of memory IDs.
    """
    if redis_client is None:
        redis_client = create_redis_client()

    if redis_client is None:
        logger.warning("Redis not available, cannot retrieve cached memories")
        return []

    try:
        members = redis_client.smembers(CI_INGESTED_MEMORIES_KEY)
        return [m.decode() if isinstance(m, bytes) else m for m in members]
    except Exception as e:
        logger.warning(f"Failed to retrieve cached memories: {e}")
        return []


def is_memory_ingested(memory_id: str, redis_client: Any | None = None) -> bool:
    """
    Check if a specific memory was ingested in this CI run.

    Args:
        memory_id: The memory ID to check.
        redis_client: Optional Redis client.

    Returns:
        True if memory was ingested, False otherwise.
    """
    if redis_client is None:
        redis_client = create_redis_client()

    if redis_client is None:
        logger.warning("Redis not available, cannot check memory status")
        return False

    try:
        return redis_client.sismember(CI_INGESTED_MEMORIES_KEY, memory_id)
    except Exception as e:
        logger.warning(f"Failed to check memory status: {e}")
        return False


def format_report_for_logs(report: CIIngestionReport) -> str:
    """
    Format ingestion report for CI logs.

    Args:
        report: The report to format.

    Returns:
        Formatted string for logging.
    """
    lines = [
        "=" * 60,
        "TEMPMEMORY INGESTION REPORT",
        "=" * 60,
        f"Timestamp: {report.timestamp}",
        f"Pipeline ID: {report.pipeline_id or 'N/A'}",
        f"Git Commit: {report.git_commit or 'N/A'}",
        "",
        f"Files Processed: {report.files_processed}",
        f"Files Ingested:  {report.files_ingested}",
        f"Files Failed:    {report.files_failed}",
        f"Files Skipped:   {report.files_skipped}",
        f"Duration:        {report.duration_seconds:.2f}s",
        "",
        f"Success: {'YES' if report.success else 'NO'}",
    ]

    if report.errors:
        lines.extend(
            [
                "",
                f"Errors ({len(report.errors)}):",
            ]
        )
        for error in report.errors[:10]:  # Limit to first 10 errors
            lines.append(f"  - {error}")
        if len(report.errors) > 10:
            lines.append(f"  ... and {len(report.errors) - 10} more")

    if report.ingested_memory_ids:
        lines.extend(
            [
                "",
                f"Ingested Memories ({len(report.ingested_memory_ids)}):",
            ]
        )
        for memory_id in report.ingested_memory_ids[:10]:  # Limit to first 10
            lines.append(f"  - {memory_id}")
        if len(report.ingested_memory_ids) > 10:
            lines.append(f"  ... and {len(report.ingested_memory_ids) - 10} more")

    lines.append("=" * 60)

    return "\n".join(lines)


def should_fail_ci(report: CIIngestionReport, strict: bool = False) -> bool:
    """
    Determine if CI should fail based on ingestion results.

    Args:
        report: The ingestion report.
        strict: If True, fail on any failure. If False, only fail on critical errors.

    Returns:
        True if CI should fail, False otherwise.
    """
    # If feature flag is disabled, never fail
    if not is_ingestion_enabled():
        return False

    # Always fail on lock acquisition errors (indicates infrastructure issue)
    for error in report.errors:
        if "Lock acquisition failed" in error:
            logger.error("Critical: Lock acquisition failed")
            return True

    if strict:
        # In strict mode, any failure causes CI to fail
        return not report.success or report.files_failed > 0
    else:
        # In non-strict mode, only fail if all files failed
        return report.files_failed > 0 and report.files_ingested == 0


# Export public API
__all__ = [
    "CIIngestionReport",
    "is_ingestion_enabled",
    "run_pre_eval_ingestion",
    "validate_ingestion_success",
    "cache_ingestion_report",
    "cache_ingested_memories",
    "get_ingestion_report",
    "get_cached_memories",
    "is_memory_ingested",
    "format_report_for_logs",
    "should_fail_ci",
    "FEATURE_FLAG_ENV",
]
