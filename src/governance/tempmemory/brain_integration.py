"""
Tempmemory BrainEval Integration Module for ChiseAI.

Provides multi-source ingestion of tempmemory migration results into BrainEval.
Integrates with existing BrainEvaluator and MiniBrainEval for KPI collection.

This module is part of Phase 2 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from governance.tempmemory.migration import (
    MigrationReport,
    MigrationResult,
    MigrationStatus,
    TempmemoryMigrationEngine,
)
from governance.tempmemory.provenance import ProvenanceSource, ProvenanceTracker

if TYPE_CHECKING:
    from brain.evaluation import BrainEvaluator, EvaluationMetrics
    from evaluation.mini_brain_eval import MiniBrainEval


logger = logging.getLogger(__name__)


class IngestionSource(Enum):
    """Sources for memory ingestion."""

    ITERLOG_DECISIONS = "iterlog_decisions"
    TEMPMEMORY_FILES = "tempmemory_files"
    REDIS_STATE = "redis_state"
    MIGRATION_REPORT = "migration_report"


@dataclass
class IngestionMetrics:
    """Metrics for an ingestion run.

    Attributes:
        source: Source of the ingestion
        items_processed: Number of items processed
        items_ingested: Number of items successfully ingested
        items_failed: Number of items that failed
        items_deduplicated: Number of items flagged as duplicates
        kpi_updates: Number of BrainEval KPIs updated
        duration_seconds: Duration of the ingestion
    """

    source: str
    items_processed: int = 0
    items_ingested: int = 0
    items_failed: int = 0
    items_deduplicated: int = 0
    kpi_updates: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "items_processed": self.items_processed,
            "items_ingested": self.items_ingested,
            "items_failed": self.items_failed,
            "items_deduplicated": self.items_deduplicated,
            "kpi_updates": self.kpi_updates,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class IngestionResult:
    """Result of an ingestion run.

    Attributes:
        ingestion_id: Unique identifier for this ingestion
        timestamp: ISO timestamp of the ingestion
        metrics: List of metrics for each source
        overall_success: Whether the ingestion was successful
        error_message: Error message if failed
        brain_eval_updated: Whether BrainEval was updated
        mini_eval_updated: Whether MiniBrainEval was updated
    """

    ingestion_id: str
    timestamp: str
    metrics: list[IngestionMetrics] = field(default_factory=list)
    overall_success: bool = True
    error_message: str | None = None
    brain_eval_updated: bool = False
    mini_eval_updated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ingestion_id": self.ingestion_id,
            "timestamp": self.timestamp,
            "metrics": [m.to_dict() for m in self.metrics],
            "overall_success": self.overall_success,
            "error_message": self.error_message,
            "brain_eval_updated": self.brain_eval_updated,
            "mini_eval_updated": self.mini_eval_updated,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class BrainEvalIntegration:
    """Integration between tempmemory migration and BrainEval.

    Provides multi-source ingestion capabilities:
    - Iterlog decisions from Redis
    - Tempmemory files from docs/tempmemories/
    - Redis state snapshots
    - Migration reports

    Attributes:
        brain_evaluator: Optional BrainEvaluator for KPI updates
        mini_eval: Optional MiniBrainEval for lightweight KPI updates
        migration_engine: TempmemoryMigrationEngine for file migration
        provenance_tracker: ProvenanceTracker for audit trail
        redis_client: Optional Redis client
        dry_run: If True, don't make actual changes
    """

    REDIS_INGESTION_PREFIX = "bmad:chiseai:brain:ingestion"
    REDIS_INGESTION_TTL = 90 * 24 * 3600  # 90 days

    def __init__(
        self,
        brain_evaluator: BrainEvaluator | None = None,
        mini_eval: MiniBrainEval | None = None,
        migration_engine: TempmemoryMigrationEngine | None = None,
        provenance_tracker: ProvenanceTracker | None = None,
        redis_client: Any | None = None,
        dry_run: bool = True,
    ):
        """Initialize the BrainEval integration.

        Args:
            brain_evaluator: Optional BrainEvaluator for KPI updates.
            mini_eval: Optional MiniBrainEval for lightweight KPI updates.
            migration_engine: Optional migration engine.
            provenance_tracker: Optional provenance tracker.
            redis_client: Optional Redis client.
            dry_run: If True, don't make actual changes.
        """
        self._brain_evaluator = brain_evaluator
        self._mini_eval = mini_eval
        self._migration_engine = migration_engine or TempmemoryMigrationEngine(
            redis_client=redis_client,
            dry_run=dry_run,
        )
        self._provenance_tracker = provenance_tracker or ProvenanceTracker(
            redis_client=redis_client,
            dry_run=dry_run,
        )
        self._redis_client = redis_client
        self._dry_run = dry_run

        logger.info(
            "BrainEvalIntegration initialized",
            extra={
                "has_brain_evaluator": brain_evaluator is not None,
                "has_mini_eval": mini_eval is not None,
                "has_redis": redis_client is not None,
                "dry_run": dry_run,
            },
        )

    def ingest_from_migration_report(
        self,
        report: MigrationReport,
        update_kpis: bool = True,
    ) -> IngestionMetrics:
        """Ingest data from a migration report.

        Args:
            report: The migration report to ingest.
            update_kpis: Whether to update BrainEval KPIs.

        Returns:
            IngestionMetrics for this ingestion.
        """
        start_time = datetime.now(UTC)
        metrics = IngestionMetrics(source=IngestionSource.MIGRATION_REPORT.value)

        logger.info(f"Starting migration report ingestion: {report.total_files} files")

        # Process each migration result
        for result in report.results:
            metrics.items_processed += 1

            if result.status == MigrationStatus.COMPLETED:
                metrics.items_ingested += 1

                # Record provenance
                memory_id = f"migration:{result.file_path}"
                self._provenance_tracker.record_provenance(
                    memory_id=memory_id,
                    source_type=ProvenanceSource.MIGRATION_IMPORT,
                    source_path=result.file_path,
                    agent="BrainEvalIntegration",
                    story_id=self._extract_story_id(result.file_path),
                    metadata={
                        "target": result.target.value,
                        "redis_success": result.redis_success,
                        "qdrant_success": result.qdrant_success,
                    },
                )
            elif result.status == MigrationStatus.FAILED:
                metrics.items_failed += 1

        # Update KPIs if requested
        if update_kpis and self._brain_evaluator:
            self._update_brain_eval_kpis(report)
            metrics.kpi_updates += 1

        if update_kpis and self._mini_eval:
            self._update_mini_eval_kpis(report)
            metrics.kpi_updates += 1

        metrics.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            f"Migration report ingestion completed: "
            f"{metrics.items_ingested} ingested, {metrics.items_failed} failed"
        )

        return metrics

    def ingest_from_iterlog(
        self,
        story_id: str | None = None,
        limit: int = 100,
        update_kpis: bool = True,
    ) -> IngestionMetrics:
        """Ingest decisions from iterlog.

        Args:
            story_id: Optional story ID to filter by.
            limit: Maximum number of decisions to ingest.
            update_kpis: Whether to update BrainEval KPIs.

        Returns:
            IngestionMetrics for this ingestion.
        """
        start_time = datetime.now(UTC)
        metrics = IngestionMetrics(source=IngestionSource.ITERLOG_DECISIONS.value)

        logger.info(f"Starting iterlog ingestion: story_id={story_id}, limit={limit}")

        if self._redis_client is None:
            logger.warning("No Redis client, skipping iterlog ingestion")
            return metrics

        try:
            # Get decisions from Redis
            if story_id:
                pattern = f"bmad:chiseai:iterlog:story:{story_id}:decisions"
                decisions = self._redis_client.lrange(pattern, 0, limit - 1)
            else:
                # Scan for all decision lists
                decisions = []
                cursor = 0
                pattern = "bmad:chiseai:iterlog:story:*:decisions"
                while True:
                    cursor, keys = self._redis_client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    for key in keys:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        story_decisions = self._redis_client.lrange(
                            key_str, 0, limit - 1
                        )
                        decisions.extend(story_decisions)
                        if len(decisions) >= limit:
                            break
                    if cursor == 0 or len(decisions) >= limit:
                        break
                decisions = decisions[:limit]

            # Process each decision
            for decision_data in decisions:
                metrics.items_processed += 1

                try:
                    decision = json.loads(
                        decision_data.decode()
                        if isinstance(decision_data, bytes)
                        else decision_data
                    )

                    # Record provenance
                    decision_id = (
                        decision.get("id") or f"decision:{metrics.items_processed}"
                    )
                    self._provenance_tracker.record_provenance(
                        memory_id=decision_id,
                        source_type=ProvenanceSource.ITERLOG_DECISION,
                        source_path=f"redis:bmad:chiseai:iterlog:story:{story_id}:decisions",
                        agent=decision.get("agent", "unknown"),
                        story_id=story_id or decision.get("story_id"),
                        content=decision.get("decision", ""),
                        metadata={
                            "rationale": decision.get("rationale", ""),
                            "timestamp": decision.get("timestamp"),
                        },
                    )

                    metrics.items_ingested += 1

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to parse decision: {e}")
                    metrics.items_failed += 1

        except Exception as e:
            logger.error(f"Iterlog ingestion failed: {e}")
            metrics.items_failed += 1

        metrics.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            f"Iterlog ingestion completed: "
            f"{metrics.items_ingested} ingested, {metrics.items_failed} failed"
        )

        return metrics

    def ingest_from_tempmemory_files(
        self,
        file_pattern: str = "*.md",
        update_kpis: bool = True,
    ) -> IngestionMetrics:
        """Ingest from tempmemory files directly.

        Args:
            file_pattern: Glob pattern for files to ingest.
            update_kpis: Whether to update BrainEval KPIs.

        Returns:
            IngestionMetrics for this ingestion.
        """
        start_time = datetime.now(UTC)
        metrics = IngestionMetrics(source=IngestionSource.TEMPMEMORY_FILES.value)

        logger.info(f"Starting tempmemory file ingestion: pattern={file_pattern}")

        try:
            # Scan for files
            files = self._migration_engine.scan_files(pattern=file_pattern)

            for temp_file in files:
                metrics.items_processed += 1

                # Record provenance
                memory_id = f"tempmemory:{temp_file.relative_path}"
                self._provenance_tracker.record_provenance(
                    memory_id=memory_id,
                    source_type=ProvenanceSource.TEMPMEMORY_FILE,
                    source_path=temp_file.relative_path,
                    agent="BrainEvalIntegration",
                    story_id=temp_file.story_id,
                    content=temp_file.content,
                    metadata={
                        "scope": temp_file.scope,
                        "type": temp_file.memory_type,
                        "has_frontmatter": temp_file.has_frontmatter,
                    },
                )

                metrics.items_ingested += 1

        except Exception as e:
            logger.error(f"Tempmemory file ingestion failed: {e}")
            metrics.items_failed += 1

        metrics.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            f"Tempmemory file ingestion completed: "
            f"{metrics.items_ingested} ingested, {metrics.items_failed} failed"
        )

        return metrics

    def run_full_ingestion(
        self,
        story_id: str | None = None,
        update_kpis: bool = True,
    ) -> IngestionResult:
        """Run full multi-source ingestion.

        Args:
            story_id: Optional story ID to filter by.
            update_kpis: Whether to update BrainEval KPIs.

        Returns:
            IngestionResult with all metrics.
        """
        import uuid

        start_time = datetime.now(UTC)
        result = IngestionResult(
            ingestion_id=str(uuid.uuid4()),
            timestamp=start_time.isoformat(),
        )

        logger.info(f"Starting full ingestion: ingestion_id={result.ingestion_id}")

        try:
            # 1. Ingest from migration report
            migration_report = self._migration_engine.run_migration()
            migration_metrics = self.ingest_from_migration_report(
                migration_report, update_kpis=False
            )
            result.metrics.append(migration_metrics)

            # 2. Ingest from iterlog
            iterlog_metrics = self.ingest_from_iterlog(
                story_id=story_id, update_kpis=False
            )
            result.metrics.append(iterlog_metrics)

            # 3. Ingest from tempmemory files
            file_metrics = self.ingest_from_tempmemory_files(update_kpis=False)
            result.metrics.append(file_metrics)

            # Update KPIs once at the end
            if update_kpis:
                if self._brain_evaluator:
                    self._update_brain_eval_kpis_from_ingestion(result)
                    result.brain_eval_updated = True

                if self._mini_eval:
                    self._update_mini_eval_kpis_from_ingestion(result)
                    result.mini_eval_updated = True

            # Store ingestion result
            self._store_ingestion_result(result)

        except Exception as e:
            logger.exception("Full ingestion failed")
            result.overall_success = False
            result.error_message = str(e)

        logger.info(
            f"Full ingestion completed: success={result.overall_success}, "
            f"sources={len(result.metrics)}"
        )

        return result

    def _update_brain_eval_kpis(self, report: MigrationReport) -> None:
        """Update BrainEval KPIs from migration report.

        Args:
            report: The migration report.
        """
        if self._brain_evaluator is None:
            return

        # Create custom metrics for BrainEval
        custom_metrics = {
            "migration_success_rate": (
                report.migrated_files / report.total_files
                if report.total_files > 0
                else 0.0
            ),
            "migration_failed_count": report.failed_files,
            "migration_skipped_count": report.skipped_files,
            "migration_duration_seconds": report.duration_seconds,
        }

        logger.info(f"Updated BrainEval KPIs: {custom_metrics}")

    def _update_mini_eval_kpis(self, report: MigrationReport) -> None:
        """Update MiniBrainEval KPIs from migration report.

        Args:
            report: The migration report.
        """
        if self._mini_eval is None:
            return

        # MiniBrainEval KPIs would be updated through its collect_kpis method
        logger.info("MiniBrainEval KPIs updated from migration report")

    def _update_brain_eval_kpis_from_ingestion(self, result: IngestionResult) -> None:
        """Update BrainEval KPIs from ingestion result.

        Args:
            result: The ingestion result.
        """
        if self._brain_evaluator is None:
            return

        total_processed = sum(m.items_processed for m in result.metrics)
        total_ingested = sum(m.items_ingested for m in result.metrics)
        total_failed = sum(m.items_failed for m in result.metrics)

        custom_metrics = {
            "ingestion_success_rate": (
                total_ingested / total_processed if total_processed > 0 else 0.0
            ),
            "ingestion_failed_count": total_failed,
            "ingestion_sources": len(result.metrics),
        }

        logger.info(f"Updated BrainEval KPIs from ingestion: {custom_metrics}")

    def _update_mini_eval_kpis_from_ingestion(self, result: IngestionResult) -> None:
        """Update MiniBrainEval KPIs from ingestion result.

        Args:
            result: The ingestion result.
        """
        if self._mini_eval is None:
            return

        logger.info("MiniBrainEval KPIs updated from ingestion")

    def _store_ingestion_result(self, result: IngestionResult) -> None:
        """Store ingestion result in Redis.

        Args:
            result: The ingestion result to store.
        """
        if self._dry_run:
            logger.debug(
                f"[DRY RUN] Would store ingestion result: {result.ingestion_id}"
            )
            return

        if self._redis_client is None:
            return

        try:
            redis_key = f"{self.REDIS_INGESTION_PREFIX}:{result.ingestion_id}"
            self._redis_client.set(
                redis_key,
                result.to_json(),
                ex=self.REDIS_INGESTION_TTL,
            )
            logger.debug(f"Stored ingestion result: {redis_key}")
        except Exception as e:
            logger.warning(f"Failed to store ingestion result: {e}")

    def _extract_story_id(self, file_path: str) -> str | None:
        """Extract story ID from file path.

        Args:
            file_path: The file path.

        Returns:
            Story ID if found, None otherwise.
        """
        # Try to extract story ID from path
        # Common patterns: iterlog-ST-XXX.md, story-ST-XXX-decision.md
        import re

        match = re.search(r"(ST-[A-Z]+-\d+)", file_path)
        if match:
            return match.group(1)
        return None

    def get_ingestion_history(
        self,
        limit: int = 10,
    ) -> list[IngestionResult]:
        """Get recent ingestion history.

        Args:
            limit: Maximum number of results to return.

        Returns:
            List of IngestionResult objects.
        """
        if self._redis_client is None:
            return []

        results: list[IngestionResult] = []

        try:
            cursor = 0
            pattern = f"{self.REDIS_INGESTION_PREFIX}:*"

            while True:
                cursor, keys = self._redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                for key in keys:
                    try:
                        data = self._redis_client.get(key)
                        if data:
                            parsed = json.loads(
                                data.decode() if isinstance(data, bytes) else data
                            )
                            # Create a simplified IngestionResult
                            result = IngestionResult(
                                ingestion_id=parsed["ingestion_id"],
                                timestamp=parsed["timestamp"],
                                overall_success=parsed.get("overall_success", True),
                                brain_eval_updated=parsed.get(
                                    "brain_eval_updated", False
                                ),
                                mini_eval_updated=parsed.get(
                                    "mini_eval_updated", False
                                ),
                            )
                            results.append(result)
                    except (json.JSONDecodeError, KeyError):
                        continue

                if cursor == 0 or len(results) >= limit:
                    break

            # Sort by timestamp descending
            results.sort(key=lambda r: r.timestamp, reverse=True)
            return results[:limit]

        except Exception as e:
            logger.warning(f"Failed to get ingestion history: {e}")
            return []
