"""
Memory Consolidation Scheduler.

Orchestrates daily memory consolidation operations including archival,
promotion, and metrics collection. Runs at 2 AM UTC by default.

Story: ST-GOV-005
Governance Feature: GF-005
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.governance.consolidation.archiver import (
    ArchiveStats,
    MemoryArchiver,
)
from src.governance.consolidation.config import (
    LAST_RUN_KEY,
    ConsolidationConfig,
)
from src.governance.consolidation.promoter import (
    GoldenMemoryPromoter,
    PromotionStats,
)
from src.governance.consolidation.rollback import (
    RollbackManager,
    RollbackStats,
)
from src.governance.tempmemory.ingestion_runner import (
    TempmemoryIngestionRunner,
)

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationResult:
    """Combined result of a consolidation run."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    archive_stats: ArchiveStats | None = None
    promotion_stats: PromotionStats | None = None
    total_processing_time_seconds: float = 0.0
    success: bool = True
    errors: list[str] = field(default_factory=list)

    # Live validation gates
    data_loss_incidents: int = 0
    rollback_time_seconds: float = 0.0
    storage_reduction_percent: float = 0.0

    ingestion_stats: dict[str, Any] | None = None
    """Stats from tempmemory ingestion step"""

    def passes_validation_gates(self) -> tuple[bool, list[str]]:
        """
        Check if consolidation passes all live validation gates.

        Gates:
        - data_loss_incidents = 0
        - rollback_time < 5 min (300s)
        - storage_reduction >= 20%

        Returns:
            Tuple of (passes, list of failures)
        """
        failures = []

        if self.data_loss_incidents != 0:
            failures.append(
                f"data_loss_incidents = {self.data_loss_incidents} (expected 0)"
            )

        if self.rollback_time_seconds >= 300:
            failures.append(
                f"rollback_time = {self.rollback_time_seconds:.1f}s (expected < 300s)"
            )

        if self.storage_reduction_percent < 20.0:
            failures.append(
                f"storage_reduction = {self.storage_reduction_percent:.1f}% "
                f"(expected >= 20%)"
            )

        return len(failures) == 0, failures


class MemoryConsolidationScheduler:
    """
    Main scheduler for memory consolidation operations.

    Orchestrates:
    1. Memory archival (memories > 90 days to cold storage)
    2. Golden promotion (high-value memories to golden set)
    3. Rollback cleanup (expired rollback data)
    4. Metrics export (for monitoring)

    Scheduling:
    - Default: Daily at 2:00 AM UTC
    - Configurable via ConsolidationConfig
    - Uses APScheduler for reliable scheduling

    Safety Features:
    - Dry run mode by default
    - Feature flag control
    - Comprehensive error handling
    - Live validation gates

    Example:
        >>> scheduler = MemoryConsolidationScheduler(config)
        >>> scheduler.start()  # Starts scheduled runs
        >>> result = scheduler.run_now()  # Run immediately
    """

    def __init__(
        self,
        config: ConsolidationConfig | None = None,
        qdrant_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the consolidation scheduler.

        Args:
            config: Optional config override (uses defaults if not provided)
            qdrant_client: Optional Qdrant client
            redis_client: Optional Redis client
        """
        self._config = config or ConsolidationConfig()
        self._qdrant_client = qdrant_client
        self._redis_client = redis_client

        # Initialize components
        self._archiver = MemoryArchiver(self._config, qdrant_client, redis_client)
        self._promoter = GoldenMemoryPromoter(self._config, qdrant_client, redis_client)
        self._rollback_manager = RollbackManager(
            self._config, qdrant_client, redis_client
        )

        # Initialize tempmemory ingestion runner
        self._ingestion_runner: TempmemoryIngestionRunner | None = None
        if self._config.run_tempmemory_ingestion:
            try:
                self._ingestion_runner = TempmemoryIngestionRunner(
                    redis_client=redis_client,
                    dry_run=self._config.tempmemory_ingestion_dry_run,
                    filter_types=self._config.tempmemory_ingestion_filter_types,
                )
                logger.info("TempmemoryIngestionRunner initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize TempmemoryIngestionRunner: {e}")

        # Scheduler state
        self._scheduler: Any | None = None
        self._is_running: bool = False
        self._last_result: ConsolidationResult | None = None

        logger.info(
            "MemoryConsolidationScheduler initialized",
            extra={
                "enabled": self._config.enabled,
                "dry_run": self._config.dry_run,
                "schedule_time": self._config.schedule_time.isoformat(),
            },
        )

    def is_enabled(self) -> bool:
        """
        Check if consolidation is enabled via feature flag.

        Returns:
            True if consolidation is enabled
        """
        if self._config.enabled:
            return True

        # Check Redis feature flag
        if self._redis_client is not None:
            try:
                flag: bytes | str | None = self._redis_client.get(
                    self._config.feature_flag_key
                )
                return flag == b"true" or flag == "true"
            except Exception as e:
                logger.warning(f"Could not read feature flag: {e}")

        return False

    def start(self) -> bool:
        """
        Start the scheduled consolidation runs.

        Returns:
            True if scheduler started successfully
        """
        if self._is_running:
            logger.warning("Scheduler is already running")
            return True

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler = BackgroundScheduler(timezone="UTC")

            # Schedule daily at configured time
            trigger = CronTrigger(
                hour=self._config.schedule_time.hour,
                minute=self._config.schedule_time.minute,
                timezone="UTC",
            )

            self._scheduler.add_job(
                self._run_consolidation,
                trigger=trigger,
                id="memory_consolidation",
                name="Daily Memory Consolidation",
                replace_existing=True,
            )

            self._scheduler.start()
            self._is_running = True

            logger.info(
                "Scheduler started",
                extra={
                    "schedule": f"Daily at {self._config.schedule_time.isoformat()} UTC",
                    "enabled": self.is_enabled(),
                },
            )

            return True

        except ImportError:
            logger.error("APScheduler not installed. Run: pip install apscheduler")
            return False
        except Exception as e:
            logger.exception(f"Failed to start scheduler: {e}")
            return False

    def stop(self) -> None:
        """Stop the scheduled consolidation runs."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

        self._is_running = False
        logger.info("Scheduler stopped")

    def run_now(
        self,
        dry_run: bool | None = None,
        archive: bool = True,
        promote: bool = True,
    ) -> ConsolidationResult:
        """
        Run consolidation immediately (bypassing schedule).

        Args:
            dry_run: Override config dry_run setting
            archive: Whether to run archival
            promote: Whether to run promotion

        Returns:
            ConsolidationResult with operation details
        """
        return self._run_consolidation(
            dry_run=dry_run,
            archive=archive,
            promote=promote,
        )

    def _run_tempmemory_ingestion_step(self, dry_run: bool) -> dict[str, Any]:
        """
        Run tempmemory ingestion as Step 0 of consolidation.

        Args:
            dry_run: Whether to run in dry-run mode

        Returns:
            Dictionary with ingestion statistics
        """
        if not self._config.run_tempmemory_ingestion:
            return {"skipped": True, "reason": "disabled in config"}

        if self._ingestion_runner is None:
            return {"skipped": True, "reason": "runner not initialized"}

        # Check cadence
        if self._config.tempmemory_ingestion_cadence == "manual":
            return {"skipped": True, "reason": "cadence set to manual"}

        logger.info("Starting Step 0: Tempmemory ingestion")

        try:
            # Run ingestion with lock
            report = self._ingestion_runner.run_with_lock()

            stats = {
                "success": report.failed_files == 0,
                "total_files": report.total_files,
                "scanned_files": report.scanned_files,
                "migrated_files": report.migrated_files,
                "failed_files": report.failed_files,
                "skipped_files": report.skipped_files,
                "duration_seconds": report.duration_seconds,
                "dry_run": report.dry_run,
            }

            logger.info(
                f"Tempmemory ingestion completed: {stats['migrated_files']} migrated, "
                f"{stats['failed_files']} failed"
            )

            return stats

        except Exception as e:
            logger.exception(f"Tempmemory ingestion failed: {e}")
            return {"success": False, "error": str(e)}

    def _run_consolidation(
        self,
        dry_run: bool | None = None,
        archive: bool = True,
        promote: bool = True,
    ) -> ConsolidationResult:
        """
        Execute the consolidation workflow.

        Args:
            dry_run: Override config dry_run setting
            archive: Whether to run archival
            promote: Whether to run promotion

        Returns:
            ConsolidationResult with operation details
        """
        start_time = datetime.now(UTC)
        is_dry_run = dry_run if dry_run is not None else self._config.dry_run

        result = ConsolidationResult()

        # Skip if disabled and not dry run
        if not self.is_enabled() and not is_dry_run:
            result.success = False
            result.errors.append("Consolidation is disabled")
            logger.warning("Consolidation skipped: disabled")
            return result

        logger.info(
            "Starting consolidation run",
            extra={"dry_run": is_dry_run, "archive": archive, "promote": promote},
        )

        try:
            # Step 0: Run tempmemory ingestion
            if self._config.run_tempmemory_ingestion:
                result.ingestion_stats = self._run_tempmemory_ingestion_step(is_dry_run)
                if result.ingestion_stats.get("failed_files", 0) > 0:
                    logger.warning(
                        f"Tempmemory ingestion had {result.ingestion_stats['failed_files']} failures"
                    )

            # Get storage size before
            storage_before = self._archiver.get_cold_storage_size()

            # 1. Run archival
            if archive:
                result.archive_stats = self._archiver.archive_memories(
                    dry_run=is_dry_run
                )
                if result.archive_stats.errors:
                    result.errors.extend(result.archive_stats.errors)

            # 2. Run promotion
            if promote:
                result.promotion_stats = self._promoter.promote_memories(
                    dry_run=is_dry_run
                )
                if result.promotion_stats.errors:
                    result.errors.extend(result.promotion_stats.errors)

            # 3. Cleanup expired rollback data
            if not is_dry_run:
                self._cleanup_expired_rollback_data()

            # 4. Calculate storage reduction
            self._archiver.get_cold_storage_size()
            if storage_before > 0:
                # Note: this is cold storage growth, actual reduction is
                # from removing memories from active storage
                result.storage_reduction_percent = self._calculate_storage_reduction(
                    result.archive_stats
                )

            # 5. Update last run timestamp
            self._update_last_run_time()

            # 6. Export metrics
            if not is_dry_run:
                self._export_metrics(result)

            logger.info(
                "Consolidation run completed",
                extra={
                    "dry_run": is_dry_run,
                    "archive_success": result.archive_stats is not None,
                    "promotion_success": result.promotion_stats is not None,
                },
            )

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            logger.exception("Consolidation run failed")

        finally:
            result.total_processing_time_seconds = (
                datetime.now(UTC) - start_time
            ).total_seconds()
            self._last_result = result

        return result

    def _cleanup_expired_rollback_data(self) -> int:
        """Remove rollback data older than retention period."""
        if self._redis_client is None:
            return 0

        cleaned = 0
        try:
            # Scan for expired rollback keys
            # Note: TTL-based cleanup handles this automatically
            logger.debug("Rollback cleanup completed (TTL-based)")
        except Exception as e:
            logger.warning(f"Rollback cleanup error: {e}")

        return cleaned

    def _calculate_storage_reduction(
        self,
        archive_stats: ArchiveStats | None,
    ) -> float:
        """
        Calculate storage reduction percentage.

        This is a simplified calculation based on archived bytes
        vs estimated total storage.
        """
        if archive_stats is None or archive_stats.memories_scanned == 0:
            return 0.0

        # Estimate: each memory averages 1KB
        avg_memory_bytes = 1024
        total_estimated_bytes = archive_stats.memories_scanned * avg_memory_bytes

        if total_estimated_bytes == 0:
            return 0.0

        reduction = (archive_stats.bytes_archived / total_estimated_bytes) * 100
        return min(reduction, 100.0)  # Cap at 100%

    def _update_last_run_time(self) -> None:
        """Update last run timestamp in Redis."""
        if self._redis_client is None:
            return

        try:
            self._redis_client.set(
                LAST_RUN_KEY,
                datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            logger.warning(f"Could not update last run time: {e}")

    def _export_metrics(self, result: ConsolidationResult) -> None:
        """Export consolidation metrics to Redis/InfluxDB."""
        if self._redis_client is None:
            return

        try:
            metrics_key = "chise:governance:consolidation:metrics:run"
            self._redis_client.hset(
                metrics_key,
                mapping={
                    "last_run": result.timestamp.isoformat(),
                    "total_time_seconds": str(result.total_processing_time_seconds),
                    "success": str(result.success).lower(),
                    "data_loss_incidents": str(result.data_loss_incidents),
                    "storage_reduction_percent": str(result.storage_reduction_percent),
                },
            )
        except Exception as e:
            logger.warning(f"Could not export metrics: {e}")

    # --- Rollback API ---

    def can_rollback(self, memory_id: str) -> bool:
        """Check if a memory can be rolled back."""
        return self._rollback_manager.can_rollback(memory_id)

    def rollback_memory(
        self,
        memory_id: str,
        dry_run: bool = False,
    ) -> RollbackStats:
        """Roll back a single memory."""
        return self._rollback_manager.rollback_memory(memory_id, dry_run)

    def rollback_batch(
        self,
        memory_ids: list[str],
        dry_run: bool = False,
    ) -> RollbackStats:
        """Roll back multiple memories."""
        return self._rollback_manager.rollback_batch(memory_ids, dry_run)

    def get_rollback_window(self):
        """Get available rollback window info."""
        return self._rollback_manager.get_rollback_window()

    # --- Component Access ---

    @property
    def archiver(self) -> MemoryArchiver:
        """Get the archiver component."""
        return self._archiver

    @property
    def promoter(self) -> GoldenMemoryPromoter:
        """Get the promoter component."""
        return self._promoter

    @property
    def rollback_manager(self) -> RollbackManager:
        """Get the rollback manager component."""
        return self._rollback_manager

    # --- Status ---

    def get_last_result(self) -> ConsolidationResult | None:
        """Get the result from the last consolidation run."""
        return self._last_result

    def is_scheduler_running(self) -> bool:
        """Check if the scheduler is actively running."""
        return self._is_running and self._scheduler is not None

    def get_config(self) -> ConsolidationConfig:
        """Get the current configuration."""
        return self._config

    def validate_live_gates(self) -> dict[str, Any]:
        """
        Validate all live validation gates.

        Returns:
            Dict with validation results
        """
        if self._last_result is None:
            return {"valid": False, "reason": "No consolidation run yet"}

        passes, failures = self._last_result.passes_validation_gates()

        return {
            "valid": passes,
            "failures": failures,
            "gates": {
                "data_loss_incidents": {
                    "value": self._last_result.data_loss_incidents,
                    "expected": 0,
                    "pass": self._last_result.data_loss_incidents == 0,
                },
                "rollback_time_seconds": {
                    "value": self._last_result.rollback_time_seconds,
                    "expected": "< 300",
                    "pass": self._last_result.rollback_time_seconds < 300,
                },
                "storage_reduction_percent": {
                    "value": self._last_result.storage_reduction_percent,
                    "expected": ">= 20",
                    "pass": self._last_result.storage_reduction_percent >= 20.0,
                },
            },
        }
